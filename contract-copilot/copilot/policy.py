"""Routing: who handles each flag. This file IS the automation boundary.

Routes:
  info    -> shown to the user as context; no decision needed
  review  -> the user decides (accept as a concern / dismiss)
  lawyer  -> packaged into the lawyer handoff; the copilot does not resolve it

Every route carries a human-readable reason, shown in the UI and stored in the audit log.
"""
from __future__ import annotations

from .taxonomy import HIGH_STAKES

LOW_CONFIDENCE = 0.6


def route(flag: dict) -> tuple[str, str]:
    cat, risk, conf = flag["category"], flag["risk"], flag.get("confidence")

    if flag.get("source") == "rules":
        return "review", "A safety rule matched, but the AI did not flag this clause. Please check it yourself."
    if not flag.get("verified", True):
        return "review", "The AI's quote could not be found in the contract, so it may be wrong. Check the clause."
    if risk == "high" and cat in HIGH_STAKES:
        return "lawyer", "High-risk clause in a category the copilot never resolves on its own."
    if conf is not None and conf < LOW_CONFIDENCE:
        if risk == "high":
            return "lawyer", f"High risk and the AI is unsure (confidence {conf:.0%})."
        return "review", f"The AI is unsure (confidence {conf:.0%})."
    if risk == "low":
        return "info", "Low risk: worth knowing, no action needed."
    return "review", "Moderate or high risk: your call."
