"""The review pipeline: redact -> split -> rules -> model -> verify -> merge -> route."""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

from .clauses import Clause, split_clauses
from .llm import DEMO, Provider, available_providers, chat_with_fallback, parse_json
from .policy import route
from .redact import Redaction, redact
from .rules import rule_hits
from .taxonomy import CATEGORIES, HIGH_STAKES, ROLES

MAX_CHARS_PER_CALL = 20000
RISKS = ("low", "medium", "high")

SYSTEM_PROMPT = """You review contracts for {role}. You are not a lawyer and you do not give legal advice.
Your job: find clauses that carry meaningful risk or are unusual/unfavourable for the signer, and explain them in plain language.

Rules:
- Only flag clauses that a careful friend with legal knowledge would point out. Do not flag standard, balanced boilerplate.
- "quote" must be copied EXACTLY from the clause text (max 30 words). Never paraphrase inside "quote".
- "confidence" (0-1) is how sure you are the clause really carries this risk. Be honest; use <0.6 when the wording is ambiguous.
- "suggestion" is a short, polite change the signer could ask for.
- Placeholders like [EMAIL_1] or [NAME_1] are hidden personal data; ignore them.
- Use these categories only: {categories}

Reply with JSON only:
{{"flags":[{{"clause_id":"C3","category":"auto_renewal","risk":"low|medium|high","confidence":0.85,"quote":"...","explanation":"...","suggestion":"..."}}],
 "summary":"2-3 sentence plain-language overview of the contract and its biggest risks"}}"""


@dataclass
class Review:
    clauses: list[Clause]
    redaction: Redaction
    flags: list[dict]
    summary: str
    provider: str
    model: str
    privacy_note: str
    warnings: list[str] = field(default_factory=list)

    def by_route(self, r: str) -> list[dict]:
        return [f for f in self.flags if f["route"] == r]


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower().strip("\"'“”.")


def verify_quote(quote: str, clause_text: str) -> bool:
    """True if the quote really appears in the clause (allowing whitespace/punctuation drift)."""
    q, c = _norm(quote), _norm(clause_text)
    if not q:
        return False
    if q in c:
        return True
    m = difflib.SequenceMatcher(None, q, c, autojunk=False).find_longest_match(0, len(q), 0, len(c))
    return m.size >= 0.85 * len(q)


def _chunks(clauses: list[Clause]) -> list[list[Clause]]:
    out, cur, size = [], [], 0
    for c in clauses:
        if cur and size + len(c.text) > MAX_CHARS_PER_CALL:
            out.append(cur)
            cur, size = [], 0
        cur.append(c)
        size += len(c.text)
    if cur:
        out.append(cur)
    return out


def _clean_flag(raw: dict, clause_ids: set[str]) -> dict | None:
    cid = str(raw.get("clause_id", "")).strip()
    if cid not in clause_ids:
        return None
    cat = raw.get("category", "other")
    if cat not in CATEGORIES:
        cat = "other"
    risk = str(raw.get("risk", "medium")).lower()
    if risk not in RISKS:
        risk = "medium"
    try:
        conf = max(0.0, min(1.0, float(raw.get("confidence", 0.5))))
    except (TypeError, ValueError):
        conf = 0.5
    return {
        "clause_id": cid,
        "category": cat,
        "risk": risk,
        "confidence": conf,
        "quote": str(raw.get("quote", "")).strip(),
        "explanation": str(raw.get("explanation", "")).strip(),
        "suggestion": str(raw.get("suggestion", "")).strip(),
        "source": "model",
    }


def _sentence_with(text: str, match: str) -> str:
    for s in re.split(r"(?<=[.;:])\s+", text):
        if match.lower() in s.lower():
            return s.strip()[:300]
    return match


