import json
import os
from collections import Counter
from dataclasses import dataclass
from itertools import combinations
from typing import Dict, List, Sequence, Set, Tuple

import numpy as np
import pandas as pd
from mlxtend.frequent_patterns import apriori, association_rules, fpgrowth
from mlxtend.preprocessing import TransactionEncoder
from scipy.spatial.distance import jensenshannon
from supabase_store import get_supabase_store


PROJECT_ROOT = os.path.dirname(__file__)
OUTPUT_ROOT = os.path.join(PROJECT_ROOT, "outputs")

MIN_SUP_GRID = [0.01, 0.015, 0.02, 0.03, 0.04]
MIN_CONF_GRID = [0.25, 0.35, 0.45, 0.55, 0.65]

RULE_COLUMNS = [
    "antecedents",
    "consequents",
    "antecedent support",
    "consequent support",
    "support",
    "confidence",
    "lift",
    "leverage",
    "conviction",
    "support_n",
    "conf_n",
    "lift_n",
    "stability",
    "profit",
    "profit_n",
    "score",
    "recent_score",
    "blend_score",
    "key",
]


@dataclass
class TunePack:
    engine: str
    minsup: float
    minconf: float
    rules_scored: pd.DataFrame
    objective: float
    holdout_mean_hr: float


def parse_items(raw_items: str) -> List[str]:
    if pd.isna(raw_items):
        return []
    parts = [piece.strip() for piece in str(raw_items).split(",")]
    return sorted({p for p in parts if p})


def normalize(series: pd.Series) -> pd.Series:
    if series.empty:
        return series
    max_v = float(series.max())
    min_v = float(series.min())
    if np.isclose(max_v, min_v):
        return pd.Series(np.ones(len(series)), index=series.index, dtype=float)
    return (series - min_v) / (max_v - min_v)


def empty_rules_df() -> pd.DataFrame:
    return pd.DataFrame(columns=RULE_COLUMNS)


def format_rule_key(antecedents: Sequence[str], consequents: Sequence[str]) -> str:
    return f"{tuple(antecedents)}=>{tuple(consequents)}"


def onehot_from_baskets(baskets: Sequence[Sequence[str]]) -> pd.DataFrame:
    if not baskets:
        return pd.DataFrame()
    encoder = TransactionEncoder()
    encoded = encoder.fit(baskets).transform(baskets)
    return pd.DataFrame(encoded, columns=encoder.columns_)


def choose_engine(onehot: pd.DataFrame) -> str:
    if onehot.empty:
        return "fp_growth"
    density = float(onehot.values.mean())
    n_items = int(onehot.shape[1])
    if density >= 0.10 or n_items >= 30:
        return "fp_growth"
    return "apriori"


def mine_itemsets(onehot: pd.DataFrame, minsup: float) -> Tuple[str, pd.DataFrame]:
    engine = choose_engine(onehot)
    if onehot.empty:
        return engine, pd.DataFrame(columns=["support", "itemsets"])
    if engine == "fp_growth":
        itemsets = fpgrowth(onehot, min_support=minsup, use_colnames=True)
    else:
        itemsets = apriori(onehot, min_support=minsup, use_colnames=True)
    if itemsets.empty:
        return engine, itemsets
    itemsets["size"] = itemsets["itemsets"].apply(len)
    itemsets = itemsets.sort_values("support", ascending=False)
    return engine, itemsets


def rules_from_itemsets(itemsets: pd.DataFrame, minconf: float) -> pd.DataFrame:
    if itemsets.empty:
        return empty_rules_df()
    rules = association_rules(itemsets, metric="confidence", min_threshold=minconf)
    if rules.empty:
        return empty_rules_df()
    rules = rules[
        (rules["confidence"] >= minconf)
        & (rules["lift"] > 1.0)
        & (rules["antecedents"].apply(len) >= 1)
        & (rules["consequents"].apply(len) >= 1)
    ].copy()
    if rules.empty:
        return empty_rules_df()
    rules["antecedents"] = rules["antecedents"].apply(lambda fs: tuple(sorted(fs)))
    rules["consequents"] = rules["consequents"].apply(lambda fs: tuple(sorted(fs)))
    rules["key"] = rules.apply(
        lambda row: format_rule_key(row["antecedents"], row["consequents"]), axis=1
    )
    rules = rules.replace([np.inf, -np.inf], np.nan)
    rules["conviction"] = rules["conviction"].fillna(999.0)
    return rules


