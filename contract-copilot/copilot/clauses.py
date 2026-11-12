"""Split a contract into numbered clauses so every flag can point at exact text."""
from __future__ import annotations

import re
from dataclasses import dataclass

HEADING = re.compile(
    r"^\s*(?:(?:section|article|clause)\s+\d+[\w.]*|\d+(?:\.\d+)*[.)]?\s+\S|\([a-z0-9]{1,3}\)\s+\S)",
    re.I,
)


@dataclass
class Clause:
    id: str
    text: str

    @property
    def heading(self) -> str:
        first = self.text.strip().splitlines()[0]
        return first[:80]


def split_clauses(text: str, min_len: int = 40) -> list[Clause]:
    text = text.replace("\r\n", "\n")
    blocks: list[str] = []
    current: list[str] = []
    for line in text.split("\n"):
        if not line.strip():
            if current:
                blocks.append("\n".join(current))
                current = []
            continue
        if HEADING.match(line) and current:
            blocks.append("\n".join(current))
            current = []
        current.append(line.rstrip())
    if current:
        blocks.append("\n".join(current))

    # Merge short fragments (titles, lone headings) into the next block.
    merged: list[str] = []
    carry = ""
    for b in blocks:
        b = (carry + "\n" + b).strip() if carry else b.strip()
        if len(b) < min_len:
            carry = b
            continue
        merged.append(b)
        carry = ""
    if carry:
        if merged:
            merged[-1] += "\n" + carry
        else:
            merged.append(carry)
    return [Clause(id=f"C{i + 1}", text=b) for i, b in enumerate(merged)]