def _demo_flags(clauses: list[Clause], hits: list[dict]) -> tuple[list[dict], str]:
    """Rules-only analysis used when no AI key is configured (and in tests)."""
    by_id = {c.id: c for c in clauses}
    flags = []
    for h in hits:
        c = by_id[h["clause_id"]]
        cat = h["category"]
        flags.append({
            "clause_id": c.id,
            "category": cat,
            "risk": "high" if cat in HIGH_STAKES else "medium",
            "confidence": 0.7,
            "quote": _sentence_with(c.text, h["match"]),
            "explanation": f"{CATEGORIES[cat]}. (Demo mode: found by a keyword rule, not by AI.)",
            "suggestion": "Ask for this clause to be removed, limited, or made mutual.",
            "source": "model",  # in demo mode the rules play the model's part
        })
    summary = (f"Demo mode (no AI key configured): {len(flags)} clauses matched keyword rules. "
               "Add a free API key to get plain-language explanations.")
    return flags, summary


def analyze(text: str, role: str = "tenant", extra_terms: list[str] | None = None,
            providers: list[Provider] | None = None, demo: bool | None = None) -> Review:
    red = redact(text, extra_terms)
    clauses = split_clauses(red.text)
    if not clauses:
        raise ValueError("No text found in the document.")
    ids = {c.id for c in clauses}
    hits = rule_hits(clauses)
    warnings: list[str] = []

    providers = available_providers() if providers is None else providers
    if demo is None:
        demo = not providers

    if demo:
        flags, summary = _demo_flags(clauses, hits)
        prov_name, model, privacy = DEMO, "keyword rules", "Demo mode: nothing leaves your computer."
    else:
        system = SYSTEM_PROMPT.format(role=ROLES.get(role, role), categories=", ".join(CATEGORIES))
        flags, summaries, used = [], [], None
        for chunk in _chunks(clauses):
            user = "\n\n".join(f"[{c.id}]\n{c.text}" for c in chunk)
            raw, used = chat_with_fallback(system, user, providers)
            try:
                data = parse_json(raw)
            except ValueError as e:
                warnings.append(f"Could not read the AI's answer for part of the contract ({e}). "
                                "Those clauses are covered by safety rules only.")
                continue
            for f in data.get("flags", []):
                cf = _clean_flag(f, ids) if isinstance(f, dict) else None
                if cf:
                    flags.append(cf)
            if data.get("summary"):
                summaries.append(str(data["summary"]))
        summary = " ".join(summaries) or "No summary returned."
        prov_name, model, privacy = used.name, used.model, used.privacy_note

    # Verify every quote against the clause it claims to come from.
    by_id = {c.id: c for c in clauses}
    for f in flags:
        f["verified"] = verify_quote(f["quote"], by_id[f["clause_id"]].text)

    # Safety net: rule hits the model did not cover become review items.
    covered = {(f["clause_id"], f["category"]) for f in flags}
    covered_clauses = {f["clause_id"] for f in flags}
    for h in hits:
        key = (h["clause_id"], h["category"])
        if key in covered:
            for f in flags:
                if (f["clause_id"], f["category"]) == key and f["source"] == "model" and not demo:
                    f["source"] = "model+rules"
            continue
        if h["clause_id"] in covered_clauses:
            continue  # model flagged the clause under another category; good enough
        flags.append({
            "clause_id": h["clause_id"], "category": h["category"], "risk": "medium", "confidence": None,
            "quote": _sentence_with(by_id[h["clause_id"]].text, h["match"]),
            "explanation": f"Safety rule matched: {CATEGORIES[h['category']].lower()}.",
            "suggestion": "", "source": "rules", "verified": True,
        })
        covered_clauses.add(h["clause_id"])

    order = {"high": 0, "medium": 1, "low": 2}
    flags.sort(key=lambda f: (order[f["risk"]], int(f["clause_id"][1:])))
    for i, f in enumerate(flags):
        f["id"] = f"F{i + 1}"
        f["route"], f["route_reason"] = route(f)

    return Review(clauses, red, flags, summary, prov_name, model, privacy, warnings)
