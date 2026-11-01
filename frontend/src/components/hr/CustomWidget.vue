<script setup>
import { computed } from 'vue'
import KpiCard from '@/components/ui/KpiCard.vue'
import ChartCard from '@/components/ui/ChartCard.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import LightBadge from '@/components/ui/LightBadge.vue'
import EChart from '@/components/charts/EChart.vue'
import { axisNumber } from '@/components/charts/echarts'
import { formatNumber, monthLabel } from '@/utils/format'
import { escapeHtml } from '@/utils/markdown'
import { latestFilled, monthMetric, unitAxes, valuesOf, widgetKeys, widgetTitle } from '@/domain/hrWidgets'

/**
 * Виджет пользовательского дашборда. series — ряд месяцев из /hr/analytics/dashboard
 * (у каждого месяца metrics: значение, светофор, изменение, цель); defs — определения метрик.
 */
const props = defineProps({
  widget: { type: Object, required: true },
  series: { type: Array, default: () => [] },
  defs: { type: Array, default: () => [] },
  periodText: { type: String, default: '' },
})

const defMap = computed(() => Object.fromEntries(props.defs.map((d) => [d.key, d])))
const title = computed(() => widgetTitle(props.widget, props.defs))
const keys = computed(() => widgetKeys(props.widget))
const metricDefs = computed(() => keys.value.map((k) => defMap.value[k] || { key: k, label: k, unit: '' }))
const type = computed(() => props.widget.widget_type)

// ---------- карточка ----------
const card = computed(() => {
  const d = metricDefs.value[0]
  if (!d) return null
  const hit = latestFilled(props.series, d.key)
  const base = { label: title.value, unit: d.unit, hint: d.description || d.label }
  if (!hit) return { ...base, value: null }
  const m = hit.metric
  return {
    ...base, value: m.value, light: m.light, delta: m.delta, direction: m.direction, target: m.target,
    deltaLabel: monthLabel(hit.month.key, true), hint: `${d.description || d.label} · ${hit.month.label}`,
  }
})

// ---------- графики ----------
const labels = computed(() => props.series.map((s) => monthLabel(s.key, true)))
const chartOption = computed(() => {
  const bar = type.value === 'bar_chart'
  const axes = unitAxes(metricDefs.value)
  const two = axes.units.length === 2
  return {
    legend: { type: 'scroll', data: metricDefs.value.map((d) => d.label) },
    grid: { left: 8, right: 12, top: 36, bottom: 4, containLabel: true },
    tooltip: {
      trigger: 'axis',
      axisPointer: bar ? { type: 'shadow' } : undefined,
      formatter: (params) => {
        const rows = params.map((p) => `${p.marker}${escapeHtml(p.seriesName)}: <b>${formatNumber(p.value, { unit: metricDefs.value[p.seriesIndex]?.unit })}</b>`)
        return [escapeHtml(params[0]?.axisValueLabel || ''), ...rows].join('<br>')
      },
    },
    xAxis: { type: 'category', data: labels.value, boundaryGap: bar },
    yAxis: axes.units.map((unit, i) => ({
      type: 'value', name: two ? unit : '', nameTextStyle: { align: i ? 'right' : 'left' }, scale: !bar,
      axisLabel: { formatter: (v) => (unit === '%' ? `${axisNumber(v)}%` : axisNumber(v)) },
      splitLine: i ? { show: false } : undefined,
    })),
    series: metricDefs.value.map((d) => ({
      name: d.label, type: bar ? 'bar' : 'line', yAxisIndex: axes.axisOf(d), data: valuesOf(props.series, d.key),
      connectNulls: true, symbol: 'circle', symbolSize: 6, lineStyle: { width: 2.2 }, barMaxWidth: 18,
      itemStyle: bar ? { borderRadius: [3, 3, 0, 0] } : undefined,
    })),
  }
})

// ---------- таблица ----------
const tableRows = computed(() => [...props.series].reverse())
const cell = (month, key) => monthMetric(month, key)
</script>

<template>
  <!-- карточка метрики -->
  <KpiCard v-if="type === 'metric_card' && card" :label="card.label" :value="card.value" :unit="card.unit" :light="card.light" :delta="card.delta ?? null"
           :direction="card.direction" :target="card.target ?? null" :deltaLabel="card.deltaLabel" :hint="card.hint" />
  <section v-else-if="type === 'metric_card'" class="card simple"><header class="card-head"><h3>{{ title }}</h3></header><p class="card-body muted">Метрика не выбрана</p></section>

  <!-- графики -->
  <ChartCard v-else-if="type === 'line_chart' || type === 'bar_chart'" :title="title" :hint="periodText" :height="280"
             :empty="!metricDefs.length || !series.length" :emptyText="metricDefs.length ? 'Нет данных за выбранный период' : 'Метрики не выбраны'">
    <EChart :option="chartOption" />
  </ChartCard>

  <!-- таблица: месяцы × метрики -->
  <section v-else-if="type === 'table'" class="card">
    <header class="card-head"><h3>{{ title }}</h3><span class="spacer" /><span class="hint">{{ periodText }}</span></header>
    <div class="card-body">
      <div v-if="metricDefs.length && series.length" class="table-wrap bordered scroll-thin">
        <table class="table table-compact">
          <thead>
            <tr>
              <th class="month-col">Месяц</th>
              <th v-for="d in metricDefs" :key="d.key" class="num" :title="d.description || d.label">
                <span class="th-label">{{ d.label }}</span><span v-if="d.unit" class="th-unit">{{ d.unit }}</span>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="m in tableRows" :key="m.key">
              <td class="month-col">{{ m.label }}</td>
              <td v-for="d in metricDefs" :key="d.key" class="num">
                <span class="cell">
                  <LightBadge v-if="cell(m, d.key)" dot :light="cell(m, d.key).light" />
                  <span :class="{ muted: cell(m, d.key)?.value === null || cell(m, d.key)?.value === undefined }">{{ formatNumber(cell(m, d.key)?.value) }}</span>
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <EmptyState v-else compact icon="table" :title="metricDefs.length ? 'Нет данных' : 'Метрики не выбраны'" />
    </div>
  </section>

  <!-- заметка -->
  <section v-else-if="type === 'note'" class="card note">
    <header class="card-head"><h3>{{ widget.title?.trim() || 'Заметка' }}</h3></header>
    <p class="card-body text">{{ widget.config?.text || 'Пустая заметка' }}</p>
  </section>
</template>

<style scoped>
.bordered { border: 1px solid var(--border); border-radius: var(--radius); max-height: 420px; }
.month-col { white-space: nowrap; font-weight: 540; }
th.month-col { font-weight: 620; }
.table th { white-space: normal; min-width: 96px; vertical-align: bottom; }
.th-label { display: block; text-transform: none; letter-spacing: 0; font-size: var(--fs-xs); line-height: 1.3; }
.th-unit { display: block; font-weight: 500; text-transform: none; letter-spacing: 0; color: var(--faint); }
.cell { display: inline-flex; align-items: center; gap: 7px; white-space: nowrap; }
.note { height: 100%; background: color-mix(in srgb, var(--light-yellow) 6%, var(--surface)); }
.note .text { white-space: pre-line; color: var(--text-2); font-size: var(--fs-base); line-height: 1.55; }
.simple { height: 100%; }
</style>
