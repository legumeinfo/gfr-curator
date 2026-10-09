import os
import sys
from gfr_curator.apis.ncbi import fetch_ncbi_metadata, search_gene_model_by_symbol
from gfr_curator.apis.crossref import fetch_crossref_metadata
from gfr_curator.apis.ols import lookup_ontology_term
from gfr_curator.apis.lis_graphql import resolve_lis_identifier
from gfr_curator.llm import query_llm, query_gemini_api
from gfr_curator.yaml_generator import build_yaml_document, resolve_filename
from gfr_curator.validator import validate_yaml_file
from rich.console import Console
from rich.syntax import Syntax

console = Console()

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
    def __init__(self, doi, api_key=None, model=None):
        self.doi = doi
        self.api_key = api_key
        self.model = model
        
    def execute(self):
        # 1. Fetch live metadata and abstract
        with console.status("[bold cyan]Fetching metadata...[/bold cyan]", spinner="dots"):
            paper_meta = fetch_ncbi_metadata(self.doi)
            paper_meta["doi"] = self.doi
            
            # If abstract not fetched, fallback to Crossref
            if not paper_meta.get("abstract"):
                console.print("[bold yellow][!] No abstract retrieved from PubMed. Checking Crossref for metadata...[/bold yellow]")
                crossref_meta = fetch_crossref_metadata(self.doi)
                # Merge
                paper_meta["title"] = paper_meta["title"] if paper_meta["title"] != "null" else crossref_meta["title"]
                if paper_meta["first_author"] == "Author":
                    paper_meta["first_author"] = crossref_meta["first_author"]
                if not paper_meta.get("authors"):
                    paper_meta["authors"] = crossref_meta.get("authors", [paper_meta["first_author"]])
                if paper_meta["year"] == "null":
                    paper_meta["year"] = crossref_meta["year"]
                    
            # Re-verify and format citation
            citation = format_citation(paper_meta.get("authors", []), paper_meta.get("first_author", "Author"), paper_meta.get("year", "null"))
            paper_meta["citation"] = citation
            
        console.print("\n[bold green][+] Paper Resolved:[/bold green]")
        console.print(f"    [bold]Title:[/bold]    {paper_meta['title']}")
        console.print(f"    [bold]Citation:[/bold] {paper_meta['citation']}")
        console.print(f"    [bold]PMID:[/bold]     {paper_meta['pmid']}")
        console.print(f"    [bold]DOI:[/bold]      {paper_meta['doi']}\n")
        
        # 2. Structured Extraction
        if not paper_meta.get("abstract"):
            console.print("[bold red][!] Error: No abstract could be fetched for this paper, cannot perform LLM extraction.[/bold red]")
            sys.exit(1)
            
        model_display = self.model or os.environ.get("LLM_MODEL") or os.environ.get("GFR_MODEL") or os.environ.get("GEMINI_MODEL") or "Gemini (LiteLLM)"
        with console.status(f"[bold cyan]Contacting LLM ({model_display})...[/bold cyan]", spinner="dots"):
            extracted_list = query_llm(paper_meta["abstract"], api_key=self.api_key, model=self.model)
        if isinstance(extracted_list, dict):
            extracted_list = [extracted_list]
            
        all_yaml_contents = []
        output_filename = None
        
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
            
            # 4. Resolve Ontology codes
            resolved_traits = []
            for trait_kw in extracted.get("traits", []):
                with console.status(f"Querying EBI OLS for ontology term: '{trait_kw}'...", spinner="dots"):
                    term = lookup_ontology_term(trait_kw)
                resolved_traits.append(term)
                
            # 5. Resolve Canonical LIS ID
            lis_gene_id = "TODO_RESOLVE_LIS_ID"
            pub_name = extracted.get("gene_model_pub_name")
            
            # Fallback: if pub_name is missing, search NCBI Gene by primary symbol
            if not pub_name or pub_name == "~":
                primary_symbol = extracted.get("gene_symbols", [])[0] if extracted.get("gene_symbols") else None
                scientific_name = extracted.get("scientific_name", "")
                if primary_symbol and scientific_name:
                    with console.status(f"Searching NCBI Gene for symbol '{primary_symbol}'...", spinner="dots"):
                        resolved_pub_name = search_gene_model_by_symbol(primary_symbol, scientific_name)
                    if resolved_pub_name:
                        console.print(f"    -> Found gene model mapping: [green]{resolved_pub_name}[/green]")
                        pub_name = resolved_pub_name
                        extracted["gene_model_pub_name"] = pub_name

            if pub_name and pub_name != "~":
                with console.status(f"Querying LIS GraphQL for gene model '{pub_name}'...", spinner="dots"):
                    resolved_id = resolve_lis_identifier(pub_name)
                if resolved_id:
                    console.print(f"    -> Found canonical identifier: [green]{resolved_id}[/green]")
                    lis_gene_id = resolved_id
                else:
                    console.print(f"    -> [yellow]Not found in LIS. Using fallback.[/yellow]")
                    if pub_name.lower().startswith(gensp):
                        lis_gene_id = f"{gensp}.Wm82.gnm2.ann1.{pub_name}"
                    else:
                        lis_gene_id = f"TODO_RESOLVE_LIS_ID_FOR_{pub_name}"
                
            # 6. Build and Write YAML File
            yaml_content = build_yaml_document(extracted, paper_meta, resolved_traits, gensp, lis_gene_id)
            all_yaml_contents.append(yaml_content)
            
            if not output_filename:
                output_filename = resolve_filename(extracted, paper_meta, gensp)
        
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
            
            # 7. Automatically validate generated YAML against schema
            is_valid, _ = validate_yaml_file(output_filename, out_console=console, verbose=True)
            if not is_valid:
                console.print("[bold yellow][!] Warning: The generated draft has schema validation errors. Please inspect above.[/bold yellow]\n")
            
            return output_filename
        except Exception as e:
            console.print(f"[bold red][!] Error: Failed to write output file {output_filename}: {e}[/bold red]")
            return None
