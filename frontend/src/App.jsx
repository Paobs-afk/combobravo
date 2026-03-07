import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { NavLink, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import AnalysisPage from "./pages/AnalysisPage";
import MenuPage from "./pages/MenuPage";
import OverviewPage from "./pages/OverviewPage";
import RulesPage from "./pages/RulesPage";
import UploadPage from "./pages/UploadPage";
import { fetchDashboardData, fetchDatasets, runDataset } from "./services/api";

function App() {
  const navigate = useNavigate();
  const location = useLocation();

  const [datasets, setDatasets] = useState([]);
  const [dataset, setDataset] = useState("A");
  const [iteration, setIteration] = useState(3);

  const [recommendations, setRecommendations] = useState({});
  const [rules, setRules] = useState([]);
  const [menuRank, setMenuRank] = useState([]);
  const [segments, setSegments] = useState({});
  const [topMeals, setTopMeals] = useState([]);

  const [loading, setLoading] = useState(false);
  const [training, setTraining] = useState(false);
  const [error, setError] = useState("");
  const [warning, setWarning] = useState("");

  const latestRequest = useRef(0);

  const activeDatasetLabel = useMemo(() => {
    const found = datasets.find((entry) => entry.id === dataset);
    return found?.label || dataset;
  }, [dataset, datasets]);

  const pageTitle = useMemo(() => {
    if (location.pathname === "/menu") return "Menu Experience";
    if (location.pathname === "/analysis") return "Visual Analytics";
    if (location.pathname === "/rules") return "Rule Intelligence";
    if (location.pathname === "/upload") return "Dataset Upload";
    return "ComboBravo Dashboard";
  }, [location.pathname]);

  const refreshDatasetsOnly = useCallback(async () => {
    try {
      const list = await fetchDatasets();
      const normalized = Array.isArray(list) ? list : [];
      setDatasets(normalized);
      if (!normalized.length) {
        setWarning(
          "No datasets found in Supabase yet. Run SQL schema, then run: npm run supabase:bootstrap."
        );
      }
      setDataset((previous) => {
        if (!normalized.length) {
          return previous;
        }
        return normalized.some((entry) => entry.id === previous)
          ? previous
          : normalized[0].id;
      });
    } catch (datasetError) {
      setError(`Failed to load dataset list: ${datasetError.message}`);
    }
  }, []);

  const loadDashboard = useCallback(async () => {
    if (!dataset || !datasets.length) {
      return;
    }

    const requestId = ++latestRequest.current;
    setLoading(true);
    setError("");
    setWarning("");

    try {
      const result = await fetchDashboardData(dataset, iteration);
      if (requestId !== latestRequest.current) {
        return;
      }

      setRecommendations(result.data.recommendations || {});
      setRules(result.data.rules || []);
      setMenuRank(result.data.menuRank || []);
      setSegments(result.data.segments || {});
      setTopMeals(result.data.topMeals || []);

      const requiredErrors = result.errors.filter((entry) => entry.required);
      const optionalErrors = result.errors.filter((entry) => !entry.required);
      if (requiredErrors.length) {
        setError(requiredErrors.map((entry) => entry.message).join(" | "));
      }
      if (optionalErrors.length) {
        setWarning(`Some sections failed: ${optionalErrors.map((entry) => entry.key).join(", ")}`);
      }
    } catch (loadError) {
      if (requestId === latestRequest.current) {
        setError(loadError.message);
      }
    } finally {
      if (requestId === latestRequest.current) {
        setLoading(false);
      }
    }
  }, [dataset, iteration, datasets.length]);

  const retrainDataset = useCallback(async () => {
    if (!dataset) {
      return;
    }
    setTraining(true);
    setError("");

    try {
      await runDataset(dataset, 3);
      await loadDashboard();
    } catch (trainError) {
      setError(trainError.message);
    } finally {
      setTraining(false);
    }
  }, [dataset, loadDashboard]);

  const handleUploaded = useCallback(
    async (datasetId) => {
      await refreshDatasetsOnly();
      if (datasetId) {
        setDataset(datasetId);
      }
      setIteration(3);
      navigate("/");
    },
    [navigate, refreshDatasetsOnly]
  );

  useEffect(() => {
    refreshDatasetsOnly();
  }, [refreshDatasetsOnly]);

  useEffect(() => {
    loadDashboard();
  }, [loadDashboard]);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="side-brand">
          <div className="logo-placeholder" title="ComboBravo">
            <span>CB</span>
          </div>
          <div className="brand-text">
            <p className="eyebrow">Market Basket AI</p>
            <h1>ComboBravo</h1>
          </div>
        </div>

        <nav className="side-nav">
          <NavLink to="/">Dashboard</NavLink>
          <NavLink to="/menu">Menu</NavLink>
          <NavLink to="/analysis">Visuals</NavLink>
          <NavLink to="/rules">Rules</NavLink>
          <NavLink to="/upload">Upload</NavLink>
        </nav>

        <div className="side-status">
          <p>Active Dataset</p>
          <strong>{activeDatasetLabel}</strong>
          <small>Iteration {iteration}</small>
        </div>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div>
            <h2>{pageTitle}</h2>
            <p>Engine: {recommendations.engine_longterm || "-"}</p>
          </div>

          <div className="controls">
            <label>
              Dataset
              <select value={dataset} onChange={(event) => setDataset(event.target.value)}>
                {datasets.map((entry) => (
                  <option key={entry.id} value={entry.id}>
                    {entry.label}
                  </option>
                ))}
              </select>
            </label>

            <label>
              Iteration
              <div className="iteration">
                {[1, 2, 3].map((value) => (
                  <button
                    key={value}
                    className={iteration === value ? "active" : ""}
                    onClick={() => setIteration(value)}
                    type="button"
                  >
                    {value}
                  </button>
                ))}
              </div>
            </label>

            <button className="action" disabled={loading || training} onClick={retrainDataset} type="button">
              {training ? "Training..." : "Retrain"}
            </button>
          </div>
        </header>

        <main className="content">
          <section className="status-strip">
            <p>
              <span>Active:</span> {activeDatasetLabel} | Iteration {iteration}
            </p>
            <p>
              <span>Rules:</span> {recommendations.system_metrics?.n_rules_blended || 0}
            </p>
          </section>

          {error ? <section className="banner error">{error}</section> : null}
          {warning ? <section className="banner warning">{warning}</section> : null}

          <Routes>
            <Route
              path="/"
              element={
                <OverviewPage
                  loading={loading}
                  recommendations={recommendations}
                  rules={rules}
                  menuRank={menuRank}
                  topMeals={topMeals}
                />
              }
            />
            <Route
              path="/menu"
              element={<MenuPage recommendations={recommendations} topMeals={topMeals} menuRank={menuRank} />}
            />
            <Route
              path="/analysis"
              element={
                <AnalysisPage
                  topMeals={topMeals}
                  menuRank={menuRank}
                  segments={segments}
                  recommendations={recommendations}
                />
              }
            />
            <Route
              path="/rules"
              element={<RulesPage rules={rules} menuRank={menuRank} recommendations={recommendations} />}
            />
            <Route
              path="/upload"
              element={
                <UploadPage
                  datasets={datasets}
                  onUploaded={handleUploaded}
                  onRefreshRequest={refreshDatasetsOnly}
                />
              }
            />
          </Routes>
        </main>
      </section>
    </div>
  );
}

export default App;
