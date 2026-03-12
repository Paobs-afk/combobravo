import math
import os
import logging
import time
import json
import shutil
from collections import Counter
from typing import Dict, List
from urllib.parse import urlparse

import pandas as pd
from dotenv import load_dotenv
from supabase import Client, create_client

BASE_DIR = os.path.dirname(__file__)
load_dotenv(os.path.join(BASE_DIR, ".env"))
load_dotenv()

DATASETS_TABLE = os.getenv("SUPABASE_DATASETS_TABLE", "cb_datasets")
TRANSACTIONS_TABLE = os.getenv("SUPABASE_TRANSACTIONS_TABLE", "cb_transactions")
MARGINS_TABLE = os.getenv("SUPABASE_MARGINS_TABLE", "cb_item_margins")
logger = logging.getLogger("combobravo.supabase")


def parse_items(raw_items: str) -> List[str]:
    return [piece.strip() for piece in str(raw_items).split(",") if piece.strip()]


def _dataset_id_label(dataset_key: str, explicit_label: str | None = None) -> tuple[str, str]:
    lower = dataset_key.lower()
    if lower == "dataseta":
        return "A", explicit_label or "Dataset A"
    if lower == "datasetb":
        return "B", explicit_label or "Dataset B"
    if lower == "datasetc":
        return "C", explicit_label or "Dataset C"
    if lower == "datasetd":
        return "D", explicit_label or "Dataset D"
    if lower == "datasete":
        return "E", explicit_label or "Dataset E"
    if lower == "datasetf":
        return "F", explicit_label or "Dataset F"
    label = explicit_label or dataset_key.replace("custom_", "Custom ").replace("_", " ").title()
    return dataset_key, label


def _preferred_dataset_order(dataset_keys: List[str]) -> List[str]:
    preferred = ["datasetA", "datasetB"]
    ordered = [name for name in preferred if name in dataset_keys]
    ordered.extend(sorted(name for name in dataset_keys if name not in preferred))
    return ordered


