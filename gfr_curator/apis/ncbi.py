import urllib.request
import urllib.parse
import json
import sys
import re
import xml.etree.ElementTree as ET
from rich.console import Console

err_console = Console(stderr=True)

def fetch_ncbi_metadata(doi):
    """
    Queries Europe PMC and PubMed EFetch to resolve PMIDs and get abstracts.
    """
    pmid = "null"
    title = "null"
    journal = "null"
    pub_year = "null"
    first_author = "Author"
    abstract = ""
    
    authors = []
    # 1. Query Europe PMC to resolve DOI metadata
    try:
        epmc_url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=DOI:{doi}&format=json"
        req = urllib.request.Request(epmc_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            results = res_data.get("resultList", {}).get("result", [])
            if results:
                paper = results[0]
                pmid = paper.get("pmid", "null")
                title = paper.get("title", "null")
                journal = paper.get("journalTitle", "null")
                pub_year = paper.get("pubYear", "null")
                
                author_string = paper.get("authorString", "")
                if author_string:
                    raw_authors = [a.strip() for a in author_string.rstrip(".").split(",") if a.strip()]
                    for a in raw_authors:
                        surname = a.split(" ")[0].strip()
                        if surname:
                            authors.append(surname)
                    if authors:
                        first_author = authors[0]
    except Exception as e:
        print(f"[!] Warning: Failed to query Europe PMC: {e}", file=sys.stderr)

    # 2. Get abstract from NCBI E-utilities if PMID resolved
    if pmid != "null":
        try:
            efetch_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id={pmid}&retmode=xml"
            with urllib.request.urlopen(efetch_url, timeout=10) as response:
                xml_data = response.read()
                root = ET.fromstring(xml_data)
                abstract_el = root.find(".//AbstractText")
                if abstract_el is not None:
                    abstract = "".join(abstract_el.itertext()).strip()
        except Exception as e:
            err_console.print(f"[bold red][!] Warning: Failed to fetch abstract from NCBI: {e}[/bold red]")
            
    return {
        "pmid": pmid,
        "title": title,
        "journal": journal,
        "year": pub_year,
        "first_author": first_author,
        "authors": authors,
        "abstract": abstract
    }

def search_gene_model_by_symbol(symbol, organism):
    """
    Searches the NCBI Gene database using a gene symbol and organism to find
    its gene model identifier (e.g. searching GmCIF1 returns Glyma.17G036300).
    """
    try:
        # 1. Search for Gene ID
        query = f"{symbol}[Gene Name] AND {organism}[Organism]"
        search_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=gene&term={urllib.parse.quote(query)}&retmode=json"
        
        req = urllib.request.Request(search_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
            idlist = data.get("esearchresult", {}).get("idlist", [])
            
        if not idlist:
            return None
            
        # 2. Fetch Gene Summary for Aliases
        gene_id = idlist[0]
        sum_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=gene&id={gene_id}&retmode=json"
        
        req = urllib.request.Request(sum_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            sum_data = json.loads(response.read().decode("utf-8"))
            aliases = sum_data.get("result", {}).get(gene_id, {}).get("otheraliases", "")
            
        # Try to find a standard plant model format (e.g., GLYMA_17G036300v4 -> Glyma.17G036300)
        match = re.search(r'(?i)(glyma|aradu|medtr)[_\.]?(\d+[a-z]\d+)(?:v\d+)?', aliases)
        if match:
            prefix = match.group(1).capitalize()
            body = match.group(2)
            return f"{prefix}.{body}"
            
        return None
    except Exception as e:
        err_console.print(f"[bold yellow][!] Warning: Failed to query NCBI Gene for symbol: {e}[/bold yellow]")
        return None
