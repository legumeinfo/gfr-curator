import os
import sys
import json
import yaml
from pathlib import Path
import jsonschema
from jsonschema import Draft202012Validator, Draft7Validator
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

def get_default_schema_path():
    """
    Finds default schema.json path, checking package directory then repo root.
    """
    pkg_schema = Path(__file__).resolve().parent / "schema.json"
    if pkg_schema.exists():
        return str(pkg_schema)
    repo_schema = Path(__file__).resolve().parent.parent / "schema.json"
    if repo_schema.exists():
        return str(repo_schema)
    return str(pkg_schema)

def load_schema(schema_path=None):
    """
    Loads JSON Schema from file.
    """
    if not schema_path:
        schema_path = get_default_schema_path()
    
    if not os.path.exists(schema_path):
        raise FileNotFoundError(f"Schema file not found at: {schema_path}")
        
    with open(schema_path, "r", encoding="utf-8") as f:
        return json.load(f)

def validate_document(doc, schema=None):
    """
    Validates a single parsed YAML document against the schema.
    Returns a list of error strings (empty if valid).
    """
    if schema is None:
        schema = load_schema()
        
    if not isinstance(doc, dict):
        return [f"Document root must be a YAML mapping/object, got {type(doc).__name__}"]
        
    validator_cls = jsonschema.validators.validator_for(schema)
    validator = validator_cls(schema)
    
    errors = []
    for err in validator.iter_errors(doc):
        path = " -> ".join([str(p) for p in err.absolute_path]) if err.absolute_path else "root"
        errors.append(f"[{path}] {err.message}")
        
    return errors

def validate_yaml_string(yaml_content, schema=None):
    """
    Validates all documents in a YAML string.
    Returns (is_valid, list of document validation results).
    """
    if schema is None:
        schema = load_schema()
        
    try:
        documents = list(yaml.safe_load_all(yaml_content))
    except yaml.YAMLError as e:
        return False, [{"doc_index": 1, "is_valid": False, "errors": [f"YAML syntax error: {e}"]}]
        
    if not documents:
        return True, []
        
    results = []
    overall_valid = True
    for idx, doc in enumerate(documents, start=1):
        if doc is None:
            continue
        errors = validate_document(doc, schema=schema)
        is_doc_valid = len(errors) == 0
        if not is_doc_valid:
            overall_valid = False
        results.append({
            "doc_index": idx,
            "is_valid": is_doc_valid,
            "errors": errors,
            "gene_symbol": (doc.get("gene_symbols", [""])[0] if isinstance(doc, dict) and doc.get("gene_symbols") else f"Doc #{idx}")
        })
        
    return overall_valid, results

def validate_yaml_file(file_path, schema_path=None, out_console=None, verbose=True):
    """
    Validates all documents in a YAML file against schema.json.
    Outputs rich formatting and returns (is_valid, results).
    """
    c = out_console or console
    
    if not os.path.exists(file_path):
        if verbose:
            c.print(f"[bold red]Error: YAML file not found: {file_path}[/bold red]")
        return False, [{"doc_index": 0, "is_valid": False, "errors": [f"File not found: {file_path}"]}]
        
    try:
        schema = load_schema(schema_path)
    except Exception as e:
        if verbose:
            c.print(f"[bold red]Error loading schema: {e}[/bold red]")
        return False, [{"doc_index": 0, "is_valid": False, "errors": [str(e)]}]

    if verbose:
        c.print(f"\n[bold cyan]===============================================[/bold cyan]")
        c.print(f"[bold]Validating YAML File:[/bold] {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        yaml_content = f.read()
        
    is_valid, results = validate_yaml_string(yaml_content, schema=schema)
    
    if verbose:
        if not results:
            c.print("[yellow]Warning: No YAML documents found. Nothing to validate.[/yellow]")
            return True, []
            
        total_docs = len(results)
        failed_docs = sum(1 for r in results if not r["is_valid"])
        
        for r in results:
            doc_idx = r["doc_index"]
            symbol_label = f" ({r.get('gene_symbol')})" if r.get("gene_symbol") else ""
            if r["is_valid"]:
                c.print(f"  [green]✔[/green] Document {doc_idx}{symbol_label}: [bold green]PASSED[/bold green]")
            else:
                c.print(f"  [red]✖[/red] Document {doc_idx}{symbol_label}: [bold red]FAILED[/bold red]")
                for err in r["errors"]:
                    c.print(f"      [red]• {err}[/red]")
                    
        c.print(f"\n[bold]--- Validation Summary for {os.path.basename(file_path)} ---[/bold]")
        c.print(f"Total documents validated: [bold]{total_docs}[/bold]")
        c.print(f"Total documents failed:    [bold]{failed_docs}[/bold]")
        
        if is_valid:
            c.print(f"[bold green][+] Overall Validation: PASSED (All documents conform to schema.json)[/bold green]\n")
        else:
            c.print(f"[bold red][!] Overall Validation: FAILED (Some documents contain schema errors)[/bold red]\n")
            
    return is_valid, results

def main():
    """
    CLI runner for stand-alone validation.
    Usage: gfr-validate <path_to_yaml> [--schema <path_to_schema>]
    """
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        console.print("Usage: [bold green]gfr-validate[/bold green] <path_to_yaml_file> [--schema <path_to_schema.json>]")
        console.print("Example: gfr-validate glyma.Tang_Su_2017.yml")
        sys.exit(0)
        
    yaml_file = sys.argv[1]
    schema_file = None
    if "--schema" in sys.argv:
        s_idx = sys.argv.index("--schema")
        if s_idx + 1 < len(sys.argv):
            schema_file = sys.argv[s_idx + 1]
            
    is_valid, _ = validate_yaml_file(yaml_file, schema_path=schema_file, verbose=True)
    sys.exit(0 if is_valid else 1)

if __name__ == "__main__":
    main()
