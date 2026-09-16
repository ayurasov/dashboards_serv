<template>
  <div v-if="loading" class="tempty">Загрузка…</div>
  <div v-else-if="empty" class="tempty">
    Нет данных по заявкам Naumen. Импортируйте файл экспорта «Все заявки».
    <div v-if="isAdmin" style="margin-top:16px">
      <label class="btn btn-p" style="cursor:pointer">
        Импорт xlsx
        <input type="file" accept=".xlsx" style="display:none" @change="onImport">
      </label>
    </div>
  </div>
  <div v-else-if="noMatch" class="tempty">
    Нет данных по выбранным фильт­рам.
    <div style="margin-top:16px"><button class="btn btn-g" @click="resetFilters">Сбросить филь­тры</button></div>
  </div>
  <div v-else class="tp-dash">

    <div class="tp-head">
      <div class="tp-head-l">
        <h1 class="tp-title">Аналитика заявок Naumen</h1>
        <div class="tp-sub">Экспорт SD: Импортозамещение (AlterOS) · {{ periodLabel }}</div>
      </div>
      <div class="tp-filters">
        <div class="tp-f-row">
          <span class="fl">Быстрый период</span>
          <div class="chip-row">
            <span v-for="q in QUICK" :key="q.v" class="chip" :class="{ active: quick === q.v }"
                  @click="quick = q.v">{{ q.label }}</span>
          </div>
        </div>
        <div class="tp-f-row">
          <span class="fl">Год регистрации</span>
          <div class="chip-row">
            <span class="chip" :class="{ active: year === 'all' }" @click="year = 'all'">Все</span>
            <span v-for="y in years" :key="y" class="chip" :class="{ active: year === String(y) }"
                  @click="year = String(y)">{{ y }}</span>
          </div>
        </div>
        <div class="tp-f-row tp-f-controls">
          <div class="tp-f-col">
            <span class="fl">Организация</span>
            <select class="fsel" v-model="org">
              <option value="all">Все организации</option>
              <option v-for="o in orgOptions" :key="o.org" :value="o.org">{{ o.org }} ({{ o.total }})</option>
            </select>
          </div>
        </div>
        <div class="tp-f-bottom">
          <div class="tp-f-meta">{{ (d.months || []).length }} месяцев · {{ (d.orgs || []).length }} организаций</div>
          <div style="display:flex;gap:8px">
            <button class="btn btn-g" @click="resetFilters">Сбросить</button>
            <label v-if="isAdmin" class="btn btn-g" style="cursor:pointer">
              {{ importing ? 'Импорт…' : 'Импорт xlsx' }}
              <input type="file" accept=".xlsx" style="display:none" @change="onImport" :disabled="importing">
            </label>
          </div>
        </div>
      </div>
    </div>

    <!-- KPI -->
    <div class="kpi-grid">
      <div class="kpi"><div class="kpi-lbl">Всего заявок</div><div class="kpi-val">{{ d.total.toLocaleString('ru-RU') }}</div></div>
      <div class="kpi" :class="kpiLight('ok')"><div class="kpi-lbl">Закрыто</div><div class="kpi-val">{{ d.closed.toLocaleString('ru-RU') }}</div><div class="kpi-sub">{{ pct(d.closed) }} от всех</div></div>
      <div class="kpi" :class="kpiLight('warn')"><div class="kpi-lbl">Просрочено</div><div class="kpi-val">{{ d.overdue.toLocaleString('ru-RU') }}</div><div class="kpi-sub">{{ d.overdue_pct }}% от всех</div></div>
      <div class="kpi"><div class="kpi-lbl">Возобновлено</div><div class="kpi-val">{{ d.reopened.toLocaleString('ru-RU') }}</div><div class="kpi-sub">{{ d.reopened_pct }}% от всех</div></div>
      <div class="kpi"><div class="kpi-lbl">Ср. время обработки</div><div class="kpi-val">{{ fmtH(d.avg_proc_hours) }}</div><div class="kpi-sub">часов</div></div>
      <div class="kpi"><div class="kpi-lbl">Ср. время решения</div><div class="kpi-val">{{ fmtH(d.avg_resolve_hours) }}</div><div class="kpi-sub">часов, от регистрации до решения</div></div>
    </div>

    <!-- Monthly dynamics -->
    <div class="tp-section">Динамика по месяцам</div>
    <div class="cgrid-2">
      <div class="ccard"><div class="ctitle">Принято vs Решено</div><div class="chart-box tp-tall"><canvas ref="cFlow"></canvas></div></div>
      <div class="ccard"><div class="ctitle">Просроченные и возобновлённые, %</div><div class="chart-box tp-tall"><canvas ref="cOverdue"></canvas></div></div>
    </div>
    <div class="cgrid-2">
      <div class="ccard"><div class="ctitle">Среднее время обработки, ч</div><div class="chart-box tp-tall"><canvas ref="cProc"></canvas></div></div>
      <div class="ccard"><div class="ctitle">Среднее время решения, ч</div><div class="chart-box tp-tall"><canvas ref="cResolve"></canvas></div></div>
    </div>

    <!-- Structure -->
    <div class="tp-section">Структура обращений</div>
    <div class="cgrid">
      <div class="ccard"><div class="ctitle">Топ организаций</div><div class="chart-box tp-tall"><canvas ref="cOrgs"></canvas></div></div>
      <div class="ccard"><div class="ctitle">Каналы обращений</div><div class="chart-box tp-tall"><canvas ref="cChannels"></canvas></div></div>
      <div class="ccard"><div class="ctitle">Статусы заявок</div><div class="chart-box tp-tall"><canvas ref="cStatuses"></canvas></div></div>
    </div>

    <!-- Org table -->
    <div class="tp-section">Организации <span class="tp-tag">детально</span></div>
    <div class="twrap">
      <div class="tscroll">
        <table>
          <thead>
            <tr><th>Организация</th><th>Заявок</th><th>Закрыто</th><th>Просрочено</th><th>% просрочки</th><th>Ср. время обработки, ч</th></tr>
          </thead>
          <tbody>
            <tr v-for="o in orgRows" :key="o.org">
              <td class="td-p">{{ o.org }}</td>
              <td>{{ o.total }}</td>
              <td>{{ o.closed }}</td>
              <td>{{ o.overdue }}</td>
              <td><span class="sb" :class="o.overdue_pct > 20 ? 's-fired' : o.overdue_pct > 10 ? 'tp-badge-mid' : 's-hired'">{{ o.overdue_pct ?? '—' }}%</span></td>
              <td>{{ o.avg_proc_hours ?? '—' }}</td>
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
import { useAuthStore } from '../../stores/auth.js'
import { toastOk, toastError } from '../../composables/useToast.js'
import Chart from 'chart.js/auto'

