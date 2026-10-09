import sys
import os
from gfr_curator.curator import GFRCurator
from gfr_curator.config import (
    load_user_config,
    is_configured,
    run_configurator,
    is_local_model,
    get_provider_info,
    save_config_dict,
    prompt_masked_key,
)
from rich.console import Console
from rich.panel import Panel

console = Console()

def resolve_api_key(model: str, key_arg: str = None) -> str:
    if key_arg:
        return key_arg
    if is_local_model(model):
        return None
    if os.environ.get("LLM_API_KEY"):
        return os.environ.get("LLM_API_KEY")
    _, env_var, _ = get_provider_info(model)
    if os.environ.get(env_var):
        return os.environ.get(env_var)
    # Check general fallbacks
    for fallback_var in ("OPENROUTER_API_KEY", "DEEPSEEK_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        if os.environ.get(fallback_var):
            return os.environ.get(fallback_var)
    return None

def main():
    # Load configuration from ~/.config/gfr-curator/config.env and local .env
    load_user_config()

    console.print(Panel.fit(
        "[bold cyan]LIS Gene Function Registry[/bold cyan]\n[italic]Automated Curation Tool[/italic]", 
        border_style="cyan"
    ))
    
    # Help flag
    if any(arg in ("-h", "--help") for arg in sys.argv[1:]):
        print("Usage: gfr-curate [DOI] [--model MODEL] [--key API_KEY] [--configure] [--validate FILE]")
        print("\nOptions:")
        print("  DOI                Digital Object Identifier of the publication")
        print("  --model MODEL      LLM model identifier (e.g. gpt-4o, claude-3-5-sonnet-20241022,")
        print("                     gemini/gemini-flash-lite-latest")
        print("  --key API_KEY      API key for the selected model provider")
        print("  --configure        Run interactive wizard to set or update default model & API credentials")
        print("  --validate FILE    Validate a YAML record draft against schema")
        print("\nConfiguration:")
        print("  Config file:       ~/.config/gfr-curator/config.env (permissions 0600)")
        print("  Environment:       LLM_MODEL, GEMINI_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY")
        sys.exit(0)

    # Validate flag (offline validation does not require LLM setup)
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

    # Explicit --configure call
    if "--configure" in sys.argv:
        run_configurator(out_console=console, is_initial=False)
        sys.exit(0)

    # First-time launch wizard
    if not is_configured():
        run_configurator(out_console=console, is_initial=True)
        load_user_config()

    # Parse arguments
    model = os.environ.get("LLM_MODEL") or os.environ.get("GFR_MODEL") or os.environ.get("GEMINI_MODEL")
    key_arg = None
    doi = ""

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--model":
            if i + 1 < len(args):
                model = args[i + 1]
                i += 2
                continue
            else:
                console.print("[bold red][!] Error: --model requires a model name.[/bold red]")
                sys.exit(1)
        elif arg == "--key":
            if i + 1 < len(args):
                key_arg = args[i + 1]
                i += 2
                continue
            else:
                console.print("[bold red][!] Error: --key requires an API key.[/bold red]")
                sys.exit(1)
        elif not arg.startswith("--") and not doi:
            doi = arg
            i += 1
        else:
            i += 1
            
    if not doi:
        try:
            doi = console.input("\n[bold yellow]Enter the DOI of the paper to curate:[/bold yellow] ").strip()
        except KeyboardInterrupt:
            console.print("\n[bold red][!] Cancelled.[/bold red]")
            sys.exit(1)
        if not doi:
            console.print("[bold red][!] Error: No DOI provided. Exiting.[/bold red]")
            sys.exit(1)
            
    # Resolve API Key
    api_key = resolve_api_key(model, key_arg=key_arg)
    if not api_key and not is_local_model(model):
        provider_name, env_var, url = get_provider_info(model)
        console.print(f"\n[bold red][!] An API Key ({env_var}) is required to run curation with {provider_name}.[/bold red]")
        if url:
            console.print(f"[dim]Key URL: {url}[/dim]")
        try:
            api_key = prompt_masked_key(f"{provider_name} API key ({env_var}): ", out_console=console)
        except (KeyboardInterrupt, EOFError):
            console.print("\nCancelled.")
            sys.exit(1)
        if not api_key:
            console.print(f"[bold red][!] Error: API Key is not set. Exiting.[/bold red]")
            sys.exit(1)
        
        # Save key for future runs
        try:
            save_config_dict({env_var: api_key})
        except Exception:
            pass
            
    # Run the orchestrator
    curator = GFRCurator(doi, api_key=api_key, model=model)
    curator.execute()

if __name__ == "__main__":
    main()


