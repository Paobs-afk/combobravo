import io
import json
import logging
import os
import re
import shutil
from collections import Counter
from typing import Dict, List

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from mba_engine import CHARTS_SUBDIR, OUTPUT_ROOT, run_all_datasets, run_dataset_iterations
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
    # always normalize the familiar overall/all alias to our internal "all" token
    if lower_key in {"all", "overall"}:
        return "all"

    if allow_all and lower_key == "all":
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
                "batch_count": 0,
            }
        )
    return rows


def dataset_keys_from_registry() -> List[str]:
    try:
        rows = list_datasets()
    except Exception:
        rows = output_dataset_fallback_rows()

    keys: List[str] = []
    for row in rows:
        key = str(row.get("dataset_key") or row.get("folder") or "").strip()
        if key:
            keys.append(key)
    return keys


def normalize_chart_filename(file_name: str) -> str:
    trimmed = os.path.basename((file_name or "").strip())
    if not trimmed:
        raise HTTPException(status_code=400, detail="Chart file name is required.")
    if trimmed != file_name:
        raise HTTPException(status_code=400, detail="Invalid chart file path.")
    if not trimmed.lower().endswith(".png"):
        raise HTTPException(status_code=400, detail="Only PNG chart files are supported.")
    return trimmed


def chart_manifest_for_dataset(dataset_key: str, iteration: int) -> List[Dict[str, str]]:
    manifest_path = ensure_output_exists(
        dataset_key=dataset_key,
        iteration=iteration,
        suffix="charts.json",
        message="Chart manifest not found.",
    )
    with open(manifest_path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload if isinstance(payload, list) else []


def _clear_chart_dir(chart_dir: str) -> None:
    os.makedirs(chart_dir, exist_ok=True)
    for file_name in os.listdir(chart_dir):
        if file_name.lower().endswith(".png"):
            try:
                os.remove(os.path.join(chart_dir, file_name))
            except OSError:
                continue


def _overall_chart_entry(iteration: int, file_name: str, title: str, description: str) -> Dict[str, str]:
    return {
        "id": file_name.replace(".png", ""),
        "title": title,
        "description": description,
        "file": file_name,
        "url": f"/api/chart-image/all/{iteration}/{file_name}",
    }


def compute_iteration_history_rows(dataset: str, max_iteration: int) -> List[Dict[str, object]]:
    if dataset == "all":
        dataset_keys = dataset_keys_from_registry()
        rows: List[Dict[str, object]] = []
        for iteration in range(1, max_iteration + 1):
            per_dataset_rows: List[Dict[str, object]] = []
            for key in dataset_keys:
                try:
                    recs_path = ensure_output_exists(
                        key, iteration, "recs.json", "Recommendation file not found"
                    )
                    with open(recs_path, "r", encoding="utf-8") as handle:
                        recs = json.load(handle)
                    per_dataset_rows.append(_extract_history_row(recs, iteration))
                except Exception:
                    continue

            if not per_dataset_rows:
                continue
            total_tx = sum(int(row["transactions"]) for row in per_dataset_rows)
            weighted_denominator = float(total_tx or len(per_dataset_rows))
            weighted_coverage = sum(
                float(row["coverage_top_rules"]) * float(row["transactions"])
                for row in per_dataset_rows
            ) / weighted_denominator
            weighted_uplift = sum(
                float(row["estimated_uplift_score"]) * float(row["transactions"])
                for row in per_dataset_rows
            ) / weighted_denominator
            weighted_drift = sum(
                float(row["drift_js"]) * float(row["transactions"])
                for row in per_dataset_rows
            ) / weighted_denominator
            rows.append(
                {
                    "iteration": iteration,
                    "transactions": int(total_tx),
                    "unique_items": int(
                        sum(int(row["unique_items"]) for row in per_dataset_rows)
                    ),
                    "coverage_top_rules": float(weighted_coverage),
                    "estimated_uplift_score": float(weighted_uplift),
                    "n_rules_blended": int(
                        sum(int(row["n_rules_blended"]) for row in per_dataset_rows)
                    ),
                    "drift_js": float(weighted_drift),
                    "engine_longterm": "mixed",
                    "minsup_longterm": float(
                        np.mean([float(row["minsup_longterm"]) for row in per_dataset_rows])
                    ),
                    "minconf_longterm": float(
                        np.mean([float(row["minconf_longterm"]) for row in per_dataset_rows])
                    ),
                }
            )
        return rows

    rows = []
    for iteration in range(1, max_iteration + 1):
        try:
            recs_path = ensure_output_exists(
                dataset, iteration, "recs.json", "Recommendation file not found"
            )
            with open(recs_path, "r", encoding="utf-8") as handle:
                recs = json.load(handle)
            rows.append(_extract_history_row(recs, iteration))
        except Exception:
            continue
    return rows


def build_overall_chart_manifest(iteration: int) -> List[Dict[str, str]]:
    iteration = max(int(iteration), 1)
    out_dir = os.path.join(OUTPUT_ROOT, "all")
    chart_dir = os.path.join(out_dir, CHARTS_SUBDIR, f"iteration_{iteration}")
    _clear_chart_dir(chart_dir)
    os.makedirs(out_dir, exist_ok=True)

    chart_manifest: List[Dict[str, str]] = []
    chart_dpi = 130
    store = get_supabase_store()
    dataset_keys = dataset_keys_from_registry()

    all_baskets: List[List[str]] = []
    segment_counts = Counter()
    rules_frames: List[pd.DataFrame] = []
    menu_frames: List[pd.DataFrame] = []

    for key in dataset_keys:
        try:
            tx_df = store.load_transactions_for_iteration(key, iteration)
            if not tx_df.empty:
                baskets = tx_df.get("basket")
                if baskets is not None:
                    for basket in baskets.tolist():
                        if isinstance(basket, list):
                            cleaned = [str(item).strip() for item in basket if str(item).strip()]
                        else:
                            cleaned = parse_items(str(basket))
                        if cleaned:
                            all_baskets.append(cleaned)

                if "segment" in tx_df.columns:
                    normalized_segment = (
                        tx_df["segment"]
                        .fillna("unknown")
                        .astype(str)
                        .str.lower()
                        .str.strip()
                    )
                    segment_counts.update(normalized_segment.tolist())
        except Exception:
            continue

        try:
            rules_path = ensure_output_exists(key, iteration, "rules.csv", "Rules file not found")
            rules_df = pd.read_csv(rules_path)
            if not rules_df.empty:
                rules_frames.append(rules_df)
        except Exception:
            pass

        try:
            menu_path = ensure_output_exists(key, iteration, "menu_rank.csv", "Ranking file not found")
            menu_df = pd.read_csv(menu_path)
            if not menu_df.empty:
                menu_frames.append(menu_df)
        except Exception:
            pass

    item_counts = Counter(item for basket in all_baskets for item in basket)
    top_items = item_counts.most_common(12)
    if top_items:
        fig, axis = plt.subplots(figsize=(9.5, 4.8))
        labels = [item for item, _ in top_items][::-1]
        values = [count for _, count in top_items][::-1]
        axis.barh(labels, values, color="#d94841", edgecolor="#7f1d1d")
        axis.set_title("Overall Top Items by Purchase Count")
        axis.set_xlabel("Purchases")
        axis.set_ylabel("Item")
        axis.grid(axis="x", alpha=0.2)
        file_name = "top_items.png"
        fig.tight_layout()
        fig.savefig(os.path.join(chart_dir, file_name), dpi=chart_dpi)
        plt.close(fig)
        chart_manifest.append(
            _overall_chart_entry(
                iteration=iteration,
                file_name=file_name,
                title="Overall Top Items",
                description="Most purchased items across all datasets in this iteration.",
            )
        )

    if rules_frames:
        all_rules = pd.concat(rules_frames, ignore_index=True)
        for metric in ["support", "confidence", "lift", "blend_score"]:
            if metric not in all_rules.columns:
                all_rules[metric] = 0.0
            all_rules[metric] = pd.to_numeric(all_rules[metric], errors="coerce").replace(
                [np.inf, -np.inf], np.nan
            ).fillna(0.0)
        sampled = all_rules.sort_values("support", ascending=False).head(180).copy()
        if not sampled.empty:
            bubble_sizes = 80 + (sampled["support"].to_numpy() * 2600)
            fig, axis = plt.subplots(figsize=(9.5, 4.8))
            scatter = axis.scatter(
                sampled["confidence"].to_numpy(),
                sampled["lift"].to_numpy(),
                s=bubble_sizes,
                c=sampled["blend_score"].to_numpy(),
                cmap="YlOrRd",
                alpha=0.75,
                edgecolors="#6b1f1f",
                linewidths=0.4,
            )
            axis.set_title("Overall Rule Quality Map")
            axis.set_xlabel("Confidence")
            axis.set_ylabel("Lift")
            axis.grid(alpha=0.2)
            fig.colorbar(scatter, ax=axis, label="Blend score")
            file_name = "rule_quality.png"
            fig.tight_layout()
            fig.savefig(os.path.join(chart_dir, file_name), dpi=chart_dpi)
            plt.close(fig)
            chart_manifest.append(
                _overall_chart_entry(
                    iteration=iteration,
                    file_name=file_name,
                    title="Overall Rule Quality",
                    description="Confidence vs lift across all datasets with support-sized bubbles.",
                )
            )

    ordered_segments = ["morning", "lunch", "dinner"]
    segment_values = [int(segment_counts.get(name, 0)) for name in ordered_segments]
    if sum(segment_values) > 0:
        fig, axis = plt.subplots(figsize=(8.6, 4.8))
        axis.bar(
            ordered_segments,
            segment_values,
            color=["#f59e0b", "#ef4444", "#6366f1"],
            edgecolor="#1f2937",
            linewidth=0.4,
        )
        axis.set_title("Overall Transaction Mix by Segment")
        axis.set_xlabel("Segment")
        axis.set_ylabel("Transactions")
        axis.grid(axis="y", alpha=0.2)
        file_name = "segment_mix.png"
        fig.tight_layout()
        fig.savefig(os.path.join(chart_dir, file_name), dpi=chart_dpi)
        plt.close(fig)
        chart_manifest.append(
            _overall_chart_entry(
                iteration=iteration,
                file_name=file_name,
                title="Overall Segment Mix",
                description="Distribution of morning, lunch, and dinner transactions across all datasets.",
            )
        )

    if menu_frames:
        all_menu = pd.concat(menu_frames, ignore_index=True)
        if "item" in all_menu.columns:
            for metric in ["pop", "impact", "rank_score"]:
                if metric not in all_menu.columns:
                    all_menu[metric] = 0.0
                all_menu[metric] = pd.to_numeric(all_menu[metric], errors="coerce").replace(
                    [np.inf, -np.inf], np.nan
                ).fillna(0.0)
            agg_menu = (
                all_menu.groupby("item", as_index=False)
                .agg(pop=("pop", "mean"), impact=("impact", "mean"), rank_score=("rank_score", "mean"))
                .sort_values("rank_score", ascending=False)
                .head(10)
            )
            if not agg_menu.empty:
                fig, axis = plt.subplots(figsize=(9.5, 4.8))
                axis.plot(
                    agg_menu["item"].astype(str).tolist(),
                    agg_menu["rank_score"].tolist(),
                    marker="o",
                    color="#b91c1c",
                    linewidth=2.2,
                )
                axis.set_title("Overall Homepage Rank Score by Item")
                axis.set_xlabel("Item")
                axis.set_ylabel("Rank score")
                axis.tick_params(axis="x", rotation=32)
                axis.grid(axis="y", alpha=0.2)
                file_name = "homepage_rank_curve.png"
                fig.tight_layout()
                fig.savefig(os.path.join(chart_dir, file_name), dpi=chart_dpi)
                plt.close(fig)
                chart_manifest.append(
                    _overall_chart_entry(
                        iteration=iteration,
                        file_name=file_name,
                        title="Overall Homepage Ranking Curve",
                        description="Averaged rank score for top homepage candidates across all datasets.",
                    )
                )

    history_rows = compute_iteration_history_rows("all", iteration)
    if history_rows:
        history_df = pd.DataFrame(history_rows).sort_values("iteration")
        if not history_df.empty:
            fig, axes = plt.subplots(1, 2, figsize=(11.2, 4.7))
            axes[0].plot(
                history_df["iteration"],
                history_df["coverage_top_rules"],
                marker="o",
                label="Coverage",
                color="#dc2626",
                linewidth=2.0,
            )
            axes[0].plot(
                history_df["iteration"],
                history_df["estimated_uplift_score"],
                marker="s",
                label="Uplift",
                color="#2563eb",
                linewidth=2.0,
            )
            axes[0].set_title("Overall Coverage and Uplift Trend")
            axes[0].set_xlabel("Iteration")
            axes[0].set_ylabel("Metric value")
            axes[0].set_xticks(history_df["iteration"].tolist())
            axes[0].set_ylim(bottom=0)
            axes[0].grid(alpha=0.2)
            axes[0].legend()

            axes[1].bar(
                history_df["iteration"].tolist(),
                history_df["n_rules_blended"].tolist(),
                color="#f97316",
                edgecolor="#7c2d12",
            )
            axes[1].plot(
                history_df["iteration"].tolist(),
                history_df["drift_js"].tolist(),
                marker="D",
                color="#0f766e",
                linewidth=2.0,
                label="Drift (JS)",
            )
            axes[1].set_title("Overall Rule Count and Drift")
            axes[1].set_xlabel("Iteration")
            axes[1].set_ylabel("Count / drift")
            axes[1].set_xticks(history_df["iteration"].tolist())
            axes[1].set_ylim(bottom=0)
            axes[1].grid(alpha=0.2)
            axes[1].legend()

            file_name = "iteration_trend.png"
            fig.tight_layout()
            fig.savefig(os.path.join(chart_dir, file_name), dpi=chart_dpi)
            plt.close(fig)
            chart_manifest.append(
                _overall_chart_entry(
                    iteration=iteration,
                    file_name=file_name,
                    title="Overall Iteration Trend",
                    description="Coverage, uplift, rule count, and drift trends merged across datasets.",
                )
            )

    manifest_path = os.path.join(out_dir, f"iteration_{iteration}_charts.json")
    with open(manifest_path, "w", encoding="utf-8") as handle:
        json.dump(chart_manifest, handle, indent=2, ensure_ascii=False)
    return chart_manifest


def _extract_history_row(recs: Dict[str, object], iteration: int) -> Dict[str, object]:
    metrics = recs.get("system_metrics") or {}
    drift = recs.get("drift") or {}
    return {
        "iteration": int(iteration),
        "transactions": int(recs.get("n_transactions", 0) or 0),
        "unique_items": int(recs.get("n_unique_items", 0) or 0),
        "coverage_top_rules": float(metrics.get("coverage_top_rules", 0.0) or 0.0),
        "estimated_uplift_score": float(metrics.get("estimated_uplift_score", 0.0) or 0.0),
        "n_rules_blended": int(metrics.get("n_rules_blended", 0) or 0),
        "drift_js": float(drift.get("js", 0.0) or 0.0),
        "engine_longterm": str(recs.get("engine_longterm", "-") or "-"),
        "minsup_longterm": float(recs.get("minsup_longterm", 0.0) or 0.0),
        "minconf_longterm": float(recs.get("minconf_longterm", 0.0) or 0.0),
    }


async def parse_uploaded_csv(upload: UploadFile) -> pd.DataFrame:
    if not upload.filename or not upload.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail=f"File '{upload.filename}' is not a CSV.")

    try:
        raw_bytes = await upload.read()
        dataframe = pd.read_csv(io.BytesIO(raw_bytes))
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"CSV parsing failed for '{upload.filename}': {exc}",
        ) from exc

    source_column = "items" if "items" in dataframe.columns else "basket" if "basket" in dataframe.columns else None
    if source_column is None:
        raise HTTPException(
            status_code=400,
            detail=(
                f"CSV '{upload.filename}' must include an 'items' or 'basket' column with comma-separated products."
            ),
        )

    dataframe = dataframe.copy()
    dataframe["items"] = dataframe[source_column].fillna("").astype(str)
    dataframe["items"] = dataframe["items"].apply(lambda value: ", ".join(parse_items(value)))
    dataframe = dataframe[dataframe["items"] != ""].reset_index(drop=True)
    return dataframe


