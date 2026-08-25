<template>
  <div class="tp-summary">
    <div class="page-header">
      <h1>Сводная аналитика ТП</h1>
      <select v-model="filterYear">
        <option value="">Все годы</option>
        <option v-for="y in years" :key="y" :value="y">{{ y }}</option>
      </select>
    </div>

    <div v-if="loading" class="loading-state">Загрузка…</div>

    <template v-else>
      <!-- Aggregate KPIs -->
      <div class="kpi-grid">
        <div class="kpi-card">
          <div class="kpi-label">Недель в выборке</div>
          <div class="kpi-value">{{ filtered.length }}</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">Ср. в работе</div>
          <div class="kpi-value">{{ avg('total_in_work') }}</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">Ср. решено/нед.</div>
          <div class="kpi-value">{{ avg('total_solved_week') }}</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">Ср. коэф. решения</div>
          <div class="kpi-value">{{ avgDec('ratio_solved_received', 2) }}</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">Ср. AltOS время, ч.</div>
          <div class="kpi-value">{{ avgDec('altos_avg_time', 1) }}</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">Ср. AltOffice время, ч.</div>
          <div class="kpi-value">{{ avgDec('altoffice_avg_time', 1) }}</div>
        </div>
      </div>

      <!-- Client hours total -->
      <div class="section-card">
        <h2>Суммарные часы по клиентам</h2>
        <div class="client-grid">
          <div class="client-item" v-for="c in clientCols" :key="c.key">
            <span class="client-name">{{ c.label }}</span>
            <span class="client-value">{{ sumVal(c.key) }} ч.</span>
          </div>
        </div>
      </div>

      <!-- Charts -->
      <div class="charts-grid">
        <div class="section-card">
          <h2>В работе / Решено по неделям</h2>
          <canvas ref="chart1" height="100"></canvas>
        </div>
        <div class="section-card">
          <h2>Среднее время решения</h2>
          <canvas ref="chart2" height="100"></canvas>
        </div>
        <div class="section-card">
          <h2>Коэффициент решения</h2>
          <canvas ref="chart3" height="100"></canvas>
        </div>
        <div class="section-card">
          <h2>Доступность AltOS (дни)</h2>
          <canvas ref="chart4" height="100"></canvas>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { tpApi } from '../../api/tp.js'
import Chart from 'chart.js/auto'

const rows = ref([])
const loading = ref(false)
const filterYear = ref('')
const chart1 = ref(null); const chart2 = ref(null); const chart3 = ref(null); const chart4 = ref(null)
let instances = []

const years = computed(() => [...new Set(rows.value.map(r => r.year))].sort((a, b) => a - b))
const filtered = computed(() => {
  let r = [...rows.value].sort((a, b) => a.year - b.year || a.week - b.week)
  if (filterYear.value !== '') r = r.filter(x => x.year === Number(filterYear.value))
  return r
})

const clientCols = [
  { key: 'rushydro_hours', label: 'РусГидро' }, { key: 'transneft_hours', label: 'Транснефть' },
  { key: 'roscosmos_hours', label: 'Роскосмос' }, { key: 'bryansk_hours', label: 'Брянск' },
  { key: 'mchs_hours', label: 'МЧС' }, { key: 'internal_sales_hours', label: 'Внутр. продажи' },
]

function mean(arr) { return arr.length ? arr.reduce((s, v) => s + (Number(v) || 0), 0) / arr.length : 0 }
function avg(key) { return Math.round(mean(filtered.value.map(r => r[key]))) }
function avgDec(key, d) { return mean(filtered.value.map(r => r[key])).toFixed(d) }
function sumVal(key) { return Math.round(filtered.value.reduce((s, r) => s + (Number(r[key]) || 0), 0)).toLocaleString('ru-RU') }

function labels() { return filtered.value.map(r => `${r.year}W${String(r.week).padStart(2,'0')}`) }

