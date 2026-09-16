<template>
  <div v-if="loading" class="tempty">Загрузка…</div>
  <div v-else class="tp-dash">

    <div class="tp-head">
      <div class="tp-head-l">
        <h1 class="tp-title">Сводная аналитика процессов ТП</h1>
        <div class="tp-sub">Сопоставление еженедельного отчёта ТП и заявок Naumen по ISO-неделям · {{ weeksCount }} недель</div>
      </div>
      <div class="tp-filters">
        <div class="tp-f-row tp-f-controls">
          <div class="tp-f-col">
            <span class="fl">Год</span>
            <select class="fsel" v-model="year">
              <option value="all">Все годы</option>
              <option v-for="y in years" :key="y" :value="y">{{ y }}</option>
            </select>
          </div>
          <div class="tp-f-col">
            <span class="fl">Быстрый период</span>
            <select class="fsel" v-model.number="lastN">
              <option :value="0">Всё время</option>
              <option :value="13">13 недель</option>
              <option :value="26">26 недель</option>
              <option :value="52">52 недели</option>
            </select>
          </div>
        </div>
        <div class="tp-f-meta">{{ rows.length }} недель в выборке · сопоставление по году и номеру ISO-недели</div>
      </div>
    </div>

    <!-- KPI -->
    <div class="kpi-grid">
      <div class="kpi"><div class="kpi-lbl">Заявок по отчёту ТП</div><div class="kpi-val">{{ fmt(sum(rows, 'tp_new_received')) }}</div><div class="kpi-sub">принято за выбранные недели</div></div>
      <div class="kpi"><div class="kpi-lbl">Зарегистрировано в Naumen</div><div class="kpi-val">{{ fmt(sum(rows, 'naumen_registered')) }}</div><div class="kpi-sub">за те же недели</div></div>
      <div class="kpi" :class="coverageClass"><div class="kpi-lbl">Покрытие отчёта заявками Naumen</div><div class="kpi-val">{{ coverage }}%</div><div class="kpi-sub">доля Naumen от принятых по отчёту</div></div>
      <div class="kpi"><div class="kpi-lbl">Просрочено в Naumen</div><div class="kpi-val">{{ fmt(sum(rows, 'naumen_overdue')) }}</div><div class="kpi-sub">{{ overduePct }}% от зарегистрированных</div></div>
      <div class="kpi"><div class="kpi-lbl">Ср. время решения по отчёту</div><div class="kpi-val">{{ fmtAvg(avgOf(rows, 'tp_altos_avg_time')) }}</div><div class="kpi-sub">AlterOS, ч</div></div>
      <div class="kpi"><div class="kpi-lbl">Ср. время решения в Naumen</div><div class="kpi-val">{{ fmtAvg(avgOf(rows, 'naumen_avg_resolve_hours')) }}</div><div class="kpi-sub">фактическое, ч</div></div>
    </div>

    <!-- Weekly charts -->
    <div class="tp-section">Поток заявок по неделям</div>
    <div class="cgrid-2">
      <div class="ccard"><div class="ctitle">Принято: отчёт ТП vs Naumen</div><div class="chart-box tp-tall"><canvas ref="cReceived"></canvas></div></div>
      <div class="ccard"><div class="ctitle">Решено: отчёт ТП vs Naumen</div><div class="chart-box tp-tall"><canvas ref="cSolved"></canvas></div></div>
    </div>
    <div class="cgrid-2">
      <div class="ccard"><div class="ctitle">В работе (отчёт) vs незакрытые Naumen</div><div class="chart-box tp-tall"><canvas ref="cBacklog"></canvas></div></div>
      <div class="ccard"><div class="ctitle">РусГидро: трудозатраты, ч vs заявки Naumen</div><div class="chart-box tp-tall"><canvas ref="cRusg"></canvas></div></div>
    </div>
    <div class="cgrid-2">
      <div class="ccard"><div class="ctitle">Среднее время решения, ч: отчёт vs Naumen</div><div class="chart-box tp-tall"><canvas ref="cAvg"></canvas></div></div>
      <div class="ccard"><div class="ctitle">Просроченные заявки Naumen по неделям</div><div class="chart-box tp-tall"><canvas ref="cOverdue"></canvas></div></div>
    </div>

    <!-- Match table -->
    <div class="tp-section">Недели детально <span class="tp-tag">отчёт + Naumen</span></div>
    <div class="twrap">
      <div class="tp-table-tools">
        <span class="td-muted">Расхождение — разница между принятыми по отчёту ТП и зарегистрированными в Naumen за ту же неделю.</span>
      </div>
      <div class="tscroll">
        <table>
          <thead>
            <tr>
              <th>Неделя</th>
              <th>Принято (отчёт)</th>
              <th>Наумен</th>
              <th>Расхожд.</th>
              <th>Решено (отчёт)</th>
              <th>Наумен</th>
              <th>В работе (отчёт)</th>
              <th>AltOS ср.вр, ч</th>
              <th>Naumen ср.вр, ч</th>
              <th>Просрочено Naumen</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in rowsReversed" :key="r.period">
              <td class="td-p">{{ r.period }}</td>
              <td>{{ fmtCell(r.tp_new_received) }}</td>
              <td>{{ r.naumen_registered || 0 }}</td>
              <td>
                <span v-if="diff(r) !== null" class="sb" :class="Math.abs(diff(r)) > 5 ? 's-fired' : diff(r) !== 0 ? 'tp-badge-mid' : 's-hired'">{{ diff(r) > 0 ? '+' : '' }}{{ diff(r) }}</span>
                <span v-else class="td-muted">—</span>
              </td>
              <td>{{ fmtCell(r.tp_solved) }}</td>
              <td>{{ r.naumen_solved || 0 }}</td>
              <td>{{ fmtCell(r.tp_in_work) }}</td>
              <td>{{ fmtCell(r.tp_altos_avg_time) }}</td>
              <td>{{ fmtCell(r.naumen_avg_resolve_hours) }}</td>
              <td>{{ r.naumen_overdue || 0 }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { tpApi } from '../../api/tp.js'
import Chart from 'chart.js/auto'

const loading = ref(true)
const all = ref([])
const year = ref('all')
const lastN = ref(0)

const cReceived = ref(null), cSolved = ref(null), cBacklog = ref(null),
      cRusg = ref(null), cAvg = ref(null), cOverdue = ref(null)
const charts = {}

const weeksCount = computed(() => all.value.length)
const years = computed(() => [...new Set(all.value.map(r => r.year))].sort())
const rows = computed(() => {
  let rs = all.value
  if (year.value !== 'all') rs = rs.filter(r => r.year === year.value)
  if (lastN.value > 0) rs = rs.slice(-lastN.value)
  return rs
})
const rowsReversed = computed(() => rows.value.slice().reverse())

const sum = (rs, key) => rs.reduce((s, r) => s + (r[key] || 0), 0)
const avgOf = (rs, key) => {
  const vals = rs.map(r => r[key]).filter(v => v != null)
  return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null
}
const fmt = v => Math.round(v).toLocaleString('ru-RU')
const fmtAvg = v => v == null ? '—' : v.toFixed(1)
const fmtCell = v => v == null ? '—' : (Number.isInteger(v) ? v : Number(v).toFixed(2))
const diff = r => (r.tp_new_received == null && !r.naumen_registered) ? null : Math.round((r.tp_new_received || 0) - (r.naumen_registered || 0))

const coverage = computed(() => {
  const tpSum = sum(rows.value, 'tp_new_received')
  if (!tpSum) return 0
  return Math.round(sum(rows.value, 'naumen_registered') / tpSum * 1000) / 10
})
const coverageClass = computed(() => coverage.value >= 85 ? 'light-green' : coverage.value >= 60 ? 'light-yellow' : 'light-red')
const overduePct = computed(() => {
  const reg = sum(rows.value, 'naumen_registered')
  return reg ? Math.round(sum(rows.value, 'naumen_overdue') / reg * 1000) / 10 : 0
})

function css(v) { return getComputedStyle(document.documentElement).getPropertyValue(v).trim() }

function baseOptions() {
  return {
    responsive: true, maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    plugins: { legend: { labels: { color: css('--c-txt'), boxWidth: 12, font: { size: 11 } } }, tooltip: { titleColor: '#fff', bodyColor: '#fff' } },
    scales: {
      x: { grid: { display: false }, ticks: { color: css('--c-muted'), font: { size: 9 }, maxRotation: 0, autoSkip: true } },
      y: { grid: { color: css('--c-div') }, ticks: { color: css('--c-muted') } },
    },
  }
}

function renderAll() {
  Object.values(charts).forEach(c => c.destroy())
  for (const k of Object.keys(charts)) delete charts[k]
  const rs = rows.value
  if (!rs.length) return
  const labels = rs.map(r => r.period)

  const combo = (el, ds) => el ? new Chart(el, { type: 'bar', data: { labels, datasets: ds }, options: baseOptions() }) : null

  charts.received = combo(cReceived.value, [
    { label: 'Принято (отчёт ТП)', data: rs.map(r => r.tp_new_received), backgroundColor: css('--series-received') },
    { label: 'Зарегистрировано (Naumen)', data: rs.map(r => r.naumen_registered), backgroundColor: css('--client-rushydro') },
  ])

  charts.solved = combo(cSolved.value, [
    { label: 'Решено (отчёт ТП)', data: rs.map(r => r.tp_solved), backgroundColor: css('--series-solved') },
    { label: 'Решено (Naumen)', data: rs.map(r => r.naumen_solved), backgroundColor: css('--client-transneft') },
  ])

  charts.backlog = combo(cBacklog.value, [
    { label: 'В работе (отчёт ТП)', data: rs.map(r => r.tp_in_work), backgroundColor: css('--series-inwork') },
    { label: 'Просрочено (Naumen)', data: rs.map(r => r.naumen_overdue), backgroundColor: css('--c-err') },
  ])

  charts.rusg = cRusg.value ? new Chart(cRusg.value, {
    type: 'bar',
    data: { labels, datasets: [
      { label: 'РусГидро, трудозатраты ч (отчёт)', data: rs.map(r => r.tp_rushydro_hours), backgroundColor: css('--client-rushydro') },
      { label: 'Заявки организаций РусГидро (Naumen)', data: rs.map(r => r.naumen_rushydro), backgroundColor: css('--client-transneft'), yAxisID: 'y1' },
    ] },
    options: Object.assign(baseOptions(), { scales: {
      x: { grid: { display: false }, ticks: { color: css('--c-muted'), font: { size: 9 }, maxRotation: 0, autoSkip: true } },
      y: { grid: { color: css('--c-div') }, ticks: { color: css('--c-muted') } },
      y1: { position: 'right', grid: { display: false }, ticks: { color: css('--c-muted') } },
    } }),
  }) : null

  charts.avg = cAvg.value ? new Chart(cAvg.value, {
    type: 'line',
    data: { labels, datasets: [
      { label: 'AlterOS ср.время (отчёт), ч', data: rs.map(r => r.tp_altos_avg_time), borderColor: css('--series-avgtime-altos'), backgroundColor: css('--series-avgtime-altos') + '22', fill: true, tension: 0.3, pointRadius: 2, spanGaps: true },
      { label: 'Naumen факт. ср.время решения, ч', data: rs.map(r => r.naumen_avg_resolve_hours), borderColor: css('--series-avgtime-altoffice'), backgroundColor: 'transparent', tension: 0.3, pointRadius: 2, spanGaps: true },
    ] },
    options: baseOptions(),
  }) : null

  charts.overdue = combo(cOverdue.value, [
    { label: 'Просрочено (Naumen)', data: rs.map(r => r.naumen_overdue), backgroundColor: css('--c-err') },
  ])
}

watch([year, lastN], async () => { await nextTick(); renderAll() })

let themeObserver = null
onMounted(async () => {
  try {
    const res = await tpApi.naumenMatch()
    all.value = res.weeks || []
    loading.value = false
    await nextTick()
    renderAll()
    themeObserver = new MutationObserver(async () => { await nextTick(); renderAll() })
    themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme', 'style'] })
  } finally { loading.value = false }
})
onUnmounted(() => { Object.values(charts).forEach(c => c.destroy()); themeObserver?.disconnect() })
</script>

<style scoped>
.tp-head{display:flex;gap:var(--sp6);align-items:flex-start;justify-content:space-between;flex-wrap:wrap;margin-bottom:var(--sp6);}
.tp-head-l{min-width:260px;}
.tp-title{font-size:1.25rem;font-weight:700;letter-spacing:-.02em;}
.tp-sub{font-size:.8125rem;color:var(--c-muted);margin-top:2px;}
.tp-filters{background:var(--c-surf2);border:1px solid var(--c-brd);border-radius:var(--r3);padding:var(--sp4) var(--sp5);box-shadow:var(--sh1);display:flex;flex-direction:column;gap:var(--sp3);min-width:300px;flex:1;max-width:480px;}
.tp-f-row{display:flex;flex-direction:column;gap:var(--sp1);}
.tp-f-controls{flex-direction:row;gap:var(--sp3);align-items:flex-end;flex-wrap:wrap;}
.tp-f-col{display:flex;flex-direction:column;gap:var(--sp1);min-width:130px;flex:1;}
.tp-f-col .fsel{width:100%;}
.tp-f-meta{font-size:.75rem;color:var(--c-faint);}
.tp-section{font-size:1.0625rem;font-weight:700;letter-spacing:-.01em;margin:var(--sp8) 0 var(--sp4);display:flex;align-items:center;gap:var(--sp3);}
.tp-section:first-of-type{margin-top:0;}
.tp-tag{font-size:.6875rem;font-weight:600;color:var(--c-muted);background:var(--c-off);padding:3px 10px;border-radius:99px;text-transform:uppercase;letter-spacing:.04em;}
.tp-tall{height:330px;}
.tp-badge-mid{background:var(--c-warn-l);color:var(--c-warn);}
.tp-badge-mid::before{background:var(--c-warn);}
.tp-table-tools{display:flex;justify-content:space-between;align-items:center;gap:var(--sp3);padding:var(--sp3) var(--sp4);font-size:.75rem;flex-wrap:wrap;}
.tscroll{max-height:540px;overflow-y:auto;}
@media(max-width:1100px){.tp-head{flex-direction:column;}.tp-filters{max-width:100%;}}
</style>
