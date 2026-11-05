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

    def test_gfr_curator_debug_flag(self):
        from gfr_curator.curator import GFRCurator
        curator = GFRCurator("10.1234/example", debug=True)
        self.assertTrue(curator.debug)
        curator_default = GFRCurator("10.1234/example")
        self.assertFalse(curator_default.debug)

    def test_gfr_curator_debug_helpers_call(self):
        from gfr_curator.curator import GFRCurator
        curator = GFRCurator("10.1234/example", debug=True)
        # Should not raise exception
        curator._debug_msg("Testing debug message")
        curator._debug_panel("Testing debug content", "Debug: Unit Test")

    def test_gfr_curator_pdf_path_initialization(self):
        import os
        from gfr_curator.curator import GFRCurator
        curator = GFRCurator("10.1234/example", pdf_path="paper.pdf")
        self.assertEqual(curator.pdf_path, os.path.abspath("paper.pdf"))

    def test_gfr_curator_pdf_skips_mcp_read_paper(self):
        from unittest.mock import patch, MagicMock
        from gfr_curator.curator import GFRCurator

        curator = GFRCurator("10.1234/example", pdf_path="paper.pdf", use_mcp=True)

        with patch("os.path.isfile", return_value=True), \
             patch("gfr_curator.curator.extract_text_from_pdf", return_value="Local PDF paper text") as mock_extract, \
             patch("gfr_curator.curator.LegumistaMCPClient") as mock_mcp_cls, \
             patch("gfr_curator.curator.fetch_ncbi_metadata", return_value={
                 "title": "Sample Paper", "citation": "Author, 2024", "year": "2024", "pmid": "123", "doi": "10.1234/example", "abstract": "Abstract text"
             }), \
             patch("gfr_curator.curator.query_llm", return_value=[]) as mock_query_llm:

            mock_mcp_instance = MagicMock()
            mock_mcp_instance.is_healthy.return_value = True
            mock_mcp_cls.return_value = mock_mcp_instance

            curator.execute()

            mock_extract.assert_called_once_with(curator.pdf_path)
            # read_paper should NEVER be called when a local PDF is provided
            mock_mcp_instance.read_paper.assert_not_called()
            # query_llm should be called with full_text="Local PDF paper text"
            self.assertEqual(mock_query_llm.call_args[1].get("full_text"), "Local PDF paper text")

    def _run_pdf_doi_detection(self, doi, detected):
        from unittest.mock import patch
        from gfr_curator.curator import GFRCurator

        curator = GFRCurator(doi, pdf_path="paper.pdf", use_mcp=False)
        with patch("os.path.isfile", return_value=True), \
             patch("gfr_curator.curator.extract_doi_from_pdf", return_value=detected), \
             patch("gfr_curator.curator.extract_text_from_pdf", return_value="text"), \
             patch("gfr_curator.curator.fetch_ncbi_metadata", return_value={
                 "title": "T", "citation": "A, 2024", "year": "2024", "pmid": "1", "doi": "x", "abstract": "abs"
             }), \
             patch("gfr_curator.curator.query_llm", return_value=[]), \
             patch("gfr_curator.curator.console.print") as mock_print:
            curator.execute()
        printed = " ".join(str(c.args[0]) for c in mock_print.call_args_list if c.args)
        return curator, printed

    def test_pdf_doi_detected_when_not_provided(self):
        curator, printed = self._run_pdf_doi_detection(None, "10.1038/detected")
        self.assertEqual(curator.doi, "10.1038/detected")
        self.assertIn("Detected DOI from PDF", printed)
        self.assertIn("10.1038/detected", printed)

    def test_pdf_doi_printed_and_mismatch_warned_when_provided(self):
        curator, printed = self._run_pdf_doi_detection("10.1234/provided", "10.1038/detected")
        self.assertEqual(curator.doi, "10.1234/provided")
        self.assertIn("10.1038/detected", printed)
        self.assertIn("differs from the DOI detected", printed)

    def test_pdf_doi_match_is_case_insensitive(self):
        curator, printed = self._run_pdf_doi_detection("10.1038/S41588-026-02577-Z", "10.1038/s41588-026-02577-z")
        self.assertNotIn("differs from the DOI detected", printed)

    def test_pdf_without_doi_and_none_provided_exits(self):
        with self.assertRaises(SystemExit) as cm:
            self._run_pdf_doi_detection(None, None)
        self.assertEqual(cm.exception.code, 1)

if __name__ == "__main__":
    unittest.main()

