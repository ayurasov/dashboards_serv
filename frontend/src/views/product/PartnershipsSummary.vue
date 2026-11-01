<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import AppIcon from '@/components/ui/AppIcon.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import KpiCard from '@/components/ui/KpiCard.vue'
import ChartCard from '@/components/ui/ChartCard.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import LightBadge from '@/components/ui/LightBadge.vue'
import PdfButton from '@/components/ui/PdfButton.vue'
import EChart from '@/components/charts/EChart.vue'
import { partnershipsApi } from '@/api/services'
import { useAuthStore } from '@/stores/auth'
import { useAsync } from '@/composables/useAsync'
import { useQueryState } from '@/composables/useQueryState'
import { axisNumber, cssVar, lightColor } from '@/components/charts/echarts'
import { formatNumber } from '@/utils/format'
import { LIGHT_LABELS } from '@/utils/lights'
import { countWord, lightSegments, orderStatuses, share, sortedEntries, summaryTotals, yearDelta } from '@/domain/partnerships'

const router = useRouter()
const auth = useAuthStore()
// Переходы в реестр — только с правом на исходные записи (ADR-0009)
const canRegistry = computed(() => auth.canRecords)
const { state: f } = useQueryState({ year: 0 })
const { data, loading } = useAsync(() => partnershipsApi.summary())

const periods = computed(() => data.value || [])
const newestFirst = computed(() => [...periods.value].reverse())
const index = computed(() => {
  const i = periods.value.findIndex((p) => p.year === f.year)
  return i >= 0 ? i : periods.value.length - 1
})
const current = computed(() => periods.value[index.value] || null)
const previous = computed(() => (index.value > 0 ? periods.value[index.value - 1] : null))
const totals = computed(() => summaryTotals(periods.value))
const LIGHTS = ['green', 'yellow', 'red']

function pick(year) {
  f.year = year === periods.value.at(-1)?.year ? 0 : year
}

// ---------- показатели выбранного года ----------
const KPI = [
  { key: 'total', label: 'Сертификаций', direction: 'higher_is_better' },
  { key: 'green', label: 'Норма', direction: 'higher_is_better', light: 'green' },
  { key: 'yellow', label: 'Внимание', direction: 'lower_is_better', light: 'yellow' },
  { key: 'red', label: 'Критично', direction: 'lower_is_better', light: 'red' },
  { key: 'nda_count', label: 'NDA подписан', direction: 'higher_is_better' },
  { key: 'agreement_count', label: 'Соглашение', direction: 'higher_is_better' },
]
const kpis = computed(() => KPI.map((k) => ({
  ...k,
  value: current.value ? current.value[k.key] : null,
  delta: yearDelta(current.value, previous.value, k.key),
  hint: current.value && k.key !== 'total' ? `${formatNumber(share(current.value[k.key], current.value.total))}% от партнёрств ${current.value.year} года` : '',
})))

// ---------- графики ----------
const years = computed(() => periods.value.map((p) => String(p.year)))
const lightsOption = computed(() => {
  const labels = { green: LIGHT_LABELS.green, yellow: LIGHT_LABELS.yellow, red: LIGHT_LABELS.red }
  return {
    legend: { data: LIGHTS.map((l) => labels[l]) },
    tooltip: { axisPointer: { type: 'shadow' } },
    xAxis: { type: 'category', data: years.value },
    yAxis: { type: 'value', minInterval: 1 },
    series: LIGHTS.map((l, i) => ({
      name: labels[l], type: 'bar', stack: 'lights', barMaxWidth: 34,
      itemStyle: { color: lightColor(l), borderColor: cssVar('--surface', '#fff'), borderWidth: 1, borderRadius: i === LIGHTS.length - 1 ? [4, 4, 0, 0] : 0 },
      data: periods.value.map((p) => p[l]),
      label: i === LIGHTS.length - 1
        ? { show: true, position: 'top', color: cssVar('--text-2'), fontSize: 11, formatter: (p) => formatNumber(periods.value[p.dataIndex].total) }
        : undefined,
    })),
  }
})

