const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");

const withBase = (url) => {
  if (/^https?:\/\//i.test(url)) {
    return url;
  }
  return `${API_BASE_URL}${url}`;
};

const parseError = async (response) => {
  try {
    const payload = await response.json();
    if (payload?.detail) {
      return String(payload.detail);
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

export const fetchDashboardData = async (dataset, iteration) => {
  const endpoints = [
    { key: "recommendations", required: true, url: `/api/recommendations/${dataset}/${iteration}` },
    { key: "rules", required: false, url: `/api/rules/${dataset}/${iteration}` },
    { key: "menuRank", required: false, url: `/api/menu-rank/${dataset}/${iteration}` },
    { key: "segments", required: false, url: `/api/segments/${dataset}/${iteration}` },
    { key: "topMeals", required: false, url: `/api/top-meals/${dataset}?limit=10` },
  ];

  const settled = await Promise.allSettled(endpoints.map((entry) => fetchJson(entry.url)));
  const data = {
    recommendations: {},
    rules: [],
    menuRank: [],
    segments: {},
    topMeals: [],
  };
  const errors = [];

  settled.forEach((result, index) => {
    const endpoint = endpoints[index];
    if (result.status === "fulfilled") {
      data[endpoint.key] = result.value;
      return;
    }
    errors.push({
      key: endpoint.key,
      required: endpoint.required,
      message: result.reason?.message || "Request failed",
    });
  });

  return { data, errors };
};

export const runDataset = (dataset, maxIteration = 3) =>
  fetchJson(`/api/run/${dataset}?max_iteration=${maxIteration}`, { method: "POST" });

export const uploadDataset = async (file, datasetName) => {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("dataset_name", datasetName || "uploaded");
  return fetchJson("/api/upload-dataset", {
    method: "POST",
    body: formData,
  });
};
