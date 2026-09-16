<template>
  <div v-if="loading" class="tempty">Загрузка данных…</div>
  <template v-else>
    <!-- Period range: «от — до» plus quick filters, mirroring the TP dashboard -->
    <div class="filters">
      <span class="fl">Период</span>
      <select class="fsel" v-model="fromMonth" @change="onBoundChange" style="min-width:140px">
        <option v-for="m in months" :key="m.key" :value="m.key">{{ m.label }}</option>
      </select>
      <span class="fl">—</span>
      <select class="fsel" v-model="toMonth" @change="onBoundChange" style="min-width:140px">
        <option v-for="m in months" :key="m.key" :value="m.key">{{ m.label }}</option>
      </select>
      <button v-for="q in QUICK" :key="q.n" class="btn" :class="{ 'btn-p': activeQuick === q.n }"
              style="font-size:.75rem;padding:4px 10px" @click="quickRange(q.n)">{{ q.label }}</button>
      <button class="btn" :class="{ 'btn-p': activeQuick === 'all' }"
              style="font-size:.75rem;padding:4px 10px" @click="allRange">Всё время</button>
      <div class="tinfo" style="flex:1;margin:0;text-align:right">
        {{ rangeLabel }} · месяцев: {{ rangeMonths.length }}
      </div>
      <button v-if="canEdit" class="btn btn-g" @click="openNewMonth">+ Месяц</button>
      <button class="btn btn-g" @click="showSettings=true">⚙ Настройки дашборда</button>
      <button class="btn btn-g" @click="autoLayout">⌗ Авторасположение</button>
    </div>

    <!-- Widget grid: order, size and visibility come from the saved layout -->
    <div class="wgrid" ref="gridEl">
      <div
        v-for="w in visibleWidgets"
        :key="w.key"
        class="wcell"
        :class="['size-' + w.size, { dragging: dragKey === w.key, 'drop-target': overKey === w.key }]"
        :data-cell="w.key"
        @dragover="dragOver(w.key, $event)"
        @drop="onDrop(w.key, $event)"
      >
        <!-- KPI cards -->
        <template v-if="w.key === 'kpi'">
          <div class="ctitle-row">
            <span class="whandle" draggable="true" title="Перетащите, чтобы изменить порядок"
                  @dragstart="dragStart(w.key, $event)" @dragend="dragEnd">⠿</span>
            <span class="ctitle">{{ title(w.key) }} — {{ rangeLabel }}</span>
          </div>
          <div class="kpi-grid" style="margin-bottom:0" v-if="currentAnalytics">
            <div class="kpi">
              <div class="kpi-lbl">Чистый прирост</div>
              <div class="kpi-val" :style="{color: currentAnalytics.net>=0?'var(--c-ok)':'var(--c-err)'}">{{ currentAnalytics.net>=0?'+':'' }}{{ currentAnalytics.net }}</div>
              <div class="kpi-sub" v-if="prevAnalytics">
                <span class="dtrend" :class="trendClass(currentAnalytics.net, prevAnalytics.net, 'higher')">
                  {{ trendArrow(currentAnalytics.net, prevAnalytics.net) }}
                  {{ deltaText(currentAnalytics.net - prevAnalytics.net) }}
                </span>
                к пред. периоду
              </div>
              <div class="kpi-sub td-muted" v-else>нет данных для сравнения</div>
            </div>
            <div class="kpi">
              <div class="kpi-lbl">Движение персонала</div>
              <div class="kpi-val" style="color:var(--c-ok)">+{{ currentAnalytics.hired }}</div>
              <div class="kpi-sub">
                <span style="color:var(--c-err)">−{{ currentAnalytics.fired }}</span>
                <span class="td-muted" v-if="prevAnalytics">
                  · <span class="dtrend" :class="trendClass(currentAnalytics.fired, prevAnalytics.fired, 'lower')">
                    {{ trendArrow(currentAnalytics.fired, prevAnalytics.fired) }} {{ deltaText(currentAnalytics.fired - prevAnalytics.fired) }}
                  </span>
                </span>
              </div>
            </div>
            <div class="kpi" v-for="m in topMetrics" :key="m.key" :class="'light-' + m.light">
              <div class="kpi-lbl">{{ m.label }}</div>
              <div class="kpi-val">{{ fmt(m.value, m.unit) }}</div>
              <div class="kpi-sub">
                <span class="light-dot" :class="'light-'+m.light"></span>
                <span class="td-muted" v-if="prevMetrics[m.key] !== undefined">
                  <span class="dtrend" :class="trendClass(m.value, prevMetrics[m.key], m.better)">
                    {{ trendArrow(m.value, prevMetrics[m.key]) }} {{ deltaText(m.value - prevMetrics[m.key]) }}{{ m.unit === '%' ? ' п.п.' : '' }}
                  </span>
                </span>
                <span v-if="m.filled"> · {{ lightLabel(m.light) }}</span>
                <span v-else style="color:var(--c-err)"> · Не заполнено</span>
              </div>
            </div>
          </div>
        </template>

        <!-- Chart / table widgets -->
        <div v-else class="ccard">
          <div class="ctitle-row">
            <span class="whandle" draggable="true" title="Перетащите, чтобы изменить порядок"
                  @dragstart="dragStart(w.key, $event)" @dragend="dragEnd">⠿</span>
            <span class="ctitle">
              <template v-if="w.key === 'metrics'">
                Метрики — {{ rangeLabel }}
                <span v-if="unfilledCount" style="color:var(--c-err);font-weight:600">
                  · не заполнено: {{ unfilledCount }}
                </span>
                <button v-if="lightFilter" class="mtab active" style="margin-left:8px;padding:2px 10px" @click="lightFilter=''">
                  {{ lightLabel(lightFilter) }} ✕
                </button>
                <button v-if="stageFilter" class="mtab active" style="margin-left:8px;padding:2px 10px" @click="stageFilter=null">
                  {{ stageFilter.label }} ✕
                </button>
              </template>
              <template v-else-if="w.key === 'notes'">Заметки — {{ singleMonth?.label || '—' }}</template>
              <template v-else-if="w.key === 'employees'">Сотрудники — {{ singleMonth?.label || '—' }}</template>
              <template v-else>{{ title(w.key) }}</template>
            </span>
            <span v-if="w.key === 'metrics'" style="display:flex;gap:6px">
              <router-link v-if="canEnterData" class="btn btn-g" style="font-size:.75rem;padding:4px 8px" :to="dataEntryLink">Данные</router-link>
            </span>
            <button v-if="w.key === 'notes' && canEdit" class="btn btn-g" style="font-size:.75rem;padding:4px 8px" @click="openEditNotes">✎ Изменить</button>
            <button v-if="CHART_OPTIONS[w.key]" class="cgear-btn" type="button"
                    title="Размер по ширине (соседи подстроятся)" @click="cycleSize(w)">⇔</button>
            <template v-if="CHART_OPTIONS[w.key]">
              <button class="cgear-btn" type="button" title="Ниже" @click="bumpHeight(w, -40)">↧</button>
              <button class="cgear-btn" type="button" title="Выше" @click="bumpHeight(w, 40)">↥</button>
            </template>
            <chart-settings
              v-if="CHART_OPTIONS[w.key]"
              :settings="w.settings || {}"
              :option="CHART_OPTIONS[w.key].value"
              :default-height="baseHeight(w.size)"
              :default-colors="palette.chartColors"
              @update="s => setSettings(w.key, s)"
            />
          </div>

          <e-chart
            v-if="CHART_OPTIONS[w.key]"
            :option="chartOption(w)"
            :height="chartHeight(w)"
            :colors="chartColors(w)"
            @click="CHART_CLICKS[w.key]"
          />

          <!-- Metrics table: months of the period plus the aggregated period column -->
          <div v-else-if="w.key === 'metrics'" class="twrap" ref="metricsCard">
            <div class="tscroll">
              <table>
                <thead>
                  <tr>
                    <th>Метрика</th>
                    <th v-for="mm in rangeMonths" :key="mm.key">{{ shortMonth(mm.label) }}</th>
                    <th style="min-width:110px">Период</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="m in visibleMetrics" :key="m.key" :class="{ 'row-unfilled': !m.filled }">
                    <td class="td-p">{{ m.label }}</td>
                    <td v-for="mm in rangeMonths" :key="mm.key" class="td-mono">
                      <span class="light-dot" :class="'light-'+monthLight(mm.key, m.key)"></span>
                      {{ fmt(monthValue(mm.key, m.key), m.unit) }}
                    </td>
                    <td class="td-mono" style="font-weight:600">
                      <span class="light-dot" :class="'light-'+m.light"></span> {{ fmt(m.value, m.unit) }}
                    </td>
                  </tr>
                  <tr v-if="!visibleMetrics.length"><td :colspan="rangeMonths.length + 2" class="tempty">Нет метрик</td></tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- Notes -->
          <template v-else-if="w.key === 'notes'">
            <div v-if="editingNotes" style="display:flex;flex-direction:column;gap:8px">
              <textarea class="fta" v-model="notesForm" style="min-height:80px"></textarea>
              <div style="display:flex;gap:8px;justify-content:flex-end">
                <button class="btn btn-g" style="font-size:.75rem" @click="editingNotes=false">Отмена</button>
                <button class="btn btn-p" style="font-size:.75rem" @click="saveNotes">Сохранить</button>
              </div>
            </div>
            <div v-else class="notes-card">{{ singleMonth?.notes || 'Нет заметок' }}</div>
          </template>

          <!-- Employee events of the selected month -->
          <div v-else-if="w.key === 'employees'" class="twrap">
            <div class="tscroll">
              <table>
                <thead><tr><th>Тип</th><th>ФИО</th><th>Дата</th></tr></thead>
                <tbody>
                  <tr v-for="e in (singleMonth?.employees || [])" :key="e.id">
                    <td><span class="sb" :class="e.event_type==='hired'?'s-hired':'s-fired'">{{ e.event_type==='hired'?'Приём':'Увольнение' }}</span></td>
                    <td class="td-p">{{ e.full_name }}</td>
                    <td class="td-muted">{{ formatDate(e.event_date) }}</td>
                  </tr>
                  <tr v-if="!singleMonth?.employees?.length"><td colspan="3" class="tempty">Нет событий</td></tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </div>

    <dashboard-settings
      v-if="showSettings"
      :widgets="ordered"
      :title="title"
      @move="move"
      @save="onSaveLayout"
      @reset="onResetLayout"
      @close="showSettings=false"
    />

    <!-- New month modal -->
    <div v-if="showNewMonth" class="modal-overlay" @click.self="showNewMonth=false">
      <div class="modal modal-sm">
        <div class="mh"><span class="mt">Новый месяц</span><button class="mc" @click="showNewMonth=false">✕</button></div>
        <div class="fg">
          <div class="fgi"><label class="fl">Год</label><input class="fi" type="number" v-model="newMonthForm.year" min="2020" max="2030"></div>
          <div class="fgi"><label class="fl">Месяц</label>
            <select class="fs" v-model="newMonthForm.month">
              <option v-for="i in 12" :key="i" :value="i">{{ monthNames[i-1] }}</option>
            </select>
          </div>
        </div>
        <div class="fgi full" style="margin-top:8px"><label class="fl">Заметки</label><textarea class="fta" v-model="newMonthForm.notes"></textarea></div>
        <div class="fac"><button class="btn btn-g" @click="showNewMonth=false">Отмена</button><button class="btn btn-p" @click="createMonth">Создать</button></div>
      </div>
    </div>
  </template>
