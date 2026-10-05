"""Agent loop: profile -> detect -> plan -> execute -> verify, running SQL on BigQuery.

Block 1 (this file so far): profile every column and detect issues with generic, type-agnostic rules.
No model is used yet: nothing here knows what a phone or an IMEI is; it only looks at shapes and counts.
"""

import json
import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import yaml
from dotenv import load_dotenv
from google.cloud import bigquery

SENTINELS = ["n/a", "na", "null", "none", "nan", "-", "?"]
ROW_ID = "_fila"

# thresholds of the generic rules
DOMINANT_PATTERN = 0.50   # a column has a "normal" shape if one pattern covers at least this share
RARE_PATTERN = 0.05       # ...and patterns below this share are flagged as format anomalies
NUMERIC_COLUMN = 0.95     # share of values castable to number for a column to be treated as numeric
OUTLIER_FACTOR = 10       # numeric value above this many times the column p99 is flagged
CANDIDATE_KEY = 0.95      # distinct/non-null ratio for a column to be treated as an identifier

# Shape of a value: each digit -> 9, each run of uppercase -> A, each run of lowercase -> a.
# "+52 55 0219 9906" -> "+99 99 9999 9999", "Silvia Carrasco" -> "Aa Aa", "SILVIA" -> "A"
PATTERN_SQL = r"""REGEXP_REPLACE(REGEXP_REPLACE(REGEXP_REPLACE({c}, r'\d', '9'), r'\p{{Lu}}+', 'A'), r'\p{{Ll}}+', 'a')"""


class BigQueryEngine:
    def __init__(self, project: str, location: str, dataset: str):
        self.client = bigquery.Client(project=project, location=location)
        self.project, self.dataset = project, dataset

    def ref(self, table: str) -> str:
        return f"`{self.project}.{self.dataset}.{table}`"

    def query(self, sql: str, params: list | None = None) -> pd.DataFrame:
        config = bigquery.QueryJobConfig(query_parameters=params or [])
        return self.client.query(sql, job_config=config).to_dataframe()

    def tables(self) -> list[str]:
        return sorted(t.table_id for t in self.client.list_tables(f"{self.project}.{self.dataset}"))

    def columns(self, table: str) -> list[str]:
        schema = self.client.get_table(f"{self.project}.{self.dataset}.{table}").schema
        return [f.name for f in schema if f.name != ROW_ID]


# --- 1. profile --------------------------------------------------------------------------

def profile_column(eng: BigQueryEngine, table: str, col: str) -> dict:
    t = eng.ref(table)
    stats = eng.query(
        f"""
        SELECT COUNT(*) AS filas,
               COUNTIF({col} IS NULL) AS nulos,
               COUNT(DISTINCT {col}) AS distintos,
               COUNTIF(SAFE_CAST({col} AS FLOAT64) IS NOT NULL) AS numericos,
               COUNTIF(SAFE_CAST({col} AS FLOAT64) < 0) AS negativos,
               MIN(LENGTH({col})) AS long_min, MAX(LENGTH({col})) AS long_max,
               COUNTIF({col} != TRIM({col}) OR {col} LIKE '%  %') AS espacios,
               COUNTIF(LOWER(TRIM({col})) IN UNNEST(@sentinels)) AS nulos_disfrazados,
               APPROX_QUANTILES(SAFE_CAST({col} AS FLOAT64), 100)[OFFSET(99)] AS p99
        FROM {t}""",
        [bigquery.ArrayQueryParameter("sentinels", "STRING", SENTINELS)],
    ).iloc[0].to_dict()
    patterns = eng.query(
        f"""
        SELECT {PATTERN_SQL.format(c=col)} AS patron, COUNT(*) AS n, ANY_VALUE({col}) AS ejemplo
        FROM {t} WHERE {col} IS NOT NULL
        GROUP BY patron ORDER BY n DESC LIMIT 15"""
    )
    non_null = max(stats["filas"] - stats["nulos"], 1)
    patterns["cuota"] = (patterns["n"] / non_null).round(4)
    stats = {k: (None if pd.isna(v) else (float(v) if k == "p99" else int(v))) for k, v in stats.items()}
    stats["es_numerica"] = stats["numericos"] / non_null >= NUMERIC_COLUMN
    stats["es_identificador"] = stats["distintos"] / non_null >= CANDIDATE_KEY
    stats["patrones"] = patterns.to_dict("records")
    return stats


def profile(eng: BigQueryEngine) -> dict:
    return {t: {c: profile_column(eng, t, c) for c in eng.columns(t)} for t in eng.tables()}


# --- 2. detect (generic rules, no model) -------------------------------------------------

