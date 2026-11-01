<script setup>
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import AppIcon from '@/components/ui/AppIcon.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import FilterBar from '@/components/ui/FilterBar.vue'
import KpiCard from '@/components/ui/KpiCard.vue'
import ChartCard from '@/components/ui/ChartCard.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import LightBadge from '@/components/ui/LightBadge.vue'
import PdfButton from '@/components/ui/PdfButton.vue'
import LayoutDialog from '@/components/ui/LayoutDialog.vue'
import EChart from '@/components/charts/EChart.vue'
import PartnershipForm from '@/components/product/PartnershipForm.vue'
import { partnershipsApi } from '@/api/services'
import { useAsync } from '@/composables/useAsync'
import { useQueryState } from '@/composables/useQueryState'
import { useDashboardLayout } from '@/composables/useDashboardLayout'
import { useAuthStore } from '@/stores/auth'
import { useAppStore } from '@/stores/app'
import { chartColors, cssVar, lightColor } from '@/components/charts/echarts'
import { formatNumber } from '@/utils/format'
import { LIGHT_LABELS } from '@/utils/lights'
import {
  PARTNERSHIP_STATUSES, PARTNERSHIP_TYPES, countByLight, countWord, fitSpans, groupLightRows, lightSegments, mergeOptions, orderStatuses,
  share, shortRuleLabel, sortedEntries,
} from '@/domain/partnerships'

const auth = useAuthStore()
const app = useAppStore()
const router = useRouter()
const canEdit = computed(() => auth.can('project_product', 'editor'))

const { state: f, reset, isDefault } = useQueryState({ year: '', status: '', almi_product: '' })
const params = computed(() => ({ year: f.year, status: f.status, almi_product: f.almi_product }))

const options = useAsync(() => partnershipsApi.options())
const { data, loading, reload } = useAsync(() => partnershipsApi.analytics(params.value), { immediate: false })
const records = useAsync(() => partnershipsApi.list(params.value), { immediate: false })
watch(params, () => { reload(); records.reload() }, { immediate: true, deep: true })

function refresh() {
  reload()
  records.reload()
  options.reload()
  app.loadServices()
}

const opts = computed(() => options.data.value || { statuses: [], almi_products: [], directions: [], types: [], years: [] })
const years = computed(() => [...opts.value.years].sort((a, b) => b - a))
const statuses = computed(() => orderStatuses(opts.value.statuses))
const total = computed(() => data.value?.total ?? 0)
const first = computed(() => loading.value && !data.value)
const noData = computed(() => isDefault() && data.value && !data.value.total)

// ---------- показатели ----------
const statusCount = (name) => data.value?.by_status?.[name] || 0
const lightOf = (key) => data.value?.lights?.find((r) => r.key === key)?.light || ''
const kpis = computed(() => {
  const t = total.value
  return [
    { label: 'Всего партнёрств', value: data.value?.total ?? null, hint: 'Записей реестра с учётом фильтров' },
    { label: 'Завершено', value: data.value ? statusCount('Завершено') : null, unit: `из ${formatNumber(t)}`, light: lightOf('status:Завершено') },
    { label: 'В работе', value: data.value ? statusCount('В работе') : null, unit: `из ${formatNumber(t)}`, light: lightOf('status:В работе') },
    { label: 'NDA подписан', value: data.value ? share(data.value.nda_count, t) : null, unit: '%', digits: 1, hint: `${formatNumber(data.value?.nda_count)} из ${formatNumber(t)}` },
    { label: 'Соглашение подписано', value: data.value ? share(data.value.agreement_count, t) : null, unit: '%', digits: 1, hint: `${formatNumber(data.value?.agreement_count)} из ${formatNumber(t)}` },
  ]
})

// ---------- светофор ----------
const lightGroups = computed(() => groupLightRows(data.value?.lights || []))
const recordLights = computed(() => countByLight(records.data.value || []))
const recordSegments = computed(() => lightSegments(recordLights.value))
const recordTotal = computed(() => recordSegments.value.reduce((s, x) => s + x.count, 0))

const compact = (obj) => Object.fromEntries(Object.entries(obj).filter(([, v]) => v !== '' && v !== null && v !== undefined))
const registryQuery = computed(() => compact(params.value))
function toRegistry(extra) {
  router.push({ path: '/product/registry', query: compact({ ...params.value, ...extra }) })
}

// ---------- графики ----------
const accent = () => cssVar('--chart-2')
const surface = () => cssVar('--surface', '#fff')
/**
 * Цвет закреплён за значением, а не за местом в рейтинге: фильтры не перекрашивают категории.
 * Зелёный и жёлтый палитры совпадают со светофором — они идут последними.
 */
