<template>
  <div v-if="loading" class="tempty">Загрузка…</div>
  <template v-else>
    <div class="filters">
      <select class="fsel" v-model="periodType">
        <option value="quarter">Квартал</option>
        <option value="half">Полугодие</option>
        <option value="year">Год</option>
      </select>
      <template v-if="rangeOptions.length">
        <span class="fl">С</span>
        <select class="fsel" v-model="fromPeriod" @change="onRangeChange('from')">
          <option value="">все периоды</option>
          <option v-for="label in rangeOptions" :key="label" :value="label">{{ label }}</option>
        </select>
        <span class="fl">По</span>
        <select class="fsel" v-model="toPeriod" @change="onRangeChange('to')">
          <option value="">все периоды</option>
          <option v-for="label in rangeOptions" :key="label" :value="label">{{ label }}</option>
        </select>
      </template>
      <select class="fsel" v-model="selectedLabel" v-if="periods.length">
        <option v-for="p in periods" :key="p.label" :value="p.label">{{ p.label }}</option>
      </select>
      <div class="tinfo" style="flex:1;margin:0" v-if="current">
        {{ current.label }}: месяцев — {{ current.months_count }}<template v-if="previous">, сравнение с {{ previous.label }}</template>
        <template v-if="rangeText">. Диапазон: {{ rangeText }}</template>
      </div>
    </div>

    <!-- KPI cards for the selected period, with deltas against the previous one -->
    <div class="kpi-grid" v-if="current">
      <div class="kpi">
        <div class="kpi-lbl">Принято</div>
        <div class="kpi-val" style="color:var(--c-ok)">{{ current.hired }}</div>
        <div class="kpi-sub" v-if="previous">
          <span class="dtrend" :class="trendClass(current.hired, previous.hired, 'higher')">
            {{ arrow(current.hired, previous.hired) }} {{ delta(current.hired - previous.hired) }}
          </span>
          к {{ previous.label }}
        </div>
      </div>
      <div class="kpi">
        <div class="kpi-lbl">Уволено</div>
        <div class="kpi-val" style="color:var(--c-err)">{{ current.fired }}</div>
        <div class="kpi-sub" v-if="previous">
          <span class="dtrend" :class="trendClass(current.fired, previous.fired, 'lower')">
            {{ arrow(current.fired, previous.fired) }} {{ delta(current.fired - previous.fired) }}
          </span>
          к {{ previous.label }}
        </div>
      </div>
      <div class="kpi">
        <div class="kpi-lbl">Чистый прирост</div>
        <div class="kpi-val" :style="{color: current.net>=0?'var(--c-ok)':'var(--c-err)'}">
          {{ current.net>=0?'+':'' }}{{ current.net }}
        </div>
        <div class="kpi-sub" v-if="previous">
          <span class="dtrend" :class="trendClass(current.net, previous.net, 'higher')">
            {{ arrow(current.net, previous.net) }} {{ delta(current.net - previous.net) }}
          </span>
          к {{ previous.label }}
        </div>
      </div>
      <div class="kpi" v-for="m in keyMetrics" :key="m.key">
        <div class="kpi-lbl">{{ m.label }}</div>
        <div class="kpi-val">{{ fmt(m.value, m.unit) }}</div>
        <div class="kpi-sub" v-if="m.prev !== null && m.prev !== undefined">
          <span class="dtrend" :class="trendClass(m.value, m.prev, m.better)">
            {{ arrow(m.value, m.prev) }} {{ delta(round2(m.value - m.prev)) }}{{ m.unit === '%' ? '%' : '' }}
          </span>
          к пред. периоду
        </div>
        <div class="kpi-sub" v-else>нет данных за пред. период</div>
      </div>
    </div>

    <!-- Traffic light summary per period -->
    <div class="cgrid-2">
      <div class="ccard">
        <div class="ctitle">Светофор по периодам</div>
        <e-chart :option="lightPeriodOpt" :height="240" />
      </div>
      <div class="ccard">
        <div class="ctitle">Светофор — {{ current?.label || '—' }}</div>
        <div class="slist">
          <div class="slist-row" v-for="l in LIGHTS" :key="l.key">
            <span class="light-dot" :class="'light-' + l.key"></span>
            <span class="slist-lbl">{{ l.label }}</span>
            <span class="slist-val">{{ currentLights[l.key] }}</span>
          </div>
          <div class="slist-row">
            <span class="slist-lbl">Всего оценённых метрик</span>
            <span class="slist-val">{{ currentLights.total }}</span>
          </div>
          <div class="slist-row">
            <span class="slist-lbl">Не заполнено</span>
            <span class="slist-val">{{ currentLights.unfilled }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Dynamics -->
    <div class="cgrid-2">
      <div class="ccard">
        <div class="ctitle">Динамика ключевых метрик по месяцам</div>
        <e-chart :option="dynamicsOpt" :height="260" />
      </div>
      <div class="ccard">
        <div class="ctitle">Статусы метрик по месяцам — {{ current?.label || '—' }}</div>
        <e-chart :option="lightMonthOpt" :height="260" />
      </div>
    </div>

    <div class="cgrid-2">
      <div class="ccard">
        <div class="ctitle">Динамика по периодам</div>
        <e-chart :option="periodChartOpt" :height="260" />
      </div>
      <div class="ccard">
        <div class="ctitle">Метрики по периодам</div>
        <div class="twrap">
          <div class="tscroll">
            <table>
              <thead><tr><th>Метрика</th><th v-for="p in periods" :key="p.label">{{ p.label }}</th></tr></thead>
              <tbody>
                <tr v-for="m in aggregatedMetrics" :key="m.metric_key">
                  <td class="td-p">{{ m.label }}</td>
                  <td v-for="p in periods" :key="p.label" class="td-mono">
                    {{ fmtMetric(p, m.metric_key, m.unit) }}
                  </td>
                </tr>
                <tr v-if="!aggregatedMetrics.length"><td :colspan="periods.length+1" class="tempty">Нет данных</td></tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>

    <!-- All metrics per month inside the selected period -->
    <div class="ccard">
      <div class="ctitle">Метрики по месяцам — {{ current?.label || '—' }}</div>
      <div class="twrap">
        <div class="tscroll">
          <table>
            <thead>
              <tr>
                <th>Метрика</th>
                <th v-for="m in currentMonths" :key="m.key">{{ m.label }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="d in metricDefs" :key="d.key">
                <td class="td-p">{{ d.label }}</td>
                <td v-for="m in currentMonths" :key="m.key" class="td-mono">
                  <span class="light-dot" :class="'light-' + monthLight(m.key, d.key)"></span>
                  {{ fmt(monthValue(m.key, d.key), d.unit) }}
                </td>
              </tr>
              <tr v-if="!currentMonths.length"><td :colspan="1" class="tempty">Нет месяцев в периоде</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </template>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { api } from '../api/client.js'
import EChart from '../components/EChart.vue'
import { setPdfParams } from '../composables/usePdfExport.js'
import { usePaletteStore } from '../stores/palette.js'

const palette = usePaletteStore()
const loading = ref(true)
const periodType = ref('quarter')
const selectedLabel = ref('')
// Empty bounds mean «all periods», which is what the API returns without them.
const fromPeriod = ref('')
const toPeriod = ref('')
const summary = ref([])
const metricDefs = ref([])
const months = ref([])
const monthAnalytics = ref({})

// The topbar PDF button reads this, so its export matches the period on screen.
setPdfParams(() => ({
  period_type: periodType.value,
  from_period: fromPeriod.value,
  to_period: toPeriod.value,
}))

const LIGHTS = [
  { key: 'green', label: 'Норма' },
  { key: 'yellow', label: 'Внимание' },
  { key: 'red', label: 'Критично' },
]
// Always reads from the active palette's traffic-light colours, never a fixed hex
// set, so a preset switch repaints these charts along with the rest of the UI.
const LIGHT_COLORS = computed(() => {
  const tl = palette.trafficLight
  return { green: tl.green, yellow: tl.yellow, red: tl.red }
})

// Key metrics shown as comparison cards; `better` drives the arrow colour.
const KEY_METRICS = [
  { key: 'turnover', better: 'lower' },
  { key: 'avg_time_to_fill', better: 'lower' },
  { key: 'offers_accepted_pct', better: 'higher' },
  { key: 'probation_pass_rate', better: 'higher' },
]

function fmt(val, unit) {
  if (val === null || val === undefined) return '—'
  if (unit === '%') return val.toFixed(2).replace('.', ',') + '%'
  if (unit === 'дн.') return val.toFixed(1).replace('.', ',')
  if (unit === 'чел.' || unit === 'шт.') return Math.round(val)
  return String(val).replace('.', ',')
}

function round2(v) { return Math.round(v * 100) / 100 }
function delta(diff) { return diff > 0 ? `+${diff}` : String(diff) }
function arrow(cur, prev) { return cur === prev ? '→' : (cur > prev ? '↑' : '↓') }
function trendClass(cur, prev, better) {
  if (cur === prev) return 'flat'
  const up = cur > prev
  if (better === 'lower') return up ? 'down' : 'up'
  return up ? 'up' : 'down'
}

const defMap = computed(() => new Map(metricDefs.value.map(d => [d.key, d])))

// The API returns metrics as a flat { key: number } map; expand it into rows and
// pull labels/units from the metric definitions.
const periods = computed(() => summary.value.map(p => ({
  ...p,
  metrics: Object.entries(p.metrics || {}).map(([key, value]) => {
    const d = defMap.value.get(key)
    return { key, value, label: d?.label || key, unit: d?.unit || '', sort: d?.sort_order ?? 999 }
  }).sort((a, b) => a.sort - b.sort),
})))

const currentIndex = computed(() => {
  const i = periods.value.findIndex(p => p.label === selectedLabel.value)
  return i >= 0 ? i : periods.value.length - 1
})
const current = computed(() => periods.value[currentIndex.value] || null)
const previous = computed(() => (currentIndex.value > 0 ? periods.value[currentIndex.value - 1] : null))

function periodMetric(period, key) {
  const hit = period?.metrics.find(m => m.key === key)
  return hit && hit.value !== null && hit.value !== undefined ? hit.value : null
}

const keyMetrics = computed(() => KEY_METRICS.map(k => {
  const d = defMap.value.get(k.key)
  return {
    key: k.key, better: k.better,
    label: d?.label || k.key, unit: d?.unit || '',
    value: periodMetric(current.value, k.key),
    prev: periodMetric(previous.value, k.key),
  }
}).filter(m => m.value !== null))

// ---------- Month → period mapping (mirrors the backend period rules) ----------

function labelFor(year, month) {
  if (periodType.value === 'quarter') return `Q${Math.ceil(month / 3)} ${year}`
  if (periodType.value === 'half') return month <= 6 ? `I полугодие ${year}` : `II полугодие ${year}`
  return `${year} год`
}

function monthPeriodLabel(key) {
  const [y, m] = key.split('-').map(Number)
  return labelFor(y, m)
}

// ---------- «С» / «По» range ----------

// Derived from the months actually loaded, in chronological order, so the option
// list matches the labels the API builds for the same data.
const rangeOptions = computed(() => {
  const seen = []
  for (const m of months.value) {
    const label = monthPeriodLabel(m.key)
    if (!seen.includes(label)) seen.push(label)
  }
  return seen
})

const rangeText = computed(() => {
  if (!fromPeriod.value && !toPeriod.value) return ''
  const first = periods.value[0]?.label
  const last = periods.value.at(-1)?.label
  if (!first) return ''
  return first === last ? first : `${first} — ${last}`
})

// An inverted range would ask the API for nonsense, so the untouched bound follows
// the one the user just moved.
function onRangeChange(edited) {
  const lo = rangeOptions.value.indexOf(fromPeriod.value)
  const hi = rangeOptions.value.indexOf(toPeriod.value)
  if (lo >= 0 && hi >= 0 && lo > hi) {
    if (edited === 'from') toPeriod.value = fromPeriod.value
    else fromPeriod.value = toPeriod.value
  }
  loadSummary()
}

const currentMonths = computed(() =>
  months.value.filter(m => monthPeriodLabel(m.key) === current.value?.label))

function monthMetric(monthKey, metricKey) {
  return monthAnalytics.value[monthKey]?.metrics?.find(m => m.key === metricKey)
}
function monthValue(monthKey, metricKey) {
  const m = monthMetric(monthKey, metricKey)
  return m && m.value !== null && m.value !== undefined ? m.value : null
}
function monthLight(monthKey, metricKey) {
  return monthMetric(monthKey, metricKey)?.light || 'gray'
}

function lightsOf(monthKeys) {
  const acc = { green: 0, yellow: 0, red: 0, total: 0, unfilled: 0 }
  for (const key of monthKeys) {
    for (const m of (monthAnalytics.value[key]?.metrics || [])) {
      if (!m.filled) acc.unfilled += 1
      if (acc[m.light] === undefined) continue
      acc[m.light] += 1
      acc.total += 1
    }
  }
  return acc
}

const currentLights = computed(() => lightsOf(currentMonths.value.map(m => m.key)))

const periodLights = computed(() => periods.value.map(p => ({
  label: p.label,
  ...lightsOf(months.value.filter(m => monthPeriodLabel(m.key) === p.label).map(m => m.key)),
})))

// ---------- Charts ----------

const lightPeriodOpt = computed(() => ({
  tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
  legend: { data: LIGHTS.map(l => l.label), bottom: 0, textStyle: { fontSize: 10 } },
  grid: { left: 35, right: 12, top: 12, bottom: 40 },
  xAxis: { type: 'category', data: periodLights.value.map(p => p.label), axisLabel: { fontSize: 10 } },
  yAxis: { type: 'value', minInterval: 1, axisLabel: { fontSize: 10 } },
  series: LIGHTS.map(l => ({
    name: l.label, type: 'bar', stack: 'lights',
    data: periodLights.value.map(p => p[l.key]),
    itemStyle: { color: LIGHT_COLORS.value[l.key] },
  })),
}))

const lightMonthOpt = computed(() => {
  const list = currentMonths.value
  return {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { data: LIGHTS.map(l => l.label), bottom: 0, textStyle: { fontSize: 10 } },
    grid: { left: 35, right: 12, top: 12, bottom: 40 },
    xAxis: { type: 'category', data: list.map(m => m.label), axisLabel: { fontSize: 10 } },
    yAxis: { type: 'value', minInterval: 1, axisLabel: { fontSize: 10 } },
    series: LIGHTS.map(l => ({
      name: l.label, type: 'bar', stack: 'lights',
      data: list.map(m => lightsOf([m.key])[l.key]),
      itemStyle: { color: LIGHT_COLORS.value[l.key] },
    })),
  }
})

// Decorative multi-series chart: each line takes the next colour from the
// active chart palette, so it repaints together with the rest of the UI.
const dynamicsOpt = computed(() => {
  const labels = months.value.map(m => m.label)
  const c = palette.chartColors
  const series = KEY_METRICS.map((k, i) => {
    const d = defMap.value.get(k.key)
    return {
      name: d?.label || k.key,
      type: 'line', smooth: true, symbolSize: 6, connectNulls: true,
      yAxisIndex: d?.unit === 'дн.' ? 1 : 0,
      data: months.value.map(m => monthValue(m.key, k.key)),
      itemStyle: { color: c[i % c.length] },
    }
  })
  return {
    tooltip: { trigger: 'axis' },
    legend: { bottom: 0, textStyle: { fontSize: 9 } },
    grid: { left: 40, right: 40, top: 14, bottom: 48 },
    xAxis: { type: 'category', data: labels, axisLabel: { fontSize: 10 } },
    yAxis: [
      { type: 'value', name: '%', nameTextStyle: { fontSize: 9 }, axisLabel: { fontSize: 10 } },
      { type: 'value', name: 'дн.', nameTextStyle: { fontSize: 9 }, axisLabel: { fontSize: 10 } },
    ],
    series,
  }
})

const aggregatedMetrics = computed(() => {
  const seen = new Map()
  for (const p of periods.value) {
    for (const m of p.metrics) {
      if (!seen.has(m.key)) seen.set(m.key, { metric_key: m.key, label: m.label, unit: m.unit })
    }
  }
  return [...seen.values()]
})

function fmtMetric(period, metricKey, unit) {
  const m = period.metrics.find(x => x.key === metricKey)
  return m ? fmt(m.value, unit) : '—'
}

// Hired/fired columns are semantic (good/bad) like the traffic-light chart, so
// they use the palette's traffic-light green/red. The net-change line is
// decorative and takes the first chart-palette colour instead.
const periodChartOpt = computed(() => {
  const labels = summary.value.map(p => p.label)
  const tl = palette.trafficLight
  const netColor = palette.chartColors[0]
  return {
    tooltip: { trigger: 'axis' },
    legend: { data: ['Принято','Уволено','Чистый прирост'], bottom: 0, textStyle: { fontSize: 11 } },
    grid: { left: 35, right: 12, top: 12, bottom: 36 },
    xAxis: { type: 'category', data: labels, axisLabel: { fontSize: 10 } },
    yAxis: { type: 'value', minInterval: 1, axisLabel: { fontSize: 10 } },
    series: [
      { name: 'Принято', type: 'bar', data: summary.value.map(p => p.hired), itemStyle: { color: tl.green } },
      { name: 'Уволено', type: 'bar', data: summary.value.map(p => p.fired), itemStyle: { color: tl.red } },
      { name: 'Чистый прирост', type: 'line', smooth: true, symbolSize: 6,
        data: summary.value.map(p => p.net), itemStyle: { color: netColor } },
    ],
  }
})

async function loadSummary() {
  const qs = new URLSearchParams({ period_type: periodType.value })
  if (fromPeriod.value) qs.set('from_period', fromPeriod.value)
  if (toPeriod.value) qs.set('to_period', toPeriod.value)
  try {
    summary.value = await api.get(`/hr/analytics/summary?${qs}`)
    if (!summary.value.some(p => p.label === selectedLabel.value)) {
      selectedLabel.value = summary.value.at(-1)?.label || ''
    }
  } catch { /* the API layer already surfaced the reason as a toast */ }
}

async function loadMonths() {
  months.value = await api.get('/hr/months')
  for (const m of months.value) {
    try {
      monthAnalytics.value[m.key] = await api.get(`/hr/analytics/month/${m.key}`)
    } catch { /* a single failing month must not blank the whole page */ }
  }
}

// Labels are period-type specific, so stale bounds would be rejected by the API.
watch(periodType, () => {
  fromPeriod.value = ''
  toPeriod.value = ''
  loadSummary()
})

onMounted(async () => {
  loading.value = true
  try {
    const [defs] = await Promise.all([api.get('/hr/metric-definitions'), loadSummary(), loadMonths()])
    metricDefs.value = defs
  } finally { loading.value = false }
})
</script>
