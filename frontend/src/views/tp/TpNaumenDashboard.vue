<template>
  <div class="naumen-dashboard">
    <!-- Page header with filters (same pattern as TpDashboard) -->
    <div class="page-header">
      <div class="page-header__left">
        <h1>Аналитика заявок (Naumen)</h1>
        <span class="data-badge">Данные по 06.08.2026</span>
      </div>
      <div class="filters">
        <select v-model="selectedYear" @change="onYearChange">
          <option value="">Все годы</option>
          <option v-for="y in availableYears" :key="y" :value="y">{{ y }}</option>
        </select>
        <select v-model="selectedQuarter">
          <option value="">Все кварталы</option>
          <option value="Q1">Q1</option>
          <option value="Q2">Q2</option>
          <option value="Q3">Q3</option>
          <option value="Q4">Q4</option>
        </select>
      </div>
    </div>

    <!-- KPI cards (same pattern: top accent bar, traffic-light coloring) -->
    <div class="kpi-grid">
      <div class="kpi-card" :class="overdueClass(globalKpi.overdue_pct, 10, 20)">
        <div class="kpi-label">Всего заявок</div>
        <div class="kpi-value">{{ fmt(filteredKpi.total) }}</div>
        <div class="kpi-sub">за период</div>
      </div>
      <div class="kpi-card light-gray">
        <div class="kpi-label">Открыто сейчас</div>
        <div class="kpi-value">{{ fmt(OPEN_NOW) }}</div>
        <div class="kpi-sub">в реализации / отложено</div>
      </div>
      <div class="kpi-card" :class="overdueClass(filteredKpi.overdue_pct, 10, 25)">
        <div class="kpi-label">Просрочено</div>
        <div class="kpi-value">{{ filteredKpi.overdue_pct }}%</div>
        <div class="kpi-sub">{{ fmt(filteredKpi.overdue) }} из {{ fmt(filteredKpi.total) }}</div>
      </div>
      <div class="kpi-card" :class="rateClass(filteredKpi.in_20min_pct, 60, 40)">
        <div class="kpi-label">Принято за 20 мин.</div>
        <div class="kpi-value">{{ filteredKpi.in_20min_pct }}%</div>
        <div class="kpi-sub">от назначения на РГ</div>
      </div>
      <div class="kpi-card" :class="rateClass(filteredKpi.satisfaction_pct, 90, 75)">
        <div class="kpi-label">Удовлетворённость</div>
        <div class="kpi-value">{{ filteredKpi.satisfaction_pct }}%</div>
        <div class="kpi-sub">положит. оценок</div>
      </div>
      <div class="kpi-card" :class="overdueClass(filteredKpi.avg_res_days, 15, 30)">
        <div class="kpi-label">Медиана решения</div>
        <div class="kpi-value">{{ filteredKpi.avg_res_days }}</div>
        <div class="kpi-sub">дней (медиана)</div>
      </div>
    </div>

    <!-- Row 2: Monthly trend + Channels pie -->
    <div class="charts-row">
      <div class="section-card chart-main">
        <div class="card-header">
          <h2>Динамика заявок по месяцам</h2>
          <div class="legend">
            <span class="legend-dot" style="background:#2980b9"></span>Всего
            <span class="legend-dot" style="background:#e74c3c"></span>Просрочено
          </div>
        </div>
        <canvas ref="trendCanvas" height="90"></canvas>
      </div>
      <div class="section-card chart-side">
        <h2>Способ обращения</h2>
        <canvas ref="channelCanvas" height="160"></canvas>
        <div class="channel-legend">
          <div v-for="(c, i) in CHANNELS" :key="c.name" class="channel-item">
            <span class="legend-dot" :style="{background: CHART_COLORS[i]}"></span>
            <span class="channel-name">{{ c.name }}</span>
            <span class="channel-val">{{ fmt(c.value) }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Row 3: Overdue trend + Acceptance rate -->
    <div class="charts-row">
      <div class="section-card chart-half">
        <h2>Доля просроченных заявок, %</h2>
        <canvas ref="overdueCanvas" height="100"></canvas>
      </div>
      <div class="section-card chart-half">
        <h2>Принято в работу за 20 мин., %</h2>
        <canvas ref="reactionCanvas" height="100"></canvas>
      </div>
    </div>

    <!-- Row 4: Satisfaction donut + Hourly heatmap -->
    <div class="charts-row">
      <div class="section-card chart-side">
        <h2>Оценки клиентов</h2>
        <canvas ref="satCanvas" height="180"></canvas>
        <div class="channel-legend">
          <div v-for="s in SAT_DATA" :key="s.label" class="channel-item">
            <span class="legend-dot" :style="{background: s.color}"></span>
            <span class="channel-name">{{ s.label }}</span>
            <span class="channel-val">{{ fmt(s.value) }}</span>
          </div>
        </div>
      </div>
      <div class="section-card chart-main">
        <h2>Распределение по часам суток</h2>
        <canvas ref="hourCanvas" height="90"></canvas>
      </div>
    </div>

    <!-- Row 5: Weekday bar -->
    <div class="section-card">
      <h2>Распределение по дням недели</h2>
      <canvas ref="weekdayCanvas" height="55"></canvas>
    </div>

    <!-- Nav tiles (same pattern as TpDashboard) -->
    <div class="nav-cards">
      <router-link to="/tp" class="nav-card">
        <span class="nav-icon">📊</span>
        <span>Еженедельный дашборд</span>
      </router-link>
      <router-link to="/tp/registry" class="nav-card">
        <span class="nav-icon">📋</span>
        <span>Реестр данных</span>
      </router-link>
      <router-link to="/tp/summary" class="nav-card">
        <span class="nav-icon">📈</span>
        <span>Сводная аналитика</span>
      </router-link>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import Chart from 'chart.js/auto'

// ── Static seed data extracted from Naumen export (tp-report/seed_data.json scope) ──
const MONTHLY = [
  {"period":"2024-01","total":60,"overdue":3,"overdue_pct":5.0,"closed":59,"avg_res_days":19.9,"satisfaction_pct":100.0,"in_20min_pct":55.0},
  {"period":"2024-02","total":41,"overdue":2,"overdue_pct":4.9,"closed":40,"avg_res_days":30.5,"satisfaction_pct":100.0,"in_20min_pct":61.0},
  {"period":"2024-03","total":38,"overdue":3,"overdue_pct":7.9,"closed":37,"avg_res_days":27.8,"satisfaction_pct":100.0,"in_20min_pct":34.2},
  {"period":"2024-04","total":35,"overdue":0,"overdue_pct":0.0,"closed":34,"avg_res_days":32.1,"satisfaction_pct":100.0,"in_20min_pct":31.4},
  {"period":"2024-05","total":30,"overdue":2,"overdue_pct":6.7,"closed":29,"avg_res_days":17.9,"satisfaction_pct":100.0,"in_20min_pct":26.7},
  {"period":"2024-06","total":39,"overdue":1,"overdue_pct":2.6,"closed":38,"avg_res_days":42.0,"satisfaction_pct":85.7,"in_20min_pct":33.3},
  {"period":"2024-07","total":32,"overdue":5,"overdue_pct":15.6,"closed":30,"avg_res_days":29.1,"satisfaction_pct":66.7,"in_20min_pct":21.9},
  {"period":"2024-08","total":36,"overdue":0,"overdue_pct":0.0,"closed":36,"avg_res_days":14.5,"satisfaction_pct":76.9,"in_20min_pct":38.9},
  {"period":"2024-09","total":63,"overdue":3,"overdue_pct":4.8,"closed":62,"avg_res_days":21.3,"satisfaction_pct":100.0,"in_20min_pct":23.8},
  {"period":"2024-10","total":116,"overdue":15,"overdue_pct":12.9,"closed":115,"avg_res_days":30.3,"satisfaction_pct":94.3,"in_20min_pct":62.9},
  {"period":"2024-11","total":115,"overdue":8,"overdue_pct":7.0,"closed":114,"avg_res_days":13.9,"satisfaction_pct":94.9,"in_20min_pct":46.1},
  {"period":"2024-12","total":88,"overdue":4,"overdue_pct":4.5,"closed":87,"avg_res_days":19.6,"satisfaction_pct":96.6,"in_20min_pct":39.8},
  {"period":"2025-01","total":72,"overdue":6,"overdue_pct":8.3,"closed":71,"avg_res_days":24.4,"satisfaction_pct":95.7,"in_20min_pct":44.4},
  {"period":"2025-02","total":92,"overdue":7,"overdue_pct":7.6,"closed":91,"avg_res_days":17.0,"satisfaction_pct":100.0,"in_20min_pct":53.3},
  {"period":"2025-03","total":61,"overdue":6,"overdue_pct":9.8,"closed":60,"avg_res_days":17.9,"satisfaction_pct":100.0,"in_20min_pct":57.4},
  {"period":"2025-04","total":73,"overdue":4,"overdue_pct":5.5,"closed":72,"avg_res_days":22.2,"satisfaction_pct":100.0,"in_20min_pct":61.6},
  {"period":"2025-05","total":65,"overdue":1,"overdue_pct":1.5,"closed":64,"avg_res_days":30.5,"satisfaction_pct":100.0,"in_20min_pct":32.3},
  {"period":"2025-06","total":41,"overdue":0,"overdue_pct":0.0,"closed":41,"avg_res_days":27.6,"satisfaction_pct":100.0,"in_20min_pct":39.0},
  {"period":"2025-07","total":56,"overdue":0,"overdue_pct":0.0,"closed":55,"avg_res_days":10.0,"satisfaction_pct":100.0,"in_20min_pct":42.9},
  {"period":"2025-08","total":57,"overdue":22,"overdue_pct":38.6,"closed":56,"avg_res_days":9.9,"satisfaction_pct":100.0,"in_20min_pct":29.8},
  {"period":"2025-09","total":51,"overdue":9,"overdue_pct":17.6,"closed":50,"avg_res_days":6.9,"satisfaction_pct":90.0,"in_20min_pct":41.2},
  {"period":"2025-10","total":36,"overdue":6,"overdue_pct":16.7,"closed":35,"avg_res_days":4.9,"satisfaction_pct":90.9,"in_20min_pct":55.6},
  {"period":"2025-11","total":23,"overdue":11,"overdue_pct":47.8,"closed":22,"avg_res_days":9.8,"satisfaction_pct":100.0,"in_20min_pct":47.8},
  {"period":"2025-12","total":23,"overdue":12,"overdue_pct":52.2,"closed":22,"avg_res_days":9.1,"satisfaction_pct":100.0,"in_20min_pct":52.2},
  {"period":"2026-01","total":27,"overdue":8,"overdue_pct":29.6,"closed":26,"avg_res_days":9.4,"satisfaction_pct":100.0,"in_20min_pct":48.1},
  {"period":"2026-02","total":37,"overdue":11,"overdue_pct":29.7,"closed":36,"avg_res_days":5.6,"satisfaction_pct":100.0,"in_20min_pct":40.5},
  {"period":"2026-03","total":37,"overdue":15,"overdue_pct":40.5,"closed":36,"avg_res_days":13.6,"satisfaction_pct":100.0,"in_20min_pct":27.0},
  {"period":"2026-04","total":54,"overdue":16,"overdue_pct":29.6,"closed":53,"avg_res_days":23.7,"satisfaction_pct":100.0,"in_20min_pct":42.6},
  {"period":"2026-05","total":35,"overdue":11,"overdue_pct":31.4,"closed":34,"avg_res_days":6.5,"satisfaction_pct":100.0,"in_20min_pct":31.4},
  {"period":"2026-06","total":47,"overdue":10,"overdue_pct":21.3,"closed":46,"avg_res_days":6.4,"satisfaction_pct":100.0,"in_20min_pct":25.5},
  {"period":"2026-07","total":50,"overdue":5,"overdue_pct":10.0,"closed":29,"avg_res_days":2.4,"satisfaction_pct":100.0,"in_20min_pct":20.0}
]

const CHANNELS = [
  {name: 'Личный кабинет', value: 781},
  {name: 'По почте', value: 717},
  {name: 'По телефону', value: 370},
]

const SAT_DATA = [
  {label: 'Отлично', value: 25, color: '#27ae60'},
  {label: 'Удовлетворён', value: 423, color: '#2ecc71'},
  {label: 'Нет серьёзных замечаний', value: 17, color: '#f39c12'},
  {label: 'Есть претензии', value: 14, color: '#e74c3c'},
]

const HOURLY = [
  {hour:7,count:11},{hour:8,count:65},{hour:9,count:222},{hour:10,count:247},
  {hour:11,count:206},{hour:12,count:152},{hour:13,count:136},{hour:14,count:194},
  {hour:15,count:181},{hour:16,count:151},{hour:17,count:119},{hour:18,count:53},
  {hour:19,count:16},{hour:20,count:5},{hour:21,count:3},{hour:22,count:2},
  {hour:23,count:1},{hour:6,count:1},{hour:0,count:1}
].sort((a,b) => a.hour - b.hour)

const WEEKDAY = [
  {name:'Пн',count:436},{name:'Вт',count:430},{name:'Ср',count:401},
  {name:'Чт',count:365},{name:'Пт',count:233},{name:'Сб',count:3},{name:'Вс',count:0}
]

const OPEN_NOW = 94
const CHART_COLORS = ['#2980b9','#27ae60','#e67e22','#8e44ad','#e74c3c','#1abc9c']

// ── Filters ──
const selectedYear = ref('')
const selectedQuarter = ref('')

const availableYears = computed(() => {
  return [...new Set(MONTHLY.map(r => r.period.slice(0, 4)))].sort()
})

const QUARTER_MAP = { Q1: ['01','02','03'], Q2: ['04','05','06'], Q3: ['07','08','09'], Q4: ['10','11','12'] }

const filteredData = computed(() => {
  return MONTHLY.filter(r => {
    const [y, m] = r.period.split('-')
    if (selectedYear.value && y !== selectedYear.value) return false
    if (selectedQuarter.value && !QUARTER_MAP[selectedQuarter.value].includes(m)) return false
    return true
  })
})

const filteredKpi = computed(() => {
  const data = filteredData.value
  if (!data.length) return {total:0,overdue:0,overdue_pct:0,in_20min_pct:0,satisfaction_pct:0,avg_res_days:0}
  const total = data.reduce((s,r) => s + r.total, 0)
  const overdue = data.reduce((s,r) => s + r.overdue, 0)
  const sumSat = data.reduce((s,r) => s + r.satisfaction_pct, 0)
  const sum20 = data.reduce((s,r) => s + r.in_20min_pct, 0)
  const avgDays = data.reduce((s,r) => s + r.avg_res_days, 0) / data.length
  return {
    total,
    overdue,
    overdue_pct: total ? +(overdue / total * 100).toFixed(1) : 0,
    in_20min_pct: +(sum20 / data.length).toFixed(1),
    satisfaction_pct: +(sumSat / data.length).toFixed(1),
    avg_res_days: +avgDays.toFixed(1),
  }
})

const globalKpi = computed(() => filteredKpi.value)

// ── Chart refs ──
const trendCanvas = ref(null)
const channelCanvas = ref(null)
const overdueCanvas = ref(null)
const reactionCanvas = ref(null)
const satCanvas = ref(null)
const hourCanvas = ref(null)
const weekdayCanvas = ref(null)

const charts = {}

function fmt(v) { return v != null ? Number(v).toLocaleString('ru-RU') : '—' }

// Traffic-light helpers (lower=worse for overdue, higher=worse for rates)
function overdueClass(val, green, yellow) {
  if (val == null) return 'light-gray'
  if (val <= green) return 'light-green'
  if (val <= yellow) return 'light-yellow'
  return 'light-red'
}
function rateClass(val, green, yellow) {
  if (val == null) return 'light-gray'
  if (val >= green) return 'light-green'
  if (val >= yellow) return 'light-yellow'
  return 'light-red'
}

function onYearChange() { selectedQuarter.value = '' }

function destroyAll() {
  Object.values(charts).forEach(c => { try { c.destroy() } catch {}})
}

function renderAll() {
  destroyAll()
  const data = filteredData.value
  if (!data.length) return
  const labels = data.map(r => r.period)

  // 1. Trend: bar (total) + line (overdue count)
  if (trendCanvas.value) {
    charts.trend = new Chart(trendCanvas.value, {
      type: 'bar',
      data: {
        labels,
        datasets: [
          { label: 'Всего', data: data.map(r => r.total), backgroundColor: 'rgba(41,128,185,0.6)', borderColor: '#2980b9', borderWidth: 1, borderRadius: 3, yAxisID: 'y' },
          { label: 'Просрочено', data: data.map(r => r.overdue), type: 'line', borderColor: '#e74c3c', backgroundColor: 'rgba(231,76,60,0.08)', tension: 0.3, fill: true, pointRadius: 3, yAxisID: 'y' },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: true,
        plugins: { legend: { display: false }, tooltip: { mode: 'index' } },
        scales: { y: { beginAtZero: true, ticks: { font: { size: 11 } } }, x: { ticks: { font: { size: 10 }, maxRotation: 45 } } },
      },
    })
  }

  // 2. Channel doughnut
  if (channelCanvas.value) {
    charts.channel = new Chart(channelCanvas.value, {
      type: 'doughnut',
      data: {
        labels: CHANNELS.map(c => c.name),
        datasets: [{ data: CHANNELS.map(c => c.value), backgroundColor: CHART_COLORS, borderWidth: 2 }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: ctx => `${ctx.label}: ${ctx.raw}` } } },
        cutout: '62%',
      },
    })
  }

  // 3. Overdue % line
  if (overdueCanvas.value) {
    charts.overdue = new Chart(overdueCanvas.value, {
      type: 'line',
      data: {
        labels,
        datasets: [{
          label: 'Просрочено, %',
          data: data.map(r => r.overdue_pct),
          borderColor: '#e74c3c', backgroundColor: 'rgba(231,76,60,0.08)',
          tension: 0.3, fill: true, pointRadius: 3, pointHoverRadius: 5,
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: true,
        plugins: { legend: { display: false } },
        scales: {
          y: { beginAtZero: true, max: 60, ticks: { callback: v => v + '%', font: { size: 11 } } },
          x: { ticks: { font: { size: 10 }, maxRotation: 45 } },
        },
      },
    })
  }

  // 4. Reaction (in_20min) % line
  if (reactionCanvas.value) {
    charts.reaction = new Chart(reactionCanvas.value, {
      type: 'line',
      data: {
        labels,
        datasets: [{
          label: 'Принято за 20 мин., %',
          data: data.map(r => r.in_20min_pct),
          borderColor: '#27ae60', backgroundColor: 'rgba(39,174,96,0.08)',
          tension: 0.3, fill: true, pointRadius: 3, pointHoverRadius: 5,
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: true,
        plugins: { legend: { display: false } },
        scales: {
          y: { beginAtZero: true, max: 100, ticks: { callback: v => v + '%', font: { size: 11 } } },
          x: { ticks: { font: { size: 10 }, maxRotation: 45 } },
        },
      },
    })
  }

  // 5. Satisfaction donut
  if (satCanvas.value) {
    charts.sat = new Chart(satCanvas.value, {
      type: 'doughnut',
      data: {
        labels: SAT_DATA.map(s => s.label),
        datasets: [{ data: SAT_DATA.map(s => s.value), backgroundColor: SAT_DATA.map(s => s.color), borderWidth: 2 }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        cutout: '62%',
      },
    })
  }

  // 6. Hourly bar
  if (hourCanvas.value) {
    charts.hour = new Chart(hourCanvas.value, {
      type: 'bar',
      data: {
        labels: HOURLY.map(h => `${h.hour}:00`),
        datasets: [{
          label: 'Заявок',
          data: HOURLY.map(h => h.count),
          backgroundColor: 'rgba(41,128,185,0.6)', borderColor: '#2980b9', borderWidth: 1, borderRadius: 3,
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: true,
        plugins: { legend: { display: false } },
        scales: { y: { beginAtZero: true, ticks: { font: { size: 11 } } }, x: { ticks: { font: { size: 10 } } } },
      },
    })
  }

  // 7. Weekday bar
  if (weekdayCanvas.value) {
    charts.weekday = new Chart(weekdayCanvas.value, {
      type: 'bar',
      data: {
        labels: WEEKDAY.map(w => w.name),
        datasets: [{
          label: 'Заявок',
          data: WEEKDAY.map(w => w.count),
          backgroundColor: WEEKDAY.map((_, i) => i < 5 ? 'rgba(41,128,185,0.65)' : 'rgba(189,195,199,0.5)'),
          borderRadius: 4,
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: true,
        plugins: { legend: { display: false } },
        scales: { y: { beginAtZero: true, ticks: { font: { size: 11 } } }, x: { ticks: { font: { size: 12 } } } },
      },
    })
  }
}

watch([selectedYear, selectedQuarter], () => nextTick(renderAll))
onMounted(() => nextTick(renderAll))
</script>

<style scoped>
.naumen-dashboard { padding: var(--space-6); display: flex; flex-direction: column; gap: var(--space-5); }

/* Header */
.page-header { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: var(--space-3); }
.page-header__left { display: flex; align-items: baseline; gap: var(--space-3); }
.page-header h1 { font-size: var(--text-xl); font-weight: 700; }
.data-badge { font-size: var(--text-xs); color: var(--color-text-muted); background: var(--color-surface-offset); border: 1px solid var(--color-border); padding: 2px var(--space-2); border-radius: var(--radius-full); }
.filters { display: flex; gap: var(--space-2); }
.filters select { padding: var(--space-2) var(--space-3); border: 1px solid var(--color-border); border-radius: var(--radius-md); background: var(--color-surface); color: var(--color-text); font-size: var(--text-sm); }

/* KPI grid — same pattern as TpDashboard */
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

/* Section cards */
.section-card { background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-lg); padding: var(--space-5); }
.section-card h2 { font-size: var(--text-base); font-weight: 600; margin-bottom: var(--space-4); }
.card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--space-4); }
.card-header h2 { margin-bottom: 0; }

/* Chart layout */
.charts-row { display: grid; grid-template-columns: 1fr 280px; gap: var(--space-3); }
@media (max-width: 800px) { .charts-row { grid-template-columns: 1fr; } }
.chart-main { min-width: 0; }
.chart-side { display: flex; flex-direction: column; }
.chart-half { min-width: 0; }
.charts-row:has(.chart-half) { grid-template-columns: 1fr 1fr; }
@media (max-width: 700px) { .charts-row:has(.chart-half) { grid-template-columns: 1fr; } }

/* Legend */
.legend { display: flex; gap: var(--space-3); align-items: center; font-size: var(--text-xs); color: var(--color-text-muted); }
.legend-dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: var(--space-1); }

/* Channel / sat legend */
.channel-legend { display: flex; flex-direction: column; gap: var(--space-2); margin-top: var(--space-3); }
.channel-item { display: flex; align-items: center; gap: var(--space-2); font-size: var(--text-xs); }
.channel-name { flex: 1; color: var(--color-text-muted); }
.channel-val { font-weight: 600; font-variant-numeric: tabular-nums; }

/* Nav cards — identical to TpDashboard */
.nav-cards { display: flex; gap: var(--space-3); flex-wrap: wrap; }
.nav-card { display: flex; align-items: center; gap: var(--space-2); padding: var(--space-4) var(--space-5); background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-lg); text-decoration: none; color: var(--color-text); font-weight: 500; font-size: var(--text-sm); transition: all var(--transition-interactive); }
.nav-card:hover { background: var(--color-primary); color: #fff; border-color: var(--color-primary); }
.nav-icon { font-size: 1.2rem; }
</style>
