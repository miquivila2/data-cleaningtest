"""Load the dirty CSVs into BigQuery bronze via Cloud Storage. Every column is loaded as STRING on purpose:
letting BigQuery infer types would reject or silently fix the errors the agent has to find."""

import csv
import os
from pathlib import Path

import pandas as pd
import yaml
from dotenv import load_dotenv
from google.cloud import bigquery, storage

TABLES = ["clientes", "consumo_mensual"]


def string_schema(csv_path: Path) -> list[bigquery.SchemaField]:
    """_fila (row position in the dirty CSV) lets us match findings with the ground truth; the rest is STRING."""
    with csv_path.open(newline="") as f:
        header = next(csv.reader(f))
    return [bigquery.SchemaField("_fila", "INT64")] + [bigquery.SchemaField(n, "STRING") for n in header]


def with_row_number(csv_path: Path) -> str:
    df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    df.insert(0, "_fila", range(len(df)))
    return df.to_csv(index=False)


def load_bronze(dirty_dir: Path, project: str, location: str, bucket_name: str) -> None:
    gcs = storage.Client(project=project)
    bq = bigquery.Client(project=project, location=location)
    bucket = gcs.bucket(bucket_name)

    for table in TABLES:
        path = dirty_dir / f"{table}.csv"
        blob = bucket.blob(f"dirty/{path.name}")
        blob.upload_from_string(with_row_number(path), content_type="text/csv")
        uri = f"gs://{bucket_name}/{blob.name}"

        job_config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.CSV,
            skip_leading_rows=1,
            schema=string_schema(path),
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        )
        target = f"{project}.bronze.{table}"
        bq.load_table_from_uri(uri, target, job_config=job_config).result()
        rows = bq.get_table(target).num_rows
        print(f"{uri} -> {target}: {rows} filas")


def main() -> None:
    load_dotenv(".env")
    cfg = yaml.safe_load(Path("config.yaml").read_text())
    project = os.environ["GCP_PROJECT"]
    location = os.environ["GCP_LOCATION"]
    load_bronze(Path(cfg["paths"]["dirty"]), project, location, f"{project}-raw")


if __name__ == "__main__":
    main()