def estimate_profit(rule_row: pd.Series, margin_map: Dict[str, float]) -> float:
    all_items = set(rule_row["antecedents"]).union(set(rule_row["consequents"]))
    return float(sum(float(margin_map.get(item, 8.0)) for item in all_items))


def score_rules(
    rules: pd.DataFrame,
    margin_map: Dict[str, float],
    prev_keys: Set[str] | None = None,
) -> pd.DataFrame:
    if rules.empty:
        return empty_rules_df()
    prev_keys = prev_keys or set()
    scored = rules.copy()
    scored["support_n"] = normalize(scored["support"]).fillna(0.0)
    scored["conf_n"] = normalize(scored["confidence"]).fillna(0.0)
    scored["lift_n"] = normalize(scored["lift"]).fillna(0.0)
    scored["profit"] = scored.apply(lambda row: estimate_profit(row, margin_map), axis=1)
    scored["profit_n"] = normalize(scored["profit"]).fillna(0.0)
    scored["stability"] = scored["key"].apply(lambda k: 1.0 if k in prev_keys else 0.0)
    scored["score"] = (
        0.30 * scored["conf_n"]
        + 0.25 * scored["lift_n"]
        + 0.20 * scored["support_n"]
        + 0.15 * scored["stability"]
        + 0.10 * scored["profit_n"]
    )
    scored["recent_score"] = 0.0
    scored["blend_score"] = scored["score"]
    scored = scored.sort_values(["score", "lift"], ascending=False)
    for col in RULE_COLUMNS:
        if col not in scored.columns:
            scored[col] = 0.0 if col not in {"antecedents", "consequents", "key"} else ""
    return scored[RULE_COLUMNS]


def holdout_hit_rate(
    rules_scored: pd.DataFrame, test_baskets: Sequence[Set[str]], top_n: int = 35, min_occ: int = 8
) -> Tuple[float, Dict[str, float]]:
    if rules_scored.empty or not test_baskets:
        return 0.0, {}
    top = rules_scored.nlargest(top_n, "score")
    rule_hr: Dict[str, float] = {}
    for _, row in top.iterrows():
        antecedent = set(row["antecedents"])
        consequent = set(row["consequents"])
        occ = 0
        hits = 0
        for basket in test_baskets:
            if antecedent.issubset(basket):
                occ += 1
                if consequent.issubset(basket):
                    hits += 1
        if occ >= min_occ:
            rule_hr[row["key"]] = float(hits / occ)
    if not rule_hr:
        return 0.0, {}
    return float(np.mean(list(rule_hr.values()))), rule_hr


def auto_tune_rules(
    baskets: Sequence[Sequence[str]], margin_map: Dict[str, float], prev_keys: Set[str] | None = None
) -> TunePack:
    if len(baskets) < 30:
        return TunePack("fp_growth", 0.02, 0.45, empty_rules_df(), 0.0, 0.0)

    split_idx = max(int(len(baskets) * 0.80), 1)
    split_idx = min(split_idx, len(baskets) - 1)
    train_baskets = [set(b) for b in baskets[:split_idx]]
    test_baskets = [set(b) for b in baskets[split_idx:]]

    train_oh = onehot_from_baskets(train_baskets)

    best_pack: TunePack | None = None
    best_objective = -1.0
    for minsup in MIN_SUP_GRID:
        engine, itemsets = mine_itemsets(train_oh, minsup)
        if itemsets.empty:
            continue
        for minconf in MIN_CONF_GRID:
            rules = rules_from_itemsets(itemsets, minconf)
            if rules.empty:
                continue
            scored = score_rules(rules, margin_map=margin_map, prev_keys=prev_keys)
            mean_hr, _ = holdout_hit_rate(scored, test_baskets, top_n=35, min_occ=6)
            objective = float(0.70 * scored["score"].mean() + 0.30 * mean_hr)
            if objective > best_objective:
                best_objective = objective
                best_pack = TunePack(
                    engine=engine,
                    minsup=float(minsup),
                    minconf=float(minconf),
                    rules_scored=scored,
                    objective=objective,
                    holdout_mean_hr=float(mean_hr),
                )

    if best_pack is None:
        return TunePack("fp_growth", 0.02, 0.45, empty_rules_df(), 0.0, 0.0)
    return best_pack


