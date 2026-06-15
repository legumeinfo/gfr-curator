import urllib.request
import json
import sys
import time
from rich.console import Console

err_console = Console(stderr=True)

def query_gemini_api(api_key, abstract):
    """
    Queries Gemini API to extract gene function information from a scientific paper abstract.
    """
    print("[*] Contacting Gemini API...")
    prompt = f"""You are an expert biocurator for the Legume Information System (LIS). Your task is to extract gene function information from the provided abstract of a scientific paper and output a structured JSON matching the LIS Gene Function Registry schema.

Scientific Paper Abstract:
{abstract}

Please extract the following information and output it as a valid JSON ARRAY of objects, with one object for EACH distinct gene characterized in the paper. For example, if the paper characterizes two genes, return an array of two objects.

[
  {{
    "scientific_name": "scientific name of the plant species studied, e.g. Glycine max",
    "classical_locus": "any classical locus name if mentioned, otherwise null",
    "gene_symbols": ["list of gene symbols for THIS specific gene, e.g. GmCIF1"],
    "gene_symbol_long": "the long-hand version of the main gene symbol acronym, e.g. Cell Wall Invertase Inhibitor 1",
    "gene_model_pub_name": "the gene model name as listed in the publication (e.g., Glyma02g17170)",
    "confidence": "an integer from 1 to 5 showing how strong the evidence is:
                  5 - High confidence (gene functional validation with stable transgenic lines)
                  4 - Medium-High (functional validation with transient expression, e.g. RNAi transient or VIGS, or heterologous expression with strong in vitro proof)
                  3 - Medium (in vitro enzyme activity only, or genetic mapping with tight linkage)
                  2 - Medium-Low (gene expression correlates with trait, or mutant phenotype described in other species only)
                  1 - Low (in silico prediction or sequence homology only)",
    "comments": ["list of 1-3 comments briefly describing THIS gene's function, regulation, and interactors"],
    "phenotype_synopsis": "brief synopsis of the phenotype for THIS gene",
    "traits": ["list of key trait keywords to lookup for THIS gene, e.g. ['seed weight', 'sucrose metabolism']"]
  }}
]

Make sure your response contains ONLY the raw JSON array without markdown formatting or any extra conversational text.
"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    data = {
        "contents": [{
            "parts": [{"text": prompt}]
        }],
        "generationConfig": {
            "responseMimeType": "application/json"
        }
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers=headers,
        method="POST"
    )
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                res_data = json.loads(response.read().decode("utf-8"))
                text = res_data["candidates"][0]["content"]["parts"][0]["text"]
                return json.loads(text.strip())
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                err_console.print(f"[bold yellow][-] Gemini API query failed ({e}). Retrying in {wait_time}s...[/bold yellow]")
                time.sleep(wait_time)
            else:
                err_console.print(f"[bold red][!] Error: Gemini API query failed after {max_retries} attempts: {e}[/bold red]")
                sys.exit(1)
