import TabIcon from "../components/TabIcon";

function AboutPage({ activeDatasetLabel = "-", iteration = 3 }) {
  return (
    <section className="page-grid">
      <article className="panel">
        <div className="tab-header">
          <span className="tab-avatar">
            <TabIcon name="about" />
          </span>
          <div>
            <h2>About ComboBravo</h2>
            <p className="muted">
              A market-basket recommendation system that learns from transactions and updates business
              recommendations over time.
            </p>
          </div>
        </div>
      </article>

      <article className="panel">
        <h2>Overall Goal (Rubric-Friendly Summary)</h2>
        <ul className="insight-list">
          <li>Ingest transaction data (A/B/custom datasets, including batch uploads).</li>
          <li>Mine patterns and association rules with full metrics.</li>
          <li>Score and rank recommendations for real business decisions.</li>
          <li>Retrain automatically when new data arrives to show self-learning behavior.</li>
          <li>Provide outputs like bundles, cross-sell, homepage ranking, promos, and insights.</li>
        </ul>
      </article>

      <section className="split-grid">
        <article className="panel">
          <h2>What Each Iteration Means</h2>
          <div className="notes-grid">
            <div className="note-card">
              <p>Iteration 1</p>
              <h3>Baseline Learn</h3>
              <small>The system trains from the first batch and builds initial rules.</small>
            </div>
            <div className="note-card">
              <p>Iteration 2</p>
              <h3>Updated Learn</h3>
              <small>New batch is added. Rules and rankings are recomputed.</small>
            </div>
            <div className="note-card">
              <p>Iteration 3+</p>
              <h3>Adaptive Learn</h3>
              <small>
                Additional data updates model behavior (drift, coverage, uplift, rule movement).
              </small>
            </div>
          </div>
        </article>

        <article className="panel">
          <h2>What Retrain Does</h2>
          <ul className="insight-list">
            <li>Re-runs the mining engine for the selected dataset filter.</li>
            <li>Recomputes itemsets/rules and scoring metrics.</li>
            <li>Updates charts, recommendations, and iteration history files.</li>
            <li>Lets you compare how outputs changed between iterations.</li>
          </ul>
          <p className="muted">
            Current context: <strong>{activeDatasetLabel}</strong>, Iteration <strong>{iteration}</strong>.
          </p>
        </article>
      </section>

      <article className="panel">
        <h2>How This Matches Your Rubrics</h2>
        <div className="kpi-grid kpi-grid-3">
          <div className="kpi">
            <p>Business Context</p>
            <h3>Users + Decisions</h3>
            <small>Owner, cashier, admin, customer workflows are represented.</small>
          </div>
          <div className="kpi">
            <p>MBA Correctness</p>
            <h3>Full Metrics</h3>
            <small>Support, confidence, lift, leverage, conviction are shown in UI.</small>
          </div>
          <div className="kpi">
            <p>Self-Learning</p>
            <h3>Iteration Loop</h3>
            <small>Iteration history and retraining demonstrate adaptation over time.</small>
          </div>
          <div className="kpi">
            <p>Evaluation</p>
            <h3>Trend Tracking</h3>
            <small>Coverage, drift, and uplift comparisons are available per iteration.</small>
          </div>
          <div className="kpi">
            <p>Data Handling</p>
            <h3>Batch Upload</h3>
            <small>Multiple CSV files can be uploaded as batches for one dataset.</small>
          </div>
          <div className="kpi">
            <p>System Output</p>
            <h3>Business Ready</h3>
            <small>Bundles, FBT, cross-sell, promo ideas, and ranking are generated.</small>
          </div>
        </div>
      </article>
    </section>
  );
}

export default AboutPage;
