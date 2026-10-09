import re
import sys

def build_yaml_document(extracted, paper_meta, resolved_traits, gensp, lis_gene_id="TODO_RESOLVE_LIS_ID"):
    """
    Serializes extracted metadata into an official GFR-compliant YAML structure.
    """
    sci_name = extracted.get("scientific_name") or "Unknown species"
    yaml_lines = [
        "---",
        f"scientific_name: {sci_name}",
    ]
    if extracted.get("classical_locus"):
        yaml_lines.append(f"classical_locus: {extracted['classical_locus']}")
    
    yaml_lines.append("gene_symbols:")
    symbols = extracted.get("gene_symbols") or ["Unknown"]
    if isinstance(symbols, str):
        symbols = [symbols]
    for sym in symbols:
        yaml_lines.append(f"  - {sym}")
        
    long_sym = extracted.get("gene_symbol_long") or (symbols[0] if symbols else "Unknown")
    yaml_lines.append(f"gene_symbol_long: {long_sym}")
    pub_name = extracted.get("gene_model_pub_name")
    yaml_lines.append(f"gene_model_pub_name: {pub_name if pub_name else '~'}")
    
    yaml_lines.append(f"gene_model_full_id: {lis_gene_id}")
    conf = extracted.get("confidence", 3)
    yaml_lines.append(f"confidence: {conf}")
    
    yaml_lines.append("curators:")
    yaml_lines.append("  - AI Curation Assistant")
    
    yaml_lines.append("comments:")
    comments = extracted.get("comments") or ["Characterized in publication"]
    if isinstance(comments, str):
        comments = [comments]
    for comment in comments:
        clean_comment = comment.replace('"', '\\"')
        yaml_lines.append(f"  - \"{clean_comment}\"")
        
    synopsis = extracted.get("phenotype_synopsis") or "Characterized in publication"
    clean_synopsis = synopsis.replace('"', '\\"')
    yaml_lines.append(f"phenotype_synopsis: \"{clean_synopsis}\"")
    
    yaml_lines.append("traits:")
    for trait in resolved_traits:
        yaml_lines.append(f"  - entity_name: {trait['entity_name']}")
        yaml_lines.append(f"    entity: {trait['entity']}")
        
    yaml_lines.append("references:")
    yaml_lines.append(f"  - citation: {paper_meta['citation']}")
    if paper_meta.get('doi') and paper_meta['doi'] not in ("null", "~"):
        yaml_lines.append(f"    doi: {paper_meta['doi']}")
    if paper_meta.get('pmid') and str(paper_meta['pmid']).isdigit() and paper_meta['pmid'] != "null":
        yaml_lines.append(f"    pmid: {int(paper_meta['pmid'])}")

    return "\n".join(yaml_lines) + "\n"

def resolve_filename(extracted, paper_meta, gensp):
    """
    Returns a filename following the pattern:
    gensp.<FirstAuthor_LastName>_<SecondAuthor_LastName>_<Publication_Year>.yml
    If only one author is present:
    gensp.<FirstAuthor_LastName>_<Publication_Year>.yml
    """
    year = paper_meta.get("year")
    if not year or str(year) == "null":
        cit_match = re.search(r"\b(19\d\d|20\d\d)\b", paper_meta.get("citation", ""))
        year = cit_match.group(1) if cit_match else "YEAR"

    clean_name = lambda s: re.sub(r"[^\w-]", "", s.strip())

    authors = paper_meta.get("authors")
    if authors and isinstance(authors, (list, tuple)):
        cleaned_authors = [clean_name(a) for a in authors if clean_name(a)]
        if len(cleaned_authors) >= 2:
            author_prefix = f"{cleaned_authors[0]}_{cleaned_authors[1]}"
        elif len(cleaned_authors) == 1:
            author_prefix = cleaned_authors[0]
        else:
            author_prefix = "Author"
    else:
        # Fallback to parsing citation string
        citation = paper_meta.get("citation", "")
        if citation:
            clean_cit = re.sub(r"\bet\.?\s*al\.?", "", citation, flags=re.IGNORECASE)
            clean_cit = re.sub(r",?\s*\b\d{4}\b.*", "", clean_cit).strip()
            parts = [clean_name(p) for p in clean_cit.split(",") if clean_name(p)]
            if len(parts) >= 2:
                author_prefix = f"{parts[0]}_{parts[1]}"
            elif len(parts) == 1:
                author_prefix = parts[0]
            else:
                author_prefix = "Author"
        else:
            first_author = paper_meta.get("first_author", "Author")
            author_prefix = clean_name(first_author) if clean_name(first_author) else "Author"

    return f"{gensp}.{author_prefix}_{year}.yml"


