"""Contract Copilot: the AI flags, you decide, a lawyer gets what the AI shouldn't judge.

Run:  streamlit run app.py
"""
from __future__ import annotations

import hmac
import json
import os
from pathlib import Path

import streamlit as st

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

from copilot.analyze import analyze
from copilot.handoff import lawyer_summary
from copilot.llm import ProviderError, available_providers
from copilot.parsing import extract_text
from copilot.store import connect, decision_stats, recent, record_decision, reviews_today, save_review
from copilot.taxonomy import CATEGORIES, ROLES

st.set_page_config(page_title="Contract Copilot", page_icon="📄", layout="wide")

SAMPLES = {json.loads(p.read_text())["name"]: json.loads(p.read_text())
           for p in sorted((Path(__file__).parent / "evals" / "dataset").glob("*.json"))}
ROUTE_BADGE = {"lawyer": "🔴 Ask a lawyer", "review": "🟡 Your decision", "info": "🟢 Good to know"}
RISK_BADGE = {"high": "High risk", "medium": "Medium risk", "low": "Low risk"}

# Public-deployment guardrails (set as environment variables on the host).
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")        # set it to hide the audit log from visitors
SESSION_LIMIT = int(os.environ.get("MAX_REVIEWS_PER_SESSION", "5"))
DAILY_LIMIT = int(os.environ.get("DAILY_REVIEW_LIMIT", "100"))  # protects your free-tier AI quota


@st.cache_resource
def db():
    return connect()


con = db()
ss = st.session_state
ss.setdefault("review", None)
ss.setdefault("decisions", {})
ss.setdefault("reviews_run", 0)
ss.setdefault("is_admin", not ADMIN_PASSWORD)

# ---------- Sidebar ----------
with st.sidebar:
    st.header("Contract Copilot")
    st.caption("Flags risky clauses in plain language. **Not legal advice.** You make every decision.")
    providers = available_providers()
    if providers:
        st.success("AI: " + " → ".join(p.name for p in providers))
        st.caption("If the first provider hits its free limit, the next one is used.")
    else:
        st.warning("Demo mode: no AI key found. Keyword rules only. See README to add a free key.")
    page = st.radio("Page", ["Review a contract", "Audit log"], label_visibility="collapsed")
    st.caption("Built as a portfolio project. Your contract text is not stored.")

# ---------- Audit log (admin only on a public deployment) ----------
if page == "Audit log":
    st.title("Audit log")
    if not ss.is_admin:
        pw = st.text_input("Admin password", type="password")
        if pw and hmac.compare_digest(pw, ADMIN_PASSWORD):
            ss.is_admin = True
            st.rerun()
        elif pw:
            st.error("Wrong password.")
        st.stop()
    st.caption("What the copilot flagged, how it routed each flag, and what people decided. Contract text is never stored.")
    rows = recent(con)
    if rows:
        st.dataframe(rows, width="stretch")
    else:
        st.info("No reviews yet.")
    st.subheader("Human agreement by category")
    st.caption("'concern' = the person agreed with the flag. 'dismissed' = they disagreed. Use this to tune prompts and rules.")
    stats = decision_stats(con)
    if stats:
        st.dataframe([{"category": c, **d} for c, d in stats.items()], width="stretch")
    else:
        st.info("No decisions recorded yet.")
    st.stop()

# ---------- Step 1: input ----------
st.title("Review a contract")
c1, c2 = st.columns([3, 2])
with c1:
    source = st.radio("Contract", ["Use a sample", "Upload a file", "Paste text"], horizontal=True)
    doc_name, text = "", ""
    if source == "Use a sample":
        doc_name = st.selectbox("Sample (synthetic, for trying the tool)", list(SAMPLES))
        text = SAMPLES[doc_name]["text"]
    elif source == "Upload a file":
        up = st.file_uploader("PDF, DOCX or TXT", type=["pdf", "docx", "txt"])
        if up:
            try:
                doc_name, text = up.name, extract_text(up.name, up.getvalue())
            except ValueError as e:
                st.error(str(e))
    else:
        text = st.text_area("Paste the contract", height=200)
        doc_name = "Pasted contract"
with c2:
    default_role = SAMPLES[doc_name]["role"] if source == "Use a sample" else "tenant"
    role = st.selectbox("I am…", list(ROLES), index=list(ROLES).index(default_role), format_func=lambda r: ROLES[r])
    hide = st.text_input("Names or addresses to hide before analysis (comma-separated)",
                         help="Emails, phone numbers, IBANs and ID numbers are hidden automatically.")
    if providers:
        st.info(providers[0].privacy_note, icon="🔒")

is_sample = source == "Use a sample"
consent = True
if providers and not is_sample:
    consent = st.checkbox(
        f"I understand this is not legal advice, and that the contract text (with personal data hidden) "
        f"is sent to an AI provider ({providers[0].name}) for analysis.")

limit_msg = ""
if providers and ss.reviews_run >= SESSION_LIMIT:
    limit_msg = f"You've reached the limit of {SESSION_LIMIT} reviews per visit. Reload the page later to continue."