@app.get("/api/health")
async def health_check():
    try:
        status = get_supabase_store().status()
    except Exception as exc:
        return {
            "ok": False,
            "service": "combobravo-mba",
            "storage": "unknown",
            "detail": str(exc),
        }
    return {
        "ok": bool(status.get("ready")),
        "service": "combobravo-mba",
        "storage": status.get("storage", "supabase"),
        "status": status,
    }


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


@app.delete("/api/datasets/{dataset_type}")
async def delete_dataset(dataset_type: str):
    dataset_key = resolve_dataset(dataset_type, allow_all=False)
    if dataset_key == "all":
        raise HTTPException(status_code=400, detail="Cannot delete the 'all' aggregate option.")

    store = get_supabase_store()
    try:
        store.delete_dataset(dataset_key)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to delete dataset '{dataset_key}': {exc}") from exc

    output_dir = os.path.join(OUTPUT_ROOT, dataset_key)
    if os.path.isdir(output_dir):
        shutil.rmtree(output_dir, ignore_errors=True)

    return {"message": f"Dataset '{dataset_key}' deleted.", "dataset_id": dataset_key}


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
async def upload_dataset(
    files: List[UploadFile] | None = File(default=None),
    file: UploadFile | None = File(default=None),
    dataset_name: str = Form("uploaded"),
    upload_mode: str = Form("replace"),
):
    mode = (upload_mode or "replace").strip().lower()
    if mode not in {"replace", "append"}:
        raise HTTPException(status_code=400, detail="upload_mode must be 'replace' or 'append'.")

    upload_files: List[UploadFile] = list(files or [])
    if file is not None:
        upload_files.append(file)
    if not upload_files:
        raise HTTPException(status_code=400, detail="Please upload at least one CSV file.")

    cleaned_batches: List[pd.DataFrame] = []
    skipped_files: List[str] = []
    for index, upload in enumerate(upload_files, start=1):
        frame = await parse_uploaded_csv(upload)
        if frame.empty:
            skipped_files.append(upload.filename or f"batch{index}")
            continue
        frame["batch_no"] = index
        cleaned_batches.append(frame)

    if not cleaned_batches:
        raise HTTPException(
            status_code=400,
            detail="All uploaded CSV files are empty after cleaning.",
        )

    dataframe = pd.concat(cleaned_batches, ignore_index=True)
    new_transactions_count = int(len(dataframe))

    unique_batches = sorted(pd.to_numeric(dataframe["batch_no"], errors="coerce").dropna().astype(int).unique())
    batch_map = {old: idx for idx, old in enumerate(unique_batches, start=1)}
    dataframe["batch_no"] = pd.to_numeric(dataframe["batch_no"], errors="coerce").fillna(1).astype(int)
    dataframe["batch_no"] = dataframe["batch_no"].map(batch_map).fillna(1).astype(int)

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

    dataset_key = sanitize_dataset_name(dataset_name)
    label = dataset_name.strip() or dataset_key.replace("custom_", "Custom ").replace("_", " ").title()

    store = get_supabase_store()
    status = store.status()
    if not status["ready"]:
        raise HTTPException(
            status_code=400,
            detail=f"Storage is not ready for upload. Status: {status}",
        )

    starting_batch = 1
    if mode == "append":
        matched = store.get_dataset_key_case_insensitive(dataset_key)
        if matched:
            dataset_key = matched
        existing_df = store.load_transactions_for_iteration(
            dataset_key, iteration=999, include_batch_no=True
        )
        if not existing_df.empty:
            existing_df = existing_df[["timestamp", "segment", "day_type", "items", "batch_no"]].copy()
            existing_df["batch_no"] = pd.to_numeric(existing_df["batch_no"], errors="coerce").fillna(1).astype(int)
            starting_batch = int(existing_df["batch_no"].max()) + 1
            dataframe["batch_no"] = (
                pd.to_numeric(dataframe["batch_no"], errors="coerce").fillna(1).astype(int) + (starting_batch - 1)
            )
            dataframe = pd.concat(
                [existing_df, dataframe[["timestamp", "segment", "day_type", "items", "batch_no"]]],
                ignore_index=True,
            )
        else:
            dataframe["batch_no"] = pd.to_numeric(dataframe["batch_no"], errors="coerce").fillna(1).astype(int)

    if len(dataframe) < 90:
        raise HTTPException(
            status_code=400,
            detail="Need at least 90 total valid transactions for learning iterations.",
        )

    dataframe["tx_id"] = np.arange(1, len(dataframe) + 1)
    dataframe = dataframe[["tx_id", "timestamp", "segment", "day_type", "items", "batch_no"]]

    unique_items = sorted({item for raw in dataframe["items"].tolist() for item in parse_items(raw)})
    margin_df = build_margin_table(unique_items)
    if mode == "append":
        existing_margin_map = store.get_margin_map(dataset_key)
        if existing_margin_map:
            margin_df["margin_php"] = margin_df.apply(
                lambda row: float(existing_margin_map.get(str(row["item"]), row["margin_php"])),
                axis=1,
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
        trained_iterations = max(3, int(pd.to_numeric(dataframe["batch_no"], errors="coerce").max() or 0))
        report = run_dataset_iterations(dataset_name=dataset_key, max_iteration=trained_iterations)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    response_payload = {
        "message": "Dataset uploaded and processed.",
        "dataset_id": dataset_key,
        "transactions": int(len(dataframe)),
        "new_transactions": int(new_transactions_count),
        "unique_items": int(len(unique_items)),
        "batch_count": int(dataframe["batch_no"].max()),
        "trained_iterations": int(trained_iterations),
        "uploaded_file_count": int(len(upload_files)),
        "upload_mode": mode,
        "starting_batch": int(starting_batch),
        "report": report,
    }
    if skipped_files:
        response_payload["skipped_files"] = skipped_files
    return response_payload


@app.post("/api/run/{dataset_type}")
async def run_dataset(dataset_type: str, max_iteration: int = Query(default=3, ge=1, le=60)):
    dataset = resolve_dataset(dataset_type, allow_all=True)
    try:
        if dataset == "all":
            # run all datasets in the workspace
            report = run_all_datasets(max_iteration=max_iteration)
        else:
            report = run_dataset_iterations(dataset_name=dataset, max_iteration=max_iteration)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"dataset": dataset, "report": report}