def detect(eng: BigQueryEngine, prof: dict) -> pd.DataFrame:
    """Each rule returns rows (tabla, _fila, columna, regla, valor). One cell can be flagged by several rules."""
    found = []

    def add(table: str, sql: str, rule: str, col: str = "*") -> None:
        df = eng.query(sql)
        df.insert(0, "tabla", table)
        df["columna"], df["regla"] = col, rule
        found.append(df[["tabla", ROW_ID, "columna", "regla", "valor"]])

    for table, cols in prof.items():
        t = eng.ref(table)
        for col, p in cols.items():
            # R1 rare format: the column has a dominant shape and this value does not follow it
            pats = p["patrones"]
            if not p["es_numerica"] and pats and pats[0]["cuota"] >= DOMINANT_PATTERN:
                rare = [x["patron"] for x in pats if x["cuota"] < RARE_PATTERN]
                if rare:
                    add(table, f"""SELECT {ROW_ID}, {col} AS valor FROM {t}
                        WHERE {PATTERN_SQL.format(c=col)} IN UNNEST({json.dumps(rare)})""",
                        "R1 formato poco frecuente", col)
            # R2 disguised nulls
            add(table, f"""SELECT {ROW_ID}, {col} AS valor FROM {t}
                WHERE LOWER(TRIM({col})) IN UNNEST({json.dumps(SENTINELS)})""", "R2 nulo disfrazado", col)
            # R3 stray whitespace
            add(table, f"""SELECT {ROW_ID}, {col} AS valor FROM {t}
                WHERE {col} != TRIM({col}) OR {col} LIKE '%  %'""", "R3 espacios sobrantes", col)
            if p["es_numerica"]:
                # R4 text in a numeric column, R5 negative, R6 extreme value
                add(table, f"""SELECT {ROW_ID}, {col} AS valor FROM {t}
                    WHERE {col} IS NOT NULL AND SAFE_CAST({col} AS FLOAT64) IS NULL
                    AND LOWER(TRIM({col})) NOT IN UNNEST({json.dumps(SENTINELS)})""",
                    "R4 texto en columna numerica", col)
                add(table, f"""SELECT {ROW_ID}, {col} AS valor FROM {t}
                    WHERE SAFE_CAST({col} AS FLOAT64) < 0""", "R5 negativo", col)
                if p["p99"] and p["p99"] > 0:
                    add(table, f"""SELECT {ROW_ID}, {col} AS valor FROM {t}
                        WHERE SAFE_CAST({col} AS FLOAT64) > {p['p99'] * OUTLIER_FACTOR}""",
                        "R6 valor extremo", col)
            # R7 repeated identifier (keeps the first occurrence unflagged)
            if p["es_identificador"] and not p["es_numerica"]:
                add(table, f"""SELECT {ROW_ID}, {col} AS valor FROM (
                    SELECT {ROW_ID}, {col}, ROW_NUMBER() OVER (PARTITION BY {col} ORDER BY {ROW_ID}) AS k
                    FROM {t} WHERE {col} IS NOT NULL) WHERE k > 1""", "R7 identificador repetido", col)

        # R8 exact duplicate rows (all columns equal), first occurrence unflagged
        data_cols = ", ".join(cols)
        add(table, f"""SELECT {ROW_ID}, CAST(NULL AS STRING) AS valor FROM (
            SELECT {ROW_ID}, ROW_NUMBER() OVER (PARTITION BY TO_JSON_STRING(STRUCT({data_cols})) ORDER BY {ROW_ID}) AS k
            FROM {t}) WHERE k > 1""", "R8 fila duplicada")

    # R9 orphan reference: a column that is an identifier in one table and also appears in another
    for key_table, cols in prof.items():
        for col, p in cols.items():
            if not p["es_identificador"]:
                continue
            for other, other_cols in prof.items():
                if other != key_table and col in other_cols:
                    add(other, f"""SELECT o.{ROW_ID}, o.{col} AS valor FROM {eng.ref(other)} o
                        LEFT JOIN {eng.ref(key_table)} k ON o.{col} = k.{col}
                        WHERE o.{col} IS NOT NULL AND k.{col} IS NULL""",
                        f"R9 sin referencia en {key_table}", col)

    return pd.concat(found, ignore_index=True)


def summarize(prof: dict, issues: pd.DataFrame) -> dict:
    rows = {t: next(iter(c.values()))["filas"] for t, c in prof.items()}
    by_rule = issues.groupby(["tabla", "regla"]).size()
    return {
        "filas": rows,
        "incidencias": int(len(issues)),
        "celdas_marcadas": int(issues[["tabla", ROW_ID, "columna"]].drop_duplicates().shape[0]),
        "por_regla": {f"{t} | {r}": int(n) for (t, r), n in by_rule.items()},
    }


def main() -> None:
    load_dotenv(".env")
    cfg = yaml.safe_load(Path("config.yaml").read_text())
    eng = BigQueryEngine(os.environ["GCP_PROJECT"], os.environ["GCP_LOCATION"], "bronze")

    run_dir = Path(cfg["paths"]["runs"]) / datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)

    prof = profile(eng)
    (run_dir / "profile.json").write_text(json.dumps(prof, ensure_ascii=False, indent=2, default=str))
    issues = detect(eng, prof)
    issues.to_csv(run_dir / "issues.csv", index=False)
    summary = summarize(prof, issues)
    (run_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))

    print(f"run: {run_dir}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
