# Data Cleaning Agent — Dalefon

Research prototype of an LLM-driven data cleaning agent for telecom customer and usage data,
built locally on a public Kaggle proxy dataset and then deployed on Google Cloud (BigQuery).

**Stack:** Python · DuckDB → BigQuery · sqlglot · pydantic · Ollama (Gemma 3, generator) · Jev (typed decisions)

## Layout
```
config.yaml          sample size, seed, models, budget
data/                raw → sample → dirty → clean  (git-ignored, created by the code)
src/cleaner/
  data/ingest.py         download, sample, synthetic columns, error injection
  agent/agent.py         profile → detect → plan → execute → verify
  models/models.py       Ollama + Jev clients
  report/report.py       audit report
  evaluate/evaluate.py   metrics vs ground truth
```

## Setup
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.lock && .venv/bin/pip install -e . --no-deps
cp .env.example .env
kaggle auth login
```