</template>

<script setup>
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api/client.js'
import { useAuthStore } from '../stores/auth.js'
import { usePaletteStore } from '../stores/palette.js'
import EChart from '../components/EChart.vue'
import ChartSettings from '../components/ChartSettings.vue'
import DashboardSettings from '../components/DashboardSettings.vue'
import { useWidgetLayout, useDragReorder } from '../composables/useWidgetLayout.js'
import { applyChartSettings, chartHeightOf, HEIGHT_MIN, HEIGHT_MAX } from '../composables/useChartSettings.js'
import { useRowEqualize } from '../composables/useRowEqualize.js'

const auth = useAuthStore()
const palette = usePaletteStore()
const router = useRouter()
const canEdit = computed(() => auth.canEdit)
const loading = ref(true)
const months = ref([])
const showNewMonth = ref(false)
const showSettings = ref(false)
const editingNotes = ref(false)
const notesForm = ref('')
const monthNames = ['Январь','Февраль','Март','Апрель','Май','Июнь','Июль','Август','Сентябрь','Октябрь','Ноябрь','Декабрь']
const newMonthForm = ref({ year: new Date().getFullYear(), month: new Date().getMonth()+1, notes: '' })

const metricsCard = ref(null)
const lightFilter = ref('')
const stageFilter = ref(null)

