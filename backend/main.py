import io
import json
import os
import re
from collections import Counter
from typing import Dict, List

import numpy as np
import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from mba_engine import OUTPUT_ROOT, run_all_datasets, run_dataset_iterations

app = FastAPI(title="ComboBravo MBA API", version="3.0.0")
BASE_DIR = os.path.dirname(__file__)
DATA_ROOT = os.path.join(BASE_DIR, "data")
BASE_DATASET_MAP: Dict[str, str] = {
    "a": "datasetA",
    "dataseta": "datasetA",
    "b": "datasetB",
    "datasetb": "datasetB",
}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def parse_items(raw_items: str) -> List[str]:
    return [piece.strip() for piece in str(raw_items).split(",") if piece.strip()]


def is_dataset_folder(folder_name: str) -> bool:
    folder_path = os.path.join(DATA_ROOT, folder_name)
    if not os.path.isdir(folder_path):
        return False
    return any(name.startswith("batch") and name.endswith(".csv") for name in os.listdir(folder_path))


def resolve_dataset(dataset_type: str, allow_all: bool = False) -> str:
    key = dataset_type.strip()
    lower_key = key.lower()
    if allow_all and lower_key in {"all", "overall"}:
        return "all"
    if lower_key in BASE_DATASET_MAP:
        return BASE_DATASET_MAP[lower_key]
    if is_dataset_folder(key):
        return key

    for folder_name in os.listdir(DATA_ROOT):
        if folder_name.lower() == lower_key and is_dataset_folder(folder_name):
            return folder_name
    raise HTTPException(
        status_code=400,
        detail="Dataset not found. Use A, B, or a valid uploaded dataset id.",
    )


def sanitize_dataset_name(dataset_name: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", dataset_name.strip().lower()).strip("_")
    if not cleaned:
        cleaned = "uploaded"
    return f"custom_{cleaned}"


def get_output_file(dataset_folder: str, iteration: int, suffix: str) -> str:
    return os.path.join(OUTPUT_ROOT, dataset_folder, f"iteration_{iteration}_{suffix}")


def ensure_output_exists(dataset_folder: str, iteration: int, suffix: str, message: str) -> str:
    file_path = get_output_file(dataset_folder, iteration, suffix)
    if not os.path.exists(file_path):
        run_dataset_iterations(dataset_name=dataset_folder, max_iteration=max(iteration, 3))
        file_path = get_output_file(dataset_folder, iteration, suffix)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=message)
    return file_path


def top_meals_for_dataset(dataset_folder: str) -> list[dict]:
    folder = os.path.join(DATA_ROOT, dataset_folder)
    if not os.path.exists(folder):
        return []
    counts = Counter()
    batch_files = sorted([name for name in os.listdir(folder) if name.startswith("batch")])
    for batch in batch_files:
        batch_path = os.path.join(folder, batch)
        df = pd.read_csv(batch_path)
        if "items" not in df.columns:
            continue
        for raw_items in df["items"].fillna("").tolist():
            for item in parse_items(raw_items):
                counts[item] += 1
    total = sum(counts.values())
    return [
        {
            "item": item,
            "count": int(count),
            "share": float(count / total) if total else 0.0,
        }
        for item, count in counts.most_common()
    ]


def dataset_stats(dataset_folder: str) -> Dict[str, object]:
    folder = os.path.join(DATA_ROOT, dataset_folder)
    batch_files = sorted([name for name in os.listdir(folder) if name.startswith("batch")])
    tx_count = 0
    unique_items = set()
    for batch in batch_files:
        df = pd.read_csv(os.path.join(folder, batch))
        tx_count += int(len(df))
        if "items" in df.columns:
            for raw_items in df["items"].fillna("").tolist():
                unique_items.update(parse_items(raw_items))
    if dataset_folder == "datasetA":
        dataset_id = "A"
        label = "Dataset A"
    elif dataset_folder == "datasetB":
        dataset_id = "B"
        label = "Dataset B"
    else:
        dataset_id = dataset_folder
        label = dataset_folder.replace("custom_", "Custom ").replace("_", " ").title()

    return {
        "id": dataset_id,
        "folder": dataset_folder,
        "label": label,
        "transactions": tx_count,
        "unique_items": len(unique_items),
    }


