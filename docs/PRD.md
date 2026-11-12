# PRD: Contract Copilot (v1)

**Status:** v1 built, entering user testing · **Owner:** you · **Last updated:** 2026-11-12

## Problem

People sign leases and service contracts they don't fully understand. A lawyer review costs more than most tenants and freelancers will pay for a "normal" contract, so they sign blind. The risky clauses (auto-renewal traps, uncapped liability, broad IP grabs, one-sided indemnities) are often recognisable, but only if you know what to look for.

## Users

| Persona | Situation | What "good" looks like for them |
|---|---|---|
| Tenant | Signing a 12-month residential lease | Knows which clauses to push back on before signing |
| Freelancer | Client sends a services agreement | Spots IP, payment and non-compete traps; asks for changes confidently |
| Small business owner | Signing a vendor/SaaS contract | Catches auto-renewals and personal guarantees |

## Goals and non-goals

**Goals**
1. The user understands every meaningful risk in the contract in under 10 minutes.
2. High-stakes clauses are never resolved by the AI alone: they reach a human, and the riskiest reach a lawyer handoff.
3. The user leaves with something actionable: changes to request, or a ready-made question list for a lawyer.

**Non-goals (v1)**
- Giving legal advice or saying a contract is "safe."
- Rewriting the contract.
- Jurisdiction-specific legal checks.
- Scanned/handwritten documents.

## How the work is split between AI and people

This is the core design decision. It lives in code in `copilot/policy.py` and `copilot/taxonomy.py`.

| Who | Does what |
|---|---|
| Local code (no AI) | Hides personal data, splits clauses, runs keyword safety rules, verifies the AI's quotes, builds the lawyer handoff |
| AI model | Finds risky clauses, categorises, rates risk and confidence, explains in plain language, suggests a change |
| The user | Decides on every 🟡 flag (concern / not a concern); adds questions |
| A lawyer (outside the product) | Receives the 🔴 items as a ready-to-send summary |

**Routing rules**
- 🔴 **Ask a lawyer:** high risk in a high-stakes category (liability, indemnity, personal guarantee, non-compete, IP assignment, dispute resolution), or high risk with AI confidence < 60%.
- 🟡 **Your decision:** medium/high risk otherwise; AI unsure; AI quote not found in the contract; a safety rule fired but the AI stayed silent.
- 🟢 **Good to know:** low risk.

## Trust features

- Every flag quotes the contract, and the quote is checked against the clause. Unverified quotes are labelled and demoted.
- Every flag says *why* it was routed where it was.
- Personal data is masked before leaving the machine; the user can add names to hide.
- The provider and its data policy are shown before analysis.
- The audit log stores flags and decisions, never the contract text.
- No "safe" verdict, ever.

## Success metrics

| Type | Metric | v1 target |
|---|---|---|
| Safety (guardrail) | Missed high-stakes clauses in evals | 0 |
| Quality | Clause recall / precision (evals) | ≥ 90% / ≥ 75% |
| Quality | Human agreement rate (flags marked "concern" vs "dismissed") | ≥ 70% |
| Value | Users who request at least one change or use the lawyer handoff | ≥ 50% |
| Effort | Median time from upload to all flags decided | < 10 min |
| Cost | AI cost per review | $0 (free tiers) |

## Risks

| Risk | Mitigation |
|---|---|
| AI misses a dangerous clause | Rules safety net; high-stakes recall tracked as a release blocker |
| AI invents text | Quote verification; unverified flags demoted to human review |
| Over-trust ("the tool said it's fine") | No safe verdicts; disclaimers in UI and handoff |
| Free tier trains on user data | Provider privacy note shown; Cloudflare first in order; v2 self-hosting |
| Free tier limits / outages | Automatic fallback across providers |
| Too many flags (alert fatigue) | Track human workload and dismissal rate per category |

## Release plan

1. **v1 (now):** hosted free models + rules + human routing. Test with 10–20 real users.
2. **v2:** self-hosted model on Oracle Always Free for private mode; trained clause classifier as the first-pass layer; big model only for hard clauses.
3. **v3:** more languages and jurisdictions; contract comparison ("what changed in the renewal").

See `decision-log.md` for why things are the way they are.
