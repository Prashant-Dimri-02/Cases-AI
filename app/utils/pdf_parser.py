# install: pip install pymupdf
import fitz  # PyMuPDF
import re
from typing import Union


def _clean_text(text: str) -> str:
    """
    Common text cleanup for extracted PDF text.
    """
    if not text:
        return ""

    # remove null characters
    text = text.replace("\x00", "")

    # normalize excessive newlines (keep paragraphs)
    text = re.sub(r"\n\s*\n+", "\n\n", text)

    # normalize spaces/tabs
    text = re.sub(r"[ \t]+", " ", text)

    # remove too many newlines
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def _extract_text_from_doc(doc: fitz.Document) -> str:
    """
    Core extraction logic from a PyMuPDF Document.
    """
    pages = []

    for page_num in range(len(doc)):
        page = doc.load_page(page_num)

        # primary extraction
        page_text = page.get_text("text")

        # fallback if empty
        if not page_text.strip():
            blocks = page.get_text("blocks")
            page_text = "\n".join(
                block[4] for block in blocks if block[4].strip()
            )

        page_text = _clean_text(page_text)
        if page_text:
            pages.append(page_text)

    return "\n\n".join(pages)


def extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    """
    Extract text from PDF bytes using PyMuPDF.

    Used when PDF is uploaded directly.
    """
    if not pdf_bytes:
        return ""

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        return _extract_text_from_doc(doc)
    finally:
        doc.close()


def extract_text_from_pdf_path(file_path: str) -> str:
    """
    Extract text from a local PDF file path using PyMuPDF.

    Used when PDF is already saved on disk.
    """
    if not file_path:
        return ""

    doc = fitz.open(file_path)
    try:
        return _extract_text_from_doc(doc)
    finally:
        doc.close()
