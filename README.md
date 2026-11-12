# Contract Copilot

An AI copilot for people signing leases and service contracts. The AI flags risky clauses and explains them in plain language. **You** decide what matters. Anything too high-stakes for the AI goes into a ready-to-send question list for a lawyer.

Not legal advice. Built as a portfolio project to practise AI product work in a high-trust setting.

## How it works

```
contract ──► mask personal data ──► split into clauses ──┬─► keyword safety rules ─┐
             (local)                (local)              └─► AI model (free tier) ─┤
                                                                                   ▼
                                          verify quotes ◄── merge ──► route each flag
                                                                       🔴 ask a lawyer
                                                                       🟡 your decision
                                                                       🟢 good to know
```

Put it on the web: [`docs/deploy-northflank.md`](docs/deploy-northflank.md)

Product docs: [`docs/PRD.md`](docs/PRD.md) · [`docs/decision-log.md`](docs/decision-log.md) · [`docs/roadmap.md`](docs/roadmap.md)

## Run it

You need Python 3.10+.

```bash
pip install -r requirements.txt
streamlit run app.py
```

It opens in your browser. With no keys it runs in **demo mode** (keyword rules only), so you can click through right away with the three sample contracts.

## Add a free AI provider

Copy `.env.example` to `.env` and fill in at least one. You can add several: if one hits its free limit, the next is used.

| Provider | Get a key | Data note |
|---|---|---|
| Cloudflare Workers AI (recommended first) | Cloudflare dashboard → AI → Workers AI → use REST API. You need the **Account ID** and an **API token** with Workers AI permission | Not used for training |
| Google Gemini | aistudio.google.com → Get API key | Free tier may be used to improve Google's products (outside EEA/UK/CH) |
| Groq | console.groq.com → API Keys | Check Groq's current policy |
| Ollama (self-hosted, v2) | Install Ollama, `ollama pull qwen2.5:7b` | Never leaves your machine |

Model names are set in `.env`; free model lists change, so check each provider's current list if a model stops working.

**Only test with sample or made-up contracts until you've decided which provider's data policy you're comfortable with.**

## Evaluate

```bash
python -m evals.run_evals --demo   # offline, rules only
python -m evals.run_evals          # with your configured AI provider
```

Reports are saved in `evals/results/`. The key number is **missed high-stakes clauses**, which must be 0.

## Test

```bash
python -m pytest -q
```

## Project layout

```
app.py                  Streamlit UI
copilot/
  parsing.py            PDF/DOCX/TXT → text
  redact.py             personal data masking
  clauses.py            clause splitting
  rules.py              keyword safety net
  llm.py                free providers + fallback
  analyze.py            the pipeline
  policy.py             routing = the automation boundary
  taxonomy.py           categories, high-stakes list, user roles
  handoff.py            lawyer question list (no AI)
  store.py              SQLite audit log (no contract text)
evals/                  labeled synthetic contracts + scorer
docs/                   PRD, decision log, roadmap
```
