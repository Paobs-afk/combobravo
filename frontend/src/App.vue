<template>
  <div class="app-shell">
    <header class="top-nav">
      <div class="brand">
        <p class="eyebrow">Market Basket Analysis Platform</p>
        <h1>ComboBravo</h1>
      </div>

      <nav class="nav-links">
        <RouterLink to="/">Overview</RouterLink>
        <RouterLink to="/analysis">Analysis</RouterLink>
        <RouterLink to="/rules">Rules</RouterLink>
        <RouterLink to="/upload">Upload</RouterLink>
      </nav>

      <div class="controls">
        <label>
          Dataset
          <select v-model="dataset">
            <option v-for="entry in datasets" :key="entry.id" :value="entry.id">
              {{ entry.label }}
            </option>
          </select>
        </label>

        <label>
          Iteration
          <div class="iteration">
            <button
              v-for="value in [1, 2, 3]"
              :key="value"
              :class="{ active: iteration === value }"
              @click="iteration = value"
            >
              {{ value }}
            </button>
          </div>
        </label>

        <button class="action" :disabled="loading || training" @click="retrainDataset">
          {{ training ? "Re-training..." : "Re-train" }}
        </button>
      </div>
    </header>

    <main class="content">
      <section v-if="error" class="banner error">{{ error }}</section>
      <section v-if="warning" class="banner warning">{{ warning }}</section>

      <RouterView
        :dataset="dataset"
        :datasets="datasets"
        :iteration="iteration"
        :loading="loading"
        :recommendations="recommendations"
        :rules="rules"
        :menu-rank="menuRank"
        :segments="segments"
        :top-meals="topMeals"
        @uploaded="handleUploaded"
        @refresh-request="refreshDatasetsOnly"
      />
    </main>
  </div>
</template>

<script setup>
import { ref, watch } from "vue";
import { RouterLink, RouterView, useRouter } from "vue-router";
import { fetchDashboardData, fetchDatasets, runDataset } from "./services/api";

const router = useRouter();

const datasets = ref([]);
const dataset = ref("A");
const iteration = ref(3);

const recommendations = ref({});
const rules = ref([]);
const menuRank = ref([]);
const segments = ref({});
const topMeals = ref([]);

const loading = ref(false);
const training = ref(false);
const error = ref("");
const warning = ref("");

let latestRequest = 0;

const refreshDatasetsOnly = async () => {
  try {
    const list = await fetchDatasets();
    datasets.value = list;
    if (list.length && !list.some((entry) => entry.id === dataset.value)) {
      dataset.value = list[0].id;
    }
  } catch (datasetError) {
    error.value = `Failed to load dataset list: ${datasetError.message}`;
  }
};

const loadDashboard = async () => {
  const requestId = ++latestRequest;
  loading.value = true;
  error.value = "";
  warning.value = "";

  try {
    const result = await fetchDashboardData(dataset.value, iteration.value);
    if (requestId !== latestRequest) {
      return;
    }

    recommendations.value = result.data.recommendations || {};
    rules.value = result.data.rules || [];
    menuRank.value = result.data.menuRank || [];
    segments.value = result.data.segments || {};
    topMeals.value = result.data.topMeals || [];

    const requiredErrors = result.errors.filter((entry) => entry.required);
    const optionalErrors = result.errors.filter((entry) => !entry.required);
    if (requiredErrors.length) {
      error.value = requiredErrors.map((entry) => entry.message).join(" | ");
    }
    if (optionalErrors.length) {
      warning.value = `Some sections failed: ${optionalErrors
        .map((entry) => entry.key)
        .join(", ")}`;
    }
  } catch (loadError) {
    if (requestId === latestRequest) {
      error.value = loadError.message;
    }
  } finally {
    if (requestId === latestRequest) {
      loading.value = false;
    }
  }
};

const retrainDataset = async () => {
  training.value = true;
  error.value = "";
  try {
    await runDataset(dataset.value, 3);
    await loadDashboard();
  } catch (trainError) {
    error.value = trainError.message;
  } finally {
    training.value = false;
  }
};

const handleUploaded = async (datasetId) => {
  await refreshDatasetsOnly();
  dataset.value = datasetId;
  iteration.value = 3;
  await loadDashboard();
  router.push("/");
};

watch([dataset, iteration], loadDashboard, { immediate: true });
refreshDatasetsOnly();
</script>

<style>
@import url("https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Nunito:wght@400;600;700;800&display=swap");

:root {
  --ink: #431611;
  --red: #ae2318;
  --line: #f0c8c2;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  font-family: "Nunito", sans-serif;
  background: linear-gradient(180deg, #fffdfd 0%, #fff7f6 100%);
  color: var(--ink);
}

.top-nav {
  position: sticky;
  top: 0;
  z-index: 30;
  background: #fff;
  border-bottom: 2px solid var(--line);
  display: grid;
  grid-template-columns: auto auto 1fr;
  gap: 14px;
  align-items: center;
  padding: 10px 16px;
}

.eyebrow {
  margin: 0;
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: #8c453d;
}

h1 {
  margin: 0;
  font-family: "Bebas Neue", sans-serif;
  color: var(--red);
  line-height: 1;
}

.nav-links {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.nav-links a {
  text-decoration: none;
  color: #7a3028;
  font-weight: 700;
  padding: 7px 10px;
  border-radius: 8px;
}

.nav-links a.router-link-active {
  background: #ffe0dc;
  color: #962016;
}

.controls {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.controls label {
  display: grid;
  gap: 4px;
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  font-weight: 700;
}

.controls select {
  border: 1px solid var(--line);
  border-radius: 10px;
  background: #fff;
  color: var(--ink);
  padding: 8px 10px;
}

.iteration {
  display: flex;
  border: 1px solid var(--line);
  border-radius: 10px;
  overflow: hidden;
}

.iteration button {
  border: 0;
  padding: 8px 9px;
  background: #fff;
  color: #8d2318;
  cursor: pointer;
  font-weight: 700;
}

.iteration button.active {
  background: #ffd8d3;
}

.action {
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 8px 11px;
  color: #8f1f14;
  background: #fff4f2;
  font-weight: 700;
  cursor: pointer;
}

.action:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.content {
  width: min(1180px, 95vw);
  margin: 14px auto 28px;
  display: grid;
  gap: 10px;
}

.banner {
  border-radius: 10px;
  padding: 10px 12px;
  font-weight: 700;
}

.banner.error {
  border: 1px solid #ef9d93;
  background: #ffe5e1;
  color: #7f1c13;
}

.banner.warning {
  border: 1px solid #f0cc93;
  background: #fff5e5;
  color: #8a5a12;
}

@media (max-width: 1080px) {
  .top-nav {
    grid-template-columns: 1fr;
  }

  .controls {
    margin-left: 0;
  }
}
</style>