def drift_score(prev_onehot: pd.DataFrame | None, curr_onehot: pd.DataFrame) -> Dict[str, float | bool]:
    if prev_onehot is None or prev_onehot.empty or curr_onehot.empty:
        return {"drift": False, "js": 0.0}
    union_cols = sorted(set(prev_onehot.columns).union(set(curr_onehot.columns)))
    prev_aligned = prev_onehot.reindex(columns=union_cols, fill_value=False)
    curr_aligned = curr_onehot.reindex(columns=union_cols, fill_value=False)

    prev_dist = prev_aligned.mean(axis=0).to_numpy(dtype=float)
    curr_dist = curr_aligned.mean(axis=0).to_numpy(dtype=float)

    prev_dist = np.clip(prev_dist, 1e-12, None)
    curr_dist = np.clip(curr_dist, 1e-12, None)
    prev_dist = prev_dist / prev_dist.sum()
    curr_dist = curr_dist / curr_dist.sum()

    js_distance = float(jensenshannon(prev_dist, curr_dist))
    return {"drift": bool(js_distance >= 0.12), "js": js_distance}


def blend_rule_views(
    long_rules: pd.DataFrame, recent_rules: pd.DataFrame, w_long: float, w_recent: float
) -> pd.DataFrame:
    if long_rules.empty and recent_rules.empty:
        return empty_rules_df()
    if recent_rules.empty:
        blended = long_rules.copy()
        blended["recent_score"] = 0.0
        blended["blend_score"] = w_long * blended["score"]
        return blended.sort_values("blend_score", ascending=False)
    if long_rules.empty:
        blended = recent_rules.copy()
        blended["recent_score"] = blended["score"]
        blended["blend_score"] = w_recent * blended["score"]
        return blended.sort_values("blend_score", ascending=False)

    long_pref = long_rules.add_suffix("_long")
    recent_pref = recent_rules.add_suffix("_recent")
    merged = pd.merge(
        long_pref,
        recent_pref,
        left_on="key_long",
        right_on="key_recent",
        how="outer",
    )
    merged["key"] = merged["key_long"].fillna(merged["key_recent"])

    combined = pd.DataFrame()
    combined["key"] = merged["key"]
    for col in [
        "antecedents",
        "consequents",
        "antecedent support",
        "consequent support",
        "support",
        "confidence",
        "lift",
        "leverage",
        "conviction",
        "support_n",
        "conf_n",
        "lift_n",
        "stability",
        "profit",
        "profit_n",
    ]:
        left_col = f"{col}_long"
        right_col = f"{col}_recent"
        combined[col] = merged[left_col].combine_first(merged[right_col])

    combined["score"] = merged["score_long"].fillna(0.0)
    combined["recent_score"] = merged["score_recent"].fillna(0.0)
    combined["blend_score"] = (
        w_long * merged["score_long"].fillna(0.0) + w_recent * merged["score_recent"].fillna(0.0)
    )
    combined = combined.sort_values(["blend_score", "lift"], ascending=False)
    for col in RULE_COLUMNS:
        if col not in combined.columns:
            combined[col] = 0.0 if col not in {"antecedents", "consequents", "key"} else ""
    return combined[RULE_COLUMNS]


def build_menu_rank(baskets: Sequence[Sequence[str]], rules: pd.DataFrame) -> pd.DataFrame:
    counts = Counter(item for basket in baskets for item in basket)
    if not counts:
        return pd.DataFrame(columns=["item", "pop", "impact", "rank_score"])

    impact_map: Dict[str, float] = {item: 0.0 for item in counts}
    for _, row in rules.iterrows():
        blend = float(row.get("blend_score", 0.0))
        for item in row["consequents"]:
            impact_map[item] = impact_map.get(item, 0.0) + blend
        for item in row["antecedents"]:
            impact_map[item] = impact_map.get(item, 0.0) + (0.35 * blend)

    ranking = pd.DataFrame({"item": list(counts.keys()), "pop": list(counts.values())})
    ranking["impact"] = ranking["item"].map(impact_map).fillna(0.0)
    ranking["rank_score"] = 0.65 * normalize(ranking["pop"]).fillna(0.0) + 1.35 * normalize(
        ranking["impact"]
    ).fillna(0.0)
    ranking = ranking.sort_values("rank_score", ascending=False).reset_index(drop=True)
    return ranking


