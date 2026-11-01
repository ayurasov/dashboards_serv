<script setup>
import AppIcon from '@/components/ui/AppIcon.vue'

/** Карточка графика сопоставления: как ChartCard, плюс короткое пояснение внизу — что именно сравнивается. */
defineProps({
  title: { type: String, required: true },
  hint: { type: String, default: '' },
  note: { type: String, default: '' },
  height: { type: Number, default: 280 },
  empty: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
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
    <div class="card-body chart-body" :style="{ height: `${height}px` }">
      <div v-if="loading" class="skeleton fill" />
      <div v-else-if="empty" class="empty">{{ emptyText }}</div>
      <slot v-else />
    </div>
    <footer v-if="note" class="note"><AppIcon name="info" :size="14" /><p>{{ note }}</p></footer>
  </section>
</template>

<style scoped>
.chart-card { display: flex; flex-direction: column; min-width: 0; }
.titles { min-width: 0; }
.hint { margin-top: 2px; font-size: var(--fs-xs); color: var(--muted); }
.chart-body { position: relative; padding-top: 8px; padding-bottom: var(--sp-3); }
.fill { height: 100%; }
.empty { height: 100%; display: grid; place-items: center; color: var(--muted); font-size: var(--fs-sm); }
.note { display: flex; gap: 8px; margin-top: auto; padding: 10px var(--sp-5) 12px; border-top: 1px solid var(--border); color: var(--muted); font-size: var(--fs-xs); line-height: 1.45; }
.note :deep(svg) { margin-top: 1px; }
</style>
