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
      <div style="flex:1"></div>
      <button v-if="canEdit" class="btn btn-g" @click="openNewMonth">+ Месяц</button>
      <button class="btn btn-g" @click="showSettings=true">⚙ Настройки дашборда</button>
    </div>

    <!-- Widget grid: order, size and visibility come from the saved layout.
         Notes is single-month only, so it disappears for a multi-month range. -->
    <div class="wgrid" ref="gridEl">
      <div
        v-for="w in shownWidgets"
        :key="w.key"
        class="wcell"
        :class="['size-' + w.size, { dragging: dragKey === w.key, 'drop-target': overKey === w.key, resizing: resizeKey === w.key }]"
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
              <div class="kpi-sub" style="display:flex;gap:12px">
                <span style="color:var(--c-ok);font-weight:600">↑ нанято {{ currentAnalytics.hired }}</span>
                <span style="color:var(--c-err);font-weight:600">↓ уволено {{ currentAnalytics.fired }}</span>
              </div>
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
              <div class="kpi-lbl">Увольнения</div>
              <div class="kpi-val" style="color:var(--c-err)">{{ currentAnalytics.fired }}</div>
              <div class="kpi-sub">
                <span style="color:var(--c-err)">по инициативе компании: {{ fireSplit.company }}</span>
                <span class="td-muted">·</span>
                <span style="color:var(--c-warn)">по собственному: {{ fireSplit.own }}</span>
              </div>
              <div class="kpi-sub" v-if="prevAnalytics">
                <span class="dtrend" :class="trendClass(currentAnalytics.fired, prevAnalytics.fired, 'lower')">
                  {{ trendArrow(currentAnalytics.fired, prevAnalytics.fired) }} {{ deltaText(currentAnalytics.fired - prevAnalytics.fired) }}
                </span>
                к пред. периоду
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
              <template v-else-if="w.key === 'employees'">Сотрудники — {{ rangeLabel }}</template>
              <template v-else>{{ title(w.key) }}</template>
            </span>
            <span v-if="w.key === 'metrics'" style="display:flex;gap:6px">
              <router-link v-if="canEnterData" class="btn btn-g" style="font-size:.75rem;padding:4px 8px" :to="dataEntryLink">Данные</router-link>
            </span>
            <button v-if="w.key === 'notes' && canEdit" class="btn btn-g" style="font-size:.75rem;padding:4px 8px" @click="openEditNotes">✎ Изменить</button>
            <!-- Drag-to-resize handles: height (bottom edge, free) and width
                 (right edge, snaps to the preset spans). -->
            <template v-if="CHART_OPTIONS[w.key]">
              <div class="rz rz-h" title="Потяните, чтобы изменить высоту"
                   @mousedown="startResize(w, 'h', $event)"></div>
              <div class="rz rz-w" title="Потяните, чтобы изменить ширину"
                   @mousedown="startResize(w, 'w', $event)"></div>
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
            :fill="true"
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

          <!-- Employee events across the whole selected period -->
          <div v-else-if="w.key === 'employees'" class="twrap">
            <div class="tscroll">
              <table>
                <thead><tr><th>Тип</th><th>ФИО</th><th>Отдел</th><th>Должность</th><th>Причина увольнения</th><th>Дата</th></tr></thead>
                <tbody>
                  <tr v-for="e in periodEmployees" :key="e.id">
                    <td><span class="sb" :class="e.event_type==='hired'?'s-hired':'s-fired'">{{ e.event_type==='hired'?'Приём':'Увольнение' }}</span></td>
                    <td class="td-p">{{ e.full_name }}</td>
                    <td class="td-muted">{{ e.department || '—' }}</td>
                    <td class="td-muted">{{ e.position || '—' }}</td>
                    <td class="td-muted">{{ e.event_type==='fired' ? (e.termination_reason || 'не указана') : 'N/A' }}</td>
                    <td class="td-muted">{{ formatDate(e.event_date) }}</td>
                  </tr>
                  <tr v-if="!periodEmployees.length"><td colspan="6" class="tempty">Нет событий</td></tr>
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
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
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

// `kind` drives the default sizes.
const WIDGET_CATALOG = [
  { key: 'kpi', title: 'KPI-карточки', size: 'large', kind: 'kpi' },
  { key: 'move', title: 'Увольнения по инициативе', size: 'medium', kind: 'chart' },
  { key: 'hire_fire', title: 'Приём / увольнение по месяцам', size: 'medium', kind: 'chart' },
  { key: 'turnover', title: 'Текучесть кадров (%)', size: 'medium', kind: 'chart' },
  { key: 'funnel', title: 'Воронка найма', size: 'medium', kind: 'chart' },
  { key: 'dynamics', title: 'Динамика по месяцам', size: 'large', kind: 'wide_chart' },
  { key: 'departments', title: 'Структура по подразделениям', size: 'wide', kind: 'wide_chart' },
  { key: 'notes', title: 'Заметки месяца', size: 'small', kind: 'chart' },
  { key: 'light_stack', title: 'Распределение метрик по светофору', size: 'large', kind: 'wide_chart' },
  { key: 'metrics', title: 'Метрики периода', size: 'large', kind: 'table' },
  { key: 'employees', title: 'Сотрудники периода', size: 'large', kind: 'table' },
]

