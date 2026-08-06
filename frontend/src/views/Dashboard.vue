<template>
  <div v-if="loading" class="tempty">Загрузка данных…</div>
  <template v-else>
    <!-- Month tabs -->
    <div class="mtabs">
      <button v-for="m in months" :key="m.key" class="mtab" :class="{active: m.key===activeMonth}" @click="activeMonth=m.key">
        {{ m.label }}
        <span style="font-size:10px;opacity:.7">+{{m.hired_count}}/-{{m.fired_count}}</span>
        <span v-if="canDeleteMonth && m.key===activeMonth" class="mtab-del" title="Удалить месяц"
              @click.stop="askDeleteMonth(m)">✕</span>
      </button>
      <button v-if="canEdit" class="mtab" @click="openNewMonth" style="border-style:dashed">+ Месяц</button>
    </div>

    <div class="filters">
      <div class="tinfo" style="flex:1;margin:0">
        Виджетов на дашборде: {{ visibleWidgets.length }} из {{ layout.length }}
      </div>
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
        @dragover="dragOver(w.key, $event)"
        @drop="onDrop(w.key, $event)"
      >
        <!-- KPI cards -->
        <template v-if="w.key === 'kpi'">
          <div class="ctitle-row">
            <span class="whandle" draggable="true" title="Перетащите, чтобы изменить порядок"
                  @dragstart="dragStart(w.key, $event)" @dragend="dragEnd">⠿</span>
            <span class="ctitle">{{ title(w.key) }}</span>
          </div>
          <div class="kpi-grid" style="margin-bottom:0" v-if="currentAnalytics">
            <div class="kpi">
              <div class="kpi-lbl">Принято</div>
              <div class="kpi-val" style="color:var(--c-ok)">{{ currentAnalytics.hired }}</div>
              <div class="kpi-sub" v-if="prevAnalytics">
                <span class="dtrend" :class="trendClass(currentAnalytics.hired, prevAnalytics.hired, 'higher')">
                  {{ trendArrow(currentAnalytics.hired, prevAnalytics.hired) }}
                  {{ deltaText(currentAnalytics.hired - prevAnalytics.hired) }}
                </span>
                к пред. месяцу
              </div>
            </div>
            <div class="kpi">
              <div class="kpi-lbl">Уволено</div>
              <div class="kpi-val" style="color:var(--c-err)">{{ currentAnalytics.fired }}</div>
              <div class="kpi-sub" v-if="prevAnalytics">
                <span class="dtrend" :class="trendClass(currentAnalytics.fired, prevAnalytics.fired, 'lower')">
                  {{ trendArrow(currentAnalytics.fired, prevAnalytics.fired) }}
                  {{ deltaText(currentAnalytics.fired - prevAnalytics.fired) }}
                </span>
                к пред. месяцу
              </div>
            </div>
            <div class="kpi">
              <div class="kpi-lbl">Чистый прирост</div>
              <div class="kpi-val" :style="{color: currentAnalytics.net>=0?'var(--c-ok)':'var(--c-err)'}">{{ currentAnalytics.net>=0?'+':'' }}{{ currentAnalytics.net }}</div>
            </div>
            <div class="kpi" v-for="m in topMetrics" :key="m.key" :class="'light-'+m.light">
              <div class="kpi-lbl">{{ m.label }}</div>
              <div class="kpi-val">{{ fmt(m.value, m.unit) }}</div>
              <div class="kpi-sub"><span class="light-dot" :class="'light-'+m.light"></span> {{ lightLabel(m.light) }}</div>
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
                Метрики {{ currentMonth?.label }}
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
              <template v-else>{{ title(w.key) }}</template>
            </span>
            <span v-if="w.key === 'metrics'" style="display:flex;gap:6px">
              <router-link v-if="canEnterData" class="btn btn-g" style="font-size:.75rem;padding:4px 8px" :to="dataEntryLink">Данные месяца</router-link>
              <button v-if="canEdit" class="btn btn-g" style="font-size:.75rem;padding:4px 8px" @click="openEditMetrics">✎ Изменить</button>
            </span>
            <button v-if="w.key === 'notes' && canEdit" class="btn btn-g" style="font-size:.75rem;padding:4px 8px" @click="openEditNotes">✎ Изменить</button>
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

          <!-- Metrics table -->
          <div v-else-if="w.key === 'metrics'" class="twrap" ref="metricsCard">
            <div class="tscroll">
              <table>
                <thead><tr><th>Метрика</th><th>Значение</th><th>Статус</th></tr></thead>
                <tbody>
                  <tr v-for="m in visibleMetrics" :key="m.key" :class="{ 'row-unfilled': !m.filled }">
                    <td class="td-p">{{ m.label }}</td>
                    <td class="td-mono">{{ fmt(m.value, m.unit) }}</td>
                    <td><span class="light-dot" :class="'light-'+m.light"></span> {{ statusLabel(m) }}</td>
                  </tr>
                  <tr v-if="!visibleMetrics.length"><td colspan="3" class="tempty">Нет метрик</td></tr>
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
            <div v-else class="notes-card">{{ currentMonth?.notes || 'Нет заметок' }}</div>
          </template>

          <!-- Employees of the month -->
          <div v-else-if="w.key === 'employees'" class="twrap">
            <div class="tscroll">
              <table>
                <thead><tr><th>Тип</th><th>ФИО</th><th>Дата</th></tr></thead>
                <tbody>
                  <tr v-for="e in (currentMonth?.employees || [])" :key="e.id">
                    <td><span class="sb" :class="e.event_type==='hired'?'s-hired':'s-fired'">{{ e.event_type==='hired'?'Приём':'Увольнение' }}</span></td>
                    <td class="td-p">{{ e.full_name }}</td>
                    <td class="td-muted">{{ formatDate(e.event_date) }}</td>
                  </tr>
                  <tr v-if="!currentMonth?.employees?.length"><td colspan="3" class="tempty">Нет событий</td></tr>
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

    <!-- Edit metrics modal -->
    <div v-if="showEditMetrics" class="modal-overlay" @click.self="showEditMetrics=false">
      <div class="modal">
        <div class="mh"><span class="mt">Метрики — {{ currentMonth?.label }}</span><button class="mc" @click="showEditMetrics=false">✕</button></div>
        <div v-for="m in editMetricsForm" :key="m.metric_key" class="fgi" style="margin-bottom:8px;flex-direction:row;align-items:center;gap:8px">
          <span style="flex:1;font-size:.8125rem">{{ m.label }}</span>
          <input class="fi" type="number" step="0.01" v-model="m.numeric_value" style="width:100px">
          <span style="font-size:.75rem;color:var(--c-muted);width:30px">{{ m.unit }}</span>
        </div>
        <div class="fac"><button class="btn btn-g" @click="showEditMetrics=false">Отмена</button><button class="btn btn-p" @click="saveMetrics">Сохранить</button></div>
      </div>
    </div>

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

    <!-- Delete month confirmation -->
    <div v-if="deleteTarget" class="modal-overlay" @click.self="deleteTarget=null">
      <div class="modal modal-sm">
        <div class="mh"><span class="mt">Удалить месяц</span><button class="mc" @click="deleteTarget=null">✕</button></div>
        <p style="font-size:.8125rem;line-height:1.6">
          Удалить «{{ deleteTarget.label }}»? Будут удалены все метрики,
          события приёма и увольнения, а также заметки этого месяца.
          Действие нельзя отменить.
        </p>
        <div class="fac">
          <button class="btn btn-g" @click="deleteTarget=null">Отмена</button>
          <button class="btn btn-d" @click="confirmDeleteMonth">Удалить</button>
        </div>
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
import { applyChartSettings, chartHeightOf } from '../composables/useChartSettings.js'
import { useRowEqualize } from '../composables/useRowEqualize.js'