def build_pair_model(baskets: Sequence[Sequence[str]]) -> Dict[str, object]:
    item_counts: Counter[str] = Counter()
    pair_counts: Counter[Tuple[str, str]] = Counter()
    tx_count = 0

    for basket in baskets:
        unique_items = sorted(set(basket))
        if not unique_items:
            continue
        tx_count += 1
        for item in unique_items:
            item_counts[item] += 1
        for left, right in combinations(unique_items, 2):
            pair_counts[(left, right)] += 1

    return {"tx_count": tx_count, "item_counts": item_counts, "pair_counts": pair_counts}


def fallback_pair_suggestions(
    selected_item: str, pair_model: Dict[str, object], limit: int = 5, min_occ: int = 4
) -> List[Dict[str, str | float]]:
    tx_count = int(pair_model.get("tx_count", 0))
    if tx_count <= 0:
        return []

    item_counts: Counter[str] = pair_model.get("item_counts", Counter())
    pair_counts: Counter[Tuple[str, str]] = pair_model.get("pair_counts", Counter())
    selected_count = int(item_counts.get(selected_item, 0))
    if selected_count <= 0:
        return []

    selected_support = float(selected_count / tx_count)
    picks: List[Dict[str, str | float]] = []
    for other_item, other_count in item_counts.items():
        if other_item == selected_item:
            continue
        pair_key = tuple(sorted((selected_item, other_item)))
        pair_count = int(pair_counts.get(pair_key, 0))
        if pair_count < min_occ:
            continue

        support = float(pair_count / tx_count)
        confidence = float(pair_count / selected_count)
        consequent_support = float(other_count / tx_count)
        lift = float(confidence / consequent_support) if consequent_support else 0.0
        leverage = float(support - (selected_support * consequent_support))
        conviction = float((1 - consequent_support) / max(1 - confidence, 1e-9))
        score = float(0.50 * confidence + 0.35 * max(lift - 1.0, 0.0) + 0.15 * support)

        picks.append(
            {
                "item": other_item,
                "score": score,
                "support": support,
                "confidence": confidence,
                "lift": lift,
                "leverage": leverage,
                "conviction": conviction,
                "why": f"pair signal: conf={confidence:.2f}, lift={lift:.2f}",
            }
        )
    return sorted(picks, key=lambda row: float(row["score"]), reverse=True)[:limit]


def top_item_suggestions(
    selected_item: str,
    rules: pd.DataFrame,
    limit: int = 5,
    pair_model: Dict[str, object] | None = None,
) -> List[Dict[str, str | float]]:
    best: Dict[str, Dict[str, str | float]] = {}
    if not rules.empty:
        for _, row in rules.sort_values("blend_score", ascending=False).iterrows():
            antecedent = set(row["antecedents"])
            if selected_item not in antecedent:
                continue
            for item in row["consequents"]:
                if item == selected_item or item in best:
                    continue
                best[item] = {
                    "item": item,
                    "score": float(row["blend_score"]),
                    "support": float(row["support"]),
                    "confidence": float(row["confidence"]),
                    "lift": float(row["lift"]),
                    "leverage": float(row.get("leverage", 0.0)),
                    "conviction": float(row.get("conviction", 0.0)),
                    "why": f"rule signal: conf={row['confidence']:.2f}, lift={row['lift']:.2f}",
                }
    ordered = sorted(best.values(), key=lambda row: float(row["score"]), reverse=True)
    if pair_model and len(ordered) < limit:
        fallback = fallback_pair_suggestions(
            selected_item, pair_model, limit=max(limit * 2, limit + 2)
        )
        for row in fallback:
            if row["item"] in best:
                continue
            ordered.append(row)
            if len(ordered) >= limit:
                break
    return ordered[:limit]


def recommendation_coverage(
    baskets: Sequence[Sequence[str]], rules: pd.DataFrame, top_n: int = 20
) -> float:
    if not baskets or rules.empty:
        return 0.0
    top = rules.sort_values("blend_score", ascending=False).head(top_n)
    antecedents = [set(row["antecedents"]) for _, row in top.iterrows()]
    if not antecedents:
        return 0.0
    covered = 0
    for basket in baskets:
        basket_set = set(basket)
        if any(antecedent.issubset(basket_set) for antecedent in antecedents):
            covered += 1
    return float(covered / len(baskets))


