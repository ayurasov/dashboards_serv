<template>
  <div class="tp-dashboard page-content">
    <!-- Header -->
    <div class="page-header">
      <h1 class="page-title">🎧 Техническая поддержка</h1>
      <div class="header-controls">
        <select v-model="selectedYear" class="filter-select" @change="load">
          <option :value="null">Все годы</option>
          <option v-for="y in years" :key="y" :value="y">{{ y }}</option>
        </select>
        <router-link to="/tp/registry" class="btn btn-secondary btn-sm">Реестр</router-link>
        <router-link to="/tp/traffic-light" class="btn btn-secondary btn-sm">Светофор</router-link>
      </div>
    </div>

    <div v-if="loading" class="loading-state">Загрузка данных…</div>
    <div v-else-if="error" class="error-banner">{{ error }}</div>

    <template v-else-if="rows.length">
      <!-- KPI row -->
      <div class="kpi-grid">
        <div class="kpi-card" v-for="kpi in kpis" :key="kpi.key">
          <span class="kpi-label">{{ kpi.label }}</span>
          <span class="kpi-value" :class="kpi.light">
            {{ kpi.value !== null ? fmt(kpi.value, kpi.unit) : '—' }}
          </span>
          <span class="kpi-sub">{{ kpi.sub }}</span>
        </div>
      </div>

      <!-- Charts row -->
      <div class="charts-row">
        <div class="chart-card">
          <h3 class="chart-title">Новые обращения / Решено за неделю</h3>
          <canvas ref="ticketsChart" height="220"></canvas>
        </div>
        <div class="chart-card">
          <h3 class="chart-title">Среднее время обработки (ч)</h3>
          <canvas ref="avgTimeChart" height="220"></canvas>
        </div>
      </div>

      <!-- Availability bar -->
      <div class="chart-card chart-wide">
        <h3 class="chart-title">Доступность (нарастающим итогом)</h3>
        <canvas ref="availChart" height="180"></canvas>
      </div>

      <!-- Client hours -->
      <div class="chart-card chart-wide">
        <h3 class="chart-title">Часы по клиентам</h3>
        <canvas ref="clientChart" height="180"></canvas>
      </div>
    </template>

    <div v-else class="empty-state">
      <div class="empty-icon">📭</div>
      <p>Нет данных за выбранный период</p>
      <router-link to="/tp/registry" class="btn btn-primary">Добавить записи</router-link>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { tpApi } from '../api/tp.js'
import Chart from 'chart.js/auto'

const rows = ref([])
const loading = ref(false)
const error = ref(null)
const selectedYear = ref(null)
const rules = ref({})

const ticketsChart = ref(null)
const avgTimeChart = ref(null)
const availChart   = ref(null)
const clientChart  = ref(null)

let chartInstances = {}

const years = computed(() => {
  const s = new Set(rows.value.map(r => r.year).filter(Boolean))
  return [...s].sort((a, b) => b - a)
})

const filtered = computed(() =>
  selectedYear.value ? rows.value.filter(r => r.year === selectedYear.value) : rows.value
)

const last = computed(() => filtered.value.at(-1) || {})

function calcLight(key, val) {
  const rule = rules.value[key]
  if (!rule || !rule.enabled || val === null || val === undefined) return ''
  const { direction, green, yellow } = rule
  if (direction === 'less') {
    if (val <= green)  return 'green'
    if (val <= yellow) return 'yellow'
    return 'red'
  } else {
    if (val >= green)  return 'green'
    if (val >= yellow) return 'yellow'
    return 'red'
  }
}

const kpis = computed(() => [
  { key: 'total_in_work',       label: 'В работе',           unit: 'шт',  sub: 'обращений', value: last.value.total_in_work,       light: calcLight('total_in_work', last.value.total_in_work) },
  { key: 'new_received',        label: 'Новых за неделю',    unit: 'шт',  sub: 'обращений', value: last.value.new_received,        light: calcLight('new_received', last.value.new_received) },
  { key: 'total_solved_week',   label: 'Решено за неделю',   unit: 'шт',  sub: '',          value: last.value.total_solved_week,   light: calcLight('total_solved_week', last.value.total_solved_week) },
  { key: 'ratio_solved_received', label: 'Коэф. закрытия',  unit: '',    sub: 'реш/получ', value: last.value.ratio_solved_received, light: calcLight('ratio_solved_received', last.value.ratio_solved_received) },
  { key: 'altos_avg_time',      label: 'Ср. время AltOS',   unit: 'ч',   sub: '',          value: last.value.altos_avg_time,      light: calcLight('altos_avg_time', last.value.altos_avg_time) },
  { key: 'altoffice_avg_time',  label: 'Ср. время AltOff',  unit: 'ч',   sub: '',          value: last.value.altoffice_avg_time,  light: calcLight('altoffice_avg_time', last.value.altoffice_avg_time) },
])

function fmt(val, unit) {
  if (val === null || val === undefined) return '—'
  const n = Number(val)
  const s = Number.isInteger(n) ? n.toLocaleString('ru') : n.toFixed(2).replace('.', ',')
  return unit ? `${s} ${unit}` : s
}

async function load() {
  loading.value = true
  error.value = null
  try {
    [rows.value, rules.value] = await Promise.all([
      tpApi.getRows(),
      tpApi.getTrafficRules(),
    ])
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
    await nextTick()
    drawCharts()
  }
}