// `kind` drives «Авторасположение»: kpi → 1/3, chart → 1/2, wide_chart → 2/3, table → full.
const WIDGET_CATALOG = [
  { key: 'kpi', title: 'KPI-карточки', size: 'large', kind: 'kpi' },
  { key: 'move', title: 'Движение персонала', size: 'medium', kind: 'chart' },
  { key: 'hire_fire', title: 'Приём / увольнение по месяцам', size: 'medium', kind: 'chart' },
  { key: 'turnover', title: 'Текучесть кадров (%)', size: 'medium', kind: 'chart' },
  { key: 'funnel', title: 'Воронка найма', size: 'medium', kind: 'chart' },
  { key: 'dynamics', title: 'Динамика по месяцам', size: 'large', kind: 'wide_chart' },
  { key: 'departments', title: 'Структура по подразделениям', size: 'wide', kind: 'wide_chart' },
  { key: 'notes', title: 'Заметки месяца', size: 'small', kind: 'chart' },
  { key: 'light_stack', title: 'Распределение метрик по светофору', size: 'large', kind: 'wide_chart' },
  { key: 'metrics', title: 'Метрики периода', size: 'large', kind: 'table' },
  { key: 'employees', title: 'Сотрудники месяца', size: 'wide', kind: 'table' },
]

const { layout, ordered, visibleWidgets, title, setSettings,
        load: loadLayout, save: saveLayout, saveQuiet, resetLayout, autoLayout, move } =
  useWidgetLayout('hr', WIDGET_CATALOG)
const { dragKey, overKey, dragStart, dragOver, drop: onDrop, dragEnd } = useDragReorder(onMoveEnd)
const { gridEl, equalize } = useRowEqualize()

// ---------- Period selection ----------

const fromMonth = ref('')
const toMonth = ref('')
// Quick presets relative to the latest month with data, like the Naumen analytics page.
const QUICK = [
  { label: 'Месяц', n: 1 },
  { label: '3 месяца', n: 3 },
  { label: 'Полгода', n: 6 },
  { label: 'Год', n: 12 },
]