@app.post("/api/run-all")
async def run_all(max_iteration: int = Query(default=3, ge=1, le=60)):
    return run_all_datasets(max_iteration=max_iteration)


@app.get("/api/charts/{dataset_type}/{iteration}")
async def get_charts(dataset_type: str, iteration: int):
    dataset = resolve_dataset(dataset_type, allow_all=True)
    if dataset == "all":
        charts = build_overall_chart_manifest(iteration)
        return {"dataset": "all", "iteration": iteration, "charts": charts}

    charts = chart_manifest_for_dataset(dataset, iteration)
    return {"dataset": dataset, "iteration": iteration, "charts": charts}


@app.get("/api/chart-image/{dataset_type}/{iteration}/{file_name}")
async def get_chart_image(dataset_type: str, iteration: int, file_name: str):
    dataset = resolve_dataset(dataset_type, allow_all=True)
    safe_name = normalize_chart_filename(file_name)
    chart_path = os.path.join(
        OUTPUT_ROOT,
        dataset,
        CHARTS_SUBDIR,
        f"iteration_{iteration}",
        safe_name,
    )
    if dataset == "all":
        if not os.path.exists(chart_path):
            build_overall_chart_manifest(iteration)
    elif not os.path.exists(chart_path):
        chart_manifest_for_dataset(dataset, iteration)
    if not os.path.exists(chart_path):
        raise HTTPException(status_code=404, detail="Chart image not found.")
    return FileResponse(chart_path, media_type="image/png")


