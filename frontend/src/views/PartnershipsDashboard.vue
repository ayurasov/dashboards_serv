<template>
  <div v-if="loading" class="tempty">Загрузка данных…</div>
  <div v-else-if="error" class="tempty">Ошибка: {{ error }}</div>
  <template v-else>
    <div class="filters">
      <select class="fsel" v-model="filters.year">
        <option value="">Все годы</option>
        <option v-for="y in yearOptions" :key="y" :value="y">{{ y }}</option>
      </select>
      <select class="fsel" v-model="filters.status">
        <option value="">Все статусы</option>
        <option v-for="s in statusOptions" :key="s" :value="s">{{ s }}</option>
      </select>
      <select class="fsel" v-model="filters.almi_product">
        <option value="">Все продукты АЛМИ</option>
        <option v-for="p in productOptions" :key="p" :value="p">{{ p }}</option>
      </select>
      <button class="btn btn-g" :disabled="!activeFilters" @click="resetFilters">Сбросить фильтры</button>
      <div class="tinfo" style="flex:1;margin:0">
        Показано {{ a.total }} из {{ totalAll }} партнёрств
        <span v-if="activeFilters"> · фильтров: {{ activeFilters }}</span>
      </div>
      <router-link class="btn btn-g" to="/product/summary">Сводка партнёрств</router-link>
      <button class="btn btn-g" @click="showSettings=true">⚙ Настройки дашборда</button>
      <button class="btn btn-g" @click="autoLayout">⌗ Авторасположение</button>
    </div>

    <!-- Widgets share one grid so those in a row can be given equal heights -->
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
          <div class="kpi-grid" style="margin-bottom:0">
            <div class="kpi">
              <div class="kpi-lbl">Всего партнёрств</div>
              <div class="kpi-val">{{ a.total }}</div>
              <div class="kpi-sub">записей в реестре</div>
            </div>
            <div class="kpi light-green">
              <div class="kpi-lbl">Завершено</div>
              <div class="kpi-val" style="color:var(--c-ok)">{{ statusCount('Завершено') }}</div>
              <div class="kpi-sub">{{ pct(statusCount('Завершено')) }}% от всего</div>
            </div>
            <div class="kpi light-yellow">
              <div class="kpi-lbl">В работе</div>
              <div class="kpi-val" style="color:var(--c-warn)">{{ statusCount('В работе') }}</div>
              <div class="kpi-sub">{{ pct(statusCount('В работе')) }}% от всего</div>
            </div>
            <div class="kpi">
              <div class="kpi-lbl">Подписано NDA</div>
              <div class="kpi-val">{{ a.nda_count }}</div>
              <div class="kpi-sub">{{ pct(a.nda_count) }}% от всего</div>
            </div>
            <div class="kpi">
              <div class="kpi-lbl">Подписано соглашений</div>
              <div class="kpi-val">{{ a.agreement_count }}</div>
              <div class="kpi-sub">{{ pct(a.agreement_count) }}% от всего</div>
            </div>
          </div>
        </template>

        <div v-else class="ccard">
          <div class="ctitle-row">
            <span class="whandle" draggable="true" title="Перетащите, чтобы изменить порядок"
                  @dragstart="dragStart(w.key, $event)" @dragend="dragEnd">⠿</span>
            <span class="ctitle">{{ title(w.key) }}</span>
            <button v-if="w.key === 'year' && canEdit" class="btn btn-p"
                    style="font-size:.75rem;padding:4px 8px" @click="showAdd=true">+ Партнёрство</button>
            <router-link v-if="w.key === 'light'" class="btn btn-g"
                         style="font-size:.75rem;padding:4px 8px" to="/product/traffic-light">Правила</router-link>
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

          <!-- Traffic light -->
          <div v-else-if="w.key === 'light'" class="slist">
            <div class="slist-row" v-for="r in lightRows" :key="r.key">
              <span class="light-dot" :class="'light-' + r.light"></span>
              <span class="slist-lbl">{{ r.group }} · {{ r.label }}</span>
              <span class="slist-val">{{ r.count }} ({{ r.share }}%)</span>
            </div>
            <div class="slist-row" v-if="!lightRows.length">
              <span class="slist-lbl tempty">Нет данных</span>
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

    <partnership-modal
      v-if="showAdd"
      :model-value="{}"
      @close="showAdd=false"
      @saved="onSaved"
    />
  </template>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import EChart from '../components/EChart.vue'
