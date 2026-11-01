<script setup>
import { computed, ref, watch } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import KpiCard from '@/components/ui/KpiCard.vue'
import ChartCard from '@/components/ui/ChartCard.vue'
import EChart from '@/components/charts/EChart.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import LightBadge from '@/components/ui/LightBadge.vue'
import PdfButton from '@/components/ui/PdfButton.vue'
import LayoutDialog from '@/components/ui/LayoutDialog.vue'
import { hrApi } from '@/api/services'
import { useAsync } from '@/composables/useAsync'
import { useQueryState } from '@/composables/useQueryState'
import { useDashboardLayout } from '@/composables/useDashboardLayout'
import { useAuthStore } from '@/stores/auth'
import { useAppStore } from '@/stores/app'
import { axisNumber, lightColor } from '@/components/charts/echarts'
import { deltaTone, formatDelta, formatNumber, monthLabel, plural } from '@/utils/format'
import { KEY_METRICS, QUICK_PERIODS, funnelSteps, groupByCategory, kpiHint, kpiLabel, lastMonths, metricMap, metricSeries } from '@/domain/hr'

const auth = useAuthStore()
const app = useAppStore()
const { state: filters, reset } = useQueryState({ months: [], quick: 6 })

const months = useAsync(() => hrApi.months())
const allKeys = computed(() => (months.data.value || []).map((m) => m.key))
const selected = computed(() => (filters.months.length ? filters.months : lastMonths(allKeys.value, filters.quick)))

const { data, loading, reload, error } = useAsync(() => hrApi.dashboard(selected.value), { immediate: false })
const loadError = computed(() => (months.error.value && !months.data.value ? months.error.value : error.value && !data.value ? error.value : null))
function retry() {
  if (months.error.value) months.reload()
  else reload()
}
watch(selected, (v) => { if (v.length || months.data.value) reload() }, { immediate: true })

function pickQuick(value) {
  filters.months = []
  filters.quick = value
}
function toggleMonth(key) {
  const set = new Set(filters.months.length ? filters.months : selected.value)
  set.has(key) ? set.delete(key) : set.add(key)
  filters.months = allKeys.value.filter((k) => set.has(k))
}

const series = computed(() => data.value?.series || [])
const latest = computed(() => data.value?.latest)
const latestMap = computed(() => metricMap(latest.value))
const labels = computed(() => series.value.map((s) => monthLabel(s.key, true)))
const keyMetrics = computed(() => KEY_METRICS.map((k) => latestMap.value[k]).filter(Boolean))

const BLOCKS = [
  { key: 'kpi', label: 'Ключевые показатели' },
  { key: 'flow', label: 'Приём и увольнение' },
  { key: 'turnover', label: 'Текучесть кадров' },
  { key: 'funnel', label: 'Воронка найма' },
  { key: 'lights', label: 'Светофор по месяцам' },
  { key: 'departments', label: 'По подразделениям' },
  { key: 'table', label: 'Все метрики месяца' },
]
const layout = useDashboardLayout('hr', BLOCKS)
const layoutOpen = ref(false)
const blockStyle = (key) => ({ order: layout.orderOf(key) })

const people = (v) => (v === null || v === undefined ? '—' : formatNumber(v, { unit: 'чел.' }))
const flowOption = computed(() => ({
  legend: { data: ['Принято', 'Уволено', 'Прирост'] },
  tooltip: { valueFormatter: people },
  xAxis: { type: 'category', data: labels.value },
  yAxis: { type: 'value', minInterval: 1 },
  series: [
    { name: 'Принято', type: 'bar', barMaxWidth: 26, itemStyle: { color: lightColor('green'), borderRadius: [4, 4, 0, 0] }, data: series.value.map((s) => s.hired) },
    { name: 'Уволено', type: 'bar', barMaxWidth: 26, itemStyle: { color: lightColor('red'), borderRadius: [4, 4, 0, 0] }, data: series.value.map((s) => s.fired) },
    { name: 'Прирост', type: 'line', symbolSize: 6, lineStyle: { width: 2, type: 'dashed' }, data: series.value.map((s) => s.net) },
  ],
}))

const turnoverOption = computed(() => {
  const target = latestMap.value.turnover?.target
  return {
    legend: { data: ['Текучесть', 'По инициативе компании'] },
    tooltip: { valueFormatter: (v) => (v === null || v === undefined ? '—' : `${formatNumber(v)}%`) },
    xAxis: { type: 'category', data: labels.value, boundaryGap: false },
    yAxis: { type: 'value', axisLabel: { formatter: (v) => `${axisNumber(v)}%` } },
    series: [
      { name: 'Текучесть', type: 'line', smooth: true, symbolSize: 7, areaStyle: { opacity: 0.08 }, lineStyle: { width: 2.5 }, data: metricSeries(series.value, 'turnover'),
        markLine: target ? { symbol: 'none', label: { formatter: `Цель ${formatNumber(target)}%`, position: 'insideEndTop' }, lineStyle: { type: 'dashed', color: lightColor('red') }, data: [{ yAxis: target }] } : undefined },
      { name: 'По инициативе компании', type: 'line', smooth: true, symbolSize: 6, data: metricSeries(series.value, 'turnover_company') },
    ],
  }
})

