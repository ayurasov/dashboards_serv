<script setup>
import { computed, ref } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import KpiCard from '@/components/ui/KpiCard.vue'
import ChartCard from '@/components/ui/ChartCard.vue'
import EChart from '@/components/charts/EChart.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import LightBadge from '@/components/ui/LightBadge.vue'
import PdfButton from '@/components/ui/PdfButton.vue'
import LayoutDialog from '@/components/ui/LayoutDialog.vue'
import TpDashProduct from '@/components/tp/TpDashProduct.vue'
import TpDashTable from '@/components/tp/TpDashTable.vue'
import TpDashDonut from '@/components/tp/TpDashDonut.vue'
import {
  axisTooltip, barSeries, fmtValue, isDense, lineSeries, stackSeries, thresholdMarkLine, useChartTheme, valueAxis, weekAxis,
} from '@/components/tp/TpDashCharts'
import { commonApi, tpApi } from '@/api/services'
import { useAsync } from '@/composables/useAsync'
import { useQueryState } from '@/composables/useQueryState'
import { useDashboardLayout } from '@/composables/useDashboardLayout'
import { useAuthStore } from '@/stores/auth'
import { useAppStore } from '@/stores/app'
import { countLights } from '@/utils/lights'
import { formatCompact, formatNumber, plural } from '@/utils/format'
import {
  CHANNELS, CLIENTS, PRODUCTS, QUICK_PERIODS,
  channelTotals, clientInfo, clientShares, comparePeriods, deltaLabel, filterRows, groupColumns, metricDigits,
  normalizeRows, periodRange, projServerSummary, quickSelection, quickWeeks, rulesByKey, seriesOf, sumOf,
  topWeeks, trafficCards, weeksOf, yearsOf,
} from '@/domain/tp'

const auth = useAuthStore()
const app = useAppStore()
const theme = useChartTheme()

// ---------- данные ----------
const reports = useAsync(() => tpApi.reports())
const columns = useAsync(() => tpApi.columns())
const rules = useAsync(() => commonApi.lightRules('tech'))

const all = computed(() => normalizeRows(reports.data.value))
const ruleList = computed(() => rules.data.value || [])
const ruleMap = computed(() => rulesByKey(ruleList.value))
const colMeta = computed(() => Object.fromEntries((columns.data.value || []).map((c) => [c.key, c])))
const metricGroups = computed(() => groupColumns(columns.data.value || []))

// ---------- фильтры (в адресной строке) ----------
const DEFAULT_METRIC = 'avail_total'
/** По умолчанию — полгода, как на дашборде службы персонала; «Всё время» — одним нажатием. */
const DEFAULT_QUICK = '26'
const { state: f, reset, isDefault } = useQueryState({ quick: DEFAULT_QUICK, years: [], from: 0, to: 0, client: '', metric: DEFAULT_METRIC })

const years = computed(() => yearsOf(all.value))
const quickN = computed(() => quickWeeks(f.quick))
const derived = computed(() => quickSelection(all.value, f.quick))
const activeYears = computed(() => {
  if (quickN.value) return derived.value.years
  return f.years.length ? f.years.map(Number).filter((y) => years.value.includes(y)) : years.value
})
const singleYear = computed(() => (activeYears.value.length === 1 ? activeYears.value[0] : null))
const weekOptions = computed(() => {
  const weeks = weeksOf(all.value, singleYear.value)
  // Неделя из ссылки, которой нет в данных, остаётся видна в списке.
  const extra = quickN.value ? [] : [f.from, f.to].filter((w) => w && !weeks.includes(w))
  return extra.length ? [...new Set([...weeks, ...extra])].sort((a, b) => a - b) : weeks
})
const weekFrom = computed(() => (quickN.value ? derived.value.weekFrom : f.from || weekOptions.value[0]) ?? '')
const weekTo = computed(() => (quickN.value ? derived.value.weekTo : f.to || weekOptions.value.at(-1)) ?? '')

function isQuick(value) {
  if (value !== 'all') return f.quick === value
  return !quickN.value && !f.years.length && !f.from && !f.to
}

function pickQuick(value) {
  f.quick = value
  f.years = []
  f.from = 0
  f.to = 0
}

