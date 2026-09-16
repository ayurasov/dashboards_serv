<template>
  <div v-if="loading" class="tempty">Загрузка…</div>
  <div v-else class="tp-dash">

    <!-- Page header + filters block (top-right) -->
    <div class="tp-head">
      <div class="tp-head-l">
        <h1 class="tp-title">Отчёт технической поддержки по неделям</h1>
        <div class="tp-sub">Заявки, трудозатраты по клиентам, AlterOS / AlterOffice / Project Server · {{ yearsLabel }}</div>
        <div v-if="clientInfo" class="tp-client-note">
          Активен фильтр по клиенту: {{ clientInfo.label }} — влияет на все графики и таблицу ниже
        </div>
      </div>

      <div class="tp-filters">
        <div class="tp-f-row">
          <span class="fl">Быстрый период</span>
          <div class="chip-row">
            <span v-for="q in QUICK" :key="q.v" class="chip" :class="{ active: quick === q.v }"
                  @click="applyQuick(q.v)">{{ q.label }}</span>
          </div>
        </div>
        <div class="tp-f-row">
          <span class="fl">Годы</span>
          <div class="chip-row">
            <span v-for="y in years" :key="y" class="chip" :class="{ active: activeYears.includes(y) }"
                  @click="toggleYear(y)">{{ y }}</span>
          </div>
        </div>
        <div class="tp-f-row tp-f-controls">
          <div class="tp-f-col">
            <span class="fl">Неделя с</span>
            <select class="fsel" v-model.number="weekFrom" @change="clearQuick"><option v-for="w in weeks" :key="w" :value="w">{{ w }}</option></select>
          </div>
          <div class="tp-f-col">
            <span class="fl">по</span>
            <select class="fsel" v-model.number="weekTo" @change="clearQuick"><option v-for="w in weeks" :key="w" :value="w">{{ w }}</option></select>
          </div>
          <div class="tp-f-col">
            <span class="fl">Клиент</span>
            <select class="fsel" v-model="clientKey">
              <option value="none">Все клиенты</option>
              <option v-for="c in CLIENTS" :key="c.key" :value="c.key">{{ c.label }}</option>
            </select>
          </div>
          <div class="tp-f-col">
            <span class="fl">Метрика тренда</span>
            <select class="fsel" v-model="trendMetric">
              <option v-for="(label, key) in METRIC_LABELS" :key="key" :value="key">{{ label }}</option>
            </select>
          </div>
        </div>
        <div class="tp-f-bottom">
          <div class="tp-f-meta">{{ filtered.length }} строк выбрано</div>
          <button class="btn btn-g" @click="resetFilters">Сбросить</button>
        </div>

        <details v-if="canEdit" class="tp-blocks">
          <summary>Блоки дашборда</summary>
          <div class="tp-blocks-list">
            <label v-for="b in BLOCKS" :key="b.key" class="tp-block-toggle">
              <input type="checkbox" v-model="blockSettings[b.key]" @change="saveBlocks">
              <span>{{ b.label }}</span>
            </label>
          </div>
        </details>
      </div>
    </div>

    <!-- Traffic light -->
    <template v-if="blockSettings.traffic">
      <div class="tp-section">Светофор <span class="tp-tag">контроль метрик выбранного периода</span></div>
      <div v-if="!trafficCards.length" class="tempty">Нет данных для оценки светофора за выбранный период</div>
      <div v-else class="tp-traffic-grid">
        <div v-for="c in trafficCards" :key="c.key" class="ccard tp-traffic-card">
          <div class="tp-traffic-head">
            <div>
              <div class="tp-traffic-title">{{ c.label }}</div>
              <div class="tp-traffic-value">{{ c.val }}</div>
            </div>
            <span class="light-dot" :class="'light-' + c.status"></span>
          </div>
          <div v-if="c.delta" class="tp-kpi-delta" :class="c.delta.cls">{{ c.delta.text }}</div>
          <span class="sb" :class="c.badgeClass">{{ c.stateLabel }}</span>
        </div>
      </div>
    </template>

    <!-- Trends -->
    <template v-if="blockSettings.trends">
      <div class="tp-section">Динамика и структура заявок</div>
      <div class="cgrid-2">
        <div class="ccard"><div class="ctitle">Динамика по неделям <span class="td-muted">{{ METRIC_LABELS[trendMetric] }}</span></div><div class="chart-box tp-tall"><canvas ref="cTrend"></canvas></div></div>
        <div class="ccard"><div class="ctitle">{{ pieTitle }}</div><div class="chart-box tp-tall"><canvas ref="cPie"></canvas></div></div>
      </div>
      <div class="cgrid-2">
        <div class="ccard"><div class="ctitle">{{ stackTitle }}</div><div class="chart-box tp-tall"><canvas ref="cStack"></canvas></div></div>
        <div class="ccard">
          <div class="ctitle">Топ недель выбранного клиента <span class="td-muted">{{ clientTopSub }}</span></div>
          <div class="chart-box tp-tall"><canvas ref="cTop"></canvas></div>
        </div>
      </div>
      <div class="cgrid">
        <div class="ccard"><div class="ctitle">Принято vs Решено</div><div class="chart-box"><canvas ref="cRs"></canvas></div></div>
        <div class="ccard"><div class="ctitle">Коэффициент решаемости</div><div class="chart-box"><canvas ref="cRatio"></canvas></div></div>
        <div class="ccard"><div class="ctitle">В работе (динамика остатка)</div><div class="chart-box"><canvas ref="cInwork"></canvas></div></div>
      </div>
    </template>

    <!-- AlterOS -->
    <template v-if="blockSettings.altos">
      <div class="tp-section">AlterOS <span class="tp-tag">линии поддержки</span></div>
      <div class="cgrid">
        <div class="ccard"><div class="ctitle">Заявки: 1-2 линия vs 3 линия</div><div class="chart-box"><canvas ref="cAltos"></canvas></div></div>
        <div class="ccard"><div class="ctitle">Среднее время решения, ч</div><div class="chart-box"><canvas ref="cAltosAvg"></canvas></div></div>
        <div class="ccard"><div class="ctitle">Доступность по срокам, ч</div><div class="chart-box"><canvas ref="cAltosAvail"></canvas></div></div>
      </div>
    </template>

    <!-- AlterOffice -->
    <template v-if="blockSettings.altoffice">
      <div class="tp-section">AlterOffice <span class="tp-tag">линии поддержки</span></div>
      <div class="cgrid">
        <div class="ccard"><div class="ctitle">Заявки: 1-2 линия vs 3 линия</div><div class="chart-box"><canvas ref="cAltoffice"></canvas></div></div>
        <div class="ccard"><div class="ctitle">Среднее время решения, ч</div><div class="chart-box"><canvas ref="cAltofficeAvg"></canvas></div></div>
        <div class="ccard"><div class="ctitle">Доступность по срокам, ч</div><div class="chart-box"><canvas ref="cAltofficeAvail"></canvas></div></div>
      </div>
    </template>

    <!-- Channels -->
    <template v-if="blockSettings.channels">
      <div class="tp-section">Каналы обращений <span class="tp-tag">Email / ТФ, РусГидро / Прочие</span></div>
      <div class="cgrid">
        <div class="ccard"><div class="ctitle">AlterOS: обращения по каналам</div><div class="chart-box"><canvas ref="cAltosCh"></canvas></div></div>
        <div class="ccard"><div class="ctitle">AlterOffice: обращения по каналам</div><div class="chart-box"><canvas ref="cAltofficeCh"></canvas></div></div>
        <div class="ccard"><div class="ctitle">Способ обращения (доля)</div><div class="chart-box"><canvas ref="cChannelPie"></canvas></div></div>
      </div>
    </template>

    <!-- Project Server -->
    <template v-if="blockSettings.projserver">
      <div class="tp-section">Project Server</div>
      <div class="cgrid-2">
        <div class="ccard"><div class="ctitle">Принято vs Решено vs Доступно</div><div class="chart-box"><canvas ref="cProj"></canvas></div></div>
        <div class="ccard">
          <div class="ctitle">Сводка Project Server</div>
          <div class="kpi-grid" style="margin-bottom:0">
            <div v-for="k in projKpis" :key="k.label" class="kpi">
              <div class="kpi-lbl">{{ k.label }}</div>
              <div class="kpi-val">{{ k.val != null ? k.fmt(k.val) : '—' }}</div>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- Detailed table -->
    <template v-if="blockSettings.table">
      <div class="tp-section">Детальная таблица <span class="tp-tag">поиск, сортировка</span></div>
      <div class="twrap">
        <div class="tp-table-tools">
          <span class="td-muted">Клик по заголовку — сортировка. Пустые ячейки — нет данных за неделю. Цветные точки — статус светофора.</span>
          <input class="srch" style="max-width:220px" type="text" v-model="search" placeholder="Поиск, напр. 2025-24">
        </div>
        <div class="tscroll">
          <table>
            <thead>
              <tr>
                <th v-for="col in TABLE_COLS" :key="col.key" :class="sortClass(col.key)" @click="toggleSort(col.key)">{{ col.label }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in tableRows" :key="r.period" :class="{ 'tp-row-client': clientKey !== 'none' }">
                <td>{{ r.period }}</td>
                <td v-for="col in TABLE_COLS.slice(1)" :key="col.key">
                  <template v-if="col.dot && r.dots[col.key]">
                    <span class="td-traffic"><span class="td-dot" :class="r.dots[col.key]"></span>{{ r.cells[col.key] }}</span>
                  </template>
                  <template v-else>{{ r.cells[col.key] }}</template>
                </td>
              </tr>
              <tr v-if="tableRows.length" class="tp-total-row">
                <td>Итого ({{ tableRows.length }} нед.)</td>
                <td v-for="col in TABLE_COLS.slice(1)" :key="col.key">{{ totals[col.key] }}</td>
              </tr>
              <tr v-else><td :colspan="TABLE_COLS.length" class="tempty">Нет строк</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>

  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { tpApi } from '../../api/tp.js'
import { useAuthStore } from '../../stores/auth.js'
import Chart from 'chart.js/auto'

const auth = useAuthStore()
const canEdit = computed(() => auth.isAdmin || auth.canEditService('tech'))

const loading = ref(true)
const RAW = ref([])

// ---------- filters ----------
const QUICK = [
  { v: '1',  label: 'Последняя неделя' },
  { v: '2',  label: '2 недели' },
  { v: '4',  label: 'Месяц' },
  { v: '8',  label: '8 недель' },
  { v: '13', label: '13 недель' },
  { v: '26', label: 'Полгода' },
  { v: 'all', label: 'Всё время' },
]
const quick = ref('all')
const activeYears = ref([])
const weekFrom = ref(1)
const weekTo = ref(53)
const clientKey = ref('none')
const trendMetric = ref('avail_total')
const search = ref('')

const CLIENTS = [
  { key: 'rushydro_hours', label: 'РусГидро', color: '--client-rushydro' },
  { key: 'transneft_hours', label: 'ТрансНефть', color: '--client-transneft' },
  { key: 'roscosmos_hours', label: 'Роскосмос', color: '--client-roscosmos' },
  { key: 'bryansk_hours', label: 'Брянск', color: '--client-bryansk' },
  { key: 'mchs_hours', label: 'МЧС', color: '--client-mchs' },
  { key: 'internal_sales_hours', label: 'Внутр.задачи+SALES', color: '--client-internal' },
]
const METRIC_LABELS = {
  total_in_work: 'Итого в работе заявок',
  avail_total: 'Трудозатраты всего доступно, ч',
  new_received: 'Принято новых заявок',
  total_solved_week: 'Решено за неделю',
  ratio_solved_received: 'Отношение решено/получено',
  altos_avg_time: 'AlterOS: среднее время решения, ч',
  altoffice_avg_time: 'AlterOffice: среднее время решения, ч',
}
const TRAFFIC_METRICS = [
  { key: 'total_in_work', label: 'Итого в работе' },
  { key: 'avail_total', label: 'Трудозатраты всего, ч' },
  { key: 'new_received', label: 'Принято новых заявок' },
  { key: 'total_solved_week', label: 'Решено за неделю' },
  { key: 'ratio_solved_received', label: 'Коэффициент решаемости' },
  { key: 'altos_avg_time', label: 'AlterOS ср. время, ч' },
  { key: 'altoffice_avg_time', label: 'AlterOffice ср. время, ч' },
  { key: 'altos_avail_total', label: 'AlterOS доступность, ч' },
  { key: 'altoffice_avail_total', label: 'AlterOffice доступность, ч' },
]
const BLOCKS = [
  { key: 'traffic', label: 'Светофор' },
  { key: 'trends', label: 'Динамика и структура заявок' },
  { key: 'altos', label: 'AlterOS' },
  { key: 'altoffice', label: 'AlterOffice' },
  { key: 'channels', label: 'Каналы обращений' },
  { key: 'projserver', label: 'Project Server' },
  { key: 'table', label: 'Детальная таблица' },
]
const TABLE_COLS = [
  { key: 'period', label: 'Период' },
  { key: 'total_in_work', label: 'В работе', dot: true },
  { key: 'avail_total', label: 'Трудозатраты, ч', dot: true },
  { key: 'new_received', label: 'Принято', dot: true },
  { key: 'total_solved_week', label: 'Решено', dot: true },
  { key: 'ratio_solved_received', label: 'Реш./Пол.', dot: true },
  { key: 'rushydro_hours', label: 'РусГидро, ч' },
  { key: 'transneft_hours', label: 'ТрансНефть, ч' },
  { key: 'roscosmos_hours', label: 'Роскосмос, ч' },
  { key: 'bryansk_hours', label: 'Брянск, ч' },
  { key: 'mchs_hours', label: 'МЧС, ч' },
  { key: 'internal_sales_hours', label: 'Внутр.+SALES, ч' },
  { key: 'altos_avg_time', label: 'AlterOS ср.вр,ч', dot: true },
  { key: 'altoffice_avg_time', label: 'AlterOffice ср.вр,ч', dot: true },
]

const trafficRules = ref({})
const blockSettings = ref(Object.fromEntries(BLOCKS.map(b => [b.key, true])))

const years = computed(() => [...new Set(RAW.value.map(d => d.year))].sort())
const weeks = computed(() => [...new Set(RAW.value.map(d => d.week))].sort((a, b) => a - b))
const yearsLabel = computed(() => {
  const ys = years.value
  return ys.length ? `${ys[0]}–${ys[ys.length - 1]}` : ''
})
const clientInfo = computed(() => CLIENTS.find(c => c.key === clientKey.value))

// ---------- filtering ----------
const filtered = computed(() => {
  if (quick.value !== 'all') {
    return RAW.value.slice(-parseInt(quick.value))
  }
  const ys = activeYears.value
  return RAW.value.filter(d => {
    if (!ys.includes(d.year)) return false
    if (ys.length === 1 && (d.week < weekFrom.value || d.week > weekTo.value)) return false
    return true
  })
})
const lastRow = computed(() => filtered.value.length ? filtered.value[filtered.value.length - 1] : null)

function applyQuick(v) {
  quick.value = v
  if (v === 'all') {
    activeYears.value = [...years.value]
    weekFrom.value = weeks.value[0]
    weekTo.value = weeks.value[weeks.value.length - 1]
  } else {
    const lastN = RAW.value.slice(-parseInt(v))
    activeYears.value = [...new Set(lastN.map(d => d.year))]
    weekFrom.value = lastN[0].week
    weekTo.value = lastN[lastN.length - 1].week
  }
}
function clearQuick() { if (quick.value !== 'all') quick.value = 'all' }
function toggleYear(y) {
  const i = activeYears.value.indexOf(y)
  if (i >= 0) activeYears.value.splice(i, 1)
  else activeYears.value.push(y)
  activeYears.value.sort()
  quick.value = 'all'
}
function resetFilters() {
  clientKey.value = 'none'
  search.value = ''
  trendMetric.value = 'avail_total'
  applyQuick('all')
}

// ---------- helpers ----------
const sum = (arr, key) => arr.reduce((s, d) => s + (d[key] || 0), 0)
const avg = (arr, key) => {
  const vals = arr.map(d => d[key]).filter(v => v != null)
  return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null
}
const ru = v => Math.round(v).toLocaleString('ru-RU')

function css(v) { return getComputedStyle(document.documentElement).getPropertyValue(v).trim() }

function evaluateTraffic(key, value) {
  const rule = trafficRules.value[key]
  if (!rule || !rule.enabled) return { status: 'gray', label: 'Отключено' }
  if (value == null) return { status: 'red', label: 'Нет данных' }
  const g = Number(rule.green), y = Number(rule.yellow)
  if (rule.direction === 'less') {
    if (value <= g) return { status: 'green', label: 'Норма' }
    if (value <= y) return { status: 'yellow', label: 'Внимание' }
    return { status: 'red', label: 'Критично' }
  }
  if (value >= g) return { status: 'green', label: 'Норма' }
  if (value >= y) return { status: 'yellow', label: 'Внимание' }
  return { status: 'red', label: 'Критично' }
}

const projKpis = computed(() => {
  const f = filtered.value
  if (!f.length) return []
  const withAvail = f.filter(d => d.projserver_avail != null)
  return [
    { label: 'Принято заявок', val: sum(f, 'projserver_taken'), fmt: ru },
    { label: 'Решено заявок', val: sum(f, 'projserver_solved'), fmt: ru },
    { label: 'Доступно, посл. неделя', val: withAvail.length ? withAvail[withAvail.length - 1].projserver_avail : null, fmt: Math.round },
  ]
})

// ---------- traffic cards ----------
// Sum metrics aggregate over the interval (thresholds scale with its length);
// the rest are level/ratio metrics averaged over the interval.
const AVG_METRICS = new Set(['total_in_work', 'ratio_solved_received', 'altos_avg_time', 'altoffice_avg_time'])

// Rows of the currently selected interval (what the charts show).
function intervalRows() {
  if (quick.value !== 'all') return RAW.value.slice(-parseInt(quick.value))
  return filtered.value
}

// Delta vs the previous interval of the same length:
// quick = N weeks  → last N rows vs the N rows before them
// quick = all      → second half of the selection vs the first half
function intervalDelta(key) {
  const f = filtered.value
  if (!f.length) return null
  let nowRows, prevRows, suffix
  if (quick.value !== 'all') {
    const n = parseInt(quick.value)
    nowRows = RAW.value.slice(-n)
    prevRows = RAW.value.length > n ? RAW.value.slice(-2 * n, -n) : []
    suffix = 'к пред. периоду'
  } else {
    const half = Math.max(1, Math.floor(f.length / 2))
    prevRows = f.slice(0, half)
    nowRows = f.slice(half)
    suffix = 'ко 1-й половине периода'
  }
  const agg = rows => rows.length ? (AVG_METRICS.has(key) ? avg(rows, key) : sum(rows, key)) : null
  const a = agg(prevRows), b = agg(nowRows)
  if (a == null || b == null || a === 0) return null
  const pct = ((b - a) / Math.abs(a)) * 100
  const cls = pct > 3 ? 'up' : pct < -3 ? 'down' : 'flat'
  const arrow = pct > 3 ? '▲' : pct < -3 ? '▼' : '—'
  return { cls, text: `${arrow} ${Math.abs(pct).toFixed(1)}% ${suffix}` }
}

// Traffic evaluation on interval-aggregated values: sum-metric thresholds
// are multiplied by the interval length (in weeks) for the comparison.
function evaluateTrafficScaled(key, value, factor) {
  const rule = trafficRules.value[key]
  if (!rule || !rule.enabled) return { status: 'gray', label: 'Отключено' }
  if (value == null) return { status: 'red', label: 'Нет данных' }
  const g = Number(rule.green) * factor
  const y = Number(rule.yellow) * factor
  if (rule.direction === 'less') {
    if (value <= g) return { status: 'green', label: 'Норма' }
    if (value <= y) return { status: 'yellow', label: 'Внимание' }
    return { status: 'red', label: 'Критично' }
  }
  if (value >= g) return { status: 'green', label: 'Норма' }
  if (value >= y) return { status: 'yellow', label: 'Внимание' }
  return { status: 'red', label: 'Критично' }
}

const trafficCards = computed(() => {
  const rows = intervalRows()
  if (!rows.length) return []
  const n = rows.length
  return TRAFFIC_METRICS
    .filter(m => trafficRules.value[m.key]?.enabled)
    .map(m => {
      const isSum = !AVG_METRICS.has(m.key)
      const vals = rows.map(d => d[m.key]).filter(v => v != null)
      const value = vals.length ? (isSum ? vals.reduce((a, b) => a + b, 0) : vals.reduce((a, b) => a + b, 0) / vals.length) : null
      const st = evaluateTrafficScaled(m.key, value, isSum ? n : 1)
      return {
        key: m.key,
        label: m.label,
        val: value == null ? '—' : (m.key === 'ratio_solved_received' ? Number(value).toFixed(2) : Number(value).toLocaleString('ru-RU', { maximumFractionDigits: 2 })),
        status: st.status,
        stateLabel: st.label,
        badgeClass: st.status === 'green' ? 's-hired' : st.status === 'yellow' ? 'tp-badge-mid' : 's-fired',
        delta: intervalDelta(m.key),
      }
    })
})

// ---------- table ----------
const sortKey = ref('period')
const sortDir = ref(1)
function toggleSort(key) {
  if (sortKey.value === key) sortDir.value *= -1
  else { sortKey.value = key; sortDir.value = 1 }
}
function sortClass(key) {
  if (sortKey.value !== key) return ''
  return sortDir.value === 1 ? 'tp-sorted-asc' : 'tp-sorted-desc'
}
const fmtCell = v => v == null ? '—' : (Number.isInteger(v) ? v : Number(v).toFixed(2))

const tableRows = computed(() => {
  let rows = filtered.value.filter(d => d.period.toLowerCase().includes(search.value.toLowerCase()))
  if (clientKey.value !== 'none') rows = rows.filter(d => d[clientKey.value] != null && d[clientKey.value] > 0)
  return rows.slice().sort((a, b) => {
    const av = a[sortKey.value], bv = b[sortKey.value]
    if (av == null && bv == null) return 0
    if (av == null) return 1
    if (bv == null) return -1
    if (typeof av === 'string') return av.localeCompare(bv) * sortDir.value
    return (av - bv) * sortDir.value
  }).map(d => {
    const cells = {}, dots = {}
    for (const col of TABLE_COLS.slice(1)) {
      cells[col.key] = col.key === 'ratio_solved_received' && d[col.key] != null
        ? Number(d[col.key]).toFixed(2) : fmtCell(d[col.key])
      if (col.dot) {
        const rule = trafficRules.value[col.key]
        if (rule && rule.enabled) dots[col.key] = evaluateTraffic(col.key, d[col.key]).status
      }
    }
    return { period: d.period, cells, dots }
  })
})
const totals = computed(() => {
  const rows = tableRows.value
  const src = filtered.value.filter(d => d.period.toLowerCase().includes(search.value.toLowerCase()) &&
    (clientKey.value === 'none' || (d[clientKey.value] != null && d[clientKey.value] > 0)))
  if (!rows.length) return {}
  const rAvg = avg(src, 'ratio_solved_received')
  const aoAvg = avg(src, 'altos_avg_time')
  const aofAvg = avg(src, 'altoffice_avg_time')
  return {
    total_in_work: fmtCell(avg(src, 'total_in_work')),
    avail_total: fmtCell(sum(src, 'avail_total')),
    new_received: fmtCell(sum(src, 'new_received')),
    total_solved_week: fmtCell(sum(src, 'total_solved_week')),
    ratio_solved_received: rAvg != null ? rAvg.toFixed(2) : '—',
    rushydro_hours: fmtCell(sum(src, 'rushydro_hours')),
    transneft_hours: fmtCell(sum(src, 'transneft_hours')),
    roscosmos_hours: fmtCell(sum(src, 'roscosmos_hours')),
    bryansk_hours: fmtCell(sum(src, 'bryansk_hours')),
    mchs_hours: fmtCell(sum(src, 'mchs_hours')),
    internal_sales_hours: fmtCell(sum(src, 'internal_sales_hours')),
    altos_avg_time: aoAvg != null ? aoAvg.toFixed(2) : '—',
    altoffice_avg_time: aofAvg != null ? aofAvg.toFixed(2) : '—',
  }
})

// ---------- charts ----------
const cTrend = ref(null), cPie = ref(null), cStack = ref(null), cTop = ref(null),
      cRs = ref(null), cRatio = ref(null), cInwork = ref(null),
      cAltos = ref(null), cAltoffice = ref(null), cAltosAvg = ref(null), cAltofficeAvg = ref(null),
      cAltosAvail = ref(null), cAltofficeAvail = ref(null),
      cAltosCh = ref(null), cAltofficeCh = ref(null), cChannelPie = ref(null), cProj = ref(null)

const charts = {}
function destroy(key) { if (charts[key]) { charts[key].destroy(); delete charts[key] } }
function destroyAll() { Object.keys(charts).forEach(destroy) }

function baseOptions(extra = {}) {
  const gridColor = css('--c-div')
  const textColor = css('--c-muted')
  return Object.assign({
    responsive: true, maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: { labels: { color: css('--c-txt'), boxWidth: 12, font: { size: 11 } } },
      tooltip: { titleColor: '#fff', bodyColor: '#fff' },
    },
    scales: {
      x: { grid: { color: gridColor }, ticks: { color: textColor, font: { size: 10 }, maxRotation: 0, autoSkip: true } },
      y: { grid: { color: gridColor }, ticks: { color: textColor, font: { size: 10 } } },
    },
  }, extra)
}
const xScale = () => ({ x: { grid: { display: false }, ticks: { color: css('--c-muted'), font: { size: 9 }, maxRotation: 0, autoSkip: true } }, y: { grid: { color: css('--c-div') }, ticks: { color: css('--c-muted') } } })
const stackedScale = () => ({ x: { stacked: true, grid: { display: false }, ticks: { color: css('--c-muted'), font: { size: 9 }, maxRotation: 0, autoSkip: true } }, y: { stacked: true, grid: { color: css('--c-div') }, ticks: { color: css('--c-muted') } } })

