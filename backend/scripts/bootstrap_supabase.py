import os
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from supabase_store import get_supabase_store, parse_items  # noqa: E402


DATA_ROOT = PROJECT_ROOT / "data"


def normalize_dataset_label(dataset_key: str) -> str:
    if dataset_key == "datasetA":
        return "Dataset A"
    if dataset_key == "datasetB":
        return "Dataset B"
    if dataset_key == "datasetC":
        return "Dataset C"
    if dataset_key == "datasetD":
        return "Dataset D"
    if dataset_key == "datasetE":
        return "Dataset E"
    if dataset_key == "datasetF":
        return "Dataset F"
    return dataset_key.replace("custom_", "Custom ").replace("_", " ").title()


def ensure_transaction_frame(df: pd.DataFrame) -> pd.DataFrame:
    frame = df.copy()

    source_col = "items" if "items" in frame.columns else "basket" if "basket" in frame.columns else None
    if source_col is None:
        raise ValueError("Transaction CSV must contain 'items' or 'basket' column.")

    frame["items"] = frame[source_col].fillna("").astype(str).apply(lambda v: ", ".join(parse_items(v)))
    frame = frame[frame["items"] != ""].reset_index(drop=True)

    if "timestamp" in frame.columns:
        timestamp = pd.to_datetime(frame["timestamp"], errors="coerce")
    else:
        timestamp = pd.Series(pd.NaT, index=frame.index)

    generated_timestamps = pd.Series(
        pd.date_range(end=pd.Timestamp.now(tz="UTC").floor("min"), periods=len(frame), freq="min"),
        index=frame.index,
    )
    timestamp = pd.to_datetime(timestamp.fillna(generated_timestamps), utc=True, errors="coerce")
    frame["timestamp"] = timestamp.dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    if "segment" not in frame.columns:
        hours = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce").dt.hour.fillna(12)
        frame["segment"] = np.where(
            hours.between(5, 10),
            "morning",
            np.where(hours.between(11, 16), "lunch", "dinner"),
        )
    else:
        segment = frame["segment"].fillna("").astype(str).str.lower().str.strip()
        frame["segment"] = segment.where(segment.isin({"morning", "lunch", "dinner"}), "lunch")

    if "day_type" not in frame.columns:
        day_index = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce").dt.dayofweek.fillna(0)
        frame["day_type"] = np.where(day_index >= 5, "weekend", "weekday")
    else:
        day_type = frame["day_type"].fillna("").astype(str).str.lower().str.strip()
        frame["day_type"] = day_type.where(day_type.isin({"weekday", "weekend"}), "weekday")

    frame["tx_id"] = pd.to_numeric(frame.get("tx_id"), errors="coerce").fillna(0).astype(int)
    zero_tx = frame["tx_id"] <= 0
    if zero_tx.any():
        frame.loc[zero_tx, "tx_id"] = range(1, int(zero_tx.sum()) + 1)

    return frame[["tx_id", "timestamp", "segment", "day_type", "items"]]


def load_dataset_transactions(dataset_key: str) -> pd.DataFrame:
    folder = DATA_ROOT / dataset_key
    if not folder.exists():
        raise FileNotFoundError(f"Missing dataset folder: {folder}")

    chunks = []
    tx_offset = 0
    for batch_no in [1, 2, 3]:
        batch_path = folder / f"batch{batch_no}.csv"
        if not batch_path.exists():
            continue
        raw = pd.read_csv(batch_path)
        tx = ensure_transaction_frame(raw)
        tx["tx_id"] = range(tx_offset + 1, tx_offset + len(tx) + 1)
        tx["batch_no"] = batch_no
        tx_offset += len(tx)
        chunks.append(tx)

    if not chunks:
        raise FileNotFoundError(f"No batch CSV files in {folder}")

    return pd.concat(chunks, ignore_index=True)


def load_dataset_margins(dataset_key: str, transactions_df: pd.DataFrame) -> pd.DataFrame:
    margin_path = DATA_ROOT / dataset_key / "margins.csv"
    if margin_path.exists():
        margin_df = pd.read_csv(margin_path)
        if {"item", "margin_php"}.issubset(set(margin_df.columns)):
            out = margin_df[["item", "margin_php"]].copy()
            out["item"] = out["item"].fillna("").astype(str).str.strip()
            out = out[out["item"] != ""]
            out["margin_php"] = pd.to_numeric(out["margin_php"], errors="coerce").fillna(0.0)
            return out

    unique_items = sorted({item for raw in transactions_df["items"] for item in parse_items(raw)})
    generated = [{"item": item, "margin_php": float(12 + (hash(item) % 18))} for item in unique_items]
    return pd.DataFrame(generated)


def push_dataset(dataset_key: str) -> None:
    transactions_df = load_dataset_transactions(dataset_key)
    margins_df = load_dataset_margins(dataset_key, transactions_df)

    store = get_supabase_store()
    store.replace_dataset_data(
        dataset_key=dataset_key,
        label=normalize_dataset_label(dataset_key),
        transactions_df=transactions_df,
        margins_df=margins_df,
    )

    unique_items = len({item for raw in transactions_df["items"] for item in parse_items(raw)})
    print(
        f"Uploaded {dataset_key}: {len(transactions_df)} transactions, "
        f"{unique_items} unique items, {len(margins_df)} margins"
    )


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")
    load_dotenv()

    args = [arg.strip() for arg in sys.argv[1:] if arg.strip()]
    if args:
        dataset_keys = []
        for arg in args:
            key = arg
            lower = arg.lower()
            if lower == "a":
                key = "datasetA"
            elif lower == "b":
                key = "datasetB"
            elif lower == "c":
                key = "datasetC"
            elif lower == "d":
                key = "datasetD"
            elif lower == "e":
                key = "datasetE"
            elif lower == "f":
                key = "datasetF"
            elif not re.match(r"^dataset[a-z0-9_]+$", arg, flags=re.IGNORECASE):
                key = f"custom_{re.sub(r'[^a-z0-9]+', '_', lower).strip('_')}"
            dataset_keys.append(key)
    else:
        dataset_keys = ["datasetA", "datasetB", "datasetC", "datasetD", "datasetE", "datasetF"]

    status = get_supabase_store().status()
    if not status["ready"]:
        raise RuntimeError(
            "Supabase tables are not ready. Run backend/sql/supabase_schema.sql first. "
            f"Status: {status}"
        )

    for dataset_key in dataset_keys:
        push_dataset(dataset_key)

    print("Supabase bootstrap complete.")


if __name__ == "__main__":
    main()