const CATEGORY_ORDER = [1, 4, 5, 0, 6, 2, 3]
function colorFor(name, list) {
  const colors = chartColors()
  const i = Math.max(0, list.indexOf(name))
  return colors[CATEGORY_ORDER[i % CATEGORY_ORDER.length]]
}

const yearEntries = computed(() => Object.entries(data.value?.by_year || {}).sort((a, b) => Number(a[0]) - Number(b[0])))
const yearsOption = computed(() => ({
  tooltip: { axisPointer: { type: 'shadow' }, formatter: (p) => `${p[0].name} год: <b>${formatNumber(p[0].value)}</b> ${countWord(p[0].value)}` },
  grid: { top: 24 },
  xAxis: { type: 'category', data: yearEntries.value.map((e) => e[0]) },
  yAxis: { type: 'value', minInterval: 1 },
  series: [{ type: 'bar', barMaxWidth: 34, cursor: 'pointer', data: yearEntries.value.map((e) => e[1]),
    itemStyle: { color: accent(), borderRadius: [4, 4, 0, 0] },
    label: { show: true, position: 'top', color: cssVar('--text-2'), fontSize: 11 } }],
}))

const directionEntries = computed(() => sortedEntries(data.value?.by_direction))
const directionsOption = computed(() => ({
  tooltip: { axisPointer: { type: 'shadow' }, formatter: (p) => `${p[0].name}: <b>${formatNumber(p[0].value)}</b>` },
  grid: { left: 8, right: 36, top: 4, bottom: 4 },
  xAxis: { type: 'value', minInterval: 1, axisLabel: { show: false }, splitLine: { show: false } },
  yAxis: { type: 'category', inverse: true, data: directionEntries.value.map((e) => e[0]), axisLine: { show: false },
    axisLabel: { width: 170, overflow: 'truncate', color: cssVar('--text-2') } },
  series: [{ type: 'bar', barMaxWidth: 16, cursor: 'pointer', data: directionEntries.value.map((e) => e[1]),
    itemStyle: { color: accent(), borderRadius: [0, 4, 4, 0] },
    label: { show: true, position: 'right', color: cssVar('--text-2'), fontSize: 11 } }],
}))

function donut(entries, list, centerLabel) {
  const sum = entries.reduce((s, e) => s + e[1], 0)
  return {
    xAxis: { show: false },
    yAxis: { show: false },
    tooltip: { trigger: 'item', formatter: (p) => `${p.name}: <b>${formatNumber(p.value)}</b> · ${formatNumber(share(p.value, sum))}%` },
    legend: { orient: 'vertical', top: 'middle', left: '54%', itemGap: 10, icon: 'circle', itemWidth: 8, itemHeight: 8,
      formatter: (name) => `${name}  {v|${formatNumber(entries.find((e) => e[0] === name)?.[1])}}`,
      textStyle: { width: 150, overflow: 'truncate', rich: { v: { color: cssVar('--muted'), fontSize: 12 } } } },
    title: { text: formatNumber(sum), subtext: centerLabel, left: '26%', top: '41%', textAlign: 'center',
      textStyle: { fontSize: 20, fontWeight: 650, color: cssVar('--text'), fontFamily: cssVar('--font-sans') },
      subtextStyle: { fontSize: 11, color: cssVar('--muted') }, itemGap: 2 },
    series: [{ type: 'pie', radius: ['56%', '78%'], center: ['27%', '50%'], cursor: 'pointer', avoidLabelOverlap: true,
      label: { show: false }, labelLine: { show: false }, padAngle: 1.5,
      itemStyle: { borderRadius: 4, borderColor: surface(), borderWidth: 2 },
      emphasis: { scaleSize: 4 },
      data: entries.map(([name, value]) => ({ name, value, itemStyle: { color: colorFor(name, list) } })) }],
  }
}

const productEntries = computed(() => sortedEntries(data.value?.by_almi_product))
const productsOption = computed(() => donut(productEntries.value, opts.value.almi_products, countWord(total.value)))
const typeEntries = computed(() => sortedEntries(data.value?.by_type))
const typeList = computed(() => mergeOptions(PARTNERSHIP_TYPES.filter((t) => opts.value.types.includes(t)), opts.value.types))
const typesOption = computed(() => donut(typeEntries.value, typeList.value, countWord(total.value)))

