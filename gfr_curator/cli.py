import sys
import os
from dotenv import load_dotenv
from gfr_curator.curator import GFRCurator
from rich.console import Console
from rich.panel import Panel

load_dotenv()

console = Console()

def main():
    console.print(Panel.fit(
        "[bold cyan]LIS Gene Function Registry[/bold cyan]\n[italic]Automated Curation Tool[/italic]", 
        border_style="cyan"
    ))
    
    # 1. Parse command line arguments or prompt interactively
    if "--validate" in sys.argv:
        from gfr_curator.validator import validate_yaml_file
        idx = sys.argv.index("--validate")
        if idx + 1 < len(sys.argv):
            target_file = sys.argv[idx + 1]
            is_valid, _ = validate_yaml_file(target_file, verbose=True)
            sys.exit(0 if is_valid else 1)
        else:
            console.print("[bold red][!] Error: --validate requires a path to a YAML file.[/bold red]")
            sys.exit(1)

    doi = ""
    if len(sys.argv) > 1:
        if sys.argv[1] in ("-h", "--help"):
            print("Usage: gfr-curate [DOI] [--key GEMINI_API_KEY] [--validate FILE]")
            sys.exit(0)
        if not sys.argv[1].startswith("--"):
            doi = sys.argv[1]
            
    if not doi:
        try:
            doi = console.input("\n[bold yellow]Enter the DOI of the paper to curate:[/bold yellow] ").strip()
        except KeyboardInterrupt:
            console.print("\n[bold red][!] Cancelled.[/bold red]")
            sys.exit(1)
        if not doi:
            console.print("[bold red][!] Error: No DOI provided. Exiting.[/bold red]")
            sys.exit(1)
            
    # Check for API Key
    api_key = os.environ.get("GEMINI_API_KEY")
    if "--key" in sys.argv:
        idx = sys.argv.index("--key")
        if idx + 1 < len(sys.argv):
            api_key = sys.argv[idx + 1]
            
    if not api_key:
        console.print("\n[bold red][!] A Gemini API Key is required to run curation.[/bold red]")
        console.print("    Get a free API key at: [link=https://aistudio.google.com/]https://aistudio.google.com/[/link]")
        try:
            api_key = console.input("[bold yellow]Please paste your GEMINI_API_KEY:[/bold yellow] ").strip()
        except KeyboardInterrupt:
            console.print("\n[bold red][!] Cancelled.[/bold red]")
            sys.exit(1)
        if not api_key:
            console.print("[bold red][!] Error: GEMINI_API_KEY is not set. Exiting.[/bold red]")
            sys.exit(1)
            
    # Run the orchestrator
    curator = GFRCurator(doi, api_key=api_key)
    curator.execute()

if __name__ == "__main__":
    main()
