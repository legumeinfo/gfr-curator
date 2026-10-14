import unittest
from unittest.mock import patch, MagicMock
from gfr_curator.apis.intermine import resolve_symbol_intermine, resolve_gene_name_intermine, run_pathquery

class TestInterMine(unittest.TestCase):

    @patch('gfr_curator.apis.intermine.run_pathquery')
    def test_resolve_symbol_intermine(self, mock_pathquery):
        mock_pathquery.return_value = [
            ["GmCIF1", "Cell Wall Inhibitor of β-Fructosidase 1", "Glyma.17G036300", "glyma.Wm82.gnm4.ann1.Glyma.17G036300", "Seed inhibitor", "10.1093/jxb/erw425"]
        ]

        rec = resolve_symbol_intermine("GmCIF1", target_doi="10.1093/jxb/erw425")
        self.assertIsNotNone(rec)
        self.assertEqual(rec["symbol"], "GmCIF1")
        self.assertEqual(rec["gene_model_pub_name"], "Glyma.17G036300")
        self.assertEqual(rec["gene_model_full_id"], "glyma.Wm82.gnm4.ann1.Glyma.17G036300")
        self.assertEqual(rec["doi"], "10.1093/jxb/erw425")

    @patch('gfr_curator.apis.intermine.run_pathquery')
    def test_resolve_gene_name_intermine(self, mock_pathquery):
        mock_pathquery.return_value = [
            ["glyma.Wm82.gnm2.ann1.Glyma.12G078000", "Glyma.12G078000", "Glyma.12G078000"],
            ["glyma.Wm82.gnm4.ann1.Glyma.12G078000", "Glyma.12G078000", "Glyma.12G078000"]
        ]

        identifier = resolve_gene_name_intermine("Glyma.12G078000")
        self.assertEqual(identifier, "glyma.Wm82.gnm2.ann1.Glyma.12G078000")

    @patch('gfr_curator.apis.intermine.run_pathquery')
    def test_resolve_symbol_not_found(self, mock_pathquery):
        mock_pathquery.return_value = []
        rec = resolve_symbol_intermine("NonExistent")
        self.assertIsNone(rec)

if __name__ == '__main__':
    unittest.main()
