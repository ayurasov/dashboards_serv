<template>
  <div class="tp-dashboard">
    <div class="page-header">
      <h1>Техническая поддержка</h1>
      <div class="period-selector">
        <select v-model="selectedYear" @change="onPeriodChange">
          <option v-for="y in years" :key="y" :value="y">{{ y }}</option>
        </select>
        <select v-model="selectedWeek">
          <option value="">Все недели</option>
          <option v-for="w in weeks" :key="w" :value="w">Неделя {{ w }}</option>
        </select>
      </div>
    </div>

    <div v-if="loading" class="loading-state">Загрузка данных…</div>

    <template v-else-if="currentRow">
      <!-- KPI grid -->
      <div class="kpi-grid">
        <div class="kpi-card" :class="trafficClass('total_in_work', currentRow.total_in_work)">
          <div class="kpi-label">В работе</div>
          <div class="kpi-value">{{ fmt(currentRow.total_in_work) }}</div>
          <div class="kpi-sub">обращений</div>
        </div>
        <div class="kpi-card" :class="trafficClass('avail_total', currentRow.avail_total)">
          <div class="kpi-label">Доступность (всего)</div>
          <div class="kpi-value">{{ fmt(currentRow.avail_total) }}</div>
          <div class="kpi-sub">часов</div>
        </div>
        <div class="kpi-card" :class="trafficClass('total_solved_week', currentRow.total_solved_week)">
          <div class="kpi-label">Решено за неделю</div>
          <div class="kpi-value">{{ fmt(currentRow.total_solved_week) }}</div>
          <div class="kpi-sub">обращений</div>
        </div>
        <div class="kpi-card" :class="trafficClass('ratio_solved_received', currentRow.ratio_solved_received)">
          <div class="kpi-label">Коэф. решения</div>
          <div class="kpi-value">{{ fmtDec(currentRow.ratio_solved_received, 2) }}</div>
          <div class="kpi-sub">решено / получено</div>
        </div>
        <div class="kpi-card" :class="trafficClass('altos_avg_time', currentRow.altos_avg_time)">
          <div class="kpi-label">AltOS — ср. время</div>
          <div class="kpi-value">{{ fmt(currentRow.altos_avg_time) }}</div>
          <div class="kpi-sub">часов</div>
        </div>
        <div class="kpi-card" :class="trafficClass('altoffice_avg_time', currentRow.altoffice_avg_time)">
          <div class="kpi-label">AltOffice — ср. время</div>
          <div class="kpi-value">{{ fmt(currentRow.altoffice_avg_time) }}</div>
          <div class="kpi-sub">часов</div>
        </div>
        <div class="kpi-card" :class="trafficClass('new_received', currentRow.new_received)">
          <div class="kpi-label">Новых получено</div>
          <div class="kpi-value">{{ fmt(currentRow.new_received) }}</div>
          <div class="kpi-sub">обращений</div>
        </div>
        <div class="kpi-card" :class="trafficClass('renewed', currentRow.renewed)">
          <div class="kpi-label">Возобновлено</div>
          <div class="kpi-value">{{ fmt(currentRow.renewed) }}</div>
          <div class="kpi-sub">обращений</div>
        </div>
      </div>

      <!-- Client hours -->
      <div class="section-card">
        <h2>Часы по клиентам</h2>
        <div class="client-grid">
          <div class="client-item" v-for="c in clientCols" :key="c.key">
            <span class="client-name">{{ c.label }}</span>
            <span class="client-value">{{ fmt(currentRow[c.key]) }} ч.</span>
          </div>
        </div>
      </div>

      <!-- Product breakdown -->
      <div class="product-grid">
        <div class="section-card">
          <h2>AltOS</h2>
          <table class="mini-table">
            <tr><td>Всего</td><td>{{ fmt(currentRow.altos_total) }}</td></tr>
            <tr><td>1–2 линия</td><td>{{ fmt(currentRow.altos_1_2line) }}</td></tr>
            <tr><td>3 линия</td><td>{{ fmt(currentRow.altos_3line) }}</td></tr>
            <tr><td>Доступность</td><td>{{ fmt(currentRow.altos_avail_total) }}</td></tr>
            <tr><td>1–3 дн.</td><td>{{ fmt(currentRow.altos_avail_1_3) }}</td></tr>
            <tr><td>4–7 дн.</td><td>{{ fmt(currentRow.altos_avail_4_7) }}</td></tr>
            <tr><td>8–10 дн.</td><td>{{ fmt(currentRow.altos_avail_8_10) }}</td></tr>
          </table>
        </div>
        <div class="section-card">
          <h2>AltOffice</h2>
          <table class="mini-table">
            <tr><td>Всего</td><td>{{ fmt(currentRow.altoffice_total) }}</td></tr>
            <tr><td>1–2 линия</td><td>{{ fmt(currentRow.altoffice_1_2line) }}</td></tr>
            <tr><td>3 линия</td><td>{{ fmt(currentRow.altoffice_3line) }}</td></tr>
            <tr><td>Доступность</td><td>{{ fmt(currentRow.altoffice_avail_total) }}</td></tr>
            <tr><td>1–3 дн.</td><td>{{ fmt(currentRow.altoffice_avail_1_3) }}</td></tr>
            <tr><td>4–7 дн.</td><td>{{ fmt(currentRow.altoffice_avail_4_7) }}</td></tr>
            <tr><td>8–10 дн.</td><td>{{ fmt(currentRow.altoffice_avail_8_10) }}</td></tr>
          </table>
        </div>
        <div class="section-card">
          <h2>Проектный сервер</h2>
          <table class="mini-table">
            <tr><td>Принято</td><td>{{ fmt(currentRow.projserver_taken) }}</td></tr>
            <tr><td>Решено</td><td>{{ fmt(currentRow.projserver_solved) }}</td></tr>
            <tr><td>Доступность</td><td>{{ fmt(currentRow.projserver_avail) }}</td></tr>
          </table>
        </div>
      </div>
    </template>

    <div v-else class="empty-state">
      <div class="empty-state-icon">📭</div>
      <h3>Нет данных</h3>
      <p>Добавьте данные в разделе «Реестр»</p>
      <router-link to="/tp/registry" class="btn btn-p">Перейти в реестр</router-link>
    </div>

    <!-- Trend chart -->
    <div class="section-card" v-if="rows.length > 1">
      <h2>Динамика за последние {{ chartData.length }} недель</h2>
      <canvas ref="chartCanvas" height="70"></canvas>
    </div>

    <!-- Navigation tiles -->
    <div class="nav-cards">
      <router-link to="/tp/registry" class="nav-card">
        <span class="nav-icon">📋</span>
        <span>Реестр данных</span>
      </router-link>
      <router-link to="/tp/summary" class="nav-card">
        <span class="nav-icon">📊</span>
        <span>Сводная аналитика</span>
      </router-link>
      <router-link to="/tp/traffic-light" class="nav-card" v-if="auth.isAdmin">
        <span class="nav-icon">🚦</span>
        <span>Настройка светофора</span>
      </router-link>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { tpApi } from '../../api/tp.js'