/** Быстрый период → явный выбор годов и недель (как в прежней версии при ручной правке). */
function materialize() {
  if (!quickN.value) return
  const d = derived.value
  f.years = d.years.length === years.value.length ? [] : d.years.map(String)
  f.from = d.years.length === 1 ? d.weekFrom || 0 : 0
  f.to = d.years.length === 1 ? d.weekTo || 0 : 0
  f.quick = 'all'
}

function toggleYear(year) {
  const set = new Set(activeYears.value)
  if (set.has(year)) {
    if (set.size === 1) return
    set.delete(year)
  } else {
    set.add(year)
  }
  const next = years.value.filter((y) => set.has(y))
  f.quick = 'all'
  f.years = next.length === years.value.length ? [] : next.map(String)
  f.from = 0
  f.to = 0
}

function setWeek(which, value) {
  materialize()
  f[which] = Number(value)
  if (f.from && f.to && f.from > f.to) {
    if (which === 'from') f.to = f.from
    else f.from = f.to
  }
}

const filtered = computed(() => filterRows(all.value, { quick: f.quick, years: f.years, weekFrom: f.from, weekTo: f.to }))
const pair = computed(() => comparePeriods(all.value, filtered.value, f.quick))
const labels = computed(() => filtered.value.map((r) => r.period))
const weeksCount = computed(() => filtered.value.length)
const client = computed(() => clientInfo(f.client))
const metric = computed(() => colMeta.value[f.metric] || { key: f.metric, label: 'Показатель', unit: '' })

const periodText = computed(() => periodRange(filtered.value))
const summaryText = computed(() => `${weeksCount.value} ${plural(weeksCount.value, ['неделя', 'недели', 'недель'])}`)

const pdfParams = computed(() => {
  if (quickN.value) return { weeks: quickN.value }
  if (singleYear.value && f.years.length) return { year: singleYear.value, week_from: f.from || null, week_to: f.to || null }
  return {}
})

// ---------- раскладка ----------
const BLOCKS = [
  { key: 'traffic', label: 'Светофор' },
  { key: 'trends', label: 'Динамика и трудозатраты по клиентам' },
  { key: 'flow', label: 'Поток заявок' },
  { key: 'altos', label: 'AlterOS' },
  { key: 'altoffice', label: 'AlterOffice' },
  { key: 'channels', label: 'Каналы обращений' },
  { key: 'projserver', label: 'Project Server' },
  { key: 'table', label: 'Детальная таблица' },
]
const layout = useDashboardLayout('tech', BLOCKS)
const layoutOpen = ref(false)
const blockStyle = (key) => ({ order: layout.orderOf(key) })

// ---------- светофор ----------
const cards = computed(() => trafficCards(filtered.value, ruleList.value, pair.value))
const lightCounts = computed(() => countLights(cards.value.map((c) => c.light)))
const cardDeltaLabel = computed(() => deltaLabel(pair.value))
const trafficHint = computed(() => (weeksCount.value === 1
  ? 'значения недели'
  : `за ${weeksCount.value} нед.: суммы, а для уровней и отношений — средние`))

function cardHint(c) {
  const lower = c.direction === 'lower_is_better'
  const parts = [`${c.aggregation === 'sum' ? 'Сумма' : 'Среднее'} за ${c.weeks} ${plural(c.weeks, ['неделю', 'недели', 'недель'])}`]
  if (c.green !== null) parts.push(`норма ${lower ? '≤' : '≥'} ${fmtValue(c.green, c.unit, c.digits)}`)
  if (c.yellow !== null) parts.push(`критично ${lower ? '>' : '<'} ${fmtValue(c.yellow, c.unit, c.digits)}`)
  if (c.aggregation === 'sum' && c.weeks > 1) parts.push('пороги недели умножены на число недель')
  return parts.join('; ')
}

// ---------- графики: динамика и клиенты ----------
const has = (rows, key) => rows.some((r) => r[key] !== null && r[key] !== undefined)
/** Есть ли ненулевые значения: нули по всем неделям — то же, что нет данных. */
const hasValue = (rows, key) => rows.some((r) => Number(r[key]) > 0)