const auth = useAuthStore()
const palette = usePaletteStore()
const router = useRouter()
const canEdit = computed(() => auth.canEdit)
const loading = ref(true)
const months = ref([])
const activeMonth = ref('')
const analytics = ref({})
const showEditMetrics = ref(false)
const editMetricsForm = ref([])
const editingNotes = ref(false)
const notesForm = ref('')
const showNewMonth = ref(false)
const showSettings = ref(false)
const newMonthForm = ref({ year: 2026, month: new Date().getMonth()+1, notes: '' })
const monthNames = ['Январь','Февраль','Март','Апрель','Май','Июнь','Июль','Август','Сентябрь','Октябрь','Ноябрь','Декабрь']

const metricsCard = ref(null)
const lightFilter = ref('')
const stageFilter = ref(null)

// `kind` drives «Авторасположение»: kpi → 1/3, chart → 1/2, wide_chart → 2/3, table → full.
const WIDGET_CATALOG = [
  { key: 'kpi', title: 'KPI-карточки', size: 'large', kind: 'kpi' },
  { key: 'hire_fire', title: 'Приём / увольнение по месяцам', size: 'medium', kind: 'chart' },
  { key: 'turnover', title: 'Текучесть кадров (%)', size: 'medium', kind: 'chart' },
  { key: 'dynamics', title: 'Динамика по месяцам', size: 'large', kind: 'wide_chart' },
  { key: 'departments', title: 'Структура по подразделениям', size: 'medium', kind: 'wide_chart' },
  { key: 'funnel', title: 'Воронка найма', size: 'medium', kind: 'chart' },
  { key: 'light_stack', title: 'Распределение метрик по светофору', size: 'large', kind: 'wide_chart' },
  { key: 'traffic_pie', title: 'Светофор метрик', size: 'small', kind: 'chart' },
  { key: 'metrics', title: 'Метрики месяца', size: 'medium', kind: 'table' },
  { key: 'notes', title: 'Заметки месяца', size: 'small', kind: 'chart' },
  { key: 'employees', title: 'Сотрудники месяца', size: 'small', kind: 'table' },
]

