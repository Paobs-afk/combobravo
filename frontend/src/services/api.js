const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");

const withBase = (url) => {
  if (/^https?:\/\//i.test(url)) {
    return url;
  }
  return `${API_BASE_URL}${url}`;
};

export const buildApiUrl = (url) => withBase(url);

const parseError = async (response) => {
  const toText = (value) => {
    if (value == null) {
      return "";
    }
    if (typeof value === "string") {
      return value;
    }
    if (Array.isArray(value)) {
      return value
        .map((entry) => {
          if (typeof entry === "string") {
            return entry;
          }
          if (entry && typeof entry === "object") {
            const location = Array.isArray(entry.loc) ? entry.loc.join(" > ") : "";
            const message = entry.msg || JSON.stringify(entry);
            return location ? `${location}: ${message}` : message;
          }
          return String(entry);
        })
        .filter(Boolean)
        .join(" | ");
    }
    if (typeof value === "object") {
      if (typeof value.message === "string") {
        return value.message;
      }
      if (value.message != null) {
        const nested = toText(value.message);
        if (nested) {
          return nested;
        }
      }
      if (value.detail != null) {
        const nestedDetail = toText(value.detail);
        if (nestedDetail) {
          return nestedDetail;
        }
      }
      try {
        return JSON.stringify(value);
      } catch (_error) {
        return Object.prototype.toString.call(value);
      }
    }
    return String(value);
  };

  try {
    const rawText = await response.text();
    let payload = null;
    if (rawText) {
      try {
        payload = JSON.parse(rawText);
      } catch (_jsonError) {
        payload = rawText;
      }
    }
    if (payload && typeof payload === "object" && Object.prototype.hasOwnProperty.call(payload, "detail")) {
      const parsed = toText(payload.detail);
      if (parsed) {
        return parsed;
      }
    }
    const fallback = toText(payload);
    if (fallback) {
      return fallback;
    }
  } catch (_error) {
    // Ignore JSON parsing errors and fall back to status text.
  }
  return `${response.status} ${response.statusText}`;
};

export const fetchJson = async (url, options = {}) => {
  const response = await fetch(withBase(url), options);
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return response.json();
};

export const fetchDatasets = () => fetchJson("/api/datasets");

export const fetchDashboardData = async (dataset, iteration, maxIteration = 6) => {
  const safeMaxIteration = Math.max(Number(maxIteration) || 1, Number(iteration) || 1, 1);
  const endpoints = [
    { key: "overview", required: true, url: `/api/overview/${dataset}/${iteration}` },
    { key: "topMeals", required: false, url: `/api/top-meals/${dataset}?limit=10` },
    { key: "charts", required: false, url: `/api/charts/${dataset}/${iteration}` },
    {
      key: "iterationHistory",
      required: false,
      url: `/api/iteration-history/${dataset}?max_iteration=${safeMaxIteration}`,
    },
  ];

  const settled = await Promise.allSettled(endpoints.map((entry) => fetchJson(entry.url)));
  const data = {
    recommendations: {},
    rules: [],
    menuRank: [],
    segments: {},
    topMeals: [],
    perDataset: null,
    charts: [],
    chartsByDataset: {},
    iterationHistory: [],
  };
  const errors = [];

  settled.forEach((result, index) => {
    const endpoint = endpoints[index];
    if (result.status === "fulfilled") {
      if (endpoint.key === "overview") {
        const overviewRecs = result.value?.recommendations || {};
        if (result.value?.per_dataset) {
          overviewRecs.per_dataset = result.value.per_dataset;
          data.perDataset = result.value.per_dataset;
        }
        data.recommendations = overviewRecs;
        data.rules = result.value?.rules || [];
        data.menuRank = result.value?.menu_rank || [];
        data.segments = result.value?.segments || {};
      } else if (endpoint.key === "charts") {
        data.charts = result.value?.charts || [];
        if (result.value?.charts_by_dataset) {
          data.chartsByDataset = result.value.charts_by_dataset;
        }
      } else if (endpoint.key === "iterationHistory") {
        data.iterationHistory = Array.isArray(result.value) ? result.value : [];
      } else {
        data[endpoint.key] = result.value;
      }
      return;
    }
    errors.push({
      key: endpoint.key,
      required: endpoint.required,
      message: result.reason?.message || "Request failed",
    });
  });

  // if this is the overall view, the server may have returned perDataset
  // but topMeals are fetched separately. grab them per dataset here.
  if (dataset === "all" && data.perDataset) {
    const keys = Object.keys(data.perDataset);
    await Promise.all(
      keys.map(async (key) => {
        try {
          const meals = await fetchJson(`/api/top-meals/${key}?limit=10`);
          data.perDataset[key].topMeals = meals;
        } catch (_err) {
          // ignore failures
          data.perDataset[key].topMeals = [];
        }
      })
    );
  }

  return { data, errors };
};

export const runDataset = (dataset, maxIteration = 3) =>
  fetchJson(`/api/run/${dataset}?max_iteration=${maxIteration}`, { method: "POST" });

export const deleteDataset = (dataset) =>
  fetchJson(`/api/datasets/${encodeURIComponent(dataset)}`, { method: "DELETE" });

export const uploadDataset = async (files, datasetName, uploadMode = "replace") => {
  const uploadFiles = Array.isArray(files) ? files : [files];
  const formData = new FormData();
  uploadFiles.filter(Boolean).forEach((file) => {
    formData.append("files", file);
  });
  formData.append("dataset_name", datasetName || "uploaded");
  formData.append("upload_mode", uploadMode || "replace");
  return fetchJson("/api/upload-dataset", {
    method: "POST",
    body: formData,
  });
};
