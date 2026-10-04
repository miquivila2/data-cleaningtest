"""Kaggle download, stratified sample, readable tables (clientes + consumo_mensual)."""

from pathlib import Path

import pandas as pd
import yaml

RAW_CSV = "telecom_churn_data.csv"
MONTHS = {6: "2014-06", 7: "2014-07", 8: "2014-08", 9: "2014-09"}

# readable name -> raw column prefix (raw columns are "<prefix>_<month>")
MONTHLY_COLUMNS = {
    "ingreso_medio": "arpu",
    "recarga_total": "total_rech_amt",
    "num_recargas": "total_rech_num",
    "fecha_ultima_recarga": "date_of_last_rech",
    "datos_2g_mb": "vol_2g_mb",
    "datos_3g_mb": "vol_3g_mb",
    "minutos_salientes": "total_og_mou",
    "minutos_entrantes": "total_ic_mou",
    "minutos_roaming_salientes": "roam_og_mou",
    "minutos_roaming_entrantes": "roam_ic_mou",
}


def load_config(path: str = "config.yaml") -> dict:
    return yaml.safe_load(Path(path).read_text())


def load_raw(raw_dir: str) -> pd.DataFrame:
    return pd.read_csv(Path(raw_dir) / RAW_CSV)


def stratified_sample(df: pd.DataFrame, rows: int, seed: int) -> pd.DataFrame:
    """Sample customers keeping the distribution of total recharge (quartiles over 4 months)."""
    recharge = df[[f"total_rech_amt_{m}" for m in MONTHS]].sum(axis=1)
    band = pd.qcut(recharge.rank(method="first"), 4, labels=False)
    frac = rows / len(df)
    return (
        df.groupby(band, group_keys=False)
        .sample(frac=frac, random_state=seed)
        .reset_index(drop=True)
    )


def to_readable(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split the wide raw table into clientes (1 row/customer) and consumo_mensual (1 row/customer-month).

    Values are kept as-is (nulls, negatives, string dates): this is the dirt the agent must find.
    circle_id is dropped because it has a single value in the whole dataset.
    """
    clientes = df[["mobile_number", "aon"]].rename(
        columns={"mobile_number": "telefono", "aon": "antiguedad_dias"}
    )
    months = []
    for m, label in MONTHS.items():
        cols = {f"{raw}_{m}": name for name, raw in MONTHLY_COLUMNS.items()}
        part = df[["mobile_number", *cols]].rename(columns={"mobile_number": "telefono", **cols})
        part.insert(1, "mes", label)
        months.append(part)
    consumo = pd.concat(months, ignore_index=True).sort_values(["telefono", "mes"], ignore_index=True)
    return clientes, consumo


def main() -> None:
    cfg = load_config()
    paths = cfg["paths"]
    raw = load_raw(paths["raw"])
    sample = stratified_sample(raw, cfg["sample"]["rows"], cfg["seed"])
    clientes, consumo = to_readable(sample)

    out = Path(paths["readable"])
    out.mkdir(parents=True, exist_ok=True)
    clientes.to_csv(out / "clientes.csv", index=False)
    consumo.to_csv(out / "consumo_mensual.csv", index=False)
    print(f"clientes: {clientes.shape} | consumo_mensual: {consumo.shape} -> {out}/")


if __name__ == "__main__":
    main()
