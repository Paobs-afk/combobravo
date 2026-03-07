import io
import json
import logging
import os
import re
from collections import Counter
from typing import Dict, List

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from mba_engine import OUTPUT_ROOT, run_all_datasets, run_dataset_iterations
from supabase_store import get_supabase_store, parse_items

BASE_DIR = os.path.dirname(__file__)
load_dotenv(os.path.join(BASE_DIR, ".env"))
load_dotenv()

app = FastAPI(title="ComboBravo MBA API", version="4.0.0")
os.makedirs(OUTPUT_ROOT, exist_ok=True)
logger = logging.getLogger("combobravo.api")

BASE_DATASET_MAP: Dict[str, str] = {
    "a": "datasetA",
    "dataseta": "datasetA",
    "b": "datasetB",
    "datasetb": "datasetB",
    "c": "datasetC",
    "datasetc": "datasetC",
    "d": "datasetD",
    "datasetd": "datasetD",
    "e": "datasetE",
    "datasete": "datasetE",
    "f": "datasetF",
    "datasetf": "datasetF",
}

cors_origins = [
    entry.strip()
    for entry in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    if entry.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def resolve_dataset(dataset_type: str, allow_all: bool = False) -> str:
    key = (dataset_type or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="Dataset is required.")

    lower_key = key.lower()
    if allow_all and lower_key in {"all", "overall"}:
        return "all"

    canonical = BASE_DATASET_MAP.get(lower_key, key)
    store = get_supabase_store()
    matched = store.get_dataset_key_case_insensitive(canonical)
    if matched:
        return matched

    raise HTTPException(
        status_code=400,
        detail="Dataset not found in Supabase. Use A, B, or an uploaded dataset id.",
    )


def sanitize_dataset_name(dataset_name: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", dataset_name.strip().lower()).strip("_")
    if not cleaned:
        cleaned = "uploaded"
    if cleaned in BASE_DATASET_MAP:
        return BASE_DATASET_MAP.get(cleaned, cleaned)
    return f"custom_{cleaned}" if not cleaned.startswith("custom_") else cleaned


def get_output_file(dataset_key: str, iteration: int, suffix: str) -> str:
    return os.path.join(OUTPUT_ROOT, dataset_key, f"iteration_{iteration}_{suffix}")


def ensure_output_exists(dataset_key: str, iteration: int, suffix: str, message: str) -> str:
    file_path = get_output_file(dataset_key, iteration, suffix)
    if not os.path.exists(file_path):
        try:
            run_dataset_iterations(dataset_name=dataset_key, max_iteration=max(iteration, 3))
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        file_path = get_output_file(dataset_key, iteration, suffix)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=message)
    return file_path


def list_datasets() -> List[Dict[str, object]]:
    store = get_supabase_store()
    return store.list_datasets()


def top_meals_for_dataset(dataset_key: str) -> list[dict]:
    store = get_supabase_store()
    return store.top_meals(dataset_key)


def build_margin_table(items: List[str]) -> pd.DataFrame:
    store = get_supabase_store()
    reference_map = store.get_margin_map("datasetA")
    if not reference_map:
        dataset_keys = store.list_dataset_keys()
        if dataset_keys:
            reference_map = store.get_margin_map(dataset_keys[0])

    rows = []
    for item in sorted(items):
        if item in reference_map:
            margin = float(reference_map[item])
        else:
            margin = float(12 + (hash(item) % 18))
        rows.append({"item": item, "margin_php": margin})
    return pd.DataFrame(rows)


def _dataset_id_label(dataset_key: str) -> tuple[str, str]:
    labels = {
        "dataseta": ("A", "Dataset A"),
        "datasetb": ("B", "Dataset B"),
        "datasetc": ("C", "Dataset C"),
        "datasetd": ("D", "Dataset D"),
        "datasete": ("E", "Dataset E"),
        "datasetf": ("F", "Dataset F"),
    }
    key = dataset_key.strip()
    mapped = labels.get(key.lower())
    if mapped:
        return mapped
    if key.startswith("custom_"):
        return key, key.replace("custom_", "Custom ").replace("_", " ").title()
    return key, key


def output_dataset_fallback_rows() -> List[Dict[str, object]]:
    if not os.path.isdir(OUTPUT_ROOT):
        return []
    rows: List[Dict[str, object]] = []
    for name in sorted(os.listdir(OUTPUT_ROOT)):
        output_dir = os.path.join(OUTPUT_ROOT, name)
        if not os.path.isdir(output_dir):
            continue
        dataset_id, label = _dataset_id_label(name)
        rows.append(
            {
                "id": dataset_id,
                "folder": name,
                "dataset_key": name,
                "label": label,
                "transactions": 0,
                "unique_items": 0,
            }
        )
    return rows


@app.get("/api/health")
async def health_check():
    try:
        status = get_supabase_store().status()
    except Exception as exc:
        return {
            "ok": False,
            "service": "combobravo-mba",
            "storage": "supabase",
            "detail": str(exc),
        }
    return {"ok": status["ready"], "service": "combobravo-mba", "storage": "supabase", "status": status}


@app.get("/api/supabase/status")
async def supabase_status():
    try:
        return get_supabase_store().status()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/datasets")
async def get_datasets():
    try:
        rows = list_datasets()
        if rows:
            return rows
        fallback = output_dataset_fallback_rows()
        if fallback:
            logger.warning("Supabase returned no datasets; using output-folder fallback.")
            return fallback
        return []
    except Exception as exc:
        logger.exception("Failed to load dataset list")
        fallback = output_dataset_fallback_rows()
        if fallback:
            logger.warning("Using output-folder fallback after dataset API failure: %s", exc)
            return fallback
        raise HTTPException(status_code=500, detail=f"Failed to load dataset list: {exc}") from exc


@app.get("/api/top-meals/{dataset_type}")
async def get_top_meals(dataset_type: str, limit: int = Query(default=10, ge=1, le=100)):
    dataset = resolve_dataset(dataset_type, allow_all=True)
    if dataset == "all":
        counts = Counter()
        for dataset_info in list_datasets():
            dataset_key = str(dataset_info.get("dataset_key") or dataset_info.get("folder") or "")
            if not dataset_key:
                continue
            for row in top_meals_for_dataset(dataset_key):
                counts[row["item"]] += int(row["count"])
        total = sum(counts.values())
        return [
            {
                "item": item,
                "count": int(count),
                "share": float(count / total) if total else 0.0,
            }
            for item, count in counts.most_common(limit)
        ]
    return top_meals_for_dataset(dataset)[:limit]


@app.post("/api/upload-dataset")
async def upload_dataset(file: UploadFile = File(...), dataset_name: str = Form("uploaded")):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a CSV file.")

    try:
        raw_bytes = await file.read()
        dataframe = pd.read_csv(io.BytesIO(raw_bytes))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"CSV parsing failed: {exc}") from exc

    source_column = "items" if "items" in dataframe.columns else "basket" if "basket" in dataframe.columns else None
    if source_column is None:
        raise HTTPException(
            status_code=400,
            detail="CSV must include an 'items' or 'basket' column with comma-separated products.",
        )

    dataframe = dataframe.copy()
    dataframe["items"] = dataframe[source_column].fillna("").astype(str)
    dataframe["items"] = dataframe["items"].apply(lambda value: ", ".join(parse_items(value)))
    dataframe = dataframe[dataframe["items"] != ""].reset_index(drop=True)

    if len(dataframe) < 90:
        raise HTTPException(
            status_code=400,
            detail="Need at least 90 valid transactions for 3 learning iterations.",
        )

    if "timestamp" in dataframe.columns:
        timestamp = pd.to_datetime(dataframe["timestamp"], errors="coerce")
    else:
        timestamp = pd.Series(pd.NaT, index=dataframe.index)

    generated_timestamps = pd.Series(
        pd.date_range(end=pd.Timestamp.now(tz="UTC").floor("min"), periods=len(dataframe), freq="min"),
        index=dataframe.index,
    )
    timestamp = timestamp.fillna(generated_timestamps)
    timestamp = pd.to_datetime(timestamp, utc=True, errors="coerce")
    dataframe["timestamp"] = timestamp.dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    if "segment" not in dataframe.columns:
        hour_values = pd.to_datetime(dataframe["timestamp"], utc=True, errors="coerce").dt.hour.fillna(12)
        dataframe["segment"] = np.where(
            hour_values.between(5, 10),
            "morning",
            np.where(hour_values.between(11, 16), "lunch", "dinner"),
        )
    else:
        normalized_segment = dataframe["segment"].fillna("").astype(str).str.lower().str.strip()
        dataframe["segment"] = normalized_segment.where(
            normalized_segment.isin({"morning", "lunch", "dinner"}), "lunch"
        )

    if "day_type" not in dataframe.columns:
        day_index = pd.to_datetime(dataframe["timestamp"], utc=True, errors="coerce").dt.dayofweek.fillna(0)
        dataframe["day_type"] = np.where(day_index >= 5, "weekend", "weekday")
    else:
        normalized_day = dataframe["day_type"].fillna("").astype(str).str.lower().str.strip()
        dataframe["day_type"] = normalized_day.where(
            normalized_day.isin({"weekday", "weekend"}), "weekday"
        )

    dataframe["tx_id"] = np.arange(1, len(dataframe) + 1)
    dataframe["batch_no"] = 1
    splits = np.array_split(dataframe.index.to_numpy(), 3)
    for index, split_idx in enumerate(splits, start=1):
        dataframe.loc[split_idx, "batch_no"] = index

    dataframe = dataframe[["tx_id", "timestamp", "segment", "day_type", "items", "batch_no"]]

    dataset_key = sanitize_dataset_name(dataset_name)
    label = dataset_name.strip() or dataset_key.replace("custom_", "Custom ").replace("_", " ").title()

    unique_items = sorted({item for raw in dataframe["items"].tolist() for item in parse_items(raw)})
    margin_df = build_margin_table(unique_items)

    store = get_supabase_store()
    status = store.status()
    if not status["ready"]:
        raise HTTPException(
            status_code=400,
            detail=(
                "Supabase tables are not ready. Run backend/sql/supabase_schema.sql in Supabase SQL Editor first. "
                f"Status: {status}"
            ),
        )

    try:
        store.replace_dataset_data(
            dataset_key=dataset_key,
            label=label,
            transactions_df=dataframe,
            margins_df=margin_df,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to write dataset to Supabase. Ensure schema is installed: {exc}",
        ) from exc

    try:
        report = run_dataset_iterations(dataset_name=dataset_key, max_iteration=3)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "message": "Dataset uploaded to Supabase and processed.",
        "dataset_id": dataset_key,
        "transactions": int(len(dataframe)),
        "unique_items": int(len(unique_items)),
        "report": report,
    }


