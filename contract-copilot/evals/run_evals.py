"""Score the copilot against labeled contracts.

Usage:
  python -m evals.run_evals            # uses your configured free providers
  python -m evals.run_evals --demo     # rules only, offline

Metrics, in order of importance:
  1. Missed high-stakes clauses  -> must be 0. A miss here is the worst failure.
  2. Clause recall               -> share of risky clauses that got any flag.
  3. Category recall             -> share flagged with the right category.
  4. Clause precision            -> share of flagged clauses that were truly risky.
  5. False alarms on fair clauses
  6. Human workload              -> share of flags that need a person (review + lawyer).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))

from copilot.analyze import analyze  # noqa: E402

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT.parent / ".env")
except ImportError:
    pass


def _clause_for(review, snippet: str) -> str | None:
    s = snippet.lower()
    for c in review.clauses:
        if s in review.redaction.restore(c.text).lower():
            return c.id
    return None


def score_case(case: dict, demo: bool) -> dict:
    review = analyze(case["text"], role=case["role"], demo=demo or None)
    flagged: dict[str, list[dict]] = {}
    for f in review.flags:
        flagged.setdefault(f["clause_id"], []).append(f)

    res = {"name": case["name"], "provider": f"{review.provider} ({review.model})", "misses": [],
           "hs_missed": [], "false_alarms": [], "overflagged": []}
    exp_ids, cat_hits, clause_hits, hs_total = set(), 0, 0, 0
    for e in case["expected"]:
        cid = _clause_for(review, e["clause_contains"])
        if cid is None:
            raise ValueError(f"{case['name']}: snippet not found: {e['clause_contains']}")
        exp_ids.add(cid)
        fs = flagged.get(cid, [])
        if fs:
            clause_hits += 1
        if any(f["category"] == e["category"] for f in fs):
            cat_hits += 1
        elif fs:
            res["misses"].append(f"{cid} flagged as {fs[0]['category']}, expected {e['category']}")
        else:
            res["misses"].append(f"{cid} not flagged (expected {e['category']})")
        if e.get("high_stakes"):
            hs_total += 1
            if not any(f["route"] in ("review", "lawyer") for f in fs):
                res["hs_missed"].append(f"{cid} {e['category']}")

    opt_ids = set()
    for o in case.get("optional", []):
        cid = _clause_for(review, o["clause_contains"])
        opt_ids.add(cid)
        if any(f["risk"] == "high" for f in flagged.get(cid, [])):
            res["overflagged"].append(f"{cid} {o['category']} rated high risk")

    benign_ids = {_clause_for(review, b) for b in case.get("benign", [])} - {None}
    for cid in benign_ids & set(flagged):
        res["false_alarms"].append(f"{cid} {flagged[cid][0]['category']}")

    n_flagged = len(flagged)
    true_flagged = len(set(flagged) & (exp_ids | opt_ids))
    res.update(
        expected=len(case["expected"]), clause_hits=clause_hits, cat_hits=cat_hits, hs_total=hs_total,
        flagged_clauses=n_flagged, true_flagged=true_flagged, benign=len(benign_ids),
        n_flags=len(review.flags), human=len(review.by_route("review")) + len(review.by_route("lawyer")),
        lawyer=len(review.by_route("lawyer")), warnings=review.warnings,
    )
    return res


def pct(a: int, b: int) -> str:
    return f"{a / b:.0%}" if b else "n/a"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="rules only, no AI calls")
    args = ap.parse_args()

    cases = [json.loads(p.read_text()) for p in sorted((ROOT / "dataset").glob("*.json"))]
    results = [score_case(c, args.demo) for c in cases]

    T = lambda k: sum(r[k] for r in results)  # noqa: E731
    hs_missed = sum(len(r["hs_missed"]) for r in results)
    fa = sum(len(r["false_alarms"]) for r in results)
    lines = [
        f"# Eval report: {datetime.now():%Y-%m-%d %H:%M}",
        "",
        f"Provider: {results[0]['provider']}  |  Contracts: {len(results)}",
        "",
        "| Metric | Result | Target |",
        "|---|---|---|",
        f"| Missed high-stakes clauses | {hs_missed} of {T('hs_total')} | 0 |",
        f"| Clause recall | {pct(T('clause_hits'), T('expected'))} | ≥ 90% |",
        f"| Category recall | {pct(T('cat_hits'), T('expected'))} | ≥ 80% |",
        f"| Clause precision | {pct(T('true_flagged'), T('flagged_clauses'))} | ≥ 75% |",
        f"| False alarms on fair clauses | {fa} of {T('benign')} | ≤ 10% |",
        f"| Human workload (flags needing a person) | {pct(T('human'), T('n_flags'))} | watch |",
        f"| Sent to lawyer handoff | {T('lawyer')} flags | watch |",
        "",
    ]
    for r in results:
        lines.append(f"## {r['name']}")
        lines.append(f"- Recall {r['clause_hits']}/{r['expected']} clauses, {r['cat_hits']}/{r['expected']} with correct category")
        for k, label in (("hs_missed", "HIGH-STAKES MISSED"), ("misses", "Miss"), ("false_alarms", "False alarm"),
                         ("overflagged", "Over-flagged fair clause"), ("warnings", "Warning")):
            for item in r[k]:
                lines.append(f"- {label}: {item}")
        lines.append("")

    report = "\n".join(lines)
    print(report)
    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    tag = "demo" if args.demo else results[0]["provider"].split()[0]
    (out / f"{datetime.now():%Y%m%d-%H%M}-{tag}.md").write_text(report)


if __name__ == "__main__":
    main()
