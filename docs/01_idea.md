# Dalefon — Data Cleaning Agent: Research Idea (Phase 1)

*Draft v0.1 · 2026-10-03 · Source: meeting notes "09-28 Reunión: Auditoría de Datos e IA para Dalefon"*

## 1. Problem (from the meeting)

| What Dalefon said | What it means for the agent |
|---|---|
| Internal data is clean, but large provider feeds (Altan, MMO — e.g. hourly data consumption per user) are **neither stored nor used** | The dirtiest, highest-value data is the external usage feed. The agent must handle high-volume, semi-structured, time-series data. |
| Data lives in several databases; messy data confuses AI and is a security risk | Unification + PII (personally identifiable information: name, email, phone, ID) handling are in scope. |
| Customer data (name, email, phone, device model, IMEI, KYC) is collected but not exploited | Clean customer entity = prerequisite for commercial use (device upsell) and for "Fony". |
| Idea: credit scoring from consumption data | The cleaned output must be **model-ready** (consistent units, no duplicate customers, no leakage). |
| Decision: audit first → report with **statistics, overview, errors found, recommendations** | The agent's first output is exactly that audit report. Cleaning comes after approval. |
| Stack: Google Cloud, read-only access to be granted | Agent runs on GCP, reads with viewer permissions, writes only to its own datasets. |

**Research question:** *Can an LLM-driven agent audit and clean telecom customer + usage data in BigQuery with accuracy comparable to a human data engineer, while staying auditable, cheap and safe for PII?*

## 2. Approach: simulate Dalefon with a public Kaggle dataset

We do not have Dalefon's data yet (access is pending). We build and validate the agent on a public proxy, so that when access arrives we only swap the source.

**Proposed dataset — "Telecom Churn Case Study" (prepaid, ~100k customers × 226 columns)**
- Prepaid mobile operator, monthly usage in MB (2G/3G), calls, recharges, recharge dates over 4 months. Closest public analogue to an MVNO (mobile operator that rents another's network — exactly Dalefon on Altan) prepaid base.
- Natively messy: many columns with high null rates, dates stored as strings, constant columns, outliers. *(To verify on download — this is from secondary sources, not yet checked.)*
- Supports the credit-scoring/churn use case later.

**Plus controlled error injection.** Real dirt has no answer key, so we can't measure accuracy on it. We additionally corrupt a copy with known errors that mimic Dalefon's reality, and keep the ground truth:

| Injected error | Dalefon analogue |
|---|---|
| Duplicate customers with slight variations | Same customer across several DBs |
| Mixed date/timestamp formats & time zones | Provider feeds (Altan vs internal) |
| Unit mismatch (MB vs GB vs bytes) | Hourly consumption feeds |
| Mexican phone formats (`+52`, `044`, 10-digit, spaces) | Customer contact data |
| Invalid IMEIs (bad Luhn check digit) | Device compatibility step |
| Malformed emails, inconsistent casing/accents | KYC / CRM |
| Negative or impossible usage values, orphan records | Feed glitches, unmatched lines |

Alternatives considered: *IBM Telco Churn* (7k × 21) — too small and too clean; *Telecom Italia Milan* — usage per grid cell, no customers.

## 3. Agent design (principle: the LLM writes rules, not rows)

The LLM never edits 100k rows one by one (slow, expensive, non-reproducible). It **reasons over profiles and samples, and emits SQL/rules** that BigQuery executes deterministically. Every change is a reviewable artifact.

```
 Kaggle CSV ─► Cloud Storage (raw) ─► BigQuery  bronze (raw, untouched)
                                         │
              ┌──────────────────────────┴──────────────────────────┐
              │                     CLEANING AGENT                  │
              │ 1. PROFILE   stats per column (nulls, types, ranges)│  ← deterministic (SQL)
              │ 2. DETECT    rule checks + LLM semantic checks      │  ← LLM: "this column is a phone"
              │ 3. PLAN      proposed fixes as structured actions   │  ← LLM: JSON plan + SQL
              │ 4. REVIEW    human approves / rejects each action   │  ← human-in-the-loop
              │ 5. EXECUTE   run approved SQL → silver              │  ← deterministic
              │ 6. VERIFY    re-profile, tests, before/after diff   │
              │ 7. REPORT    audit report (stats, errors, recs)     │
              └──────────────────────────┬──────────────────────────┘
                                         ▼
                        BigQuery silver (clean) ─► gold (model/dashboard-ready)
                                         ▼
                        Looker Studio: quality dashboard + transformed data
```
*(bronze/silver/gold = "medallion" layers: raw → cleaned → business-ready.)*

**Stack (proposal):** Python agent · Vertex AI **Gemini** as LLM (native to GCP, data stays in Dalefon's project) · BigQuery · Cloud Storage · Cloud Run job to run it in the cloud · Looker Studio to view results. PII is masked before any sample is sent to the LLM.

## 4. How we evaluate (what makes it research, not a demo)

| Metric | How |
|---|---|
| Detection precision / recall | Against the injected ground truth (precision = % flagged that were real errors; recall = % real errors found) |
| Repair accuracy | % of corrupted cells restored to the true value |
| Data quality score before → after | % rows passing all rules, null rate, duplicate rate |
| Cost & time per run | LLM tokens (€) + BigQuery bytes scanned |
| Baseline comparison | vs. (a) a hand-written pandas script, (b) Google's built-in BigQuery Data Preparation (Gemini) |

## 5. Phases

| # | Phase | Output |
|---|---|---|
| 1 | Idea (this doc) | Scope, dataset, design, metrics agreed |
| 2 | Local pipeline | Download Kaggle data, profile it, inject errors, build agent locally against DuckDB/pandas, measure |
| 3 | GCP setup | Project, bucket, BigQuery datasets, service account (read-only on bronze), Vertex AI enabled |
| 4 | Run on GCP | Agent runs against BigQuery, writes silver/gold |
| 5 | Results | Transformed data in BigQuery + Looker Studio, audit report = template for the real Dalefon audit |

## 6. Open decisions

1. Dataset: confirm the prepaid ~100k dataset (+ injected errors).
2. LLM: Gemini on Vertex AI (recommended) vs. Claude on Vertex AI.
3. GCP: your own project with billing to prototype, or wait for a Dalefon sandbox?
4. Language of deliverables for Dalefon (Spanish?).

## Prerequisites detected on this machine
- Python 3.14 ✔ · git ✔
- Missing: `gcloud` SDK, `kaggle` CLI + API token (`~/.kaggle/kaggle.json`), pandas