const statusEntries = computed(() => {
  const counts = data.value?.by_status || {}
  return mergeOptions(PARTNERSHIP_STATUSES, Object.keys(counts)).map((s) => [s, counts[s] || 0])
})
const statusesOption = computed(() => ({
  tooltip: { axisPointer: { type: 'shadow' }, formatter: (p) => `${p[0].name}: <b>${formatNumber(p[0].value)}</b> · ${formatNumber(share(p[0].value, total.value))}%` },
  grid: { left: 8, right: 40, top: 4, bottom: 4 },
  xAxis: { type: 'value', minInterval: 1, axisLabel: { show: false }, splitLine: { show: false } },
  yAxis: { type: 'category', inverse: true, data: statusEntries.value.map((e) => e[0]), axisLine: { show: false }, axisLabel: { color: cssVar('--text-2') } },
  series: [{ type: 'bar', barMaxWidth: 18, cursor: 'pointer',
    showBackground: true, backgroundStyle: { color: cssVar('--surface-3'), borderRadius: 4 },
    data: statusEntries.value.map(([name, value]) => ({ value, itemStyle: { color: lightColor(lightOf(`status:${name}`) || 'gray'), borderRadius: 4 } })),
    label: { show: true, position: 'right', color: cssVar('--text-2'), fontSize: 11 } }],
}))

const onYear = (p) => p?.name && toRegistry({ year: p.name })
const onDirection = (p) => p?.name && toRegistry({ direction: p.name })
const onProduct = (p) => p?.name && toRegistry({ almi_product: p.name })
const onType = (p) => p?.name && toRegistry({ type: p.name })
const onStatus = (p) => p?.name && toRegistry({ status: p.name })

// ---------- раскладка ----------
const BLOCKS = [
  { key: 'kpi', label: 'Ключевые показатели', span: 12 },
  { key: 'lights', label: 'Светофор партнёрств', span: 12 },
  { key: 'years', label: 'Сертификаты по годам', span: 7 },
  { key: 'directions', label: 'Топ направлений', span: 5 },
  { key: 'products', label: 'По продукту АЛМИ', span: 4 },
  { key: 'types', label: 'По типу продукта', span: 4 },
  { key: 'statuses', label: 'По статусу', span: 4 },
]
const layout = useDashboardLayout('project_product', BLOCKS)
const layoutOpen = ref(false)
const visibleBlocks = computed(() => layout.ordered.value.filter((b) => b.visible))
const spans = computed(() => fitSpans(visibleBlocks.value))
// На средних экранах — по два блока в ряд
const spansMd = computed(() => fitSpans(visibleBlocks.value.map((b) => ({ key: b.key, span: b.span >= 7 ? 12 : 6 }))))
const blockStyle = (key) => ({ order: layout.orderOf(key), '--span': spans.value[key] || 12, '--span-md': spansMd.value[key] || 12 })

// ---------- добавление ----------
const adding = ref(false)
function onSaved() {
  adding.value = false
  refresh()
}

const periodText = computed(() => {
  const parts = [f.year ? `${f.year} год` : '', f.status, f.almi_product].filter(Boolean)
  return parts.length ? `Отбор: ${parts.join(' · ')}` : 'Сертификация совместимости продуктов партнёров с продуктами АЛМИ'
})
</script>