const docsOption = computed(() => ({
  legend: { data: ['NDA подписан', 'Соглашение подписано'] },
  tooltip: { valueFormatter: (v) => (v === null || v === undefined ? '—' : `${formatNumber(v)}%`) },
  xAxis: { type: 'category', data: years.value, boundaryGap: false },
  yAxis: { type: 'value', max: 100, axisLabel: { formatter: (v) => `${axisNumber(v)}%` } },
  series: [
    { name: 'NDA подписан', type: 'line', symbolSize: 7, lineStyle: { width: 2 }, itemStyle: { color: cssVar('--chart-2') },
      data: periods.value.map((p) => share(p.nda_count, p.total)) },
    { name: 'Соглашение подписано', type: 'line', symbolSize: 7, lineStyle: { width: 2 }, itemStyle: { color: cssVar('--chart-5') },
      data: periods.value.map((p) => share(p.agreement_count, p.total)) },
  ],
}))

// ---------- разбивка выбранного года ----------
const statusRows = computed(() => {
  const counts = current.value?.by_status || {}
  return orderStatuses(Object.keys(counts)).map((name) => ({ name, count: counts[name], share: share(counts[name], current.value.total) }))
})
const productRows = computed(() => sortedEntries(current.value?.by_almi_product)
  .map(([name, count]) => ({ name, count, share: share(count, current.value.total) })))

function toRegistry(extra = {}) {
  if (!canRegistry.value) return
  router.push({ path: '/product/registry', query: { year: String(current.value.year), ...extra } })
}
</script>