def list_datasets() -> List[Dict[str, object]]:
    datasets = []
    for folder_name in os.listdir(DATA_ROOT):
        if is_dataset_folder(folder_name):
            datasets.append(dataset_stats(folder_name))
    datasets.sort(
        key=lambda item: (
            0 if item["folder"] in {"datasetA", "datasetB"} else 1,
            item["label"].lower(),
        )
    )
    return datasets


def build_margin_table(items: List[str]) -> pd.DataFrame:
    reference_path = os.path.join(DATA_ROOT, "datasetA", "margins.csv")
    reference_map: Dict[str, float] = {}
    if os.path.exists(reference_path):
        reference_df = pd.read_csv(reference_path)
        if "item" in reference_df.columns and "margin_php" in reference_df.columns:
            reference_map = dict(zip(reference_df["item"], reference_df["margin_php"]))

    rows = []
    for item in sorted(items):
        if item in reference_map:
            margin = float(reference_map[item])
        else:
            margin = float(12 + (hash(item) % 18))
        rows.append({"item": item, "margin_php": margin})
    return pd.DataFrame(rows)


@app.get("/api/health")
async def health_check():
    return {"ok": True, "service": "combobravo-mba"}


@app.get("/api/datasets")
async def get_datasets():
    return list_datasets()


@app.get("/api/top-meals/{dataset_type}")
async def get_top_meals(dataset_type: str, limit: int = Query(default=10, ge=1, le=100)):
    dataset = resolve_dataset(dataset_type, allow_all=True)
    if dataset == "all":
        counts = Counter()
        for dataset_info in list_datasets():
            for row in top_meals_for_dataset(dataset_info["folder"]):
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
    dataframe["items"] = dataframe["items"].apply(
        lambda value: ", ".join(parse_items(value))
    )
    dataframe = dataframe[dataframe["items"] != ""].reset_index(drop=True)
    if len(dataframe) < 90:
        raise HTTPException(
            status_code=400,
            detail="Need at least 90 valid transactions for 3 learning iterations.",
        )

    if "timestamp" in dataframe.columns:
        dataframe["timestamp"] = pd.to_datetime(dataframe["timestamp"], errors="coerce")
    else:
        dataframe["timestamp"] = pd.NaT
    generated_timestamps = pd.Series(
        pd.date_range(end=pd.Timestamp.utcnow().floor("min"), periods=len(dataframe), freq="min"),
        index=dataframe.index,
    )
    dataframe["timestamp"] = dataframe["timestamp"].fillna(generated_timestamps)
    dataframe["timestamp"] = dataframe["timestamp"].astype(str)

    if "segment" not in dataframe.columns:
        hour_values = pd.to_datetime(dataframe["timestamp"]).dt.hour
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
        day_index = pd.to_datetime(dataframe["timestamp"]).dt.dayofweek
        dataframe["day_type"] = np.where(day_index >= 5, "weekend", "weekday")
    else:
        normalized_day = dataframe["day_type"].fillna("").astype(str).str.lower().str.strip()
        dataframe["day_type"] = normalized_day.where(
            normalized_day.isin({"weekday", "weekend"}), "weekday"
        )

    dataframe["tx_id"] = np.arange(1, len(dataframe) + 1)
    dataframe = dataframe[["tx_id", "timestamp", "segment", "day_type", "items"]]

    dataset_folder = sanitize_dataset_name(dataset_name)
    dataset_dir = os.path.join(DATA_ROOT, dataset_folder)
    os.makedirs(dataset_dir, exist_ok=True)

    splits = np.array_split(dataframe, 3)
    for index, split_df in enumerate(splits, start=1):
        split_df.to_csv(os.path.join(dataset_dir, f"batch{index}.csv"), index=False)

    unique_items = sorted({item for raw in dataframe["items"].tolist() for item in parse_items(raw)})
    margin_df = build_margin_table(unique_items)
    margin_df.to_csv(os.path.join(dataset_dir, "margins.csv"), index=False)

    report = run_dataset_iterations(dataset_name=dataset_folder, max_iteration=3)
    return {
        "message": "Dataset uploaded and processed.",
        "dataset_id": dataset_folder,
        "transactions": int(len(dataframe)),
        "unique_items": int(len(unique_items)),
        "report": report,
    }


@app.post("/api/run/{dataset_type}")
async def run_dataset(dataset_type: str, max_iteration: int = Query(default=3, ge=1, le=6)):
    dataset = resolve_dataset(dataset_type)
    report = run_dataset_iterations(dataset_name=dataset, max_iteration=max_iteration)
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