function monthShift(key, delta) {
  const [y, m] = key.split('-').map(Number)
  const total = y * 12 + (m - 1) + delta
  const ny = Math.floor(total / 12), nm = total % 12 + 1
  return `${ny}-${String(nm).padStart(2, '0')}`
}

function setRange(from, to) {
  if (from > to) [from, to] = [to, from]
  fromMonth.value = from
  toMonth.value = to
}

function onBoundChange() { setRange(fromMonth.value, toMonth.value) }

function quickRange(n) {
  const last = months.value.at(-1)?.key
  if (!last) return
  setRange(monthShift(last, -(n - 1)), last)
}

function allRange() {
  if (!months.value.length) return
  setRange(months.value[0].key, months.value.at(-1).key)
}

const activeQuick = computed(() => {
  const last = months.value.at(-1)?.key
  if (!last || !fromMonth.value) return ''
  for (const q of QUICK) {
    if (toMonth.value === last && fromMonth.value === monthShift(last, -(q.n - 1))) return q.n
  }
  if (months.value.length && fromMonth.value === months.value[0].key && toMonth.value === last) return 'all'
  return ''
})

const rangeMonths = computed(() =>
  months.value.filter(m => fromMonth.value <= m.key && m.key <= toMonth.value))
// Month-bound widgets (notes, employees, data-entry link) follow the last month of the range.
const singleMonth = computed(() => rangeMonths.value.at(-1) || null)
const rangeLabel = computed(() => {
  const n = rangeMonths.value.length
  if (!n) return 'нет данных за период'
  return n === 1 ? rangeMonths.value[0].label : `${rangeMonths.value[0].label} — ${rangeMonths.value.at(-1).label}`
})

// ---------- Range analytics (current + previous period) ----------

const rangeAnalytics = ref({})
const prevAnalytics = ref(null)
const rangeKey = computed(() => `${fromMonth.value}_${toMonth.value}`)

const currentAnalytics = computed(() => rangeAnalytics.value[rangeKey.value] || null)

const rangeLen = computed(() => {
  if (!fromMonth.value || !toMonth.value) return 1
  const [fy, fm] = fromMonth.value.split('-').map(Number)
  const [ty, tm] = toMonth.value.split('-').map(Number)
  return (ty * 12 + tm) - (fy * 12 + fm) + 1
})

async function loadRange() {
  if (!fromMonth.value || !toMonth.value) return
  const key = rangeKey.value
  if (!rangeAnalytics.value[key]) {
    try {
      rangeAnalytics.value[key] = await api.get(`/hr/analytics/range?from_month=${fromMonth.value}&to_month=${toMonth.value}`)
    } catch (e) { console.error(e) }
  }
  // Previous period of the same length, directly before the selected one.
  const firstData = months.value[0]?.key
  const prevTo = monthShift(fromMonth.value, -1)
  const prevFrom = monthShift(prevTo, -(rangeLen.value - 1))
  if (!firstData || prevTo < firstData) {
    prevAnalytics.value = null
    return
  }
  const pkey = `${prevFrom}_${prevTo}`
  if (!rangeAnalytics.value[pkey]) {
    try {
      rangeAnalytics.value[pkey] = await api.get(`/hr/analytics/range?from_month=${prevFrom}&to_month=${prevTo}`)
    } catch (e) { console.error(e) }
  }
  const prev = rangeAnalytics.value[pkey]
  prevAnalytics.value = prev && prev.months_count ? prev : null
}

// Monthly analytics power the per-month charts (loaded once for all months).
const analytics = ref({})

const LIGHT_LABELS = { green: 'Норма', yellow: 'Внимание', red: 'Критично' }
function lightLabel(light) { return LIGHT_LABELS[light] || '—' }

const visibleMetrics = computed(() => {
  let list = currentAnalytics.value?.metrics || []
  if (lightFilter.value) list = list.filter(m => m.light === lightFilter.value)
  if (stageFilter.value) list = list.filter(m => stageFilter.value.keys.includes(m.key))
  return list
})

const unfilledCount = computed(() => (currentAnalytics.value?.metrics || []).filter(m => !m.filled).length)
const canEnterData = computed(() => auth.canEditMetrics('hr'))
const dataEntryLink = computed(() => ({ path: '/hr/data-entry', query: singleMonth.value ? { month: singleMonth.value.key } : {} }))

function scrollToMetrics() {
  const el = Array.isArray(metricsCard.value) ? metricsCard.value[0] : metricsCard.value
  el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
}

// Key metric cards: the traffic light is attached directly to the card
// (border + dot); an unfilled metric reads as red from the API.
const TOP_KEYS = [
  { key: 'total_employees', better: 'higher' },
  { key: 'turnover', better: 'lower' },
  { key: 'avg_time_to_fill', better: 'lower' },
  { key: 'offers_accepted_pct', better: 'higher' },
  { key: 'probation_pass_rate', better: 'higher' },
  { key: 'probation_pass_rate_adaptation', better: 'higher' },
]
const topMetrics = computed(() => {
  const list = currentAnalytics.value?.metrics || []
  return TOP_KEYS.map(t => {
    const m = list.find(x => x.key === t.key)
    return m ? { ...m, better: t.better } : null
  }).filter(Boolean)
})

