"""Controlled error injection on the readable tables + ground truth (one error per row, seed-reproducible)."""

import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

MONTHS_ES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
SENTINELS = ["N/A", "null", "-", ""]

# error code -> (share of original rows, description)
CLIENTES_ERRORS = {
    "C1": (0.03, "cliente duplicado con variaciones"),
    "C2": (0.08, "telefono en otro formato"),
    "C3": (0.03, "email mal formado"),
    "C4": (0.02, "imei invalido"),
    "C5": (0.10, "modelo escrito de otra forma"),
    "C6": (0.08, "fecha_alta en otro formato"),
    "C7": (0.05, "nombre con mayusculas o espacios mal"),
    "C8": (0.02, "nulo disfrazado"),
    "C9": (0.01, "fecha_alta y antiguedad_dias no cuadran"),
}
CONSUMO_ERRORS = {
    "U1": (0.03, "unidades mezcladas (GB en columna MB)"),
    "U2": (0.02, "fila repetida"),
    "U3": (0.01, "consumo negativo imposible"),
    "U4": (0.005, "valor atipico extremo (x100)"),
    "U5": (0.05, "mes en otro formato"),
    "U6": (0.03, "numero con coma decimal"),
    "U7": (0.01, "consumo sin cliente"),
    "U8": (0.01, "recarga fuera de su mes"),
}
DECIMAL_COLUMNS = [
    "ingreso_medio", "datos_2g_mb", "datos_3g_mb", "minutos_salientes", "minutos_entrantes",
]


