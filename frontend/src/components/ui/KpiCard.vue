<script setup>
import { computed } from 'vue'
import { LIGHT_LABELS } from '@/utils/lights'
import { deltaTone, formatDelta, formatNumber } from '@/utils/format'
import AppIcon from './AppIcon.vue'

/**
 * Показатель: значение, единица, светофор, изменение к прошлому периоду с оценкой по направлению.
 * delta — абсолютное изменение; deltaPct — относительное (если задано, показывается оно).
 */
const props = defineProps({
  label: { type: String, required: true },
  value: { type: [Number, String], default: null },
  unit: { type: String, default: '' },
  digits: { type: Number, default: 2 },
  light: { type: String, default: '' },
  delta: { type: Number, default: null },
  deltaPct: { type: Number, default: null },
  deltaLabel: { type: String, default: '' },
  direction: { type: String, default: 'neutral' },
  hint: { type: String, default: '' },
  caption: { type: String, default: '' },
  target: { type: Number, default: null },
  loading: { type: Boolean, default: false },
})

const display = computed(() => (typeof props.value === 'string' ? props.value : formatNumber(props.value, { digits: props.digits })))
const tone = computed(() => deltaTone(props.deltaPct ?? props.delta, props.direction, props.deltaPct !== null ? 0.5 : 0))
const deltaText = computed(() => {
  if (props.deltaPct !== null && props.deltaPct !== undefined) {
    const sign = props.deltaPct > 0 ? '+' : props.deltaPct < 0 ? '−' : '±'
    return `${sign}${Math.abs(props.deltaPct).toLocaleString('ru-RU', { maximumFractionDigits: 1 })}%`
  }
  return formatDelta(props.delta, props.unit, props.digits)
})
const showDelta = computed(() => props.delta !== null || props.deltaPct !== null)
const unitText = computed(() => (props.unit && props.value !== null && props.value !== undefined && props.value !== '' ? props.unit : ''))
</script>

<template>
  <div class="kpi card" :class="light ? `l-${light}` : ''">
    <div class="top">
      <span class="label" :title="hint || label">{{ label }}</span>
      <span v-if="light" class="light" :title="LIGHT_LABELS[light]" />
    </div>
    <div v-if="loading" class="skeleton value-skel" />
    <div v-else class="value num">{{ display }}<span v-if="unitText" class="unit" :class="{ pct: unit === '%' }">{{ unit }}</span></div>
    <div class="bottom">
      <span v-if="showDelta && deltaText" class="delta num" :class="`delta-${tone}`">
        <AppIcon v-if="tone !== 'flat'" :name="(deltaPct ?? delta) > 0 ? 'arrow-up' : 'arrow-down'" :size="12" :stroke="2.4" />
        {{ deltaText }}
      </span>
      <span v-if="deltaLabel && showDelta" class="muted">{{ deltaLabel }}</span>
      <span v-if="target !== null" class="muted target">цель {{ formatNumber(target, { unit }) }}</span>
      <span v-if="caption || $slots.caption" class="muted caption"><slot name="caption">{{ caption }}</slot></span>
      <span v-else-if="light && !showDelta && target === null" class="state">{{ LIGHT_LABELS[light] }}</span>
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
.light { width: 9px; height: 9px; margin-top: 4px; border-radius: 50%; background: var(--light-gray); box-shadow: 0 0 0 3px color-mix(in srgb, var(--light-gray) 20%, transparent); }
.l-green .light { background: var(--light-green); box-shadow: 0 0 0 3px color-mix(in srgb, var(--light-green) 20%, transparent); }
.l-yellow .light { background: var(--light-yellow); box-shadow: 0 0 0 3px color-mix(in srgb, var(--light-yellow) 22%, transparent); }
.l-red .light { background: var(--light-red); box-shadow: 0 0 0 3px color-mix(in srgb, var(--light-red) 20%, transparent); }
.value { font-size: var(--fs-kpi); font-weight: 680; letter-spacing: -0.02em; line-height: 1.1; color: var(--text); }
.unit { margin-left: 4px; font-size: 15px; font-weight: 560; color: var(--muted); letter-spacing: 0; }
.unit.pct { margin-left: 1px; }
.value-skel { height: 31px; width: 60%; }
.bottom { margin-top: auto; display: flex; flex-wrap: wrap; align-items: center; gap: 4px 8px; font-size: var(--fs-xs); }
.delta { display: inline-flex; align-items: center; gap: 2px; font-weight: 620; }
.state { color: var(--muted); }
.target { margin-left: auto; }
</style>
