<script setup>
import { computed } from 'vue'

/** Мини-график ряда показателя (спарклайн): тренд рядом со значением без перехода на дашборд.
 *  points — значения от старых к новым, null/undefined — пропуски (точки сжаты по оси X). */
const props = defineProps({
  points: { type: Array, default: () => [] },
  width: { type: Number, default: 64 },
  height: { type: Number, default: 20 },
  tone: { type: String, default: '' },  // '', 'good', 'bad' — цвет последней точки
})

const view = { w: 56, h: 18 }  // svg viewBox; фактический размер — width/height
const pts = computed(() => {
  const clean = props.points.filter((v) => v !== null && v !== undefined && Number.isFinite(Number(v)))
  if (clean.length < 2) return []
  const values = clean.map(Number)
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = max - min || 1
  return values.map((v, i) => {
    const x = (i / (values.length - 1)) * (view.w - 2) + 1
    const y = view.h - 2 - ((v - min) / span) * (view.h - 4)
    return [Number(x.toFixed(1)), Number(y.toFixed(1))]
  })
})
const path = computed(() => pts.value.map(([x, y]) => `${x},${y}`).join(' '))
const last = computed(() => pts.value[pts.value.length - 1] || [])
</script>

<template>
  <svg v-if="pts.length >= 2" class="spark" :width="width" :height="height" :viewBox="`0 0 ${view.w} ${view.h}`"
       fill="none" aria-hidden="true" preserveAspectRatio="none">
    <polyline :points="path" stroke="var(--text-2)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" opacity=".65" />
    <circle v-if="last.length" :cx="last[0]" :cy="last[1]" r="2.2"
            :fill="tone === 'good' ? 'var(--light-green)' : tone === 'bad' ? 'var(--light-red)' : 'var(--accent)'" />
  </svg>
</template>

<style scoped>
.spark { display: block; flex: 0 0 auto; }
</style>