def normalize_transactions_df(
    df: pd.DataFrame, iteration: int, include_batch_no: bool = False
) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["tx_id", "timestamp", "segment", "day_type", "items", "basket"])

    if "tx_id" not in df.columns:
        df["tx_id"] = range(1, len(df) + 1)

    if "timestamp" not in df.columns:
        df["timestamp"] = pd.NaT

    df["_sort_tx_id"] = pd.to_numeric(df["tx_id"], errors="coerce").fillna(10**12)
    df["_sort_ts"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.sort_values(["_sort_tx_id", "_sort_ts"], na_position="last").drop(columns=["_sort_tx_id", "_sort_ts"])
    df = df.reset_index(drop=True)

    if "batch_no" in df.columns and df["batch_no"].notna().any():
        numeric_batch = pd.to_numeric(df["batch_no"], errors="coerce")
        df = df[numeric_batch <= int(iteration)].copy()
    else:
        total = len(df)
        chunk_size = max(math.ceil(total / 3), 1)
        cutoff = min(total, chunk_size * int(iteration))
        df = df.head(cutoff).copy()

    df["items"] = df.get("items", "").fillna("").astype(str)
    df = df[df["items"].str.strip() != ""].copy()
    if df.empty:
        return pd.DataFrame(columns=["tx_id", "timestamp", "segment", "day_type", "items", "basket"])

    timestamp = pd.to_datetime(df.get("timestamp"), errors="coerce")
    generated_timestamps = pd.Series(
        pd.date_range(end=pd.Timestamp.now(tz="UTC").floor("min"), periods=len(df), freq="min"),
        index=df.index,
    )
    timestamp = timestamp.fillna(generated_timestamps)
    df["timestamp"] = timestamp.astype(str)

    if "segment" not in df.columns:
        df["segment"] = "lunch"
    normalized_segment = df["segment"].fillna("").astype(str).str.lower().str.strip()
    hour_values = pd.to_datetime(df["timestamp"], errors="coerce").dt.hour.fillna(12)
    generated_segment = pd.Series(
        [
            "morning" if 5 <= int(hour) <= 10 else "lunch" if 11 <= int(hour) <= 16 else "dinner"
            for hour in hour_values
        ],
        index=df.index,
    )
    df["segment"] = normalized_segment.where(
        normalized_segment.isin({"morning", "lunch", "dinner"}),
        generated_segment,
    )

    if "day_type" not in df.columns:
        df["day_type"] = "weekday"
    normalized_day = df["day_type"].fillna("").astype(str).str.lower().str.strip()
    weekday_index = pd.to_datetime(df["timestamp"], errors="coerce").dt.dayofweek.fillna(0)
    generated_day = pd.Series(
        ["weekend" if int(day) >= 5 else "weekday" for day in weekday_index],
        index=df.index,
    )
    df["day_type"] = normalized_day.where(
        normalized_day.isin({"weekday", "weekend"}),
        generated_day,
    )

    df["tx_id"] = pd.to_numeric(df["tx_id"], errors="coerce").fillna(0).astype(int)
    zero_tx = df["tx_id"] <= 0
    if zero_tx.any():
        df.loc[zero_tx, "tx_id"] = range(1, int(zero_tx.sum()) + 1)

    df["batch_no"] = pd.to_numeric(df.get("batch_no"), errors="coerce").fillna(1).astype(int)
    df["basket"] = df["items"].apply(parse_items)
    columns = ["tx_id", "timestamp", "segment", "day_type", "items", "basket"]
    if include_batch_no:
        columns.append("batch_no")
    return df[columns]


class SupabaseStore:
    def __init__(self, url: str, key: str):
        self.client: Client = create_client(url, key)
        self.datasets_table = DATASETS_TABLE
        self.transactions_table = TRANSACTIONS_TABLE
        self.margins_table = MARGINS_TABLE
        self.cache_ttl_seconds = max(float(os.getenv("SUPABASE_CACHE_TTL_SECONDS", "20")), 0.0)
        self._dataset_keys_cache: List[str] | None = None
        self._dataset_keys_cache_until: float = 0.0
        self._datasets_cache: List[Dict[str, object]] | None = None
        self._datasets_cache_until: float = 0.0

    def _fetch_all(self, table_name: str, columns: str = "*", page_size: int = 1000, **filters) -> List[dict]:
        rows: List[dict] = []
        offset = 0
        while True:
            query = self.client.table(table_name).select(columns)
            for key, value in filters.items():
                query = query.eq(key, value)
            query = query.range(offset, offset + page_size - 1)
            try:
                response = query.execute()
            except Exception as exc:
                logger.warning("Supabase read failed for table '%s': %s", table_name, exc)
                return rows
            batch = response.data or []
            if not batch:
                break
            rows.extend(batch)
            if len(batch) < page_size:
                break
            offset += page_size
        return rows

    def _cache_is_valid(self, expiry: float) -> bool:
        return expiry > time.monotonic()

    def clear_cache(self) -> None:
        self._dataset_keys_cache = None
        self._dataset_keys_cache_until = 0.0
        self._datasets_cache = None
        self._datasets_cache_until = 0.0

    def list_dataset_keys(self) -> List[str]:
        if self._dataset_keys_cache is not None and self._cache_is_valid(self._dataset_keys_cache_until):
            return list(self._dataset_keys_cache)

        keys: set[str] = set()

        datasets = self._fetch_all(self.datasets_table, columns="dataset_key")
        for row in datasets:
            dataset_key = str(row.get("dataset_key") or "").strip()
            if dataset_key:
                keys.add(dataset_key)

        tx_rows = self._fetch_all(self.transactions_table, columns="dataset_key")
        for row in tx_rows:
            dataset_key = str(row.get("dataset_key") or "").strip()
            if dataset_key:
                keys.add(dataset_key)

        if not keys:
            return []

        ordered = _preferred_dataset_order(list(keys))
        self._dataset_keys_cache = ordered
        self._dataset_keys_cache_until = time.monotonic() + self.cache_ttl_seconds
        return ordered

    def dataset_exists(self, dataset_key: str) -> bool:
        normalized = dataset_key.strip().lower()
        return any(entry.lower() == normalized for entry in self.list_dataset_keys())

    def get_dataset_key_case_insensitive(self, dataset_key: str) -> str | None:
        normalized = dataset_key.strip().lower()
        for entry in self.list_dataset_keys():
            if entry.lower() == normalized:
                return entry
        return None

    def list_datasets(self) -> List[Dict[str, object]]:
        if self._datasets_cache is not None and self._cache_is_valid(self._datasets_cache_until):
            return [dict(row) for row in self._datasets_cache]

        dataset_meta = {
            str(row.get("dataset_key")): row
            for row in self._fetch_all(self.datasets_table, columns="dataset_key,label")
            if row.get("dataset_key")
        }
        tx_rows = self._fetch_all(self.transactions_table, columns="dataset_key,items,batch_no")
        stats: Dict[str, Dict[str, object]] = {}
        for tx in tx_rows:
            dataset_key = str(tx.get("dataset_key") or "").strip()
            if not dataset_key:
                continue
            if dataset_key not in stats:
                stats[dataset_key] = {"transactions": 0, "unique_items": set(), "batch_count": 0}
            stats[dataset_key]["transactions"] = int(stats[dataset_key]["transactions"]) + 1
            try:
                batch_no = int(tx.get("batch_no") or 0)
            except Exception:
                batch_no = 0
            stats[dataset_key]["batch_count"] = max(int(stats[dataset_key]["batch_count"]), max(batch_no, 0))
            for item in parse_items(tx.get("items", "")):
                unique_items = stats[dataset_key]["unique_items"]
                if isinstance(unique_items, set):
                    unique_items.add(item)

        all_dataset_keys = set(dataset_meta.keys()) | set(stats.keys())
        ordered_keys = _preferred_dataset_order(list(all_dataset_keys))

        rows: List[Dict[str, object]] = []
        for dataset_key in ordered_keys:
            meta_label = dataset_meta.get(dataset_key, {}).get("label")
            dataset_id, label = _dataset_id_label(dataset_key, explicit_label=meta_label)
            stat = stats.get(dataset_key, {"transactions": 0, "unique_items": set(), "batch_count": 0})
            unique_items = stat.get("unique_items", set())
            unique_count = len(unique_items) if isinstance(unique_items, set) else 0
            transactions_count = int(stat.get("transactions", 0) or 0)
            batch_count = int(stat.get("batch_count", 0) or 0)
            if transactions_count > 0 and batch_count <= 0:
                batch_count = 1
            rows.append(
                {
                    "id": dataset_id,
                    "folder": dataset_key,
                    "dataset_key": dataset_key,
                    "label": label,
                    "transactions": transactions_count,
                    "unique_items": int(unique_count),
                    "batch_count": batch_count,
                }
            )

        rows.sort(
            key=lambda item: (
                0 if item["dataset_key"] in {"datasetA", "datasetB"} else 1,
                str(item["label"]).lower(),
            )
        )
        self._datasets_cache = [dict(row) for row in rows]
        self._datasets_cache_until = time.monotonic() + self.cache_ttl_seconds
        self._dataset_keys_cache = [row["dataset_key"] for row in rows if row.get("dataset_key")]
        self._dataset_keys_cache_until = time.monotonic() + self.cache_ttl_seconds
        return rows

    def top_meals(self, dataset_key: str, limit: int | None = None) -> List[Dict[str, object]]:
        tx_rows = self._fetch_all(
            self.transactions_table,
            columns="items",
            dataset_key=dataset_key,
        )
        counts = Counter()
        for row in tx_rows:
            for item in parse_items(row.get("items", "")):
                counts[item] += 1

        total = sum(counts.values())
        rows = [
            {
                "item": item,
                "count": int(count),
                "share": float(count / total) if total else 0.0,
            }
            for item, count in counts.most_common(limit)
        ]
        return rows

    def load_transactions_for_iteration(
        self, dataset_key: str, iteration: int, include_batch_no: bool = False
    ) -> pd.DataFrame:
        rows = self._fetch_all(
            self.transactions_table,
            columns="tx_id,timestamp,segment,day_type,items,batch_no",
            dataset_key=dataset_key,
        )
        if not rows:
            columns = ["tx_id", "timestamp", "segment", "day_type", "items", "basket"]
            if include_batch_no:
                columns.append("batch_no")
            return pd.DataFrame(columns=columns)
        return normalize_transactions_df(
            pd.DataFrame(rows), iteration=iteration, include_batch_no=include_batch_no
        )

    def get_margin_map(self, dataset_key: str) -> Dict[str, float]:
        rows = self._fetch_all(
            self.margins_table,
            columns="item,margin_php",
            dataset_key=dataset_key,
        )
        margin_map: Dict[str, float] = {}
        for row in rows:
            item = str(row.get("item") or "").strip()
            if not item:
                continue
            try:
                margin_map[item] = float(row.get("margin_php") or 0.0)
            except Exception:
                margin_map[item] = 0.0
        return margin_map

    def upsert_dataset(self, dataset_key: str, label: str) -> None:
        self.client.table(self.datasets_table).upsert(
            [{"dataset_key": dataset_key, "label": label}],
            on_conflict="dataset_key",
        ).execute()

    def table_accessible(self, table_name: str) -> tuple[bool, str | None]:
        try:
            self.client.table(table_name).select("*").limit(1).execute()
            return True, None
        except Exception as exc:
            return False, str(exc)

    def status(self) -> Dict[str, object]:
        dataset_ok, dataset_error = self.table_accessible(self.datasets_table)
        tx_ok, tx_error = self.table_accessible(self.transactions_table)
        margin_ok, margin_error = self.table_accessible(self.margins_table)
        parsed = urlparse(str(self.client.supabase_url))
        return {
            "supabase_host": parsed.netloc or str(self.client.supabase_url),
            "tables": {
                self.datasets_table: {"ok": dataset_ok, "error": dataset_error},
                self.transactions_table: {"ok": tx_ok, "error": tx_error},
                self.margins_table: {"ok": margin_ok, "error": margin_error},
            },
            "ready": dataset_ok and tx_ok and margin_ok,
        }

    def replace_dataset_data(
        self,
        dataset_key: str,
        label: str,
        transactions_df: pd.DataFrame,
        margins_df: pd.DataFrame,
    ) -> None:
        status = self.status()
        if not status["ready"]:
            raise RuntimeError(
                "Supabase tables are not ready. Run backend/sql/supabase_schema.sql first. "
                f"Status: {status}"
            )

        self.upsert_dataset(dataset_key, label)
        self.client.table(self.transactions_table).delete().eq("dataset_key", dataset_key).execute()
        self.client.table(self.margins_table).delete().eq("dataset_key", dataset_key).execute()

        if not transactions_df.empty:
            payload = []
            for row in transactions_df.to_dict(orient="records"):
                tx_id = int(row.get("tx_id") or 0)
                batch_no = int(row.get("batch_no") or 1)
                payload.append(
                    {
                        "dataset_key": dataset_key,
                        "tx_id": tx_id,
                        "timestamp": str(row.get("timestamp") or ""),
                        "segment": str(row.get("segment") or "lunch"),
                        "day_type": str(row.get("day_type") or "weekday"),
                        "items": str(row.get("items") or ""),
                        "batch_no": batch_no,
                    }
                )
            for start in range(0, len(payload), 500):
                self.client.table(self.transactions_table).insert(payload[start : start + 500]).execute()

        if not margins_df.empty:
            payload = []
            for row in margins_df.to_dict(orient="records"):
                item = str(row.get("item") or "").strip()
                if not item:
                    continue
                payload.append(
                    {
                        "dataset_key": dataset_key,
                        "item": item,
                        "margin_php": float(row.get("margin_php") or 0.0),
                    }
                )
            for start in range(0, len(payload), 500):
                self.client.table(self.margins_table).upsert(
                    payload[start : start + 500],
                    on_conflict="dataset_key,item",
                ).execute()
        self.clear_cache()

    def delete_dataset(self, dataset_key: str) -> None:
        self.client.table(self.datasets_table).delete().eq("dataset_key", dataset_key).execute()
        self.clear_cache()


class LocalCsvStore:
    def __init__(self, data_root: str | None = None, fallback_reason: str | None = None):
        self.data_root = data_root or os.path.join(BASE_DIR, "data")
        self.local_root = os.path.join(self.data_root, "local_datasets")
        self.registry_path = os.path.join(self.local_root, "registry.json")
        self.fallback_reason = fallback_reason or ""
        os.makedirs(self.local_root, exist_ok=True)
        self._registry = self._load_registry()

    def _load_registry(self) -> Dict[str, Dict[str, str]]:
        if not os.path.exists(self.registry_path):
            return {}
        try:
            with open(self.registry_path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            if isinstance(payload, dict):
                return {
                    str(key): value
                    for key, value in payload.items()
                    if isinstance(value, dict)
                }
        except Exception:
            return {}
        return {}

    def _save_registry(self) -> None:
        with open(self.registry_path, "w", encoding="utf-8") as handle:
            json.dump(self._registry, handle, indent=2, ensure_ascii=False)

    def _dataset_dir(self, dataset_key: str) -> str | None:
        local_dir = os.path.join(self.local_root, dataset_key)
        if os.path.isdir(local_dir):
            return local_dir
        base_dir = os.path.join(self.data_root, dataset_key)
        if os.path.isdir(base_dir):
            return base_dir
        return None

    def _batch_files(self, dataset_key: str) -> List[tuple[int, str]]:
        dataset_dir = self._dataset_dir(dataset_key)
        if not dataset_dir:
            return []
        rows: List[tuple[int, str]] = []
        for file_name in os.listdir(dataset_dir):
            lower = file_name.lower()
            if not lower.startswith("batch") or not lower.endswith(".csv"):
                continue
            numeric = "".join(ch for ch in lower if ch.isdigit())
            batch_no = int(numeric) if numeric else 1
            rows.append((batch_no, os.path.join(dataset_dir, file_name)))
        return sorted(rows, key=lambda item: (item[0], item[1]))

    def _load_dataset_transactions(self, dataset_key: str) -> pd.DataFrame:
        batch_files = self._batch_files(dataset_key)
        frames: List[pd.DataFrame] = []
        for batch_no, file_path in batch_files:
            try:
                frame = pd.read_csv(file_path)
            except Exception:
                continue
            frame = frame.copy()
            if "batch_no" not in frame.columns:
                frame["batch_no"] = batch_no
            frames.append(frame)

        if not frames:
            dataset_dir = self._dataset_dir(dataset_key)
            if not dataset_dir:
                return pd.DataFrame()
            merged_file = os.path.join(dataset_dir, "transactions.csv")
            if os.path.exists(merged_file):
                try:
                    merged = pd.read_csv(merged_file)
                    if "batch_no" not in merged.columns:
                        merged["batch_no"] = 1
                    frames.append(merged)
                except Exception:
                    pass
        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)

    def clear_cache(self) -> None:
        self._registry = self._load_registry()

    def list_dataset_keys(self) -> List[str]:
        keys: set[str] = set()

        if os.path.isdir(self.data_root):
            for folder in os.listdir(self.data_root):
                if folder in {"upload_samples", "local_datasets"}:
                    continue
                folder_path = os.path.join(self.data_root, folder)
                if not os.path.isdir(folder_path):
                    continue
                has_batch = any(
                    file_name.lower().startswith("batch") and file_name.lower().endswith(".csv")
                    for file_name in os.listdir(folder_path)
                )
                if has_batch:
                    keys.add(folder)

        if os.path.isdir(self.local_root):
            for folder in os.listdir(self.local_root):
                folder_path = os.path.join(self.local_root, folder)
                if os.path.isdir(folder_path):
                    keys.add(folder)

        keys.update(self._registry.keys())
        if not keys:
            return []
        return _preferred_dataset_order(list(keys))

    def dataset_exists(self, dataset_key: str) -> bool:
        normalized = dataset_key.strip().lower()
        return any(entry.lower() == normalized for entry in self.list_dataset_keys())

    def get_dataset_key_case_insensitive(self, dataset_key: str) -> str | None:
        normalized = dataset_key.strip().lower()
        for entry in self.list_dataset_keys():
            if entry.lower() == normalized:
                return entry
        return None

    def list_datasets(self) -> List[Dict[str, object]]:
        rows: List[Dict[str, object]] = []
        for dataset_key in self.list_dataset_keys():
            dataset_df = self._load_dataset_transactions(dataset_key)
            transactions = int(len(dataset_df))
            unique_items: set[str] = set()
            if not dataset_df.empty and "items" in dataset_df.columns:
                for raw_items in dataset_df["items"].fillna("").astype(str).tolist():
                    unique_items.update(parse_items(raw_items))
            if not dataset_df.empty and "batch_no" in dataset_df.columns:
                batch_count = int(
                    pd.to_numeric(dataset_df["batch_no"], errors="coerce").fillna(0).astype(int).max()
                )
            else:
                batch_count = 1 if transactions else 0
            if transactions > 0 and batch_count <= 0:
                batch_count = 1
            label_override = self._registry.get(dataset_key, {}).get("label")
            dataset_id, label = _dataset_id_label(dataset_key, explicit_label=label_override)
            rows.append(
                {
                    "id": dataset_id,
                    "folder": dataset_key,
                    "dataset_key": dataset_key,
                    "label": label,
                    "transactions": transactions,
                    "unique_items": len(unique_items),
                    "batch_count": batch_count,
                }
            )
        rows.sort(
            key=lambda item: (
                0 if item["dataset_key"] in {"datasetA", "datasetB"} else 1,
                str(item["label"]).lower(),
            )
        )
        return rows

    def top_meals(self, dataset_key: str, limit: int | None = None) -> List[Dict[str, object]]:
        dataset_df = self._load_dataset_transactions(dataset_key)
        counts = Counter()
        if not dataset_df.empty and "items" in dataset_df.columns:
            for raw_items in dataset_df["items"].fillna("").astype(str).tolist():
                for item in parse_items(raw_items):
                    counts[item] += 1
        total = sum(counts.values())
        rows = [
            {
                "item": item,
                "count": int(count),
                "share": float(count / total) if total else 0.0,
            }
            for item, count in counts.most_common(limit)
        ]
        return rows

    def load_transactions_for_iteration(
        self, dataset_key: str, iteration: int, include_batch_no: bool = False
    ) -> pd.DataFrame:
        dataset_df = self._load_dataset_transactions(dataset_key)
        if dataset_df.empty:
            columns = ["tx_id", "timestamp", "segment", "day_type", "items", "basket"]
            if include_batch_no:
                columns.append("batch_no")
            return pd.DataFrame(columns=columns)
        return normalize_transactions_df(
            dataset_df, iteration=iteration, include_batch_no=include_batch_no
        )

    def get_margin_map(self, dataset_key: str) -> Dict[str, float]:
        dataset_dir = self._dataset_dir(dataset_key)
        if not dataset_dir:
            return {}
        margins_file = os.path.join(dataset_dir, "margins.csv")
        if not os.path.exists(margins_file):
            return {}
        try:
            margins_df = pd.read_csv(margins_file)
        except Exception:
            return {}
        margin_map: Dict[str, float] = {}
        for _, row in margins_df.iterrows():
            item = str(row.get("item") or "").strip()
            if not item:
                continue
            try:
                margin_map[item] = float(row.get("margin_php") or 0.0)
            except Exception:
                margin_map[item] = 0.0
        return margin_map

    def status(self) -> Dict[str, object]:
        return {
            "storage": "local_csv",
            "ready": True,
            "data_root": self.data_root,
            "fallback_reason": self.fallback_reason,
        }

    def replace_dataset_data(
        self,
        dataset_key: str,
        label: str,
        transactions_df: pd.DataFrame,
        margins_df: pd.DataFrame,
    ) -> None:
        dataset_dir = os.path.join(self.local_root, dataset_key)
        os.makedirs(dataset_dir, exist_ok=True)

        for file_name in os.listdir(dataset_dir):
            if file_name.lower().startswith("batch") and file_name.lower().endswith(".csv"):
                os.remove(os.path.join(dataset_dir, file_name))
            if file_name.lower() == "margins.csv":
                os.remove(os.path.join(dataset_dir, file_name))

        tx_df = transactions_df.copy()
        tx_df["batch_no"] = pd.to_numeric(tx_df.get("batch_no"), errors="coerce").fillna(1).astype(int)
        export_columns = ["tx_id", "timestamp", "segment", "day_type", "items", "batch_no"]
        for batch_no in sorted(tx_df["batch_no"].unique().tolist()):
            batch_frame = tx_df[tx_df["batch_no"] == int(batch_no)][export_columns].copy()
            batch_path = os.path.join(dataset_dir, f"batch{int(batch_no)}.csv")
            batch_frame.to_csv(batch_path, index=False)

        margin_export = margins_df.copy()
        margin_export = margin_export[["item", "margin_php"]]
        margin_export.to_csv(os.path.join(dataset_dir, "margins.csv"), index=False)

        self._registry[dataset_key] = {"label": label}
        self._save_registry()

    def delete_dataset(self, dataset_key: str) -> None:
        dataset_dir = os.path.join(self.local_root, dataset_key)
        if os.path.isdir(dataset_dir):
            shutil.rmtree(dataset_dir, ignore_errors=True)
        if dataset_key in self._registry:
            self._registry.pop(dataset_key, None)
            self._save_registry()


_STORE: SupabaseStore | LocalCsvStore | None = None


def get_supabase_store() -> SupabaseStore | LocalCsvStore:
    global _STORE
    if _STORE is not None:
        return _STORE

    mode = os.getenv("STORE_MODE", "auto").strip().lower()
    data_root = os.getenv("LOCAL_DATA_ROOT", os.path.join(BASE_DIR, "data"))

    def use_local(reason: str) -> LocalCsvStore:
        logger.warning("Using local CSV fallback store: %s", reason)
        return LocalCsvStore(data_root=data_root, fallback_reason=reason)

    if mode in {"local", "csv", "offline"}:
        _STORE = use_local("forced by STORE_MODE")
        return _STORE

    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip() or os.getenv("SUPABASE_ANON_KEY", "").strip()

    if not url or not key:
        if mode == "supabase":
            raise RuntimeError(
                "Missing Supabase credentials. Set SUPABASE_URL and SUPABASE_ANON_KEY (or SUPABASE_SERVICE_ROLE_KEY) in backend/.env"
            )
        _STORE = use_local("missing Supabase credentials")
        return _STORE

    try:
        candidate = SupabaseStore(url=url, key=key)
        if mode == "supabase":
            _STORE = candidate
            return _STORE

        status = candidate.status()
        if status.get("ready"):
            _STORE = candidate
        else:
            reason = f"Supabase not ready: {status}"
            _STORE = use_local(reason)
    except Exception as exc:
        if mode == "supabase":
            raise
        _STORE = use_local(f"Supabase initialization failed: {exc}")
    return _STORE
