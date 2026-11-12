"""Build the 'ask a lawyer' package. Deterministic: no AI call, so it costs nothing and never invents."""
from __future__ import annotations

from datetime import date

from .taxonomy import CATEGORIES, ROLES


def lawyer_summary(review, decisions: dict[str, dict], doc_name: str, role: str) -> str:
    restore = review.redaction.restore
    escalated = review.by_route("lawyer")
    concerns = [f for f in review.flags if f["route"] != "lawyer" and decisions.get(f["id"], {}).get("decision") == "concern"]

    lines = [
        f"# Contract questions for a lawyer: {doc_name}",
        "",
        f"Prepared {date.today().isoformat()} by the signer ({ROLES.get(role, role)}) with help from an AI review tool.",
        "The tool is not a lawyer. Quotes below are copied from the contract; explanations are the tool's plain-language reading.",
        "",
        f"**Overview from the tool:** {restore(review.summary)}",
        "",
    ]

    def block(title: str, items: list[dict]) -> None:
        if not items:
            return
        lines.extend([f"## {title}", ""])
        for f in items:
            note = decisions.get(f["id"], {}).get("note", "").strip()
            lines.append(f"### {f['clause_id']}: {CATEGORIES[f['category']]}")
            lines.append(f"> {restore(f['quote'])}")
            lines.append("")
            if f["explanation"]:
                lines.append(f"- What the tool thinks it means: {restore(f['explanation'])}")
            lines.append(f"- Why it is here: {f['route_reason']}")
            if f["suggestion"]:
                lines.append(f"- Possible change to request: {restore(f['suggestion'])}")
            if note:
                lines.append(f"- **My question:** {note}")
            lines.append("")

    block("Clauses the tool would not judge on its own", escalated)
    block("Clauses I marked as concerns", concerns)
    if not escalated and not concerns:
        lines.append("_No clauses were escalated or marked as concerns._")
    return "\n".join(lines)
