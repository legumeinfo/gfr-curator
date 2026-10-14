import unittest
from gfr_curator.curator import format_rich_text
from gfr_curator.yaml_generator import resolve_filename, build_yaml_document, strip_html_tags

class TestGFRCurator(unittest.TestCase):
    def test_format_rich_text_italics_and_bold(self):
        text = "Characterization in soybean (<i>Glycine max</i>) and <em>Lotus</em> with <b>strong</b> phenotypes"
        result = format_rich_text(text)
        self.assertEqual(result, "Characterization in soybean ([italic]Glycine max[/italic]) and [italic]Lotus[/italic] with [bold]strong[/bold] phenotypes")

    def test_format_rich_text_jats_xml(self):
        text = "Studies in <jats:italic>Medicago truncatula</jats:italic> and &lt;i&gt;Phaseolus vulgaris&lt;/i&gt;"
        result = format_rich_text(text)
        self.assertEqual(result, "Studies in [italic]Medicago truncatula[/italic] and [italic]Phaseolus vulgaris[/italic]")

    def test_strip_html_tags(self):
        raw = "Soybean (<i>Glycine max</i>) with <jats:italic>GmCIF1</jats:italic> & <b>mutations</b>"
        cleaned = strip_html_tags(raw)
        self.assertEqual(cleaned, "Soybean (Glycine max) with GmCIF1 & mutations")

    def test_resolve_filename_two_authors_from_citation(self):
        extracted = {"scientific_name": "Glycine max"}
        paper_meta = {"citation": "Tang, Su et al., 2017", "year": "2017"}
        gensp = "glyma"
        filename = resolve_filename(extracted, paper_meta, gensp)
        self.assertEqual(filename, "glyma.Tang_Su_2017.yml")

    def test_resolve_filename_two_authors_from_authors_list(self):
        extracted = {"scientific_name": "Glycine max"}
        paper_meta = {
            "authors": ["Tang", "Su", "Han"],
            "citation": "Tang, Su et al., 2017",
            "year": "2017"
        }
        gensp = "glyma"
        filename = resolve_filename(extracted, paper_meta, gensp)
        self.assertEqual(filename, "glyma.Tang_Su_2017.yml")

    def test_resolve_filename_single_author_from_authors_list(self):
        extracted = {"scientific_name": "Glycine max"}
        paper_meta = {"authors": ["Smith"], "year": "2024"}
        gensp = "glyma"
        filename = resolve_filename(extracted, paper_meta, gensp)
        self.assertEqual(filename, "glyma.Smith_2024.yml")

    def test_resolve_filename_single_author_from_citation(self):
        extracted = {"scientific_name": "Glycine max"}
        paper_meta = {"citation": "Smith, 2024", "year": "2024"}
        gensp = "glyma"
        filename = resolve_filename(extracted, paper_meta, gensp)
        self.assertEqual(filename, "glyma.Smith_2024.yml")

    def test_resolve_filename_legacy_single_author_et_al(self):
        extracted = {"scientific_name": "Glycine max"}
        paper_meta = {"citation": "Tang et al., 2017", "year": "2017"}
        gensp = "glyma"
        filename = resolve_filename(extracted, paper_meta, gensp)
        self.assertEqual(filename, "glyma.Tang_2017.yml")

    def test_unresolved_ids_schema_compliance(self):
        from gfr_curator.validator import validate_yaml_string
        extracted = {
            "scientific_name": "Vigna radiata",
            "gene_symbols": ["VrTIFY6B"],
            "gene_symbol_long": "TIFY domain-containing protein 6B",
            "gene_model_pub_name": None,
            "confidence": 4,
            "comments": ["Promoter insertion regulates flavonoid content."],
            "phenotype_synopsis": "Promoter insertion regulates flavonoid content.",
        }
        paper_meta = {
            "citation": "Chen, Xing et al., 2026",
            "doi": "10.1038/s41588-026-02644-5",
            "pmid": 42432247,
            "year": "2026"
        }
        resolved_traits = [
            {"entity_name": "flavonoid content", "entity": "TO:0000290"}
        ]
        gensp = "vigra"
        yaml_content = build_yaml_document(extracted, paper_meta, resolved_traits, gensp)
        self.assertIn('gene_model_pub_name: "~"', yaml_content)
        self.assertIn('gene_model_full_id: vigra.TODO.TODO.VrTIFY6B', yaml_content)
        is_valid, results = validate_yaml_string(yaml_content)
        self.assertTrue(is_valid, f"Validation failed: {results}")

if __name__ == "__main__":
    unittest.main()

