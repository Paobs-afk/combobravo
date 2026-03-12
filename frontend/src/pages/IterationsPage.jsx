import { useMemo } from "react";
import ChartGallery from "../components/ChartGallery";
import TabIcon from "../components/TabIcon";

function IterationsPage({
  iterationHistory = [],
  recommendations = {},
  charts = [],
  chartsByDataset = {},
}) {
  const toPercent = (value) => `${(Number(value || 0) * 100).toFixed(1)}%`;
  const toFixed = (value, digits = 2) => Number(value || 0).toFixed(digits);

  const sortedRows = useMemo(
    () => [...iterationHistory].sort((left, right) => Number(left.iteration) - Number(right.iteration)),
    [iterationHistory]
  );

  const deltaSummary = useMemo(() => {
    if (sortedRows.length < 2) {
      return null;
    }
    const first = sortedRows[0];
    const last = sortedRows[sortedRows.length - 1];
    return {
      coverageDelta: Number(last.coverage_top_rules || 0) - Number(first.coverage_top_rules || 0),
      upliftDelta:
        Number(last.estimated_uplift_score || 0) - Number(first.estimated_uplift_score || 0),
      rulesDelta: Number(last.n_rules_blended || 0) - Number(first.n_rules_blended || 0),
    };
  }, [sortedRows]);

  const chartPreviewGroups = useMemo(
    () =>
      Object.entries(chartsByDataset || {})
        .map(([datasetKey, rows]) => ({
          datasetKey,
          charts: Array.isArray(rows) ? rows.slice(0, 2) : [],
        }))
        .filter((entry) => entry.charts.length),
    [chartsByDataset]
  );

  return (
    <section className="page-grid">
      <article className="panel">
        <div className="tab-header">
          <span className="tab-avatar">
            <TabIcon name="iterations" />
          </span>
          <div>
            <h2>Self-Learning Iteration Lab</h2>
            <p className="muted">
              Automated update tracking across iteration 1, 2, and 3+ for quality comparison.
            </p>
          </div>
        </div>
        <div className="kpi-grid kpi-grid-3">
          <div className="kpi">
            <p>Current Drift</p>
            <h3>{toFixed(recommendations.drift?.js, 4)}</h3>
            <small>Jensen-Shannon shift score</small>
          </div>
          <div className="kpi">
            <p>Long-Term Weight</p>
            <h3>{toPercent(recommendations.blend?.w_long)}</h3>
            <small>Model memory weight</small>
          </div>
          <div className="kpi">
            <p>Recent Weight</p>
            <h3>{toPercent(recommendations.blend?.w_recent)}</h3>
            <small>Trend adaptation weight</small>
          </div>
        </div>
      </article>

      <article className="panel">
        <h2>Iteration History</h2>
        <table>
          <thead>
            <tr>
              <th>Iteration</th>
              <th>Transactions</th>
              <th>Rules</th>
              <th>Coverage</th>
              <th>Uplift</th>
              <th>Drift (JS)</th>
              <th>Engine</th>
            </tr>
          </thead>
          <tbody>
            {sortedRows.map((row) => (
              <tr key={`it-${row.iteration}`}>
                <td>{row.iteration}</td>
                <td>{Number(row.transactions || 0).toLocaleString()}</td>
                <td>{Number(row.n_rules_blended || 0).toLocaleString()}</td>
                <td>{toPercent(row.coverage_top_rules)}</td>
                <td>{toFixed(row.estimated_uplift_score, 3)}</td>
                <td>{toFixed(row.drift_js, 4)}</td>
                <td>{row.engine_longterm || "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!sortedRows.length ? <p className="muted">No iteration history generated yet.</p> : null}
        {deltaSummary ? (
          <p className="muted iteration-delta">
            From first to latest iteration: coverage {toFixed(deltaSummary.coverageDelta * 100, 2)} pts,
            uplift {toFixed(deltaSummary.upliftDelta, 3)}, rules {toFixed(deltaSummary.rulesDelta, 0)}.
          </p>
        ) : null}
      </article>

      <article className="panel">
        <h2>Python-Generated Trend Charts</h2>
        <ChartGallery charts={charts} />
      </article>

      {chartPreviewGroups.length ? (
        <article className="panel">
          <h2>Dataset Comparison Snapshots</h2>
          <div className="page-grid">
            {chartPreviewGroups.map((entry) => (
              <section key={entry.datasetKey} className="panel panel-inline">
                <h3>{entry.datasetKey}</h3>
                <ChartGallery charts={entry.charts} />
              </section>
            ))}
          </div>
        </article>
      ) : null}
    </section>
  );
}

export default IterationsPage;