const trendOption = computed(() => {
  const t = theme.value
  const m = metric.value
  const digits = metricDigits(m.key)
  return {
    legend: { show: false },
    grid: { top: 16 },
    tooltip: axisTooltip({ unit: m.unit, digits }),
    xAxis: weekAxis(labels.value, { boundaryGap: false }),
    yAxis: valueAxis(),
    series: [lineSeries(m.label, seriesOf(filtered.value, m.key), t.c(2), {
      area: true, markLine: thresholdMarkLine(ruleMap.value[m.key], { unit: m.unit, digits }),
    })],
  }
})

const shares = computed(() => clientShares(filtered.value, f.client))
const sharesTotal = computed(() => shares.value.reduce((s, x) => s + x.value, 0))
const pieItems = computed(() => {
  const t = theme.value
  return shares.value.map((s) => ({ name: clientInfo(s.key)?.short || s.label, value: s.value, color: s.color ? t.c(s.color) : t.c(7) }))
})

const stackOption = computed(() => {
  const t = theme.value
  const n = labels.value.length
  const list = client.value ? [client.value] : CLIENTS
  return {
    legend: { data: list.map((c) => c.short || c.label) },
    grid: { top: client.value ? 28 : 52 },
    tooltip: axisTooltip({ unit: 'ч', total: !client.value }),
    xAxis: weekAxis(labels.value, { boundaryGap: !isDense(n) || !!client.value }),
    yAxis: valueAxis(),
    series: list.map((c) => (client.value
      ? barSeries(c.short || c.label, seriesOf(filtered.value, c.key), t.c(c.color), { count: n })
      : stackSeries(c.short || c.label, seriesOf(filtered.value, c.key), t.c(c.color), { stack: 'clients', count: n }))),
  }
})

const topKey = computed(() => f.client || 'avail_total')
const top = computed(() => topWeeks(filtered.value, topKey.value, 15))
const topOption = computed(() => {
  const t = theme.value
  return {
    legend: { show: false },
    grid: { left: 8, right: 44, top: 4, bottom: 4, containLabel: true },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow', shadowStyle: { color: t.border, opacity: 0.35 } }, valueFormatter: (v) => fmtValue(v, 'ч') },
    xAxis: { type: 'value', show: false },
    yAxis: { type: 'category', inverse: true, data: top.value.map((x) => x.period), axisLine: { show: false }, axisLabel: { fontVariantNumeric: 'tabular-nums' } },
    series: [{
      name: client.value?.label || 'Трудозатраты', type: 'bar', barMaxWidth: 12, data: top.value.map((x) => x.value),
      itemStyle: { color: client.value ? t.c(client.value.color) : t.c(2), borderRadius: [0, 3, 3, 0] },
      label: { show: true, position: 'right', color: t.text2, fontSize: 11, formatter: (p) => formatNumber(p.value, { digits: 1 }) },
    }],
  }
})

// ---------- графики: поток заявок ----------
const flowOption = computed(() => {
  const t = theme.value
  const n = labels.value.length
  const dense = isDense(n)
  const make = (name, key, color) => (dense
    ? lineSeries(name, seriesOf(filtered.value, key), color, { count: n })
    : barSeries(name, seriesOf(filtered.value, key), color, { count: n }))
  return {
    legend: { data: ['Принято', 'Решено'] },
    tooltip: axisTooltip({ unit: 'шт.', digits: 0 }),
    xAxis: weekAxis(labels.value, { boundaryGap: !dense }),
    yAxis: valueAxis({ minInterval: 1 }),
    series: [make('Принято', 'new_received', t.c(2)), make('Решено', 'total_solved_week', t.c(3))],
  }
})

const ratioOption = computed(() => {
  const t = theme.value
  return {
    legend: { show: false },
    grid: { top: 16 },
    tooltip: axisTooltip({ digits: 2 }),
    xAxis: weekAxis(labels.value, { boundaryGap: false }),
    yAxis: valueAxis(),
    series: [lineSeries('Решено / получено', seriesOf(filtered.value, 'ratio_solved_received'), t.c(6), {
      area: true, markLine: thresholdMarkLine(ruleMap.value.ratio_solved_received, { digits: 2, fallback: { value: 1, label: 'решено = получено' } }),
    })],
  }
})

