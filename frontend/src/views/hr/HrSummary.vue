<script setup>
import { computed, watch } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import FilterBar from '@/components/ui/FilterBar.vue'
import SegmentedControl from '@/components/ui/SegmentedControl.vue'
import KpiCard from '@/components/ui/KpiCard.vue'
import ChartCard from '@/components/ui/ChartCard.vue'
import EChart from '@/components/charts/EChart.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import LightBadge from '@/components/ui/LightBadge.vue'
import PdfButton from '@/components/ui/PdfButton.vue'
import { hrApi } from '@/api/services'
import { useAsync } from '@/composables/useAsync'
import { useQueryState } from '@/composables/useQueryState'
import { useAuthStore } from '@/stores/auth'
import { useAppStore } from '@/stores/app'
import { axisNumber, lightColor } from '@/components/charts/echarts'
import { deltaTone, formatDelta, formatNumber, plural } from '@/utils/format'
import {
  AGGREGATION_LABELS, FLOW_ROWS, PERIOD_TYPES, SUMMARY_KPIS, alignRange, chartKind, focusIndex, isPartial, monthsCaption,
  periodDelta, periodLight, periodValue, rangeText, rowDefinition, rowSeries, shortLabel, sliceRange, summaryGroups,
} from '@/domain/hrSummary'

const auth = useAuthStore()
const app = useAppStore()
const { state: f, reset, isDefault } = useQueryState({ period: 'quarter', from: '', to: '', focus: '', metric: 'turnover' })

const defs = useAsync(() => hrApi.metrics())
const summary = useAsync(() => hrApi.summary(f.period), { immediate: false })
watch(() => f.period, (_, old) => {
  if (old !== undefined) Object.assign(f, { from: '', to: '', focus: '' })
  summary.reload()
}, { immediate: true })

const all = computed(() => summary.data.value || [])
const periods = computed(() => sliceRange(all.value, f.from, f.to))
const fi = computed(() => focusIndex(periods.value, f.focus))
const focused = computed(() => periods.value[fi.value] || null)
const previous = computed(() => (fi.value > 0 ? periods.value[fi.value - 1] : null))
const loading = computed(() => summary.loading.value && !summary.data.value)

function setRange(edited, value) {
  const next = alignRange(all.value, edited === 'from' ? value : f.from, edited === 'to' ? value : f.to, edited)
  Object.assign(f, next)
  if (f.focus && !sliceRange(all.value, next.from, next.to).some((p) => p.key === f.focus)) f.focus = ''
}
function focusPeriod(key) {
  f.focus = key === periods.value.at(-1)?.key ? '' : key
}

const groups = computed(() => summaryGroups(defs.data.value))
const definition = (key) => rowDefinition(defs.data.value, key)
const rowHint = (row) => [row.description, AGGREGATION_LABELS[row.aggregation]].filter(Boolean).join(' · ')

// ---------- итоги периода ----------
const kpis = computed(() => {
  if (!focused.value) return []
  const rows = [...FLOW_ROWS, ...SUMMARY_KPIS.map(definition).filter(Boolean)]
  return rows.map((r) => ({
    key: r.key, label: r.label, unit: r.unit, direction: r.direction, hint: rowHint(r),
    value: periodValue(focused.value, r.key), light: periodLight(focused.value, r.key), delta: periodDelta(periods.value, fi.value, r.key),
  }))
})
const partial = computed(() => isPartial(focused.value, f.period))

// ---------- графики ----------
const labels = computed(() => periods.value.map((p) => shortLabel(p, f.period)))
const chartRow = computed(() => definition(f.metric) || definition('turnover') || FLOW_ROWS[0])
const chartOptions = computed(() => groups.value.map((g) => ({ label: g.label, items: g.items })))
const capitalize = (text) => (text ? text[0].toUpperCase() + text.slice(1) : '')
const unitFormatter = (unit) => (v) => (v === null || v === undefined ? '—' : formatNumber(v, { unit }))

function pointColor(row, period) {
  if (row.key === 'hired') return lightColor('green')
  if (row.key === 'fired') return lightColor('red')
  const light = periodLight(period, row.key)
  return light && light !== 'gray' ? lightColor(light) : null
}

const dynamicsOption = computed(() => {
  const row = chartRow.value
  const kind = chartKind(row)
  const values = rowSeries(periods.value, row.key)
  const data = values.map((value, i) => {
    const color = pointColor(row, periods.value[i])
    const focus = i === fi.value
    return { value, itemStyle: color ? { color } : undefined, symbolSize: focus ? 12 : 8 }
  })
  return {
    legend: { show: false },
    tooltip: { trigger: 'axis', valueFormatter: unitFormatter(row.unit) },
    grid: { left: 8, right: 16, top: 16, bottom: 8, containLabel: true },
    xAxis: { type: 'category', data: labels.value, boundaryGap: kind === 'bar', axisLabel: { interval: 0, hideOverlap: true } },
    yAxis: { type: 'value', minInterval: row.unit === 'чел.' || row.unit === 'шт.' ? 1 : 0, axisLabel: { formatter: (v) => (row.unit === '%' ? `${axisNumber(v)}%` : axisNumber(v)) } },
    series: [kind === 'bar'
      ? { name: row.label, type: 'bar', barMaxWidth: 36, data, itemStyle: { borderRadius: [4, 4, 0, 0] } }
      : { name: row.label, type: 'line', connectNulls: true, symbol: 'circle', showAllSymbol: true, lineStyle: { width: 2.5 }, areaStyle: { opacity: 0.06 }, data }],
  }
})

