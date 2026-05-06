"""
CipherLens — Multi-Format Text Extraction Pipeline

Extracts readable text from various document formats:
  • PDF (digital)  → PyMuPDF (fitz)
  • PDF (scanned)  → pytesseract OCR via Pillow
  • Images         → pytesseract OCR
  • DOCX           → python-docx
  • TXT            → Direct UTF-8 read

The pipeline intelligently falls back to OCR if a PDF yields no
extractable text (indicating it's a scanned document).
"""

import io
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# Supported file extensions
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"}
PDF_EXTENSIONS = {".pdf"}
DOCX_EXTENSIONS = {".docx"}
TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".xml", ".html"}

# Windows-friendly defaults; can be overridden with TESSERACT_CMD env var.
_TESSERACT_CANDIDATES = [
    os.getenv("TESSERACT_CMD", "").strip(),
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
]


def _configure_tesseract_path(pytesseract_module) -> None:
    """Point pytesseract to an installed binary when PATH is stale/missing."""
    for candidate in _TESSERACT_CANDIDATES:
        if candidate and os.path.exists(candidate):
            pytesseract_module.pytesseract.tesseract_cmd = candidate
            return


def _extract_text_from_pdf(file_data: bytes) -> str:
    """
    Extract text from a PDF using PyMuPDF.
    Falls back to OCR if no text is found (scanned PDF).
    """
    import fitz  # PyMuPDF

    text_parts = []
    try:
        doc = fitz.open(stream=file_data, filetype="pdf")
        for page in doc:
            text_parts.append(page.get_text())
        doc.close()
    except Exception as e:
        logger.warning(f"PyMuPDF text extraction failed: {e}")
        return ""

    full_text = "\n".join(text_parts).strip()

    # If no text found, the PDF is likely scanned — try OCR
    if not full_text:
        logger.info("No digital text in PDF, attempting OCR...")
        full_text = _ocr_pdf(file_data)

    return full_text


def _ocr_pdf(file_data: bytes) -> str:
    """
    OCR a scanned PDF by converting each page to an image, then running
    Tesseract on each page image.
    """
    try:
        import fitz  # PyMuPDF
        from PIL import Image
        import pytesseract
        _configure_tesseract_path(pytesseract)
    except ImportError as e:
        logger.warning(f"OCR dependencies not available: {e}")
        return ""

    text_parts = []
    try:
        doc = fitz.open(stream=file_data, filetype="pdf")
        for page_num, page in enumerate(doc):
            # Render page to a pixmap (image)
            pix = page.get_pixmap(dpi=200)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            page_text = pytesseract.image_to_string(img)
            text_parts.append(page_text)
        doc.close()
    except Exception as e:
        logger.warning(f"OCR on PDF failed: {e}")

    return "\n".join(text_parts).strip()


def _extract_text_from_image(file_data: bytes) -> str:
    """Extract text from an image using Tesseract OCR."""
    try:
        from PIL import Image
        import pytesseract
        _configure_tesseract_path(pytesseract)
    except ImportError as e:
        logger.warning(f"OCR dependencies not available: {e}")
        return ""

    try:
        img = Image.open(io.BytesIO(file_data))
        text = pytesseract.image_to_string(img)
        return text.strip()
    except Exception as e:
        logger.warning(f"Image OCR failed: {e}")
        return ""


def _extract_text_from_docx(file_data: bytes) -> str:
    """Extract text from a DOCX file using python-docx."""
    try:
        from docx import Document
    except ImportError as e:
        logger.warning(f"python-docx not available: {e}")
        return ""

    try:
        doc = Document(io.BytesIO(file_data))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n".join(paragraphs)
    except Exception as e:
        logger.warning(f"DOCX extraction failed: {e}")
        return ""


def _extract_text_from_txt(file_data: bytes) -> str:
    """Extract text from a plain text file."""
    try:
        return file_data.decode("utf-8").strip()
    except UnicodeDecodeError:
        try:
            return file_data.decode("latin-1").strip()
        except Exception:
            return ""


def extract_text(file_data: bytes, filename: str) -> str:
    """
    Extract text from a file based on its extension.

    Args:
        file_data: Raw bytes of the file.
        filename: Original filename (used to determine file type).

    Returns:
        Extracted text as a string. Empty string if extraction fails.
    """
    import os
    ext = os.path.splitext(filename.lower())[1]

    if ext in PDF_EXTENSIONS:
        text = _extract_text_from_pdf(file_data)
    elif ext in IMAGE_EXTENSIONS:
        text = _extract_text_from_image(file_data)
    elif ext in DOCX_EXTENSIONS:
        text = _extract_text_from_docx(file_data)
    elif ext in TEXT_EXTENSIONS:
        text = _extract_text_from_txt(file_data)
    else:
        logger.info(f"Unsupported file type for text extraction: {ext}")
        text = ""

    if text:
        logger.info(f"Extracted {len(text)} characters from {filename}")
    else:
        logger.warning(f"No text extracted from {filename}")

    return text
