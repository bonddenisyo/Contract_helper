import json
import re
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


def test_parties_and_addresses_found_automatically():
    r = redact(LEASE["text"])
    assert set(r.hidden["NAME"]) == {"Harbor View Property LLC", "Jane Doe"}
    assert r.hidden["ADDRESS"] == ["12 Harbor View Road, Unit 4B"]
    assert r.hidden["PHONE"] == ["+1 415 555 0142"], "phone must not swallow the next clause number"
    assert "Jane Doe" not in r.text and "Landlord" in r.text and "$2,100" in r.text
    from copilot.redact import find_parties
    assert find_parties('This Agreement (the "Agreement") is made by Ayşe Kaya ("Tenant").') == ["Ayşe Kaya"]


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
    record_decision(con, rid, first["id"], "concern")
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


def test_audit_log_stores_no_contract_text(tmp_path):
    review = analyze(LEASE["text"], role="tenant", demo=True)
    con = connect(tmp_path / "b.db")
    rid = save_review(con, review, "lease.txt", "tenant")
    record_decision(con, rid, review.flags[0]["id"], "concern")
    dump = "\n".join(con.iterdump())
    for f in review.flags:
        assert f["quote"][:30] not in dump
    assert "automatically renew" not in dump and "Jane Doe" not in dump


class SeqProvider(llm.Provider):
    """Returns canned answers in order, to simulate a model misbehaving."""
    def __init__(self, replies):
        super().__init__("fake", "", "", "fake-model", "test")
        self.replies, self.calls = list(replies), 0

    def chat(self, system, user, **kw):
        self.calls += 1
        r = self.replies.pop(0) if self.replies else self.last
        self.last = r
        if isinstance(r, Exception):
            raise r
        return r


def test_unreadable_answer_is_retried_once():
    good = json.dumps({"summary": "A lease.", "flags": []})
    p = SeqProvider(["We need to look at the clauses. The tenant", good] * 10)
    review = analyze(LEASE["text"], role="tenant", providers=[p])
    assert not review.warnings and review.summary


def test_all_answers_unreadable_gives_one_clear_warning():
    p = SeqProvider([llm.ProviderError("fake: empty answer")])
    review = analyze(LEASE["text"], role="tenant", providers=[p])
    assert len(review.warnings) == 1 and "keyword safety rules only" in review.warnings[0]
    assert review.by_route("lawyer"), "rules must still catch high-stakes clauses"


class FakeResp:
    def __init__(self, status, payload):
        self.status_code, self._p, self.headers, self.text = status, payload, {}, json.dumps(payload)

    def json(self):
        return self._p


def test_cloudflare_request_sets_budget_and_handles_cutoff(monkeypatch):
    sent = []

    def post(url, headers, json, timeout):
        sent.append(dict(json))
        if len(sent) == 1:
            return FakeResp(400, {"error": "unknown field reasoning_effort"})
        return FakeResp(200, {"choices": [{"message": {"content": None}, "finish_reason": "length"}]})

    monkeypatch.setattr(llm.requests, "post", post)
    p = llm.Provider("cloudflare", "https://x", "k", "@cf/openai/gpt-oss-120b", "")
    try:
        p.chat("s", "u")
        raise AssertionError("expected ProviderError")
    except llm.ProviderError as e:
        assert "cut off" in str(e)
    assert sent[0]["max_tokens"] >= 4000 and sent[0]["reasoning_effort"] == "low"
    assert "reasoning_effort" not in sent[1], "retry without the option if the provider rejects it"


def test_slow_parts_are_cut_off_by_the_time_limit(monkeypatch):
    import time as _t
    from copilot import analyze as A

    class Slow(FakeProvider):
        def chat(self, system, user, **kw):
            if "[C1]" in user:
                _t.sleep(3)  # one stuck part
            return json.dumps({"summary": "ok", "flags": []})

    monkeypatch.setattr(A, "MAX_CHARS_PER_CALL", 300)
    monkeypatch.setattr(A, "REVIEW_TIME_LIMIT", 1.0)
    seen = []
    t0 = _t.monotonic()
    review = A.analyze(LEASE["text"], role="tenant", providers=[Slow("")], progress=lambda d, t: seen.append((d, t)))
    assert _t.monotonic() - t0 < 2.5, "the review must not wait for the stuck part"
    assert any("took too long" in w for w in review.warnings)
    assert any("C1" in w for w in review.warnings)
    assert seen[0][0] == 0 and seen[-1][0] >= 1, "progress is reported"


def test_overview_is_one_short_text_not_glued_part_summaries():
    from copilot import analyze as A
    long_part = json.dumps({"summary": "Part risk. " * 3, "flags": []})

    class P(FakeProvider):
        def chat(self, system, user, **kw):
            if "overview" in system:
                return json.dumps({"overview": " ".join(f"Sentence {i}." for i in range(1, 15))})
            return long_part

    old = A.MAX_CHARS_PER_CALL
    A.MAX_CHARS_PER_CALL = 300
    try:
        review = A.analyze(LEASE["text"], role="tenant", providers=[P("")])
    finally:
        A.MAX_CHARS_PER_CALL = old
    assert review.summary.startswith("Sentence 1.") and review.summary.endswith("Sentence 8.")
    assert "Part risk" not in review.summary


def test_overview_falls_back_without_ai():
    from copilot import analyze as A

    class P(FakeProvider):
        def chat(self, system, user, **kw):
            if "overview" in system:
                raise llm.ProviderError("down")
            return json.dumps({"summary": "x", "flags": []})

    review = A.analyze(LEASE["text"], role="tenant", providers=[P("")])
    assert review.summary.startswith("We found") and len(re.split(r"(?<=[.])\s+", review.summary)) <= 4