@app.get("/api/iteration-history/{dataset_type}")
async def get_iteration_history(
    dataset_type: str, max_iteration: int = Query(default=3, ge=1, le=60)
):
    dataset = resolve_dataset(dataset_type, allow_all=True)
    return compute_iteration_history_rows(dataset, max_iteration)


@app.get("/api/recommendations/{dataset_type}/{iteration}")
async def get_recommendations(dataset_type: str, iteration: int):
    # recommendations endpoint now understands the overall alias as well
    dataset = resolve_dataset(dataset_type, allow_all=True)
    if dataset == "all":
        # simply aggregate by summing numeric values across all datasets so callers
        # get something useful rather than an error.
        agg: Dict[str, object] = {}
        for info in list_datasets():
            key = str(info.get("dataset_key") or info.get("folder") or "").strip()
            if not key:
                continue
            try:
                path = ensure_output_exists(key, iteration, "recs.json", "Recommendation file not found")
                with open(path, "r", encoding="utf-8") as h:
                    recs = json.load(h)
                for k, v in recs.items():
                    if isinstance(v, (int, float)):
                        agg[k] = agg.get(k, 0) + v
                    else:
                        agg[k] = v
            except Exception:
                continue
        return agg

    file_path = ensure_output_exists(dataset, iteration, "recs.json", "Recommendation file not found")
    with open(file_path, "r", encoding="utf-8") as handle:
        return json.load(handle)


