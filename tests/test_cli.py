import sys
import unittest
from io import StringIO
from unittest.mock import patch, MagicMock
from gfr_curator.cli import main

class TestCLI(unittest.TestCase):
    @patch("sys.stdout", new_callable=StringIO)
    def test_help_contains_debug_flag(self, mock_stdout):
        with patch.object(sys, "argv", ["gfr-curate", "--help"]):
            with self.assertRaises(SystemExit) as cm:
                main()
            self.assertEqual(cm.exception.code, 0)
            output = mock_stdout.getvalue()
            self.assertIn("--debug", output)
            self.assertIn("Show detailed diagnostic and operational details", output)

    @patch("gfr_curator.cli.GFRCurator")
    @patch("gfr_curator.cli.is_configured", return_value=True)
    def test_debug_flag_passed_to_curator(self, mock_is_configured, mock_curator_cls):
        mock_instance = MagicMock()
        mock_curator_cls.return_value = mock_instance

        with patch.object(sys, "argv", ["gfr-curate", "10.1093/jxb/erw425", "--model", "gpt-4o", "--key", "sk-test", "--debug"]):
            main()
            mock_curator_cls.assert_called_once()
            call_kwargs = mock_curator_cls.call_args[1]
            self.assertTrue(call_kwargs.get("debug"))
            mock_instance.execute.assert_called_once()

    @patch("gfr_curator.cli.GFRCurator")
    @patch("gfr_curator.cli.is_configured", return_value=True)
    def test_debug_flag_default_is_false(self, mock_is_configured, mock_curator_cls):
        mock_instance = MagicMock()
        mock_curator_cls.return_value = mock_instance

        with patch.object(sys, "argv", ["gfr-curate", "10.1093/jxb/erw425", "--model", "gpt-4o", "--key", "sk-test"]):
            main()
            mock_curator_cls.assert_called_once()
            call_kwargs = mock_curator_cls.call_args[1]
            self.assertFalse(call_kwargs.get("debug"))

    @patch("gfr_curator.validator.validate_yaml_file")
    def test_validate_with_debug_flag(self, mock_validate):
        mock_validate.return_value = (True, [])
        with patch.object(sys, "argv", ["gfr-curate", "--validate", "test.yml", "--debug"]):
            with self.assertRaises(SystemExit) as cm:
                main()
            self.assertEqual(cm.exception.code, 0)
            mock_validate.assert_called_once()
            call_kwargs = mock_validate.call_args[1]
            self.assertTrue(call_kwargs.get("debug"))

if __name__ == "__main__":
    unittest.main()
