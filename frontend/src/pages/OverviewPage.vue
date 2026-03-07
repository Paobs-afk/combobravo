<template>
  <section class="page-grid">
    <article class="panel">
      <h2>System Summary</h2>
      <div class="kpi-grid">
        <div class="kpi">
          <p>Transactions</p>
          <h3>{{ recommendations.n_transactions || 0 }}</h3>
        </div>
        <div class="kpi">
          <p>Unique Items</p>
          <h3>{{ recommendations.n_unique_items || 0 }}</h3>
        </div>
        <div class="kpi">
          <p>Engine</p>
          <h3>{{ recommendations.engine_longterm || "-" }}</h3>
        </div>
        <div class="kpi">
          <p>Coverage</p>
          <h3>{{ toPercent(recommendations.system_metrics?.coverage_top_rules) }}</h3>
        </div>
      </div>
    </article>

    <article class="panel">
      <h2>Recommendation Notes</h2>
      <p v-for="(note, index) in notes" :key="`note-${index}`">{{ note }}</p>
      <p v-if="loading" class="muted">Refreshing data...</p>
    </article>

    <article class="panel">
      <h2>Top Bundles</h2>
      <div class="bundle-grid">
        <BundleCard
          v-for="(bundle, index) in bundles"
          :key="`${bundle.name}-${index}`"
          :bundle="bundle"
          :index="index + 1"
        />
      </div>
      <p v-if="!bundles.length" class="muted">No bundle generated in this iteration.</p>
    </article>

    <article class="panel">
      <h2>Promo Suggestions</h2>
      <PromoEngine :promos="recommendations.promos || []" />
    </article>
  </section>
</template>

<script setup>
import { computed } from "vue";
import BundleCard from "../components/BundleCard.vue";
import PromoEngine from "../components/PromoEngine.vue";

const props = defineProps({
  loading: { type: Boolean, default: false },
  recommendations: { type: Object, default: () => ({}) },
  rules: { type: Array, default: () => [] },
  topMeals: { type: Array, default: () => [] },
});

const toPercent = (value) => `${(Number(value || 0) * 100).toFixed(1)}%`;

const bundles = computed(() => {
  const source = props.recommendations.top_bundles || [];
  return source.map((bundle, index) => ({
    name: `Combo ${index + 1}`,
    items: bundle.items || [],
    support: Number(bundle.support || 0),
    confidence: Number(bundle.confidence || 0),
    lift: Number(bundle.lift || 0),
    why: bundle.why || "",
  }));
});

const notes = computed(() => {
  const list = [];
  if (props.topMeals?.[0]) {
    list.push(`Top meal overall: ${props.topMeals[0].item} (${props.topMeals[0].count} orders).`);
  }
  if (props.recommendations.business_insights?.length) {
    list.push(...props.recommendations.business_insights.slice(0, 3));
  }
  if (!list.length) {
    list.push("No insight generated yet.");
  }
  return list;
});
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

.kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}

.kpi {
  border: 1px solid #f0d2ce;
  border-radius: 10px;
  padding: 10px;
  background: #fffdfd;
}

.kpi p {
  margin: 0;
  font-size: 0.72rem;
  color: #89443d;
  text-transform: uppercase;
}

.kpi h3 {
  margin: 6px 0 0;
}

.bundle-grid {
  display: grid;
  gap: 10px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.muted {
  color: #8c4d46;
}

@media (max-width: 960px) {
  .kpi-grid,
  .bundle-grid {
    grid-template-columns: 1fr;
  }
}
</style>
