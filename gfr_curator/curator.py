import os
import sys
import re
from gfr_curator.apis.ncbi import fetch_ncbi_metadata, search_gene_model_by_symbol
from gfr_curator.apis.crossref import fetch_crossref_metadata
from gfr_curator.apis.ols import lookup_ontology_term
from gfr_curator.apis.lis_graphql import resolve_lis_identifier
from gfr_curator.apis.intermine import resolve_symbol_intermine, resolve_gene_name_intermine
from gfr_curator.apis.legumista_mcp import LegumistaMCPClient
from gfr_curator.llm import query_llm, query_gemini_api
from gfr_curator.yaml_generator import build_yaml_document, resolve_filename
from gfr_curator.validator import validate_yaml_file
from rich.console import Console
from rich.syntax import Syntax
from rich.panel import Panel
from rich.markup import escape

console = Console()
err_console = Console(stderr=True)

def format_rich_text(text: str) -> str:
    """
    Formats text containing HTML/XML tags (<i>, <em>, <jats:italic>, <b>, <strong>) for display in Rich console.
    Escapes non-markup brackets to prevent markup errors, and converts HTML italics/bold to Rich tags.
    """
    if not text or not isinstance(text, str):
        return ""
    escaped = escape(str(text))
    # Convert HTML/XML italics tags (<i>, <em>, <jats:italic>, &lt;i&gt;, etc.) to Rich [italic]
    escaped = re.sub(
        r'(?:<(?:\w+:)?(?:i|em|italic)>|&lt;(?:\w+:)?(?:i|em|italic)&gt;)(.*?)(?:</(?:\w+:)?(?:i|em|italic)>|&lt;/(?:\w+:)?(?:i|em|italic)&gt;)',
        r'[italic]\1[/italic]',
        escaped,
        flags=re.IGNORECASE
    )
    # Convert HTML/XML bold tags (<b>, <strong>, <jats:bold>, etc.) to Rich [bold]
    escaped = re.sub(
        r'(?:<(?:\w+:)?(?:b|strong|bold)>|&lt;(?:\w+:)?(?:b|strong|bold)&gt;)(.*?)(?:</(?:\w+:)?(?:b|strong|bold)>|&lt;/(?:\w+:)?(?:b|strong|bold)&gt;)',
        r'[bold]\1[/bold]',
        escaped,
        flags=re.IGNORECASE
    )
    # Strip any dangling or orphan unclosed tags
    escaped = re.sub(
        r'(?:</?(?:\w+:)?(?:i|em|italic|b|strong|bold)>|&lt;/?(?:\w+:)?(?:i|em|italic|b|strong|bold)&gt;)',
        '',
        escaped,
        flags=re.IGNORECASE
    )
    return escaped

def format_citation(authors, first_author, year):
    """
    Formats citation string to match GFR schema regex requirements:
    'Author, Author et al., YEAR', 'Author, Author, YEAR', or 'Author, YEAR'
    """
    if authors:
        if len(authors) == 1:
            return f"{authors[0]}, {year}"
        elif len(authors) == 2:
            return f"{authors[0]}, {authors[1]}, {year}"
        else:
            return f"{authors[0]}, {authors[1]} et al., {year}"
    return f"{first_author}, {year}"