<template>
  <div class="page">
    <PageHeader title="Технологические партнёрства" :description="periodText" :updatedAt="app.service('project_product')?.data_updated_at">
      <button class="btn btn-ghost" type="button" title="Состав и порядок блоков" @click="layoutOpen = true"><AppIcon name="settings" :size="15" />Настроить</button>
      <router-link :to="{ path: '/product/registry', query: registryQuery }" class="btn"><AppIcon name="list" :size="15" />Реестр</router-link>
      <PdfButton report="partnerships/summary" />
      <button v-if="canEdit" class="btn btn-primary" type="button" @click="adding = true"><AppIcon name="plus" :size="15" />Добавить партнёрство</button>
    </PageHeader>

    <FilterBar :summary="data ? `${formatNumber(total)} ${countWord(total)}` : ''" :resettable="!isDefault()" @reset="reset">
      <label class="field"><span>Год сертификации</span>
        <select v-model="f.year" class="select"><option value="">Все годы</option><option v-for="y in years" :key="y" :value="String(y)">{{ y }}</option></select>
      </label>
      <label class="field"><span>Статус</span>
        <select v-model="f.status" class="select"><option value="">Все статусы</option><option v-for="s in statuses" :key="s" :value="s">{{ s }}</option></select>
      </label>
      <label class="field"><span>Продукт АЛМИ</span>
        <select v-model="f.almi_product" class="select"><option value="">Все продукты</option><option v-for="p in opts.almi_products" :key="p" :value="p">{{ p }}</option></select>
      </label>
    </FilterBar>

    <EmptyState v-if="noData" icon="handshake" title="Партнёрств пока нет"
                text="Добавьте первое партнёрство — после этого здесь появятся показатели, светофор и графики.">
      <button v-if="canEdit" class="btn btn-primary" type="button" @click="adding = true"><AppIcon name="plus" :size="15" />Добавить партнёрство</button>
    </EmptyState>

    <EmptyState v-else-if="data && !data.total" icon="filter" title="Нет партнёрств по выбранным фильтрам" text="Измените или сбросьте фильтры.">
      <button class="btn" type="button" @click="reset">Сбросить фильтры</button>
    </EmptyState>

    <div v-else class="blocks">
      <section v-if="layout.visible('kpi')" class="block grid grid-kpi" :style="blockStyle('kpi')">
        <KpiCard v-for="k in kpis" :key="k.label" :label="k.label" :value="k.value" :unit="k.unit || ''" :digits="k.digits || 0"
                 :light="k.light || ''" :hint="k.hint || ''" :loading="first" />
      </section>

      <section v-if="layout.visible('lights')" class="block card lights" :style="blockStyle('lights')">
        <header class="card-head">
          <div>
            <h3>Светофор партнёрств</h3>
            <p class="hint">Оценка записи — худшая из оценок по статусу, NDA, соглашению и сроку сертификата</p>
          </div>
          <span class="spacer" />
          <router-link to="/settings/partnership-lights" class="btn btn-sm btn-ghost"><AppIcon name="traffic" :size="14" />Правила</router-link>
        </header>
        <div class="card-body">
          <div v-if="first" class="skeleton" style="height: 220px" />
          <template v-else>
            <div class="overall">
              <div class="overall-head">
                <span class="overall-title">Итоговая оценка записей</span>
                <span class="muted num">{{ formatNumber(recordTotal) }} {{ countWord(recordTotal) }}</span>
              </div>
              <div class="track" role="img" :aria-label="recordSegments.map((s) => `${LIGHT_LABELS[s.light]}: ${s.count}`).join(', ')">
                <span v-for="s in recordSegments" v-show="s.count" :key="s.light" class="seg" :class="s.light" :style="{ flexGrow: s.count }" :title="`${LIGHT_LABELS[s.light]}: ${s.count} (${formatNumber(s.share)}%)`" />
              </div>
              <div class="legend">
                <button v-for="s in recordSegments" :key="s.light" class="legend-item" type="button" :title="`Открыть в реестре: ${LIGHT_LABELS[s.light].toLowerCase()}`" @click="toRegistry({ light: s.light })">
                  <LightBadge :light="s.light" dot />{{ LIGHT_LABELS[s.light] }}
                  <b class="num">{{ formatNumber(s.count) }}</b><span class="muted num">{{ formatNumber(s.share) }}%</span>
                  <AppIcon name="chevron-right" :size="12" class="go" />
                </button>
              </div>
            </div>

            <div class="groups">
              <div v-for="g in lightGroups" :key="g.key" class="group">
                <h4>{{ g.label }}</h4>
                <ul>
                  <li v-for="r in g.items" :key="r.key" :class="{ zero: !r.count }" :title="`${r.label}: ${LIGHT_LABELS[r.light].toLowerCase()} · ${r.count} (${formatNumber(r.share)}%)`">
                    <span class="row-head">
                      <LightBadge :light="r.light" dot />
                      <span class="row-label ellipsis">{{ shortRuleLabel(r.label, r.group) }}</span>
                      <b class="num">{{ formatNumber(r.count) }}</b>
                      <span class="row-share num">{{ formatNumber(r.share) }}%</span>
                    </span>
                    <span class="bar"><span class="fill" :class="r.light" :style="{ width: `${Math.min(100, r.share)}%` }" /></span>
                  </li>
                </ul>
                <p v-if="g.key === 'cert_age' && g.total < total" class="group-note muted">Без даты сертификата: {{ formatNumber(total - g.total) }}</p>
              </div>
            </div>
          </template>
        </div>
      </section>

      <div v-if="layout.visible('years')" class="block" :style="blockStyle('years')">
        <ChartCard title="Сертификаты по годам" hint="По году сертификата; щелчок по столбцу открывает реестр" :height="280" :empty="!first && !yearEntries.length" emptyText="Нет записей с датой сертификата">
          <div v-if="first" class="skeleton fill-skel" />
          <EChart v-else :option="yearsOption" @click="onYear" />
        </ChartCard>
      </div>
      <div v-if="layout.visible('directions')" class="block" :style="blockStyle('directions')">
        <ChartCard title="Топ направлений" :hint="`${directionEntries.length} самых частых направлений`" :height="280" :empty="!first && !directionEntries.length">
          <div v-if="first" class="skeleton fill-skel" />
          <EChart v-else :option="directionsOption" @click="onDirection" />
        </ChartCard>
      </div>


      <div v-if="layout.visible('products')" class="block" :style="blockStyle('products')">
        <ChartCard title="По продукту АЛМИ" hint="С каким продуктом АЛМИ сертифицирован" :height="240" :empty="!first && !productEntries.length">
          <div v-if="first" class="skeleton fill-skel" />
          <EChart v-else :option="productsOption" @click="onProduct" />
        </ChartCard>
      </div>

      <div v-if="layout.visible('types')" class="block" :style="blockStyle('types')">
        <ChartCard title="По типу продукта" hint="ПО, комплексы и оборудование" :height="240" :empty="!first && !typeEntries.length">
          <div v-if="first" class="skeleton fill-skel" />
          <EChart v-else :option="typesOption" @click="onType" />
        </ChartCard>
      </div>
      <div v-if="layout.visible('statuses')" class="block" :style="blockStyle('statuses')">
        <ChartCard title="По статусу" hint="Цвет — оценка статуса по правилам светофора" :height="240" :empty="!first && !total">
          <div v-if="first" class="skeleton fill-skel" />
          <EChart v-else :option="statusesOption" @click="onStatus" />
        </ChartCard>
      </div>

    </div>

    <LayoutDialog v-if="layoutOpen" :items="layout.ordered.value" @close="layoutOpen = false" @save="layout.save" @reset="layout.reset" />
    <PartnershipForm v-if="adding" :options="opts" :defaults="{ status: f.status || 'В работе', almi_product: f.almi_product }" @close="adding = false" @saved="onSaved" />
  </div>
