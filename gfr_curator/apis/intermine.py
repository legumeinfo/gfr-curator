import json
import urllib.parse
import urllib.request
from typing import Optional, Dict, Any, List
from rich.console import Console

err_console = Console(stderr=True)

INTERMINE_BASE_URL = "https://mines.legumeinfo.org/legumemine/service"

def run_pathquery(query_xml: str, service_url: str = INTERMINE_BASE_URL, timeout: int = 15) -> List[List[Any]]:
    """
    Executes a PathQuery XML against an InterMine endpoint and returns the results rows.
    """
    params = urllib.parse.urlencode({"query": query_xml, "format": "json"})
    url = f"{service_url}/query/results?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "gfr-curator/0.1.0 (Mozilla/5.0)"})
    
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("wasSuccessful", True):
                return data.get("results", [])
    except Exception as e:
        err_console.print(f"[dim yellow][!] Warning: InterMine query error: {e}[/dim yellow]")
        
    return []

def resolve_symbol_intermine(symbol: str, target_doi: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Resolves a gene symbol (e.g., GmCIF1) in InterMine to its gene model and canonical LIS ID.
    If multiple publications exist, prioritizes matching target_doi if provided.
    """
    if not symbol:
        return None

    clean_symbol = symbol.strip()
    query_xml = f"""<query model="genomic" view="GeneFunction.symbol GeneFunction.symbolLong GeneFunction.gene.name GeneFunction.gene.primaryIdentifier GeneFunction.synopsis GeneFunction.publications.doi">
<constraint path="GeneFunction.symbol" op="=" value="{clean_symbol}"/>
</query>"""

    results = run_pathquery(query_xml)
    if not results:
        return None

    # Each row: [symbol, symbolLong, gene.name, gene.primaryIdentifier, synopsis, doi]
    matched_row = results[0]
    if target_doi:
        clean_target_doi = target_doi.strip().lower()
        for row in results:
            if len(row) > 5 and row[5] and row[5].strip().lower() == clean_target_doi:
                matched_row = row
                break

    return {
        "symbol": matched_row[0],
        "symbol_long": matched_row[1] if len(matched_row) > 1 and matched_row[1] else None,
        "gene_model_pub_name": matched_row[2] if len(matched_row) > 2 and matched_row[2] else None,
        "gene_model_full_id": matched_row[3] if len(matched_row) > 3 and matched_row[3] else None,
        "synopsis": matched_row[4] if len(matched_row) > 4 and matched_row[4] else None,
        "doi": matched_row[5] if len(matched_row) > 5 and matched_row[5] else None,
    }

def resolve_gene_name_intermine(gene_name: str) -> Optional[str]:
    """
    Resolves a published gene name/model (e.g., 'Glyma.12G078000') to its canonical
    primaryIdentifier in LIS InterMine (e.g. 'glyma.Wm82.gnm2.ann1.Glyma.12G078000').
    Prioritizes gnm2 or gnm4 assemblies.
    """
    if not gene_name:
        return None

    clean_name = gene_name.strip()
    query_xml = f"""<query model="genomic" view="Gene.primaryIdentifier Gene.secondaryIdentifier Gene.name" sortOrder="Gene.primaryIdentifier asc">
<constraint path="Gene.name" op="=" value="{clean_name}"/>
</query>"""

    results = run_pathquery(query_xml)
    if not results:
        return None

    # Prefer gnm2 or gnm4 if available
    for row in results:
        identifier = row[0]
        if "gnm2" in identifier:
            return identifier
    for row in results:
        identifier = row[0]
        if "gnm4" in identifier:
            return identifier

    return results[0][0]