def build_cart_targets(
    rules: pd.DataFrame,
    menu_rank: pd.DataFrame,
    pair_model: Dict[str, object] | None = None,
    max_items: int = 10,
    suggestion_limit: int = 5,
) -> Dict[str, List[Dict[str, str | float]]]:
    seed_items: List[str] = []
    if not menu_rank.empty:
        seed_items = menu_rank["item"].head(max_items).tolist()
    elif not rules.empty:
        seed_items = list(
            dict.fromkeys(
                item for _, row in rules.iterrows() for item in list(row["antecedents"])
            )
        )[:max_items]

    targets: Dict[str, List[Dict[str, str | float]]] = {}
    for item in seed_items:
        picks = top_item_suggestions(item, rules, limit=suggestion_limit, pair_model=pair_model)
        if picks:
            targets[item] = picks
    return targets


def generate_promos(
    rules: pd.DataFrame, pair_model: Dict[str, object] | None = None, limit: int = 5
) -> List[Dict[str, object]]:
    promos: List[Dict[str, object]] = []
    seen_bundle: Set[Tuple[str, ...]] = set()

    if not rules.empty:
        for _, row in rules.sort_values("blend_score", ascending=False).iterrows():
            bundle = tuple(dict.fromkeys(list(row["antecedents"]) + list(row["consequents"])))
            if len(bundle) < 2 or bundle in seen_bundle:
                continue
            seen_bundle.add(bundle)
            promo_name = "Bundle Discount 10%" if len(bundle) >= 3 else "Add-on Suggestion 15%"
            promos.append(
                {
                    "bundle": list(bundle),
                    "promo": promo_name,
                    "why": f"lift={row['lift']:.2f}, conf={row['confidence']:.2f}, profit~{row['profit']:.0f}php",
                }
            )
            if len(promos) >= limit:
                break

    if pair_model and len(promos) < limit:
        item_counts: Counter[str] = pair_model.get("item_counts", Counter())
        pair_counts: Counter[Tuple[str, str]] = pair_model.get("pair_counts", Counter())
        tx_count = int(pair_model.get("tx_count", 0))
        if tx_count > 0:
            pair_rows = sorted(pair_counts.items(), key=lambda pair: pair[1], reverse=True)
            for (left, right), pair_count in pair_rows:
                bundle = (left, right)
                if bundle in seen_bundle:
                    continue
                left_support = float(item_counts.get(left, 0) / tx_count)
                right_support = float(item_counts.get(right, 0) / tx_count)
                confidence = float(pair_count / max(item_counts.get(left, 1), 1))
                support = float(pair_count / tx_count)
                lift = float(confidence / right_support) if right_support else 0.0
                if support < 0.02 or lift <= 1.0:
                    continue
                seen_bundle.add(bundle)
                promos.append(
                    {
                        "bundle": [left, right],
                        "promo": "Pair Promo 12%",
                        "why": f"pair support={support:.2f}, lift={lift:.2f}, conf={confidence:.2f}",
                    }
                )
                if len(promos) >= limit:
                    break
    return promos


def generate_top_bundles(
    rules: pd.DataFrame, pair_model: Dict[str, object] | None = None, limit: int = 5
) -> List[Dict[str, object]]:
    bundles: List[Dict[str, object]] = []
    seen: Set[Tuple[str, ...]] = set()

    if not rules.empty:
        for _, row in rules.sort_values("blend_score", ascending=False).iterrows():
            bundle = tuple(dict.fromkeys(list(row["antecedents"]) + list(row["consequents"])))
            if len(bundle) < 2 or bundle in seen:
                continue
            seen.add(bundle)
            bundles.append(
                {
                    "items": list(bundle),
                    "support": float(row["support"]),
                    "confidence": float(row["confidence"]),
                    "lift": float(row["lift"]),
                    "leverage": float(row.get("leverage", 0.0)),
                    "conviction": float(row.get("conviction", 0.0)),
                    "why": f"strong bundle because lift={row['lift']:.2f} and confidence={row['confidence']:.2f}",
                }
            )
            if len(bundles) >= limit:
                return bundles

    if pair_model:
        item_counts: Counter[str] = pair_model.get("item_counts", Counter())
        pair_counts: Counter[Tuple[str, str]] = pair_model.get("pair_counts", Counter())
        tx_count = int(pair_model.get("tx_count", 0))
        if tx_count > 0:
            for (left, right), pair_count in sorted(pair_counts.items(), key=lambda pair: pair[1], reverse=True):
                bundle = (left, right)
                if bundle in seen:
                    continue
                left_support = float(item_counts.get(left, 0) / tx_count)
                right_support = float(item_counts.get(right, 0) / tx_count)
                support = float(pair_count / tx_count)
                confidence = float(pair_count / max(item_counts.get(left, 1), 1))
                lift = float(confidence / right_support) if right_support else 0.0
                leverage = float(support - (left_support * right_support))
                conviction = float((1 - right_support) / max(1 - confidence, 1e-9))
                if support < 0.02 or lift <= 1.0:
                    continue
                seen.add(bundle)
                bundles.append(
                    {
                        "items": [left, right],
                        "support": support,
                        "confidence": confidence,
                        "lift": lift,
                        "leverage": leverage,
                        "conviction": conviction,
                        "why": "pair-driven bundle from frequent co-purchases",
                    }
                )
                if len(bundles) >= limit:
                    break

    return bundles


