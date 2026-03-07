<template>
  <section class="page-grid">
    <article class="panel">
      <h2>Cart Recommendation Tool</h2>
      <label class="control">
        Select Meal
        <select v-model="selectedItem">
          <option v-for="item in availableItems" :key="item" :value="item">{{ item }}</option>
        </select>
      </label>
      <div class="suggestions">
        <p v-for="suggestion in suggestions" :key="suggestion.item">
          Add <strong>{{ suggestion.item }}</strong> - {{ suggestion.why }}
        </p>
        <p v-if="!suggestions.length" class="muted">No suggestion for this selected meal.</p>
      </div>
    </article>

    <article class="panel">
      <h2>Rule Explorer</h2>
      <label class="control">
        Search Rules
        <input v-model="query" type="text" placeholder="Search item name..." />
      </label>
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
          <tr v-for="rule in filteredRules.slice(0, 30)" :key="rule.key">
            <td>{{ rule.label }}</td>
            <td>{{ toPercent(rule.support) }}</td>
            <td>{{ toPercent(rule.confidence) }}</td>
            <td>{{ toFixed(rule.lift, 2) }}</td>
            <td>{{ toFixed(rule.leverage, 4) }}</td>
            <td>{{ toFixed(rule.conviction, 2) }}</td>
          </tr>
        </tbody>
      </table>
      <p v-if="!filteredRules.length" class="muted">No rules matched this filter.</p>
    </article>
  </section>
</template>

<script setup>
import { computed, ref, watch } from "vue";

const props = defineProps({
  rules: { type: Array, default: () => [] },
  menuRank: { type: Array, default: () => [] },
  recommendations: { type: Object, default: () => ({}) },
});

const query = ref("");
const selectedItem = ref("Burger");

const toFixed = (value, digits = 2) => Number(value || 0).toFixed(digits);
const toPercent = (value) => `${(Number(value || 0) * 100).toFixed(1)}%`;
const parseItems = (raw) =>
  String(raw || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);

const normalizedRules = computed(() =>
  props.rules.map((row) => {
    const antecedents = parseItems(row.antecedents);
    const consequents = parseItems(row.consequents);
    return {
      key: row.key || `${antecedents.join("|")}=>${consequents.join("|")}`,
      antecedents,
      consequents,
      label: `${antecedents.join(" + ")} -> ${consequents.join(" + ")}`,
      support: Number(row.support || 0),
      confidence: Number(row.confidence || 0),
      lift: Number(row.lift || 0),
      leverage: Number(row.leverage || 0),
      conviction: Number(row.conviction || 0),
      blendScore: Number(row.blend_score || 0),
    };
  })
);

const filteredRules = computed(() => {
  const keyword = query.value.trim().toLowerCase();
  if (!keyword) {
    return normalizedRules.value;
  }
  return normalizedRules.value.filter((rule) => rule.label.toLowerCase().includes(keyword));
});

const availableItems = computed(() => {
  const items = props.menuRank.map((row) => row.item);
  if (items.length) {
    return items;
  }
  const set = new Set();
  normalizedRules.value.forEach((rule) => {
    rule.antecedents.forEach((item) => set.add(item));
    rule.consequents.forEach((item) => set.add(item));
  });
  return [...set];
});

const suggestions = computed(() => {
  const map = props.recommendations.cart_targets || {};
  if (Array.isArray(map[selectedItem.value])) {
    return map[selectedItem.value];
  }
  const picks = [];
  for (const rule of normalizedRules.value) {
    if (!rule.antecedents.includes(selectedItem.value)) {
      continue;
    }
    for (const item of rule.consequents) {
      if (item !== selectedItem.value) {
        picks.push({
          item,
          score: rule.blendScore,
          why: `conf ${toPercent(rule.confidence)}, lift ${toFixed(rule.lift, 2)}`,
        });
      }
    }
  }
  return picks.sort((left, right) => right.score - left.score).slice(0, 6);
});

watch(
  availableItems,
  (items) => {
    if (!items.includes(selectedItem.value)) {
      selectedItem.value = items[0] || "";
    }
  },
  { immediate: true }
);
</script>

<style scoped>
.page-grid {
  display: grid;
  gap: 12px;
}

.panel {
  border: 1px solid #efc7c2;
  border-radius: 12px;
  background: #fff;
  padding: 14px;
}

.control {
  display: grid;
  gap: 6px;
  margin-bottom: 10px;
  font-size: 0.75rem;
  text-transform: uppercase;
  color: #7a362f;
  font-weight: 700;
}

input,
select {
  border: 1px solid #f1c8c2;
  border-radius: 10px;
  background: #fff;
  padding: 8px 10px;
}

.suggestions p {
  margin: 7px 0 0;
}

table {
  width: 100%;
  border-collapse: collapse;
}

th,
td {
  border-bottom: 1px solid #f0d7d4;
  padding: 8px;
  text-align: left;
}

th {
  font-size: 0.74rem;
  text-transform: uppercase;
  color: #8f4740;
}

.muted {
  color: #8c4d46;
}
</style>
