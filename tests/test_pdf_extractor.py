import os
import unittest
from unittest.mock import patch, MagicMock
from gfr_curator.pdf_extractor import extract_text_from_pdf, extract_doi_from_pdf

class TestPdfExtractor(unittest.TestCase):
    def test_extract_text_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            extract_text_from_pdf("nonexistent_test_file_12345.pdf")

    @patch("shutil.which", return_value=None)
    @patch("pypdf.PdfReader")
    def test_extract_text_pypdf(self, mock_reader_cls, mock_which):
        mock_reader = MagicMock()
        page1 = MagicMock()
        page1.extract_text.return_value = "Page 1 content on legumes"
        page2 = MagicMock()
        page2.extract_text.return_value = "Page 2 content on genes"
        mock_reader.pages = [page1, page2]
        mock_reader_cls.return_value = mock_reader

        with patch("os.path.isfile", return_value=True):
            text = extract_text_from_pdf("fake.pdf")
            self.assertIn("Page 1 content on legumes", text)
            self.assertIn("Page 2 content on genes", text)

    @patch("shutil.which", return_value="/usr/bin/pdftotext")
    @patch("subprocess.run")
    def test_extract_text_pdftotext(self, mock_subprocess_run, mock_which):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "A" * 100  # More than 50 chars
        mock_subprocess_run.return_value = mock_result

        with patch("os.path.isfile", return_value=True):
            text = extract_text_from_pdf("fake.pdf")
            self.assertEqual(text, "A" * 100)
            mock_subprocess_run.assert_called_once()

    def test_extract_doi_from_pdf_nonexistent_returns_none(self):
        result = extract_doi_from_pdf("nonexistent_test_file_12345.pdf")
        self.assertIsNone(result)

    @patch("shutil.which", return_value="/usr/bin/pdftotext")
    @patch("subprocess.run")
    def test_extract_doi_regex_formats(self, mock_subprocess_run, mock_which):
        sample_texts = [
            ("https://doi.org/10.1038/s41588-026-02577-z", "10.1038/s41588-026-02577-z"),
            ("doi: 10.1093/jxb/erw425.", "10.1093/jxb/erw425"),
            ("DOI:10.1111/tpj.15342;", "10.1111/tpj.15342"),
        ]
        with patch("os.path.isfile", return_value=True):
            for raw_text, expected_doi in sample_texts:
                mock_result = MagicMock()
                mock_result.returncode = 0
                mock_result.stdout = f"Header info\n{raw_text}\nRest of publication..."
                mock_subprocess_run.return_value = mock_result

                detected = extract_doi_from_pdf("fake.pdf")
                self.assertEqual(detected, expected_doi)

    def test_real_pdf_if_present(self):
        # If the local sample PDF exists in the working directory, test it directly
        local_pdf = "41588_2026_Article_2577.pdf"
        if os.path.isfile(local_pdf):
            doi = extract_doi_from_pdf(local_pdf)
            self.assertEqual(doi, "10.1038/s41588-026-02577-z")
            text = extract_text_from_pdf(local_pdf)
            self.assertGreater(len(text), 1000)
            self.assertIn("peanut", text.lower())

if __name__ == "__main__":
    unittest.main()