def portfolio_delta(prev_rules: pd.DataFrame, curr_rules: pd.DataFrame) -> Dict[str, object]:
    prev_map = {row["key"]: row for _, row in prev_rules.iterrows()}
    curr_map = {row["key"]: row for _, row in curr_rules.iterrows()}
    prev_keys = set(prev_map.keys())
    curr_keys = set(curr_map.keys())

    stable_keys = curr_keys.intersection(prev_keys)
    emerging_keys = curr_keys.difference(prev_keys)
    fading_keys = prev_keys.difference(curr_keys)

    def to_brief(rule_row: pd.Series) -> Dict[str, List[str]]:
        return {
            "antecedents": list(rule_row["antecedents"]),
            "consequents": list(rule_row["consequents"]),
        }

    stable = [to_brief(curr_map[key]) for key in list(stable_keys)[:8]]
    emerging = [to_brief(curr_map[key]) for key in list(emerging_keys)[:8]]
    fading = [to_brief(prev_map[key]) for key in list(fading_keys)[:8]]
    return {
        "stable": stable,
        "emerging": emerging,
        "fading": fading,
        "stable_count": len(stable_keys),
        "emerging_count": len(emerging_keys),
        "fading_count": len(fading_keys),
    }


def build_business_insights(
    menu_rank: pd.DataFrame,
    blended_rules: pd.DataFrame,
    coverage: float,
    estimated_uplift_score: float,
    drift: Dict[str, float | bool],
    margin_map: Dict[str, float],
) -> List[str]:
    insights: List[str] = []
    if not menu_rank.empty:
        anchor_items = menu_rank["item"].head(3).tolist()
        insights.append(
            f"Homepage anchor order should be {', '.join(anchor_items)} based on rank score."
        )

    if not blended_rules.empty:
        strongest = blended_rules.iloc[0]
        insights.append(
            f"Most influential cross-sell rule: {', '.join(strongest['antecedents'])} -> {', '.join(strongest['consequents'])}."
        )

    if margin_map and not menu_rank.empty:
        ranked_items = menu_rank[["item", "rank_score"]].copy()
        ranked_items["margin_php"] = ranked_items["item"].map(margin_map).fillna(0.0)
        ranked_items["rank_order"] = np.arange(1, len(ranked_items) + 1)
        high_margin = ranked_items.sort_values("margin_php", ascending=False).head(6)
        underexposed = high_margin[high_margin["rank_order"] > max(3, len(ranked_items) * 0.35)]
        if not underexposed.empty:
            pick = underexposed.iloc[0]
            insights.append(
                f"Shelf placement suggestion: move {pick['item']} near checkout to monetize its high margin ({pick['margin_php']:.0f}php)."
            )

    insights.append(
        "FP-Growth is automatically selected for dense baskets to avoid Apriori candidate explosion."
    )
    insights.append(
        f"Iteration drift score (JS) is {float(drift['js']):.4f}, recent-model weight adapted automatically."
    )
    insights.append(
        f"Top-rule coverage is {coverage:.1%} of baskets with estimated uplift score {estimated_uplift_score:.2f}."
    )
    return insights


def rules_for_export(rules: pd.DataFrame) -> pd.DataFrame:
    export = rules.copy()
    export["antecedents"] = export["antecedents"].apply(
        lambda items: ", ".join(items) if isinstance(items, tuple) else str(items)
    )
    export["consequents"] = export["consequents"].apply(
        lambda items: ", ".join(items) if isinstance(items, tuple) else str(items)
    )
    return export


def load_transactions(dataset_name: str, iteration: int) -> pd.DataFrame:
    store = get_supabase_store()
    df = store.load_transactions_for_iteration(dataset_name, iteration)
    if df.empty:
        raise FileNotFoundError(f"No transactions found for dataset '{dataset_name}' iteration {iteration}")
    return df