class GFRCurator:
    def __init__(self, doi, api_key=None, model=None, use_mcp=True, mcp_url=None):
        self.doi = doi
        self.api_key = api_key
        self.model = model
        self.use_mcp = use_mcp
        self.mcp_url = mcp_url
        self.mcp_client = None
        
    def execute(self):
        # 0. Connect to Legumista MCP server if enabled
        if self.use_mcp:
            with console.status("[bold cyan]Connecting to Legumista MCP server...[/bold cyan]", spinner="dots"):
                self.mcp_client = LegumistaMCPClient(self.mcp_url)
                if self.mcp_client.is_healthy():
                    console.print(f"[bold green][+] Legumista MCP connected:[/bold green] [cyan]{self.mcp_client.base_url}[/cyan]")
                else:
                    console.print(f"[bold yellow][!] Legumista MCP unavailable at {self.mcp_client.base_url}. Falling back to direct API mode.[/bold yellow]")
                    self.mcp_client = None

        # 1. Fetch live metadata and abstract
        full_text = None
        with console.status("[bold cyan]Fetching metadata and publication...[/bold cyan]", spinner="dots"):
            paper_meta = fetch_ncbi_metadata(self.doi)
            paper_meta["doi"] = self.doi

            # Enrich from Legumista OpenAlex if MCP is connected
            if self.mcp_client:
                oa_meta = self.mcp_client.openalex_by_doi(self.doi)
                if oa_meta:
                    if paper_meta["title"] == "null" and oa_meta.get("title"):
                        paper_meta["title"] = oa_meta["title"]
                    if (not paper_meta.get("authors") or paper_meta.get("first_author") == "Author") and oa_meta.get("authors"):
                        paper_meta["authors"] = oa_meta["authors"]
                        paper_meta["first_author"] = oa_meta.get("first_author", "Author")
                    if paper_meta["year"] == "null" and oa_meta.get("year"):
                        paper_meta["year"] = oa_meta["year"]
                    if not paper_meta.get("abstract") and oa_meta.get("abstract"):
                        paper_meta["abstract"] = oa_meta["abstract"]
                    if paper_meta.get("pmid") == "null" and oa_meta.get("pmid"):
                        paper_meta["pmid"] = oa_meta["pmid"]

            # If abstract still not fetched, fallback to Crossref
            if not paper_meta.get("abstract"):
                console.print("[bold yellow][!] No abstract retrieved from PubMed/OpenAlex. Checking Crossref for metadata...[/bold yellow]")
                crossref_meta = fetch_crossref_metadata(self.doi)
                paper_meta["title"] = paper_meta["title"] if paper_meta["title"] != "null" else crossref_meta["title"]
                if paper_meta["first_author"] == "Author":
                    paper_meta["first_author"] = crossref_meta["first_author"]
                if not paper_meta.get("authors"):
                    paper_meta["authors"] = crossref_meta.get("authors", [paper_meta["first_author"]])
                if paper_meta["year"] == "null":
                    paper_meta["year"] = crossref_meta["year"]

            # Format citation string
            citation = format_citation(paper_meta.get("authors", []), paper_meta.get("first_author", "Author"), paper_meta.get("year", "null"))
            paper_meta["citation"] = citation

            # Fetch open-access full text via Legumista read_paper if MCP is active
            if self.mcp_client:
                full_text = self.mcp_client.read_paper(self.doi)

        console.print("\n[bold green][+] Paper Resolved:[/bold green]")
        console.print(f"    [bold]Title:[/bold]    {format_rich_text(paper_meta['title'])}")
        console.print(f"    [bold]Citation:[/bold] {paper_meta['citation']}")
        console.print(f"    [bold]PMID:[/bold]     {paper_meta['pmid']}")
        console.print(f"    [bold]DOI:[/bold]      {paper_meta['doi']}")
        if full_text:
            console.print(f"    [bold]Full Text:[/bold] [green]Retrieved ({len(full_text):,} chars via Legumista OA)[/green]\n")
        else:
            console.print("    [bold]Full Text:[/bold] [dim]Not available open-access (using abstract)[/dim]\n")

        # 2. Structured Extraction
        if not paper_meta.get("abstract") and not full_text:
            console.print("[bold red][!] Error: No abstract or text could be fetched for this paper, cannot perform LLM extraction.[/bold red]")
            sys.exit(1)

        model_display = self.model or os.environ.get("LLM_MODEL") or os.environ.get("GFR_MODEL") or os.environ.get("GEMINI_MODEL") or "Gemini (LiteLLM)"
        with console.status(f"[bold cyan]Contacting LLM ({model_display})...[/bold cyan]", spinner="dots"):
            extracted_list = query_llm(paper_meta.get("abstract", ""), api_key=self.api_key, model=self.model, full_text=full_text)
        if isinstance(extracted_list, dict):
            extracted_list = [extracted_list]

        all_yaml_contents = []
        output_filename = None
        verified_gene_ids = []

        for extracted in extracted_list:
            gene_symbols = extracted.get("gene_symbols") or ["Unknown"]
            if isinstance(gene_symbols, str):
                gene_symbols = [gene_symbols]
            symbol_label = gene_symbols[0] if gene_symbols else "Unknown"
            console.print(f"[*] Processing extracted gene: [bold magenta]{symbol_label}[/bold magenta]...")

            # 3. Resolve Genus/Species Prefixes
            genus_prefix = "gen"
            species_prefix = "sp"
            sci_name = extracted.get("scientific_name") or ""
            sci_name_parts = sci_name.strip().split(" ")
            if len(sci_name_parts) >= 1 and sci_name_parts[0]:
                genus_prefix = sci_name_parts[0].lower()[:3]
            if len(sci_name_parts) >= 2 and sci_name_parts[1]:
                species_prefix = sci_name_parts[1].lower()[:2]

            gensp = f"{genus_prefix}{species_prefix}"

            # 4. Resolve Canonical LIS ID and Model Name via Legumista InterMine
            lis_gene_id = None
            pub_name = extracted.get("gene_model_pub_name")
            primary_symbol = gene_symbols[0] if gene_symbols and gene_symbols[0] != "Unknown" else None

            # Attempt MCP mine_gene_symbol resolution first
            if self.mcp_client and primary_symbol:
                with console.status(f"Resolving '{primary_symbol}' via Legumista mine_gene_symbol...", spinner="dots"):
                    mcp_records = self.mcp_client.mine_gene_symbol(primary_symbol, taxon=sci_name)
                if mcp_records:
                    # Pick record matching current DOI if possible, otherwise first record
                    matched_rec = mcp_records[0]
                    clean_doi = self.doi.strip().lower()
                    for r in mcp_records:
                        if r.get("doi") and r["doi"].strip().lower() == clean_doi:
                            matched_rec = r
                            break

                    if (not pub_name or pub_name == "~") and matched_rec.get("gene_model_pub_name"):
                        pub_name = matched_rec["gene_model_pub_name"]
                        extracted["gene_model_pub_name"] = pub_name

                    if matched_rec.get("gene_model_full_id"):
                        lis_gene_id = matched_rec["gene_model_full_id"]

                    if matched_rec.get("symbol_long") and (not extracted.get("gene_symbol_long") or extracted["gene_symbol_long"] == primary_symbol):
                        extracted["gene_symbol_long"] = matched_rec["symbol_long"]

                    console.print(f"    -> [green]Resolved via Legumista InterMine: {pub_name} ({lis_gene_id})[/green]")

            # Fallback to direct InterMine lookup if still unresolved
            if (not lis_gene_id or "TODO" in lis_gene_id) and primary_symbol:
                direct_rec = resolve_symbol_intermine(primary_symbol, target_doi=self.doi)
                if direct_rec:
                    if (not pub_name or pub_name == "~") and direct_rec.get("gene_model_pub_name"):
                        pub_name = direct_rec["gene_model_pub_name"]
                        extracted["gene_model_pub_name"] = pub_name
                    if direct_rec.get("gene_model_full_id"):
                        lis_gene_id = direct_rec["gene_model_full_id"]
                    if direct_rec.get("symbol_long") and (not extracted.get("gene_symbol_long") or extracted["gene_symbol_long"] == primary_symbol):
                        extracted["gene_symbol_long"] = direct_rec["symbol_long"]
                    console.print(f"    -> [green]Resolved via direct InterMine: {pub_name} ({lis_gene_id})[/green]")

            # If pub_name was in the paper but lis_gene_id not yet found, lookup pub_name in InterMine
            if (not lis_gene_id or "TODO" in lis_gene_id) and pub_name and pub_name != "~":
                with console.status(f"Resolving model name '{pub_name}' in InterMine...", spinner="dots"):
                    resolved_id = resolve_gene_name_intermine(pub_name) or resolve_lis_identifier(pub_name)
                if resolved_id:
                    console.print(f"    -> [green]Found canonical identifier: {resolved_id}[/green]")
                    lis_gene_id = resolved_id
                else:
                    if pub_name.lower().startswith(gensp) and gensp == "glyma":
                        lis_gene_id = f"glyma.Wm82.gnm2.ann1.{pub_name}"
                    else:
                        lis_gene_id = f"{gensp}.TODO.TODO.{pub_name}"

            # Fallback: search NCBI Gene by primary symbol if pub_name is still missing
            if not pub_name or pub_name == "~":
                if primary_symbol and sci_name:
                    with console.status(f"Searching NCBI Gene for symbol '{primary_symbol}'...", spinner="dots"):
                        resolved_pub_name = search_gene_model_by_symbol(primary_symbol, sci_name)
                    if resolved_pub_name:
                        console.print(f"    -> Found gene model mapping via NCBI: [green]{resolved_pub_name}[/green]")
                        pub_name = resolved_pub_name
                        extracted["gene_model_pub_name"] = pub_name
                        resolved_id = resolve_gene_name_intermine(pub_name) or resolve_lis_identifier(pub_name)
                        if resolved_id:
                            lis_gene_id = resolved_id

            if not lis_gene_id or "TODO" in lis_gene_id:
                placeholder_target = (pub_name if (pub_name and pub_name != "~") else primary_symbol) or "RESOLVE_LIS_ID"
                lis_gene_id = f"{gensp}.TODO.TODO.{placeholder_target}"
            else:
                verified_gene_ids.append(lis_gene_id)

            # 5. Resolve Ontology codes
            resolved_traits = []
            seen_trait_entities = set()
            for trait_kw in extracted.get("traits", []):
                with console.status(f"Querying EBI OLS for ontology term: '{trait_kw}'...", spinner="dots"):
                    term = lookup_ontology_term(trait_kw)
                if term["entity"] not in seen_trait_entities:
                    seen_trait_entities.add(term["entity"])
                    resolved_traits.append(term)

            # Enrich with curated GO terms from Legumista mine_gene_ontology
            if self.mcp_client and pub_name and pub_name != "~":
                with console.status(f"Checking Legumista for curated GO terms on '{pub_name}'...", spinner="dots"):
                    go_terms = self.mcp_client.mine_gene_ontology(pub_name)
                for gt in go_terms:
                    if gt["entity"] not in seen_trait_entities:
                        seen_trait_entities.add(gt["entity"])
                        resolved_traits.append(gt)

            # 6. Build and Write YAML File
            yaml_content = build_yaml_document(extracted, paper_meta, resolved_traits, gensp, lis_gene_id)
            all_yaml_contents.append(yaml_content)

            if not output_filename:
                output_filename = resolve_filename(extracted, paper_meta, gensp)

        # 7. Verification using Legumista verify_ids tool
        if self.mcp_client and self.doi:
            with console.status("[bold cyan]Verifying identifiers with Legumista verify_ids...[/bold cyan]", spinner="dots"):
                verify_parts = [f"DOI: {self.doi}"]
                if verified_gene_ids:
                    verify_parts.append(f"genes: {', '.join(verified_gene_ids)}")
                verify_query = ", ".join(verify_parts)
                verification_report = self.mcp_client.verify_ids(verify_query)
            console.print("\n[bold cyan]=== Legumista Identifier Verification ===[/bold cyan]")
            for line in verification_report.splitlines():
                formatted_line = format_rich_text(line)
                if "FOUND" in line and "NOT FOUND" not in line:
                    console.print(f"[green]{formatted_line}[/green]")
                elif "NOT FOUND" in line or "MISMATCH" in line or "RETRACTED" in line:
                    console.print(f"[yellow]{formatted_line}[/yellow]")
                else:
                    console.print(f"[dim]{formatted_line}[/dim]")
            console.print("=========================================\n")

        final_yaml = "".join(all_yaml_contents)

        console.print(f"\n[*] Generating Gene Function Registry YAML draft -> [bold]{output_filename}[/bold]...")

        try:
            with open(output_filename, "w") as f:
                f.write(final_yaml)
            console.print(f"[bold green][+] Success! Curation draft saved to: {output_filename}[/bold green]")

            # Print Syntax highlighted output
            syntax = Syntax(final_yaml, "yaml", theme="monokai", line_numbers=True)
            console.print("\n=== YAML Curation Document Output ===")
            console.print(syntax)
            console.print("=====================================\n")

            # 8. Automatically validate generated YAML against schema
            is_valid, _ = validate_yaml_file(output_filename, out_console=console, verbose=True)
            if not is_valid:
                console.print("[bold yellow][!] Warning: The generated draft has schema validation errors. Please inspect above.[/bold yellow]\n")

            return output_filename
        except Exception as e:
            console.print(f"[bold red][!] Error: Failed to write output file {output_filename}: {e}[/bold red]")
            return None