const lightsOption = computed(() => ({
  legend: { data: ['Норма', 'Внимание', 'Критично'] },
  tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
  xAxis: { type: 'category', data: labels.value, axisLabel: { interval: 0, hideOverlap: true } },
  yAxis: { type: 'value', minInterval: 1 },
  series: [['green', 'Норма'], ['yellow', 'Внимание'], ['red', 'Критично']].map(([light, name]) => ({
    name, type: 'bar', stack: 'lights', barMaxWidth: 32, itemStyle: { color: lightColor(light) },
    data: periods.value.map((p) => p.light_counts?.[light] || 0),
  })),
}))

function onChartClick(params) {
  const period = periods.value[params.dataIndex]
  if (period) focusPeriod(period.key)
}

const countText = computed(() => {
  const n = periods.value.length
  return n ? `${n} ${plural(n, ['период', 'периода', 'периодов'])}` : ''
})
</script>

<template>
  <div class="page">
    <PageHeader title="Сводка по периодам" :description="periods.length ? `Периоды: ${rangeText(periods)}` : 'Метрики службы персонала по месяцам, кварталам, полугодиям и годам'"
                :updatedAt="app.service('hr')?.data_updated_at">
      <PdfButton report="hr/summary" :params="{ period_type: f.period }" />
    </PageHeader>

    <FilterBar :summary="countText" :resettable="!isDefault()" @reset="reset">
      <SegmentedControl v-model="f.period" :options="PERIOD_TYPES" />
      <label class="field"><span>С</span>
        <select class="select" :value="f.from" :disabled="!all.length" @change="setRange('from', $event.target.value)">
          <option value="">Первого периода</option>
          <option v-for="p in all" :key="p.key" :value="p.key">{{ p.label }}</option>
        </select>
      </label>
      <label class="field"><span>По</span>
        <select class="select" :value="f.to" :disabled="!all.length" @change="setRange('to', $event.target.value)">
          <option value="">Последний период</option>
          <option v-for="p in all" :key="p.key" :value="p.key">{{ p.label }}</option>
        </select>
      </label>
    </FilterBar>

    <EmptyState v-if="summary.data.value && !all.length" icon="table" title="Данных пока нет"
                text="Сводка строится по месяцам с данными. Добавьте месяц в разделе «Ввод данных».">
      <router-link v-if="auth.can('hr', 'editor')" to="/hr/data" class="btn btn-primary">Ввод данных</router-link>
    </EmptyState>

    <template v-else>
      <!-- итоги периода -->
      <section class="stack">
        <div class="section-title">
          <h2>{{ focused ? `Итоги: ${focused.label}` : 'Итоги периода' }}</h2>
          <span v-if="previous" class="muted">изменение к периоду «{{ previous.label }}»</span>
          <span v-if="partial" class="badge badge-yellow" :title="`Есть данные не за все месяцы периода: ${focused.months.length}`">неполный период: {{ monthsCaption(focused, f.period) }}</span>
        </div>
        <div v-if="loading" class="grid grid-kpi"><div v-for="i in 7" :key="i" class="skeleton" style="height: 112px" /></div>
        <div v-else class="grid grid-kpi">
          <KpiCard v-for="k in kpis" :key="k.key" :label="k.label" :value="k.value" :unit="k.unit" :light="k.light" :delta="k.delta"
                   :direction="k.direction" :hint="k.hint" />
        </div>
      </section>

      <!-- графики -->
      <div class="charts">
        <ChartCard title="Динамика" :hint="capitalize(AGGREGATION_LABELS[chartRow.aggregation])" :empty="!loading && !periods.length">
          <template #actions>
            <select v-model="f.metric" class="select select-sm metric-select" aria-label="Метрика графика">
              <optgroup v-for="g in chartOptions" :key="g.label" :label="g.label">
                <option v-for="r in g.items" :key="r.key" :value="r.key">{{ r.label }}</option>
              </optgroup>
            </select>
          </template>
          <div v-if="loading" class="skeleton" style="height: 100%" />
          <EChart v-else :option="dynamicsOption" @click="onChartClick" />
        </ChartCard>
        <ChartCard title="Светофор по периодам" hint="Сколько метрик в норме, требует внимания, критично" :empty="!loading && !periods.length">
          <div v-if="loading" class="skeleton" style="height: 100%" />
          <EChart v-else :option="lightsOption" @click="onChartClick" />
        </ChartCard>
      </div>

      <!-- таблица -->
      <section class="card">
        <header class="card-head">
          <h3>Метрики по периодам</h3>
          <span class="hint">Щелчок по периоду — итоги за него, по строке — график динамики</span>
        </header>
        <div class="card-body">
          <div v-if="loading" class="skeleton" style="height: 320px" />
          <div v-else class="table-wrap summary-wrap scroll-thin">
            <table class="table table-compact summary">
              <thead>
                <tr>
                  <th class="metric-col">Метрика</th>
                  <th v-for="(p, i) in periods" :key="p.key" class="num period" :class="{ focus: i === fi }" :title="`${p.label}: месяцев с данными — ${p.months_count}`" @click="focusPeriod(p.key)">
                    <span class="p-label">{{ p.label }}</span>
                    <span v-if="monthsCaption(p, f.period)" class="p-caption" :class="{ partial: isPartial(p, f.period) }">{{ monthsCaption(p, f.period) }}</span>
                  </th>
                  <th class="num delta-col" :title="previous ? `${focused.label} к ${previous.label}` : ''">Изменение</th>
                </tr>
              </thead>
              <tbody v-for="g in groups" :key="g.key">
                <tr class="group-row"><td :colspan="periods.length + 2">{{ g.label }}</td></tr>
                <tr v-for="r in g.items" :key="r.key" class="clickable" :class="{ active: r.key === chartRow.key }" @click="f.metric = r.key">
                  <td class="metric-col" :title="rowHint(r)">
                    <span class="m-label">{{ r.label }}</span><span v-if="r.unit" class="m-unit">{{ r.unit }}</span>
                  </td>
                  <td v-for="(p, i) in periods" :key="p.key" class="num" :class="{ focus: i === fi }">
                    <span class="cell">
                      <LightBadge v-if="periodLight(p, r.key)" dot :light="periodLight(p, r.key)" />
                      <span :class="{ 'muted': periodValue(p, r.key) === null }">{{ formatNumber(periodValue(p, r.key)) }}</span>
                    </span>
                  </td>
                  <td class="num delta-col" :class="`delta-${deltaTone(periodDelta(periods, fi, r.key), r.direction)}`">
                    {{ formatDelta(periodDelta(periods, fi, r.key), r.unit) || '—' }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <p class="legend muted">
            <span><LightBadge dot light="green" />норма</span><span><LightBadge dot light="yellow" />внимание</span>
            <span><LightBadge dot light="red" />критично или не заполнено</span><span><LightBadge dot light="gray" />без оценки</span>
            <span class="spacer" />
            <span><AppIcon name="info" :size="13" />Суммы считаются за период, уровни — по последнему месяцу или среднему</span>
          </p>
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.charts { display: grid; grid-template-columns: minmax(0, 1.7fr) minmax(0, 1fr); gap: var(--sp-4); }
@media (max-width: 1100px) { .charts { grid-template-columns: minmax(0, 1fr); } }
.metric-select { width: auto; max-width: 260px; min-width: 0; flex: 0 1 auto; }
.section-title { flex-wrap: wrap; }

.summary-wrap { border: 1px solid var(--border); border-radius: var(--radius); }
.summary th.metric-col, .summary td.metric-col { position: sticky; left: 0; z-index: 2; background: var(--surface); min-width: 260px; max-width: 320px; }
.summary th.metric-col { z-index: 3; background: var(--surface-2); }
.summary tbody tr:hover td.metric-col { background: var(--row-hover); }
.summary th.period { cursor: pointer; user-select: none; min-width: 108px; vertical-align: bottom; }
.summary th.period:hover { color: var(--text); }
.p-label { display: block; }
.p-caption { display: block; margin-top: 1px; font-size: 10.5px; font-weight: 500; text-transform: none; letter-spacing: 0; color: var(--faint); }
.p-caption.partial { color: color-mix(in srgb, var(--light-yellow) 80%, var(--text)); }
.summary th.focus { color: var(--text); background: color-mix(in srgb, var(--chart-2) 10%, var(--surface-2)); box-shadow: inset 0 -2px 0 var(--chart-2); }
.summary td.focus { background: color-mix(in srgb, var(--chart-2) 5%, transparent); }
.summary td.num { white-space: nowrap; }
.cell { display: inline-flex; align-items: center; gap: 7px; }
.m-label { font-weight: 520; }
.m-unit { margin-left: 6px; font-size: var(--fs-xs); color: var(--muted); }
.summary tr.active td.metric-col { box-shadow: inset 3px 0 0 var(--chart-2); }
.summary tr.active .m-label { font-weight: 640; }
.delta-col { min-width: 104px; border-left: 1px solid var(--border); font-weight: 560; }
.group-row td { position: static !important; background: var(--surface-2) !important; font-size: var(--fs-xs); font-weight: 650; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); padding-top: 7px; padding-bottom: 7px; }
@media (max-width: 640px) { .summary th.metric-col, .summary td.metric-col { min-width: 150px; } }
.legend { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 16px; margin-top: 12px; font-size: var(--fs-xs); }
.legend span { display: inline-flex; align-items: center; gap: 6px; }
</style>
