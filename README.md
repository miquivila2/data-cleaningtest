# Data Cleaning Agent — Dalefon

Research prototype of an LLM-driven data cleaning agent for telecom customer and usage data,
built locally on a public Kaggle proxy dataset and then deployed on Google Cloud (BigQuery).

**Stack:** Python · DuckDB → BigQuery · sqlglot · pydantic · Ollama (Gemma 3, generator) · Jev (typed decisions)

## Layout
```
config/                  settings.yaml + declarative quality rules
data/                    raw → sample → dirty (+ ground_truth) → clean   (git-ignored)
src/dalefon_cleaner/
  ingest/                Kaggle download, stratified sample, load to engine
  synth/                 Dalefon-like columns (MX phone, IMEI, email)
  injection/             controlled error injection + ground truth
  engine/                SQL backend: duckdb | bigquery
  agent/                 profile → detect → plan → review → execute → verify
    models/              model clients behind one interface (ollama, jev)
    prompts/             versioned prompt templates
  pii/                   masking before any external call
  report/                audit report
  evaluation/            metrics vs ground truth, baselines
  cli.py                 cleaner ingest | inject | run | evaluate
infra/                   gcloud scripts + Dockerfile (Cloud Run Job)
notebooks/  reports/  tests/
```

## Setup
```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
cp .env.example .env
kaggle auth login
```
