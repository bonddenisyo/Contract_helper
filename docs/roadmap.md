# Roadmap

## v1 — Ship and learn (now)
- [x] Review pipeline: masking → clauses → rules → AI → quote check → routing
- [x] Free providers with fallback; demo mode without keys
- [x] Review UI with decisions and lawyer handoff
- [x] Audit log and human-agreement stats
- [x] Eval runner with safety metric
- [ ] Get free API keys and run evals on real models; record results in `evals/results`
- [x] Docker + Northflank deployment setup (see `deploy-northflank.md`)
- [ ] Deploy on Northflank and share the link
- [ ] 5–10 user interviews before launch, 10–20 test users after
- [ ] Add 10+ real anonymised contracts as a held-out eval set

## v2 — Private and cheaper
- [ ] Oracle Cloud Always Free ARM server running Ollama; set `OLLAMA_BASE_URL` and put `ollama` first in `PROVIDER_ORDER` for a "private mode"
- [ ] Train a small clause classifier (Colab/Kaggle free GPU) on public labelled contract data; replace keyword rules as the first-pass layer
- [ ] Send only uncertain or high-risk clauses to the large model
- [ ] Compare cost, speed and quality of v1 vs v2 in the eval report

## v3 — Broader
- [ ] More languages (start with the users' own)
- [ ] Jurisdiction notes
- [ ] "What changed" comparison between two versions of a contract

## Interview metrics to collect along the way
Human agreement rate per category · high-stakes misses · time to decision · % users who request a change or use the handoff · provider fallback rate
