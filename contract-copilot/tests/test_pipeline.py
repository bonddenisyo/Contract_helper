import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from copilot import llm  # noqa: E402
from copilot.analyze import analyze, verify_quote  # noqa: E402
from copilot.clauses import split_clauses  # noqa: E402
from copilot.handoff import lawyer_summary  # noqa: E402
from copilot.policy import route  # noqa: E402
from copilot.redact import redact  # noqa: E402
from copilot.store import connect, decision_stats, record_decision, save_review  # noqa: E402

LEASE = json.loads((ROOT / "evals/dataset/lease_harbor_view.json").read_text())


def test_redact_masks_personal_data_but_keeps_money():
    r = redact("Call +1 415 555 0142 or mail a@b.com. Rent is $2,100. Pay to Jane Doe.", ["Jane Doe"])
    assert "a@b.com" not in r.text and "555 0142" not in r.text and "Jane Doe" not in r.text
    assert "$2,100" in r.text
    assert r.restore(r.text).endswith("Pay to Jane Doe.")


def test_clauses_split_on_numbering():
    cs = split_clauses(LEASE["text"])
    assert len(cs) >= 14
    assert any("automatically renew" in c.text for c in cs)


def test_quote_verification():
    clause = "This Lease shall automatically renew for successive twelve-month terms."
    assert verify_quote("shall automatically renew", clause)
    assert verify_quote("“This lease shall  automatically renew”", clause)
    assert not verify_quote("tenant may cancel at any time", clause)


def test_routing_policy():
    base = {"source": "model", "verified": True, "confidence": 0.9}
    assert route({**base, "category": "indemnification", "risk": "high"})[0] == "lawyer"
    assert route({**base, "category": "auto_renewal", "risk": "high", "confidence": 0.4})[0] == "lawyer"
    assert route({**base, "category": "auto_renewal", "risk": "medium", "confidence": 0.4})[0] == "review"
    assert route({**base, "category": "auto_renewal", "risk": "low"})[0] == "info"
    assert route({**base, "category": "indemnification", "risk": "high", "verified": False})[0] == "review"
    assert route({**base, "category": "deposit", "risk": "medium", "source": "rules"})[0] == "review"


def test_demo_pipeline_end_to_end(tmp_path):
    review = analyze(LEASE["text"], role="tenant", extra_terms=["Jane Doe"], demo=True)
    assert review.provider == "demo"
    assert review.by_route("lawyer"), "high-stakes clauses must reach the lawyer handoff"
    assert all(f["verified"] for f in review.flags)
    assert "jane.doe@example.com" not in "\n".join(c.text for c in review.clauses)

    con = connect(tmp_path / "a.db")
    rid = save_review(con, review, "lease.txt", "tenant")
    first = review.by_route("review")[0]
    record_decision(con, rid, first["id"], "concern", "Can this be 60 days?")
    assert decision_stats(con)[first["category"]]["concern"] == 1

    md = lawyer_summary(review, {first["id"]: {"decision": "concern", "note": "Can this be 60 days?"}}, "lease.txt", "tenant")
    assert "Can this be 60 days?" in md and "Clauses the tool would not judge on its own" in md


class FakeProvider(llm.Provider):
    def __init__(self, reply: str):
        super().__init__("fake", "", "", "fake-model", "test")
        self.reply = reply

    def chat(self, system, user, **kw):
        return self.reply


def test_model_path_verifies_quotes_and_adds_rule_safety_net():
    review0 = analyze(LEASE["text"], role="tenant", demo=True)
    renew = next(c for c in review0.clauses if "automatically renew" in c.text)
    reply = json.dumps({"summary": "A lease.", "flags": [
        {"clause_id": renew.id, "category": "auto_renewal", "risk": "medium", "confidence": 0.9,
         "quote": "shall automatically renew for successive twelve-month terms", "explanation": "x", "suggestion": "y"},
        {"clause_id": renew.id, "category": "deposit", "risk": "high", "confidence": 0.9,
         "quote": "this sentence is invented", "explanation": "x", "suggestion": "y"},
        {"clause_id": "C999", "category": "other", "risk": "high", "quote": "ghost clause"},
    ]})
    review = analyze(LEASE["text"], role="tenant", providers=[FakeProvider("```json\n" + reply + "\n```")])
    f_ok = next(f for f in review.flags if f["category"] == "auto_renewal")
    f_bad = next(f for f in review.flags if f["category"] == "deposit" and f["clause_id"] == renew.id)
    assert f_ok["verified"] and f_ok["source"] == "model+rules"
    assert not f_bad["verified"] and f_bad["route"] == "review"
    assert not any(f["clause_id"] == "C999" for f in review.flags)
    assert any(f["source"] == "rules" for f in review.flags), "rule hits the model missed must be surfaced"


def test_fallback_skips_failing_provider():
    class Broken(FakeProvider):
        def chat(self, system, user, **kw):
            raise llm.ProviderError("rate limited (429)")

    text, used = llm.chat_with_fallback("s", "u", [Broken("x"), FakeProvider('{"flags": []}')])
    assert used.name == "fake" and text == '{"flags": []}'