@app.get("/api/rules/{dataset_type}/{iteration}")
async def get_rules(
    dataset_type: str, iteration: int, limit: int = Query(default=40, ge=1, le=300)
):
    dataset = resolve_dataset(dataset_type, allow_all=True)
    if dataset == "all":
        frames = []
        for info in list_datasets():
            key = str(info.get("dataset_key") or info.get("folder") or "").strip()
            if not key:
                continue
            try:
                file_path = ensure_output_exists(key, iteration, "rules.csv", "Rules file not found")
                df = pd.read_csv(file_path)
                frames.append(df)
            except Exception:
                continue
        if not frames:
            return []
        df_all = pd.concat(frames, ignore_index=True)
        df_all = df_all.replace([np.inf, -np.inf], np.nan).replace({np.nan: None})
        return df_all.head(limit).to_dict(orient="records")

    file_path = ensure_output_exists(dataset, iteration, "rules.csv", "Rules file not found")
    df = pd.read_csv(file_path)
    if df.empty:
        return []
    df = df.replace([np.inf, -np.inf], np.nan).replace({np.nan: None})
    return df.head(limit).to_dict(orient="records")


@app.get("/api/menu-rank/{dataset_type}/{iteration}")
async def get_menu_ranking(dataset_type: str, iteration: int):
    dataset = resolve_dataset(dataset_type, allow_all=True)
    if dataset == "all":
        frames = []
        for info in list_datasets():
            key = str(info.get("dataset_key") or info.get("folder") or "").strip()
            if not key:
                continue
            try:
                file_path = ensure_output_exists(key, iteration, "menu_rank.csv", "Ranking file not found")
                frames.append(pd.read_csv(file_path))
            except Exception:
                continue
        if not frames:
            return []
        all_menu = pd.concat(frames, ignore_index=True)
        return all_menu.to_dict(orient="records")

    file_path = ensure_output_exists(dataset, iteration, "menu_rank.csv", "Ranking file not found")
    df = pd.read_csv(file_path)
    if df.empty:
        return []
    return df.to_dict(orient="records")


