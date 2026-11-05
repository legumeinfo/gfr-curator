import os
import re
import shutil
import subprocess
import logging

logger = logging.getLogger(__name__)

def extract_text_from_pdf(pdf_path: str) -> str:
    """
    Extracts plain text content from a local PDF file.
    Prefers pdftotext (poppler-utils) if available for speed and layout fidelity;
    falls back to pypdf.
    """
    if not os.path.isfile(pdf_path):
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    # 1. Try pdftotext if installed
    if shutil.which("pdftotext"):
        try:
            result = subprocess.run(
                ["pdftotext", pdf_path, "-"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False
            )
            if result.returncode == 0 and result.stdout and len(result.stdout.strip()) > 50:
                return result.stdout.strip()
        except Exception as e:
            logger.debug(f"pdftotext execution failed: {e}")

    # 2. Fall back to pypdf
    try:
        logging.getLogger("pypdf").setLevel(logging.ERROR)
        from pypdf import PdfReader
        reader = PdfReader(pdf_path)
        pages_text = []
        for page in reader.pages:
            txt = page.extract_text()
            if txt:
                pages_text.append(txt)
        extracted = "\n\n".join(pages_text).strip()
        if extracted:
            return extracted
    except ImportError:
        pass
    except Exception as e:
        logger.debug(f"pypdf extraction failed: {e}")

    if not shutil.which("pdftotext"):
        raise RuntimeError(
            "Could not extract text from PDF. Please install 'pypdf' (pip install pypdf) "
            "or 'pdftotext' (poppler-utils)."
        )
    raise ValueError(f"No extractable text found in PDF: '{pdf_path}'. The file may be image-only/scanned.")

def extract_doi_from_pdf(pdf_path: str, max_pages: int = 5) -> str | None:
    """
    Inspects the initial pages of a PDF to automatically detect a publication DOI.
    Returns the cleaned DOI string if found, otherwise None.
    """
    if not os.path.isfile(pdf_path):
        return None

    first_pages_text = ""

    # Try pdftotext first
    if shutil.which("pdftotext"):
        try:
            result = subprocess.run(
                ["pdftotext", "-l", str(max_pages), pdf_path, "-"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False
            )
            if result.returncode == 0 and result.stdout:
                first_pages_text = result.stdout
        except Exception:
            pass

    # Fallback to pypdf
    if not first_pages_text:
        try:
            logging.getLogger("pypdf").setLevel(logging.ERROR)
            from pypdf import PdfReader
            reader = PdfReader(pdf_path)
            num_pages = min(max_pages, len(reader.pages))
            pages = [reader.pages[i].extract_text() or "" for i in range(num_pages)]
            first_pages_text = "\n\n".join(pages)
        except Exception:
            pass

    if not first_pages_text:
        return None

    # Regex matching standard DOI formats
    doi_pattern = re.compile(
        r'(?:https?://(?:dx\.)?doi\.org/|doi:\s*|DOI:\s*)?(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)',
        re.IGNORECASE
    )
    for match in doi_pattern.finditer(first_pages_text):
        candidate = match.group(1).rstrip(".,;()[]{}'\"")
        # Ensure it looks like a reasonable DOI path
        if "/" in candidate and len(candidate.split("/")[1]) >= 2:
            return candidate

    # Secondary loose search for 10.xxxx/...
    loose_pattern = re.compile(r'\b(10\.\d{4,9}/[^\s"\'<>]+)')
    match = loose_pattern.search(first_pages_text)
    if match:
        return match.group(1).rstrip(".,;()[]{}'\"")

    return None
