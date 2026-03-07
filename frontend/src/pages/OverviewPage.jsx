import { useEffect, useMemo, useState } from "react";
import BundleCard from "../components/BundleCard";
import PromoEngine from "../components/PromoEngine";

function OverviewPage({
  loading = false,
  recommendations = {},
  rules = [],
  menuRank = [],
  topMeals = [],
}) {
  const [selectedAnchor, setSelectedAnchor] = useState("");

  const toPercent = (value) => `${(Number(value || 0) * 100).toFixed(1)}%`;
  const toFixed = (value, digits = 2) => Number(value || 0).toFixed(digits);

  const parseItems = (value) => {
    if (Array.isArray(value)) {
      return value.map((item) => String(item).trim()).filter(Boolean);
    }
    return String(value || "")
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
  };

  const kpis = useMemo(
    () => [
      {
        label: "Transactions",
        value: Number(recommendations.n_transactions || 0).toLocaleString(),
        note: "Processed in selected iteration",
      },
      {
        label: "Unique Items",
        value: Number(recommendations.n_unique_items || 0).toLocaleString(),
        note: "Menu variety available",
      },
      {
        label: "Coverage",
        value: toPercent(recommendations.system_metrics?.coverage_top_rules),
        note: "Baskets reached by top rules",
      },
      {
        label: "Estimated Uplift",
        value: toFixed(recommendations.system_metrics?.estimated_uplift_score, 2),
        note: "Rule-driven opportunity score",
      },
      {
        label: "Rules Blended",
        value: Number(
          recommendations.system_metrics?.n_rules_blended || 0
        ).toLocaleString(),
        note: "Long-term + recent model rules",
      },
      {
        label: "Primary Engine",
        value: recommendations.engine_longterm || "-",
        note: "Auto-selected mining algorithm",
      },
    ],
    [recommendations]
  );

  const bundles = useMemo(() => {
    const source = recommendations.top_bundles || [];
    return source.map((bundle, index) => ({
      name: `Bundle ${index + 1}`,
      items: bundle.items || [],
      support: Number(bundle.support || 0),
      confidence: Number(bundle.confidence || 0),
      lift: Number(bundle.lift || 0),
      leverage: Number(bundle.leverage || 0),
      conviction: Number(bundle.conviction || 0),
      why: bundle.why || "",
    }));
  }, [recommendations]);

  const topRules = useMemo(() => {
    const richRules = recommendations.top_rules_full_measures || [];
    if (richRules.length) {
      return richRules.map((row, index) => ({
        key: `rich-${index}-${(row.antecedents || []).join("|")}`,
        label: `${parseItems(row.antecedents).join(" + ")} -> ${parseItems(
          row.consequents
        ).join(" + ")}`,
        support: Number(row.support || 0),
        confidence: Number(row.confidence || 0),
        lift: Number(row.lift || 0),
        leverage: Number(row.leverage || 0),
        conviction: Number(row.conviction || 0),
      }));
    }

    return rules.map((row) => ({
      key: row.key || `${row.antecedents}-${row.consequents}`,
      label: `${parseItems(row.antecedents).join(" + ")} -> ${parseItems(
        row.consequents
      ).join(" + ")}`,
      support: Number(row.support || 0),
      confidence: Number(row.confidence || 0),
      lift: Number(row.lift || 0),
      leverage: Number(row.leverage || 0),
      conviction: Number(row.conviction || 0),
    }));
  }, [recommendations, rules]);

  const rankingRows = useMemo(() => {
    const source = recommendations.homepage_ranking_preview?.length
      ? recommendations.homepage_ranking_preview
      : menuRank;

    return [...source]
      .map((row) => ({
        item: row.item,
        pop: Number(row.pop || 0),
        impact: Number(row.impact || 0),
        rank_score: Number(row.rank_score || 0),
      }))
      .sort((left, right) => right.rank_score - left.rank_score)
      .slice(0, 10);
  }, [menuRank, recommendations]);

  const anchorOptions = useMemo(() => {
    const targets = Object.keys(recommendations.cart_targets || {});
    if (targets.length) {
      return targets;
    }
    return rankingRows.map((row) => row.item);
  }, [rankingRows, recommendations]);

  const selectedAnchorSuggestions = useMemo(() => {
    const map = recommendations.cart_targets || {};
    if (selectedAnchor && Array.isArray(map[selectedAnchor])) {
      return map[selectedAnchor];
    }
    const widget = recommendations.fbt_widget?.suggestions;
    if (Array.isArray(widget)) {
      return widget;
    }
    return [];
  }, [recommendations, selectedAnchor]);

  const notes = useMemo(() => {
    const insightList = recommendations.business_insights || [];
    if (insightList.length) {
      return insightList;
    }
    if (topMeals?.[0]) {
      return [
        `Top meal overall: ${topMeals[0].item} (${topMeals[0].count} orders).`,
      ];
    }
    return ["No insight generated yet."];
  }, [recommendations, topMeals]);

  useEffect(() => {
    if (!anchorOptions.includes(selectedAnchor)) {
      setSelectedAnchor(anchorOptions[0] || "");
    }
  }, [anchorOptions, selectedAnchor]);

  return (
    <section className="page-grid">
      <article className="panel">
        <div className="panel-head">
          <h2>System Dashboard</h2>
          {loading ? <span className="chip">Refreshing...</span> : null}
        </div>
        <div className="kpi-grid">
          {kpis.map((kpi) => (
            <div key={kpi.label} className="kpi">
              <p>{kpi.label}</p>
              <h3>{kpi.value}</h3>
              <small>{kpi.note}</small>
            </div>
          ))}
        </div>
      </article>

      <article className="panel">
        <h2>Top Bundles With Explanation</h2>
        <div className="bundle-grid">
          {bundles.map((bundle, index) => (
            <BundleCard
              key={`${bundle.name}-${index}`}
              bundle={bundle}
              index={index + 1}
            />
          ))}
        </div>
        {!bundles.length ? (
          <p className="muted">No bundle generated in this iteration.</p>
        ) : null}
      </article>

      <section className="split-grid">
        <article className="panel">
          <h2>Top Association Rules (Full Measures)</h2>
          <table>
            <thead>
              <tr>
                <th>Rule</th>
                <th>Support</th>
                <th>Confidence</th>
                <th>Lift</th>
                <th>Leverage</th>
                <th>Conviction</th>
              </tr>
            </thead>
            <tbody>
              {topRules.slice(0, 10).map((rule) => (
                <tr key={rule.key}>
                  <td>{rule.label}</td>
                  <td>{toPercent(rule.support)}</td>
                  <td>{toPercent(rule.confidence)}</td>
                  <td>{toFixed(rule.lift, 2)}</td>
                  <td>{toFixed(rule.leverage, 4)}</td>
                  <td>{toFixed(rule.conviction, 2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!topRules.length ? <p className="muted">No rules found.</p> : null}
        </article>

        <article className="panel">
          <h2>Homepage Ranking Logic</h2>
          <div className="rank-list">
            {rankingRows.map((item) => (
              <article key={item.item} className="rank-row">
                <div className="rank-head">
                  <strong>{item.item}</strong>
                  <span>{toFixed(item.rank_score, 3)}</span>
                </div>
                <div className="bar">
                  <div
                    className="fill"
                    style={{ width: `${Math.min(item.rank_score * 55, 100)}%` }}
                  />
                </div>
                <small>
                  Pop {item.pop} | Rule impact {toFixed(item.impact, 2)}
                </small>
              </article>
            ))}
          </div>
        </article>
      </section>

      <section className="split-grid">
        <article className="panel">
          <div className="panel-head">
            <h2>Frequently Bought Together Widget</h2>
            <label className="inline-control">
              Item
              <select
                value={selectedAnchor}
                onChange={(event) => setSelectedAnchor(event.target.value)}
              >
                {anchorOptions.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="card-stack">
            {selectedAnchorSuggestions.map((pick) => (
              <article key={pick.item} className="suggestion-card">
                <h4>
                  {selectedAnchor} + {pick.item}
                </h4>
                <p>{pick.why}</p>
                <small>
                  support {toPercent(pick.support)} | confidence{" "}
                  {toPercent(pick.confidence)} | lift {toFixed(pick.lift, 2)}
                </small>
              </article>
            ))}
          </div>
          {!selectedAnchorSuggestions.length ? (
            <p className="muted">No suggestions available.</p>
          ) : null}
        </article>

        <article className="panel">
          <h2>Cross-Sell Suggestions (When Added To Cart)</h2>
          <p className="muted">
            Simulated checkout prompt for <strong>{selectedAnchor}</strong>.
          </p>
          <ul className="insight-list">
            {selectedAnchorSuggestions.slice(0, 5).map((pick) => (
              <li key={`cross-${pick.item}`}>
                Suggest <strong>{pick.item}</strong> using {pick.why}
              </li>
            ))}
          </ul>
        </article>
      </section>

      <section className="split-grid">
        <article className="panel">
          <h2>Promo Recommendation Generator</h2>
          <PromoEngine promos={recommendations.promos || []} />
        </article>

        <article className="panel">
          <h2>Business Insights</h2>
          <ul className="insight-list">
            {notes.map((note, index) => (
              <li key={`note-${index}`}>{note}</li>
            ))}
          </ul>
        </article>
      </section>
    </section>
  );
}

export default OverviewPage;
