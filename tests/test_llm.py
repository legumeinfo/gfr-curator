import unittest
from unittest.mock import patch, MagicMock
from gfr_curator.llm import normalize_model_name, parse_llm_json_response, query_llm, query_gemini_api
from gfr_curator.cli import is_local_model, get_provider_info, resolve_api_key

class TestLLM(unittest.TestCase):
    def test_normalize_model_name(self):
        self.assertEqual(normalize_model_name("gemini-flash-lite-latest"), "gemini/gemini-flash-lite-latest")
        self.assertEqual(normalize_model_name("gemini/gemini-flash-lite-latest"), "gemini/gemini-flash-lite-latest")
        self.assertEqual(normalize_model_name("gpt-4o"), "gpt-4o")
        self.assertEqual(normalize_model_name("claude-3-5-sonnet"), "claude-3-5-sonnet")
        self.assertEqual(normalize_model_name("ollama/llama3"), "ollama/llama3")
        self.assertIsNone(normalize_model_name(None))

    def test_parse_llm_json_response_array(self):
        raw = '[{"gene_symbols": ["GmCIF1"], "scientific_name": "Glycine max"}]'
        res = parse_llm_json_response(raw)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["gene_symbols"], ["GmCIF1"])

    def test_parse_llm_json_response_wrapped_markdown(self):
        raw = '```json\n[{"gene_symbols": ["GmCIF1"]}]\n```'
        res = parse_llm_json_response(raw)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["gene_symbols"], ["GmCIF1"])

    def test_parse_llm_json_response_dict_with_genes_key(self):
        raw = '{"genes": [{"gene_symbols": ["GmCIF1"]}]}'
        res = parse_llm_json_response(raw)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["gene_symbols"], ["GmCIF1"])

    def test_parse_llm_json_response_single_dict(self):
        raw = '{"gene_symbols": ["GmCIF1"], "scientific_name": "Glycine max"}'
        res = parse_llm_json_response(raw)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["gene_symbols"], ["GmCIF1"])

    def test_parse_llm_json_response_empty(self):
        with self.assertRaises(ValueError):
            parse_llm_json_response("")

    @patch("gfr_curator.llm.litellm.completion")
    def test_query_llm_success(self, mock_completion):
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content='[{"gene_symbols": ["GmCIF1"], "scientific_name": "Glycine max"}]'))
        ]
        mock_completion.return_value = mock_response

        res = query_llm("abstract text", api_key="test-key", model="gpt-4o")
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["gene_symbols"], ["GmCIF1"])
        mock_completion.assert_called_once()
        call_kwargs = mock_completion.call_args[1]
        self.assertEqual(call_kwargs["model"], "gpt-4o")
        self.assertEqual(call_kwargs["api_key"], "test-key")

    @patch("gfr_curator.llm.litellm.completion")
    def test_query_gemini_api_backwards_compatible(self, mock_completion):
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content='[{"gene_symbols": ["GmCIF1"]}]'))
        ]
        mock_completion.return_value = mock_response

        res = query_gemini_api("key-123", "some abstract", model_override="gemini/gemini-flash-lite-latest")
        self.assertEqual(len(res), 1)
        call_kwargs = mock_completion.call_args[1]
        self.assertEqual(call_kwargs["model"], "gemini/gemini-flash-lite-latest")
        self.assertEqual(call_kwargs["api_key"], "key-123")

    def test_is_local_model(self):
        self.assertTrue(is_local_model("ollama/llama3"))
        self.assertTrue(is_local_model("local/model"))
        self.assertFalse(is_local_model("gpt-4o"))
        self.assertFalse(is_local_model("gemini/gemini-2.5-flash"))
        self.assertFalse(is_local_model(None))

    def test_get_provider_info(self):
        name, env, url = get_provider_info("gpt-4o")
        self.assertEqual(name, "OpenAI")
        self.assertEqual(env, "OPENAI_API_KEY")

        name, env, url = get_provider_info("claude-3-5-sonnet")
        self.assertEqual(name, "Anthropic")
        self.assertEqual(env, "ANTHROPIC_API_KEY")

        name, env, url = get_provider_info(None)
        self.assertEqual(name, "Gemini")
        self.assertEqual(env, "GEMINI_API_KEY")

    def test_format_friendly_error_json_error(self):
        from gfr_curator.llm import format_friendly_error

        # 1. 503 Service unavailable with embedded JSON
        raw_503 = '''litellm.ServiceUnavailableError: GeminiException - {
  "error": {
    "code": 503,
    "message": "This model is currently experiencing high demand. Spikes in demand are usually temporary. Please try again later.",
    "status": "UNAVAILABLE"
  }
}'''
        res = format_friendly_error(raw_503)
        self.assertEqual(res, "This model is currently experiencing high demand. Spikes in demand are usually temporary. Please try again later.")

        # 2. 404 Deprecated model with embedded JSON
        raw_404 = '''litellm.NotFoundError: GeminiException - {
  "error": {
    "code": 404,
    "message": "This model models/gemini-2.5-flash is no longer available to new users.",
    "status": "NOT_FOUND"
  }
}'''
        self.assertEqual(format_friendly_error(raw_404), "This model models/gemini-2.5-flash is no longer available to new users.")

        # 3. Clean raw exception prefix
        raw_plain = "AuthenticationError: OpenAIException - Incorrect API key provided."
        self.assertEqual(format_friendly_error(raw_plain), "Incorrect API key provided.")

        # 4. None / empty
        self.assertEqual(format_friendly_error(None), "Unknown error")

if __name__ == "__main__":
    unittest.main()
