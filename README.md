# Data Cleaning Agent — Dalefon

Research prototype of an LLM-driven data cleaning agent for telecom customer and usage data,
built locally on a public Kaggle proxy dataset and then deployed on Google Cloud (BigQuery + Vertex AI).

- `docs/01_idea.md` — research idea, design and evaluation
- `docs/02_tasks.md` — task pipeline (interactive tracker: `docs/pipeline.html`)

## Layout
```
data/{raw,dirty,clean}   datasets (git-ignored)
src/agent                profile → detect → plan → review → execute → verify → report
src/injection            controlled error injection + ground truth
notebooks/               exploration
reports/                 generated audit reports
tests/
```

## Setup
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
kaggle auth login        # or save a token to ~/.kaggle/access_token
```