const { layout, ordered, visibleWidgets, title, setSettings,
        load: loadLayout, save: saveLayout, saveQuiet, resetLayout, move } =
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
// Month-bound widgets (notes, funnel, data-entry link) follow the last month of the range.
const singleMonth = computed(() => rangeMonths.value.at(-1) || null)
const isSingleMonth = computed(() => rangeMonths.value.length <= 1)
// Notes only make sense for one month — hide the widget for a multi-month range.
const shownWidgets = computed(() =>
  visibleWidgets.value.filter(w => w.key !== 'notes' || isSingleMonth.value))
// All employee events of the selected period, for the employees widget.
const periodEmployees = computed(() =>
  rangeMonths.value.flatMap(m => m.employees || [])
    .sort((a, b) => String(a.event_date).localeCompare(String(b.event_date))))
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
  if (unit === '%') {
    // At most two decimals in KPI/cards, without trailing zeros.
    const n = Math.round(val * 100) / 100
    return (Number.isInteger(n) ? String(n) : n.toFixed(2).replace(/0$/, '')).replace('.', ',') + '%'
  }
  if (unit === 'дн.') return val.toFixed(1).replace('.', ',') + ' дн.'
  if (unit === 'чел.' || unit === 'шт.') return Math.round(val) + ' ' + unit
  return String(val).replace('.', ',')
}

// Fired split by dismissal initiative across the whole period.
const fireSplit = computed(() => {
  const g = (k) => (currentAnalytics.value?.metrics || []).find(m => m.key === k)?.value ?? 0
  return { company: Math.round(g('fired_by_company')), own: Math.round(g('fired_by_own')) }
})

function formatDate(d) { return new Date(d).toLocaleDateString('ru-RU') }

