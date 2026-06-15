import sys

def build_yaml_document(extracted, paper_meta, resolved_traits, gensp, lis_gene_id="TODO_RESOLVE_LIS_ID"):
    """
    Serializes extracted metadata into an official GFR-compliant YAML structure.
    """
    yaml_lines = [
        "---",
        f"scientific_name: {extracted['scientific_name']}",
    ]
    if extracted.get("classical_locus"):
        yaml_lines.append(f"classical_locus: {extracted['classical_locus']}")
    
    yaml_lines.append("gene_symbols:")
    for sym in extracted["gene_symbols"]:
        yaml_lines.append(f"  - {sym}")
        
    yaml_lines.append(f"gene_symbol_long: {extracted['gene_symbol_long']}")
    yaml_lines.append(f"gene_model_pub_name: {extracted['gene_model_pub_name'] if extracted.get('gene_model_pub_name') else '~'}")
    
    yaml_lines.append(f"gene_model_full_id: {lis_gene_id}")
    yaml_lines.append(f"confidence: {extracted['confidence']}")
    
    yaml_lines.append("curators:")
    yaml_lines.append("  - AI Curation Assistant")
    
    yaml_lines.append("comments:")
    for comment in extracted["comments"]:
        yaml_lines.append(f"  - \"{comment}\"")
        
    yaml_lines.append(f"phenotype_synopsis: \"{extracted['phenotype_synopsis']}\"")
    
    yaml_lines.append("traits:")
    for trait in resolved_traits:
        yaml_lines.append(f"  - entity_name: {trait['entity_name']}")
        yaml_lines.append(f"    entity: {trait['entity']}")
        
    yaml_lines.append("references:")
    yaml_lines.append(f"  - citation: {paper_meta['citation']}")
    yaml_lines.append(f"    doi: {paper_meta['doi']}")
    yaml_lines.append(f"    pmid: {paper_meta['pmid']}")

    return "\n".join(yaml_lines) + "\n"

def resolve_filename(extracted, paper_meta, gensp):
    """
    Returns standard GFR naming spec filename.
    """
    author_prefix = paper_meta['citation'].split(" ")[0].replace(",", "")
    return f"{gensp}.{author_prefix}_{paper_meta['year']}.yml"
