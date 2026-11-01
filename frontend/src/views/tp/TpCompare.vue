<script setup>
import { computed } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import ChartCard from '@/components/ui/ChartCard.vue'
import EChart from '@/components/charts/EChart.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import LightBadge from '@/components/ui/LightBadge.vue'
import TpCompareSpark from '@/components/tp/TpCompareSpark.vue'
import { fmtValue, useChartTheme } from '@/components/tp/TpDashCharts'
import { commonApi, tpApi } from '@/api/services'
import { useAsync } from '@/composables/useAsync'
import { useQueryState } from '@/composables/useQueryState'
import { useAppStore } from '@/stores/app'
import { formatDelta, formatNumber, plural } from '@/utils/format'
import {
  QUICK_PERIODS, TRAFFIC_METRICS,
  compareMetrics, comparePeriods, groupColumns, intervalTitle, isAvgMetric, normalizeRows, periodRange, rulesByKey,
  seriesOf, shortLabels, toneCounts,
} from '@/domain/tp'

const app = useAppStore()
const theme = useChartTheme()
const { state: f } = useQueryState({ quick: '8', group: 'key' })

const reports = useAsync(() => tpApi.reports())
const columns = useAsync(() => tpApi.columns())
const rules = useAsync(() => commonApi.lightRules('tech'))

const all = computed(() => normalizeRows(reports.data.value))
const pair = computed(() => comparePeriods(all.value, all.value, f.quick))
const nowTitle = computed(() => intervalTitle(pair.value, 'now'))
const prevTitle = computed(() => intervalTitle(pair.value, 'prev'))
const items = computed(() => compareMetrics(columns.data.value || [], pair.value, rulesByKey(rules.data.value)))
const groups = computed(() => groupColumns(items.value))
const counts = computed(() => toneCounts(items.value))
const comparable = computed(() => pair.value.now.length > 0 && pair.value.prev.length > 0)
const partial = computed(() => pair.value.mode === 'quick' && pair.value.prev.length > 0 && pair.value.prev.length < pair.value.weeks)

// Мини-графики: недели обоих интервалов подряд.
const sparkRows = computed(() => [...pair.value.prev, ...pair.value.now])
const sparks = computed(() => Object.fromEntries(items.value.map((m) => [m.key, seriesOf(sparkRows.value, m.key)])))

const fmtPct = (pct) => {
  if (pct === null || pct === undefined) return '—'
  const sign = pct > 0 ? '+' : pct < 0 ? '−' : '±'
  return `${sign}${formatNumber(Math.abs(pct), { digits: 1 })}%`
}

// ---------- графики ----------
const KEY_GROUP = 'key'
const groupOptions = computed(() => [{ key: KEY_GROUP, label: 'Ключевые показатели' }, ...groupColumns(columns.data.value || []).map((g) => ({ key: g.key, label: g.label }))])
const chartItems = computed(() => {
  if (f.group === KEY_GROUP) {
    const byKey = Object.fromEntries(items.value.map((m) => [m.key, m]))
    return TRAFFIC_METRICS.map((m) => byKey[m.key]).filter(Boolean)
  }
  return items.value.filter((m) => m.group === f.group)
})
const chartNames = computed(() => shortLabels(chartItems.value.map((m) => m.label)))
const chartHeight = computed(() => Math.max(220, 24 + chartItems.value.length * 44))

const toneColor = (m) => {
  const t = theme.value
  if (m.direction === 'neutral' || m.tone === 'flat') return t.light('gray')
  return t.light(m.tone === 'good' ? 'green' : 'red')
}

function tooltipFor(m, name) {
  const row = (label, value) => `<div style="display:flex;justify-content:space-between;gap:16px"><span>${label}</span><b style="font-variant-numeric:tabular-nums">${value}</b></div>`
  return `<div style="font-weight:600;margin-bottom:4px">${name}</div>`
    + row(nowTitle.value, fmtValue(m.now, m.unit, m.digits))
    + row(prevTitle.value, fmtValue(m.prev, m.unit, m.digits))
    + row('Изменение', `${formatDelta(m.delta, m.unit, m.digits) || '—'} · ${fmtPct(m.pct)}`)
}

/** Левая граница оси с запасом под подпись самого длинного отрицательного столбца. */
function negativeRoom({ min, max }) {
  if (min >= 0) return 0
  const pad = Math.max(Math.abs(min) * 0.6, (Math.max(max, 0) - min) * 0.25)
  return Math.floor((min - pad) / 10) * 10
}

