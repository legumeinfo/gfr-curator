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
    def __init__(self, doi, api_key=None, model=None, use_mcp=True, mcp_url=None, debug=False):
        self.doi = doi
        self.api_key = api_key
        self.model = model
        self.use_mcp = use_mcp
        self.mcp_url = mcp_url
        self.debug = debug
        self.mcp_client = None

    def _debug_msg(self, message: str):
        if self.debug:
            console.print(f"[dim yellow][DEBUG] {message}[/dim yellow]")

    def _debug_panel(self, content: str, title: str):
        if self.debug:
            console.print(Panel(
                content,
                title=f"[bold yellow]{title}[/bold yellow]",
                border_style="yellow",
                expand=False
            ))
        
    def execute(self):
        if self.debug:
            self._debug_panel(
                f"[bold]Target DOI:[/bold] {self.doi}\n"
                f"[bold]Model:[/bold] {self.model or os.environ.get('LLM_MODEL') or 'Default provider'}\n"
                f"[bold]MCP Enabled:[/bold] {self.use_mcp} (URL: {self.mcp_url or 'https://mcp.legumeinfo.org'})\n"
                f"[bold]Debug Mode:[/bold] Enabled (displaying diagnostic details)",
                "Debug: Configuration"
            )

        # 0. Connect to Legumista MCP server if enabled
        if self.use_mcp:
            self._debug_msg(f"Initializing connection to Legumista MCP server: {self.mcp_url or 'https://mcp.legumeinfo.org'}")
            with console.status("[bold cyan]Connecting to Legumista MCP server...[/bold cyan]", spinner="dots"):
                self.mcp_client = LegumistaMCPClient(self.mcp_url)
                if self.mcp_client.is_healthy():
                    console.print(f"[bold green][+] Legumista MCP connected:[/bold green] [cyan]{self.mcp_client.base_url}[/cyan]")
                    self._debug_msg(f"MCP handshake successful (session_id: {self.mcp_client.session_id or 'none'})")
                else:
                    console.print(f"[bold yellow][!] Legumista MCP unavailable at {self.mcp_client.base_url}. Falling back to direct API mode.[/bold yellow]")
                    self._debug_msg("MCP endpoint unreachable or failed handshake. Falling back to direct REST & InterMine queries.")
                    self.mcp_client = None
        else:
            self._debug_msg("Legumista MCP is disabled via flag. Direct API lookups will be used.")

        # 1. Fetch live metadata and abstract
        full_text = None
        self._debug_panel(
            f"Resolving metadata for DOI '{self.doi}':\n"
            f"1. Query Europe PMC REST API for PMID, title, authors, and publication year.\n"
            f"2. Query NCBI E-utilities (efetch) for abstract XML if PMID was resolved.\n"
            f"3. Query Legumista MCP 'openalex_by_doi' to enrich missing fields.\n"
            f"4. Fallback to Crossref API if abstract is still not found.\n"
            f"5. Check Legumista MCP 'read_paper' for open-access full-text retrieval.",
            "Debug: Metadata Retrieval"
        )

        with console.status("[bold cyan]Fetching metadata and publication...[/bold cyan]", spinner="dots"):
            self._debug_msg(f"Querying Europe PMC / NCBI EFetch for DOI '{self.doi}'...")
            paper_meta = fetch_ncbi_metadata(self.doi)
            paper_meta["doi"] = self.doi
            self._debug_msg(
                f"NCBI / Europe PMC result: PMID={paper_meta.get('pmid')}, "
                f"Title={'resolved' if paper_meta.get('title') != 'null' else 'null'}, "
                f"Year={paper_meta.get('year')}, "
                f"Authors={len(paper_meta.get('authors', []))}, "
                f"Abstract={len(paper_meta.get('abstract', ''))} chars"
            )

            # Enrich from Legumista OpenAlex if MCP is connected
            if self.mcp_client:
                self._debug_msg(f"Querying OpenAlex via Legumista MCP 'openalex_by_doi' for '{self.doi}'...")
                oa_meta = self.mcp_client.openalex_by_doi(self.doi)
                if oa_meta:
                    self._debug_msg("OpenAlex metadata retrieved; checking for missing fields to merge...")
                    if paper_meta["title"] == "null" and oa_meta.get("title"):
                        self._debug_msg(f"Filled title from OpenAlex: {oa_meta['title'][:60]}...")
                        paper_meta["title"] = oa_meta["title"]
                    if (not paper_meta.get("authors") or paper_meta.get("first_author") == "Author") and oa_meta.get("authors"):
                        self._debug_msg(f"Filled authors from OpenAlex ({len(oa_meta['authors'])} authors)")
                        paper_meta["authors"] = oa_meta["authors"]
                        paper_meta["first_author"] = oa_meta.get("first_author", "Author")
                    if paper_meta["year"] == "null" and oa_meta.get("year"):
                        self._debug_msg(f"Filled publication year from OpenAlex: {oa_meta['year']}")
                        paper_meta["year"] = oa_meta["year"]
                    if not paper_meta.get("abstract") and oa_meta.get("abstract"):
                        self._debug_msg(f"Filled abstract from OpenAlex ({len(oa_meta['abstract'])} chars)")
                        paper_meta["abstract"] = oa_meta["abstract"]
                    if paper_meta.get("pmid") == "null" and oa_meta.get("pmid"):
                        self._debug_msg(f"Filled PMID from OpenAlex: {oa_meta['pmid']}")
                        paper_meta["pmid"] = oa_meta["pmid"]

            # If abstract still not fetched, fallback to Crossref
            if not paper_meta.get("abstract"):
                self._debug_msg("Abstract missing after Europe PMC and OpenAlex. Initiating Crossref API fallback...")
                console.print("[bold yellow][!] No abstract retrieved from PubMed/OpenAlex. Checking Crossref for metadata...[/bold yellow]")
                crossref_meta = fetch_crossref_metadata(self.doi)
                paper_meta["title"] = paper_meta["title"] if paper_meta["title"] != "null" else crossref_meta["title"]
                if paper_meta["first_author"] == "Author":
                    paper_meta["first_author"] = crossref_meta["first_author"]
                if not paper_meta.get("authors"):
                    paper_meta["authors"] = crossref_meta.get("authors", [paper_meta["first_author"]])
                if paper_meta["year"] == "null":
                    paper_meta["year"] = crossref_meta["year"]
                self._debug_msg("Crossref fallback metadata merged.")

            # Format citation string
            citation = format_citation(paper_meta.get("authors", []), paper_meta.get("first_author", "Author"), paper_meta.get("year", "null"))
            paper_meta["citation"] = citation
            self._debug_msg(f"Derived GFR citation: '{citation}'")

            # Fetch open-access full text via Legumista read_paper if MCP is active
            if self.mcp_client:
                self._debug_msg(f"Attempting open-access full text retrieval via Legumista 'read_paper'...")
                full_text = self.mcp_client.read_paper(self.doi)
                if full_text:
                    self._debug_msg(f"Open-access full text retrieved ({len(full_text):,} chars). Will provide body excerpt to LLM.")
                else:
                    self._debug_msg("Full text not available open-access. Falling back to abstract only.")

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
        self._debug_panel(
            f"Prompting LLM to extract structured biocuration records from publication:\n"
            f"- Model: {model_display}\n"
            f"- Abstract: {len(paper_meta.get('abstract', '')):,} chars\n"
            f"- Full Text Available: {'Yes (' + str(len(full_text)) + ' chars)' if full_text else 'No'}\n"
            f"- Expected Output: JSON containing species, gene symbols, published gene model, confidence score (2-5), functional comments, phenotype synopsis, traits, and curation notes.",
            "Debug: LLM Extraction"
        )

        with console.status(f"[bold cyan]Contacting LLM ({model_display})...[/bold cyan]", spinner="dots"):
            extracted_list = query_llm(
                paper_meta.get("abstract", ""),
                api_key=self.api_key,
                model=self.model,
                full_text=full_text,
                debug=self.debug
            )
        if isinstance(extracted_list, dict):
            extracted_list = [extracted_list]

        self._debug_msg(f"Extracted {len(extracted_list)} gene entity candidate(s) from LLM output.")

        all_yaml_contents = []
        output_filename = None
        verified_gene_ids = []

        for idx, extracted in enumerate(extracted_list, start=1):
            gene_symbols = extracted.get("gene_symbols") or ["Unknown"]
            if isinstance(gene_symbols, str):
                gene_symbols = [gene_symbols]
            symbol_label = gene_symbols[0] if gene_symbols else "Unknown"
            console.print(f"[*] Processing extracted gene: [bold magenta]{symbol_label}[/bold magenta]...")

            if self.debug:
                summary_lines = [
                    f"[bold]Candidate #{idx}:[/bold] {symbol_label}",
                    f"[bold]Scientific Name:[/bold] {extracted.get('scientific_name') or 'Unknown'}",
                    f"[bold]Symbols:[/bold] {', '.join(gene_symbols)}",
                    f"[bold]Long Name:[/bold] {extracted.get('gene_symbol_long') or '~'}",
                    f"[bold]Published Model:[/bold] {extracted.get('gene_model_pub_name') or '~'}",
                    f"[bold]Assigned Confidence:[/bold] {extracted.get('confidence', 3)}/5",
                    f"[bold]Identified Traits:[/bold] {', '.join(extracted.get('traits', [])) or 'None'}"
                ]
                notes = extracted.get("curation_notes") or extracted.get("reasoning")
                if notes:
                    summary_lines.append(f"\n[italic bold]Extraction Notes:[/italic bold]\n{notes}")
                self._debug_panel("\n".join(summary_lines), f"Debug: Gene Candidate '{symbol_label}'")

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
            self._debug_msg(f"Species '{sci_name}' parsed -> genus prefix '{genus_prefix}', species prefix '{species_prefix}' -> gensp code '{gensp}'")

            # 4. Resolve Canonical LIS ID and Model Name via Legumista InterMine
            lis_gene_id = None
            pub_name = extracted.get("gene_model_pub_name")
            primary_symbol = gene_symbols[0] if gene_symbols and gene_symbols[0] != "Unknown" else None

            self._debug_panel(
                f"Resolving canonical LIS gene identifier for '{symbol_label}':\n"
                f"1. Query Legumista MCP 'mine_gene_symbol' using symbol='{primary_symbol}' and taxon='{sci_name}'.\n"
                f"2. If unresolved, run direct LegumeMine PathQuery for symbol='{primary_symbol}'.\n"
                f"3. If published model name ('{pub_name or '~'}') is present, resolve assembly identifier in InterMine/GraphQL.\n"
                f"4. If still unresolved, search NCBI Gene for symbol='{primary_symbol}' in organism '{sci_name}'.\n"
                f"5. Fall back to schema-compliant placeholder '{gensp}.TODO.TODO.<name>' if no database match found.",
                f"Debug: Identifier Resolution for '{symbol_label}'"
            )

            # Attempt MCP mine_gene_symbol resolution first
            if self.mcp_client and primary_symbol:
                self._debug_msg(f"Step 4.1: Querying Legumista MCP mine_gene_symbol(symbol='{primary_symbol}', taxon='{sci_name}')")
                with console.status(f"Resolving '{primary_symbol}' via Legumista mine_gene_symbol...", spinner="dots"):
                    mcp_records = self.mcp_client.mine_gene_symbol(primary_symbol, taxon=sci_name)
                if mcp_records:
                    self._debug_msg(f"Legumista MCP returned {len(mcp_records)} matching record(s). Matching against DOI '{self.doi}'...")
                    # Pick record matching current DOI if possible, otherwise first record
                    matched_rec = mcp_records[0]
                    clean_doi = self.doi.strip().lower()
                    for r in mcp_records:
                        if r.get("doi") and r["doi"].strip().lower() == clean_doi:
                            matched_rec = r
                            self._debug_msg(f"Found exact DOI match in Legumista record: {r}")
                            break

                    if (not pub_name or pub_name == "~") and matched_rec.get("gene_model_pub_name"):
                        pub_name = matched_rec["gene_model_pub_name"]
                        extracted["gene_model_pub_name"] = pub_name
                        self._debug_msg(f"Updated published model name to: {pub_name}")

                    if matched_rec.get("gene_model_full_id"):
                        lis_gene_id = matched_rec["gene_model_full_id"]
                        self._debug_msg(f"Identified canonical full ID: {lis_gene_id}")

                    if matched_rec.get("symbol_long") and (not extracted.get("gene_symbol_long") or extracted["gene_symbol_long"] == primary_symbol):
                        extracted["gene_symbol_long"] = matched_rec["symbol_long"]
                        self._debug_msg(f"Updated long symbol name to: {extracted['gene_symbol_long']}")

                    console.print(f"    -> [green]Resolved via Legumista InterMine: {pub_name} ({lis_gene_id})[/green]")
                else:
                    self._debug_msg("No matching records found in Legumista MCP for this symbol.")

            # Fallback to direct InterMine lookup if still unresolved
            if (not lis_gene_id or "TODO" in lis_gene_id) and primary_symbol:
                self._debug_msg(f"Step 4.2: Querying direct InterMine PathQuery for symbol '{primary_symbol}' (target_doi='{self.doi}')")
                direct_rec = resolve_symbol_intermine(primary_symbol, target_doi=self.doi)
                if direct_rec:
                    self._debug_msg(f"Direct InterMine returned match: {direct_rec}")
                    if (not pub_name or pub_name == "~") and direct_rec.get("gene_model_pub_name"):
                        pub_name = direct_rec["gene_model_pub_name"]
                        extracted["gene_model_pub_name"] = pub_name
                    if direct_rec.get("gene_model_full_id"):
                        lis_gene_id = direct_rec["gene_model_full_id"]
                    if direct_rec.get("symbol_long") and (not extracted.get("gene_symbol_long") or extracted["gene_symbol_long"] == primary_symbol):
                        extracted["gene_symbol_long"] = direct_rec["symbol_long"]
                    console.print(f"    -> [green]Resolved via direct InterMine: {pub_name} ({lis_gene_id})[/green]")
                else:
                    self._debug_msg("Direct InterMine PathQuery returned no results.")

            # If pub_name was in the paper but lis_gene_id not yet found, lookup pub_name in InterMine
            if (not lis_gene_id or "TODO" in lis_gene_id) and pub_name and pub_name != "~":
                self._debug_msg(f"Step 4.3: Resolving published model name '{pub_name}' in InterMine / GraphQL...")
                with console.status(f"Resolving model name '{pub_name}' in InterMine...", spinner="dots"):
                    resolved_id = resolve_gene_name_intermine(pub_name) or resolve_lis_identifier(pub_name)
                if resolved_id:
                    self._debug_msg(f"Found canonical identifier from assembly lookup: {resolved_id}")
                    console.print(f"    -> [green]Found canonical identifier: {resolved_id}[/green]")
                    lis_gene_id = resolved_id
                else:
                    self._debug_msg(f"Model name '{pub_name}' not resolved in InterMine; checking assembly prefix heuristics for '{gensp}'...")
                    if pub_name.lower().startswith(gensp) and gensp == "glyma":
                        lis_gene_id = f"glyma.Wm82.gnm2.ann1.{pub_name}"
                        self._debug_msg(f"Applied soybean default assembly: {lis_gene_id}")
                    else:
                        lis_gene_id = f"{gensp}.TODO.TODO.{pub_name}"
                        self._debug_msg(f"Assigned placeholder assembly ID: {lis_gene_id}")

            # Fallback: search NCBI Gene by primary symbol if pub_name is still missing
            if not pub_name or pub_name == "~":
                if primary_symbol and sci_name:
                    self._debug_msg(f"Step 4.4: Searching NCBI Gene for symbol '{primary_symbol}' in organism '{sci_name}'...")
                    with console.status(f"Searching NCBI Gene for symbol '{primary_symbol}'...", spinner="dots"):
                        resolved_pub_name = search_gene_model_by_symbol(primary_symbol, sci_name)
                    if resolved_pub_name:
                        self._debug_msg(f"NCBI Gene alias resolved to model name: {resolved_pub_name}")
                        console.print(f"    -> Found gene model mapping via NCBI: [green]{resolved_pub_name}[/green]")
                        pub_name = resolved_pub_name
                        extracted["gene_model_pub_name"] = pub_name
                        resolved_id = resolve_gene_name_intermine(pub_name) or resolve_lis_identifier(pub_name)
                        if resolved_id:
                            self._debug_msg(f"Resolved NCBI model name in InterMine: {resolved_id}")
                            lis_gene_id = resolved_id
                    else:
                        self._debug_msg("NCBI Gene search returned no matching gene model alias.")

            if not lis_gene_id or "TODO" in lis_gene_id:
                placeholder_target = (pub_name if (pub_name and pub_name != "~") else primary_symbol) or "RESOLVE_LIS_ID"
                lis_gene_id = f"{gensp}.TODO.TODO.{placeholder_target}"
                self._debug_msg(f"LIS ID unresolved; assigned schema-compliant placeholder: {lis_gene_id}")
            else:
                verified_gene_ids.append(lis_gene_id)
                self._debug_msg(f"Verified canonical LIS ID: {lis_gene_id}")

            # 5. Resolve Ontology codes
            resolved_traits = []
            seen_trait_entities = set()
            trait_list = extracted.get("traits", [])

            self._debug_panel(
                f"Mapping trait keywords to standardized ontology terms:\n"
                f"- Trait keywords: {trait_list}\n"
                f"- Ontology sources: EMBL-EBI OLS4 (Trait Ontology TO, Gene Ontology GO, Plant Ontology PO, PATO)\n"
                f"- Curated annotations: Checking Legumista 'mine_gene_ontology' for '{pub_name or '~'}'",
                f"Debug: Ontology Mapping for '{symbol_label}'"
            )

            for trait_kw in trait_list:
                self._debug_msg(f"Querying EBI OLS4 select API for trait keyword: '{trait_kw}'...")
                with console.status(f"Querying EBI OLS for ontology term: '{trait_kw}'...", spinner="dots"):
                    term = lookup_ontology_term(trait_kw)
                self._debug_msg(f"OLS4 match for '{trait_kw}': {term.get('entity')} ({term.get('entity_name')})")
                if term["entity"] not in seen_trait_entities:
                    seen_trait_entities.add(term["entity"])
                    resolved_traits.append(term)

            # Enrich with curated GO terms from Legumista mine_gene_ontology
            if self.mcp_client and pub_name and pub_name != "~":
                self._debug_msg(f"Checking Legumista MCP mine_gene_ontology for curated annotations on '{pub_name}'...")
                with console.status(f"Checking Legumista for curated GO terms on '{pub_name}'...", spinner="dots"):
                    go_terms = self.mcp_client.mine_gene_ontology(pub_name)
                self._debug_msg(f"Retrieved {len(go_terms)} curated GO term(s) from Legumista: {[gt['entity'] for gt in go_terms]}")
                for gt in go_terms:
                    if gt["entity"] not in seen_trait_entities:
                        seen_trait_entities.add(gt["entity"])
                        resolved_traits.append(gt)

            # 6. Build and Write YAML File
            self._debug_msg(f"Building YAML document structure for gene '{symbol_label}'...")
            yaml_content = build_yaml_document(extracted, paper_meta, resolved_traits, gensp, lis_gene_id)
            all_yaml_contents.append(yaml_content)

            if not output_filename:
                output_filename = resolve_filename(extracted, paper_meta, gensp)
                self._debug_msg(f"Resolved draft output filename: '{output_filename}'")

        # 7. Verification using Legumista verify_ids tool
        if self.mcp_client and self.doi:
            verify_parts = [f"DOI: {self.doi}"]
            if verified_gene_ids:
                verify_parts.append(f"genes: {', '.join(verified_gene_ids)}")
            verify_query = ", ".join(verify_parts)

            self._debug_panel(
                f"Validating resolved identifiers against the live LIS database via Legumista MCP 'verify_ids':\n"
                f"Query: {verify_query}",
                "Debug: Identifier Verification"
            )

            with console.status("[bold cyan]Verifying identifiers with Legumista verify_ids...[/bold cyan]", spinner="dots"):
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
            self._debug_msg(f"Running automated JSON Schema validation on '{output_filename}'...")
            is_valid, _ = validate_yaml_file(output_filename, out_console=console, verbose=True, debug=self.debug)
            if not is_valid:
                console.print("[bold yellow][!] Warning: The generated draft has schema validation errors. Please inspect above.[/bold yellow]\n")

            return output_filename
        except Exception as e:
            console.print(f"[bold red][!] Error: Failed to write output file {output_filename}: {e}[/bold red]")
            return None
