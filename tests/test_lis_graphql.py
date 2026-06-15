import unittest
from unittest.mock import patch, MagicMock
from gfr_curator.apis.lis_graphql import resolve_lis_identifier

class TestLISGraphQL(unittest.TestCase):
    
    @patch('gfr_curator.apis.lis_graphql.requests.post')
    def test_resolve_lis_identifier_found(self, mock_post):
        # Setup mock response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": {
                "genes": {
                    "results": [
                        {"identifier": "glyma.Wm82.gnm2.ann1.Glyma.12G078000"}
                    ]
                }
            }
        }
        mock_post.return_value = mock_response
        
        identifier = resolve_lis_identifier("Glyma.12G078000")
        self.assertEqual(identifier, "glyma.Wm82.gnm2.ann1.Glyma.12G078000")
        
        # Verify call
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertEqual(kwargs['json']['variables']['name'], "Glyma.12G078000")

    @patch('gfr_curator.apis.lis_graphql.requests.post')
    def test_resolve_lis_identifier_not_found(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": {
                "genes": {
                    "results": []
                }
            }
        }
        mock_post.return_value = mock_response
        
        identifier = resolve_lis_identifier("UnknownGene")
        self.assertIsNone(identifier)

    def test_resolve_lis_identifier_none_input(self):
        identifier = resolve_lis_identifier(None)
        self.assertIsNone(identifier)

if __name__ == '__main__':
    unittest.main()
