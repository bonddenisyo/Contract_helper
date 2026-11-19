"""Build the 'ask a lawyer' package. Deterministic: no AI call, so it costs nothing and never invents.

The same content is rendered two ways: Markdown for the on-screen preview, and a Word
document (.docx) for the user to send to a lawyer. Built in memory; never saved on the server.
"""
from __future__ import annotations

import io
from datetime import date

from .taxonomy import CATEGORIES, ROLES

TITLE = "Contract questions for a lawyer"
DISCLAIMER = ("The tool is not a lawyer. Quotes are copied from the contract; explanations are the "
              "tool's plain-language reading and may be wrong.")


def _content(review, decisions: dict[str, dict], role: str) -> dict:
    """Everything the handoff says, in one place, so both formats always match."""
    restore = review.redaction.restore
    clause_text = {c.id: restore(c.text) for c in review.clauses}

    def item(f: dict) -> dict:
        return {
            "heading": f"{f['clause_id']}: {CATEGORIES[f['category']]}",
            "quote": restore(f["quote"]),
            "clause": clause_text.get(f["clause_id"], ""),
            "meaning": restore(f["explanation"]),
            "why": f["route_reason"],
            "change": restore(f["suggestion"]),
            "note": decisions.get(f["id"], {}).get("note", "").strip(),
        }

    escalated = review.by_route("lawyer")
    concerns = [f for f in review.flags
                if f["route"] != "lawyer" and decisions.get(f["id"], {}).get("decision") == "concern"]
    return {
        "prepared": f"Prepared {date.today().strftime('%d %B %Y')} by the signer "
                    f"({ROLES.get(role, role)}) with help from an AI review tool.",
        "overview": restore(review.summary),
        "sections": [(title, [item(f) for f in items]) for title, items in (
            ("Clauses the tool would not judge on its own", escalated),
            ("Clauses I marked as concerns", concerns),
        ) if items],
    }


def lawyer_summary(review, decisions: dict[str, dict], doc_name: str, role: str) -> str:
    """Markdown version, used for the preview in the app."""
    c = _content(review, decisions, role)
    lines = [f"# {TITLE}: {doc_name}", "", c["prepared"], DISCLAIMER, "",
             f"**Overview from the tool:** {c['overview']}", ""]
    for title, items in c["sections"]:
        lines.extend([f"## {title}", ""])
        for it in items:
            lines.append(f"### {it['heading']}")
            lines.append(f"> {it['quote']}")
            lines.append("")
            if it["meaning"]:
                lines.append(f"- What the tool thinks it means: {it['meaning']}")
            lines.append(f"- Why it is here: {it['why']}")
            if it["change"]:
                lines.append(f"- Possible change to request: {it['change']}")
            if it["note"]:
                lines.append(f"- **My question:** {it['note']}")
            lines.append("")
    if not c["sections"]:
        lines.append("_No clauses were escalated or marked as concerns._")
    return "\n".join(lines)


def lawyer_docx(review, decisions: dict[str, dict], doc_name: str, role: str) -> bytes:
    """Word version for the lawyer: the quote, the full clause, and room for their answer."""
    from docx import Document
    from docx.enum.text import WD_BREAK
    from docx.shared import Cm, Pt, RGBColor

    c = _content(review, decisions, role)
    grey, ink, accent = RGBColor(0x5F, 0x63, 0x68), RGBColor(0x1F, 0x23, 0x28), RGBColor(0x2F, 0x5D, 0x8A)

    doc = Document()
    for s in doc.sections:
        s.left_margin = s.right_margin = Cm(2.2)
        s.top_margin = s.bottom_margin = Cm(2)
    normal = doc.styles["Normal"]
    normal.font.name, normal.font.size, normal.font.color.rgb = "Calibri", Pt(11), ink
    normal.paragraph_format.space_after = Pt(4)
    for name, size in (("Title", 22), ("Heading 1", 15), ("Heading 2", 12)):
        st = doc.styles[name]
        st.font.name, st.font.size, st.font.color.rgb = "Calibri", Pt(size), accent if name != "Title" else ink
        st.font.bold = name != "Title"

    def label_line(label: str, text: str, italic: bool = False) -> None:
        p = doc.add_paragraph(style="List Bullet")
        p.add_run(label).bold = True
        r = p.add_run(text)
        r.italic = italic

    doc.add_paragraph(TITLE, style="Title")
    p = doc.add_paragraph()
    p.add_run(doc_name).bold = True
    meta = doc.add_paragraph()
    r = meta.add_run(f"{c['prepared']} {DISCLAIMER}")
    r.font.size, r.font.color.rgb = Pt(9.5), grey

    doc.add_heading("Overview", level=1)
    doc.add_paragraph(c["overview"])

    if not c["sections"]:
        doc.add_paragraph("No clauses were escalated or marked as concerns.")
    for title, items in c["sections"]:
        doc.add_heading(title, level=1)
        for i, it in enumerate(items):
            doc.add_heading(it["heading"], level=2)
            q = doc.add_paragraph()
            q.paragraph_format.left_indent = Cm(0.8)
            qr = q.add_run(f"“{it['quote']}”")
            qr.italic = True
            if it["meaning"]:
                label_line("What the tool thinks it means: ", it["meaning"])
            label_line("Why it is here: ", it["why"])
            if it["change"]:
                label_line("Possible change to request: ", it["change"])
            if it["note"]:
                label_line("My question: ", it["note"])
            if it["clause"] and it["clause"].strip() != it["quote"].strip():
                full = doc.add_paragraph()
                full.paragraph_format.left_indent = Cm(0.8)
                fr = full.add_run("Full clause: ")
                fr.bold, fr.font.size, fr.font.color.rgb = True, Pt(9), grey
                tr = full.add_run(it["clause"])
                tr.font.size, tr.font.color.rgb = Pt(9), grey
            answer = doc.add_paragraph()
            ar = answer.add_run("Lawyer's answer:")
            ar.bold, ar.font.color.rgb = True, accent
            answer.add_run().add_break(WD_BREAK.LINE)
            answer.add_run().add_break(WD_BREAK.LINE)
            answer.paragraph_format.space_after = Pt(14 if i < len(items) - 1 else 6)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