import { useAuthStore } from '../../stores/auth.js'
import Chart from 'chart.js/auto'

const auth = useAuthStore()
const rows = ref([])
const trafficRules = ref({})
const loading = ref(false)
const selectedYear = ref(null)
const selectedWeek = ref('')
const chartCanvas = ref(null)
let chartInstance = null

const years = computed(() => [...new Set(rows.value.map(r => r.year))].sort((a, b) => a - b))
const weeks = computed(() => {
  if (!selectedYear.value) return []
  return [...new Set(
    rows.value.filter(r => r.year === selectedYear.value).map(r => r.week)
  )].sort((a, b) => a - b)
})

const sortedRows = computed(() =>
  [...rows.value].sort((a, b) => a.year - b.year || a.week - b.week)
)

const filteredRows = computed(() => {
  let r = sortedRows.value
  if (selectedYear.value) r = r.filter(x => x.year === selectedYear.value)
  if (selectedWeek.value !== '') r = r.filter(x => x.week === Number(selectedWeek.value))
  return r
})

const currentRow = computed(() => filteredRows.value[filteredRows.value.length - 1] ?? null)
const chartData = computed(() => sortedRows.value.slice(-20))

const clientCols = [
  { key: 'rushydro_hours', label: 'РусГидро' },
  { key: 'transneft_hours', label: 'Транснефть' },
  { key: 'roscosmos_hours', label: 'Роскосмос' },
  { key: 'bryansk_hours', label: 'Брянск' },
  { key: 'mchs_hours', label: 'МЧС' },
  { key: 'internal_sales_hours', label: 'Внутренние продажи' },
]

function fmt(v) { return v != null ? Number(v).toLocaleString('ru-RU') : '—' }
function fmtDec(v, d = 1) { return v != null ? Number(v).toFixed(d) : '—' }

function trafficClass(key, value) {
  const rule = trafficRules.value[key]
  if (!rule || !rule.enabled || value == null) return 'light-gray'
  const v = Number(value)
  if (rule.direction === 'less') {
    if (v <= rule.green) return 'light-green'
    if (v <= rule.yellow) return 'light-yellow'
    return 'light-red'
  } else {
    if (v >= rule.green) return 'light-green'
    if (v >= rule.yellow) return 'light-yellow'
    return 'light-red'
  }
}

function onPeriodChange() {
  selectedWeek.value = ''
}