def load_margin_map(dataset_name: str) -> Dict[str, float]:
    store = get_supabase_store()
    return store.get_margin_map(dataset_name)


def build_segment_snapshot(df: pd.DataFrame, margin_map: Dict[str, float]) -> Dict[str, object]:
    snapshot: Dict[str, object] = {}
    for segment in ["morning", "lunch", "dinner"]:
        seg_df = df[df["segment"] == segment]
        seg_baskets = seg_df["basket"].tolist()
        if len(seg_baskets) < 40:
            continue
        seg_pack = auto_tune_rules(seg_baskets, margin_map=margin_map)
        seg_rules = seg_pack.rules_scored.copy()
        seg_rules["blend_score"] = seg_rules["score"]
        seg_menu = build_menu_rank(seg_baskets, seg_rules)
        seg_pairs = build_pair_model(seg_baskets)
        snapshot[segment] = {
            "n_tx": int(len(seg_df)),
            "engine": seg_pack.engine,
            "minsup": seg_pack.minsup,
            "minconf": seg_pack.minconf,
            "holdout_mean_hr": seg_pack.holdout_mean_hr,
            "menu_rank_top10": seg_menu.head(10).to_dict(orient="records"),
            "promos_top3": generate_promos(seg_rules, pair_model=seg_pairs, limit=3),
        }
    return snapshot


def ensure_output_dir(dataset_name: str) -> str:
    out_dir = os.path.join(OUTPUT_ROOT, dataset_name)
    os.makedirs(out_dir, exist_ok=True)
    return out_dir


