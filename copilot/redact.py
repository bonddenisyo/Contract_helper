"""Mask personal data locally before any text leaves the machine.

Money amounts, dates and durations are deliberately NOT masked: the analysis needs them.
The mapping stays local so the UI can show the original values back to the user.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

PATTERNS: list[tuple[str, re.Pattern]] = [
    ("EMAIL", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")),
    ("IBAN", re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){3,7}(?:\s?[A-Z0-9]{1,3})?\b")),
    ("CARD", re.compile(r"\b(?:\d{4}[ -]?){3}\d{4}\b")),
    ("PHONE", re.compile(r"(?<![\w$€£₺])\+?\d[\d ().-]{8,}\d\b")),
    ("ID", re.compile(r"\b\d{9,}\b")),
    ("ADDRESS", re.compile(
        r"\b\d{1,5}[A-Za-z]?\s+(?:[A-ZÇĞİÖŞÜ][\w'.-]*\s+){1,4}"
        r"(?:Street|St\.|Road|Rd\.|Avenue|Ave\.|Boulevard|Blvd\.|Lane|Ln\.|Drive|Dr\.|Way|Court|Place|Square"
        r"|Sokak|Sok\.|Caddesi|Cad\.|Bulvarı)\b(?:,?\s+(?:Unit|Apt\.?|Apartment|Suite|No\.?|Daire)\s*[\w-]+)?")),
]

# Contracts name their parties in a predictable way: Jane Doe ("Tenant"), Acme Ltd. (the "Client").
# We hide whatever stands before such a definition, so users don't have to type names in.
PARTY_DEF = re.compile(
    r"((?:[A-ZÇĞİÖŞÜ][\w&'.,-]*\s+){0,5}[A-ZÇĞİÖŞÜ][\w&'.-]*)\s*,?\s*\((?:the\s+|hereinafter\s+)?[\"“]([^\"”]{2,40})[\"”]\)")
NOT_PARTIES = {"agreement", "lease", "contract", "services", "premises", "term", "fees", "order form",
               "effective date", "confidential information", "deliverables", "work", "property", "statement of work"}
LEADING_NOISE = re.compile(r"^(?:This|The|And|Between|By|With|Of|To|For|Agreement|Lease|Contract)\s+", re.I)


def find_parties(text: str) -> list[str]:
    """Names defined as parties in the contract, e.g. 'Jane Doe' from: Jane Doe ("Tenant")."""
    names = []
    for m in PARTY_DEF.finditer(text):
        name, role = m.group(1).strip(" ,"), m.group(2).strip()
        if role.lower() in NOT_PARTIES:
            continue
        # "Subscription. CloudLedger Ltd." -> keep only the part after a heading/sentence break
        name = re.split(r"(?<!\bInc)(?<!\bLtd)(?<!\bCo)(?<!\bCorp)(?<!\b[A-Z])\.\s+", name)[-1]
        prev = None
        while prev != name:  # strip capitalised filler words that precede the real name
            prev, name = name, LEADING_NOISE.sub("", name)
        if len(name) >= 3 and name.lower() not in NOT_PARTIES and name.lower() != role.lower():
            names.append(name)
    return names


@dataclass
class Redaction:
    text: str
    mapping: dict[str, str] = field(default_factory=dict)  # placeholder -> original

    def restore(self, s: str) -> str:
        for ph, orig in self.mapping.items():
            s = s.replace(ph, orig)
        return s

    @property
    def hidden(self) -> dict[str, list[str]]:
        """What was hidden, by kind, for showing back to the user (never sent anywhere)."""
        out: dict[str, list[str]] = {}
        for ph, orig in self.mapping.items():
            out.setdefault(ph.strip("[]").rsplit("_", 1)[0], []).append(orig)
        return out

    @property
    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for ph in self.mapping:
            kind = ph.strip("[]").rsplit("_", 1)[0]
            out[kind] = out.get(kind, 0) + 1
        return out


def redact(text: str, extra_terms: list[str] | None = None) -> Redaction:
    """Replace personal data with placeholders like [EMAIL_1].

    Party names are found automatically from the contract's own definitions.
    extra_terms: anything else to hide (kept for programmatic use and tests).
    """
    mapping: dict[str, str] = {}
    seen: dict[str, str] = {}
    counters: dict[str, int] = {}

    def placeholder(kind: str, value: str) -> str:
        if value in seen:
            return seen[value]
        counters[kind] = counters.get(kind, 0) + 1
        ph = f"[{kind}_{counters[kind]}]"
        seen[value] = ph
        mapping[ph] = value
        return ph

    out = text
    terms = find_parties(text) + list(extra_terms or [])
    for term in sorted({t.strip() for t in terms if t.strip()}, key=len, reverse=True):
        out = re.sub(re.escape(term), lambda m: placeholder("NAME", m.group(0)), out, flags=re.I)
    for kind, pat in PATTERNS:
        out = pat.sub(lambda m, k=kind: placeholder(k, m.group(0)), out)
    return Redaction(text=out, mapping=mapping)
