import urllib.request
import json
import sys

def fetch_crossref_metadata(doi):
    """
    Queries the Crossref API to retrieve publication metadata for a DOI.
    Returns a dict containing title, first_author, and year.
    """
    title = "null"
    first_author = "Author"
    pub_year = "null"
    
    try:
        crossref_url = f"https://api.crossref.org/works/{doi}"
        req = urllib.request.Request(crossref_url, headers={'User-Agent': 'Mozilla/5.0 (mailto:curator@legumeinfo.org)'})
        with urllib.request.urlopen(req, timeout=10) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            message = res_data.get("message", {})
            
            titles = message.get("title", [])
            if titles:
                title = titles[0]
                
            authors = []
            author_objs = message.get("author", [])
            for author_obj in author_objs:
                family = author_obj.get("family")
                if family:
                    authors.append(family)
            if authors:
                first_author = authors[0]
                
            date_parts = message.get("created", {}).get("date-parts", [[]])[0]
            if date_parts:
                pub_year = date_parts[0]
    except Exception as e:
        print(f"[!] Warning: Failed to query Crossref for DOI {doi}: {e}", file=sys.stderr)
        
    return {
        "title": title,
        "first_author": first_author,
        "authors": authors if 'authors' in locals() else [first_author],
        "year": pub_year
    }
