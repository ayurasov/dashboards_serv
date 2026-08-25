<template>
  <div class="tp-dashboard">
    <!-- Header -->
    <div class="page-header">
      <div class="page-header__left">
        <h1 class="page-title">Техническая поддержка</h1>
        <p class="page-subtitle">Еженедельный дашборд</p>
      </div>
      <div class="page-header__right">
        <label class="field-label">Период:</label>
        <select v-model="selectedPeriod" class="select-sm" @change="applyFilter">
          <option value="">Все периоды</option>
          <option v-for="p in periods" :key="p" :value="p">{{ p }}</option>
        </select>
        <label class="field-label ml-3">Последние:</label>
        <select v-model="lastN" class="select-sm" @change="applyFilter">
          <option :value="0">Все</option>
          <option :value="4">4 нед.</option>
          <option :value="8">8 нед.</option>
          <option :value="13">13 нед.</option>
          <option :value="26">26 нед.</option>
        </select>
      </div>
    </div>

    <div v-if="loading" class="loading-state">Загрузка данных...</div>
    <div v-else-if="error" class="error-state">{{ error }}</div>

    <template v-else>
      <!-- KPI cards -->
      <div class="kpi-grid">
        <div v-for="kpi in kpis" :key="kpi.key" class="kpi-card" :class="`kpi-card--${kpi.light}`">
          <div class="kpi-card__label">{{ kpi.label }}</div>
          <div class="kpi-card__value">{{ fmt(kpi.value, kpi.decimals) }}</div>
          <div class="kpi-card__sub">{{ kpi.sub }}</div>
          <div class="kpi-card__light" :class="`light--${kpi.light}`"></div>
        </div>
      </div>

      <!-- Charts row 1: load & tickets -->
      <div class="charts-row">
        <div class="chart-card">
          <h3 class="chart-title">Нагрузка (в работе / доступность)</h3>
          <canvas ref="loadChart"></canvas>
        </div>
        <div class="chart-card">
          <h3 class="chart-title">Поступившие / решённые заявки</h3>
          <canvas ref="ticketChart"></canvas>
        </div>
      </div>

      <!-- Charts row 2: SLA times -->
      <div class="charts-row">
        <div class="chart-card">
          <h3 class="chart-title">Среднее время решения (ч.)</h3>
          <canvas ref="slaChart"></canvas>
        </div>
        <div class="chart-card">
          <h3 class="chart-title">Клиентские часы по заказчикам</h3>
          <canvas ref="clientChart"></canvas>
        </div>
      </div>

      <!-- Latest week notes -->
      <div v-if="lastRow && lastRow.extra" class="notes-card">
        <h3 class="chart-title">Комментарий к последней неделе</h3>
        <p class="notes-text">{{ lastRow.extra }}</p>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { useAuthStore } from '../stores/auth'
import Chart from 'chart.js/auto'

const auth = useAuthStore()
const apiBase = import.meta.env.VITE_API_URL || ''

const rows = ref([])
const trafficRules = ref({})
const loading = ref(true)
const error = ref(null)
const selectedPeriod = ref('')
const lastN = ref(13)

// Chart refs
const loadChart = ref(null)
const ticketChart = ref(null)
const slaChart = ref(null)
const clientChart = ref(null)
let charts = []

