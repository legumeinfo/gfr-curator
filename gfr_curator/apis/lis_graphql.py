import requests
from rich.console import Console

err_console = Console(stderr=True)

LIS_GRAPHQL_URL = "https://graphql.lis.ncgr.org/"

def resolve_lis_identifier(gene_model_pub_name):
    """
    Queries the LIS GraphQL endpoint for the LIS identifier
    given a published gene model name (e.g., 'Glyma.12G078000').
    Returns the identifier string or None if not found.
    """
    if not gene_model_pub_name:
        return None

    query = """
    query GetGeneIdentifier($name: String!) {
      genes(name: $name) {
        results {
          identifier
        }
      }
    }
    """
    
    variables = {
        "name": gene_model_pub_name
    }
    
    try:
        response = requests.post(
            LIS_GRAPHQL_URL,
            json={'query': query, 'variables': variables},
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        
        results = data.get("data", {}).get("genes", {}).get("results", [])
        if results and len(results) > 0:
            # Sort or select the most appropriate identifier if multiple exist?
            # For now, just take the first one or we can prioritize 'gnm2' over 'gnm4' etc.
            # But the first match is typically fine.
            return results[0].get("identifier")
            
        return None
    except requests.exceptions.RequestException as e:
        err_console.print(f"[bold red][!] Error querying LIS GraphQL API: {e}[/bold red]")
        return None
    except Exception as e:
        err_console.print(f"[bold red][!] Unexpected error querying LIS GraphQL API: {e}[/bold red]")
        return None