const prevMetrics = computed(() => {
  const out = {}
  for (const m of (prevAnalytics.value?.metrics || [])) {
    if (m.value !== null && m.value !== undefined) out[m.key] = m.value
  }
  return out
})

function fmt(val, unit) {
  if (val === null || val === undefined) return '—'
  if (unit === '%') return val.toFixed(2).replace('.', ',') + '%'
  if (unit === 'дн.') return val.toFixed(1).replace('.', ',') + ' дн.'
  if (unit === 'чел.' || unit === 'шт.') return Math.round(val) + ' ' + unit
  return String(val).replace('.', ',')
}

function formatDate(d) { return new Date(d).toLocaleDateString('ru-RU') }

function deltaText(diff) {
  if (!diff) return '0'
  return (diff > 0 ? '+' : '') + (Math.abs(diff) < 1 ? diff.toFixed(2).replace('.', ',') : diff)
}

function trendArrow(cur, prev) {
  if (cur === prev) return '→'
  return cur > prev ? '↑' : '↓'
}

/** `better` says which direction is good, so the arrow can be coloured. */
function trendClass(cur, prev, better) {
  if (cur === prev) return 'flat'
  const up = cur > prev
  if (better === 'lower') return up ? 'down' : 'up'
  return up ? 'up' : 'down'
}

function monthValue(monthKey, metricKey) {
  const hit = analytics.value[monthKey]?.metrics?.find(m => m.key === metricKey)
  return hit && hit.value !== null && hit.value !== undefined ? hit.value : null
}

function monthLight(monthKey, metricKey) {
  const hit = analytics.value[monthKey]?.metrics?.find(m => m.key === metricKey)
  return hit?.light || 'gray'
}

/** «Февраль 2026» → «Фев 26» so a 12-month table stays readable. */
function shortMonth(label) {
  const [name, year] = String(label || '').split(' ')
  if (!year) return name
  return `${name.slice(0, 3)} ${year.slice(2)}`
}

function funnelValue(monthKey, metricKey, fallback) {
  return monthValue(monthKey, metricKey) ?? fallback
}

// ---------- Charts ----------

/** Generates `count` shades of `hex`, lightest to darkest, for the funnel chart —
 *  keeps the funnel legible and on-brand no matter which chart palette is active. */
function funnelGreenShades(hex, count) {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex || '') || /^#?([0-9a-f]{6})$/i.exec('2d6e17')
  const n = parseInt(m[1], 16)
  const r0 = (n >> 16) & 255, g0 = (n >> 8) & 255, b0 = n & 255
  const n2 = Math.max(count, 1)
  return Array.from({ length: n2 }, (_, i) => {
    // i=0 -> lightest (mixed toward white), last -> the base colour itself.
    const t = n2 === 1 ? 1 : 1 - (i / (n2 - 1)) * 0.55
    const mix = (c) => Math.round(c * t + 255 * (1 - t) * 0.35)
    const r = Math.min(255, mix(r0)), g = Math.min(255, mix(g0)), b = Math.min(255, mix(b0))
    return '#' + [r, g, b].map(v => v.toString(16).padStart(2, '0')).join('')
  })
}

function baseHeight(size) { return size === 'large' || size === 'wide' ? 280 : 220 }

// A taller neighbour raises the whole row; the chart then stretches to fill the
// freed space (see `stretchCharts` below), so content follows the card height.
const stretch = ref({})
const STRETCH_MAX = 600

function stretchCharts() {
  const grid = gridEl.value
  if (!grid) return
  const out = {}
  for (const w of visibleWidgets.value) {
    if (!CHART_OPTIONS[w.key]) continue
    const cell = grid.querySelector(`[data-cell="${w.key}"]`)
    if (!cell) continue
    const titleRow = cell.querySelector('.ctitle-row')?.offsetHeight || 0
    // .ccard vertical padding (2 × var(--sp5)) plus a small breathing room.
    const avail = cell.offsetHeight - titleRow - 34
    if (avail > 0) out[w.key] = Math.min(avail, STRETCH_MAX)
  }
  stretch.value = out
}

function chartHeight(w) {
  const base = chartHeightOf(w.settings, baseHeight(w.size))
  const s = stretch.value[w.key]
  return s ? Math.max(base, Math.min(s, STRETCH_MAX)) : Math.min(base, HEIGHT_MAX)
}
function chartOption(w) { return applyChartSettings(CHART_OPTIONS[w.key].value, w.settings) }
function chartColors(w) { return w.settings?.colors?.length ? w.settings.colors : null }

const SIZES = ['small', 'medium', 'wide', 'large']

/** Cycles the widget between the preset widths; the row reflows automatically. */
function cycleSize(w) {
  const row = layout.value.find(x => x.key === w.key)
  if (!row) return
  row.size = SIZES[(SIZES.indexOf(row.size) + 1) % SIZES.length]
  saveQuiet()
}

