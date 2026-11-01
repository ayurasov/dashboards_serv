<script setup>
import { computed } from 'vue'

/**
 * Мини-график для строки таблицы сравнения: недели предыдущего интервала — бледной линией,
 * текущего — основной, последняя неделя — точкой. split — индекс первой недели текущего интервала.
 */
const props = defineProps({
  values: { type: Array, required: true },
  split: { type: Number, default: 0 },
  width: { type: Number, default: 104 },
  height: { type: Number, default: 26 },
})

const PAD = 3
const points = computed(() => {
  const vals = props.values
  const nums = vals.filter((v) => v !== null && v !== undefined).map(Number)
  if (nums.length < 2) return []
  const min = Math.min(...nums)
  const max = Math.max(...nums)
  const w = props.width - PAD * 2
  const h = props.height - PAD * 2
  const step = vals.length > 1 ? w / (vals.length - 1) : 0
  return vals.map((v, i) => (v === null || v === undefined ? null : {
    i, x: PAD + i * step, y: PAD + (max === min ? h / 2 : h - ((Number(v) - min) / (max - min)) * h),
  })).filter(Boolean)
})

function path(list) {
  return list.map((p, k) => `${k ? 'L' : 'M'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join('')
}

// Предыдущий отрезок доходит до первой точки текущего, чтобы линия была непрерывной.
const prevPath = computed(() => {
  const list = points.value
  const firstNow = list.findIndex((p) => p.i >= props.split)
  return path(firstNow < 0 ? list : list.slice(0, firstNow + 1))
})
const nowPath = computed(() => path(points.value.filter((p) => p.i >= props.split)))
const last = computed(() => points.value.at(-1))
const divider = computed(() => {
  if (props.split <= 0 || props.values.length < 2) return null
  return PAD + (props.split - 0.5) * ((props.width - PAD * 2) / (props.values.length - 1))
})
</script>

<template>
  <svg v-if="points.length" class="spark" :width="width" :height="height" :viewBox="`0 0 ${width} ${height}`" aria-hidden="true">
    <line v-if="divider !== null" class="divider" :x1="divider" :x2="divider" y1="2" :y2="height - 2" />
    <path class="prev" :d="prevPath" />
    <path class="now" :d="nowPath" />
    <circle v-if="last" class="dot" :cx="last.x" :cy="last.y" r="2.4" />
  </svg>
  <span v-else class="faint">—</span>
</template>

<style scoped>
.spark { display: block; overflow: visible; }
path { fill: none; stroke-width: 1.5; stroke-linejoin: round; stroke-linecap: round; }
.prev { stroke: color-mix(in srgb, var(--chart-7) 70%, transparent); }
.now { stroke: var(--accent); }
.dot { fill: var(--accent); stroke: var(--surface); stroke-width: 1.5; }
.divider { stroke: var(--border-strong); stroke-width: 1; stroke-dasharray: 2 2; }
</style>
