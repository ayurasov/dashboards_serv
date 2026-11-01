<script setup>
/** Карточка графика: заголовок, пояснение, действия, содержимое с фиксированной высотой. */
defineProps({
  title: { type: String, required: true },
  hint: { type: String, default: '' },
  height: { type: [Number, String], default: 300 },
  empty: { type: Boolean, default: false },
  emptyText: { type: String, default: 'Нет данных за выбранный период' },
})
</script>

<template>
  <section class="card chart-card">
    <header class="card-head">
      <div class="titles">
        <h3>{{ title }}</h3>
        <p v-if="hint" class="hint">{{ hint }}</p>
      </div>
      <div class="spacer" />
      <slot name="actions" />
    </header>
    <div class="card-body" :style="{ height: typeof height === 'number' ? `${height}px` : height }">
      <div v-if="empty" class="empty">{{ emptyText }}</div>
      <slot v-else />
    </div>
  </section>
</template>

<style scoped>
.chart-card { display: flex; flex-direction: column; min-width: 0; }
.titles { min-width: 0; }
.hint { margin-top: 2px; font-size: var(--fs-xs); color: var(--muted); }
.card-body { position: relative; padding-top: 8px; }
.empty { height: 100%; display: grid; place-items: center; color: var(--muted); font-size: var(--fs-sm); }
</style>