/** Steps the chart height up/down within the sane 200–500 px band. */
function bumpHeight(w, delta) {
  const row = layout.value.find(x => x.key === w.key)
  if (!row) return
  const cur = chartHeightOf(row.settings, baseHeight(row.size))
  const next = Math.min(Math.max(cur + delta, HEIGHT_MIN), HEIGHT_MAX)
  setSettings(w.key, { ...(row.settings || {}), height: next })
}

async function onMoveEnd(fromKey, toKey) {
  move(fromKey, toKey)
  // Drag-and-drop reorders used to be lost on reload — persist immediately.
  await saveQuiet()
}

async function onSaveLayout() {
  if (await saveLayout()) showSettings.value = false
}

async function onResetLayout() {
  await resetLayout()
  showSettings.value = false
}

// Hires/fires are semantic (good/bad), so they always use the palette's
// traffic-light green/red — never the decorative chart palette.
const hireFireOpt = computed(() => {
  const ms = rangeMonths.value
  const tl = palette.trafficLight
  return {
    tooltip: { trigger: 'axis' },
    legend: { data: ['Принято','Уволено'], bottom: 0, textStyle: { fontSize: 11 } },
    grid: { left: 35, right: 12, top: 12, bottom: 40 },
    xAxis: { type: 'category', data: ms.map(m => m.label), axisLabel: { fontSize: 10 } },
    yAxis: { type: 'value', minInterval: 1, axisLabel: { fontSize: 10 } },
    series: [
      { name: 'Принято', type: 'bar', data: ms.map(m => m.hired_count), itemStyle: { color: tl.green } },
      { name: 'Уволено', type: 'bar', data: ms.map(m => m.fired_count), itemStyle: { color: tl.red } },
    ],
  }
})

/** Turnover split by dismissal initiative: company decisions vs. employee's own will. */
const moveOpt = computed(() => {
  const ms = rangeMonths.value
  const tl = palette.trafficLight
  return {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { data: ['Принято','По инициативе компании','По собственному желанию'], bottom: 0, textStyle: { fontSize: 10 } },
    grid: { left: 35, right: 12, top: 12, bottom: 46 },
    xAxis: { type: 'category', data: ms.map(m => m.label), axisLabel: { fontSize: 10 } },
    yAxis: { type: 'value', minInterval: 1, axisLabel: { fontSize: 10 } },
    series: [
      { name: 'Принято', type: 'bar', data: ms.map(m => m.hired_count), itemStyle: { color: tl.green } },
      { name: 'По инициативе компании', type: 'bar', stack: 'fired', data: ms.map(m => monthValue(m.key, 'fired_by_company')), itemStyle: { color: tl.red } },
      { name: 'По собственному желанию', type: 'bar', stack: 'fired', data: ms.map(m => monthValue(m.key, 'fired_by_own')), itemStyle: { color: tl.yellow } },
    ],
  }
})

/** Months of the range that actually have a turnover value. */
const turnoverMonths = computed(() => rangeMonths.value.filter(m => monthValue(m.key, 'turnover') !== null))

// Decorative single-series chart: always takes the first colour of the active
// chart palette, so it repaints whenever the preset changes.
const turnoverOpt = computed(() => {
  const ms = turnoverMonths.value
  const color = palette.chartColors[0]
  return {
    tooltip: { trigger: 'axis', valueFormatter: v => v?.toFixed(2) + '%' },
    grid: { left: 40, right: 12, top: 12, bottom: 30 },
    xAxis: { type: 'category', data: ms.map(m => m.label), axisLabel: { fontSize: 10 } },
    yAxis: { type: 'value', axisLabel: { fontSize: 10, formatter: '{value}%' } },
    series: [{ type: 'line', data: ms.map(m => monthValue(m.key, 'turnover')), smooth: true, symbolSize: 8, lineStyle: { width: 2.5, color }, itemStyle: { color }, areaStyle: { color } }],
  }
})

/** Headcount is a real metric (total_employees), not an accumulated guess. */
const dynamicsOpt = computed(() => {
  const ms = rangeMonths.value
  const c = palette.chartColors
  return {
    tooltip: { trigger: 'axis' },
    legend: { data: ['Численность','Принято','Уволено','Текучесть'], bottom: 0, textStyle: { fontSize: 10 } },
    grid: { left: 40, right: 45, top: 14, bottom: 46 },
    xAxis: { type: 'category', data: ms.map(m => m.label), axisLabel: { fontSize: 10 } },
    yAxis: [
      { type: 'value', name: 'чел.', nameTextStyle: { fontSize: 9 }, axisLabel: { fontSize: 10 } },
      { type: 'value', name: '%', nameTextStyle: { fontSize: 9 }, axisLabel: { fontSize: 10, formatter: '{value}%' } },
    ],
    series: [
      { name: 'Численность', type: 'line', data: ms.map(m => monthValue(m.key, 'total_employees')), smooth: true, symbolSize: 6, connectNulls: true, lineStyle: { width: 2.5 }, itemStyle: { color: c[0 % c.length] } },
      { name: 'Принято', type: 'line', data: ms.map(m => m.hired_count), smooth: true, symbolSize: 6, itemStyle: { color: c[1 % c.length] } },
      { name: 'Уволено', type: 'line', data: ms.map(m => m.fired_count), smooth: true, symbolSize: 6, itemStyle: { color: c[2 % c.length] } },
      { name: 'Текучесть', type: 'line', yAxisIndex: 1, data: ms.map(m => monthValue(m.key, 'turnover')), smooth: true, symbolSize: 6, connectNulls: true, lineStyle: { type: 'dashed', width: 2, color: c[3 % c.length] }, itemStyle: { color: c[3 % c.length] } },
    ],
  }
})