const auth = useAuthStore()
const isAdmin = computed(() => auth.isAdmin || auth.canAdminService('tech'))

const loading = ref(true)
const empty = ref(false)
const noMatch = ref(false)
const importing = ref(false)
const d = ref({})
const dAll = ref({})   // unfiltered summary — source of year/org options
const quick = ref('all')
const year = ref('all')
const org = ref('all')

const QUICK = [
  { v: '1',  label: 'Последний месяц' },
  { v: '3',  label: '3 месяца' },
  { v: '6',  label: '6 месяцев' },
  { v: '12', label: '12 месяцев' },
  { v: 'all', label: 'Всё время' },
]

const cFlow = ref(null), cOverdue = ref(null), cProc = ref(null), cResolve = ref(null),
      cOrgs = ref(null), cChannels = ref(null), cStatuses = ref(null)
const charts = {}

const periodLabel = computed(() => {
  if (!d.value.first) return ''
  const f = new Date(d.value.first).toLocaleDateString('ru-RU', { month: 'short', year: 'numeric' })
  const l = new Date(d.value.last).toLocaleDateString('ru-RU', { month: 'short', year: 'numeric' })
  return `${f} — ${l}`
})
const years = computed(() => [...new Set((dAll.value.months || []).map(m => m.month.slice(0, 4)))].sort())
const orgOptions = computed(() => (dAll.value.orgs || []))

const filteredMonths = computed(() => d.value.months || [])
const filteredOrgs = computed(() => d.value.orgs || [])
const orgRows = computed(() => filteredOrgs.value)

function resetFilters() {
  quick.value = 'all'
  year.value = 'all'
  org.value = 'all'
}

const pct = v => d.value.total ? Math.round(v / d.value.total * 1000) / 10 : 0
const fmtH = v => v == null ? '—' : Math.round(v).toLocaleString('ru-RU')
const kpiLight = s => s === 'ok' ? 'light-green' : s === 'warn' ? 'light-yellow' : ''

function css(v) { return getComputedStyle(document.documentElement).getPropertyValue(v).trim() }