const inWorkOption = computed(() => {
  const t = theme.value
  return {
    legend: { show: false },
    grid: { top: 16 },
    tooltip: axisTooltip({ unit: 'шт.', digits: 0 }),
    xAxis: weekAxis(labels.value, { boundaryGap: false }),
    yAxis: valueAxis(),
    series: [lineSeries('В работе', seriesOf(filtered.value, 'total_in_work'), t.c(5), {
      area: true, markLine: thresholdMarkLine(ruleMap.value.total_in_work, { unit: 'шт.', digits: 0 }),
    })],
  }
})

const flowTotals = computed(() => ({
  received: sumOf(filtered.value, 'new_received'),
  solved: sumOf(filtered.value, 'total_solved_week'),
}))

// ---------- графики: каналы ----------
// Цвет — способ обращения, насыщенность — группа клиентов (РусГидро ярче, прочие светлее).
const CHANNEL_STYLE = { email: 2, phone: 5 }
function channelOption(product) {
  const t = theme.value
  const n = labels.value.length
  return {
    legend: { data: CHANNELS.map((c) => c.label) },
    grid: { top: 52 },
    tooltip: axisTooltip({ unit: 'шт.', digits: 0, total: true }),
    xAxis: weekAxis(labels.value, { boundaryGap: !isDense(n) }),
    yAxis: valueAxis({ minInterval: 1 }),
    series: CHANNELS.map((c) => stackSeries(c.label, seriesOf(filtered.value, `${product}_${c.suffix}`), t.c(CHANNEL_STYLE[c.channel]), {
      stack: 'ch', count: n, opacity: c.group === 'rushydro' ? 1 : 0.55,
    })),
  }
}
const altosChannels = computed(() => channelOption('altos'))
const altofficeChannels = computed(() => channelOption('altoffice'))
const channels = computed(() => channelTotals(filtered.value))
const channelItems = computed(() => {
  const t = theme.value
  return [
    { name: 'E-mail', value: channels.value.email, color: t.c(CHANNEL_STYLE.email) },
    { name: 'Телефон', value: channels.value.phone, color: t.c(CHANNEL_STYLE.phone) },
  ]
})
const hasChannels = (product) => CHANNELS.some((c) => hasValue(filtered.value, `${product}_${c.suffix}`))

// ---------- Project Server ----------
const ps = computed(() => projServerSummary(filtered.value))
const psTicketsOption = computed(() => {
  const t = theme.value
  const n = labels.value.length
  return {
    legend: { data: ['Принято', 'Решено'] },
    tooltip: axisTooltip({ unit: 'шт.', digits: 0 }),
    xAxis: weekAxis(labels.value),
    yAxis: valueAxis({ minInterval: 1 }),
    series: [
      barSeries('Принято', seriesOf(filtered.value, 'projserver_taken'), t.c(2), { count: n }),
      barSeries('Решено', seriesOf(filtered.value, 'projserver_solved'), t.c(3), { count: n }),
    ],
  }
})
const psAvailOption = computed(() => {
  const t = theme.value
  return {
    legend: { show: false },
    grid: { top: 16 },
    tooltip: axisTooltip({ unit: 'ч' }),
    xAxis: weekAxis(labels.value, { boundaryGap: false }),
    yAxis: valueAxis(),
    series: [lineSeries('Доступно', seriesOf(filtered.value, 'projserver_avail'), t.c(6), { area: true })],
  }
})

const loadingFirst = computed(() => reports.loading.value && !reports.data.value)
const canEdit = computed(() => auth.can('tech', 'editor'))
const canManage = computed(() => auth.can('tech', 'manager'))
</script>

