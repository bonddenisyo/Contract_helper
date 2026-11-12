"""Cheap, deterministic safety net. Runs locally on every clause.

Rules are not smart, but they never get tired or hallucinate. If a rule fires and the model
says nothing, the clause goes to human review: disagreement between layers is a signal.
In v2 a trained clause classifier replaces/extends this layer.
"""
from __future__ import annotations

import re

from .clauses import Clause

RULES: dict[str, list[str]] = {
    "auto_renewal": [r"automatic(?:ally)?\s+renew", r"auto[- ]renew", r"renew(?:s|ed)?\s+for\s+(?:successive|additional)"],
    "early_termination_penalty": [r"early\s+termination\s+(?:fee|charge|penalty)", r"liquidated\s+damages", r"remaining\s+(?:rent|fees)\s+(?:for|through|until)"],
    "uncapped_liability": [r"unlimited\s+liability", r"without\s+limit(?:ation)?\s+(?:as\s+to|of)\s+amount", r"liable\s+for\s+(?:any\s+and\s+)?all\s+(?:losses|damages)"],
    "indemnification": [r"indemnif", r"hold\s+harmless"],
    "non_compete": [r"non[- ]compet", r"shall\s+not\s+(?:directly\s+or\s+indirectly\s+)?(?:compete|provide\s+services\s+to|work\s+for)"],
    "ip_assignment": [r"assigns?\s+(?:to\s+\w+\s+)?all\s+(?:right|intellectual)", r"all\s+intellectual\s+property\s+(?:created|developed|conceived)", r"whether\s+or\s+not\s+related\s+to"],
    "payment_terms": [r"net\s*(?:60|75|90|120)", r"within\s+(?:sixty|ninety|60|90|120)\s+days", r"late\s+fee", r"sole\s+discretion\s+to\s+withhold"],
    "deposit": [r"deposit\s+(?:is|shall\s+be)\s+non[- ]refundable", r"retain\s+the\s+(?:entire\s+)?(?:security\s+)?deposit", r"forfeit"],
    "rent_increase": [r"increase\s+(?:the\s+)?(?:rent|fees?|price)\s+at\s+any\s+time", r"(?:rent|fees?)\s+may\s+be\s+(?:increased|adjusted)"],
    "unilateral_changes": [r"may\s+(?:amend|modify|change)\s+(?:this|these|the)\s+(?:agreement|terms|lease|contract)\s+at\s+any\s+time", r"sole\s+discretion\s+to\s+(?:amend|modify|change)"],
    "dispute_resolution": [r"binding\s+arbitration", r"waives?\s+(?:any\s+)?right\s+to\s+(?:a\s+)?(?:jury|trial)", r"class\s+action\s+waiver", r"exclusive\s+jurisdiction"],
    "personal_guarantee": [r"personal(?:ly)?\s+guarant"],
    "entry_access": [r"enter\s+the\s+(?:premises|property|unit)\s+at\s+any\s+time", r"enter\b[^.]{0,80}without\s+(?:prior\s+)?notice"],
    "confidentiality": [r"in\s+perpetuity", r"survive\s+indefinitely", r"perpetual(?:ly)?\s+confidential"],
    "termination": [r"terminate\s+(?:this\s+agreement\s+)?(?:at\s+any\s+time\s+)?(?:for\s+any\s+reason\s+or\s+no\s+reason|without\s+cause)"],
}

_COMPILED = {cat: [re.compile(p, re.I) for p in pats] for cat, pats in RULES.items()}


def rule_hits(clauses: list[Clause]) -> list[dict]:
    """Return [{clause_id, category, match}] for every rule that fires."""
    hits = []
    for c in clauses:
        for cat, pats in _COMPILED.items():
            for p in pats:
                m = p.search(c.text)
                if m:
                    hits.append({"clause_id": c.id, "category": cat, "match": m.group(0)})
                    break
    return hits