function baseOptions(extra = {}) {
  return Object.assign({
    responsive: true, maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    plugins: { legend: { labels: { color: css('--c-txt'), boxWidth: 12, font: { size: 11 } } }, tooltip: { titleColor: '#fff', bodyColor: '#fff' } },
    scales: {
      x: { grid: { display: false }, ticks: { color: css('--c-muted'), font: { size: 9 }, maxRotation: 0, autoSkip: true } },
      y: { grid: { color: css('--c-div') }, ticks: { color: css('--c-muted') } },
    },
  }, extra)
}

function pctLabels(labels, data, colors) {
  const total = data.reduce((a, b) => a + (b || 0), 0)
  return labels.map((label, i) => ({
    text: `${label} — ${total > 0 ? ((data[i] / total) * 100).toFixed(1) : '0.0'}%`,
    fillStyle: colors[i], strokeStyle: colors[i], index: i,
  }))
}

function mk(key, el, cfg) {
  if (!el) return
  charts[key] = new Chart(el, cfg)
}

function renderAll() {
  Object.values(charts).forEach(c => c.destroy())
  for (const k of Object.keys(charts)) delete charts[k]
  const ms = filteredMonths.value
  if (!ms.length) return
  const labels = ms.map(m => m.month)

  mk('flow', cFlow.value, {
    type: 'bar',
    data: { labels, datasets: [
      { label: 'Принято', data: ms.map(m => m.registered), backgroundColor: css('--series-received') },
      { label: 'Решено', data: ms.map(m => m.solved), backgroundColor: css('--series-solved') },
    ] },
    options: baseOptions(),
  })

  mk('overdue', cOverdue.value, {
    type: 'line',
    data: { labels, datasets: [
      { label: 'Просрочено, %', data: ms.map(m => m.overdue_pct), borderColor: css('--c-err'), backgroundColor: css('--c-err') + '22', fill: true, tension: 0.3, pointRadius: 2, spanGaps: true },
      { label: 'Возобновлено, % (×10)', data: ms.map(m => m.reopened && m.registered ? Math.round((m.reopened / m.registered) * 1000) / 10 : null), borderColor: css('--c-warn'), backgroundColor: 'transparent', tension: 0.3, pointRadius: 2, spanGaps: true },
    ] },
    options: baseOptions(),
  })

  mk('proc', cProc.value, {
    type: 'line',
    data: { labels, datasets: [{
      label: 'Ср. время обработки, ч', data: ms.map(m => m.avg_proc_hours),
      borderColor: css('--series-avgtime-altos'), backgroundColor: css('--series-avgtime-altos') + '22', fill: true, tension: 0.3, pointRadius: 2, spanGaps: true,
    }] },
    options: baseOptions(),
  })

  charts.resolve = new Chart(cResolve.value, {
    type: 'line',
    data: { labels, datasets: [{
      label: 'Ср. время решения, ч', data: ms.map(m => m.avg_resolve_hours),
      borderColor: css('--series-avgtime-altoffice'), backgroundColor: css('--series-avgtime-altoffice') + '22', fill: true, tension: 0.3, pointRadius: 2, spanGaps: true,
    }] },
    options: baseOptions(),
  })

  const topOrgs = (d.value.orgs || []).slice(0, 15).slice().reverse()
  mk('orgs', cOrgs.value, {
    type: 'bar',
    data: { labels: topOrgs.map(o => o.org), datasets: [
      { label: 'Заявок', data: topOrgs.map(o => o.total), backgroundColor: css('--client-rushydro') },
      { label: 'Просрочено', data: topOrgs.map(o => o.overdue), backgroundColor: css('--c-err') },
    ] },
    options: baseOptions({ indexAxis: 'y', scales: { x: { grid: { color: css('--c-div') }, ticks: { color: css('--c-muted'), font: { size: 9 } } }, y: { grid: { display: false }, ticks: { color: css('--c-muted'), font: { size: 9 } } } } }),
  })

  const ch = d.value.channels || []
  mk('channels', cChannels.value, {
    type: 'doughnut',
    data: { labels: ch.map(c => c.channel), datasets: [{ data: ch.map(c => c.count), backgroundColor: [css('--client-transneft'), css('--client-rushydro'), css('--client-mchs'), css('--client-internal')], borderWidth: 0 }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom', labels: { color: css('--c-txt'), font: { size: 11 }, boxWidth: 12, generateLabels: c => pctLabels(c.data.labels, c.data.datasets[0].data, c.data.datasets[0].backgroundColor) } } } },
  })

  const st = d.value.statuses || []
  mk('statuses', cStatuses.value, {
    type: 'doughnut',
    data: { labels: st.map(s => s.status), datasets: [{ data: st.map(s => s.count), backgroundColor: [css('--c-ok'), css('--c-warn'), css('--c-blue'), css('--c-err'), css('--client-internal')], borderWidth: 0 }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom', labels: { color: css('--c-txt'), font: { size: 11 }, boxWidth: 12, generateLabels: c => pctLabels(c.data.labels, c.data.datasets[0].data, c.data.datasets[0].backgroundColor) } } } },
  })
}

async function load() {
  loading.value = true
  try {
    const params = {}
    if (quick.value !== 'all') params.months = parseInt(quick.value)
    if (year.value !== 'all') params.year = year.value
    if (org.value !== 'all') params.org = org.value
    const [res, all] = await Promise.all([tpApi.naumenSummary(params), dAll.value.months ? Promise.resolve(null) : tpApi.naumenSummary()])
    if (all) dAll.value = all.empty ? {} : all
    if (res.empty) {
      noMatch.value = !!(dAll.value.months && dAll.value.months.length)
      if (!noMatch.value) { empty.value = true }
      return
    }
    noMatch.value = false
    d.value = res
    loading.value = false
    await nextTick()
    renderAll()
  } finally { loading.value = false }
}

async function onImport(e) {
  const file = e.target.files[0]
  if (!file) return
  importing.value = true
  try {
    const res = await tpApi.naumenImport(file)
    toastOk(`Импортировано заявок: ${res.count}`)
    await load()
  } catch (err) {
    toastError(err.message)
  } finally {
    importing.value = false
    e.target.value = ''
  }
}

watch([quick, year, org], async () => { await load() })

let themeObserver = null
onMounted(async () => {
  await load()
  themeObserver = new MutationObserver(async () => { await nextTick(); renderAll() })
  themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme', 'style'] })
})
onUnmounted(() => { Object.values(charts).forEach(c => c.destroy()); themeObserver?.disconnect() })
</script>

<style scoped>
.tp-head{display:flex;gap:var(--sp6);align-items:flex-start;justify-content:space-between;flex-wrap:wrap;margin-bottom:var(--sp6);}
.tp-head-l{min-width:260px;}
.tp-title{font-size:1.25rem;font-weight:700;letter-spacing:-.02em;}
.tp-sub{font-size:.8125rem;color:var(--c-muted);margin-top:2px;}
.tp-filters{background:var(--c-surf2);border:1px solid var(--c-brd);border-radius:var(--r3);padding:var(--sp4) var(--sp5);box-shadow:var(--sh1);display:flex;flex-direction:column;gap:var(--sp3);min-width:340px;flex:1;max-width:640px;}
.tp-f-row{display:flex;flex-direction:column;gap:var(--sp1);}
.tp-f-controls{flex-direction:row;gap:var(--sp3);align-items:flex-end;flex-wrap:wrap;}
.tp-f-col{display:flex;flex-direction:column;gap:var(--sp1);min-width:150px;flex:1;}
.tp-f-col .fsel{width:100%;}
.tp-f-bottom{display:flex;justify-content:space-between;align-items:center;gap:var(--sp3);}
.tp-f-meta{font-size:.75rem;color:var(--c-faint);}
.chip-row{display:flex;flex-wrap:wrap;gap:6px;}
.chip{padding:4px 10px;border-radius:99px;border:1px solid var(--c-div);background:var(--c-surf2);font-size:.75rem;cursor:pointer;transition:all .15s;user-select:none;color:var(--c-muted);font-weight:500;}
.chip.active{background:var(--c-red);color:#fff;border-color:var(--c-red);}
.chip:hover:not(.active){background:var(--c-off);color:var(--c-txt);}
.tp-section{font-size:1.0625rem;font-weight:700;letter-spacing:-.01em;margin:var(--sp8) 0 var(--sp4);display:flex;align-items:center;gap:var(--sp3);}
.tp-section:first-of-type{margin-top:0;}
.tp-tag{font-size:.6875rem;font-weight:600;color:var(--c-muted);background:var(--c-off);padding:3px 10px;border-radius:99px;text-transform:uppercase;letter-spacing:.04em;}
.tp-tall{height:330px;}
.tp-badge-mid{background:var(--c-warn-l);color:var(--c-warn);}
.tp-badge-mid::before{background:var(--c-warn);}
.tscroll{max-height:520px;overflow-y:auto;}
@media(max-width:1100px){.tp-head{flex-direction:column;}.tp-filters{max-width:100%;}}
</style>