import ChartSettings from '../components/ChartSettings.vue'
import DashboardSettings from '../components/DashboardSettings.vue'
import PartnershipModal from '../components/PartnershipModal.vue'
import { api } from '../api/client.js'
import { useAuthStore } from '../stores/auth.js'
import { usePaletteStore } from '../stores/palette.js'
import { setPdfParams } from '../composables/usePdfExport.js'
import { useWidgetLayout, useDragReorder } from '../composables/useWidgetLayout.js'
import { applyChartSettings, chartHeightOf } from '../composables/useChartSettings.js'
import { useRowEqualize } from '../composables/useRowEqualize.js'

const router = useRouter()
const auth = useAuthStore()
const palette = usePaletteStore()
const canEdit = computed(() => auth.canEdit)

const loading = ref(true)
const error = ref('')
const showAdd = ref(false)
const EMPTY = { total: 0, by_status: {}, by_almi_product: {}, by_year: {}, by_direction: {}, nda_count: 0, agreement_count: 0 }
const a = ref({ ...EMPTY })
const lightRows = ref([])

// Filter dropdown choices come from an unfiltered snapshot so narrowing one
// filter never empties the others.
const allOptions = ref({ ...EMPTY })
const totalAll = computed(() => allOptions.value.total)
const yearOptions = computed(() => Object.keys(allOptions.value.by_year || {}).sort().reverse())
const statusOptions = computed(() => Object.keys(allOptions.value.by_status || {}).sort((x, y) => x.localeCompare(y, 'ru')))
const productOptions = computed(() => Object.keys(allOptions.value.by_almi_product || {}).sort((x, y) => x.localeCompare(y, 'ru')))

const filters = reactive({ year: '', status: '', almi_product: '' })
const activeFilters = computed(() => Object.values(filters).filter(Boolean).length)
function resetFilters() { filters.year = ''; filters.status = ''; filters.almi_product = '' }

// The topbar PDF button reads these, so its export honours the page filters.
setPdfParams(() => ({ status: filters.status, almi_product: filters.almi_product }))

const statusColors = computed(() => {
  const tl = palette.trafficLight
  return [tl.green, tl.yellow, tl.neutral, tl.red, ...palette.chartColors]
})

// Order, size, visibility and per-chart appearance persist under the продуктовый
// офис service key. `kind` drives «Авторасположение».
const WIDGET_CATALOG = [
  { key: 'kpi', title: 'KPI-карточки', size: 'large', kind: 'kpi' },
  { key: 'light', title: 'Светофор партнёрств', size: 'medium', kind: 'chart' },
  { key: 'year', title: 'Сертификаты по годам', size: 'medium', kind: 'chart' },
  { key: 'product', title: 'По продукту АЛМИ', size: 'medium', kind: 'chart' },
  { key: 'status', title: 'По статусу', size: 'medium', kind: 'chart' },
  { key: 'direction', title: 'Топ-8 направлений', size: 'large', kind: 'wide_chart' },
]

const { ordered, visibleWidgets, title, setSettings, load: loadLayout,
        save: saveLayout, resetLayout, autoLayout, move } =
  useWidgetLayout('project_product', WIDGET_CATALOG)
const { dragKey, overKey, dragStart, dragOver, drop: onDrop, dragEnd } = useDragReorder(move)
const { gridEl, equalize } = useRowEqualize()

const showSettings = ref(false)

async function onSaveLayout() {
  if (await saveLayout()) showSettings.value = false
}

async function onResetLayout() {
  await resetLayout()
  showSettings.value = false
}

function baseHeight(size) { return size === 'large' || size === 'wide' ? 280 : 260 }
function chartHeight(w) { return chartHeightOf(w.settings, baseHeight(w.size)) }
function chartOption(w) { return applyChartSettings(CHART_OPTIONS[w.key].value, w.settings) }
function chartColors(w) {
  if (w.settings?.colors?.length) return w.settings.colors
  return w.key === 'status' ? statusColors.value : palette.chartColors
}

function statusCount(name) { return a.value.by_status?.[name] || 0 }
function pct(n) { return a.value.total ? Math.round((n / a.value.total) * 100) : 0 }

const axisBase = {
  axisLine: { lineStyle: { color: 'var(--c-div)' } },
  axisLabel: { color: '#8a8985', fontSize: 10 },
}

const years = computed(() => Object.keys(a.value.by_year || {}).sort())

const yearOpt = computed(() => ({
  grid: { left: 40, right: 12, top: 16, bottom: 28 },
  tooltip: { trigger: 'axis' },
  xAxis: {
    type: 'category', data: years.value, ...axisBase,
    axisLabel: { ...axisBase.axisLabel, rotate: years.value.length > 10 ? 45 : 0 },
  },
  yAxis: { type: 'value', ...axisBase, splitLine: { lineStyle: { color: 'rgba(140,140,140,.15)' } } },
  series: [{
    type: 'bar', data: years.value.map(y => a.value.by_year[y]),
    barMaxWidth: 34, itemStyle: { borderRadius: [4, 4, 0, 0] },
  }],
}))

