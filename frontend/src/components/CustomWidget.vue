<template>
  <div class="ccard" :class="{ 'cd-wide': wide }">
    <div class="ctitle">{{ widget.title || DEFAULT_TITLES[widget.widget_type] || 'Виджет' }}</div>

    <!-- metric_card: latest filled value of one metric, coloured by its traffic light -->
    <template v-if="widget.widget_type === 'metric_card'">
      <div v-if="!card" class="cd-empty">Метрика не выбрана</div>
      <div v-else class="kpi" style="border:0;padding:0">
        <div class="kpi-lbl">
          <span class="light-dot" :class="'light-' + card.light"></span>
          {{ card.label }}
        </div>
        <div class="kpi-val" :style="{ color: LIGHT_VARS[card.light] }">{{ card.text }}</div>
        <div class="kpi-sub">{{ card.month ? card.month : 'нет данных' }}</div>
      </div>
    </template>

    <!-- note: free text -->
    <div v-else-if="widget.widget_type === 'note'" class="cd-note">
      {{ widget.config?.text || 'Пустая заметка' }}
    </div>

    <!-- table: metrics × months -->
    <template v-else-if="widget.widget_type === 'table'">
      <div v-if="!rows.length" class="cd-empty">Метрики не выбраны</div>
      <div v-else class="twrap">
        <div class="tscroll">
          <table>
            <thead>
              <tr><th>Метрика</th><th v-for="m in months" :key="m.key">{{ m.label }}</th></tr>
            </thead>
            <tbody>
              <tr v-for="r in rows" :key="r.key">
                <td class="td-p">{{ r.label }}</td>
                <td v-for="m in months" :key="m.key" class="td-mono">
                  <span class="light-dot" :class="'light-' + light(m.key, r.key)"></span>
                  {{ fmt(value(m.key, r.key), r.unit) }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>

    <!-- line_chart / bar_chart: selected metrics over all months -->
    <template v-else>
      <div v-if="!rows.length" class="cd-empty">Метрики не выбраны</div>
      <e-chart v-else :option="chartOpt" :height="height" />
    </template>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import EChart from './EChart.vue'
import { usePaletteStore } from '../stores/palette.js'

const palette = usePaletteStore()

const props = defineProps({
  widget: { type: Object, required: true },
  months: { type: Array, default: () => [] },
  analytics: { type: Object, default: () => ({}) },
  defs: { type: Array, default: () => [] },
  height: { type: Number, default: 240 },
})

const DEFAULT_TITLES = {
  metric_card: 'Карточка метрики',
  line_chart: 'Линейный график',
  bar_chart: 'Столбчатый график',
  table: 'Таблица метрик',
  note: 'Заметка',
}
const LIGHT_VARS = { green: 'var(--c-ok)', yellow: 'var(--c-warn)', red: 'var(--c-err)', gray: 'var(--c-muted)' }
// Falls back to the fixed set only if the active palette has no chart colours at all.
const FALLBACK_SERIES_COLORS = ['#1a4f80', '#6b2fa0', '#2d6e17', '#a06010', '#c0392b', '#0f7b7b']
const seriesColors = computed(() => (palette.chartColors?.length ? palette.chartColors : FALLBACK_SERIES_COLORS))

const wide = computed(() => props.widget.widget_type === 'table')

const defMap = computed(() => new Map(props.defs.map(d => [d.key, d])))

function fmt(val, unit) {
  if (val === null || val === undefined) return '—'
  if (unit === '%') return val.toFixed(2).replace('.', ',') + '%'
  if (unit === 'дн.') return val.toFixed(1).replace('.', ',')
  if (unit === 'чел.' || unit === 'шт.') return String(Math.round(val))
  return String(val).replace('.', ',')
}

function entry(monthKey, metricKey) {
  return props.analytics[monthKey]?.metrics?.find(m => m.key === metricKey)
}
function value(monthKey, metricKey) {
  const m = entry(monthKey, metricKey)
  return m && m.value !== null && m.value !== undefined ? m.value : null
}
function light(monthKey, metricKey) {
  return entry(monthKey, metricKey)?.light || 'gray'
}

/** Metric keys the widget is configured for; `metric_key` is the single-metric form. */
const keys = computed(() => {
  const cfg = props.widget.config || {}
  const list = Array.isArray(cfg.metric_keys) ? cfg.metric_keys : []
  return cfg.metric_key ? [cfg.metric_key, ...list.filter(k => k !== cfg.metric_key)] : list
})

const rows = computed(() => keys.value.map(key => {
  const d = defMap.value.get(key)
  return { key, label: d?.label || key, unit: d?.unit || '' }
}))

// Latest month in which the metric is actually filled — a card showing "—" for the
// newest month would hide a value that exists one month back.
const card = computed(() => {
  const row = rows.value[0]
  if (!row) return null
  for (let i = props.months.length - 1; i >= 0; i -= 1) {
    const m = props.months[i]
    const v = value(m.key, row.key)
    if (v !== null) {
      return { label: row.label, text: fmt(v, row.unit), light: light(m.key, row.key), month: m.label }
    }
  }
  return { label: row.label, text: '—', light: 'gray', month: '' }
})

const chartOpt = computed(() => {
  const bar = props.widget.widget_type === 'bar_chart'
  // A day-scale metric next to percentages flattens the percentage lines, so days
  // get their own axis.
  const hasDays = rows.value.some(r => r.unit === 'дн.')
  return {
    tooltip: { trigger: 'axis' },
    legend: { bottom: 0, textStyle: { fontSize: 9 } },
    grid: { left: 40, right: hasDays ? 40 : 12, top: 14, bottom: 44 },
    xAxis: { type: 'category', data: props.months.map(m => m.label), axisLabel: { fontSize: 10 } },
    yAxis: hasDays
      ? [{ type: 'value', axisLabel: { fontSize: 10 } },
         { type: 'value', name: 'дн.', nameTextStyle: { fontSize: 9 }, axisLabel: { fontSize: 10 } }]
      : { type: 'value', axisLabel: { fontSize: 10 } },
    series: rows.value.map((r, i) => ({
      name: r.label,
      type: bar ? 'bar' : 'line',
      smooth: !bar,
      symbolSize: 6,
      connectNulls: true,
      yAxisIndex: hasDays && r.unit === 'дн.' ? 1 : 0,
      data: props.months.map(m => value(m.key, r.key)),
      itemStyle: { color: seriesColors.value[i % seriesColors.value.length] },
    })),
  }
})
</script>