elif providers and reviews_today(con) >= DAILY_LIMIT:
    limit_msg = "The free daily AI capacity is used up. Please come back tomorrow, or try a sample in the meantime."
if limit_msg:
    st.warning(limit_msg)

if st.button("Review contract", type="primary", disabled=not text.strip() or not consent or bool(limit_msg)):
    ss.reviews_run += 1
    with st.spinner("Reading the contract…"):
        try:
            review = analyze(text, role=role, extra_terms=[t for t in hide.split(",") if t.strip()])
        except (ProviderError, ValueError) as e:
            st.error(f"Review failed: {e}")
            st.stop()
    ss.review, ss.decisions, ss.doc_name, ss.role = review, {}, doc_name, role
    # File names can contain people's names, so the audit log only keeps the kind of document.
    log_name = f"Sample: {doc_name}" if is_sample else ("Uploaded " + Path(doc_name).suffix if source == "Upload a file" else "Pasted text")
    ss.review_id = save_review(con, review, log_name, role)

review = ss.review
if not review:
    st.stop()

# ---------- Step 2: results ----------
restore = review.redaction.restore
st.divider()
m = st.columns(4)
m[0].metric("Clauses read", len(review.clauses))
m[1].metric("🔴 Ask a lawyer", len(review.by_route("lawyer")))
m[2].metric("🟡 Your decision", len(review.by_route("review")))
m[3].metric("🟢 Good to know", len(review.by_route("info")))
st.markdown(f"**Overview:** {restore(review.summary)}")
st.caption(f"Analyzed by {review.provider} ({review.model}). Personal data hidden before analysis: "
           f"{review.redaction.counts or 'none found'}.")
for w in review.warnings:
    st.warning(w)

clause_text = {c.id: restore(c.text) for c in review.clauses}


def decide(fid: str, decision: str, note: str) -> None:
    ss.decisions[fid] = {"decision": decision, "note": note}
    record_decision(con, ss.review_id, fid, decision, note)


tabs = st.tabs([f"{ROUTE_BADGE[r]} ({len(review.by_route(r))})" for r in ("lawyer", "review", "info")] + ["Full contract"])
for tab, r in zip(tabs, ("lawyer", "review", "info")):
    with tab:
        items = review.by_route(r)
        if not items:
            st.write("Nothing here.")
        for f in items:
            with st.container(border=True):
                head = f"**{f['clause_id']} · {CATEGORIES[f['category']]}** · {RISK_BADGE[f['risk']]}"
                if f["confidence"] is not None:
                    head += f" · AI confidence {f['confidence']:.0%}"
                st.markdown(head)
                st.markdown(f"> {restore(f['quote'])}")
                if not f["verified"]:
                    st.warning("This quote was not found word-for-word in the contract. Read the clause below.")
                if f["explanation"]:
                    st.write(restore(f["explanation"]))
                if f["suggestion"]:
                    st.markdown(f"**You could ask:** {restore(f['suggestion'])}")
                st.caption(f"Why it's here: {f['route_reason']} · Source: {f['source']}")
                with st.expander("Show full clause"):
                    st.text(clause_text[f["clause_id"]])

                done = ss.decisions.get(f["id"])
                if r == "info":
                    continue
                if done:
                    label = {"concern": "✅ Marked as a concern", "dismissed": "Dismissed", "lawyer_question": "📝 Question added for lawyer"}
                    st.success(label[done["decision"]] + (f": {done['note']}" if done["note"] else ""))
                    continue
                note = st.text_input("Your note or question (optional)", key=f"note_{f['id']}")
                b = st.columns(3)
                if r == "lawyer":
                    b[0].button("Add to lawyer questions", key=f"lq_{f['id']}", on_click=decide, args=(f["id"], "lawyer_question", note))
                    b[1].button("I understand, not a concern", key=f"d_{f['id']}", on_click=decide, args=(f["id"], "dismissed", note))
                else:
                    b[0].button("This is a concern", key=f"c_{f['id']}", on_click=decide, args=(f["id"], "concern", note))
                    b[1].button("Not a concern", key=f"d_{f['id']}", on_click=decide, args=(f["id"], "dismissed", note))
with tabs[3]:
    flagged = {f["clause_id"] for f in review.flags}
    for c in review.clauses:
        st.markdown(("🚩 " if c.id in flagged else "") + f"**{c.id}**")
        st.text(clause_text[c.id])

# ---------- Step 3: handoff ----------
st.divider()
st.subheader("Lawyer handoff")
pending = [f for f in review.flags if f["route"] != "info" and f["id"] not in ss.decisions]
st.caption(f"{len(pending)} flags still waiting for your decision." if pending else "All flags decided.")
md = lawyer_summary(review, ss.decisions, ss.doc_name, ss.role)
st.download_button("Download questions for a lawyer (.md)", md, file_name="lawyer-questions.md")
with st.expander("Preview"):
    st.markdown(md)