const pieTitle = computed(() => clientInfo.value
  ? `${clientInfo.value.label}: доля в общих трудозатратах`
  : 'Трудозатраты по клиентам, суммарно')
const stackTitle = computed(() => clientInfo.value
  ? `${clientInfo.value.label}: трудозатраты по неделям`
  : 'Трудозатраты по клиентам по неделям (стек)')
const clientTopSub = computed(() => clientInfo.value ? `Топ-15 недель: ${clientInfo.value.label}` : 'Выберите клиента в фильтре')

function pctLabels(labels, data, colors) {
  const total = data.reduce((a, b) => a + (b || 0), 0)
  return labels.map((label, i) => ({
    text: `${label} — ${total > 0 ? ((data[i] / total) * 100).toFixed(1) : '0.0'}%`,
    fillStyle: colors[i], strokeStyle: colors[i], index: i,
  }))
}

function mk(key, el, cfgFactory) {
  if (!el) return  // block hidden or canvas not mounted yet
  charts[key] = new Chart(el, cfgFactory())
}

function renderAll() {
  const f = filtered.value
  const labels = f.map(d => d.period)
  destroyAll()
  if (!f.length) return

  // Trend
  mk('trend', cTrend.value, () => ({
    type: 'line',
    data: { labels, datasets: [{
      label: METRIC_LABELS[trendMetric.value], data: f.map(d => d[trendMetric.value]),
      borderColor: css('--series-solved'), backgroundColor: css('--series-solved') + '22',
      fill: true, tension: 0.3, pointRadius: 2, spanGaps: true,
    }] },
    options: baseOptions({ plugins: { legend: { display: false }, tooltip: { titleColor: '#fff', bodyColor: '#fff' } } }),
  }))

  // Client pie
  if (clientInfo.value) {
    const clientSum = sum(f, clientInfo.value.key)
    const rest = Math.max(0, sum(f, 'avail_total') - clientSum)
    mk('pie', cPie.value, () => ({
      type: 'doughnut',
      data: { labels: [clientInfo.value.label, 'Остальные клиенты'], datasets: [{ data: [clientSum, rest], backgroundColor: [css(clientInfo.value.color), css('--c-div')], borderWidth: 0 }] },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom', labels: { color: css('--c-txt'), font: { size: 11 }, boxWidth: 12, generateLabels: c => pctLabels(c.data.labels, c.data.datasets[0].data, c.data.datasets[0].backgroundColor) } } } },
    }))
  } else {
    const values = CLIENTS.map(c => sum(f, c.key))
    const colors = CLIENTS.map(c => css(c.color))
    mk('pie', cPie.value, () => ({
      type: 'doughnut',
      data: { labels: CLIENTS.map(c => c.label), datasets: [{ data: values, backgroundColor: colors, borderWidth: 0 }] },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom', labels: { color: css('--c-txt'), font: { size: 11 }, boxWidth: 12, generateLabels: c => pctLabels(c.data.labels, c.data.datasets[0].data, c.data.datasets[0].backgroundColor) } } } },
    }))
  }

  // Client stack
  if (clientInfo.value) {
    mk('stack', cStack.value, () => ({
      type: 'bar',
      data: { labels, datasets: [{ label: clientInfo.value.label, data: f.map(d => d[clientInfo.value.key]), backgroundColor: css(clientInfo.value.color) }] },
      options: baseOptions({ scales: xScale() }),
    }))
  } else {
    mk('stack', cStack.value, () => ({
      type: 'bar',
      data: { labels, datasets: CLIENTS.map(c => ({ label: c.label, data: f.map(d => d[c.key]), backgroundColor: css(c.color), stack: 'clients' })) },
      options: baseOptions({ scales: stackedScale() }),
    }))
  }

  // Client top
  if (clientInfo.value) {
    const rows = f.filter(d => d[clientInfo.value.key] != null && d[clientInfo.value.key] > 0)
      .slice().sort((a, b) => b[clientInfo.value.key] - a[clientInfo.value.key]).slice(0, 15)
      .sort((a, b) => a.period.localeCompare(b.period))
    mk('top', cTop.value, () => ({
      type: 'bar',
      data: { labels: rows.map(d => d.period), datasets: [{ label: clientInfo.value.label, data: rows.map(d => d[clientInfo.value.key]), backgroundColor: css(clientInfo.value.color) }] },
      options: baseOptions({ scales: xScale() }),
    }))
  }

  // Received vs solved
  mk('rs', cRs.value, () => ({
    type: 'bar',
    data: { labels, datasets: [
      { label: 'Принято', data: f.map(d => d.new_received), backgroundColor: css('--series-received') },
      { label: 'Решено', data: f.map(d => d.total_solved_week), backgroundColor: css('--series-solved') },
    ] },
    options: baseOptions({ scales: xScale() }),
  }))

  // Ratio
  mk('ratio', cRatio.value, () => ({
    type: 'line',
    data: { labels, datasets: [{
      label: 'Решено/Получено', data: f.map(d => d.ratio_solved_received),
      borderColor: css('--c-ok'), backgroundColor: css('--c-ok') + '22', fill: true, tension: 0.3, pointRadius: 2, spanGaps: true,
    }] },
    options: baseOptions({ plugins: { legend: { display: false }, tooltip: { titleColor: '#fff', bodyColor: '#fff' } } }),
  }))

  // In work
  mk('inwork', cInwork.value, () => ({
    type: 'line',
    data: { labels, datasets: [{
      label: 'В работе', data: f.map(d => d.total_in_work),
      borderColor: css('--series-inwork'), backgroundColor: css('--series-inwork') + '22', fill: true, tension: 0.3, pointRadius: 2, spanGaps: true,
    }] },
    options: baseOptions({ plugins: { legend: { display: false }, tooltip: { titleColor: '#fff', bodyColor: '#fff' } } }),
  }))

  // AltOS / AltOffice lines
  const lines = (el, k12, k3, c12, c3) => el ? new Chart(el, {
    type: 'line',
    data: { labels, datasets: [
      { label: '1-2 линия', data: f.map(d => d[k12]), borderColor: css(c12), backgroundColor: 'transparent', tension: 0.3, pointRadius: 1, spanGaps: true },
      { label: '3 линия', data: f.map(d => d[k3]), borderColor: css(c3), backgroundColor: 'transparent', tension: 0.3, pointRadius: 1, spanGaps: true },
    ] },
    options: baseOptions(),
  }) : null
  charts.altos = lines(cAltos.value, 'altos_1_2line', 'altos_3line', '--series-altos-l12', '--series-altos-l3')
  charts.altoffice = lines(cAltoffice.value, 'altoffice_1_2line', 'altoffice_3line', '--series-altoffice-l12', '--series-altoffice-l3')

  // Avg time
  const avgTime = (el, key, color) => el ? new Chart(el, {
    type: 'line',
    data: { labels, datasets: [{
      label: 'Ср. время решения, ч', data: f.map(d => d[key]),
      borderColor: css(color), backgroundColor: css(color) + '22', fill: true, tension: 0.3, pointRadius: 1, spanGaps: true,
    }] },
    options: baseOptions({ plugins: { legend: { display: false }, tooltip: { titleColor: '#fff', bodyColor: '#fff' } } }),
  }) : null
  charts.altosAvg = avgTime(cAltosAvg.value, 'altos_avg_time', '--series-avgtime-altos')
  charts.altofficeAvg = avgTime(cAltofficeAvg.value, 'altoffice_avg_time', '--series-avgtime-altoffice')

  // Availability buckets
  const avail = (el, p) => el ? new Chart(el, {
    type: 'bar',
    data: { labels, datasets: [
      { label: '1-3 дня', data: f.map(d => d[p + '_1_3']), backgroundColor: css('--c-ok'), stack: 'a' },
      { label: '4-7 дней', data: f.map(d => d[p + '_4_7']), backgroundColor: css('--c-warn'), stack: 'a' },
      { label: '8-10 дней', data: f.map(d => d[p + '_8_10']), backgroundColor: css('--c-err'), stack: 'a' },
    ] },
    options: baseOptions({ scales: stackedScale() }),
  }) : null
  charts.altosAvail = avail(cAltosAvail.value, 'altos_avail')
  charts.altofficeAvail = avail(cAltofficeAvail.value, 'altoffice_avail')

  // Channels
  const channels = (el, p) => el ? new Chart(el, {
    type: 'bar',
    data: { labels, datasets: [
      { label: 'РусГидро Email', data: f.map(d => d[p + '_rusg_email']), backgroundColor: css('--client-rushydro'), stack: 'a' },
      { label: 'РусГидро ТФ', data: f.map(d => d[p + '_rusg_tf']), backgroundColor: css('--channel-rushydro-tf'), stack: 'a' },
      { label: 'Прочие Email', data: f.map(d => d[p + '_other_email']), backgroundColor: css('--client-transneft'), stack: 'a' },
      { label: 'Прочие ТФ', data: f.map(d => d[p + '_other_tf']), backgroundColor: css('--channel-other-tf'), stack: 'a' },
    ] },
    options: baseOptions({ scales: stackedScale() }),
  }) : null
  charts.altosCh = channels(cAltosCh.value, 'altos')
  charts.altofficeCh = channels(cAltofficeCh.value, 'altoffice')

  // Channel share doughnut (email vs phone vs cabinet — derived from report channels)
  const chVals = [
    sum(f, 'altos_rusg_email') + sum(f, 'altos_other_email') + sum(f, 'altoffice_rusg_email') + sum(f, 'altoffice_other_email'),
    sum(f, 'altos_rusg_tf') + sum(f, 'altos_other_tf') + sum(f, 'altoffice_rusg_tf') + sum(f, 'altoffice_other_tf'),
  ]
  mk('chPie', cChannelPie.value, () => ({
    type: 'doughnut',
    data: { labels: ['Email', 'Телефон (ТФ)'], datasets: [{ data: chVals, backgroundColor: [css('--client-transneft'), css('--channel-rushydro-tf')], borderWidth: 0 }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom', labels: { color: css('--c-txt'), font: { size: 11 }, boxWidth: 12, generateLabels: c => pctLabels(c.data.labels, c.data.datasets[0].data, c.data.datasets[0].backgroundColor) } } } },
  }))

  // Project Server
  mk('proj', cProj.value, () => ({
    type: 'bar',
    data: { labels, datasets: [
      { label: 'Принято', data: f.map(d => d.projserver_taken), backgroundColor: css('--series-received'), type: 'bar' },
      { label: 'Решено', data: f.map(d => d.projserver_solved), backgroundColor: css('--series-solved'), type: 'bar' },
      { label: 'Доступно', data: f.map(d => d.projserver_avail), borderColor: css('--series-proj-avail'), backgroundColor: 'transparent', type: 'line', tension: 0.3, pointRadius: 1, spanGaps: true, yAxisID: 'y1' },
    ] },
    options: baseOptions({
      scales: {
        x: { grid: { display: false }, ticks: { color: css('--c-muted'), font: { size: 9 }, maxRotation: 0, autoSkip: true } },
        y: { grid: { color: css('--c-div') }, ticks: { color: css('--c-muted') } },
        y1: { position: 'right', grid: { display: false }, ticks: { color: css('--c-muted') } },
      },
    }),
  }))
}

watch([filtered, trendMetric, clientKey, blockSettings], async () => { await nextTick(); renderAll() }, { deep: true })

let themeObserver = null

async function saveBlocks() {
  try { await tpApi.putSetting('block_settings', blockSettings.value) } catch {}
}

onMounted(async () => {
  try {
    const [rows, rules, blocks] = await Promise.all([
      tpApi.rows(), tpApi.getSetting('traffic_rules'), tpApi.getSetting('block_settings'),
    ])
    RAW.value = rows
      .filter(r => r.year != null && r.week != null)
      .map(r => ({ ...r, year: Math.round(r.year), week: Math.round(r.week) }))
      .sort((a, b) => a.year - b.year || a.week - b.week)
    trafficRules.value = rules || {}
    if (blocks && typeof blocks === 'object') {
      for (const b of BLOCKS) if (blocks[b.key] !== undefined) blockSettings.value[b.key] = !!blocks[b.key]
    }
    activeYears.value = [...years.value]
    weekFrom.value = weeks.value[0]
    weekTo.value = weeks.value[weeks.value.length - 1]
    loading.value = false
    await nextTick()
    renderAll()
    themeObserver = new MutationObserver(async () => { await nextTick(); renderAll() })
    themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme', 'style'] })
  } finally { loading.value = false }
})
onUnmounted(() => { destroyAll(); themeObserver?.disconnect() })
</script>

<style scoped>
.tp-dash{display:flex;flex-direction:column;}
.tp-head{display:flex;gap:var(--sp6);align-items:flex-start;justify-content:space-between;flex-wrap:wrap;margin-bottom:var(--sp6);}
.tp-head-l{min-width:260px;}
.tp-title{font-size:1.25rem;font-weight:700;letter-spacing:-.02em;}
.tp-sub{font-size:.8125rem;color:var(--c-muted);margin-top:2px;}
.tp-client-note{font-size:.8125rem;color:var(--c-red);font-weight:600;margin-top:var(--sp3);background:var(--c-red-l);padding:var(--sp2) var(--sp4);border-radius:var(--r2);display:inline-block;}
.tp-filters{background:var(--c-surf2);border:1px solid var(--c-brd);border-radius:var(--r3);padding:var(--sp4) var(--sp5);box-shadow:var(--sh1);display:flex;flex-direction:column;gap:var(--sp3);min-width:360px;flex:1;max-width:720px;}
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
.tp-kpi-delta{font-size:.75rem;font-weight:600;}
.tp-kpi-delta.up{color:var(--c-ok);}
.tp-kpi-delta.down{color:var(--c-err);}
.tp-kpi-delta.flat{color:var(--c-muted);}
.tp-tall{height:330px;}
.tp-traffic-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:var(--sp4);margin-bottom:var(--sp6);}
.tp-traffic-head{display:flex;align-items:flex-start;justify-content:space-between;gap:var(--sp3);margin-bottom:var(--sp3);}
.tp-traffic-title{font-weight:600;font-size:.8125rem;}
.tp-traffic-value{font-size:1.5rem;font-weight:700;font-variant-numeric:tabular-nums;line-height:1.15;}
.tp-traffic-meta{font-size:.75rem;color:var(--c-muted);}
.light-dot{width:14px;height:14px;margin-top:4px;}
.tp-badge-mid{background:var(--c-warn-l);color:var(--c-warn);}
.tp-badge-mid::before{background:var(--c-warn);}
.td-traffic{display:inline-flex;align-items:center;gap:6px;}
.td-dot{width:9px;height:9px;border-radius:50%;flex-shrink:0;display:inline-block;}
.td-dot.green{background:var(--c-ok);}
.td-dot.yellow{background:var(--c-warn);}
.td-dot.red{background:var(--c-err);}
.td-dot.gray{background:var(--c-faint);}
.tp-table-tools{display:flex;justify-content:space-between;align-items:center;gap:var(--sp3);padding:var(--sp3) var(--sp4);font-size:.75rem;flex-wrap:wrap;}
table thead th{cursor:pointer;user-select:none;white-space:nowrap;}
table thead th.tp-sorted-asc::after{content:' ▲';font-size:9px;}
table thead th.tp-sorted-desc::after{content:' ▼';font-size:9px;}
.tp-row-client td{background:color-mix(in oklab, var(--c-red) 6%, transparent);}
.tp-total-row td{position:sticky;bottom:0;background:var(--c-dyn);font-weight:700;border-top:2px solid var(--c-red);}
.tscroll{max-height:540px;overflow-y:auto;}
.tp-blocks{font-size:.8125rem;}
.tp-blocks summary{cursor:pointer;color:var(--c-muted);font-weight:600;}
.tp-blocks-list{display:flex;flex-wrap:wrap;gap:var(--sp3);margin-top:var(--sp2);}
.tp-block-toggle{display:inline-flex;align-items:center;gap:6px;font-size:.75rem;color:var(--c-muted);cursor:pointer;}
@media(max-width:1100px){.tp-head{flex-direction:column;}.tp-filters{max-width:100%;}}
</style>
