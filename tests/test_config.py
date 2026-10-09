import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from rich.console import Console

from gfr_curator.config import (
    get_config_dir,
    get_config_file,
    is_local_model,
    mask_key,
    read_config_dict,
    save_config_dict,
    is_configured,
    load_user_config,
    run_configurator,
)

class TestConfig(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_dir = Path(self.temp_dir.name) / ".config" / "gfr-curator"
        self.config_file = self.config_dir / "config.env"
        os.environ["GFR_CONFIG_DIR"] = str(self.config_dir)
        os.environ["GFR_CONFIG_FILE"] = str(self.config_file)

    def tearDown(self):
        self.temp_dir.cleanup()
        os.environ.pop("GFR_CONFIG_DIR", None)
        os.environ.pop("GFR_CONFIG_FILE", None)

    def test_paths(self):
        self.assertEqual(get_config_dir(), self.config_dir)
        self.assertEqual(get_config_file(), self.config_file)

    def test_mask_key(self):
        self.assertEqual(mask_key(""), "(none)")
        self.assertEqual(mask_key("short"), "********")
        self.assertEqual(mask_key("AIzaSy1234567890"), "AIza...7890")

    def test_is_local_model(self):
        self.assertTrue(is_local_model("ollama/llama3"))
        self.assertTrue(is_local_model("local/mistral"))
        self.assertFalse(is_local_model("gpt-4o"))
        self.assertFalse(is_local_model("gemini/gemini-flash-lite-latest"))
        self.assertFalse(is_local_model(None))

    def test_save_and_read_config(self):
        # File doesn't exist yet
        self.assertFalse(is_configured())
        self.assertEqual(read_config_dict(), {})

        # Save updates
        saved_path = save_config_dict({"LLM_MODEL": "gpt-4o", "OPENAI_API_KEY": "sk-test-123"})
        self.assertEqual(saved_path, self.config_file)
        self.assertTrue(self.config_file.exists())
        self.assertTrue(is_configured())

        # Check permissions (0600)
        mode = os.stat(self.config_file).st_mode
        self.assertEqual(stat.S_IMODE(mode), 0o600)

        # Read back
        data = read_config_dict()
        self.assertEqual(data.get("LLM_MODEL"), "gpt-4o")
        self.assertEqual(data.get("OPENAI_API_KEY"), "sk-test-123")

        # Update without losing OPENAI_API_KEY
        save_config_dict({"LLM_MODEL": "gemini/gemini-2.5-flash", "GEMINI_API_KEY": "AIza-test"})
        data2 = read_config_dict()
        self.assertEqual(data2.get("LLM_MODEL"), "gemini/gemini-2.5-flash")
        self.assertEqual(data2.get("OPENAI_API_KEY"), "sk-test-123")
        self.assertEqual(data2.get("GEMINI_API_KEY"), "AIza-test")

    def test_load_user_config(self):
        save_config_dict({"TEST_CUSTOM_GFR_VAR": "test_val_999"})
        load_user_config()
        self.assertEqual(os.environ.get("TEST_CUSTOM_GFR_VAR"), "test_val_999")
        os.environ.pop("TEST_CUSTOM_GFR_VAR", None)

    @patch("sys.stdin.isatty", return_value=False)
    def test_run_configurator_model_selection_and_key(self, mock_isatty):
        # Simulate user choosing option 1 (Gemini) and typing a key
        mock_console = MagicMock()
        mock_console.input.side_effect = ["1", "my-gemini-key-123"]

        run_configurator(out_console=mock_console, is_initial=True)
        data = read_config_dict()
        self.assertEqual(data.get("LLM_MODEL"), "gemini/gemini-flash-lite-latest")
        self.assertEqual(data.get("GEMINI_API_KEY"), "my-gemini-key-123")

    @patch("sys.stdin.isatty", return_value=False)
    def test_run_configurator_local_model_no_key(self, mock_isatty):
        # Simulate user choosing option 4 (Ollama)
        mock_console = MagicMock()
        mock_console.input.side_effect = ["4"]

        run_configurator(out_console=mock_console, is_initial=False)
        data = read_config_dict()
        self.assertEqual(data.get("LLM_MODEL"), "ollama/llama3")

    def test_get_all_known_models(self):
        from gfr_curator.config import get_all_known_models
        models = get_all_known_models()
        self.assertIn("gemini/gemini-flash-lite-latest", models)
        self.assertIn("gpt-4o", models)
        self.assertIn("claude-3-5-sonnet-20241022", models)
        self.assertIn("deepseek/deepseek-chat", models)

    @patch("sys.stdin.isatty", return_value=False)
    def test_search_and_select_model_fallback(self, mock_isatty):
        from gfr_curator.config import search_and_select_model
        mock_console = MagicMock()
        mock_console.input.side_effect = ["deepseek/deepseek-chat"]
        chosen = search_and_select_model(out_console=mock_console)
        self.assertEqual(chosen, "deepseek/deepseek-chat")

    @patch("sys.stdin.isatty", return_value=True)
    @patch("gfr_curator.config._prompt_toolkit_select", return_value="claude-3-5-sonnet-20241022")
    def test_search_and_select_model_prompt_toolkit(self, mock_pt, mock_isatty):
        from gfr_curator.config import search_and_select_model
        mock_console = MagicMock()
        chosen = search_and_select_model(out_console=mock_console)
        self.assertEqual(chosen, "claude-3-5-sonnet-20241022")

    @patch("sys.stdin.isatty", return_value=False)
    def test_run_configurator_with_search_option(self, mock_isatty):
        mock_console = MagicMock()
        mock_console.input.side_effect = ["5", "deepseek/deepseek-chat", "sk-deepseek-test"]
        run_configurator(out_console=mock_console, is_initial=False)
        data = read_config_dict()
        self.assertEqual(data.get("LLM_MODEL"), "deepseek/deepseek-chat")
        self.assertEqual(data.get("DEEPSEEK_API_KEY"), "sk-deepseek-test")

    def test_model_completer(self):
        from gfr_curator.config import ModelCompleter
        from prompt_toolkit.document import Document

        models = [
            "gemini/gemini-flash-lite-latest",
            "claude-3-5-sonnet-20241022",
            "gpt-4o",
            "deepseek/deepseek-chat",
        ]
        completer = ModelCompleter(models)

        # 1. Exact substring match
        doc = Document("claud", 5)
        completions = list(completer.get_completions(doc, None))
        self.assertEqual([c.text for c in completions], ["claude-3-5-sonnet-20241022"])
        self.assertEqual(completions[0].start_position, -5)

        # 2. Token match (e.g. gemini flash)
        doc2 = Document("gemini flash", 12)
        completions2 = list(completer.get_completions(doc2, None))
        self.assertIn("gemini/gemini-flash-lite-latest", [c.text for c in completions2])
        self.assertEqual(completions2[0].start_position, -12)

        # 3. Empty query returns initial models
        doc3 = Document("", 0)
        completions3 = list(completer.get_completions(doc3, None))
        self.assertEqual(len(completions3), 4)

    def test_prompt_masked_key_fallback(self):
        from gfr_curator.config import prompt_masked_key
        mock_console = MagicMock()
        mock_console.input.return_value = "my-secret-key"

        with patch("sys.stdin.isatty", return_value=False):
            key = prompt_masked_key("API Key: ", out_console=mock_console)
            self.assertEqual(key, "my-secret-key")
            mock_console.input.assert_called_with("API Key: ", password=True)

if __name__ == "__main__":
    unittest.main()