const pctOption = computed(() => {
  const t = theme.value
  const list = chartItems.value
  return {
    legend: { show: false },
    grid: { left: 8, right: 56, top: 8, bottom: 8, containLabel: true },
    tooltip: {
      trigger: 'axis', axisPointer: { type: 'shadow', shadowStyle: { color: t.border, opacity: 0.35 } },
      formatter: (params) => { const p = params[0]; return p ? tooltipFor(list[p.dataIndex], chartNames.value[p.dataIndex]) : '' },
    },
    // Запас слева под подписи отрицательных столбцов.
    // Граница с запасом обычно не совпадает с шагом делений — её подпись не показываем.
    xAxis: { type: 'value', min: negativeRoom, axisLabel: { showMinLabel: !list.some((m) => m.pct < 0), formatter: (v) => `${formatNumber(v)}%` } },
    yAxis: { type: 'category', inverse: true, data: chartNames.value, axisLine: { onZero: false, show: false }, axisLabel: { width: 210, overflow: 'truncate', color: t.text2 } },
    series: [{
      name: 'Изменение', type: 'bar', barMaxWidth: 14,
      data: list.map((m) => ({
        value: m.pct === null ? null : Math.round(m.pct * 10) / 10,
        itemStyle: { color: toneColor(m), borderRadius: m.pct < 0 ? [3, 0, 0, 3] : [0, 3, 3, 0] },
        label: { position: m.pct < 0 ? 'left' : 'right' },
      })),
      label: { show: true, color: t.text2, fontSize: 11, formatter: (p) => fmtPct(p.value) },
      markLine: { symbol: 'none', silent: true, animation: false, label: { show: false }, lineStyle: { color: t.muted, type: 'solid', width: 1 }, data: [{ xAxis: 0 }] },
    }],
  }
})

// Значения разного масштаба и единиц: длина столбца — доля от большего из двух значений показателя,
// подписи — фактические значения с единицами.
const valuesOption = computed(() => {
  const t = theme.value
  const list = chartItems.value
  const rel = (m, which) => {
    const top = Math.max(Math.abs(m.now ?? 0), Math.abs(m.prev ?? 0))
    const v = m[which]
    return v === null ? null : top > 0 ? (Math.abs(v) / top) * 100 : 0
  }
  const label = (which) => ({ show: true, position: 'right', color: t.text2, fontSize: 11,
    formatter: (p) => fmtValue(list[p.dataIndex][which], list[p.dataIndex].unit, list[p.dataIndex].digits) })
  return {
    legend: { data: [prevTitle.value, nowTitle.value] },
    grid: { left: 8, right: 84, top: 30, bottom: 4, containLabel: true },
    tooltip: {
      trigger: 'axis', axisPointer: { type: 'shadow', shadowStyle: { color: t.border, opacity: 0.35 } },
      formatter: (params) => { const p = params[0]; return p ? tooltipFor(list[p.dataIndex], chartNames.value[p.dataIndex]) : '' },
    },
    xAxis: { type: 'value', show: false, max: 100 },
    yAxis: { type: 'category', inverse: true, data: chartNames.value, axisLine: { show: false }, axisLabel: { width: 210, overflow: 'truncate', color: t.text2 } },
    series: [
      { name: prevTitle.value, type: 'bar', barMaxWidth: 11, barGap: '30%', data: list.map((m) => rel(m, 'prev')),
        itemStyle: { color: t.c(7), opacity: 0.55, borderRadius: [0, 3, 3, 0] }, label: label('prev') },
      { name: nowTitle.value, type: 'bar', barMaxWidth: 11, data: list.map((m) => rel(m, 'now')),
        itemStyle: { color: t.c(2), borderRadius: [0, 3, 3, 0] }, label: label('now') },
    ],
  }
})

const loadingFirst = computed(() => (reports.loading.value && !reports.data.value) || (columns.loading.value && !columns.data.value))
const weeksText = (n) => `${n} ${plural(n, ['неделя', 'недели', 'недель'])}`
</script>