class Injector:
    """Applies errors to one table and records each one. Rows are tracked by a hidden _rid."""

    def __init__(self, table: str, df: pd.DataFrame, rng: np.random.Generator):
        self.table = table
        self.df = df.copy()
        self.df["_rid"] = range(len(self.df))
        self.originals = len(self.df)
        self.rng = rng
        self.used: set[int] = set()
        self.log: list[dict] = []

    def pick(self, share: float, eligible: pd.Series | None = None) -> list[int]:
        mask = ~self.df["_rid"].isin(self.used) & (self.df["_rid"] < self.originals)
        if eligible is not None:
            mask &= eligible
        candidates = self.df.index[mask].to_numpy()
        n = min(round(share * self.originals), len(candidates))
        rows = sorted(self.rng.choice(candidates, size=n, replace=False).tolist())
        self.used.update(self.df.loc[rows, "_rid"])
        return rows

    def cell(self, code: str, rows: list[int], column: str, corrupt, recoverable: str) -> None:
        for i in rows:
            original = self.df.at[i, column]
            dirty = corrupt(original)
            self.df.at[i, column] = dirty
            self.record(code, self.df.at[i, "_rid"], column, original, dirty, recoverable)

    def duplicate(self, code: str, rows: list[int], vary=None) -> None:
        copies = []
        for i in rows:
            row = self.df.loc[i].copy()
            if vary:
                row = vary(row)
            row["_rid"] = self.originals + len(self.log)
            self.record(code, row["_rid"], "*", "", "", "sí", related=self.df.at[i, "_rid"])
            copies.append(row)
        self.df = pd.concat([self.df, pd.DataFrame(copies)], ignore_index=True)

    def record(self, code, rid, column, original, dirty, recoverable, related=None) -> None:
        errors = CLIENTES_ERRORS if self.table == "clientes" else CONSUMO_ERRORS
        self.log.append({
            "tabla": self.table, "_rid": rid, "columna": column, "tipo": code,
            "descripcion": errors[code][1], "valor_original": original, "valor_sucio": dirty,
            "recuperable": recoverable, "_rid_relacionada": related,
        })

    def finish(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Shuffle rows (so injected copies are not at the end) and translate _rid into file row numbers."""
        df = self.df.iloc[self.rng.permutation(len(self.df))].reset_index(drop=True)
        position = dict(zip(df["_rid"], df.index))
        truth = pd.DataFrame(self.log)
        truth.insert(1, "fila", truth.pop("_rid").map(position))
        truth["fila_relacionada"] = truth.pop("_rid_relacionada").map(position).astype("Int64")
        return df.drop(columns="_rid"), truth


# --- clientes corruptions ---------------------------------------------------------------

def phone_variant(rng):
    def f(d: str) -> str:
        a, rest = d[:2], d[2:]
        options = [f"+52 {a} {rest[:4]} {rest[4:]}", f"044 {a} {rest[:4]} {rest[4:]}",
                   f"({a}) {rest[:4]}-{rest[4:]}", f"52{d}", f"{a}-{rest[:4]}-{rest[4:]}"]
        return options[rng.integers(len(options))]
    return f


def email_variant(rng):
    def f(e: str) -> tuple[str, str]:
        local, domain = e.split("@")
        options = [(f"{local}@@{domain}", "sí"), (f"{local} @{domain}", "sí"),
                   (f"{local.replace('.', ' ', 1)}@{domain}", "sí"), (f"{local}{domain}", "no")]
        if domain.endswith(".com"):
            options.append((f"{local}@{domain[:-4]}.con", "sí"))
        return options[rng.integers(len(options))]
    return f


def imei_variant(rng):
    def f(imei: str) -> str:
        if rng.random() < 0.5:
            return imei[:-1]  # 14 digits
        pos = rng.integers(len(imei))
        new = str((int(imei[pos]) + rng.integers(1, 10)) % 10)  # any single-digit change breaks Luhn
        return imei[:pos] + new + imei[pos + 1:]
    return f


def model_variant(rng):
    def f(m: str) -> str:
        brandless = m.split(" ", 1)[1] if m.split(" ")[0] in ("Samsung", "Google", "Motorola") else f"Apple {m}"
        options = [m.lower().replace(" ", ""), m.upper(), brandless, m.replace(" ", "  ") + " "]
        return options[rng.integers(len(options))]
    return f


def date_variant(rng):
    def f(iso: str) -> str:
        y, m, d = iso.split("-")
        options = [f"{d}/{m}/{y}", f"{m}-{d}-{y}", f"{int(d)} {MONTHS_ES[int(m) - 1]} {y}", f"{y}/{m}/{d}"]
        return options[rng.integers(len(options))]
    return f


def name_variant(rng):
    def f(n: str) -> str:
        first, last = n.split(" ", 1)
        options = [n.upper(), n.lower(), f"  {n} ", f"{first}  {last}", f"{first.upper()} {last.lower()}"]
        return options[rng.integers(len(options))]
    return f


def strip_accents(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()


def inject_clientes(df: pd.DataFrame, rng: np.random.Generator) -> Injector:
    inj = Injector("clientes", df, rng)

    # C1 first, from rows that will stay clean, so each duplicate points to a clean original
    phone = phone_variant(rng)
    def vary(row):
        row["nombre"] = row["nombre"].upper() if rng.random() < 0.5 else strip_accents(row["nombre"])
        if rng.random() < 0.5:
            row["telefono"] = phone(row["telefono"])
        return row
    inj.duplicate("C1", inj.pick(CLIENTES_ERRORS["C1"][0]), vary)

    inj.cell("C2", inj.pick(0.08), "telefono", phone, "sí")
    email = email_variant(rng)
    for i in inj.pick(0.03):  # recoverability depends on the variant
        original = inj.df.at[i, "email"]
        dirty, rec = email(original)
        inj.df.at[i, "email"] = dirty
        inj.record("C3", inj.df.at[i, "_rid"], "email", original, dirty, rec)
    inj.cell("C4", inj.pick(0.02), "imei", imei_variant(rng), "no")
    inj.cell("C5", inj.pick(0.10), "modelo_dispositivo", model_variant(rng), "sí")
    inj.cell("C6", inj.pick(0.08), "fecha_alta", date_variant(rng), "sí")
    inj.cell("C7", inj.pick(0.05), "nombre", name_variant(rng), "sí")
    for i in inj.pick(0.02):
        column = ["email", "modelo_dispositivo"][rng.integers(2)]
        original = inj.df.at[i, column]
        dirty = SENTINELS[rng.integers(len(SENTINELS))]
        inj.df.at[i, column] = dirty
        inj.record("C8", inj.df.at[i, "_rid"], column, original, dirty, "no")
    inj.cell("C9", inj.pick(0.01), "antiguedad_dias",
             lambda v: str(max(0, int(v) + int(rng.choice([-1, 1]) * rng.integers(365, 2000)))), "sí")
    return inj


# --- consumo corruptions ----------------------------------------------------------------

def to_float(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def inject_consumo(df: pd.DataFrame, valid_phones: set[str], rng: np.random.Generator) -> Injector:
    inj = Injector("consumo_mensual", df, rng)

    for i in inj.pick(0.03, to_float(inj.df["datos_3g_mb"]) > 0):
        column = "datos_3g_mb"
        original = inj.df.at[i, column]
        dirty = f"{float(original) / 1024:.4f}"
        inj.df.at[i, column] = dirty
        inj.record("U1", inj.df.at[i, "_rid"], column, original, dirty, "sí")

    inj.cell("U3", inj.pick(0.01, to_float(inj.df["minutos_salientes"]) > 0),
             "minutos_salientes", lambda v: f"-{v}", "parcial")
    inj.cell("U4", inj.pick(0.005, to_float(inj.df["minutos_entrantes"]) > 0),
             "minutos_entrantes", lambda v: f"{float(v) * 100:.2f}", "parcial")

    def month_variant(label: str) -> str:
        y, m = label.split("-")
        options = [f"{MONTHS_ES[int(m) - 1]}-{y}", f"{m}/{y}", f"{y}-{int(m)}"]
        return options[rng.integers(len(options))]
    inj.cell("U5", inj.pick(0.05), "mes", month_variant, "sí")

    for i in inj.pick(0.03):
        candidates = [c for c in DECIMAL_COLUMNS
                      if "." in inj.df.at[i, c] and float(inj.df.at[i, c]) != 0]  # "0,0" is too easy
        if not candidates:
            continue
        column = candidates[rng.integers(len(candidates))]
        original = inj.df.at[i, column]
        dirty = original.replace(".", ",")
        inj.df.at[i, column] = dirty
        inj.record("U6", inj.df.at[i, "_rid"], column, original, dirty, "sí")

    def orphan(_: str) -> str:
        while True:
            number = "".join(rng.choice(list("0123456789"), size=10))
            if number not in valid_phones and number[0] != "0":
                return number
    inj.cell("U7", inj.pick(0.01), "telefono", orphan, "no")

    def next_month(us_date: str) -> str:
        shifted = pd.to_datetime(us_date, format="%m/%d/%Y") + pd.Timedelta(days=31)
        return f"{shifted.month}/{shifted.day}/{shifted.year}"
    inj.cell("U8", inj.pick(0.01, inj.df["fecha_ultima_recarga"] != ""),
             "fecha_ultima_recarga", next_month, "no")

    # U2 last, copying rows that stayed clean (an exact resend of the feed)
    inj.duplicate("U2", inj.pick(0.02))
    return inj


def main() -> None:
    cfg = yaml.safe_load(Path("config.yaml").read_text())
    paths = cfg["paths"]
    rng = np.random.default_rng(cfg["seed"])
    read = lambda name: pd.read_csv(Path(paths["readable"]) / name, dtype=str, keep_default_na=False)

    clientes = read("clientes.csv")
    consumo = read("consumo_mensual.csv")
    clientes_dirty, truth_c = inject_clientes(clientes, rng).finish()
    consumo_dirty, truth_u = inject_consumo(consumo, set(clientes["telefono"]), rng).finish()

    dirty_dir, truth_dir = Path(paths["dirty"]), Path(paths["ground_truth"])
    dirty_dir.mkdir(parents=True, exist_ok=True)
    truth_dir.mkdir(parents=True, exist_ok=True)
    clientes_dirty.to_csv(dirty_dir / "clientes.csv", index=False)
    consumo_dirty.to_csv(dirty_dir / "consumo_mensual.csv", index=False)
    truth = pd.concat([truth_c, truth_u], ignore_index=True)
    truth.to_csv(truth_dir / "errores.csv", index=False)

    print(f"clientes: {len(clientes)} -> {len(clientes_dirty)} | consumo: {len(consumo)} -> {len(consumo_dirty)}")
    print(truth.groupby(["tabla", "tipo"]).size().to_string())


if __name__ == "__main__":
    main()
