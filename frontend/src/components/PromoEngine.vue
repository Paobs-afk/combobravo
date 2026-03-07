<template>
  <section class="promo-engine">
    <article v-if="!promos.length" class="promo-empty">
      No promo candidate for this iteration. Try another dataset/iteration.
    </article>
    <article v-for="(promo, index) in promos" :key="`${promo.promo}-${index}`" class="promo-item">
      <div class="promo-head">
        <p class="promo-tag">{{ promo.promo }}</p>
      </div>
      <p class="promo-bundle">{{ promo.bundle.join(" + ") }}</p>
      <p class="promo-logic">{{ promo.why }}</p>
    </article>
  </section>
</template>

<script setup>
defineProps({
  promos: {
    type: Array,
    default: () => [],
  },
});
</script>

<style scoped>
.promo-engine {
  display: grid;
  gap: 12px;
}

.promo-item {
  border: 1px solid #f6cec8;
  border-radius: 14px;
  padding: 12px;
  background: #fff;
}

.promo-head {
  display: flex;
  justify-content: space-between;
}

.promo-tag {
  margin: 0;
  background: #af1f14;
  color: #fff;
  padding: 5px 10px;
  border-radius: 999px;
  font-size: 0.72rem;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.promo-bundle {
  margin: 10px 0 0;
  color: #3b1310;
  font-weight: 700;
}

.promo-logic {
  margin: 8px 0 0;
  color: #7d413b;
  font-size: 0.84rem;
}

.promo-empty {
  border: 1px dashed #f1b5af;
  border-radius: 12px;
  padding: 16px;
  color: #8e4c45;
  background: #fff9f8;
}
</style>
