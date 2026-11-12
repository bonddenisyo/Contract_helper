"""Turn an uploaded file into plain text. Everything runs locally."""
from __future__ import annotations

import io


def extract_text(filename: str, data: bytes) -> str:
    name = filename.lower()
    if name.endswith(".pdf"):
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        pages = [(p.extract_text() or "") for p in reader.pages]
        text = "\n\n".join(pages)
        if not text.strip():
            raise ValueError(
                "This PDF has no readable text (it may be a scan). "
                "Try a text-based PDF, a .docx, or paste the text."
            )
        return text
    if name.endswith(".docx"):
        from docx import Document

        doc = Document(io.BytesIO(data))
        return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
    if name.endswith((".txt", ".md")):
        return data.decode("utf-8", errors="replace")
    raise ValueError("Unsupported file type. Use PDF, DOCX or TXT.")