<template>
  <div class="page">
    <PageHeader title="Сводка по годам" description="Партнёрства по году сертификации: оценка светофора, NDA и соглашения">
      <router-link to="/product" class="btn btn-ghost"><AppIcon name="grid" :size="15" />Дашборд</router-link>
      <PdfButton report="partnerships/summary" />
    </PageHeader>

    <div v-if="loading && !data" class="stack">
      <div class="skeleton" style="height: 52px" />
      <div class="grid grid-kpi"><div v-for="i in 6" :key="i" class="skeleton" style="height: 112px" /></div>
      <div class="skeleton" style="height: 320px" />
    </div>

    <EmptyState v-else-if="data && !periods.length" icon="calendar" title="Нет партнёрств с датой сертификата"
                text="Сводка строится по году сертификата. Укажите дату сертификата в реестре — и годы появятся здесь.">
      <router-link v-if="canRegistry" to="/product/registry" class="btn btn-primary">Открыть реестр</router-link>
    </EmptyState>

    <template v-else-if="current">
      <div class="years card">
        <span class="years-label">Год сертификации</span>
        <div class="row-wrap">
          <button v-for="p in newestFirst" :key="p.year" type="button" class="chip" :class="{ active: p.year === current.year }" :aria-pressed="p.year === current.year" @click="pick(p.year)">
            {{ p.year }}<span class="chip-count num">{{ p.total }}</span>
          </button>
        </div>
      </div>

      <section class="stack">
        <div class="section-title">
          <h2>{{ current.label }}</h2>
          <span class="muted">{{ previous ? `изменение к ${previous.year} году` : 'предыдущего года в данных нет' }}</span>
          <span class="spacer" />
          <button v-if="canRegistry" class="btn btn-sm btn-ghost" type="button" @click="toRegistry()">Записи года в реестре<AppIcon name="chevron-right" :size="13" /></button>
        </div>
        <div class="grid grid-kpi kpis">
          <KpiCard v-for="k in kpis" :key="k.key" :label="k.label" :value="k.value" :light="k.light || ''" :delta="k.delta"
                   :direction="k.direction" :deltaLabel="previous ? `к ${previous.year}` : ''" :hint="k.hint" :digits="0" />
        </div>
      </section>

      <div class="grid grid-2">
        <ChartCard title="Оценка по годам" hint="Записи по итоговому светофору; над столбцом — всего за год" :height="290">
          <EChart :option="lightsOption" @click="(p) => pick(Number(p.name))" />
        </ChartCard>
        <ChartCard title="NDA и соглашения" hint="Доля партнёрств года с подписанными документами" :height="290">
          <EChart :option="docsOption" />
        </ChartCard>
      </div>

      <section class="card">
        <header class="card-head">
          <h3>Показатели по годам</h3>
          <span class="hint">Щелчок по строке выбирает год</span>
        </header>
        <div class="card-body table-wrap flush">
          <table class="table">
            <thead>
              <tr>
                <th>Год</th>
                <th class="num">Всего</th>
                <th class="col-bar">Оценка</th>
                <th v-for="l in LIGHTS" :key="l" class="num"><LightBadge :light="l" dot class="th-dot" />{{ LIGHT_LABELS[l] }}</th>
                <th class="num">NDA</th>
                <th class="num">Соглашения</th>
                <th>Продукты АЛМИ</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="p in newestFirst" :key="p.year" class="clickable" :class="{ selected: p.year === current.year }" @click="pick(p.year)">
                <td class="year">{{ p.year }}</td>
                <td class="num strong">{{ formatNumber(p.total) }}</td>
                <td class="col-bar">
                  <div class="stackbar" :title="lightSegments(p).map((s) => `${LIGHT_LABELS[s.light]}: ${s.count} (${formatNumber(s.share)}%)`).join('\n')">
                    <span v-for="s in lightSegments(p)" v-show="s.count" :key="s.light" class="seg" :class="s.light" :style="{ flexGrow: s.count }" />
                  </div>
                </td>
                <td v-for="l in LIGHTS" :key="l" class="num">
                  <span :class="{ zero: !p[l] }">{{ formatNumber(p[l]) }}</span>
                  <span class="pct">{{ formatNumber(share(p[l], p.total, 0)) }}%</span>
                </td>
                <td class="num">{{ formatNumber(p.nda_count) }}<span class="pct">{{ formatNumber(share(p.nda_count, p.total, 0)) }}%</span></td>
                <td class="num">{{ formatNumber(p.agreement_count) }}<span class="pct">{{ formatNumber(share(p.agreement_count, p.total, 0)) }}%</span></td>
                <td class="products">
                  <span v-for="[name, count] in sortedEntries(p.by_almi_product, 2)" :key="name" class="badge">{{ name }} <b class="num">{{ count }}</b></span>
                  <span v-if="Object.keys(p.by_almi_product).length > 2" class="muted more">+{{ Object.keys(p.by_almi_product).length - 2 }}</span>
                </td>
              </tr>
            </tbody>
            <tfoot>
              <tr>
                <td>Все годы</td>
                <td class="num">{{ formatNumber(totals.total) }}</td>
                <td class="col-bar">
                  <div class="stackbar">
                    <span v-for="s in lightSegments(totals)" v-show="s.count" :key="s.light" class="seg" :class="s.light" :style="{ flexGrow: s.count }" />
                  </div>
                </td>
                <td v-for="l in LIGHTS" :key="l" class="num">{{ formatNumber(totals[l]) }}<span class="pct">{{ formatNumber(share(totals[l], totals.total, 0)) }}%</span></td>
                <td class="num">{{ formatNumber(totals.nda_count) }}<span class="pct">{{ formatNumber(share(totals.nda_count, totals.total, 0)) }}%</span></td>
                <td class="num">{{ formatNumber(totals.agreement_count) }}<span class="pct">{{ formatNumber(share(totals.agreement_count, totals.total, 0)) }}%</span></td>
                <td />
              </tr>
            </tfoot>
          </table>
        </div>
      </section>

      <div class="grid grid-2">
        <section class="card">
          <header class="card-head"><h3>Статусы</h3><span class="hint">{{ current.label }}</span></header>
          <div class="card-body">
            <ul class="bars">
              <li v-for="r in statusRows" :key="r.name">
                <button type="button" class="bar-row" :disabled="!canRegistry" :title="canRegistry ? `Открыть в реестре: ${r.name}, ${current.year}` : r.name" @click="toRegistry({ status: r.name })">
                  <span class="bar-label">{{ r.name }}</span>
                  <span class="bar-track"><span class="bar-fill" :style="{ width: `${r.share}%` }" /></span>
                  <b class="num">{{ formatNumber(r.count) }}</b>
                  <span class="pct num">{{ formatNumber(r.share) }}%</span>
                </button>
              </li>
            </ul>
          </div>
        </section>
        <section class="card">
          <header class="card-head"><h3>Продукты АЛМИ</h3><span class="hint">{{ current.label }}, {{ formatNumber(current.total) }} {{ countWord(current.total) }}</span></header>
          <div class="card-body">
            <ul v-if="productRows.length" class="bars">
              <li v-for="r in productRows" :key="r.name">
                <button type="button" class="bar-row" :disabled="!canRegistry" :title="canRegistry ? `Открыть в реестре: ${r.name}, ${current.year}` : r.name" @click="toRegistry({ almi_product: r.name })">
                  <span class="bar-label">{{ r.name }}</span>
                  <span class="bar-track"><span class="bar-fill alt" :style="{ width: `${r.share}%` }" /></span>
                  <b class="num">{{ formatNumber(r.count) }}</b>
                  <span class="pct num">{{ formatNumber(r.share) }}%</span>
                </button>
              </li>
            </ul>
            <p v-else class="muted">Продукт АЛМИ не указан ни в одной записи года</p>
          </div>
        </section>
      </div>
    </template>
  </div>
