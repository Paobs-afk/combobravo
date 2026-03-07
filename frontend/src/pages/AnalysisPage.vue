<template>
  <section class="page-grid">
    <article class="panel">
      <h2>Top 10 Meals Overall</h2>
      <table>
        <thead>
          <tr>
            <th>Meal</th>
            <th>Count</th>
            <th>Share</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="meal in topMeals.slice(0, 10)" :key="meal.item">
            <td>{{ meal.item }}</td>
            <td>{{ meal.count }}</td>
            <td>{{ toPercent(meal.share) }}</td>
          </tr>
        </tbody>
      </table>
      <p v-if="!topMeals.length" class="muted">No top meal data.</p>
    </article>

    <article class="panel">
      <h2>Homepage Ranking</h2>
      <div class="rank-list">
        <article v-for="item in rankRows" :key="item.item" class="rank-row">
          <div class="rank-head">
            <h4>{{ item.item }}</h4>
            <span>{{ toFixed(item.rank_score, 3) }}</span>
          </div>
          <div class="bar">
            <div class="fill" :style="{ width: `${Math.min(item.rank_score * 55, 100)}%` }"></div>
          </div>
          <p>Pop {{ item.pop }} | Impact {{ toFixed(item.impact, 2) }}</p>
        </article>
      </div>
    </article>

    <article class="panel">
      <h2>Segment Analysis</h2>
      <div class="segment-grid">
        <article v-for="segment in segmentRows" :key="segment.name" class="segment-card">
          <h4>{{ segment.name }}</h4>
          <p>Transactions: {{ segment.data.n_tx }}</p>
          <p>Engine: {{ segment.data.engine }}</p>
          <p>Thresholds: sup {{ segment.data.minsup }} / conf {{ segment.data.minconf }}</p>
          <p>Top meal: {{ segment.data.menu_rank_top10?.[0]?.item || "N/A" }}</p>
        </article>
      </div>
    </article>
  </section>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  topMeals: { type: Array, default: () => [] },
  menuRank: { type: Array, default: () => [] },
  segments: { type: Object, default: () => ({}) },
});

const toPercent = (value) => `${(Number(value || 0) * 100).toFixed(1)}%`;
const toFixed = (value, digits = 2) => Number(value || 0).toFixed(digits);

const rankRows = computed(() =>
  [...props.menuRank]
    .map((row) => ({
      item: row.item,
      pop: Number(row.pop || 0),
      impact: Number(row.impact || 0),
      rank_score: Number(row.rank_score || 0),
    }))
    .sort((left, right) => right.rank_score - left.rank_score)
    .slice(0, 10)
);

const segmentRows = computed(() =>
  Object.entries(props.segments || {}).map(([name, data]) => ({ name, data }))
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

.rank-list {
  display: grid;
  gap: 8px;
}

.rank-row {
  border: 1px solid #f3d7d3;
  border-radius: 10px;
  padding: 9px;
}

.rank-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}

.rank-head h4 {
  margin: 0;
}

.bar {
  margin-top: 7px;
  height: 8px;
  border-radius: 999px;
  background: #ffe7e3;
  overflow: hidden;
}

.fill {
  height: 100%;
  background: linear-gradient(90deg, #ff8f85, #be2b1f);
}

.rank-row p {
  margin: 7px 0 0;
  color: #7e413a;
  font-size: 0.8rem;
}

.segment-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.segment-card {
  border: 1px solid #f3d7d3;
  border-radius: 10px;
  padding: 10px;
  background: #fffdfd;
}

.segment-card h4 {
  margin: 0 0 6px;
  text-transform: capitalize;
}

.segment-card p {
  margin: 4px 0 0;
  font-size: 0.82rem;
  color: #6f3933;
}

.muted {
  color: #8c4d46;
}

@media (max-width: 960px) {
  .segment-grid {
    grid-template-columns: 1fr;
  }
}
</style>
