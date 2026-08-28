<template>
  <div v-if="loading" class="tempty">Загрузка…</div>
  <div v-else class="tp-dash">

    <!-- Week selector -->
    <div class="filters" style="margin-bottom:12px">
      <label class="fl" style="align-self:center">Глубина анализа:</label>
      <select class="cfsel" v-model="weeks" @change="load">
        <option :value="4">4 недели</option>
        <option :value="8">8 недель</option>
        <option :value="12">12 недель</option>
        <option :value="26">26 недель</option>
      </select>
      <span class="tinfo" style="margin-left:auto">
        Последняя неделя: <strong>{{ lastWeekLabel }}</strong>
      </span>
    </div>

    <!-- KPI cards -->
    <div class="kpi-grid">
      <div v-for="k in KPI_CARDS" :key="k.key" class="kpi-card">
        <div class="kpi-label">{{ k.label }}</div>
        <div class="kpi-value">{{ fmtKpi(k, summary.last_week?.[k.key]) }}</div>
        <div class="kpi-trend" :class="trendClass(k, summary.trend?.[k.key])">
          {{ trendLabel(k, summary.trend?.[k.key]) }}
        </div>
        <div v-if="summary.traffic?.[k.key]" class="kpi-tl"
             :class="'kpi-tl-' + summary.traffic[k.key]">
          {{ TL_LABEL[summary.traffic[k.key]] }}
        </div>
      </div>
    </div>

    <!-- Charts row -->
    <div class="chart-row">
      <div class="chart-card" v-for="c in CHARTS" :key="c.key">
        <div class="chart-title">{{ c.label }}</div>
        <canvas :ref="el => canvasRefs[c.key] = el" height="200"></canvas>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { tpApi } from '../../api/tp.js'
import Chart from 'chart.js/auto'

const loading   = ref(true)
const weeks     = ref(8)
const summary   = ref({})
const canvasRefs = {}
const charts = {}

const TL_LABEL = { green: '● Норма', yellow: '● Внимание', red: '● Критично' }

const KPI_CARDS = [
  { key: 'total_in_work',        label: 'В работе (всего)',    dir: 'less', fmt: 'int' },
  { key: 'avail_total',          label: 'Доступность (всего)', dir: 'less', fmt: 'int' },
  { key: 'new_received',         label: 'Новых получено',      dir: 'less', fmt: 'int' },
  { key: 'total_solved_week',    label: 'Решено за неделю',   dir: 'more', fmt: 'int' },
  { key: 'ratio_solved_received',label: 'Коэф. решения',      dir: 'more', fmt: 'ratio' },
  { key: 'altos_avg_time',       label: 'AltOS ср.время, ч',  dir: 'less', fmt: 'h1' },
  { key: 'altoffice_avg_time',   label: 'AltOffice ср.время, ч', dir:'less', fmt:'h1' },
]

const CHARTS = [
  { key: 'total_in_work',     label: 'В работе (всего) по неделям' },
  { key: 'altos_avg_time',    label: 'AltOS — ср.время обработки (ч)' },
  { key: 'altoffice_avg_time',label: 'AltOffice — ср.время обработки (ч)' },
]

const lastWeekLabel = computed(() => {
  const lw = summary.value?.last_week
  if (!lw) return '—'
  return `${Math.round(lw.year ?? 0)}, нед. ${Math.round(lw.week ?? 0)}`
})

function fmtKpi(card, val) {
  if (val == null) return '—'
  if (card.fmt === 'ratio') return Number(val).toFixed(2)
  if (card.fmt === 'h1')   return Number(val).toFixed(1)
  return Math.round(val)
}

function trendClass(card, delta) {
  if (delta == null) return 'trend-neutral'
  const good = card.dir === 'less' ? delta < 0 : delta > 0
  if (delta === 0) return 'trend-neutral'
  return good ? 'trend-good' : 'trend-bad'
}

function trendLabel(card, delta) {
  if (delta == null) return ''
  const sign = delta > 0 ? '+' : ''
  const val  = card.fmt === 'ratio' ? Number(delta).toFixed(2)
             : card.fmt === 'h1'    ? Number(delta).toFixed(1)
             : Math.round(delta)
  return `${sign}${val} vs прошлая`
}

function buildCharts() {
  const chartData = summary.value?.chart || []
  const labels = chartData.map(r => `Н${Math.round(r.week)}`)

  CHARTS.forEach(c => {
    const el = canvasRefs[c.key]
    if (!el) return
    if (charts[c.key]) { charts[c.key].destroy() }
    const palette = getComputedStyle(document.documentElement)
    const primary = palette.getPropertyValue('--color-primary').trim() || '#2563eb'
    charts[c.key] = new Chart(el, {
      type: 'line',
      data: {
        labels,
        datasets: [{
          label: c.label,
          data: chartData.map(r => r[c.key] ?? null),
          borderColor: primary,
          backgroundColor: primary + '22',
          fill: true,
          tension: 0.3,
          pointRadius: 3,
        }]
      },
      options: {
        responsive: true,
        plugins: { legend: { display: false } },
        scales: { y: { beginAtZero: false } }
      }
    })
  })
}

async function load() {
  loading.value = true
  try {
    summary.value = await tpApi.summary(weeks.value)
    await nextTick()
    buildCharts()
  } finally { loading.value = false }
}

onMounted(load)
onUnmounted(() => Object.values(charts).forEach(c => c.destroy()))
</script>

<style scoped>
.tp-dash { display: flex; flex-direction: column; gap: 20px; }

.kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 12px;
}
.kpi-card {
  background: var(--color-surface, #fff);
  border: 1px solid var(--color-border, #e5e7eb);
  border-radius: 8px;
  padding: 14px 16px;
  display: flex; flex-direction: column; gap: 4px;
}
.kpi-label { font-size: .75rem; color: var(--color-muted, #6b7280); font-weight: 500; }
.kpi-value { font-size: 1.5rem; font-weight: 700; font-variant-numeric: tabular-nums; }
.kpi-trend { font-size: .75rem; }
.trend-good    { color: #16a34a; }
.trend-bad     { color: #dc2626; }
.trend-neutral { color: var(--color-muted, #6b7280); }
.kpi-tl { font-size: .7rem; font-weight: 600; margin-top: 4px; }
.kpi-tl-green  { color: #16a34a; }
.kpi-tl-yellow { color: #d97706; }
.kpi-tl-red    { color: #dc2626; }

.chart-row {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px;
}
.chart-card {
  background: var(--color-surface, #fff);
  border: 1px solid var(--color-border, #e5e7eb);
  border-radius: 8px;
  padding: 14px 16px;
}
.chart-title { font-size: .8rem; font-weight: 600; margin-bottom: 8px; color: var(--color-muted,#555); }
</style>
