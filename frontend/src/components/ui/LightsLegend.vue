<script setup>
/** Легенда семантики показателей: значок — статус по порогам светофора, стрелка — изменение
 *  к прошлому периоду. Одна строка под заголовком дашборда, чтобы «зелёная стрелка при критичном
 *  статусе» не читалась как противоречие (аудит 2026-11-20, A1). */
import LightBadge from './LightBadge.vue'
import AppIcon from './AppIcon.vue'
</script>

<template>
  <p class="lights-legend" aria-label="Как читать показатели: значок — статус по порогам светофора, стрелка — изменение к прошлому периоду">
    <LightBadge light="green" dot /><LightBadge light="yellow" dot /><LightBadge light="red" dot />
    <span>— статус по порогам светофора</span>
    <AppIcon name="arrow-up" :size="12" :stroke="2.4" /><AppIcon name="arrow-down" :size="12" :stroke="2.4" />
    <span>— изменение к прошлому периоду</span>
  </p>
</template>

<style scoped>
.lights-legend { display: flex; align-items: center; flex-wrap: wrap; gap: 4px 6px; margin: -8px 0 0; font-size: var(--fs-xs); color: var(--muted); }
.lights-legend :deep(svg) { opacity: .55; }
</style>