function deltaText(diff) {
  if (!diff) return '0'
  // Deltas also read as percentages, so keep at most two decimals.
  const r = Math.round(diff * 100) / 100
  return (r > 0 ? '+' : '') + String(r).replace('.', ',')
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

// The natural (minimum) chart height: user-dragged height or the size default.
// Actual height comes from flex — the chart fills the card, and the card fills
// the equalized row (see .echart-fill in style.css).
function chartHeight(w) { return chartHeightOf(w.settings, baseHeight(w.size)) }
function chartOption(w) { return applyChartSettings(CHART_OPTIONS[w.key].value, w.settings) }
function chartColors(w) { return w.settings?.colors?.length ? w.settings.colors : null }

const SIZES = ['small', 'medium', 'wide', 'large']
// Column spans mirrored from .wcell.size-* in style.css.
const SPANS = { small: 2, medium: 3, wide: 4, large: 6 }

// ---------- Drag-to-resize ----------

// Pulling the bottom edge changes this chart's height (and with it its row);
// pulling the right edge snaps between the preset widths.
const resizeKey = ref('')
let resizeCtx = null

function startResize(w, mode, ev) {
  ev.preventDefault()
  ev.stopPropagation()
  resizeKey.value = w.key
  resizeCtx = { mode, startY: ev.clientY, startX: ev.clientX, key: w.key }
  window.addEventListener('mousemove', onResizeMove)
  window.addEventListener('mouseup', onResizeEnd)
}

/** Cap the saved heights of the chart widgets sharing `key`'s grid row at `max`.
 *  Cells are grouped by their rounded offsetTop, mirroring the row equalizer. */
function clampRowHeights(key, max) {
  const grid = gridEl.value
  const cell = grid?.querySelector(`[data-cell="${key}"]`)
  if (!grid || !cell) return
  const top = Math.round(cell.offsetTop)
  const keys = new Set()
  for (const el of grid.querySelectorAll('.wcell')) {
    if (Math.round(el.offsetTop) === top && el.dataset.cell) keys.add(el.dataset.cell)
  }
  keys.delete(key)
  if (!keys.size) return
  for (const r of layout.value) {
    if (!keys.has(r.key) || !CHART_OPTIONS[r.key]) continue
    const h = chartHeightOf(r.settings, baseHeight(r.size))
    if (h > max) r.settings = { ...(r.settings || {}), height: max }
  }
}

function onResizeMove(ev) {
  const ctx = resizeCtx
  if (!ctx) return
  const row = layout.value.find(x => x.key === ctx.key)
  if (!row) return
  if (ctx.mode === 'h') {
    const delta = ev.clientY - ctx.startY
    if (Math.abs(delta) < 3) return
    const cur = chartHeightOf(row.settings, baseHeight(row.size))
    const next = Math.min(Math.max(cur + delta, HEIGHT_MIN), HEIGHT_MAX)
    ctx.startY = ev.clientY
    row.settings = { ...(row.settings || {}), height: next }
    // Shrinking must actually shrink the row: a previously enlarged neighbour
    // would otherwise keep the row (and this chart) pinned tall. Cap the
    // neighbours' saved heights to the dragged target, in the same grid row.
    if (next < cur) clampRowHeights(ctx.key, next)
  } else {
    const grid = gridEl.value
    if (!grid) return
    // A full grid-column width of pointer travel per size step, so one drag
    // gesture moves exactly one size at a time.
    const step = grid.clientWidth / 6
    const delta = ev.clientX - ctx.startX
    if (Math.abs(delta) < step) return
    ctx.startX = ev.clientX
    const dir = delta > 0 ? 1 : -1
    const idx = SIZES.indexOf(row.size)
    row.size = SIZES[Math.min(Math.max(idx + dir, 0), SIZES.length - 1)]
  }
}

function onResizeEnd() {
  resizeKey.value = ''
  resizeCtx = null
  window.removeEventListener('mousemove', onResizeMove)
  window.removeEventListener('mouseup', onResizeEnd)
  saveQuiet()
  // Re-run the row equalizer after the resize settles — the passes queued by
  // the mid-drag mutations can complete before the final chart minHeight is
  // rendered, leaving a stale (too tall) row pin.
  requestAnimationFrame(() => requestAnimationFrame(equalize))
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

/** Dismissals split by initiative: company decisions vs. employee's own will. */
const moveOpt = computed(() => {
  const ms = rangeMonths.value
  const tl = palette.trafficLight
  return {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { data: ['По инициативе компании', 'По собственному желанию'], bottom: 0, textStyle: { fontSize: 10 } },
    grid: { left: 35, right: 12, top: 12, bottom: 46 },
    xAxis: { type: 'category', data: ms.map(m => m.label), axisLabel: { fontSize: 10 } },
    yAxis: { type: 'value', minInterval: 1, axisLabel: { fontSize: 10 } },
    series: [
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

/** Headcount per department at the END of the selected period: cumulative
 *  hires minus fires from the first month of data up to the range end.
 *  Departments that ended up empty are dropped — that was the noise. */
const departmentRows = computed(() => {
  const acc = new Map()
  for (const m of months.value) {
    if (m.key > toMonth.value) break
    for (const e of (m.employees || [])) {
      const dept = e.department || 'Без отдела'
      const cur = acc.get(dept) || 0
      acc.set(dept, cur + (e.event_type === 'fired' ? -1 : 1))
    }
  }
  return [...acc.entries()]
    .map(([name, count]) => ({ name, count }))
    .filter(r => r.count > 0)
    .sort((a, b) => b.count - a.count)
})

// A plain headcount structure: one series, sorted largest first.
const departmentsOpt = computed(() => {
  const rows = departmentRows.value
  if (!rows.length) return { title: { text: 'Нет данных по подразделениям', left: 'center', top: 'middle', textStyle: { fontSize: 12, color: '#8a8880' } } }
  const color = palette.chartColors[0]
  return {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 130, right: 30, top: 10, bottom: 20 },
    xAxis: { type: 'value', minInterval: 1, axisLabel: { fontSize: 10 } },
    yAxis: { type: 'category', inverse: true, data: rows.map(r => r.name), axisLabel: { fontSize: 10, width: 120, overflow: 'truncate' } },
    series: [
      { name: 'Численность', type: 'bar', data: rows.map(r => r.count), itemStyle: { color }, barMaxWidth: 22,
        label: { show: true, position: 'right', fontSize: 10 } },
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
  const ms = rangeMonths.value
  // A range sums the stages across its months; a single month is the trivial
  // case of the same sum. The acceptance rate is averaged and applied to the
  // summed hiring-manager interviews.
  const sum = (key) => ms.reduce((a, m) => a + (monthValue(m.key, key) ?? 0), 0)
  const hiredSum = () => ms.reduce((a, m) => a + (monthValue(m.key, 'hired_count') ?? m.hired_count ?? 0), 0)
  return FUNNEL_STAGES.map(s => {
    let value = 0
    if (s.keys[0] === 'offers_accepted_pct') {
      const pcts = ms.map(m => monthValue(m.key, 'offers_accepted_pct')).filter(v => v !== null)
      const pct = pcts.length ? pcts.reduce((a, b) => a + b, 0) / pcts.length : null
      value = pct === null ? 0 : Math.round(sum('interviews_hm') * pct / 100)
    } else if (s.keys[0] === 'hired_count') {
      value = hiredSum()
    } else {
      value = sum(s.keys[0])
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

// Row equalization gives every widget in a grid row the height of the tallest
// one; the flex-filled chart then follows the card automatically. Extra rAF
// passes let a just-changed chart minHeight settle before the row re-measures
// (a single pass can measure mid-update and pin a stale height).
watch([visibleWidgets, layout, currentAnalytics, months, rangeMonths], () => {
  nextTick(() => {
    equalize()
    requestAnimationFrame(() => {
      equalize()
      requestAnimationFrame(equalize)
    })
  })
}, { deep: true })

onMounted(loadData)
</script>