function buildCharts() {
  instances.forEach(c => c.destroy())
  instances = []
  if (!filtered.value.length) return
  const L = labels()
  const make = (canvas, cfg) => { if (canvas) instances.push(new Chart(canvas, cfg)) }
  make(chart1.value, { type: 'line', data: { labels: L, datasets: [
    { label: 'В работе', data: filtered.value.map(r => r.total_in_work), borderColor: '#e67e22', tension: 0.3, fill: false },
    { label: 'Решено', data: filtered.value.map(r => r.total_solved_week), borderColor: '#27ae60', tension: 0.3, fill: false },
    { label: 'Новых', data: filtered.value.map(r => r.new_received), borderColor: '#2980b9', tension: 0.3, fill: false, borderDash: [4,4] },
  ]}, options: { responsive: true } })
  make(chart2.value, { type: 'bar', data: { labels: L, datasets: [
    { label: 'AltOS', data: filtered.value.map(r => r.altos_avg_time), backgroundColor: 'rgba(52,152,219,.7)' },
    { label: 'AltOffice', data: filtered.value.map(r => r.altoffice_avg_time), backgroundColor: 'rgba(155,89,182,.7)' },
  ]}, options: { responsive: true } })
  make(chart3.value, { type: 'line', data: { labels: L, datasets: [
    { label: 'Коэф.', data: filtered.value.map(r => r.ratio_solved_received), borderColor: '#16a085', tension: 0.3, fill: false },
  ]}, options: { responsive: true, scales: { y: { beginAtZero: true } } } })
  make(chart4.value, { type: 'bar', data: { labels: L, datasets: [
    { label: '1-3 дн.', data: filtered.value.map(r => r.altos_avail_1_3), backgroundColor: 'rgba(39,174,96,.8)', stack: 'avail' },
    { label: '4-7 дн.', data: filtered.value.map(r => r.altos_avail_4_7), backgroundColor: 'rgba(241,196,15,.8)', stack: 'avail' },
    { label: '8-10 дн.', data: filtered.value.map(r => r.altos_avail_8_10), backgroundColor: 'rgba(231,76,60,.8)', stack: 'avail' },
  ]}, options: { responsive: true, scales: { x: { stacked: true }, y: { stacked: true, beginAtZero: true } } } })
}

watch(filtered, () => nextTick(buildCharts))
onMounted(async () => {
  loading.value = true
  try { rows.value = await tpApi.getRows() } finally { loading.value = false }
  await nextTick()
  buildCharts()
})
</script>

<style scoped>
.tp-summary { padding: var(--space-6); display: flex; flex-direction: column; gap: var(--space-5); }
.page-header { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: var(--space-3); }
.page-header h1 { font-size: var(--text-xl); font-weight: 700; }
.page-header select { padding: var(--space-2) var(--space-3); border: 1px solid var(--color-border); border-radius: var(--radius-md); background: var(--color-surface); color: var(--color-text); font-size: var(--text-sm); }
.kpi-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: var(--space-3); }
.kpi-card { background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-lg); padding: var(--space-4); text-align: center; }
.kpi-label { font-size: var(--text-xs); color: var(--color-text-muted); margin-bottom: var(--space-2); text-transform: uppercase; letter-spacing: .03em; }
.kpi-value { font-size: var(--text-xl); font-weight: 700; font-variant-numeric: tabular-nums; }
.section-card { background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-lg); padding: var(--space-5); }
.section-card h2 { font-size: var(--text-lg); font-weight: 600; margin-bottom: var(--space-4); }
.client-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: var(--space-2); }
.client-item { display: flex; justify-content: space-between; align-items: center; padding: var(--space-2) var(--space-3); background: var(--color-surface-offset); border-radius: var(--radius-md); font-size: var(--text-sm); }
.client-name { color: var(--color-text-muted); }
.client-value { font-weight: 600; font-variant-numeric: tabular-nums; }
.charts-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(400px, 1fr)); gap: var(--space-4); }
.loading-state { padding: var(--space-8); text-align: center; color: var(--color-text-muted); }
</style>