const { layout, ordered, visibleWidgets, title, settingsOf, setSettings,
        load: loadLayout, save: saveLayout, resetLayout, autoLayout, move } =
  useWidgetLayout('hr', WIDGET_CATALOG)
const { dragKey, overKey, dragStart, dragOver, drop: onDrop, dragEnd } = useDragReorder(move)
const { gridEl, equalize } = useRowEqualize()

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
function chartHeight(w) { return chartHeightOf(w.settings, baseHeight(w.size)) }
function chartOption(w) { return applyChartSettings(CHART_OPTIONS[w.key].value, w.settings) }
function chartColors(w) { return w.settings?.colors?.length ? w.settings.colors : null }

async function onSaveLayout() {
  if (await saveLayout()) showSettings.value = false
}

async function onResetLayout() {
  await resetLayout()
  showSettings.value = false
}

const currentMonth = computed(() => months.value.find(m => m.key === activeMonth.value))
const currentAnalytics = computed(() => analytics.value[activeMonth.value])
const prevAnalytics = computed(() => {
  const i = months.value.findIndex(m => m.key === activeMonth.value)
  return i > 0 ? analytics.value[months.value[i - 1].key] : null
})

const LIGHT_LABELS = { green: 'Норма', yellow: 'Внимание', red: 'Критично' }
function lightLabel(light) { return LIGHT_LABELS[light] || '—' }
function statusLabel(m) { return m.filled ? lightLabel(m.light) : 'Не заполнено' }

const visibleMetrics = computed(() => {
  let list = currentAnalytics.value?.metrics || []
  if (lightFilter.value) list = list.filter(m => m.light === lightFilter.value)
  if (stageFilter.value) list = list.filter(m => stageFilter.value.keys.includes(m.key))
  return list
})

const unfilledCount = computed(() => (currentAnalytics.value?.metrics || []).filter(m => !m.filled).length)
const canEnterData = computed(() => auth.canEditMetrics('hr'))
const dataEntryLink = computed(() => ({ path: '/hr/data-entry', query: activeMonth.value ? { month: activeMonth.value } : {} }))

function scrollToMetrics() {
  const el = Array.isArray(metricsCard.value) ? metricsCard.value[0] : metricsCard.value
  el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
}

/** Clicking a donut segment filters the metrics table to that segment's status. */
function onLightClick(params) {
  const hit = currentAnalytics.value?.metrics?.find(m => m.label === params?.name)
  if (!hit) return
  lightFilter.value = lightFilter.value === hit.light ? '' : hit.light
  stageFilter.value = null
  scrollToMetrics()
}

