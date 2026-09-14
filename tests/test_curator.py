import unittest
from gfr_curator.yaml_generator import resolve_filename, build_yaml_document

class TestGFRCurator(unittest.TestCase):
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

if __name__ == "__main__":
    unittest.main()

