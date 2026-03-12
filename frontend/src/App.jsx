import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { NavLink, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import TabIcon from "./components/TabIcon";
import AnalysisPage from "./pages/AnalysisPage";
import AboutPage from "./pages/AboutPage";
import IterationsPage from "./pages/IterationsPage";
import MenuPage from "./pages/MenuPage";
import OverviewPage from "./pages/OverviewPage";
import RulesPage from "./pages/RulesPage";
import UploadPage from "./pages/UploadPage";
import { fetchDashboardData, fetchDatasets, runDataset } from "./services/api";

const THEME_KEY = "combobravo_theme";

const NAV_ITEMS = [
  { path: "/", label: "Dashboard", icon: "dashboard" },
  { path: "/menu", label: "Menu", icon: "menu" },
  { path: "/analysis", label: "Analytics", icon: "analysis" },
  { path: "/rules", label: "Rules", icon: "rules" },
  { path: "/iterations", label: "Iterations", icon: "iterations" },
  { path: "/about", label: "About", icon: "about" },
  { path: "/upload", label: "Upload", icon: "upload" },
];

const PAGE_META = {
  "/": { title: "ComboBravo Dashboard", icon: "dashboard" },
  "/menu": { title: "Menu Experience", icon: "menu" },
  "/analysis": { title: "Detailed Analytics", icon: "analysis" },
  "/rules": { title: "Rule Intelligence", icon: "rules" },
  "/iterations": { title: "Iteration Intelligence", icon: "iterations" },
  "/about": { title: "About ComboBravo", icon: "about" },
  "/upload": { title: "Dataset Upload", icon: "upload" },
};

const detectTheme = () => {
  const stored = window.localStorage.getItem(THEME_KEY);
  if (stored === "light" || stored === "dark") {
    return stored;
  }
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
};

function App() {
  const navigate = useNavigate();
  const location = useLocation();

  const [datasets, setDatasets] = useState([]);
  const [dataset, setDataset] = useState("all");
  const [iteration, setIteration] = useState(3);

  const [recommendations, setRecommendations] = useState({});
  const [rules, setRules] = useState([]);
  const [menuRank, setMenuRank] = useState([]);
  const [segments, setSegments] = useState({});
  const [topMeals, setTopMeals] = useState([]);
  const [charts, setCharts] = useState([]);
  const [chartsByDataset, setChartsByDataset] = useState({});
  const [iterationHistory, setIterationHistory] = useState([]);

  const [loading, setLoading] = useState(false);
  const [training, setTraining] = useState(false);
  const [error, setError] = useState("");
  const [warning, setWarning] = useState("");
  const [theme, setTheme] = useState("light");

  const latestRequest = useRef(0);

  const selectedDatasetMeta = useMemo(
    () => datasets.find((entry) => entry.id === dataset) || null,
    [dataset, datasets]
  );

  const maxIterationAvailable = useMemo(() => {
    const batchCount = Number(selectedDatasetMeta?.batch_count || 0);
    return Math.max(3, batchCount || 0);
  }, [selectedDatasetMeta]);

  const iterationOptions = useMemo(
    () => Array.from({ length: maxIterationAvailable }, (_, index) => index + 1),
    [maxIterationAvailable]
  );

  const activeDatasetLabel = useMemo(() => {
    const found = datasets.find((entry) => entry.id === dataset);
    return found?.label || (dataset === "all" ? "All Datasets" : dataset || "-");
  }, [dataset, datasets]);

  const pageMeta = useMemo(() => {
    if (location.pathname.startsWith("/menu")) return PAGE_META["/menu"];
    if (location.pathname.startsWith("/analysis")) return PAGE_META["/analysis"];
    if (location.pathname.startsWith("/rules")) return PAGE_META["/rules"];
    if (location.pathname.startsWith("/iterations")) return PAGE_META["/iterations"];
    if (location.pathname.startsWith("/about")) return PAGE_META["/about"];
    if (location.pathname.startsWith("/upload")) return PAGE_META["/upload"];
    return PAGE_META["/"];
  }, [location.pathname]);

  const refreshDatasetsOnly = useCallback(async () => {
    try {
      const list = await fetchDatasets();
      const normalized = (Array.isArray(list) ? list : [])
        .map((entry) => ({
          ...entry,
          id: entry?.id || entry?.dataset_key || entry?.folder || "",
          label: entry?.label || entry?.dataset_key || entry?.folder || "Unnamed Dataset",
          batch_count: Number(entry?.batch_count || 0),
        }))
        .filter((entry) => Boolean(entry.id) && entry.id !== "all");

      const allBatchCount = normalized.reduce(
        (maxValue, entry) => Math.max(maxValue, Number(entry.batch_count || 0)),
        0
      );

      const withAll = [
        { id: "all", label: "All Datasets", dataset_key: "all", batch_count: allBatchCount },
        ...normalized,
      ];
      setDatasets(withAll);

      if (!normalized.length) {
        setWarning(
          "No datasets found in Supabase yet. Run schema setup, then upload at least one CSV."
        );
      }

      setDataset((previous) => {
        if (withAll.some((entry) => entry.id === previous)) {
          return previous;
        }
        return withAll[0]?.id || "all";
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
      const result = await fetchDashboardData(dataset, iteration, maxIterationAvailable);
      if (requestId !== latestRequest.current) {
        return;
      }

      setRecommendations(result.data.recommendations || {});
      setRules(result.data.rules || []);
      setMenuRank(result.data.menuRank || []);
      setSegments(result.data.segments || {});
      setTopMeals(result.data.topMeals || []);
      setCharts(result.data.charts || []);
      setChartsByDataset(result.data.chartsByDataset || {});
      setIterationHistory(result.data.iterationHistory || []);

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
  }, [dataset, iteration, datasets.length, maxIterationAvailable]);

  const retrainDataset = useCallback(async () => {
    if (!dataset) {
      return;
    }
    setTraining(true);
    setError("");

    try {
      await runDataset(dataset, maxIterationAvailable);
      await loadDashboard();
    } catch (trainError) {
      setError(trainError.message);
    } finally {
      setTraining(false);
    }
  }, [dataset, loadDashboard, maxIterationAvailable]);

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
    setTheme(detectTheme());
    refreshDatasetsOnly();
  }, [refreshDatasetsOnly]);

  useEffect(() => {
    loadDashboard();
  }, [loadDashboard]);

  useEffect(() => {
    setIteration((previous) => Math.min(Math.max(previous, 1), maxIterationAvailable));
  }, [maxIterationAvailable]);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    window.localStorage.setItem(THEME_KEY, theme);
  }, [theme]);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="side-brand">
          <div className="brand-logo-wrap" title="ComboBravo">
            <img className="logo-image" src="/logo.png" alt="ComboBravo logo" />
          </div>
          <div className="brand-text">
            <p className="eyebrow">Market Basket AI</p>
            <h1>ComboBravo</h1>
            <small>Self-Learning Recommendation System</small>
          </div>
        </div>

        <nav className="side-nav">
          {NAV_ITEMS.map((item) => (
            <NavLink key={item.path} to={item.path} end={item.path === "/"}>
              <span className="nav-icon">
                <TabIcon name={item.icon} />
              </span>
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>

          <div className="side-status">
            <p>Active Dataset</p>
            <strong>{activeDatasetLabel}</strong>
            <small>
              Iteration {iteration} / {maxIterationAvailable}
            </small>
          </div>
        </aside>

      <section className="workspace">
        <header className="topbar">
          <div className="topbar-title">
            <span className="page-logo">
              <TabIcon name={pageMeta.icon} />
            </span>
            <div>
              <h2>{pageMeta.title}</h2>
              <p>Engine: {recommendations.engine_longterm || "-"}</p>
            </div>
          </div>

          <div className="controls">
            <label>
              Dataset Filter
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
                {iterationOptions.map((value) => (
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

            <button
              className="theme-toggle"
              onClick={() => setTheme((old) => (old === "dark" ? "light" : "dark"))}
              type="button"
              aria-label="Toggle color mode"
            >
              <TabIcon name={theme === "dark" ? "sun" : "moon"} />
              <span>{theme === "dark" ? "Light" : "Dark"}</span>
            </button>
          </div>
        </header>

        <main className="content">
          <section className="status-strip">
            <p>
              <span>Active:</span> {activeDatasetLabel} | Iteration {iteration}/{maxIterationAvailable}
            </p>
            {dataset === "all" ? (
              <p className="status-note">(showing merged metrics from all datasets)</p>
            ) : null}
            <p>
              <span>Rules:</span> {recommendations.system_metrics?.n_rules_blended || 0}
            </p>
            <p>
              <span>Charts:</span> {charts.length || Object.keys(chartsByDataset || {}).length}
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
                  charts={charts}
                  chartsByDataset={chartsByDataset}
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
                  charts={charts}
                  chartsByDataset={chartsByDataset}
                  iterationHistory={iterationHistory}
                />
              }
            />
            <Route
              path="/rules"
              element={<RulesPage rules={rules} menuRank={menuRank} recommendations={recommendations} />}
            />
            <Route
              path="/iterations"
              element={
                <IterationsPage
                  iterationHistory={iterationHistory}
                  recommendations={recommendations}
                  charts={charts}
                  chartsByDataset={chartsByDataset}
                />
              }
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
            <Route
              path="/about"
              element={<AboutPage activeDatasetLabel={activeDatasetLabel} iteration={iteration} />}
            />
          </Routes>
        </main>
      </section>
    </div>
  );
}

export default App;