<template>
  <div class="page">
    <PageHeader title="Сравнение периодов" description="Текущий интервал и предыдущий такой же длины: суммы за недели, для уровней и отношений — средние"
                :updatedAt="app.service('tech')?.data_updated_at">
      <router-link to="/tp" class="btn"><AppIcon name="grid" :size="15" />Дашборд</router-link>
    </PageHeader>

    <div class="filters card">
      <div class="f-row">
        <span class="f-label">Длина</span>
        <div class="row-wrap">
          <button v-for="q in QUICK_PERIODS" :key="q.value" type="button" class="chip" :class="{ active: f.quick === q.value }" @click="f.quick = q.value">{{ q.label }}</button>
        </div>
      </div>
      <div v-if="all.length" class="f-row intervals">
        <div class="interval">
          <span class="swatch now" />
          <div class="stack-tight">
            <strong>{{ nowTitle }}</strong>
            <span class="muted num">{{ periodRange(pair.now) || 'нет недель' }}<template v-if="pair.mode === 'halves'"> · {{ weeksText(pair.now.length) }}</template></span>
          </div>
        </div>
        <span class="vs muted">против</span>
        <div class="interval">
          <span class="swatch prev" />
          <div class="stack-tight">
            <strong>{{ prevTitle }}</strong>
            <span class="muted num">{{ periodRange(pair.prev) || 'нет недель' }}<template v-if="pair.mode === 'halves'"> · {{ weeksText(pair.prev.length) }}</template></span>
          </div>
        </div>
        <span class="spacer" />
        <div v-if="comparable" class="row-wrap tones" title="Оценка изменения по направлению показателя">
          <span class="badge badge-green"><AppIcon name="arrow-up" :size="11" :stroke="2.4" />Лучше · {{ counts.good }}</span>
          <span class="badge badge-red"><AppIcon name="arrow-down" :size="11" :stroke="2.4" />Хуже · {{ counts.bad }}</span>
          <span class="badge badge-gray">Без изменений · {{ counts.flat }}</span>
        </div>
      </div>
      <p v-if="all.length && !comparable" class="note"><AppIcon name="info" :size="14" />Для сравнения не хватает недель: в отчёте {{ weeksText(all.length) }}. Выберите период короче.</p>
      <p v-else-if="partial" class="note"><AppIcon name="info" :size="14" />Предыдущий интервал неполный — суммы за него меньше обычного.</p>
    </div>

    <template v-if="loadingFirst">
      <div class="grid grid-2">
        <div class="skeleton" style="height: 320px" />
        <div class="skeleton" style="height: 320px" />
      </div>
      <div class="skeleton" style="height: 420px" />
    </template>

    <EmptyState v-else-if="reports.error.value || columns.error.value" icon="alert" title="Не удалось загрузить отчёт" :text="(reports.error.value || columns.error.value).message">
      <button class="btn" type="button" @click="reports.reload(); columns.reload()"><AppIcon name="refresh" :size="14" />Повторить</button>
    </EmptyState>

    <EmptyState v-else-if="!all.length" icon="calendar" title="Данных пока нет" text="Добавьте недели в разделе «Недельный отчёт» — после этого здесь можно будет сравнить периоды.">
      <router-link to="/tp/registry" class="btn btn-primary">Недельный отчёт</router-link>
    </EmptyState>

    <template v-else>
      <section class="stack">
        <div class="section-title">
          <h2>Изменения по показателям</h2>
          <span class="muted">{{ groupOptions.find((g) => g.key === f.group)?.label }}</span>
          <span class="spacer" />
          <label class="field inline">
            <span>На графиках</span>
            <select v-model="f.group" class="select">
              <option v-for="g in groupOptions" :key="g.key" :value="g.key">{{ g.label }}</option>
            </select>
          </label>
        </div>
        <div class="grid grid-2">
          <ChartCard title="Изменение к предыдущему периоду" hint="%, зелёный — лучше, красный — хуже, серый — показатель без оценки направления"
                     :height="chartHeight" :empty="!comparable || !chartItems.length">
            <EChart :option="pctOption" />
          </ChartCard>
          <ChartCard title="Значения за периоды" hint="Длина — относительно большего из двух значений, подписи — фактические значения"
                     :height="chartHeight" :empty="!chartItems.length">
            <EChart :option="valuesOption" />
          </ChartCard>
        </div>
      </section>

      <section class="card">
        <header class="card-head">
          <div>
            <h3>Все показатели</h3>
            <p class="hint">«ср.» — среднее за недели интервала, остальные — суммы. Точка — светофор текущего интервала с порогами, умноженными на число недель.</p>
          </div>
        </header>
        <div class="table-wrap scroll-thin wrap">
          <table class="table table-compact">
            <thead>
              <tr>
                <th>Показатель</th>
                <th class="num">{{ nowTitle }}</th>
                <th class="num">{{ prevTitle }}</th>
                <th class="num">Изменение</th>
                <th class="num">%</th>
                <th class="spark-col">Динамика</th>
              </tr>
            </thead>
            <tbody v-for="g in groups" :key="g.key">
              <tr class="group-row"><td colspan="6">{{ g.label }}</td></tr>
              <tr v-for="m in g.items" :key="m.key">
                <td>
                  <span class="metric">{{ m.label }}</span>
                  <span v-if="isAvgMetric(m.key)" class="agg" title="Среднее за недели интервала">ср.</span>
                </td>
                <td class="num strong"><span class="val"><LightBadge v-if="m.light" :light="m.light" dot />{{ fmtValue(m.now, m.unit, m.digits) }}</span></td>
                <td class="num muted">{{ fmtValue(m.prev, m.unit, m.digits) }}</td>
                <td class="num" :class="`delta-${m.tone}`">{{ formatDelta(m.delta, m.unit, m.digits) || '—' }}</td>
                <td class="num" :class="`delta-${m.tone}`">{{ fmtPct(m.pct) }}</td>
                <td class="spark-col"><TpCompareSpark :values="sparks[m.key]" :split="pair.prev.length" /></td>
              </tr>
            </tbody>
          </table>
          <EmptyState v-if="!items.length" compact icon="table" title="Нет показателей" text="Список показателей отчёта не загрузился." />
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.filters { padding: 12px 16px; display: flex; flex-direction: column; gap: 10px; }
.f-row { display: flex; align-items: center; flex-wrap: wrap; gap: 8px 12px; }
.f-label { width: 56px; flex: 0 0 auto; font-size: var(--fs-xs); text-transform: uppercase; letter-spacing: .05em; color: var(--muted); font-weight: 620; }
.intervals { padding-top: 10px; border-top: 1px dashed var(--border); gap: 10px 16px; }
.interval { display: flex; align-items: center; gap: 10px; }
.stack-tight { display: flex; flex-direction: column; line-height: 1.3; }
.stack-tight strong { font-size: var(--fs-sm); font-weight: 620; }
.stack-tight .muted { font-size: var(--fs-xs); }
.swatch { width: 10px; height: 10px; border-radius: 3px; flex: 0 0 10px; }
.swatch.now { background: var(--chart-2); }
.swatch.prev { background: color-mix(in srgb, var(--chart-7) 55%, transparent); }
.vs { font-size: var(--fs-xs); }
.tones .badge { gap: 4px; }
.note { display: flex; align-items: center; gap: 6px; font-size: var(--fs-sm); color: var(--text-2); }
.field.inline { flex-direction: row; align-items: center; gap: 8px; }
.field.inline > span { font-size: var(--fs-xs); text-transform: uppercase; letter-spacing: .05em; color: var(--muted); font-weight: 620; white-space: nowrap; }
.field.inline .select { height: 32px; width: auto; min-width: 220px; }
.section-title { align-items: center; flex-wrap: wrap; }
.hint { margin-top: 2px; font-size: var(--fs-xs); color: var(--muted); }
.wrap { margin-top: 12px; border-top: 1px solid var(--border); border-radius: 0 0 var(--radius-lg) var(--radius-lg); }
.group-row td { background: var(--surface-2); font-size: var(--fs-xs); font-weight: 650; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); padding-top: 8px; padding-bottom: 8px; }
.metric { color: var(--text); }
.agg { margin-left: 6px; font-size: var(--fs-xs); color: var(--muted); padding: 0 5px; border: 1px solid var(--border); border-radius: var(--radius-sm); cursor: help; }
.strong { font-weight: 620; }
.val { display: inline-flex; align-items: center; gap: 6px; justify-content: flex-end; }
.spark-col { width: 128px; }
.table th:first-child, .table td:first-child { padding-left: var(--sp-5); }
@media (max-width: 640px) {
  .f-label { width: 100%; }
  .field.inline .select { min-width: 0; }
  .vs { display: none; }
}
</style>
