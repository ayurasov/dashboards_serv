<template>
  <div class="tp-dashboard">

    <!-- ===== TOP: title + filters ===== -->
    <div class="page-header">
      <div class="page-head-left">
        <h1 class="page-title">Техническая поддержка</h1>
        <p class="page-sub">Дашборд показателей ТП — недельные данные</p>
      </div>
      <div class="tp-filterbar">
        <div class="chip-row">
          <button v-for="q in quickPeriods" :key="q.val"
            class="qchip" :class="{active: quickPeriod===q.val}"
            type="button" @click="setQuickPeriod(q.val)">{{ q.label }}</button>
        </div>
        <select class="fsel" v-model="selectedYear" @change="onYearChange">
          <option :value="null">Все годы</option>
          <option v-for="y in years" :key="y" :value="y">{{ y }}</option>
        </select>
        <select class="fsel" v-model="selectedWeekFrom" @change="onManualFilter">
          <option value="">Неделя (c)</option>
          <option v-for="w in weeks" :key="w" :value="w">Неделя {{ w }}</option>
        </select>
        <select class="fsel" v-model="selectedWeekTo" @change="onManualFilter">
          <option value="">Неделя (по)</option>
          <option v-for="w in weeks" :key="w" :value="w">Неделя {{ w }}</option>
        </select>
        <select class="fsel" v-model="clientFilter">
          <option value="none">Все клиенты</option>
          <option v-for="c in CLIENTS" :key="c.key" :value="c.key">{{ c.label }}</option>
        </select>
        <select class="fsel" v-model="trendMetric">
          <option v-for="(label, key) in METRIC_LABELS" :key="key" :value="key">{{ label }}</option>
        </select>
        <button class="btn btn-g" type="button" @click="resetFilters">Сброс</button>
      </div>
    </div>

    <div v-if="loading" class="loading-state">Загрузка…</div>

    <template v-else>

      <!-- ===== KPI GRID ===== -->
      <div class="section-title">Ключевые показатели (KPI)</div>
      <div class="kpi-grid">
        <div v-for="m in KPI_METRICS" :key="m.key" class="kpi-card" :class="trafficClass(m.key, lastRow?.[m.key])">
          <div class="kpi-lbl">{{ m.label }}</div>
          <div class="kpi-val">{{ fmt(lastRow?.[m.key]) }}{{ m.unit ? ' '+m.unit : '' }}</div>
          <div class="kpi-sub">Период: {{ lastRow?.period ?? '—' }}</div>
        </div>
      </div>

      <!-- ===== TRAFFIC GRID ===== -->
      <div class="section-title">Светофор &mdash; контроль метриктекущей недели</div>
      <div class="traffic-grid">
        <div v-for="m in TRAFFIC_METRICS" :key="m.key" class="traffic-card">
          <div class="traffic-head">
            <div>
              <div class="traffic-title">{{ m.label }}</div>
              <div class="traffic-value">{{ fmt(lastRow?.[m.key]) }}{{ m.unit ? ' '+m.unit : '' }}</div>
              <div class="traffic-meta">Неделя: {{ lastRow?.period ?? '—' }}</div>
            </div>
            <span class="traffic-dot" :class="trafficStatus(m.key, lastRow?.[m.key])"></span>
          </div>
          <span class="badge" :class="'badge-'+trafficStatus(m.key, lastRow?.[m.key])">
            {{ trafficLabel(m.key, lastRow?.[m.key]) }}
          </span>
          <div class="traffic-meta" style="margin-top:10px;">
            Направление: {{ trafficRules[m.key]?.direction==='more' ? 'Больше — лучше' : 'Меньше — лучше' }}
            &middot; зелёный: {{ trafficRules[m.key]?.green ?? '—' }}
            &middot; жёлтый: {{ trafficRules[m.key]?.yellow ?? '—' }}
          </div>
        </div>
      </div>

      <!-- ===== SECTION: TRENDS ===== -->
      <div class="section-title">Динамика и структура заявок</div>
      <div class="cgrid-2">
        <div class="ccard">
          <div class="ctitle">Динамика по неделям <span class="csub">{{ METRIC_LABELS[trendMetric] }}</span></div>
          <div class="chart-wrap tall"><canvas ref="trendChart"></canvas></div>
        </div>
        <div class="ccard">
          <div class="ctitle">{{ clientFilter==='none' ? 'Трудозатраты по клиентам, суммарно' : clientLabel+': доля в общих трудозатратах' }}</div>
          <div class="chart-wrap tall"><canvas ref="clientPieChart"></canvas></div>
        </div>
      </div>
      <div class="cgrid-2">
        <div class="ccard">
          <div class="ctitle">{{ clientFilter==='none' ? 'Трудозатраты по клиентам (стек)' : clientLabel+': трудозатраты по неделям' }}</div>
          <div class="chart-wrap tall"><canvas ref="clientStackChart"></canvas></div>
        </div>
        <div class="ccard">
          <div class="ctitle">Топ недель выбранного клиента <span class="csub">{{ clientFilter==='none' ? '— выберите клиента' : clientLabel }}</span></div>
          <div class="chart-wrap tall"><canvas ref="clientTopChart"></canvas></div>
        </div>
      </div>
      <div class="cgrid">
        <div class="ccard">
          <div class="ctitle">Принято vs Решено</div>
          <div class="chart-wrap"><canvas ref="rsChart"></canvas></div>
        </div>
        <div class="ccard">
          <div class="ctitle">Коэффициент решаемости</div>
          <div class="chart-wrap"><canvas ref="ratioChart"></canvas></div>
        </div>
        <div class="ccard">
          <div class="ctitle">В работе (динамика остатка)</div>
          <div class="chart-wrap"><canvas ref="inworkChart"></canvas></div>
        </div>
      </div>

      <!-- ===== AlterOS ===== -->
      <div class="section-title">AlterOS <span class="section-tag">линии поддержки</span></div>
      <div class="cgrid">
        <div class="ccard">
          <div class="ctitle">Заявки: 1-2 линия vs 3 линия</div>
          <div class="chart-wrap"><canvas ref="altosChart"></canvas></div>
        </div>
        <div class="ccard">
          <div class="ctitle">Среднее время решения, ч</div>
          <div class="chart-wrap"><canvas ref="altosAvgChart"></canvas></div>
        </div>
        <div class="ccard">
          <div class="ctitle">Доступность по срокам, ч</div>
          <div class="chart-wrap"><canvas ref="altosAvailChart"></canvas></div>
        </div>
      </div>

      <!-- ===== AlterOffice ===== -->
      <div class="section-title">AlterOffice <span class="section-tag">линии поддержки</span></div>
      <div class="cgrid">
        <div class="ccard">
          <div class="ctitle">Заявки: 1-2 линия vs 3 линия</div>
          <div class="chart-wrap"><canvas ref="altofficeChart"></canvas></div>
        </div>
        <div class="ccard">
          <div class="ctitle">Среднее время решения, ч</div>
          <div class="chart-wrap"><canvas ref="altofficeAvgChart"></canvas></div>
        </div>
        <div class="ccard">
          <div class="ctitle">Доступность по срокам, ч</div>
          <div class="chart-wrap"><canvas ref="altofficeAvailChart"></canvas></div>
        </div>
      </div>

      <!-- ===== Channels ===== -->
      <div class="section-title">Каналы обращений <span class="section-tag">Email / ТФ, РусГидро / Прочие</span></div>
      <div class="cgrid-2">
        <div class="ccard">
          <div class="ctitle">AlterOS: обращения по каналам</div>
          <div class="chart-wrap"><canvas ref="altosChannelsChart"></canvas></div>
        </div>
        <div class="ccard">
          <div class="ctitle">AlterOffice: обращения по каналам</div>
          <div class="chart-wrap"><canvas ref="altofficeChannelsChart"></canvas></div>
        </div>
      </div>

      <!-- ===== Project Server ===== -->
      <div class="section-title">Project Server</div>
      <div class="cgrid-2">
        <div class="ccard">
          <div class="ctitle">Принято vs Решено vs Доступно</div>
          <div class="chart-wrap"><canvas ref="projserverChart"></canvas></div>
        </div>
        <div class="ccard">
          <div class="ctitle">Сводка Project Server</div>
          <div class="kpi-grid" style="margin-bottom:0;">
            <div class="kpi-card light-gray">
              <div class="kpi-lbl">Принято</div>
              <div class="kpi-val">{{ fmt(lastRow?.projserver_taken) }}</div>
            </div>
            <div class="kpi-card light-gray">
              <div class="kpi-lbl">Решено</div>
              <div class="kpi-val">{{ fmt(lastRow?.projserver_solved) }}</div>
            </div>
            <div class="kpi-card light-gray">
              <div class="kpi-lbl">Доступно</div>
              <div class="kpi-val">{{ fmt(lastRow?.projserver_avail) }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- ===== DETAIL TABLE ===== -->
      <div class="section-title">Детальная таблица <span class="section-tag">поиск, сортировка</span></div>
      <div class="ccard">
        <div class="ctitle" style="justify-content:space-between;">
          <span>Детальная таблица по неделям</span>
          <input v-model="tableSearch" class="srch" placeholder="Поиск: 2025-24" style="max-width:200px;">
        </div>
        <div class="tscroll">
          <table>
            <thead>
              <tr>
                <th @click="sortBy('period')">Период {{ sortIcon('period') }}</th>
                <th @click="sortBy('total_in_work')">В работе {{ sortIcon('total_in_work') }}</th>
                <th @click="sortBy('avail_total')">Трудозатраты, ч {{ sortIcon('avail_total') }}</th>
                <th @click="sortBy('new_received')">Принято {{ sortIcon('new_received') }}</th>
                <th @click="sortBy('total_solved_week')">Решено {{ sortIcon('total_solved_week') }}</th>
                <th @click="sortBy('ratio_solved_received')">Реш./Пол. {{ sortIcon('ratio_solved_received') }}</th>
                <th @click="sortBy('rushydro_hours')">РусГидро, ч {{ sortIcon('rushydro_hours') }}</th>
                <th @click="sortBy('transneft_hours')">ТрансНефть, ч {{ sortIcon('transneft_hours') }}</th>
                <th @click="sortBy('roscosmos_hours')">Роскосмос, ч {{ sortIcon('roscosmos_hours') }}</th>
                <th @click="sortBy('bryansk_hours')">Брянск, ч {{ sortIcon('bryansk_hours') }}</th>
                <th @click="sortBy('mchs_hours')">МЧС, ч {{ sortIcon('mchs_hours') }}</th>
                <th @click="sortBy('internal_sales_hours')">Внутр.+SALES, ч {{ sortIcon('internal_sales_hours') }}</th>
                <th @click="sortBy('altos_avg_time')">AltOS ср.вр, ч {{ sortIcon('altos_avg_time') }}</th>
                <th @click="sortBy('altoffice_avg_time')">AltOff ср.вр, ч {{ sortIcon('altoffice_avg_time') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!tableRows.length">
                <td colspan="14" class="tempty">Нет данных</td>
              </tr>
              <tr v-for="row in tableRows" :key="row.period"
                :style="clientFilter!=='none' ? 'background:color-mix(in oklab, var(--c-red) 8%, transparent)' : ''">
                <td class="td-p">{{ row.period }}</td>
                <td><span class="td-dot" :class="trafficStatus('total_in_work', row.total_in_work)"></span>{{ fmt(row.total_in_work) }}</td>
                <td><span class="td-dot" :class="trafficStatus('avail_total', row.avail_total)"></span>{{ fmt(row.avail_total) }}</td>
                <td><span class="td-dot" :class="trafficStatus('new_received', row.new_received)"></span>{{ fmt(row.new_received) }}</td>
                <td><span class="td-dot" :class="trafficStatus('total_solved_week', row.total_solved_week)"></span>{{ fmt(row.total_solved_week) }}</td>
                <td>
                  <span v-if="row.ratio_solved_received!=null"
                    class="badge"
                    :class="row.ratio_solved_received>=1 ? 'badge-green' : row.ratio_solved_received>=0.7 ? 'badge-yellow' : 'badge-red'">
                    {{ row.ratio_solved_received.toFixed(2) }}
                  </span>
                  <span v-else>—</span>
                </td>
                <td>{{ fmt(row.rushydro_hours) }}</td>
                <td>{{ fmt(row.transneft_hours) }}</td>
                <td>{{ fmt(row.roscosmos_hours) }}</td>
                <td>{{ fmt(row.bryansk_hours) }}</td>
                <td>{{ fmt(row.mchs_hours) }}</td>
                <td>{{ fmt(row.internal_sales_hours) }}</td>
                <td><span class="td-dot" :class="trafficStatus('altos_avg_time', row.altos_avg_time)"></span>{{ fmt(row.altos_avg_time) }}</td>
                <td><span class="td-dot" :class="trafficStatus('altoffice_avg_time', row.altoffice_avg_time)"></span>{{ fmt(row.altoffice_avg_time) }}</td>
              </tr>
              <!-- TOTAL ROW -->
              <tr v-if="tableRows.length" class="total-row">
                <td class="td-p">Итого ({{ tableRows.length }} нед.)</td>
                <td>{{ fmtDec(avg(tableRows,'total_in_work')) }}</td>
                <td>{{ fmt(sumf(tableRows,'avail_total')) }}</td>
                <td>{{ fmt(sumf(tableRows,'new_received')) }}</td>
                <td>{{ fmt(sumf(tableRows,'total_solved_week')) }}</td>
                <td>{{ fmtDec(avg(tableRows,'ratio_solved_received'),2) }}</td>
                <td>{{ fmt(sumf(tableRows,'rushydro_hours')) }}</td>
                <td>{{ fmt(sumf(tableRows,'transneft_hours')) }}</td>
                <td>{{ fmt(sumf(tableRows,'roscosmos_hours')) }}</td>
                <td>{{ fmt(sumf(tableRows,'bryansk_hours')) }}</td>
                <td>{{ fmt(sumf(tableRows,'mchs_hours')) }}</td>
                <td>{{ fmt(sumf(tableRows,'internal_sales_hours')) }}</td>
                <td>{{ fmtDec(avg(tableRows,'altos_avg_time')) }}</td>
                <td>{{ fmtDec(avg(tableRows,'altoffice_avg_time')) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="legend-note">
          Пустые ячейки — отсутствие данных за неделю. Цветные точки — статус светофора.
        </div>
      </div>

    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, nextTick, onBeforeUnmount } from 'vue'
import { tpApi } from '../../api/tp.js'
import Chart from 'chart.js/auto'

// ── Data & filter state ───────────────────────────────────────────────────────
const rows       = ref([])
const trafficRules = ref({})
const loading    = ref(false)
const quickPeriod = ref('all')
const selectedYear = ref(null)
const selectedWeekFrom = ref('')
const selectedWeekTo   = ref('')
const clientFilter = ref('none')
const trendMetric = ref('total_in_work')
const tableSearch = ref('')
const sortKey = ref('period')
const sortDir = ref(-1)   // -1 = desc by default

// ── Constants ─────────────────────────────────────────────────────────────────
const CLIENTS = [
  { key:'rushydro_hours',       label:'РусГидро',        color:'#f5a351' },
  { key:'transneft_hours',      label:'ТрансНефть',     color:'#14549c' },
  { key:'roscosmos_hours',      label:'Роскосмос',      color:'#ed1941' },
  { key:'bryansk_hours',        label:'Брянск',          color:'#8b1e3f' },
  { key:'mchs_hours',           label:'МЧС',             color:'#1f88c9' },
  { key:'internal_sales_hours', label:'Внутренние+SALES', color:'#6f7b8a' },
]
const METRIC_LABELS = {
  total_in_work:          'В работе',
  avail_total:            'Трудозатраты, ч',
  new_received:           'Принято',
  total_solved_week:      'Решено за неделю',
  ratio_solved_received:  'Коэф. решаемости',
  altos_avg_time:         'AlterOS ср. время, ч',
  altoffice_avg_time:     'AlterOffice ср. время, ч',
}
const KPI_METRICS = [
  { key:'total_in_work',         label:'В работе' },
  { key:'avail_total',           label:'Трудозатраты', unit:'ч' },
  { key:'new_received',          label:'Принято' },
  { key:'total_solved_week',     label:'Решено' },
  { key:'ratio_solved_received', label:'Коэф. решаемости' },
  { key:'altos_avg_time',        label:'AlterOS ср.вр, ч' },
  { key:'altoffice_avg_time',    label:'AlterOffice ср.вр, ч' },
  { key:'renewed',               label:'Возобновлено' },
]
const TRAFFIC_METRICS = [
  { key:'total_in_work',         label:'Заявок в работе' },
  { key:'avail_total',           label:'Трудозатраты', unit:'ч' },
  { key:'new_received',          label:'Принято за неделю' },
  { key:'total_solved_week',     label:'Решено за неделю' },
  { key:'ratio_solved_received', label:'Коэф. решаемости' },
  { key:'altos_avg_time',        label:'AlterOS ср. время, ч' },
  { key:'altoffice_avg_time',    label:'AlterOffice ср. время, ч' },
]
const quickPeriods = [
  { label:'2 нед.', val:2 },
  { label:'Месяц', val:4 },
  { label:'8 нед.', val:8 },
  { label:'13 нед.', val:13 },
  { label:'Полгода', val:26 },
  { label:'Всё', val:'all' },
]

// ── Canvas refs ───────────────────────────────────────────────────────────────
const trendChart         = ref(null)
const clientPieChart     = ref(null)
const clientStackChart   = ref(null)
const clientTopChart     = ref(null)
const rsChart            = ref(null)
const ratioChart         = ref(null)
const inworkChart        = ref(null)
const altosChart         = ref(null)
const altosAvgChart      = ref(null)
const altosAvailChart    = ref(null)
const altofficeChart     = ref(null)
const altofficeAvgChart  = ref(null)
const altofficeAvailChart = ref(null)
const altosChannelsChart  = ref(null)
const altofficeChannelsChart = ref(null)
const projserverChart    = ref(null)

let charts = {}

// ── Derived ───────────────────────────────────────────────────────────────────
const years = computed(() => [...new Set(rows.value.map(r => r.year))].sort((a,b)=>a-b))
const weeks = computed(() => {
  const base = selectedYear.value
    ? rows.value.filter(r => r.year === selectedYear.value)
    : rows.value
  return [...new Set(base.map(r => r.week))].sort((a,b)=>a-b)
})

const sorted = computed(() =>
  [...rows.value].sort((a,b) => a.year-b.year || a.week-b.week)
)

const filtered = computed(() => {
  let r = sorted.value
  if (selectedYear.value)    r = r.filter(x => x.year === selectedYear.value)
  if (selectedWeekFrom.value !== '') r = r.filter(x => x.week >= Number(selectedWeekFrom.value))
  if (selectedWeekTo.value   !== '') r = r.filter(x => x.week <= Number(selectedWeekTo.value))
  if (quickPeriod.value !== 'all' && quickPeriod.value !== 'custom') r = r.slice(-quickPeriod.value)
  return r
})

const lastRow = computed(() => filtered.value[filtered.value.length - 1] ?? null)

const clientLabel = computed(() =>
  CLIENTS.find(c => c.key === clientFilter.value)?.label ?? ''
)

const tableRows = computed(() => {
  const s = tableSearch.value.toLowerCase()
  let r = filtered.value.filter(d => d.period?.toLowerCase().includes(s))
  if (clientFilter.value !== 'none') r = r.filter(d => d[clientFilter.value] != null && d[clientFilter.value] > 0)
  return [...r].sort((a,b) => {
    const av = a[sortKey.value], bv = b[sortKey.value]
    if (av == null && bv == null) return 0
    if (av == null) return 1
    if (bv == null) return -1
    return typeof av === 'string'
      ? av.localeCompare(bv) * sortDir.value
      : (av - bv) * sortDir.value
  })
})

// ── Traffic helpers ───────────────────────────────────────────────────────────
const DEFAULT_RULES = {
  total_in_work:         { direction:'less', green:80,   yellow:120,  enabled:true },
  avail_total:           { direction:'more', green:200,  yellow:120,  enabled:true },
  new_received:          { direction:'less', green:60,   yellow:100,  enabled:true },
  total_solved_week:     { direction:'more', green:60,   yellow:40,   enabled:true },
  ratio_solved_received: { direction:'more', green:1,    yellow:0.7,  enabled:true },
  altos_avg_time:        { direction:'less', green:8,    yellow:12,   enabled:true },
  altoffice_avg_time:    { direction:'less', green:8,    yellow:12,   enabled:true },
}

function getRule(key) {
  return trafficRules.value[key] ?? DEFAULT_RULES[key]
}

function trafficStatus(key, value) {
  const rule = getRule(key)
  if (!rule?.enabled || value == null) return 'gray'
  const v = Number(value)
  if (rule.direction === 'more') {
    if (v >= rule.green) return 'green'
    if (v >= rule.yellow) return 'yellow'
    return 'red'
  } else {
    if (v <= rule.green) return 'green'
    if (v <= rule.yellow) return 'yellow'
    return 'red'
  }
}

function trafficLabel(key, value) {
  const s = trafficStatus(key, value)
  return s === 'green' ? 'Норма' : s === 'yellow' ? 'Умеренно' : s === 'red' ? 'Критично' : '—'
}

function trafficClass(key, value) {
  return 'light-' + trafficStatus(key, value)
}

// ── Formatting ────────────────────────────────────────────────────────────────
function fmt(v)    { return v != null ? (Number.isInteger(v) ? v : Number(v).toFixed(2)) : '—' }
function fmtDec(v, d=2) { return v != null ? Number(v).toFixed(d) : '—' }
function sumf(arr, key) { return arr.reduce((s,d) => s + (d[key] ?? 0), 0) }
function avg(arr, key)  {
  const vals = arr.map(d => d[key]).filter(v => v != null)
  return vals.length ? vals.reduce((s,v)=>s+v,0)/vals.length : null
}

// ── Sort ─────────────────────────────────────────────────────────────────────
function sortBy(key) {
  if (sortKey.value === key) sortDir.value = -sortDir.value
  else { sortKey.value = key; sortDir.value = -1 }
}
function sortIcon(key) {
  if (sortKey.value !== key) return ''
  return sortDir.value === 1 ? '▲' : '▼'
}

// ── Quick-period filters ──────────────────────────────────────────────────────
function setQuickPeriod(val) {
  quickPeriod.value = val
  selectedYear.value = null
  selectedWeekFrom.value = ''
  selectedWeekTo.value = ''
}
function onYearChange() {
  selectedWeekFrom.value = ''
  selectedWeekTo.value = ''
  quickPeriod.value = 'custom'
}
function onManualFilter() { quickPeriod.value = 'custom' }
function resetFilters() {
  quickPeriod.value = 'all'
  selectedYear.value = null
  selectedWeekFrom.value = ''
  selectedWeekTo.value = ''
  clientFilter.value = 'none'
  trendMetric.value = 'total_in_work'
  tableSearch.value = ''
}

// ── Chart helpers ─────────────────────────────────────────────────────────────
const CSS_COLORS = {
  '--c-ok':   '#5a9e68', '--c-warn': '#c9974a', '--c-err': '#c97171', '--c-div': '#dbd8d2',
  '--c-txt':  '#1e1c17', '--c-muted':'#6b6a65',
  '--series-received':'#2f7ed8', '--series-solved':'#c0392b', '--series-inwork':'#7a52a1',
  '--series-altos-l12':'#d84e3a','--series-altos-l3':'#d39b35',
  '--series-altoffice-l12':'#2b67a0','--series-altoffice-l3':'#c55f7a',
  '--series-avgtime-altos':'#b8860b','--series-avgtime-altoffice':'#3e8a7a',
  '--series-proj-avail':'#8d6e1f',
  '--client-rushydro':'#f5a351','--client-transneft':'#14549c','--client-roscosmos':'#ed1941',
  '--client-bryansk':'#8b1e3f','--client-mchs':'#1f88c9','--client-internal':'#6f7b8a',
  '--channel-rushydro-tf':'#b85e12','--channel-other-tf':'#6b8fb3',
}
function css(v) {
  if (v.startsWith('--')) return CSS_COLORS[v] ?? getComputedStyle(document.documentElement).getPropertyValue(v).trim()
  return v
}

function destroyChart(id) { if (charts[id]) { charts[id].destroy(); delete charts[id] } }

function baseOptions(extra = {}) {
  return Object.assign({
    responsive: true, maintainAspectRatio: false,
    interaction: { mode:'index', intersect:false },
    plugins: {
      legend: { labels:{ color:css('--c-txt'), boxWidth:12, font:{size:11} } },
      tooltip: { titleColor:'#fff', bodyColor:'#fff' }
    },
    scales: {
      x: { grid:{ color:css('--c-div') }, ticks:{ color:css('--c-muted'), font:{size:10}, maxRotation:0, autoSkip:true } },
      y: { grid:{ color:css('--c-div') }, ticks:{ color:css('--c-muted'), font:{size:10} } }
    }
  }, extra)
}

function sum(arr, key) { return arr.reduce((s,d)=>s+(d[key]??0),0) }

function pctLegendLabels(chartRef) {
  const ds = chartRef.data.datasets[0]
  const total = ds.data.reduce((a,b)=>a+(b||0),0)
  return chartRef.data.labels.map((label,i) => {
    const pct = total>0 ? ((ds.data[i]/total)*100).toFixed(1) : '0.0'
    return { text:`${label} — ${pct}%`, fillStyle:ds.backgroundColor[i], strokeStyle:ds.backgroundColor[i], index:i }
  })
}

// ── All chart renderers ───────────────────────────────────────────────────────
function renderAllCharts() {
  if (!filtered.value.length) return
  const f = filtered.value
  const labels = f.map(d => d.period)

  // Trend
  destroyChart('trend')
  if (trendChart.value) {
    const primary = css('--series-solved')
    charts['trend'] = new Chart(trendChart.value, {
      type:'line',
      data:{ labels, datasets:[{ label: METRIC_LABELS[trendMetric.value], data: f.map(d=>d[trendMetric.value]),
        borderColor:primary, backgroundColor:primary+'22', fill:true, tension:0.3, pointRadius:2, spanGaps:true }]},
      options: baseOptions()
    })
  }

  // Client Pie
  destroyChart('clientPie')
  if (clientPieChart.value) {
    if (clientFilter.value !== 'none') {
      const ci = CLIENTS.find(c=>c.key===clientFilter.value)
      const cs = sum(f, ci.key), rest = Math.max(0, sum(f,'avail_total')-cs)
      charts['clientPie'] = new Chart(clientPieChart.value, {
        type:'doughnut',
        data:{ labels:[ci.label,'Остальные'], datasets:[{ data:[cs,rest], backgroundColor:[ci.color,css('--c-div')], borderWidth:0 }]},
        options:{ responsive:true, maintainAspectRatio:false, plugins:{ legend:{ position:'bottom', labels:{ color:css('--c-txt'), font:{size:11}, boxWidth:12, generateLabels:pctLegendLabels }} } }
      })
    } else {
      const vals = CLIENTS.map(c=>sum(f,c.key))
      charts['clientPie'] = new Chart(clientPieChart.value, {
        type:'doughnut',
        data:{ labels:CLIENTS.map(c=>c.label), datasets:[{ data:vals, backgroundColor:CLIENTS.map(c=>c.color), borderWidth:0 }]},
        options:{ responsive:true, maintainAspectRatio:false, plugins:{ legend:{ position:'bottom', labels:{ color:css('--c-txt'), font:{size:11}, boxWidth:12, generateLabels:pctLegendLabels }} } }
      })
    }
  }

  // Client Stack
  destroyChart('clientStack')
  if (clientStackChart.value) {
    if (clientFilter.value !== 'none') {
      const ci = CLIENTS.find(c=>c.key===clientFilter.value)
      charts['clientStack'] = new Chart(clientStackChart.value, {
        type:'bar', data:{ labels, datasets:[{ label:ci.label, data:f.map(d=>d[ci.key]), backgroundColor:ci.color }]},
        options: baseOptions({ scales:{ x:{ grid:{display:false}, ticks:{color:css('--c-muted'),font:{size:9},maxRotation:0,autoSkip:true} }, y:{ grid:{color:css('--c-div')}, ticks:{color:css('--c-muted')} } } })
      })
    } else {
      charts['clientStack'] = new Chart(clientStackChart.value, {
        type:'bar',
        data:{ labels, datasets: CLIENTS.map(c=>({ label:c.label, data:f.map(d=>d[c.key]), backgroundColor:c.color, stack:'clients' })) },
        options: baseOptions({ scales:{ x:{ stacked:true, grid:{display:false}, ticks:{color:css('--c-muted'),font:{size:9},maxRotation:0,autoSkip:true} }, y:{ stacked:true, grid:{color:css('--c-div')}, ticks:{color:css('--c-muted')} } } })
      })
    }
  }

  // Client Top-15
  destroyChart('clientTop')
  if (clientTopChart.value && clientFilter.value !== 'none') {
    const ci = CLIENTS.find(c=>c.key===clientFilter.value)
    const topRows = f.filter(d=>d[ci.key]!=null&&d[ci.key]>0).sort((a,b)=>b[ci.key]-a[ci.key]).slice(0,15).sort((a,b)=>a.period.localeCompare(b.period))
    charts['clientTop'] = new Chart(clientTopChart.value, {
      type:'bar', data:{ labels:topRows.map(d=>d.period), datasets:[{ label:ci.label, data:topRows.map(d=>d[ci.key]), backgroundColor:ci.color }]},
      options: baseOptions({ scales:{ x:{ grid:{display:false}, ticks:{color:css('--c-muted'),font:{size:9},maxRotation:0,autoSkip:true} }, y:{ grid:{color:css('--c-div')}, ticks:{color:css('--c-muted')} } } })
    })
  }

  // Received vs Solved
  destroyChart('rs')
  if (rsChart.value) {
    charts['rs'] = new Chart(rsChart.value, {
      type:'bar',
      data:{ labels, datasets:[
        { label:'Принято', data:f.map(d=>d.new_received), backgroundColor:css('--series-received') },
        { label:'Решено', data:f.map(d=>d.total_solved_week), backgroundColor:css('--series-solved') },
      ]},
      options: baseOptions({ scales:{ x:{ grid:{display:false}, ticks:{color:css('--c-muted'),font:{size:9},maxRotation:0,autoSkip:true} }, y:{ grid:{color:css('--c-div')}, ticks:{color:css('--c-muted')} } } })
    })
  }

  // Ratio
  destroyChart('ratio')
  if (ratioChart.value) {
    charts['ratio'] = new Chart(ratioChart.value, {
      type:'line',
      data:{ labels, datasets:[{ label:'Решено/Получено', data:f.map(d=>d.ratio_solved_received), borderColor:css('--c-ok'), backgroundColor:css('--c-ok')+'22', fill:true, tension:0.3, pointRadius:2, spanGaps:true }]},
      options: baseOptions({ plugins:{ legend:{display:false}, tooltip:{titleColor:'#fff',bodyColor:'#fff'} } })
    })
  }

  // In work
  destroyChart('inwork')
  if (inworkChart.value) {
    charts['inwork'] = new Chart(inworkChart.value, {
      type:'line',
      data:{ labels, datasets:[{ label:'В работе', data:f.map(d=>d.total_in_work), borderColor:css('--series-inwork'), backgroundColor:css('--series-inwork')+'22', fill:true, tension:0.3, pointRadius:2, spanGaps:true }]},
      options: baseOptions({ plugins:{ legend:{display:false}, tooltip:{titleColor:'#fff',bodyColor:'#fff'} } })
    })
  }

  // AlterOS lines
  destroyChart('altos')
  if (altosChart.value) {
    charts['altos'] = new Chart(altosChart.value, {
      type:'line',
      data:{ labels, datasets:[
        { label:'1-2 линия', data:f.map(d=>d.altos_1_2line), borderColor:css('--series-altos-l12'), backgroundColor:'transparent', tension:0.3, pointRadius:1, spanGaps:true },
        { label:'3 линия',  data:f.map(d=>d.altos_3line),   borderColor:css('--series-altos-l3'),  backgroundColor:'transparent', tension:0.3, pointRadius:1, spanGaps:true },
      ]},
      options: baseOptions()
    })
  }

  // AlterOS avg time
  destroyChart('altosAvg')
  if (altosAvgChart.value) {
    const c = css('--series-avgtime-altos')
    charts['altosAvg'] = new Chart(altosAvgChart.value, {
      type:'line',
      data:{ labels, datasets:[{ label:'Ср. время, ч', data:f.map(d=>d.altos_avg_time), borderColor:c, backgroundColor:c+'22', fill:true, tension:0.3, pointRadius:1, spanGaps:true }]},
      options: baseOptions({ plugins:{ legend:{display:false}, tooltip:{titleColor:'#fff',bodyColor:'#fff'} } })
    })
  }

  // AlterOS availability
  destroyChart('altosAvail')
  if (altosAvailChart.value) {
    charts['altosAvail'] = new Chart(altosAvailChart.value, {
      type:'bar',
      data:{ labels, datasets:[
        { label:'1-3 дн.', data:f.map(d=>d.altos_avail_1_3), backgroundColor:css('--c-ok'),   stack:'a' },
        { label:'4-7 дн.', data:f.map(d=>d.altos_avail_4_7), backgroundColor:css('--c-warn'), stack:'a' },
        { label:'8-10 дн.', data:f.map(d=>d.altos_avail_8_10), backgroundColor:css('--c-err'), stack:'a' },
      ]},
      options: baseOptions({ scales:{ x:{ stacked:true, grid:{display:false}, ticks:{color:css('--c-muted'),font:{size:9},maxRotation:0,autoSkip:true} }, y:{ stacked:true, grid:{color:css('--c-div')}, ticks:{color:css('--c-muted')} } } })
    })
  }

  // AlterOffice lines
  destroyChart('altoffice')
  if (altofficeChart.value) {
    charts['altoffice'] = new Chart(altofficeChart.value, {
      type:'line',
      data:{ labels, datasets:[
        { label:'1-2 линия', data:f.map(d=>d.altoffice_1_2line), borderColor:css('--series-altoffice-l12'), backgroundColor:'transparent', tension:0.3, pointRadius:1, spanGaps:true },
        { label:'3 линия',  data:f.map(d=>d.altoffice_3line),   borderColor:css('--series-altoffice-l3'),  backgroundColor:'transparent', tension:0.3, pointRadius:1, spanGaps:true },
      ]},
      options: baseOptions()
    })
  }

  // AlterOffice avg time
  destroyChart('altofficeAvg')
  if (altofficeAvgChart.value) {
    const c = css('--series-avgtime-altoffice')
    charts['altofficeAvg'] = new Chart(altofficeAvgChart.value, {
      type:'line',
      data:{ labels, datasets:[{ label:'Ср. время, ч', data:f.map(d=>d.altoffice_avg_time), borderColor:c, backgroundColor:c+'22', fill:true, tension:0.3, pointRadius:1, spanGaps:true }]},
      options: baseOptions({ plugins:{ legend:{display:false}, tooltip:{titleColor:'#fff',bodyColor:'#fff'} } })
    })
  }

  // AlterOffice availability
  destroyChart('altofficeAvail')
  if (altofficeAvailChart.value) {
    charts['altofficeAvail'] = new Chart(altofficeAvailChart.value, {
      type:'bar',
      data:{ labels, datasets:[
        { label:'1-3 дн.', data:f.map(d=>d.altoffice_avail_1_3), backgroundColor:css('--c-ok'),   stack:'a' },
        { label:'4-7 дн.', data:f.map(d=>d.altoffice_avail_4_7), backgroundColor:css('--c-warn'), stack:'a' },
        { label:'8-10 дн.', data:f.map(d=>d.altoffice_avail_8_10), backgroundColor:css('--c-err'), stack:'a' },
      ]},
      options: baseOptions({ scales:{ x:{ stacked:true, grid:{display:false}, ticks:{color:css('--c-muted'),font:{size:9},maxRotation:0,autoSkip:true} }, y:{ stacked:true, grid:{color:css('--c-div')}, ticks:{color:css('--c-muted')} } } })
    })
  }

  // AlterOS channels
  destroyChart('altosChannels')
  if (altosChannelsChart.value) {
    charts['altosChannels'] = new Chart(altosChannelsChart.value, {
      type:'bar',
      data:{ labels, datasets:[
        { label:'РусГидро Email', data:f.map(d=>d.altos_rusg_email),  backgroundColor:css('--client-rushydro'), stack:'a' },
        { label:'РусГидро ТФ',    data:f.map(d=>d.altos_rusg_tf),     backgroundColor:css('--channel-rushydro-tf'), stack:'a' },
        { label:'Прочие Email',   data:f.map(d=>d.altos_other_email), backgroundColor:css('--client-transneft'), stack:'a' },
        { label:'Прочие ТФ',     data:f.map(d=>d.altos_other_tf),    backgroundColor:css('--channel-other-tf'), stack:'a' },
      ]},
      options: baseOptions({ scales:{ x:{ stacked:true, grid:{display:false}, ticks:{color:css('--c-muted'),font:{size:9},maxRotation:0,autoSkip:true} }, y:{ stacked:true, grid:{color:css('--c-div')}, ticks:{color:css('--c-muted')} } } })
    })
  }

  // AlterOffice channels
  destroyChart('altofficeChannels')
  if (altofficeChannelsChart.value) {
    charts['altofficeChannels'] = new Chart(altofficeChannelsChart.value, {
      type:'bar',
      data:{ labels, datasets:[
        { label:'РусГидро Email', data:f.map(d=>d.altoffice_rusg_email),  backgroundColor:css('--client-rushydro'), stack:'a' },
        { label:'РусГидро ТФ',    data:f.map(d=>d.altoffice_rusg_tf),     backgroundColor:css('--channel-rushydro-tf'), stack:'a' },
        { label:'Прочие Email',   data:f.map(d=>d.altoffice_other_email), backgroundColor:css('--client-transneft'), stack:'a' },
        { label:'Прочие ТФ',     data:f.map(d=>d.altoffice_other_tf),    backgroundColor:css('--channel-other-tf'), stack:'a' },
      ]},
      options: baseOptions({ scales:{ x:{ stacked:true, grid:{display:false}, ticks:{color:css('--c-muted'),font:{size:9},maxRotation:0,autoSkip:true} }, y:{ stacked:true, grid:{color:css('--c-div')}, ticks:{color:css('--c-muted')} } } })
    })
  }

  // Project Server
  destroyChart('projserver')
  if (projserverChart.value) {
    charts['projserver'] = new Chart(projserverChart.value, {
      type:'bar',
      data:{ labels, datasets:[
        { label:'Принято',    data:f.map(d=>d.projserver_taken),  backgroundColor:css('--series-received'), type:'bar' },
        { label:'Решено',    data:f.map(d=>d.projserver_solved),  backgroundColor:css('--series-solved'),   type:'bar' },
        { label:'Доступно', data:f.map(d=>d.projserver_avail),  borderColor:css('--series-proj-avail'), backgroundColor:'transparent', type:'line', tension:0.3, pointRadius:1, spanGaps:true, yAxisID:'y1' },
      ]},
      options: baseOptions({ scales:{
        x:{ grid:{display:false}, ticks:{color:css('--c-muted'),font:{size:9},maxRotation:0,autoSkip:true} },
        y:{ grid:{color:css('--c-div')}, ticks:{color:css('--c-muted')} },
        y1:{ position:'right', grid:{display:false}, ticks:{color:css('--c-muted')} }
      } })
    })
  }
}

// ── Lifecycle ────────────────────────────────────────────────────────────────
async function loadAll() {
  loading.value = true
  try {
    const [r, tr] = await Promise.all([tpApi.getRows(), tpApi.getSetting('traffic_rules').catch(()=>({}))])
    rows.value = r
    trafficRules.value = tr ?? {}
  } catch (e) {
    console.error('TP load error', e)
  } finally {
    loading.value = false
    await nextTick()
    renderAllCharts()
  }
}

watch([filtered, trendMetric, clientFilter], () => nextTick(renderAllCharts))

onBeforeUnmount(() => { Object.values(charts).forEach(c => c.destroy()); charts = {} })

onMounted(loadAll)
</script>

<style scoped>
.tp-dashboard { display:flex; flex-direction:column; gap:var(--sp6); padding-bottom:var(--sp8); }

/* ===== Header ===== */
.page-header { display:flex; align-items:flex-start; justify-content:space-between; flex-wrap:wrap; gap:var(--sp4); }
.page-head-left { flex:0 0 auto; }
.page-title { font-size:1.25rem; font-weight:800; letter-spacing:-.02em; }
.page-sub   { font-size:.75rem; color:var(--c-muted); margin-top:2px; }
.tp-filterbar { display:flex; align-items:center; flex-wrap:wrap; gap:var(--sp2); justify-content:flex-end; margin-left:auto; }
.chip-row { display:flex; flex-wrap:wrap; gap:5px; }
.qchip { padding:4px 10px; border-radius:999px; border:1px solid var(--c-div); background:var(--c-surf2); font-size:.75rem; font-weight:600; color:var(--c-muted); transition:background .14s,color .14s,border-color .14s; white-space:nowrap; }
.qchip:hover { background:var(--c-off); color:var(--c-txt); }
.qchip.active { background:var(--c-red); color:#fff; border-color:var(--c-red); }

/* ===== Section titles ===== */
.section-title { font-size:.8125rem; font-weight:800; text-transform:uppercase; letter-spacing:.06em; color:var(--c-muted); padding:var(--sp2) 0 var(--sp1); border-bottom:1px solid var(--c-div); }
.section-tag   { font-weight:500; text-transform:none; letter-spacing:0; font-size:.7rem; padding:2px 6px; border-radius:4px; background:var(--c-off); margin-left:6px; }

/* ===== KPI ===== */
.kpi-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(160px,1fr)); gap:var(--sp3); }
.kpi-card { background:var(--c-surf2); border:1px solid var(--c-brd); border-radius:var(--r3); padding:var(--sp4); display:flex; flex-direction:column; gap:4px; position:relative; overflow:hidden; box-shadow:var(--sh1); }
.kpi-card::before { content:''; position:absolute; top:0; left:0; right:0; height:3px; }
.kpi-card.light-green::before  { background:var(--c-ok); }
.kpi-card.light-yellow::before { background:var(--c-warn); }
.kpi-card.light-red::before    { background:var(--c-err); }
.kpi-card.light-gray::before   { background:var(--c-div); }
.kpi-lbl { font-size:.6875rem; font-weight:600; color:var(--c-muted); text-transform:uppercase; letter-spacing:.04em; }
.kpi-val { font-size:clamp(1.4rem,1.1rem+1vw,2rem); font-weight:800; letter-spacing:-.03em; font-variant-numeric:tabular-nums; line-height:1; }
.kpi-sub { font-size:.625rem; color:var(--c-muted); }

/* ===== Traffic grid ===== */
.traffic-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:var(--sp4); }
.traffic-card { background:var(--c-surf2); border:1px solid var(--c-brd); border-radius:var(--r3); padding:var(--sp5); box-shadow:var(--sh1); }
.traffic-head { display:flex; align-items:flex-start; justify-content:space-between; gap:var(--sp4); margin-bottom:var(--sp3); }
.traffic-title { font-weight:800; letter-spacing:-.01em; margin-bottom:4px; }
.traffic-value { font-size:1.5rem; font-weight:800; font-variant-numeric:tabular-nums; line-height:1.1; }
.traffic-meta  { font-size:.7rem; color:var(--c-muted); margin-top:4px; }
.traffic-dot   { width:16px; height:16px; border-radius:50%; margin-top:4px; flex-shrink:0; }
.traffic-dot.green  { background:var(--c-ok);   box-shadow:0 0 0 4px color-mix(in oklab,var(--c-ok)   12%,transparent); }
.traffic-dot.yellow { background:var(--c-warn);  box-shadow:0 0 0 4px color-mix(in oklab,var(--c-warn) 12%,transparent); }
.traffic-dot.red    { background:var(--c-err);   box-shadow:0 0 0 4px color-mix(in oklab,var(--c-err)  12%,transparent); }
.traffic-dot.gray   { background:var(--c-faint); }
.badge { display:inline-flex; align-items:center; padding:3px 10px; border-radius:99px; font-size:.75rem; font-weight:700; }
.badge-green  { background:var(--c-ok-l);  color:var(--c-ok); }
.badge-yellow { background:var(--c-warn-l); color:var(--c-warn); }
.badge-red    { background:var(--c-err-l);  color:var(--c-err); }
.badge-gray   { background:var(--c-off);    color:var(--c-muted); }

/* ===== Chart grids ===== */
.cgrid   { display:grid; grid-template-columns:1fr 1fr 1fr; gap:var(--sp4); }
.cgrid-2 { display:grid; grid-template-columns:1fr 1fr;     gap:var(--sp4); }
@media(max-width:1100px){ .cgrid{grid-template-columns:1fr 1fr} }
@media(max-width:700px) { .cgrid,.cgrid-2{grid-template-columns:1fr} }

.ccard { background:var(--c-surf2); border:1px solid var(--c-brd); border-radius:var(--r3); padding:var(--sp5); box-shadow:var(--sh1); }
.ctitle { font-size:.8125rem; font-weight:700; margin-bottom:var(--sp3); display:flex; justify-content:space-between; align-items:baseline; gap:var(--sp2); }
.csub { font-size:.7rem; color:var(--c-muted); font-weight:400; }
.chart-wrap { height:240px; position:relative; }
.chart-wrap.tall { height:300px; }

/* ===== Table ===== */
.tscroll { overflow-x:auto; max-height:520px; overflow-y:auto; border-radius:var(--r2); border:1px solid var(--c-div); margin-top:var(--sp3); }
table { width:100%; border-collapse:collapse; font-size:.78rem; font-variant-numeric:tabular-nums; }
thead th { position:sticky; top:0; background:var(--c-surf); z-index:1; padding:var(--sp2) var(--sp3); text-align:left; font-size:.625rem; font-weight:700; text-transform:uppercase; letter-spacing:.05em; color:var(--c-muted); border-bottom:1px solid var(--c-div); white-space:nowrap; cursor:pointer; user-select:none; }
tbody td { padding:var(--sp2) var(--sp3); border-bottom:1px solid var(--c-div); white-space:nowrap; vertical-align:middle; }
tbody tr:hover td { background:var(--c-off); }
tr.total-row td { font-weight:700; background:var(--c-off); border-top:2px solid var(--c-div); position:sticky; bottom:0; }
.td-p { font-weight:600; white-space:nowrap; }
.td-dot { display:inline-block; width:7px; height:7px; border-radius:50%; margin-right:4px; vertical-align:middle; flex-shrink:0; }
.td-dot.green  { background:var(--c-ok); }
.td-dot.yellow { background:var(--c-warn); }
.td-dot.red    { background:var(--c-err); }
.td-dot.gray   { background:var(--c-faint); }
.legend-note { font-size:.6875rem; color:var(--c-faint); font-style:italic; margin-top:var(--sp3); }
.tempty { text-align:center; padding:2rem; color:var(--c-faint); }
.loading-state { padding:4rem; text-align:center; color:var(--c-muted); }

@media(max-width:900px){
  .page-header { flex-direction:column; align-items:stretch; }
  .tp-filterbar { justify-content:flex-start; margin-left:0; }
}
</style>
