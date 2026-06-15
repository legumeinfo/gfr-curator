import urllib.request
import urllib.parse
import json
import sys
from rich.console import Console

err_console = Console(stderr=True)

def lookup_ontology_term(query, ontology="to,go,po,pato"):
    """
    Queries EMBL-EBI OLS4 API to find matching TO, GO, PO, or PATO terms.
    """
    try:
        encoded_query = urllib.parse.quote(query)
        url = f"https://www.ebi.ac.uk/ols4/api/select?q={encoded_query}&ontology={ontology}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            docs = res_data.get("response", {}).get("docs", [])
            if docs:
                match = docs[0]
                return {
                    "entity_name": match.get("label"),
                    "entity": match.get("obo_id")
                }
    except Exception as e:
        err_console.print(f"[bold yellow][!] Warning: Failed to lookup ontology term '{query}': {e}[/bold yellow]")
    return {
        "entity_name": query,
        "entity": "TO:XXXXXXX"  # Fallback code
    }
