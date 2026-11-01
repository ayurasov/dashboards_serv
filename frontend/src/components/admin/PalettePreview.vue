<script setup>
import { computed } from 'vue'
import EChart from '@/components/charts/EChart.vue'
import { LIGHT_LABELS } from '@/utils/lights'

/** Живой предпросмотр палитры: показатели со светофором и столбцы в цветах серий (цвета берутся напрямую). */
const props = defineProps({
  colors: { type: Object, required: true },
  height: { type: Number, default: 96 },
})

const SAMPLES = [
  { light: 'green', label: 'Офферы', value: '86%' },
  { light: 'yellow', label: 'Закрытие', value: '41 дн.' },
  { light: 'red', label: 'Текучесть', value: '9,1%' },
]
const VALUES = [42, 68, 55, 81, 36, 60, 48]
const MONTHS = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл']

const tl = computed(() => props.colors.traffic_light || {})
const option = computed(() => ({
  animation: false,
  color: props.colors.charts,
  grid: { left: 0, right: 0, top: 6, bottom: 18, containLabel: false },
  tooltip: { show: false },
  legend: { show: false },
  xAxis: { type: 'category', data: MONTHS, axisLabel: { fontSize: 10, margin: 6 } },
  yAxis: { type: 'value', show: false, max: 84 },
  series: [{ type: 'bar', colorBy: 'data', barWidth: '62%', data: VALUES, itemStyle: { borderRadius: [3, 3, 0, 0] } }],
}))
</script>

<template>
  <div class="preview">
    <div class="tiles">
      <div v-for="s in SAMPLES" :key="s.light" class="tile" :style="{ '--c': tl[s.light] }">
        <span class="t-label">{{ s.label }}</span>
        <span class="t-value num">{{ s.value }}</span>
        <span class="t-state"><i />{{ LIGHT_LABELS[s.light] }}</span>
      </div>
    </div>
    <div class="chart">
      <EChart :option="option" :height="height" />
    </div>
    <div class="brand-row">
      <span class="btn-sample" :style="{ background: colors.brand?.primary }">Кнопка</span>
      <span class="link-sample" :style="{ color: colors.brand?.primary }">Раздел меню</span>
      <span class="muted-sample" :style="{ color: colors.brand?.muted }">Подпись</span>
      <span class="spacer" />
      <span class="neutral" :style="{ '--c': tl.neutral }"><i />{{ LIGHT_LABELS.gray }}</span>
    </div>
  </div>
</template>

<style scoped>
.preview { display: flex; flex-direction: column; gap: 10px; }
.tiles { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
.tile { position: relative; display: flex; flex-direction: column; gap: 2px; padding: 9px 10px 8px 12px; border-radius: 10px; border: 1px solid var(--border); background: var(--surface); overflow: hidden; }
.tile::before { content: ''; position: absolute; left: 0; top: 8px; bottom: 8px; width: 3px; border-radius: 0 3px 3px 0; background: var(--c); }
.t-label { font-size: 10.5px; color: var(--muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.t-value { font-size: 17px; font-weight: 680; letter-spacing: -0.01em; color: var(--text); line-height: 1.2; }
.t-state, .neutral { display: inline-flex; align-items: center; gap: 5px; font-size: 10.5px; color: var(--text-2); }
.t-state i, .neutral i { width: 7px; height: 7px; border-radius: 50%; background: var(--c); }
.chart { padding: 2px 2px 0; }
.chart :deep(.echart) { min-height: 0; }
.brand-row { display: flex; align-items: center; gap: 10px; font-size: var(--fs-xs); white-space: nowrap; }
.btn-sample { padding: 3px 10px; border-radius: 6px; color: #fff; font-weight: 600; }
.link-sample { font-weight: 600; }
</style>
