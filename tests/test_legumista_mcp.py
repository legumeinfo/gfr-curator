import unittest
from unittest.mock import patch, MagicMock
from gfr_curator.apis.legumista_mcp import LegumistaMCPClient

class TestLegumistaMCP(unittest.TestCase):
    def setUp(self):
        self.client = LegumistaMCPClient(base_url="https://mcp.test.org")

    @patch('urllib.request.urlopen')
    def test_ensure_initialized_success(self, mock_urlopen):
        # Mock initialize response
        resp1 = MagicMock()
        resp1.headers.get.return_value = "test-session-123"

        # Mock notifications/initialized response
        resp2 = MagicMock()
        resp2.read.return_value = b''

        cm1 = MagicMock()
        cm1.__enter__.return_value = resp1
        cm2 = MagicMock()
        cm2.__enter__.return_value = resp2

        mock_urlopen.side_effect = [cm1, cm2]

        healthy = self.client.is_healthy()
        self.assertTrue(healthy)
        self.assertEqual(self.client.session_id, "test-session-123")
        self.assertTrue(self.client._initialized)

    @patch('urllib.request.urlopen')
    def test_call_tool_sse(self, mock_urlopen):
        self.client._initialized = True
        self.client.session_id = "test-session-123"

        resp = MagicMock()
        resp.read.return_value = b'event: message\ndata: {"jsonrpc":"2.0","id":2,"result":{"content":[{"type":"text","text":"hello"}]}}\n\n'
        
        cm = MagicMock()
        cm.__enter__.return_value = resp
        mock_urlopen.return_value = cm

        res = self.client.call_tool("test_tool", {"arg": "val"})
        self.assertIn("content", res)
        self.assertEqual(res["content"][0]["text"], "hello")

    @patch.object(LegumistaMCPClient, 'call_tool')
    def test_mine_gene_symbol_parsing(self, mock_call):
        sample_output = """Gene symbol — GmCIF1 [source: curated LIS catalog, NOT a mine query]
1 curated record(s)
  species | gene | doi | synopsis
  glyma | glyma.Wm82.gnm4.ann1.Glyma.17G036300 | 10.1093/jxb/erw425 | Seed development inhibitor

Gene symbol in Glycine max — GmCIF1 [mines: legumemine, glycinemine]
1 row(s)
  Symbol | Symbol Long | Name | Identifier | Synopsis | DOI | in
  GmCIF1 | Cell Wall Inhibitor of β-Fructosidase 1 | Glyma.17G036300 | glyma.Wm82.gnm4.ann1.Glyma.17G036300 | Seed development inhibitor | 10.1093/jxb/erw425 | both
"""
        mock_call.return_value = {
            "content": [{"type": "text", "text": sample_output}]
        }

        records = self.client.mine_gene_symbol("GmCIF1", taxon="Glycine max")
        self.assertGreaterEqual(len(records), 1)
        found_pub_name = any(r.get("gene_model_pub_name") == "Glyma.17G036300" for r in records)
        self.assertTrue(found_pub_name)

    @patch.object(LegumistaMCPClient, 'call_tool')
    def test_openalex_by_doi_parsing(self, mock_call):
        sample_text = """[1] Suppression of extracellular invertase inhibitor gene expression (2016)
    doi:10.1093/jxb/erw425 | pmid:28204559 | Journal of Experimental Botany | cited-by:65 | src:openalex
    authors: Xiaofei Tang, Tao Su, Mei Han
Cell wall invertase plays multiple functions in plant growth.
"""
        mock_call.return_value = {
            "content": [{"type": "text", "text": sample_text}]
        }

        meta = self.client.openalex_by_doi("10.1093/jxb/erw425")
        self.assertIsNotNone(meta)
        self.assertEqual(meta["title"], "Suppression of extracellular invertase inhibitor gene expression")
        self.assertEqual(meta["year"], "2016")
        self.assertEqual(meta["pmid"], "28204559")
        self.assertIn("Tang", meta["authors"])

    @patch.object(LegumistaMCPClient, 'call_tool')
    def test_verify_ids(self, mock_call):
        mock_call.return_value = {
            "content": [{"type": "text", "text": "verify_ids — 2 identifier(s): 2 FOUND\nDOI 10.1093/jxb/erw425 — FOUND\ngene glyma.Wm82.gnm4.ann1.Glyma.17G036300 — FOUND"}]
        }
        res = self.client.verify_ids("test")
        self.assertIn("2 FOUND", res)

if __name__ == '__main__':
    unittest.main()
