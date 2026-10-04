"""Kaggle download, stratified sample, readable tables (clientes + consumo_mensual), Dalefon-like columns."""

import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from faker import Faker

RAW_CSV = "telecom_churn_data.csv"
MONTHS = {6: "2014-06", 7: "2014-07", 8: "2014-08", 9: "2014-09"}
SNAPSHOT_DATE = pd.Timestamp("2014-09-30")  # last day covered by the dataset

MX_AREA_CODES = ["55", "56", "33", "81"]  # CDMX, CDMX, Guadalajara, Monterrey (2-digit -> 10-digit numbers)
EMAIL_DOMAINS = ["gmail.com", "hotmail.com", "outlook.com", "yahoo.com.mx", "icloud.com"]
ESIM_DEVICES = [
    "iPhone 12", "iPhone 13", "iPhone 14", "iPhone 15", "iPhone 16",
    "Samsung Galaxy S23", "Samsung Galaxy S24", "Samsung Galaxy A54", "Samsung Galaxy A55",
    "Motorola Edge 40", "Motorola Edge 50", "Google Pixel 7", "Google Pixel 8", "Xiaomi 14",
]

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


def to_mx_phone(numbers: pd.Series, rng: np.random.Generator) -> pd.Series:
    """Map raw 10-digit numbers (70000xxxxx) to Mexican 10-digit numbers: area code + last 8 digits.

    The last 8 raw digits are unique, so the mapping stays unique and both tables keep joining.
    """
    area = rng.choice(MX_AREA_CODES, size=len(numbers))
    return pd.Series(area, index=numbers.index) + numbers.astype(str).str[-8:]


def luhn_check_digit(body: str) -> str:
    total = 0
    for i, d in enumerate(reversed(body)):
        n = int(d)
        if i % 2 == 0:  # double every second digit from the right (check digit not yet appended)
            n = n * 2 - 9 if n > 4 else n * 2
        total += n
    return str((10 - total % 10) % 10)


def make_imei(rng: np.random.Generator) -> str:
    body = "35" + "".join(rng.choice(list("0123456789"), size=12))
    return body + luhn_check_digit(body)


def slug(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return "".join(c for c in ascii_text.lower() if c.isalnum() or c == " ").strip().replace(" ", ".")


def add_dalefon_columns(
    clientes: pd.DataFrame, consumo: pd.DataFrame, seed: int
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Add clean synthetic customer columns like the ones Dalefon collects (name, email, device, IMEI, signup)."""
    rng = np.random.default_rng(seed)
    fake = Faker("es_MX")
    Faker.seed(seed)

    phone_map = dict(zip(clientes["telefono"], to_mx_phone(clientes["telefono"], rng)))
    out = clientes.copy()
    out["telefono"] = out["telefono"].map(phone_map)

    names, emails, seen = [], [], set()
    for _ in range(len(out)):
        first, last = fake.first_name(), fake.last_name()
        names.append(f"{first} {last}")
        local = f"{slug(first)}.{slug(last)}"
        email = f"{local}@{rng.choice(EMAIL_DOMAINS)}"
        while email in seen:
            email = f"{local}{rng.integers(1, 999)}@{email.split('@')[1]}"
        seen.add(email)
        emails.append(email)
    out["nombre"] = names
    out["email"] = emails
    out["modelo_dispositivo"] = rng.choice(ESIM_DEVICES, size=len(out))
    out["imei"] = [make_imei(rng) for _ in range(len(out))]
    out["fecha_alta"] = (SNAPSHOT_DATE - pd.to_timedelta(out["antiguedad_dias"], unit="D")).dt.date

    out = out[["telefono", "nombre", "email", "modelo_dispositivo", "imei", "fecha_alta", "antiguedad_dias"]]
    consumo = consumo.assign(telefono=consumo["telefono"].map(phone_map))
    return out, consumo


def main() -> None:
    cfg = load_config()
    paths = cfg["paths"]
    raw = load_raw(paths["raw"])
    sample = stratified_sample(raw, cfg["sample"]["rows"], cfg["seed"])
    clientes, consumo = to_readable(sample)
    clientes, consumo = add_dalefon_columns(clientes, consumo, cfg["seed"])

    out = Path(paths["readable"])
    out.mkdir(parents=True, exist_ok=True)
    clientes.to_csv(out / "clientes.csv", index=False)
    consumo.to_csv(out / "consumo_mensual.csv", index=False)
    print(f"clientes: {clientes.shape} | consumo_mensual: {consumo.shape} -> {out}/")


if __name__ == "__main__":
    main()