async function loadAll() {
  loading.value = true
  try {
    const [r, tr] = await Promise.all([tpApi.getRows(), tpApi.getSetting('traffic_rules')])
    rows.value = r
    trafficRules.value = tr
    if (!selectedYear.value && years.value.length) {
      selectedYear.value = years.value[years.value.length - 1]
    }
  } catch (e) {
    console.error('TP load error', e)
  } finally {
    loading.value = false
    await nextTick()
    renderChart()
  }
}

function renderChart() {
  if (!chartCanvas.value || !chartData.value.length) return
  const labels = chartData.value.map(r => `${r.year}W${String(r.week).padStart(2, '0')}`)
  if (chartInstance) chartInstance.destroy()
  chartInstance = new Chart(chartCanvas.value, {
    type: 'line',
    data: {
      labels,
      datasets: [
        { label: 'В работе', data: chartData.value.map(r => r.total_in_work), borderColor: '#e67e22', backgroundColor: 'rgba(230,126,34,0.08)', tension: 0.3, fill: true },
        { label: 'Решено', data: chartData.value.map(r => r.total_solved_week), borderColor: '#27ae60', backgroundColor: 'rgba(39,174,96,0.08)', tension: 0.3, fill: true },
        { label: 'Новых', data: chartData.value.map(r => r.new_received), borderColor: '#2980b9', tension: 0.3, fill: false, borderDash: [4, 4] },
      ],
    },
    options: {
      responsive: true,
      plugins: { legend: { position: 'top' } },
      scales: { y: { beginAtZero: true } },
    },
  })
}

watch(chartData, () => nextTick(renderChart))
onMounted(loadAll)
</script>

<style scoped>
.tp-dashboard { padding: var(--space-6); display: flex; flex-direction: column; gap: var(--space-5); }
.page-header { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: var(--space-3); }
.page-header h1 { font-size: var(--text-xl); font-weight: 700; }
.period-selector { display: flex; gap: var(--space-2); }
.period-selector select { padding: var(--space-2) var(--space-3); border: 1px solid var(--color-border); border-radius: var(--radius-md); background: var(--color-surface); color: var(--color-text); font-size: var(--text-sm); }

.kpi-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); gap: var(--space-3); }
.kpi-card { background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-lg); padding: var(--space-4); text-align: center; position: relative; overflow: hidden; }
.kpi-card::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px; }
.kpi-card.light-green::before { background: #27ae60; }
.kpi-card.light-yellow::before { background: #f1c40f; }
.kpi-card.light-red::before { background: #e74c3c; }
.kpi-card.light-gray::before { background: var(--color-border); }
.kpi-label { font-size: var(--text-xs); color: var(--color-text-muted); margin-bottom: var(--space-2); text-transform: uppercase; letter-spacing: .03em; }
.kpi-value { font-size: var(--text-xl); font-weight: 700; font-variant-numeric: tabular-nums; }
.kpi-sub { font-size: var(--text-xs); color: var(--color-text-muted); margin-top: var(--space-1); }

.section-card { background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-lg); padding: var(--space-5); }
.section-card h2 { font-size: var(--text-lg); font-weight: 600; margin-bottom: var(--space-4); }

.client-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: var(--space-2); }
.client-item { display: flex; justify-content: space-between; align-items: center; padding: var(--space-2) var(--space-3); background: var(--color-surface-offset); border-radius: var(--radius-md); font-size: var(--text-sm); }
.client-name { color: var(--color-text-muted); }
.client-value { font-weight: 600; font-variant-numeric: tabular-nums; }

.product-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: var(--space-3); }
.mini-table { width: 100%; font-size: var(--text-sm); }
.mini-table tr:not(:last-child) td { padding-bottom: var(--space-2); }
.mini-table td:first-child { color: var(--color-text-muted); }
.mini-table td:last-child { text-align: right; font-variant-numeric: tabular-nums; font-weight: 600; }

.nav-cards { display: flex; gap: var(--space-3); flex-wrap: wrap; }
.nav-card { display: flex; align-items: center; gap: var(--space-2); padding: var(--space-4) var(--space-5); background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-lg); text-decoration: none; color: var(--color-text); font-weight: 500; font-size: var(--text-sm); transition: all var(--transition-interactive); }
.nav-card:hover { background: var(--color-primary); color: #fff; border-color: var(--color-primary); }
.nav-icon { font-size: 1.2rem; }

.loading-state { padding: var(--space-8); text-align: center; color: var(--color-text-muted); }
.empty-state { display: flex; flex-direction: column; align-items: center; text-align: center; padding: var(--space-16) var(--space-8); color: var(--color-text-muted); gap: var(--space-3); }
.empty-state-icon { font-size: 2.5rem; }
.empty-state h3 { color: var(--color-text); font-size: var(--text-lg); }
.empty-state p { max-width: 36ch; }
</style>