const funnel = computed(() => funnelSteps(latest.value))
// Месяц без значений: пустые графики показывают «нет данных», а не пустую сетку
const hasTurnover = computed(() => [...metricSeries(series.value, 'turnover'), ...metricSeries(series.value, 'turnover_company')].some((v) => v !== null))
const hasFunnel = computed(() => funnel.value.some((s) => s.value !== null))
const funnelOption = computed(() => ({
  tooltip: { trigger: 'item', formatter: (p) => `${p.name}: <b>${formatNumber(p.value)}</b>${funnel.value[p.dataIndex].share !== null ? ` · ${funnel.value[p.dataIndex].share}%` : ''}` },
  grid: { left: 8, right: 48, top: 8, bottom: 8, containLabel: true },
  xAxis: { type: 'value', show: false },
  yAxis: { type: 'category', inverse: true, data: funnel.value.map((s) => s.label), axisLine: { show: false } },
  series: [{ type: 'bar', barWidth: 22, data: funnel.value.map((s) => s.value), itemStyle: { borderRadius: 6 },
    label: { show: true, position: 'right', formatter: (p) => formatNumber(p.value), color: 'inherit' } }],
}))

const lightsOption = computed(() => ({
  legend: { data: ['Норма', 'Внимание', 'Критично'] },
  tooltip: { axisPointer: { type: 'shadow' }, valueFormatter: (v) => `${formatNumber(v ?? 0)} ${plural(v ?? 0, ['метрика', 'метрики', 'метрик'])}` },
  xAxis: { type: 'category', data: labels.value, axisLabel: { interval: 0, hideOverlap: true } },
  yAxis: { type: 'value', minInterval: 1 },
  series: [['green', 'Норма'], ['yellow', 'Внимание'], ['red', 'Критично']].map(([l, name]) => ({
    name, type: 'bar', stack: 'l', barMaxWidth: 30, itemStyle: { color: lightColor(l) }, data: series.value.map((s) => s.light_counts[l]),
  })),
}))

const deptOption = computed(() => {
  const rows = (data.value?.departments || []).slice(0, 10)
  return {
    legend: { data: ['Принято', 'Уволено'] },
    tooltip: { valueFormatter: people, axisPointer: { type: 'shadow' } },
    grid: { left: 8, right: 16, top: 28, bottom: 8, containLabel: true },
    xAxis: { type: 'value', minInterval: 1 },
    yAxis: { type: 'category', inverse: true, data: rows.map((r) => r.department), axisLabel: { width: 180, overflow: 'truncate' } },
    series: [
      { name: 'Принято', type: 'bar', stack: 'd', itemStyle: { color: lightColor('green') }, data: rows.map((r) => r.hired) },
      { name: 'Уволено', type: 'bar', stack: 'd', itemStyle: { color: lightColor('red') }, data: rows.map((r) => r.fired) },
    ],
  }
})

const groups = computed(() => groupByCategory(latest.value?.metrics || []))
const periodText = computed(() => {
  const s = series.value
  if (!s.length) return ''
  return s.length === 1 ? s[0].label : `${s[0].label} — ${s[s.length - 1].label}`
})
</script>

