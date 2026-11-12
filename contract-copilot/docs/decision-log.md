# Decision log

Short records of product decisions: context, decision, trade-off. Add one whenever you change direction.

---

### D1 · The AI never resolves high-stakes clauses (2026-11-12)
**Context:** A missed indemnity or personal guarantee can cost a user far more than the contract is worth.
**Decision:** High-risk flags in six high-stakes categories always route to the lawyer handoff, regardless of model confidence.
**Trade-off:** More items for the user to act on. Accepted: the cost of a false alarm here is a question to a lawyer; the cost of a miss is real money.

### D2 · Mistakes are asymmetric, so the system leans toward flagging (2026-11-12)
**Context:** A missed risky clause is worse than an extra flag.
**Decision:** Keyword rules run alongside the model. When a rule fires and the model is silent, the clause goes to human review.
**Trade-off:** Rules create some noise. We track dismissal rate per category and prune rules that users consistently dismiss.

### D3 · Verify every quote (2026-11-12)
**Context:** Models sometimes "quote" text that isn't in the document.
**Decision:** Each quote is matched against its clause locally. Unverified flags are labelled and sent to human review instead of the lawyer list.
**Trade-off:** A few correct-but-paraphrased flags get demoted. Worth it for trust.

### D4 · Free hosted models first, self-hosting later (2026-11-12)
**Context:** Zero budget; need real users quickly.
**Decision:** v1 uses free tiers with fallback (Cloudflare Workers AI → Gemini → Groq → Ollama). Cloudflare first because it does not train on inputs; Gemini's free tier may.
**Trade-off:** Daily limits and some privacy exposure. Mitigated by masking and by showing the provider's policy before analysis. v2 adds a self-hosted path.

### D5 · Mask personal data locally; let users name what to hide (2026-11-12)
**Context:** Detecting names with regex is unreliable; ML name detection adds weight.
**Decision:** Automatically mask emails, phones, IBANs, card and ID numbers. Ask the user for names/addresses. Keep money, dates and durations visible because the analysis needs them.
**Trade-off:** Relies on users filling the field. Measure how often they do.

### D6 · Lawyer handoff is generated without AI (2026-11-12)
**Context:** The handoff is what a professional will read; it must not contain invented content.
**Decision:** Build it deterministically from verified quotes, explanations and the user's own notes.
**Trade-off:** Less polished prose. Accuracy matters more here.

### D7 · Don't store contracts (2026-11-12)
**Decision:** The audit log keeps flags, routes and decisions only.
**Trade-off:** Can't re-run old reviews. Users can re-upload.

---

### Known limitation: the rules were written while looking at the eval set
The keyword rules were tuned on the three synthetic contracts in `evals/dataset`, so demo-mode scores are optimistic. Next step: add a held-out set of real (anonymised) contracts that nobody tunes against, and report scores on it separately.

---

### D8 · Public web deployment on Northflank (2026-11-12)
**Context:** Users shouldn't have to install anything. A public site also means strangers can use the AI key and see shared data.
**Decision:** Deploy the same app as a Docker container on Northflank. Add guardrails for a public site: a consent checkbox before any real contract is sent to an AI provider; per-visit and daily review limits to stay inside free-tier quotas; the audit log behind an admin password; the log keeps only the kind of document ("Uploaded .pdf"), never the file name.
**Trade-off:** Limits can block a genuine user on a busy day, and the audit log resets on redeploy. Both are acceptable for a test with 10–20 users.
