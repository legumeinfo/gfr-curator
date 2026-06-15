import requests
import json
import re

def search_gene_model_by_symbol(symbol, organism, gensp):
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {
        "db": "gene",
        "term": f"{symbol}[Gene Name] AND {organism}[Organism]",
        "retmode": "json"
    }
    resp = requests.get(url, params=params)
    data = resp.json()
    
    idlist = data.get("esearchresult", {}).get("idlist", [])
    if not idlist:
        return None
        
    gene_id = idlist[0]
    sum_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
    sum_params = {
        "db": "gene",
        "id": gene_id,
        "retmode": "json"
    }
    sum_resp = requests.get(sum_url, params=sum_params)
    sum_data = sum_resp.json()
    
    aliases = sum_data.get("result", {}).get(gene_id, {}).get("otheraliases", "")
    
    # Try to find a pattern like GLYMA_17G036300v4 -> Glyma.17G036300
    # For general legume formats, it's often Prefix.##G######
    print(f"Aliases for {symbol}: {aliases}")
    
    # Simple regex to find Glyma format
    match = re.search(r'(?i)(glyma)[_\.]?(\d+[a-z]\d+)(?:v\d+)?', aliases)
    if match:
        prefix = match.group(1).capitalize()
        body = match.group(2)
        return f"{prefix}.{body}"
    return None

print(search_gene_model_by_symbol("GmCIF1", "Glycine max", "glyma"))