/** Headcount per department, derived from hire/fire events across all months. */
const departmentRows = computed(() => {
  const acc = new Map()
  for (const m of months.value) {
    for (const e of (m.employees || [])) {
      const dept = e.department || 'Без отдела'
      const cur = acc.get(dept) || { hired: 0, fired: 0 }
      if (e.event_type === 'fired') cur.fired += 1
      else cur.hired += 1
      acc.set(dept, cur)
    }
  }
  return [...acc.entries()]
    .map(([name, v]) => ({ name, ...v, net: v.hired - v.fired }))
    .sort((a, b) => a.net - b.net)
})

// Same semantic green/red as the hire/fire chart above — positive vs. negative
// headcount movement, not a decorative series.
const departmentsOpt = computed(() => {
  const rows = departmentRows.value
  if (!rows.length) return { title: { text: 'Нет данных по подразделениям', left: 'center', top: 'middle', textStyle: { fontSize: 12, color: '#8a8880' } } }
  const tl = palette.trafficLight
  return {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { data: ['Принято','Уволено'], bottom: 0, textStyle: { fontSize: 10 } },
    grid: { left: 110, right: 20, top: 10, bottom: 40 },
    xAxis: { type: 'value', minInterval: 1, axisLabel: { fontSize: 10 } },
    yAxis: { type: 'category', data: rows.map(r => r.name), axisLabel: { fontSize: 10, width: 100, overflow: 'truncate' } },
    series: [
      { name: 'Принято', type: 'bar', stack: 'total', data: rows.map(r => r.hired), itemStyle: { color: tl.green } },
      { name: 'Уволено', type: 'bar', stack: 'total', data: rows.map(r => r.fired), itemStyle: { color: tl.red } },
    ],
  }
})

// Each funnel stage maps to the metrics that describe it, so a click can filter
// the metrics table down to the relevant rows.
const FUNNEL_STAGES = [
  { label: 'Открытые позиции', keys: ['projects_count'] },
  { label: 'Кандидаты (резюме)', keys: ['resumes_screened'] },
  { label: 'Интервью с HR', keys: ['interviews_hr'] },
  { label: 'Интервью с заказчиком', keys: ['interviews_hm'] },
  { label: 'Принятые офферы', keys: ['offers_accepted_pct'] },
  { label: 'Нанято', keys: ['hired_count'] },
]

const funnelRows = computed(() => {
  const mk = singleMonth.value?.key || ''
  return FUNNEL_STAGES.map(s => {
    let value = 0
    if (s.keys[0] === 'offers_accepted_pct') {
      // Only the acceptance rate is tracked; apply it to the interviews with the hiring manager.
      const pct = monthValue(mk, 'offers_accepted_pct')
      const base = monthValue(mk, 'interviews_hm') || 0
      value = pct === null ? 0 : Math.round(base * pct / 100)
    } else if (s.keys[0] === 'hired_count') {
      value = funnelValue(mk, 'hired_count', singleMonth.value?.hired_count ?? 0)
    } else {
      value = monthValue(mk, s.keys[0]) ?? 0
    }
    return { ...s, value: Math.round(value) }
  })
})

// The funnel always reads as a gradient of the palette's traffic-light green,
// regardless of the active chart-colour preset, so its shape stays legible.
const funnelOpt = computed(() => {
  const shades = funnelGreenShades(palette.trafficLight.green, funnelRows.value.length)
  return {
    tooltip: { trigger: 'item', formatter: '{b}: {c}' },
    series: [{
      type: 'funnel', left: '5%', right: '5%', top: 10, bottom: 10,
      minSize: '18%', sort: 'none', gap: 2,
      label: { show: true, position: 'inside', fontSize: 10, formatter: '{b}: {c}' },
      data: funnelRows.value.map((r, i) => ({
        name: r.label, value: r.value,
        itemStyle: { color: shades[i] },
      })),
    }],
  }
})

/** Green/yellow/red metric counts per month of the period, stacked. */
const lightStackOpt = computed(() => {
  const ms = rangeMonths.value
  const count = (key, light) => (analytics.value[key]?.metrics || []).filter(m => m.light === light).length
  const tl = palette.trafficLight
  return {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { data: ['Норма','Внимание','Критично'], bottom: 0, textStyle: { fontSize: 10 } },
    grid: { left: 35, right: 12, top: 12, bottom: 40 },
    xAxis: { type: 'category', data: ms.map(m => m.label), axisLabel: { fontSize: 10 } },
    yAxis: { type: 'value', minInterval: 1, axisLabel: { fontSize: 10 } },
    series: [
      { name: 'Норма', type: 'bar', stack: 'l', data: ms.map(m => count(m.key, 'green')), itemStyle: { color: tl.green } },
      { name: 'Внимание', type: 'bar', stack: 'l', data: ms.map(m => count(m.key, 'yellow')), itemStyle: { color: tl.yellow } },
      { name: 'Критично', type: 'bar', stack: 'l', data: ms.map(m => count(m.key, 'red')), itemStyle: { color: tl.red } },
    ],
  }
})