// Slices under this share get no drawn label — with several sub-2% slices the
// callouts collide into an unreadable stack. Their names stay in the legend and
// their exact values in the tooltip, so nothing is actually lost.
const MIN_LABEL_SHARE = 0.05

function pieData(counts) {
  const entries = Object.entries(counts || {})
  const total = entries.reduce((sum, [, v]) => sum + v, 0) || 1
  return entries.map(([name, value]) => {
    const show = value / total >= MIN_LABEL_SHARE
    return { name, value, label: { show }, labelLine: { show } }
  })
}

const PIE_LABEL = { formatter: '{b}\n{d}%', fontSize: 11, lineHeight: 14, color: '#8a8985' }
const PIE_LABEL_LINE = { length: 10, length2: 10 }

const productOpt = computed(() => ({
  tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
  legend: { bottom: 0, textStyle: { color: '#8a8985', fontSize: 11 } },
  series: [{
    type: 'pie',
    radius: '55%',
    center: ['50%', '44%'],
    avoidLabelOverlap: true,
    data: pieData(a.value.by_almi_product),
    label: PIE_LABEL,
    labelLine: PIE_LABEL_LINE,
  }],
}))

const directionOpt = computed(() => {
  const entries = Object.entries(a.value.by_direction || {}).sort((x, y) => x[1] - y[1])
  return {
    grid: { left: 8, right: 30, top: 10, bottom: 10, containLabel: true },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    xAxis: { type: 'value', ...axisBase, splitLine: { lineStyle: { color: 'rgba(140,140,140,.15)' } } },
    yAxis: {
      type: 'category',
      data: entries.map(e => e[0]),
      ...axisBase,
      // Wrap rather than truncate: several direction names run past 20 characters.
      axisLabel: { ...axisBase.axisLabel, fontSize: 11, width: 150, overflow: 'break', lineHeight: 13 },
    },
    series: [{ type: 'bar', data: entries.map(e => e[1]), barMaxWidth: 18, itemStyle: { borderRadius: [0, 4, 4, 0] } }],
  }
})

const statusOpt = computed(() => ({
  tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
  legend: { bottom: 0, textStyle: { color: '#8a8985', fontSize: 11 } },
  series: [{
    type: 'pie',
    radius: ['38%', '58%'],
    center: ['50%', '44%'],
    avoidLabelOverlap: true,
    data: pieData(a.value.by_status),
    label: PIE_LABEL,
    labelLine: PIE_LABEL_LINE,
  }],
}))

// ---------- Chart → registry navigation ----------

function toRegistry(query) {
  router.push({ path: '/product/registry', query })
}
function onYearClick(params) {
  // The registry has no year column; its cert_date filter matches the ISO string.
  if (params?.name) toRegistry({ cert_date: params.name })
}
function onProductClick(params) { if (params?.name) toRegistry({ almi_product: params.name }) }
function onStatusClick(params) { if (params?.name) toRegistry({ status: params.name }) }
function onDirectionClick(params) { if (params?.name) toRegistry({ direction: params.name }) }

const CHART_OPTIONS = { year: yearOpt, product: productOpt, status: statusOpt, direction: directionOpt }
const CHART_CLICKS = {
  year: onYearClick, product: onProductClick, status: onStatusClick, direction: onDirectionClick,
}

// ---------- Loading ----------

function query() {
  const qs = new URLSearchParams()
  for (const [k, v] of Object.entries(filters)) if (v) qs.set(k, v)
  const s = qs.toString()
  return s ? `?${s}` : ''
}

async function loadAnalytics() {
  error.value = ''
  try {
    a.value = await api.get(`/partnerships/analytics${query()}`)
    const lightQs = filters.year ? `?year=${filters.year}` : ''
    lightRows.value = (await api.get(`/partnerships/traffic-light${lightQs}`)).filter(r => r.count > 0)
  } catch (e) {
    error.value = e.message
  }
}

watch(filters, loadAnalytics)

async function load() {
  loading.value = true
  try {
    allOptions.value = await api.get('/partnerships/analytics')
    await Promise.all([loadAnalytics(), loadLayout()])
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

watch([visibleWidgets, lightRows, a], () => nextTick(equalize), { deep: true })

function onSaved() {
  showAdd.value = false
  load()
}

onMounted(load)
</script>
