from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

SOURCE_DIR = Path("data/Inventory Management")
OUT_DIR = Path("data/processed")
RAW_DIR = OUT_DIR / "raw"
CLEAN_DIR = OUT_DIR / "clean"

DATE_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
CHUNK_SIZE = 200_000
LARGE_FILE_BYTES = 50 * 1024 * 1024

DATETIME_HINTS = {
    "created",
    "updated",
    "start_time",
    "end_time",
    "start_date_time",
    "end_date_time",
    "promise_time",
    "pickup_time",
    "report_date",
    "balance_date",
    "valid_from",
    "valid_to",
    "contract_start",
    "termination_date",
}

NUMERIC_HINT_TOKENS = (
    "_id",
    "amount",
    "price",
    "quantity",
    "vat",
    "discount",
    "points",
    "cash",
    "cost",
    "value",
    "commission",
    "redemptions",
    "orders",
    "cltv",
    "threshold",
    "number",
    "index",
    "variance",
    "balance",
    "total",
    "opening",
    "closing",
    "expected",
    "actual",
    "tier",
    "service_charge",
    "delivery_charge",
)


def is_epoch_unit(series: pd.Series) -> str | None:
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().mean() < 0.6:
        return None
    numeric_non_null = numeric.dropna()
    if numeric_non_null.empty:
        return None
    max_value = numeric_non_null.max()
    if max_value > 1e12:
        lower, upper = 946684800000, 4102444800000
        share = numeric_non_null.between(lower, upper).mean()
        if share >= 0.6:
            return "ms"
        return None
    if max_value > 1e9:
        lower, upper = 946684800, 4102444800
        share = numeric_non_null.between(lower, upper).mean()
        if share >= 0.6:
            return "s"
    return None


def add_datetime_columns(df: pd.DataFrame) -> pd.DataFrame:
    for col in df.columns:
        col_lower = col.lower().strip()
        if (
            col_lower in DATETIME_HINTS
            or col_lower.endswith("_time")
            or col_lower.endswith("_date")
            or col_lower.endswith("_datetime")
        ):
            unit = is_epoch_unit(df[col])
            if unit is None:
                continue
            try:
                numeric = pd.to_numeric(df[col], errors="coerce").astype("float64")
                dt_values = pd.to_datetime(
                    numeric.to_numpy(),
                    unit=unit,
                    errors="coerce",
                    utc=True,
                )
                df[f"{col}_dt"] = (
                    pd.Series(dt_values, index=df.index).dt.strftime(DATE_FORMAT)
                )
            except Exception:
                continue
    return df


def should_try_numeric(column_name: str) -> bool:
    name = column_name.lower()
    if name in {"id", "index", "number"}:
        return True
    return any(token in name for token in NUMERIC_HINT_TOKENS)


def coerce_numeric_columns(df: pd.DataFrame) -> pd.DataFrame:
    for col in df.columns:
        if col.endswith("_dt"):
            continue
        if not should_try_numeric(col):
            continue
        numeric = pd.to_numeric(df[col], errors="coerce")
        if numeric.notna().mean() >= 0.6:
            df[col] = numeric
    return df


def strip_string_columns(df: pd.DataFrame) -> pd.DataFrame:
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].astype("string").str.strip()
    return df


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [c.strip() for c in df.columns]
    df = strip_string_columns(df)
    df = coerce_numeric_columns(df)
    df = add_datetime_columns(df)
    return df


def process_file(path: Path) -> None:
    output_path = CLEAN_DIR / path.name
    if path.stat().st_size > LARGE_FILE_BYTES:
        if output_path.exists():
            output_path.unlink()
        for i, chunk in enumerate(
            pd.read_csv(
                path,
                dtype=str,
                chunksize=CHUNK_SIZE,
                encoding="utf-8",
                encoding_errors="replace",
                low_memory=False,
            )
        ):
            cleaned = clean_dataframe(chunk)
            cleaned.to_csv(
                output_path,
                index=False,
                mode="w" if i == 0 else "a",
                header=i == 0,
            )
    else:
        df = pd.read_csv(
            path,
            dtype=str,
            encoding="utf-8",
            encoding_errors="replace",
            low_memory=False,
        )
        cleaned = clean_dataframe(df)
        cleaned.to_csv(output_path, index=False)


def write_manifest(source_dir: Path, manifest_path: Path) -> None:
    rows = []
    for csv_path in sorted(source_dir.glob("*.csv")):
        stat = csv_path.stat()
        modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        rows.append(
            {
                "file": csv_path.name,
                "size_bytes": stat.st_size,
                "modified_utc": modified.strftime(DATE_FORMAT),
            }
        )

    with open(manifest_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["file", "size_bytes", "modified_utc"]
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    CLEAN_DIR.mkdir(parents=True, exist_ok=True)

    write_manifest(SOURCE_DIR, RAW_DIR / "manifest.csv")

    for csv_path in sorted(SOURCE_DIR.glob("*.csv")):
        process_file(csv_path)


if __name__ == "__main__":
    main()