</template>

<style scoped>
.years { display: flex; align-items: center; gap: 10px 14px; flex-wrap: wrap; padding: 12px 16px; }
.years-label { font-size: var(--fs-xs); text-transform: uppercase; letter-spacing: .05em; color: var(--muted); font-weight: 620; }
.chip-count { font-size: var(--fs-xs); color: var(--muted); font-weight: 560; }
.chip.active .chip-count { color: inherit; opacity: .7; }
.kpis { grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); }
.section-title .btn { gap: 4px; }

.flush { padding: 12px 0 0; border-radius: 0 0 var(--radius-lg) var(--radius-lg); }
.th-dot { display: inline-block; margin-right: 6px; vertical-align: 0; }
.table td.num, .table td:first-child { white-space: nowrap; }
.year { font-weight: 620; font-variant-numeric: tabular-nums; }
.strong { font-weight: 620; }
.col-bar { width: 22%; min-width: 140px; }
.stackbar { display: flex; gap: 2px; height: 8px; border-radius: 4px; overflow: hidden; background: var(--surface-3); }
.seg { min-width: 3px; }
.seg.green { background: var(--light-green); }
.seg.yellow { background: var(--light-yellow); }
.seg.red { background: var(--light-red); }
.pct { display: inline-block; min-width: 42px; margin-left: 6px; color: var(--muted); font-size: var(--fs-xs); text-align: right; }
.zero { color: var(--faint); }
tr.selected td { background: color-mix(in srgb, var(--chart-2) 7%, transparent); }
tr.selected td:first-child { box-shadow: inset 3px 0 0 var(--chart-2); }
.products { white-space: nowrap; }
.products .badge { margin-right: 4px; font-weight: 560; }
.products .badge b { font-weight: 680; color: var(--text); }
.more { font-size: var(--fs-xs); }

.bars { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 2px; }
.bar-row { width: 100%; display: grid; grid-template-columns: minmax(110px, 180px) 1fr 44px 52px; align-items: center; gap: 12px; padding: 7px 8px; border: 0; border-radius: var(--radius-sm); background: transparent; color: var(--text); font-size: var(--fs-sm); text-align: left; cursor: pointer; transition: background var(--t-fast); }
.bar-row:hover:not(:disabled) { background: var(--row-hover); }
.bar-row:disabled { cursor: default; color: var(--text); }
.bar-label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text-2); }
.bar-track { height: 8px; border-radius: 4px; background: var(--surface-3); overflow: hidden; }
.bar-fill { display: block; height: 100%; border-radius: 4px; background: var(--chart-2); }
.bar-fill.alt { background: var(--chart-5); }
.bar-row b { text-align: right; font-weight: 650; }
.bar-row .pct { margin: 0; }
</style>