// ---- fetch ----
async function fetchData() {
  loading.value = true
  error.value = null
  try {
    const headers = { Authorization: `Bearer ${auth.token}` }
    const [rowsRes, rulesRes] = await Promise.all([
      fetch(`${apiBase}/api/tp/rows`, { headers }),
      fetch(`${apiBase}/api/tp/settings/traffic_rules`, { headers }),
    ])
    if (!rowsRes.ok) throw new Error(`rows: ${rowsRes.status}`)
    rows.value = await rowsRes.json()
    trafficRules.value = rulesRes.ok ? await rulesRes.json() : {}
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

// ---- filter ----
const filtered = computed(() => {
  let data = rows.value.slice()
  if (selectedPeriod.value) data = data.filter(r => r.period === selectedPeriod.value)
  if (lastN.value > 0) data = data.slice(-lastN.value)
  return data
})

const periods = computed(() => [...new Set(rows.value.map(r => r.period).filter(Boolean))])
const lastRow = computed(() => filtered.value[filtered.value.length - 1] || null)

// ---- traffic light ----
function getLight(key, value) {
  const rule = trafficRules.value[key]
  if (!rule || !rule.enabled || value == null) return 'gray'
  const { direction, green, yellow } = rule
  if (direction === 'less') {
    if (value <= green) return 'green'
    if (value <= yellow) return 'yellow'
    return 'red'
  } else {
    if (value >= green) return 'green'
    if (value >= yellow) return 'yellow'
    return 'red'
  }
}

function avg(key) {
  const vals = filtered.value.map(r => r[key]).filter(v => v != null)
  return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null
}
function last(key) {
  return lastRow.value ? lastRow.value[key] : null
}
function fmt(v, dec = 0) {
  if (v == null) return '—'
  return Number(v).toLocaleString('ru-RU', { maximumFractionDigits: dec })
}

const kpis = computed(() => [
  { key: 'total_in_work', label: 'В работе', value: last('total_in_work'), light: getLight('total_in_work', last('total_in_work')), sub: 'посл. неделя', decimals: 0 },
  { key: 'avail_total', label: 'Доступность (всего)', value: last('avail_total'), light: getLight('avail_total', last('avail_total')), sub: 'посл. неделя', decimals: 0 },
  { key: 'new_received', label: 'Новых заявок', value: last('new_received'), light: getLight('new_received', last('new_received')), sub: 'за неделю', decimals: 0 },
  { key: 'total_solved_week', label: 'Решено за неделю', value: last('total_solved_week'), light: getLight('total_solved_week', last('total_solved_week')), sub: 'посл. неделя', decimals: 0 },
  { key: 'ratio_solved_received', label: 'Коэф. решения', value: last('ratio_solved_received'), light: getLight('ratio_solved_received', last('ratio_solved_received')), sub: 'решено/поступило', decimals: 2 },
  { key: 'altos_avg_time', label: 'SLA AltOS (ч.)', value: avg('altos_avg_time'), light: getLight('altos_avg_time', avg('altos_avg_time')), sub: `среднее за ${filtered.value.length} нед.`, decimals: 1 },
  { key: 'altoffice_avg_time', label: 'SLA AltOffice (ч.)', value: avg('altoffice_avg_time'), light: getLight('altoffice_avg_time', avg('altoffice_avg_time')), sub: `среднее за ${filtered.value.length} нед.`, decimals: 1 },
])

// ---- charts ----
const palette = [
  'rgba(1,105,111,0.85)', 'rgba(218,113,1,0.85)', 'rgba(161,44,123,0.85)',
  'rgba(67,122,34,0.85)', 'rgba(0,100,148,0.85)', 'rgba(122,57,187,0.85)',
]

function makeLabels() {
  return filtered.value.map(r => r.period || `${r.year}-W${String(r.week).padStart(2,'0')}`)
}

function destroyCharts() {
  charts.forEach(c => c.destroy())
  charts = []
}

function buildCharts() {
  destroyCharts()
  const labels = makeLabels()

  const mk = (ref, config) => {
    if (!ref.value) return
    const c = new Chart(ref.value, config)
    charts.push(c)
  }

  const lineOpts = (datasets) => ({
    type: 'line',
    data: { labels, datasets },
    options: { responsive: true, plugins: { legend: { position: 'bottom' } } },
  })

  mk(loadChart, lineOpts([
    { label: 'В работе', data: filtered.value.map(r => r.total_in_work), borderColor: palette[0], backgroundColor: palette[0].replace('0.85', '0.1'), tension: 0.3, fill: true },
    { label: 'Доступность', data: filtered.value.map(r => r.avail_total), borderColor: palette[1], backgroundColor: palette[1].replace('0.85', '0.1'), tension: 0.3, fill: true },
  ]))

  mk(ticketChart, lineOpts([
    { label: 'Новых', data: filtered.value.map(r => r.new_received), borderColor: palette[2], tension: 0.3 },
    { label: 'Решено', data: filtered.value.map(r => r.total_solved_week), borderColor: palette[3], tension: 0.3 },
  ]))

  mk(slaChart, lineOpts([
    { label: 'AltOS ср.вр. (ч.)', data: filtered.value.map(r => r.altos_avg_time), borderColor: palette[0], tension: 0.3 },
    { label: 'AltOffice ср.вр. (ч.)', data: filtered.value.map(r => r.altoffice_avg_time), borderColor: palette[4], tension: 0.3 },
  ]))

  // Client hours bar
  const clientKeys = ['rushydro_hours','transneft_hours','roscosmos_hours','bryansk_hours','mchs_hours','internal_sales_hours']
  const clientLabels = ['РусГидро','Транснефть','РосКосмос','Брянск','МЧС','Внутр./Продажи']
  mk(clientChart, {
    type: 'bar',
    data: {
      labels,
      datasets: clientKeys.map((k, i) => ({
        label: clientLabels[i],
        data: filtered.value.map(r => r[k]),
        backgroundColor: palette[i % palette.length],
      })),
    },
    options: { responsive: true, plugins: { legend: { position: 'bottom' } }, scales: { x: { stacked: true }, y: { stacked: true } } },
  })
}

function applyFilter() {
  nextTick(buildCharts)
}

onMounted(async () => {
  await fetchData()
  await nextTick()
  buildCharts()
})

watch(filtered, () => nextTick(buildCharts))
</script>

<style scoped>
.tp-dashboard { padding: var(--space-6); }
.page-header { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: var(--space-4); margin-bottom: var(--space-6); }
.page-title { font-size: var(--text-xl); font-weight: 700; color: var(--color-text); margin: 0; }
.page-subtitle { font-size: var(--text-sm); color: var(--color-text-muted); margin: 0; }
.page-header__right { display: flex; align-items: center; gap: var(--space-2); flex-wrap: wrap; }
.field-label { font-size: var(--text-sm); color: var(--color-text-muted); }
.ml-3 { margin-left: var(--space-3); }
.select-sm { padding: var(--space-1) var(--space-2); border: 1px solid var(--color-border); border-radius: var(--radius-sm); background: var(--color-surface); color: var(--color-text); font-size: var(--text-sm); }

.loading-state, .error-state { padding: var(--space-12); text-align: center; color: var(--color-text-muted); }
.error-state { color: var(--color-error); }

/* KPI grid */
.kpi-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: var(--space-4); margin-bottom: var(--space-6); }
.kpi-card { background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-lg); padding: var(--space-4); position: relative; overflow: hidden; box-shadow: var(--shadow-sm); }
.kpi-card__label { font-size: var(--text-sm); color: var(--color-text-muted); margin-bottom: var(--space-1); }
.kpi-card__value { font-size: var(--text-xl); font-weight: 700; color: var(--color-text); font-variant-numeric: tabular-nums; }
.kpi-card__sub { font-size: var(--text-xs); color: var(--color-text-faint); margin-top: var(--space-1); }
.kpi-card__light { position: absolute; top: var(--space-3); right: var(--space-3); width: 10px; height: 10px; border-radius: 50%; }
.light--green { background: var(--color-success); }
.light--yellow { background: var(--color-gold); }
.light--red { background: var(--color-error); }
.light--gray { background: var(--color-text-faint); }
.kpi-card--green { border-left: 3px solid var(--color-success); }
.kpi-card--yellow { border-left: 3px solid var(--color-gold); }
.kpi-card--red { border-left: 3px solid var(--color-error); }

/* Charts */
.charts-row { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-4); margin-bottom: var(--space-4); }
@media (max-width: 768px) { .charts-row { grid-template-columns: 1fr; } }
.chart-card { background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-lg); padding: var(--space-4); box-shadow: var(--shadow-sm); }
.chart-title { font-size: var(--text-base); font-weight: 600; color: var(--color-text); margin: 0 0 var(--space-3) 0; }

/* Notes */
.notes-card { background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-lg); padding: var(--space-4); margin-top: var(--space-4); box-shadow: var(--shadow-sm); }
.notes-text { font-size: var(--text-base); color: var(--color-text); line-height: 1.7; max-width: none; }
</style>