<template>
  <div class="page">
    <PageHeader title="Техническая поддержка" :description="periodText ? `Период: ${periodText} · ${summaryText}` : 'Недельный отчёт: нагрузка, трудозатраты, решение заявок'"
                :updatedAt="app.service('tech')?.data_updated_at">
      <button class="btn btn-ghost" type="button" title="Состав и порядок блоков" @click="layoutOpen = true"><AppIcon name="settings" :size="15" />Настроить</button>
      <router-link to="/tp/registry" class="btn"><AppIcon :name="canEdit ? 'edit' : 'table'" :size="15" />Недельный отчёт</router-link>
      <PdfButton report="tp/dashboard" :params="pdfParams" />
    </PageHeader>

    <!-- Период и фильтры -->
    <div class="filters card">
      <div class="f-row">
        <span class="f-label">Период</span>
        <div class="row-wrap">
          <button v-for="q in QUICK_PERIODS" :key="q.value" type="button" class="chip" :class="{ active: isQuick(q.value) }" @click="pickQuick(q.value)">{{ q.label }}</button>
        </div>
        <span class="spacer" />
        <button v-if="!isDefault()" class="btn btn-ghost btn-sm" type="button" @click="reset"><AppIcon name="refresh" :size="13" />Сбросить</button>
      </div>
      <div class="f-row">
        <span class="f-label">Годы</span>
        <div class="row-wrap">
          <button v-for="y in years" :key="y" type="button" class="chip" :class="{ active: activeYears.includes(y) }"
                  :aria-pressed="activeYears.includes(y)" @click="toggleYear(y)">{{ y }}</button>
        </div>
      </div>
      <div class="f-row f-fields">
        <label class="field inline" :class="{ disabled: !singleYear }" :title="singleYear ? '' : 'Диапазон недель задаётся, когда выбран один год'">
          <span>Недели</span>
          <select class="select" :value="weekFrom" :disabled="!singleYear" aria-label="Неделя с" @change="setWeek('from', $event.target.value)">
            <option v-for="w in weekOptions" :key="w" :value="w">с {{ w }}</option>
          </select>
          <select class="select" :value="weekTo" :disabled="!singleYear" aria-label="Неделя по" @change="setWeek('to', $event.target.value)">
            <option v-for="w in weekOptions" :key="w" :value="w">по {{ w }}</option>
          </select>
        </label>
        <label class="field inline">
          <span>Клиент</span>
          <select v-model="f.client" class="select">
            <option value="">Все клиенты</option>
            <option v-for="c in CLIENTS" :key="c.key" :value="c.key">{{ c.label }}</option>
          </select>
        </label>
        <label class="field inline">
          <span>Метрика тренда</span>
          <select v-model="f.metric" class="select metric">
            <optgroup v-for="g in metricGroups" :key="g.key" :label="g.label">
              <option v-for="c in g.items" :key="c.key" :value="c.key">{{ c.label }}</option>
            </optgroup>
          </select>
        </label>
      </div>
      <p v-if="client" class="client-note"><AppIcon name="filter" :size="13" />Клиент «{{ client.label }}»: структура трудозатрат, топ недель и таблица показывают только его данные</p>
    </div>

    <!-- Загрузка -->
    <template v-if="loadingFirst">
      <div class="grid grid-kpi">
        <KpiCard v-for="i in 6" :key="i" label="Загрузка" loading />
      </div>
      <div class="grid grid-2">
        <div class="skeleton" style="height: 340px" />
        <div class="skeleton" style="height: 340px" />
      </div>
    </template>

    <EmptyState v-else-if="reports.error.value" icon="alert" title="Не удалось загрузить отчёт" :text="reports.error.value.message">
      <button class="btn" type="button" @click="reports.reload()"><AppIcon name="refresh" :size="14" />Повторить</button>
    </EmptyState>

    <EmptyState v-else-if="!all.length" icon="calendar" title="Данных пока нет"
                text="Добавьте недели в разделе «Недельный отчёт» или загрузите файл отчёта — после этого здесь появятся показатели.">
      <router-link to="/tp/registry" class="btn btn-primary">Недельный отчёт</router-link>
    </EmptyState>

    <EmptyState v-else-if="!filtered.length" compact icon="search" title="Нет недель в выбранном периоде" text="Измените годы или диапазон недель.">
      <button class="btn" type="button" @click="reset">Сбросить фильтры</button>
    </EmptyState>

    <div v-else class="blocks">
      <!-- Светофор -->
      <section v-if="layout.visible('traffic')" class="stack" :style="blockStyle('traffic')">
        <div class="section-title">
          <h2>Светофор</h2>
          <span class="muted">{{ trafficHint }}</span>
          <span class="spacer" />
          <span v-if="cards.length" class="light-summary">
            <LightBadge v-if="lightCounts.green" light="green" :label="`Норма · ${lightCounts.green}`" />
            <LightBadge v-if="lightCounts.yellow" light="yellow" :label="`Внимание · ${lightCounts.yellow}`" />
            <LightBadge v-if="lightCounts.red" light="red" :label="`Критично · ${lightCounts.red}`" />
          </span>
        </div>
        <div v-if="cards.length" class="grid traffic-grid">
          <KpiCard v-for="c in cards" :key="c.key" :label="c.label" :value="c.value" :unit="c.unit" :digits="c.digits" :light="c.light"
                   :deltaPct="c.deltaPct" :deltaLabel="cardDeltaLabel" :direction="c.direction" :hint="cardHint(c)" />
        </div>
        <div v-else-if="rules.loading.value" class="grid grid-kpi"><KpiCard v-for="i in 6" :key="i" label="Загрузка" loading /></div>
        <div v-else class="card">
          <EmptyState compact icon="traffic" title="Светофор не настроен" text="Включите правила для показателей — карточки покажут оценку выбранного периода.">
            <router-link v-if="canManage" to="/settings/traffic-light/tech" class="btn btn-sm">Настроить светофор</router-link>
          </EmptyState>
        </div>
      </section>

      <!-- Динамика и клиенты -->
      <section v-if="layout.visible('trends')" class="stack" :style="blockStyle('trends')">
        <div class="section-title"><h2>Динамика и трудозатраты</h2><span class="muted">по неделям выбранного периода</span></div>
        <div class="grid grid-2">
          <ChartCard :title="metric.label" :hint="`Метрика тренда${metric.unit ? `, ${metric.unit}` : ''} · меняется в фильтре`" :empty="!has(filtered, metric.key)">
            <EChart :option="trendOption" />
          </ChartCard>
          <ChartCard :title="client ? `Доля клиента «${client.label}»` : 'Трудозатраты по клиентам'"
                     :hint="client ? 'В общих трудозатратах за период' : 'Сумма за период, ч'" :empty="!sharesTotal">
            <TpDashDonut :items="pieItems" unit="ч" :total="formatCompact(Math.round(sharesTotal))" totalLabel="ч за период" />
          </ChartCard>
        </div>
        <div class="grid grid-2">
          <ChartCard :title="client ? `${client.label}: трудозатраты по неделям` : 'Трудозатраты по клиентам по неделям'" hint="По неделям, ч" :empty="!sharesTotal">
            <EChart :option="stackOption" />
          </ChartCard>
          <ChartCard :title="client ? `Топ недель: ${client.label}` : 'Самые загруженные недели'"
                     :hint="client ? '15 недель с наибольшими трудозатратами клиента, ч' : '15 недель с наибольшими трудозатратами, ч'" :empty="!top.length">
            <EChart :option="topOption" />
          </ChartCard>
        </div>
      </section>

      <!-- Поток заявок -->
      <section v-if="layout.visible('flow')" class="stack" :style="blockStyle('flow')">
        <div class="section-title">
          <h2>Поток заявок</h2>
          <span class="muted">принято {{ formatNumber(flowTotals.received) }} · решено {{ formatNumber(flowTotals.solved) }}</span>
        </div>
        <div class="grid grid-3">
          <ChartCard title="Принято и решено" hint="Заявки по неделям, шт." :height="260" :empty="!has(filtered, 'new_received') && !has(filtered, 'total_solved_week')">
            <EChart :option="flowOption" />
          </ChartCard>
          <ChartCard title="Решено / получено" hint="Коэффициент решаемости по неделям" :height="260" :empty="!has(filtered, 'ratio_solved_received')">
            <EChart :option="ratioOption" />
          </ChartCard>
          <ChartCard title="В работе" hint="Остаток заявок на конец недели, шт." :height="260" :empty="!has(filtered, 'total_in_work')">
            <EChart :option="inWorkOption" />
          </ChartCard>
        </div>
      </section>

      <!-- AlterOS и AlterOffice -->
      <template v-for="p in PRODUCTS" :key="p.key">
        <TpDashProduct v-if="layout.visible(p.key)" :product="p.key" :title="p.label" :rows="filtered" :rules="ruleMap" :style="blockStyle(p.key)" />
      </template>

      <!-- Каналы -->
      <section v-if="layout.visible('channels')" class="stack" :style="blockStyle('channels')">
        <div class="section-title"><h2>Каналы обращений</h2><span class="muted">e-mail и телефон, РусГидро и прочие клиенты</span></div>
        <div class="grid grid-3">
          <ChartCard title="AlterOS: обращения по каналам" hint="По неделям, шт." :height="260" :empty="!hasChannels('altos')">
            <EChart :option="altosChannels" />
          </ChartCard>
          <ChartCard title="AlterOffice: обращения по каналам" hint="По неделям, шт." :height="260" :empty="!hasChannels('altoffice')">
            <EChart :option="altofficeChannels" />
          </ChartCard>
          <ChartCard title="Способ обращения" hint="Доля за период, оба продукта" :height="260" :empty="!(channels.email + channels.phone)">
            <TpDashDonut :items="channelItems" unit="шт." :total="formatNumber(channels.email + channels.phone)" totalLabel="обращений" :wideFrom="280" />
          </ChartCard>
        </div>
      </section>

      <!-- Project Server -->
      <section v-if="layout.visible('projserver')" class="stack" :style="blockStyle('projserver')">
        <div class="section-title"><h2>Project Server</h2><span class="muted">заявки и доступные часы</span></div>
        <div class="grid grid-kpi">
          <KpiCard label="Принято заявок" :value="ps.taken" unit="шт." hint="Сумма за период" />
          <KpiCard label="Решено заявок" :value="ps.solved" unit="шт." hint="Сумма за период" />
          <KpiCard label="Решено от принятого" :value="ps.solvedShare" unit="%" :digits="0" hint="Решено / принято за период" />
          <KpiCard label="Доступно на последней неделе" :value="ps.availLast" unit="ч" :hint="ps.availLastPeriod ? `Неделя ${ps.availLastPeriod}` : ''" />
        </div>
        <div class="grid grid-2">
          <ChartCard title="Принято и решено" hint="Заявки по неделям, шт." :height="240" :empty="!hasValue(filtered, 'projserver_taken') && !hasValue(filtered, 'projserver_solved')" emptyText="Заявок Project Server за период не было">
            <EChart :option="psTicketsOption" />
          </ChartCard>
          <ChartCard title="Доступно" :hint="ps.availAvg !== null ? `По неделям, в среднем ${fmtValue(ps.availAvg, 'ч')}` : 'По неделям, ч'" :height="240" :empty="!hasValue(filtered, 'projserver_avail')" emptyText="Доступных часов за период нет">
            <EChart :option="psAvailOption" />
          </ChartCard>
        </div>
      </section>

      <!-- Таблица -->
      <TpDashTable v-if="layout.visible('table')" :rows="filtered" :rules="ruleMap" :client="f.client" :style="blockStyle('table')" />
    </div>

    <LayoutDialog v-if="layoutOpen" :items="layout.ordered.value" @close="layoutOpen = false" @save="layout.save" @reset="layout.reset" />
  </div>