<template>
  <div class="page">
    <PageHeader title="Служба персонала" :description="periodText ? `Период: ${periodText}` : 'Найм, адаптация, текучесть'" :updatedAt="app.service('hr')?.data_updated_at">
      <button class="btn btn-ghost" type="button" title="Состав и порядок блоков" @click="layoutOpen = true"><AppIcon name="settings" :size="15" />Настроить</button>
      <router-link v-if="auth.can('hr', 'editor')" to="/hr/data" class="btn"><AppIcon name="edit" :size="15" />Ввод данных</router-link>
      <PdfButton report="hr/dashboard" :params="{ months: selected }" />
    </PageHeader>

    <div class="period card">
      <div class="row-wrap">
        <button v-for="q in QUICK_PERIODS" :key="q.value" type="button" class="chip" :class="{ active: !filters.months.length && filters.quick === q.value }" @click="pickQuick(q.value)">{{ q.label }}</button>
      </div>
      <div class="months row-wrap">
        <button v-for="m in months.data.value || []" :key="m.key" type="button" class="chip month" :class="{ active: selected.includes(m.key) }" :title="`${m.label}: принято ${m.hired}, уволено ${m.fired}`" @click="toggleMonth(m.key)">
          {{ monthLabel(m.key, true) }}
        </button>
        <button v-if="filters.months.length" type="button" class="btn btn-sm btn-ghost" @click="reset">Сбросить</button>
      </div>
    </div>

    <EmptyState v-if="months.data.value && !months.data.value.length" icon="calendar" title="Данных пока нет"
                text="Добавьте первый месяц в разделе «Ввод данных» — после этого здесь появятся показатели.">
      <router-link v-if="auth.can('hr', 'editor')" to="/hr/data" class="btn btn-primary">Ввод данных</router-link>
    </EmptyState>

    <EmptyState v-else-if="loadError" icon="alert" title="Не удалось загрузить дашборд" :text="loadError.message">
      <button class="btn" type="button" @click="retry"><AppIcon name="refresh" :size="14" />Повторить</button>
    </EmptyState>

    <div v-else class="blocks">
      <section v-if="layout.visible('kpi')" class="stack" :style="blockStyle('kpi')">
        <div class="section-title"><h2>Ключевые показатели</h2><span class="muted">{{ latest ? `за ${latest.label}, изменение к предыдущему месяцу` : '' }}</span></div>
        <div class="grid grid-kpi">
          <KpiCard label="Принято за период" :value="data?.totals.hired" unit="чел." :loading="loading && !data" />
          <KpiCard label="Уволено за период" :value="data?.totals.fired" unit="чел." :loading="loading && !data" />
          <KpiCard label="Чистый прирост" :value="data?.totals.net" unit="чел." :loading="loading && !data" />
          <KpiCard v-for="m in keyMetrics" :key="m.key" :label="kpiLabel(m)" :value="m.value" :unit="m.unit" :light="m.light"
                   :delta="m.delta" :direction="m.direction" :target="m.target" :hint="kpiHint(m)" />
        </div>
      </section>

      <div class="grid grid-2" :style="{ order: Math.min(layout.orderOf('flow'), layout.orderOf('turnover')) }">
        <ChartCard v-if="layout.visible('flow')" title="Приём и увольнение" hint="По месяцам периода" :loading="loading && !data" :empty="!series.length">
          <EChart :option="flowOption" />
        </ChartCard>
        <ChartCard v-if="layout.visible('turnover')" title="Текучесть кадров" hint="Накопительно с начала года, %" :loading="loading && !data" :empty="!hasTurnover">
          <EChart :option="turnoverOption" />
        </ChartCard>
      </div>

      <div class="grid grid-3" :style="{ order: Math.min(layout.orderOf('funnel'), layout.orderOf('lights'), layout.orderOf('departments')) }">
        <ChartCard v-if="layout.visible('funnel')" title="Воронка найма" :hint="latest ? latest.label : ''" :height="260" :loading="loading && !data" :empty="!latest || !hasFunnel">
          <EChart :option="funnelOption" />
        </ChartCard>
        <ChartCard v-if="layout.visible('lights')" title="Светофор по месяцам" hint="Сколько метрик в норме, требует внимания, критично" :height="260" :loading="loading && !data" :empty="!series.length">
          <EChart :option="lightsOption" />
        </ChartCard>
        <ChartCard v-if="layout.visible('departments')" title="По подразделениям" hint="Приёмы и увольнения за период" :height="260" :loading="loading && !data" :empty="!data?.departments?.length">
          <EChart :option="deptOption" />
        </ChartCard>
      </div>

      <section v-if="layout.visible('table') && latest" class="card" :style="blockStyle('table')">
        <header class="card-head">
          <h3>Все метрики за {{ latest.label }}</h3>
          <span class="spacer" />
          <router-link v-if="auth.can('hr', 'editor')" :to="{ path: '/hr/data', query: { month: latest.key } }" class="btn btn-sm"><AppIcon name="edit" :size="13" />Изменить</router-link>
        </header>
        <div class="card-body table-wrap">
          <table class="table">
            <thead><tr><th>Метрика</th><th class="num">Значение</th><th class="num">Прошлый месяц</th><th class="num">Изменение</th><th class="num">Цель</th><th>Оценка</th></tr></thead>
            <tbody v-for="g in groups" :key="g.key">
              <tr class="group-row"><td colspan="6">{{ g.label }}</td></tr>
              <tr v-for="m in g.items" :key="m.key">
                <td><span :title="m.description">{{ m.label }}</span><div v-if="m.source_note" class="note">{{ m.source_note }}</div></td>
                <td class="num strong">{{ formatNumber(m.value, { unit: m.unit }) }}</td>
                <td class="num muted">{{ formatNumber(m.previous, { unit: m.unit }) }}</td>
                <td class="num" :class="`delta-${deltaTone(m.delta, m.direction)}`">{{ formatDelta(m.delta, m.unit) }}</td>
                <td class="num muted">{{ formatNumber(m.target, { unit: m.unit }) }}</td>
                <td><LightBadge :light="m.light" /></td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>

    <LayoutDialog v-if="layoutOpen" :items="layout.ordered.value" @close="layoutOpen = false" @save="layout.save" @reset="layout.reset" />
  </div>
</template>

<style scoped>
.period { padding: 12px 16px; display: flex; flex-direction: column; gap: 10px; }
.months { padding-top: 10px; border-top: 1px dashed var(--border); }
.chip.month { height: 26px; padding: 0 10px; text-transform: capitalize; }
.blocks { display: flex; flex-direction: column; gap: var(--sp-5); }
.group-row td { background: var(--surface-2); font-size: var(--fs-xs); font-weight: 650; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); padding-top: 8px; padding-bottom: 8px; }
.strong { font-weight: 620; }
.note { font-size: var(--fs-xs); color: var(--muted); margin-top: 2px; }
</style>
