<script setup>
import { computed } from 'vue'
import { LIGHT_LABELS } from '@/utils/lights'
import { formatNumber } from '@/utils/format'

/**
 * Показатель с поясняющей строкой («13,2% от всех заявок»). Оформление совпадает с KpiCard,
 * у которого нет места под подпись к значению.
 */
const props = defineProps({
  label: { type: String, required: true },
  value: { type: [Number, String], default: null },
  unit: { type: String, default: '' },
  digits: { type: Number, default: 1 },
  caption: { type: String, default: '' },
  light: { type: String, default: '' },
  hint: { type: String, default: '' },
  loading: { type: Boolean, default: false },
})

const display = computed(() => (typeof props.value === 'string' ? props.value : formatNumber(props.value, { digits: props.digits })))
const hasValue = computed(() => props.value !== null && props.value !== undefined && props.value !== '')
</script>

<template>
  <div class="kpi card" :class="light && light !== 'gray' ? `l-${light}` : ''" :title="hint || undefined">
    <div class="top">
      <span class="label">{{ label }}</span>
      <span v-if="light && light !== 'gray'" class="light" :title="LIGHT_LABELS[light]" />
    </div>
    <div v-if="loading" class="skeleton value-skel" />
    <div v-else class="value num">{{ display }}<span v-if="unit && hasValue" class="unit" :class="{ pct: unit === '%' }">{{ unit }}</span></div>
    <div class="bottom">
      <div v-if="loading" class="skeleton caption-skel" />
      <span v-else-if="caption" class="caption">{{ caption }}</span>
    </div>
  </div>
</template>

<style scoped>
.kpi { position: relative; padding: 16px 18px 14px; display: flex; flex-direction: column; gap: 6px; min-height: 112px; overflow: hidden; }
.kpi::before { content: ''; position: absolute; left: 0; top: 14px; bottom: 14px; width: 3px; border-radius: 0 3px 3px 0; background: transparent; }
.kpi.l-green::before { background: var(--light-green); }
.kpi.l-yellow::before { background: var(--light-yellow); }
.kpi.l-red::before { background: var(--light-red); }
.top { display: flex; align-items: flex-start; gap: 8px; }
.label { flex: 1; font-size: var(--fs-sm); color: var(--text-2); font-weight: 520; line-height: 1.3; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.light { width: 9px; height: 9px; margin-top: 4px; border-radius: 50%; }
.l-green .light { background: var(--light-green); box-shadow: 0 0 0 3px color-mix(in srgb, var(--light-green) 20%, transparent); }
.l-yellow .light { background: var(--light-yellow); box-shadow: 0 0 0 3px color-mix(in srgb, var(--light-yellow) 22%, transparent); }
.l-red .light { background: var(--light-red); box-shadow: 0 0 0 3px color-mix(in srgb, var(--light-red) 20%, transparent); }
.value { font-size: var(--fs-kpi); font-weight: 680; letter-spacing: -0.02em; line-height: 1.1; color: var(--text); }
.unit { margin-left: 4px; font-size: 15px; font-weight: 560; color: var(--muted); letter-spacing: 0; }
.unit.pct { margin-left: 1px; }
.value-skel { height: 31px; width: 60%; }
.caption-skel { height: 12px; width: 70%; border-radius: 4px; }
.bottom { margin-top: auto; display: flex; align-items: center; min-height: 16px; font-size: var(--fs-xs); }
.caption { color: var(--muted); line-height: 1.35; }
</style>