@app.post("/api/run/{dataset_type}")
async def run_dataset(dataset_type: str, max_iteration: int = Query(default=3, ge=1, le=6)):
    dataset = resolve_dataset(dataset_type)
    try:
        report = run_dataset_iterations(dataset_name=dataset, max_iteration=max_iteration)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"dataset": dataset, "report": report}


@app.post("/api/run-all")
async def run_all(max_iteration: int = Query(default=3, ge=1, le=6)):
    return run_all_datasets(max_iteration=max_iteration)


@app.get("/api/recommendations/{dataset_type}/{iteration}")
async def get_recommendations(dataset_type: str, iteration: int):
    dataset = resolve_dataset(dataset_type)
    file_path = ensure_output_exists(dataset, iteration, "recs.json", "Recommendation file not found")
    with open(file_path, "r", encoding="utf-8") as handle:
        return json.load(handle)


@app.get("/api/rules/{dataset_type}/{iteration}")
async def get_rules(
    dataset_type: str, iteration: int, limit: int = Query(default=40, ge=1, le=300)
):
    dataset = resolve_dataset(dataset_type)
    file_path = ensure_output_exists(dataset, iteration, "rules.csv", "Rules file not found")
    df = pd.read_csv(file_path)
    if df.empty:
        return []
    df = df.replace([np.inf, -np.inf], np.nan).replace({np.nan: None})
    return df.head(limit).to_dict(orient="records")


