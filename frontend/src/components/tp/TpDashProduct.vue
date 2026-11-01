<script setup>
import { computed } from 'vue'
import ChartCard from '@/components/ui/ChartCard.vue'
import EChart from '@/components/charts/EChart.vue'
import { COMPLEXITY, productSummary, seriesOf } from '@/domain/tp'
import { formatNumber } from '@/utils/format'
import { axisTooltip, fmtValue, isDense, lineSeries, stackSeries, thresholdMarkLine, useChartTheme, valueAxis, weekAxis } from './TpDashCharts'

/** Блок продукта (AlterOS или AlterOffice): решено по линиям, среднее время решения, доступность по сложности. */
const props = defineProps({
  product: { type: String, required: true },
  title: { type: String, required: true },
  rows: { type: Array, required: true },
  rules: { type: Object, default: () => ({}) },
})

const theme = useChartTheme()
const labels = computed(() => props.rows.map((r) => r.period))
const key = (suffix) => `${props.product}_${suffix}`
const summary = computed(() => productSummary(props.rows, props.product))
const has = (k) => props.rows.some((r) => r[k] !== null && r[k] !== undefined)

const summaryText = computed(() => {
  const s = summary.value
  const parts = []
  if (s.total !== null) parts.push(`решено ${formatNumber(s.total)}`)
  if (s.l12Share !== null) parts.push(`1–2 линия ${formatNumber(s.l12Share, { digits: 0 })}%`, `3 линия ${formatNumber(s.l3Share, { digits: 0 })}%`)
  if (s.avgTime !== null) parts.push(`среднее время ${fmtValue(s.avgTime, 'ч')}`)
  return parts.join(' · ')
})

const linesOption = computed(() => {
  const t = theme.value
  const n = labels.value.length
  return {
    legend: { data: ['1–2 линия', '3 линия'] },
    tooltip: axisTooltip({ unit: 'шт.', digits: 0, total: true }),
    xAxis: weekAxis(labels.value, { boundaryGap: !isDense(n) }),
    yAxis: valueAxis({ minInterval: 1 }),
    series: [
      stackSeries('1–2 линия', seriesOf(props.rows, key('1_2line')), t.c(2), { stack: 'lines', count: n }),
      stackSeries('3 линия', seriesOf(props.rows, key('3line')), t.c(5), { stack: 'lines', count: n }),
    ],
  }
})

const avgTimeOption = computed(() => {
  const t = theme.value
  return {
    legend: { show: false },
    grid: { top: 16 },
    tooltip: axisTooltip({ unit: 'ч' }),
    xAxis: weekAxis(labels.value, { boundaryGap: false }),
    yAxis: valueAxis(),
    series: [lineSeries('Среднее время решения', seriesOf(props.rows, key('avg_time')), t.c(6), {
      area: true, markLine: thresholdMarkLine(props.rules[key('avg_time')], { unit: 'ч' }),
    })],
  }
})

// Сложность — порядковая шкала: один цвет, насыщенность растёт со сложностью.
const COMPLEXITY_OPACITY = [0.45, 0.72, 1]
const availOption = computed(() => {
  const t = theme.value
  const n = labels.value.length
  return {
    legend: { data: COMPLEXITY.map((c) => c.label), formatter: (name) => `${COMPLEXITY.find((c) => c.label === name)?.short ?? name}` },
    tooltip: axisTooltip({ unit: 'ч', total: true }),
    xAxis: weekAxis(labels.value, { boundaryGap: !isDense(n) }),
    yAxis: valueAxis(),
    series: COMPLEXITY.map((c, i) => stackSeries(c.label, seriesOf(props.rows, key(`avail_${c.suffix}`)), t.c(2), {
      stack: 'avail', count: n, opacity: COMPLEXITY_OPACITY[i],
    })),
  }
})
</script>

<template>
  <section class="stack">
    <div class="section-title">
      <h2>{{ title }}</h2>
      <span class="muted">{{ summaryText || 'Линии поддержки' }}</span>
    </div>
    <div class="grid grid-3">
      <ChartCard title="Решено по линиям поддержки" hint="Заявки по неделям, шт." :height="260" :empty="!has(key('total')) && !has(key('1_2line'))">
        <EChart :option="linesOption" />
      </ChartCard>
      <ChartCard title="Среднее время решения" hint="По неделям, ч" :height="260" :empty="!has(key('avg_time'))">
        <EChart :option="avgTimeOption" />
      </ChartCard>
      <ChartCard title="Доступность по сложности заявок" :hint="summary.avail !== null ? `Всего за период ${fmtValue(summary.avail, 'ч')}` : 'По неделям, ч'" :height="260" :empty="!has(key('avail_total')) && !has(key('avail_8_10'))">
        <EChart :option="availOption" />
      </ChartCard>
    </div>
  </section>
</template>