</template>

<style scoped>
.blocks { display: grid; grid-template-columns: repeat(12, minmax(0, 1fr)); gap: var(--sp-4); align-items: stretch; }
.block { grid-column: span var(--span, 12); min-width: 0; }
.block > :deep(.chart-card) { height: 100%; }
@media (max-width: 1100px) { .block { grid-column: span var(--span-md, 12); } }
@media (max-width: 860px) { .block { grid-column: 1 / -1; } }
.fill-skel { height: 100%; }

.lights .card-head { align-items: flex-start; }
.overall { padding: 12px 14px 12px; border: 1px solid var(--border); border-radius: var(--radius); background: var(--surface-2); }
.overall-head { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; margin-bottom: 8px; font-size: var(--fs-sm); }
.overall-title { font-weight: 600; color: var(--text); }
.track { display: flex; gap: 2px; height: 10px; border-radius: 5px; overflow: hidden; background: var(--surface-3); }
.seg { min-width: 4px; }
.seg.green, .fill.green { background: var(--light-green); }
.seg.yellow, .fill.yellow { background: var(--light-yellow); }
.seg.red, .fill.red { background: var(--light-red); }
.fill.gray { background: var(--light-gray); }
.legend { display: flex; flex-wrap: wrap; gap: 4px 6px; margin-top: 8px; }
.legend-item { display: inline-flex; align-items: center; gap: 7px; height: 28px; padding: 0 8px 0 9px; border: 1px solid transparent; border-radius: var(--radius-sm); background: transparent; color: var(--text-2); font-size: var(--fs-sm); cursor: pointer; transition: all var(--t-fast); }
.legend-item b { color: var(--text); font-weight: 650; }
.legend-item .go { color: var(--faint); opacity: 0; transition: opacity var(--t-fast); }
.legend-item:hover { background: var(--surface); border-color: var(--border); color: var(--text); }
.legend-item:hover .go { opacity: 1; }

.groups { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: var(--sp-5) var(--sp-6); margin-top: var(--sp-5); }
@media (max-width: 1280px) { .groups { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 640px) { .groups { grid-template-columns: minmax(0, 1fr); } }
.group h4 { font-size: var(--fs-xs); font-weight: 650; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); margin-bottom: 8px; }
.group ul { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 10px; }
.group li.zero { opacity: .5; }
.row-head { display: flex; align-items: center; gap: 8px; font-size: var(--fs-sm); }
.row-label { flex: 1; min-width: 0; color: var(--text-2); }
.row-head b { font-weight: 650; }
.row-share { width: 46px; text-align: right; color: var(--muted); font-size: var(--fs-xs); }
.bar { display: block; height: 4px; margin: 5px 0 0 16px; border-radius: 2px; background: var(--surface-3); overflow: hidden; }
.fill { display: block; height: 100%; border-radius: 2px; transition: width var(--t); }
.group-note { margin-top: 8px; font-size: var(--fs-xs); }
</style>
