import math
import os
import logging
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


class SupabaseStore:
    def __init__(self, url: str, key: str):
        self.client: Client = create_client(url, key)
        self.datasets_table = DATASETS_TABLE
        self.transactions_table = TRANSACTIONS_TABLE
        self.margins_table = MARGINS_TABLE

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

    def _dataset_id_label(self, dataset_key: str, explicit_label: str | None = None) -> tuple[str, str]:
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

    def list_dataset_keys(self) -> List[str]:
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

        preferred = ["datasetA", "datasetB"]
        ordered = [name for name in preferred if name in keys]
        ordered.extend(sorted(name for name in keys if name not in preferred))
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
        dataset_meta = {
            str(row.get("dataset_key")): row
            for row in self._fetch_all(self.datasets_table, columns="dataset_key,label")
            if row.get("dataset_key")
        }

        rows: List[Dict[str, object]] = []
        for dataset_key in self.list_dataset_keys():
            tx_rows = self._fetch_all(
                self.transactions_table,
                columns="items",
                dataset_key=dataset_key,
            )
            unique_items: set[str] = set()
            for tx in tx_rows:
                for item in parse_items(tx.get("items", "")):
                    unique_items.add(item)

            meta_label = dataset_meta.get(dataset_key, {}).get("label")
            dataset_id, label = self._dataset_id_label(dataset_key, explicit_label=meta_label)
            rows.append(
                {
                    "id": dataset_id,
                    "folder": dataset_key,
                    "dataset_key": dataset_key,
                    "label": label,
                    "transactions": len(tx_rows),
                    "unique_items": len(unique_items),
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

    def load_transactions_for_iteration(self, dataset_key: str, iteration: int) -> pd.DataFrame:
        rows = self._fetch_all(
            self.transactions_table,
            columns="tx_id,timestamp,segment,day_type,items,batch_no",
            dataset_key=dataset_key,
        )
        if not rows:
            return pd.DataFrame(columns=["tx_id", "timestamp", "segment", "day_type", "items", "basket"])

        df = pd.DataFrame(rows)
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

        df["basket"] = df["items"].apply(parse_items)
        return df[["tx_id", "timestamp", "segment", "day_type", "items", "basket"]]

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


_STORE: SupabaseStore | None = None


def get_supabase_store() -> SupabaseStore:
    global _STORE
    if _STORE is not None:
        return _STORE

    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip() or os.getenv("SUPABASE_ANON_KEY", "").strip()

    if not url or not key:
        raise RuntimeError(
            "Missing Supabase credentials. Set SUPABASE_URL and SUPABASE_ANON_KEY (or SUPABASE_SERVICE_ROLE_KEY) in backend/.env"
        )

    _STORE = SupabaseStore(url=url, key=key)
    return _STORE