function destroyAll() {
  Object.values(chartInstances).forEach(c => c?.destroy())
  chartInstances = {}
}

function drawCharts() {
  destroyAll()
  const data = filtered.value
  if (!data.length) return

  const labels = data.map(r => `${r.year ?? ''}w${r.week ?? ''}`)

  // 1. Tickets
  if (ticketsChart.value) {
    chartInstances.tickets = new Chart(ticketsChart.value, {
      type: 'line',
      data: {
        labels,
        datasets: [
          { label: 'Новых',   data: data.map(r => r.new_received),      borderColor: '#3b82f6', backgroundColor: 'rgba(59,130,246,.08)', tension: .3, fill: true },
          { label: 'Решено',  data: data.map(r => r.total_solved_week), borderColor: '#22c55e', backgroundColor: 'rgba(34,197,94,.08)',  tension: .3, fill: true },
        ],
      },
      options: { plugins: { legend: { position: 'bottom' } }, scales: { y: { beginAtZero: true } } },
    })
  }

  // 2. Avg time
  if (avgTimeChart.value) {
    chartInstances.avgTime = new Chart(avgTimeChart.value, {
      type: 'line',
      data: {
        labels,
        datasets: [
          { label: 'AltOS',    data: data.map(r => r.altos_avg_time),    borderColor: '#8b5cf6', tension: .3 },
          { label: 'AltOffice',data: data.map(r => r.altoffice_avg_time),borderColor: '#f59e0b', tension: .3 },
        ],
      },
      options: { plugins: { legend: { position: 'bottom' } }, scales: { y: { beginAtZero: true } } },
    })
  }

  // 3. Availability
  if (availChart.value) {
    chartInstances.avail = new Chart(availChart.value, {
      type: 'bar',
      data: {
        labels,
        datasets: [
          { label: 'AltOS',    data: data.map(r => r.altos_avail_total),    backgroundColor: 'rgba(59,130,246,.7)' },
          { label: 'AltOffice',data: data.map(r => r.altoffice_avail_total),backgroundColor: 'rgba(139,92,246,.7)' },
          { label: 'ProjServer',data: data.map(r => r.projserver_avail),    backgroundColor: 'rgba(34,197,94,.7)' },
        ],
      },
      options: { plugins: { legend: { position: 'bottom' } }, scales: { y: { beginAtZero: true } } },
    })
  }

  // 4. Client hours
  if (clientChart.value) {
    const lastRow = data.at(-1) || {}
    chartInstances.client = new Chart(clientChart.value, {
      type: 'bar',
      data: {
        labels: ['РусГидро','Транснефть','Роскосмос','Брянск','МЧС','Внутренние'],
        datasets: [{
          label: 'Часы (посл. неделя)',
          data: [
            lastRow.rushydro_hours, lastRow.transneft_hours, lastRow.roscosmos_hours,
            lastRow.bryansk_hours,  lastRow.mchs_hours,      lastRow.internal_sales_hours,
          ],
          backgroundColor: ['#3b82f6','#8b5cf6','#f59e0b','#22c55e','#ef4444','#6b7280'],
        }],
      },
      options: { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } },
    })
  }
}

onMounted(load)
watch(filtered, () => nextTick(drawCharts))
</script>

<style scoped>
.tp-dashboard { padding: var(--space-6); }
.page-header   { display: flex; align-items: center; justify-content: space-between; margin-bottom: var(--space-6); flex-wrap: wrap; gap: var(--space-3); }
.page-title    { font-size: var(--text-xl); font-weight: 700; }
.header-controls { display: flex; gap: var(--space-2); align-items: center; }
.filter-select { padding: var(--space-2) var(--space-3); border: 1px solid var(--color-border); border-radius: var(--radius-md); background: var(--color-surface); color: var(--color-text); font-size: var(--text-sm); }

.kpi-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: var(--space-4); margin-bottom: var(--space-6); }
.kpi-card  { background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-lg); padding: var(--space-4); display: flex; flex-direction: column; gap: var(--space-1); }
.kpi-label { font-size: var(--text-xs); color: var(--color-text-muted); text-transform: uppercase; letter-spacing: .05em; }
.kpi-value { font-size: var(--text-xl); font-weight: 700; font-variant-numeric: tabular-nums; }
.kpi-value.green  { color: var(--color-success); }
.kpi-value.yellow { color: var(--color-gold); }
.kpi-value.red    { color: var(--color-notification); }
.kpi-sub   { font-size: var(--text-xs); color: var(--color-text-faint); }

.charts-row  { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-4); margin-bottom: var(--space-4); }
.chart-card  { background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-lg); padding: var(--space-4); }
.chart-wide  { margin-bottom: var(--space-4); }
.chart-title { font-size: var(--text-sm); font-weight: 600; color: var(--color-text-muted); margin-bottom: var(--space-3); }

.loading-state { text-align: center; padding: var(--space-16); color: var(--color-text-muted); }
.error-banner  { background: var(--color-error-highlight); color: var(--color-error); padding: var(--space-4); border-radius: var(--radius-md); margin-bottom: var(--space-4); }
.empty-state   { display: flex; flex-direction: column; align-items: center; gap: var(--space-4); padding: var(--space-16); color: var(--color-text-muted); }
.empty-icon    { font-size: 3rem; }

@media (max-width: 768px) {
  .charts-row { grid-template-columns: 1fr; }
}
</style>