@app.get("/api/menu-rank/{dataset_type}/{iteration}")
async def get_menu_ranking(dataset_type: str, iteration: int):
    dataset = resolve_dataset(dataset_type)
    file_path = ensure_output_exists(dataset, iteration, "menu_rank.csv", "Ranking file not found")
    df = pd.read_csv(file_path)
    if df.empty:
        return []
    return df.to_dict(orient="records")


@app.get("/api/segments/{dataset_type}/{iteration}")
async def get_segment_snapshot(dataset_type: str, iteration: int):
    dataset = resolve_dataset(dataset_type)
    file_path = ensure_output_exists(
        dataset, iteration, "segment_snapshot.json", "Segment snapshot file not found"
    )
    with open(file_path, "r", encoding="utf-8") as handle:
        return json.load(handle)


@app.get("/api/overview/{dataset_type}/{iteration}")
async def get_overview(dataset_type: str, iteration: int):
    dataset = resolve_dataset(dataset_type)
    recs_path = ensure_output_exists(dataset, iteration, "recs.json", "Recommendation file not found")
    rules_path = ensure_output_exists(dataset, iteration, "rules.csv", "Rules file not found")
    menu_path = ensure_output_exists(dataset, iteration, "menu_rank.csv", "Ranking file not found")
    segment_path = ensure_output_exists(
        dataset, iteration, "segment_snapshot.json", "Segment snapshot file not found"
    )

    with open(recs_path, "r", encoding="utf-8") as handle:
        recs = json.load(handle)
    with open(segment_path, "r", encoding="utf-8") as handle:
        segments = json.load(handle)

    rules = pd.read_csv(rules_path).replace([np.inf, -np.inf], np.nan).replace({np.nan: None})
    menu_rank = pd.read_csv(menu_path)
    return {
        "recommendations": recs,
        "rules": rules.head(120).to_dict(orient="records"),
        "menu_rank": menu_rank.to_dict(orient="records"),
        "segments": segments,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