@app.get("/api/segments/{dataset_type}/{iteration}")
async def get_segment_snapshot(dataset_type: str, iteration: int):
    dataset = resolve_dataset(dataset_type, allow_all=True)
    if dataset == "all":
        merged: Dict[str, Dict[str, object]] = {}
        for info in list_datasets():
            key = str(info.get("dataset_key") or info.get("folder") or "").strip()
            if not key:
                continue
            try:
                file_path = ensure_output_exists(
                    key, iteration, "segment_snapshot.json", "Segment snapshot file not found"
                )
                with open(file_path, "r", encoding="utf-8") as handle:
                    segmap = json.load(handle)
                for name, data in segmap.items():
                    if name not in merged:
                        merged[name] = data.copy()
                    else:
                        existing = merged[name]
                        old_n = existing.get("n_tx", 0) or 0
                        new_n = data.get("n_tx", 0) or 0
                        total = old_n + new_n
                        existing["n_tx"] = total
                        for field in ["holdout_mean_hr", "minsup", "minconf"]:
                            if field in existing and field in data:
                                existing[field] = (
                                    existing.get(field, 0) * old_n + data.get(field, 0) * new_n
                                ) / (total or 1)
            except Exception:
                continue
        return merged

    file_path = ensure_output_exists(
        dataset, iteration, "segment_snapshot.json", "Segment snapshot file not found"
    )
    with open(file_path, "r", encoding="utf-8") as handle:
        return json.load(handle)