// ---------- Chart click navigation ----------

function monthKeyByLabel(label) {
  return rangeMonths.value.find(m => m.label === label)?.key || ''
}

/** Clicking a month in a chart narrows the period down to that single month. */
function setSingleMonth(key) { if (key) setRange(key, key) }

function onHireFireClick(params) {
  const key = monthKeyByLabel(params?.name)
  if (!key) return
  const query = { month: key }
  if (params.seriesName === 'Принято') query.event_type = 'hired'
  if (params.seriesName === 'Уволено') query.event_type = 'fired'
  router.push({ path: '/registry', query })
}

function onTurnoverClick(params) {
  const key = turnoverMonths.value[params?.dataIndex]?.key || monthKeyByLabel(params?.name)
  if (key) setSingleMonth(key)
}

function onDynamicsClick(params) {
  setSingleMonth(monthKeyByLabel(params?.name))
}

function onDepartmentClick(params) {
  const dept = params?.name
  if (!dept) return
  router.push({ path: '/registry', query: dept === 'Без отдела' ? {} : { department: dept } })
}

function onFunnelClick(params) {
  const stage = FUNNEL_STAGES.find(s => s.label === params?.name)
  if (!stage) return
  stageFilter.value = stageFilter.value?.label === stage.label ? null : stage
  lightFilter.value = ''
  scrollToMetrics()
}

function onLightStackClick(params) {
  setSingleMonth(monthKeyByLabel(params?.name))
  const light = { 'Норма': 'green', 'Внимание': 'yellow', 'Критично': 'red' }[params?.seriesName]
  if (light) {
    lightFilter.value = lightFilter.value === light ? '' : light
    stageFilter.value = null
    scrollToMetrics()
  }
}

// Widget key → its option/click handler, so the template renders every chart
// through one <e-chart> and the gear popover can reach the raw option.
const CHART_OPTIONS = {
  move: moveOpt,
  hire_fire: hireFireOpt,
  turnover: turnoverOpt,
  dynamics: dynamicsOpt,
  departments: departmentsOpt,
  funnel: funnelOpt,
  light_stack: lightStackOpt,
}

const CHART_CLICKS = {
  hire_fire: onHireFireClick,
  turnover: onTurnoverClick,
  dynamics: onDynamicsClick,
  departments: onDepartmentClick,
  funnel: onFunnelClick,
  light_stack: onLightStackClick,
}

// ---------- Data loading ----------

async function loadData() {
  loading.value = true
  try {
    months.value = await api.get('/hr/months')
    if (months.value.length) allRange()
    await Promise.all([loadAllAnalytics(), loadRange(), loadLayout()])
  } finally { loading.value = false }
}

async function loadAllAnalytics() {
  await Promise.all(months.value.map(async m => {
    if (!analytics.value[m.key]) {
      try {
        analytics.value[m.key] = await api.get(`/hr/analytics/month/${m.key}`)
      } catch (e) { console.error(e) }
    }
  }))
}

watch([fromMonth, toMonth], () => { lightFilter.value = ''; stageFilter.value = null; loadRange() })

function openNewMonth() { showNewMonth.value = true }

function openEditNotes() {
  notesForm.value = singleMonth.value?.notes || ''
  editingNotes.value = true
}

async function saveNotes() {
  if (!singleMonth.value) return
  try {
    await api.put(`/hr/months/${singleMonth.value.key}`, { notes: notesForm.value })
    months.value = await api.get('/hr/months')
    editingNotes.value = false
  } catch { /* the API layer already surfaced the reason as a toast */ }
}

async function createMonth() {
  try {
    const key = `${newMonthForm.value.year}-${String(newMonthForm.value.month).padStart(2,'0')}`
    await api.post('/hr/months', { year: newMonthForm.value.year, month: newMonthForm.value.month, notes: newMonthForm.value.notes })
    months.value = await api.get('/hr/months')
    setRange(key, key)
    showNewMonth.value = false
    newMonthForm.value = { year: new Date().getFullYear(), month: new Date().getMonth()+1, notes: '' }
    await Promise.all([loadAllAnalytics(), loadRange()])
  } catch { /* the API layer already surfaced the reason as a toast */ }
}

// Row equalization first (it sets the row min-heights), then the charts stretch
// to whatever height their card got.
watch([visibleWidgets, currentAnalytics, months, rangeMonths], () => {
  nextTick(() => {
    equalize()
    requestAnimationFrame(() => requestAnimationFrame(stretchCharts))
  })
}, { deep: true })

onMounted(loadData)
</script>
