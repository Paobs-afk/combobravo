import { useMemo } from "react";

function AnalysisPage({ topMeals = [], menuRank = [], segments = {}, recommendations = {} }) {
  const toPercent = (value) => `${(Number(value || 0) * 100).toFixed(1)}%`;
  const toFixed = (value, digits = 2) => Number(value || 0).toFixed(digits);

  const topMealsRows = useMemo(() => {
    const rows = [...topMeals]
      .map((row) => ({
        item: row.item,
        count: Number(row.count || 0),
        share: Number(row.share || 0),
      }))
      .slice(0, 10);
    const maxCount = Math.max(...rows.map((row) => row.count), 1);
    return rows.map((row) => ({
      ...row,
      width: Number(((row.count / maxCount) * 100).toFixed(2)),
    }));
  }, [topMeals]);

  const rankRows = useMemo(
    () =>
      [...menuRank]
        .map((row) => ({
          item: row.item,
          pop: Number(row.pop || 0),
          impact: Number(row.impact || 0),
          rank_score: Number(row.rank_score || 0),
        }))
        .sort((left, right) => right.rank_score - left.rank_score)
        .slice(0, 10),
    [menuRank]
  );

  const segmentRows = useMemo(
    () => Object.entries(segments || {}).map(([name, data]) => ({ name, data })),
    [segments]
  );

  return (
    <section className="page-grid">
      <section className="split-grid">
        <article className="panel">
          <h2>Top 10 Meals Visual</h2>
          <div className="bar-list">
            {topMealsRows.map((meal) => (
              <article key={meal.item} className="bar-row">
                <div className="bar-head">
                  <strong>{meal.item}</strong>
                  <span>{meal.count} orders</span>
                </div>
                <div className="bar-track">
                  <div className="bar-fill" style={{ width: `${meal.width}%` }} />
                </div>
                <small>share {toPercent(meal.share)}</small>
              </article>
            ))}
          </div>
          {!topMealsRows.length ? <p className="muted">No top meal data.</p> : null}
        </article>

        <article className="panel">
          <h2>Homepage Ranking Simulation</h2>
          <div className="rank-table">
            {rankRows.map((item, index) => (
              <article key={item.item} className="rank-card">
                <p className="position">#{index + 1}</p>
                <div>
                  <h4>{item.item}</h4>
                  <small>
                    rank {toFixed(item.rank_score, 3)} | impact {toFixed(item.impact, 2)}
                  </small>
                </div>
              </article>
            ))}
          </div>
        </article>
      </section>

      <article className="panel">
        <h2>Segment Dashboard</h2>
        <div className="segment-grid">
          {segmentRows.map((segment) => (
            <article key={segment.name} className="segment-card">
              <div className="segment-head">
                <h4>{segment.name}</h4>
                <span>{segment.data.n_tx} tx</span>
              </div>
              <p>
                Engine: <strong>{segment.data.engine}</strong>
              </p>
              <p>
                minsup {segment.data.minsup} | minconf {segment.data.minconf}
              </p>
              <p>Holdout hit-rate {toPercent(segment.data.holdout_mean_hr)}</p>
              <p>Top ranked item: {segment.data.menu_rank_top10?.[0]?.item || "N/A"}</p>
              <div className="segment-promos">
                {(segment.data.promos_top3 || []).map((promo, index) => (
                  <span key={`promo-${index}`}>{promo.promo}</span>
                ))}
              </div>
            </article>
          ))}
        </div>
        {!segmentRows.length ? (
          <p className="muted">No segment snapshot for this dataset yet.</p>
        ) : null}
      </article>

      <article className="panel">
        <h2>Learning Iteration Notes</h2>
        <div className="notes-grid">
          <div className="note-card">
            <p>Drift Score</p>
            <h3>{toFixed(recommendations.drift?.js, 4)}</h3>
            <small>
              Jensen-Shannon distance between previous and current distribution
            </small>
          </div>
          <div className="note-card">
            <p>Long-term Weight</p>
            <h3>{toPercent(recommendations.blend?.w_long)}</h3>
            <small>Stable purchasing behavior emphasis</small>
          </div>
          <div className="note-card">
            <p>Recent Weight</p>
            <h3>{toPercent(recommendations.blend?.w_recent)}</h3>
            <small>Recent trend emphasis</small>
          </div>
        </div>
      </article>
    </section>
  );
}

export default AnalysisPage;