def run_dataset_iterations(dataset_name: str, max_iteration: int = 3) -> List[Dict[str, object]]:
    margin_map = load_margin_map(dataset_name)
    out_dir = ensure_output_dir(dataset_name)

    previous_onehot: pd.DataFrame | None = None
    previous_blended = empty_rules_df()
    reports: List[Dict[str, object]] = []

    for iteration in range(1, max_iteration + 1):
        df = load_transactions(dataset_name, iteration)
        baskets = df["basket"].tolist()
        onehot = onehot_from_baskets(baskets)
        drift = drift_score(previous_onehot, onehot)
        w_recent = 0.60 if drift["drift"] else 0.30
        w_long = 1.00 - w_recent

        prev_keys = set(previous_blended["key"].tolist()) if not previous_blended.empty else set()
        long_pack = auto_tune_rules(baskets, margin_map=margin_map, prev_keys=prev_keys)

        recent_window = min(500, len(baskets))
        recent_pack = auto_tune_rules(
            baskets[-recent_window:], margin_map=margin_map, prev_keys=prev_keys
        )
        blended_rules = blend_rule_views(
            long_pack.rules_scored, recent_pack.rules_scored, w_long=w_long, w_recent=w_recent
        )

        pair_model = build_pair_model(baskets)
        menu_rank = build_menu_rank(baskets, blended_rules)
        cart_targets = build_cart_targets(
            blended_rules, menu_rank, pair_model=pair_model, max_items=10, suggestion_limit=5
        )
        coverage = recommendation_coverage(baskets, blended_rules, top_n=20)
        avg_basket_size = float(np.mean([len(b) for b in baskets])) if baskets else 0.0
        mean_blend = float(blended_rules["blend_score"].head(12).mean()) if not blended_rules.empty else 0.0
        estimated_uplift_score = float(min(1.0, coverage * (1.0 + mean_blend)))

        promos = generate_promos(blended_rules, pair_model=pair_model, limit=5)
        top_bundles = generate_top_bundles(blended_rules, pair_model=pair_model, limit=5)
        top_rules_full = []
        for _, row in blended_rules.head(12).iterrows():
            top_rules_full.append(
                {
                    "antecedents": list(row["antecedents"]),
                    "consequents": list(row["consequents"]),
                    "support": float(row["support"]),
                    "confidence": float(row["confidence"]),
                    "lift": float(row["lift"]),
                    "leverage": float(row.get("leverage", 0.0)),
                    "conviction": float(row.get("conviction", 0.0)),
                    "blend_score": float(row.get("blend_score", 0.0)),
                }
            )

        portfolio = portfolio_delta(previous_blended.head(25), blended_rules.head(25))
        widget_item = "Burger"
        if widget_item not in cart_targets:
            if not menu_rank.empty:
                widget_item = str(menu_rank.iloc[0]["item"])
            elif cart_targets:
                widget_item = next(iter(cart_targets.keys()))
        fbt_widget = cart_targets.get(
            widget_item,
            top_item_suggestions(widget_item, blended_rules, limit=5, pair_model=pair_model),
        )
        cross_sell_widget = cart_targets.get(
            widget_item,
            top_item_suggestions(widget_item, blended_rules, limit=5, pair_model=pair_model),
        )
        burger_suggestions = top_item_suggestions(
            "Burger", blended_rules, limit=5, pair_model=pair_model
        )
        segment_snapshot = build_segment_snapshot(df, margin_map)

        insights = build_business_insights(
            menu_rank=menu_rank,
            blended_rules=blended_rules,
            coverage=coverage,
            estimated_uplift_score=estimated_uplift_score,
            drift=drift,
            margin_map=margin_map,
        )
        homepage_ranking_preview = menu_rank.head(10).to_dict(orient="records")

        rec_json = {
            "business": {
                "scenario": "Restaurant kiosk recommender backend",
                "users": ["owner", "cashier", "admin", "customer"],
                "decisions": [
                    "combo creation",
                    "cross-sell prompts at checkout",
                    "homepage item ordering",
                    "promo strategy",
                ],
                "value": "higher average order value and faster recommendation updates from new transactions",
            },
            "algorithm_notes": {
                "primary_engine": long_pack.engine,
                "diff_vs_apriori": "FP-Growth compresses transactions into an FP-tree and avoids generating all candidate itemsets.",
                "why_fit": "The datasets have 1,000+ transactions with dense food baskets, so FP-Growth scales better in speed and memory.",
            },
            "iteration": iteration,
            "n_transactions": int(len(df)),
            "n_unique_items": int(onehot.shape[1]),
            "drift": drift,
            "blend": {"w_long": w_long, "w_recent": w_recent},
            "engine_longterm": long_pack.engine,
            "minsup_longterm": long_pack.minsup,
            "minconf_longterm": long_pack.minconf,
            "holdout_mean_hr_longterm": long_pack.holdout_mean_hr,
            "engine_recent": recent_pack.engine,
            "holdout_mean_hr_recent": recent_pack.holdout_mean_hr,
            "system_metrics": {
                "avg_basket_size": avg_basket_size,
                "coverage_top_rules": coverage,
                "estimated_uplift_score": estimated_uplift_score,
                "n_rules_blended": int(len(blended_rules)),
                "recommendable_items": int(len(cart_targets)),
            },
            "top_bundles": top_bundles,
            "top_rules_full_measures": top_rules_full,
            "homepage_ranking_preview": homepage_ranking_preview,
            "fbt_widget": {"anchor_item": widget_item, "suggestions": fbt_widget},
            "cross_sell_widget": {"cart_item": widget_item, "suggestions": cross_sell_widget},
            "fbt_burger": burger_suggestions,
            "cross_sell_burger": burger_suggestions,
            "cart_targets": cart_targets,
            "promos": promos,
            "portfolio": portfolio,
            "business_insights": insights,
        }

        rules_export = rules_for_export(blended_rules)
        rules_export.to_csv(os.path.join(out_dir, f"iteration_{iteration}_rules.csv"), index=False)
        menu_rank.to_csv(os.path.join(out_dir, f"iteration_{iteration}_menu_rank.csv"), index=False)
        with open(
            os.path.join(out_dir, f"iteration_{iteration}_recs.json"), "w", encoding="utf-8"
        ) as handle:
            json.dump(rec_json, handle, indent=2, ensure_ascii=False)
        with open(
            os.path.join(out_dir, f"iteration_{iteration}_segment_snapshot.json"),
            "w",
            encoding="utf-8",
        ) as handle:
            json.dump(segment_snapshot, handle, indent=2, ensure_ascii=False)

        reports.append(
            {
                "iteration": iteration,
                "n_transactions": int(len(df)),
                "engine_longterm": long_pack.engine,
                "engine_recent": recent_pack.engine,
                "n_rules": int(len(blended_rules)),
                "drift_js": float(drift["js"]),
            }
        )
        previous_onehot = onehot
        previous_blended = blended_rules
    return reports


def run_all_datasets(max_iteration: int = 3) -> Dict[str, List[Dict[str, object]]]:
    store = get_supabase_store()
    dataset_names = store.list_dataset_keys()
    reports: Dict[str, List[Dict[str, object]]] = {}
    for dataset_name in dataset_names:
        reports[dataset_name] = run_dataset_iterations(dataset_name, max_iteration=max_iteration)
    return reports
