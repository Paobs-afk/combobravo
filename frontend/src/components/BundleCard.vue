<template>
  <article class="bundle-card">
    <div class="bundle-top">
      <p class="bundle-id">Bundle {{ index }}</p>
      <h3>{{ bundle.name }}</h3>
    </div>
    <div class="bundle-items">
      <span v-for="item in bundle.items" :key="item" class="tag">{{ item }}</span>
    </div>
    <p class="bundle-why">{{ bundle.why }}</p>
    <div class="metrics">
      <span>Support {{ toPercent(bundle.support) }}</span>
      <span>Confidence {{ toPercent(bundle.confidence) }}</span>
      <span class="lift">Lift {{ toFloat(bundle.lift) }}x</span>
    </div>
  </article>
</template>

<script setup>
defineProps({
  bundle: {
    type: Object,
    required: true,
  },
  index: {
    type: Number,
    default: 1,
  },
});

const toPercent = (value) => `${(Number(value || 0) * 100).toFixed(1)}%`;
const toFloat = (value) => Number(value || 0).toFixed(2);
</script>

<style scoped>
.bundle-card {
  border: 1px solid #f5b7b1;
  border-radius: 14px;
  background: linear-gradient(140deg, #fff, #fff8f8);
  padding: 14px;
}

.bundle-top {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
}

.bundle-id {
  margin: 0;
  font-size: 0.7rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #aa2e25;
  font-weight: 700;
}

h3 {
  margin: 0;
  font-size: 1.05rem;
  color: #3d1713;
}

.bundle-items {
  margin-top: 10px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.tag {
  font-size: 0.8rem;
  border-radius: 999px;
  padding: 5px 10px;
  background: #fff;
  border: 1px solid #f4d7d4;
  color: #6f221b;
}

.bundle-why {
  margin: 12px 0 0;
  color: #7d413b;
  font-size: 0.85rem;
}

.metrics {
  margin-top: 10px;
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  font-size: 0.78rem;
  color: #6f221b;
}

.lift {
  color: #9f1002;
  font-weight: 700;
}
</style>