</template>

<style scoped>
.filters { padding: 12px 16px; display: flex; flex-direction: column; gap: 10px; }
.f-row { display: flex; align-items: center; flex-wrap: wrap; gap: 8px 12px; }
.f-label { width: 56px; flex: 0 0 auto; font-size: var(--fs-xs); text-transform: uppercase; letter-spacing: .05em; color: var(--muted); font-weight: 620; }
.f-fields { padding-top: 10px; border-top: 1px dashed var(--border); gap: 10px 18px; }
.field.inline { flex-direction: row; align-items: center; gap: 8px; }
.field.inline > span { font-size: var(--fs-xs); text-transform: uppercase; letter-spacing: .05em; color: var(--muted); font-weight: 620; white-space: nowrap; }
.field.inline .select { height: 32px; width: auto; min-width: 92px; }
.field.inline .select.metric { min-width: 220px; max-width: 320px; }
.field.disabled .select { opacity: .55; }
.traffic-grid { grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); }
.client-note { display: flex; align-items: center; gap: 6px; font-size: var(--fs-sm); color: var(--text-2); padding: 6px 10px; border-radius: var(--radius); background: color-mix(in srgb, var(--chart-2) 8%, transparent); align-self: flex-start; }
.blocks { display: flex; flex-direction: column; gap: var(--sp-6); }
.light-summary { display: inline-flex; flex-wrap: wrap; gap: 6px; align-self: center; }
@media (max-width: 640px) {
  .f-label { width: 100%; }
  .field.inline { flex-wrap: wrap; }
  .field.inline .select.metric { min-width: 0; max-width: 100%; }
}
</style>
