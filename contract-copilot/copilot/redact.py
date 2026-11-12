"""Mask personal data locally before any text leaves the machine.

Money amounts, dates and durations are deliberately NOT masked: the analysis needs them.
The mapping stays local so the UI can show the original values back to the user.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

PATTERNS: list[tuple[str, re.Pattern]] = [
    ("EMAIL", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    ("IBAN", re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){3,7}(?:\s?[A-Z0-9]{1,3})?\b")),
    ("CARD", re.compile(r"\b(?:\d{4}[ -]?){3}\d{4}\b")),
    ("PHONE", re.compile(r"(?<![\w$€£₺])\+?\d[\d\s().-]{8,}\d\b")),
    ("ID", re.compile(r"\b\d{9,}\b")),
]


@dataclass
class Redaction:
    text: str
    mapping: dict[str, str] = field(default_factory=dict)  # placeholder -> original

    def restore(self, s: str) -> str:
        for ph, orig in self.mapping.items():
            s = s.replace(ph, orig)
        return s

    @property
    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for ph in self.mapping:
            kind = ph.strip("[]").rsplit("_", 1)[0]
            out[kind] = out.get(kind, 0) + 1
        return out


def redact(text: str, extra_terms: list[str] | None = None) -> Redaction:
    """Replace personal data with placeholders like [EMAIL_1].

    extra_terms: names/addresses the user asks to hide (e.g. party names). Name detection
    is unreliable with regex, so we let the user tell us instead of guessing.
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
    for term in sorted({t.strip() for t in (extra_terms or []) if t.strip()}, key=len, reverse=True):
        out = re.sub(re.escape(term), lambda m: placeholder("NAME", m.group(0)), out, flags=re.I)
    for kind, pat in PATTERNS:
        out = pat.sub(lambda m, k=kind: placeholder(k, m.group(0)), out)
    return Redaction(text=out, mapping=mapping)