@app.get("/api/overview/{dataset_type}/{iteration}")
async def get_overview(dataset_type: str, iteration: int):
    dataset = resolve_dataset(dataset_type, allow_all=True)

    if dataset == "all":
        # aggregate across every known dataset
        all_keys = []
        for info in list_datasets():
            key = str(info.get("dataset_key") or info.get("folder") or "").strip()
            if key:
                all_keys.append(key)

        # helper containers
        recs_list = []
        rules_frames = []
        menu_frames = []
        segment_maps = []

        for key in all_keys:
            try:
                rec_path = ensure_output_exists(
                    key, iteration, "recs.json", "Recommendation file not found for %s" % key
                )
                with open(rec_path, "r", encoding="utf-8") as h:
                    recs_list.append(json.load(h))
                rules_path = ensure_output_exists(
                    key, iteration, "rules.csv", "Rules file not found for %s" % key
                )
                df_rules = pd.read_csv(rules_path).replace([np.inf, -np.inf], np.nan).replace({np.nan: None})
                rules_frames.append(df_rules)
                menu_path = ensure_output_exists(
                    key, iteration, "menu_rank.csv", "Ranking file not found for %s" % key
                )
                menu_frames.append(pd.read_csv(menu_path))
                seg_path = ensure_output_exists(
                    key, iteration, "segment_snapshot.json", "Segment snapshot file not found for %s" % key
                )
                with open(seg_path, "r", encoding="utf-8") as h:
                    segment_maps.append(json.load(h))
            except Exception:
                # skip datasets that haven't been trained yet
                continue

        # aggregate recommendations (numeric sums, others keep last)
        aggregated_recs: Dict[str, object] = {}
        for recs in recs_list:
            for k, v in recs.items():
                if isinstance(v, (int, float)):
                    aggregated_recs[k] = aggregated_recs.get(k, 0) + v
                else:
                    aggregated_recs[k] = v

        # aggregate rules, menu, segments
        if rules_frames:
            all_rules = pd.concat(rules_frames, ignore_index=True)
            all_rules = all_rules.replace([np.inf, -np.inf], np.nan).replace({np.nan: None})
            aggregated_rules = all_rules.sort_values("support", ascending=False).head(120).to_dict(orient="records")
        else:
            aggregated_rules = []

        if menu_frames:
            all_menu = pd.concat(menu_frames, ignore_index=True)
            agg_menu = (
                all_menu.groupby("item", as_index=False)
                .agg(pop=("pop", "mean"), impact=("impact", "mean"), rank_score=("rank_score", "mean"))
            )
            aggregated_menu_rank = agg_menu.sort_values("rank_score", ascending=False).to_dict(orient="records")
        else:
            aggregated_menu_rank = []

        # merge segments by name, summing n_tx and averaging some metrics
        aggregated_segments: Dict[str, Dict[str, object]] = {}
        for segmap in segment_maps:
            for name, data in segmap.items():
                if name not in aggregated_segments:
                    aggregated_segments[name] = data.copy()
                else:
                    existing = aggregated_segments[name]
                    old_n = existing.get("n_tx", 0) or 0
                    new_n = data.get("n_tx", 0) or 0
                    total = old_n + new_n
                    existing["n_tx"] = total
                    for field in ["holdout_mean_hr", "minsup", "minconf"]:
                        if field in existing and field in data:
                            existing[field] = (
                                existing.get(field, 0) * old_n + data.get(field, 0) * new_n
                            ) / (total or 1)
        # construct per-dataset dictionary to give front-end detail
        per_dataset: Dict[str, object] = {}
        for idx, key in enumerate(all_keys):
            per_dataset[key] = {
                "recommendations": recs_list[idx] if idx < len(recs_list) else {},
                "rules": rules_frames[idx].head(120).to_dict(orient="records") if idx < len(rules_frames) else [],
                "menu_rank": menu_frames[idx].to_dict(orient="records") if idx < len(menu_frames) else [],
                "segments": segment_maps[idx] if idx < len(segment_maps) else {},
            }

        return {
            "recommendations": aggregated_recs,
            "rules": aggregated_rules,
            "menu_rank": aggregated_menu_rank,
            "segments": aggregated_segments,
            "per_dataset": per_dataset,
        }

    # default single-dataset behaviour
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