const topMetrics = computed(() => {
  if (!currentAnalytics.value) return []
  const keys = ['turnover', 'avg_time_to_fill', 'offers_accepted_pct', 'probation_pass_rate', 'probation_pass_rate_adaptation']
  return currentAnalytics.value.metrics.filter(m => keys.includes(m.key)).slice(0, 5)
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
  return (diff > 0 ? '+' : '') + diff
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

function metricValue(monthKey, metricKey) {
  const hit = analytics.value[monthKey]?.metrics?.find(m => m.key === metricKey)
  return hit && hit.value !== null && hit.value !== undefined ? hit.value : null
}

// Hires/fires are semantic (good/bad), so they always use the palette's
// traffic-light green/red — never the decorative chart palette. Only the
// exact shade ("softness") follows the active preset.
const hireFireOpt = computed(() => {
  const labels = months.value.map(m => m.label)
  const hired = months.value.map(m => m.hired_count)
  const fired = months.value.map(m => m.fired_count)
  const tl = palette.trafficLight
  return {
    tooltip: { trigger: 'axis' },
    legend: { data: ['Принято','Уволено'], bottom: 0, textStyle: { fontSize: 11 } },
    grid: { left: 35, right: 12, top: 12, bottom: 40 },
    xAxis: { type: 'category', data: labels, axisLabel: { fontSize: 10 } },
    yAxis: { type: 'value', minInterval: 1, axisLabel: { fontSize: 10 } },
    series: [
      { name: 'Принято', type: 'bar', data: hired, itemStyle: { color: tl.green } },
      { name: 'Уволено', type: 'bar', data: fired, itemStyle: { color: tl.red } },
    ],
  }
})

/** Months that actually have a turnover value — the x-axis of the turnover chart. */
const turnoverMonths = computed(() => months.value.filter(m => metricValue(m.key, 'turnover') !== null))

// Decorative single-series chart: always takes the first colour of the active
// chart palette, so it repaints whenever the preset changes.
const turnoverOpt = computed(() => {
  const labels = turnoverMonths.value.map(m => m.label)
  const values = turnoverMonths.value.map(m => metricValue(m.key, 'turnover'))
  const color = palette.chartColors[0]
  return {
    tooltip: { trigger: 'axis', valueFormatter: v => v?.toFixed(2) + '%' },
    grid: { left: 40, right: 12, top: 12, bottom: 30 },
    xAxis: { type: 'category', data: labels, axisLabel: { fontSize: 10 } },
    yAxis: { type: 'value', axisLabel: { fontSize: 10, formatter: '{value}%' } },
    series: [{ type: 'line', data: values, smooth: true, symbolSize: 8, lineStyle: { width: 2.5, color }, itemStyle: { color }, areaStyle: { color } }],
  }
})

/** Headcount is not tracked directly, so it is accumulated from hire/fire events. */
// Multi-line, decorative: each series takes the next colour from the active
// chart palette so the whole chart repaints together on a preset change.
const dynamicsOpt = computed(() => {
  const labels = months.value.map(m => m.label)
  const hired = months.value.map(m => m.hired_count)
  const fired = months.value.map(m => m.fired_count)
  let running = 0
  const headcount = months.value.map(m => (running += m.hired_count - m.fired_count))
  const turnover = months.value.map(m => metricValue(m.key, 'turnover'))
  const c = palette.chartColors
  return {
    tooltip: { trigger: 'axis' },
    legend: { data: ['Численность (накопительно)','Принято','Уволено','Текучесть'], bottom: 0, textStyle: { fontSize: 10 } },
    grid: { left: 40, right: 45, top: 14, bottom: 46 },
    xAxis: { type: 'category', data: labels, axisLabel: { fontSize: 10 } },
    yAxis: [
      { type: 'value', name: 'чел.', nameTextStyle: { fontSize: 9 }, axisLabel: { fontSize: 10 } },
      { type: 'value', name: '%', nameTextStyle: { fontSize: 9 }, axisLabel: { fontSize: 10, formatter: '{value}%' } },
    ],
    series: [
      { name: 'Численность (накопительно)', type: 'line', data: headcount, smooth: true, symbolSize: 6, lineStyle: { width: 2.5 }, itemStyle: { color: c[0 % c.length] } },
      { name: 'Принято', type: 'line', data: hired, smooth: true, symbolSize: 6, itemStyle: { color: c[1 % c.length] } },
      { name: 'Уволено', type: 'line', data: fired, smooth: true, symbolSize: 6, itemStyle: { color: c[2 % c.length] } },
      { name: 'Текучесть', type: 'line', yAxisIndex: 1, data: turnover, smooth: true, symbolSize: 6, connectNulls: true, lineStyle: { type: 'dashed', width: 2, color: c[3 % c.length] }, itemStyle: { color: c[3 % c.length] } },
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

const funnelRows = computed(() => FUNNEL_STAGES.map(s => {
  let value = 0
  if (s.keys[0] === 'offers_accepted_pct') {
    // Only the acceptance rate is tracked; apply it to the interviews with the hiring manager.
    const pct = metricValue(activeMonth.value, 'offers_accepted_pct')
    const base = metricValue(activeMonth.value, 'interviews_hm') || 0
    value = pct === null ? 0 : Math.round(base * pct / 100)
  } else if (s.keys[0] === 'hired_count') {
    value = metricValue(activeMonth.value, 'hired_count') ?? currentAnalytics.value?.hired ?? 0
  } else {
    value = metricValue(activeMonth.value, s.keys[0]) ?? 0
  }
  return { ...s, value: Math.round(value) }
}))

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

/** Green/yellow/red metric counts per month, stacked. */
const lightStackOpt = computed(() => {
  const labels = months.value.map(m => m.label)
  const count = (key, light) => (analytics.value[key]?.metrics || []).filter(m => m.light === light).length
  const tl = palette.trafficLight
  return {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { data: ['Норма','Внимание','Критично'], bottom: 0, textStyle: { fontSize: 10 } },
    grid: { left: 35, right: 12, top: 12, bottom: 40 },
    xAxis: { type: 'category', data: labels, axisLabel: { fontSize: 10 } },
    yAxis: { type: 'value', minInterval: 1, axisLabel: { fontSize: 10 } },
    series: [
      { name: 'Норма', type: 'bar', stack: 'l', data: months.value.map(m => count(m.key, 'green')), itemStyle: { color: tl.green } },
      { name: 'Внимание', type: 'bar', stack: 'l', data: months.value.map(m => count(m.key, 'yellow')), itemStyle: { color: tl.yellow } },
      { name: 'Критично', type: 'bar', stack: 'l', data: months.value.map(m => count(m.key, 'red')), itemStyle: { color: tl.red } },
    ],
  }
})

const trafficLightOpt = computed(() => {
  if (!currentAnalytics.value) return {}
  const metrics = currentAnalytics.value.metrics.filter(m => m.light !== 'gray')
  const tl = palette.trafficLight
  const colors = { green: tl.green, yellow: tl.yellow, red: tl.red }
  return {
    tooltip: { trigger: 'item', formatter: '{b}: {c}' },
    series: [{ type: 'pie', radius: ['45%','70%'], center: ['26%','50%'],
      data: metrics.map(m => ({ value: 1, name: m.label, itemStyle: { color: colors[m.light] || tl.neutral } })),
      label: { show: false }, labelLine: { show: false }
    }],
    legend: { type: 'scroll', orient: 'vertical', right: 0, top: 'center',
              textStyle: { fontSize: 8 }, itemWidth: 8, itemHeight: 8, itemGap: 6 },
  }
})

// ---------- Chart click navigation ----------

function monthKeyByLabel(label) {
  return months.value.find(m => m.label === label)?.key || ''
}

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
  if (!key) return
  if (canEnterData.value) router.push({ path: '/hr/data-entry', query: { month: key } })
  else activeMonth.value = key
}

function onDynamicsClick(params) {
  const key = monthKeyByLabel(params?.name)
  if (key) activeMonth.value = key
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
  const key = monthKeyByLabel(params?.name)
  if (key) activeMonth.value = key
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
  hire_fire: hireFireOpt,
  turnover: turnoverOpt,
  dynamics: dynamicsOpt,
  departments: departmentsOpt,
  funnel: funnelOpt,
  light_stack: lightStackOpt,
  traffic_pie: trafficLightOpt,
}

const CHART_CLICKS = {
  hire_fire: onHireFireClick,
  turnover: onTurnoverClick,
  dynamics: onDynamicsClick,
  departments: onDepartmentClick,
  funnel: onFunnelClick,
  light_stack: onLightStackClick,
  traffic_pie: onLightClick,
}

// ---------- Data loading ----------

async function loadData() {
  loading.value = true
  try {
    months.value = await api.get('/hr/months')
    if (!activeMonth.value && months.value.length) activeMonth.value = months.value[0].key
    await loadAnalytics()
    await Promise.all([loadAllAnalytics(), loadLayout()])
  } finally { loading.value = false }
}

async function loadAnalytics() {
  if (!activeMonth.value) return
  if (!analytics.value[activeMonth.value]) {
    try {
      const data = await api.get(`/hr/analytics/month/${activeMonth.value}`)
      analytics.value[activeMonth.value] = data
    } catch (e) { console.error(e) }
  }
}

async function loadAllAnalytics() {
  for (const m of months.value) {
    if (!analytics.value[m.key]) {
      try {
        analytics.value[m.key] = await api.get(`/hr/analytics/month/${m.key}`)
      } catch (e) { console.error(e) }
    }
  }
}

watch(activeMonth, () => { lightFilter.value = ''; stageFilter.value = null; loadAnalytics() })

function openEditMetrics() {
  if (!currentAnalytics.value) return
  editMetricsForm.value = currentAnalytics.value.metrics.map(m => ({
    metric_key: m.key, label: m.label, unit: m.unit,
    numeric_value: m.value, text_value: m.text_value
  }))
  showEditMetrics.value = true
}

async function saveMetrics() {
  try {
    await api.put(`/hr/months/${activeMonth.value}/metrics`, editMetricsForm.value.map(m => ({
      metric_key: m.metric_key, numeric_value: m.numeric_value, text_value: m.text_value || ''
    })))
    delete analytics.value[activeMonth.value]
    await loadAnalytics()
    months.value = await api.get('/hr/months')
    showEditMetrics.value = false
  } catch { /* the API layer already surfaced the reason as a toast */ }
}

function openNewMonth() { showNewMonth.value = true }

function openEditNotes() {
  notesForm.value = currentMonth.value?.notes || ''
  editingNotes.value = true
}

async function saveNotes() {
  try {
    await api.put(`/hr/months/${activeMonth.value}`, { notes: notesForm.value })
    months.value = await api.get('/hr/months')
    editingNotes.value = false
  } catch { /* the API layer already surfaced the reason as a toast */ }
}

async function createMonth() {
  try {
    const key = `${newMonthForm.value.year}-${String(newMonthForm.value.month).padStart(2,'0')}`
    await api.post('/hr/months', { year: newMonthForm.value.year, month: newMonthForm.value.month, notes: newMonthForm.value.notes })
    months.value = await api.get('/hr/months')
    activeMonth.value = key
    showNewMonth.value = false
    newMonthForm.value = { year: 2026, month: new Date().getMonth()+1, notes: '' }
  } catch { /* the API layer already surfaced the reason as a toast */ }
}

// ---------- Month deletion ----------

const canDeleteMonth = computed(() => auth.canEditMetrics('hr'))
const deleteTarget = ref(null)

function askDeleteMonth(m) { deleteTarget.value = m }

async function confirmDeleteMonth() {
  const key = deleteTarget.value?.key
  if (!key) return
  try {
    await api.del(`/hr/months/${key}`)
    delete analytics.value[key]
    months.value = await api.get('/hr/months')
    if (activeMonth.value === key) activeMonth.value = months.value[0]?.key || ''
    deleteTarget.value = null
  } catch { /* the API layer already surfaced the reason as a toast */ }
}

watch([visibleWidgets, currentAnalytics, months], () => nextTick(equalize), { deep: true })

onMounted(loadData)
</script>
