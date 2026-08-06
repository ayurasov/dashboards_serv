<template>
  <div v-if="loading" class="tempty">Загрузка…</div>
  <div v-else-if="error" class="tempty">Ошибка: {{ error }}</div>
  <div v-else-if="!periods.length" class="tempty">Нет партнёрств с датой сертификата</div>
  <template v-else>
    <div class="filters">
      <select class="fsel" v-model="selectedYear">
        <option v-for="p in periods" :key="p.year" :value="p.year">{{ p.label }}</option>
      </select>
      <div class="tinfo" style="flex:1;margin:0" v-if="current">
        {{ current.label }}: партнёрств — {{ current.total }}<template v-if="previous">, сравнение с {{ previous.label }}</template>
      </div>
      <router-link class="btn btn-g" to="/product">К дашборду</router-link>
    </div>

    <div class="kpi-grid" v-if="current">
      <div class="kpi" v-for="k in kpis" :key="k.label">
        <div class="kpi-lbl">{{ k.label }}</div>
        <div class="kpi-val" :style="k.color ? { color: k.color } : null">{{ k.value }}</div>
        <div class="kpi-sub" v-if="previous">
          <span class="dtrend" :class="trendClass(k.value, k.prev, k.better)">
            {{ arrow(k.value, k.prev) }} {{ delta(k.value - k.prev) }}
          </span>
          к {{ previous.label }}
        </div>
        <div class="kpi-sub" v-else>нет предыдущего периода</div>
      </div>
    </div>

    <div class="cgrid-2">
      <div class="ccard">
        <div class="ctitle">Светофор по годам</div>
        <e-chart :option="lightYearOpt" :height="260" />
      </div>
      <div class="ccard">
        <div class="ctitle">Светофор — {{ current?.label || '—' }}</div>
        <div class="slist" v-if="current">
          <div class="slist-row" v-for="l in LIGHTS" :key="l.key">
            <span class="light-dot" :class="'light-' + l.key"></span>
            <span class="slist-lbl">{{ l.label }}</span>
            <span class="slist-val">{{ current[l.key] }} ({{ share(current[l.key]) }}%)</span>
          </div>
          <div class="slist-row">
            <span class="slist-lbl">Подписано NDA</span>
            <span class="slist-val">{{ current.nda_count }} ({{ share(current.nda_count) }}%)</span>
          </div>
          <div class="slist-row">
            <span class="slist-lbl">Подписано соглашений</span>
            <span class="slist-val">{{ current.agreement_count }} ({{ share(current.agreement_count) }}%)</span>
          </div>
        </div>
      </div>
    </div>

    <div class="cgrid-2">
      <div class="ccard">
        <div class="ctitle">Динамика партнёрств по годам</div>
        <e-chart :option="dynamicsOpt" :height="260" />
      </div>
      <div class="ccard">
        <div class="ctitle">Статусы — {{ current?.label || '—' }}</div>
        <e-chart :option="statusOpt" :height="260" @click="onStatusClick" />
      </div>
    </div>

    <div class="ccard">
      <div class="ctitle">Показатели по годам</div>
      <div class="twrap">
        <div class="tscroll">
          <table>
            <thead>
              <tr>
                <th>Показатель</th>
                <th v-for="p in periods" :key="p.year">{{ p.label }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in ROWS" :key="r.key">
                <td class="td-p">
                  <span v-if="r.light" class="light-dot" :class="'light-' + r.light"></span>
                  {{ r.label }}
                </td>
                <td v-for="p in periods" :key="p.year" class="td-mono">{{ p[r.key] }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <div class="ccard" v-if="current">
      <div class="ctitle">Продукты АЛМИ — {{ current.label }}</div>
      <div class="twrap">
        <div class="tscroll">
          <table>
            <thead><tr><th>Продукт АЛМИ</th><th>Партнёрств</th><th>Доля</th></tr></thead>
            <tbody>
              <tr v-for="[name, count] in currentProducts" :key="name" class="row-click"
                  @click="$router.push({ path: '/product/registry', query: { almi_product: name } })">
                <td class="td-p">{{ name }}</td>
                <td class="td-mono">{{ count }}</td>
                <td class="td-mono">{{ share(count) }}%</td>
              </tr>
              <tr v-if="!currentProducts.length"><td colspan="3" class="tempty">Нет данных</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </template>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import EChart from '../components/EChart.vue'
import { api } from '../api/client.js'
import { usePaletteStore } from '../stores/palette.js'

const router = useRouter()
const palette = usePaletteStore()

const loading = ref(true)
const error = ref('')
const periods = ref([])
const selectedYear = ref(null)

const LIGHTS = [
  { key: 'green', label: 'Норма (завершено)' },
  { key: 'yellow', label: 'Внимание (в работе / отложено)' },
  { key: 'red', label: 'Критично (не подписывают)' },
]
const lightColor = (key) => palette.trafficLight[key]

const ROWS = [
  { key: 'total', label: 'Всего партнёрств' },
  { key: 'green', label: 'Норма', light: 'green' },
  { key: 'yellow', label: 'Внимание', light: 'yellow' },
  { key: 'red', label: 'Критично', light: 'red' },
  { key: 'nda_count', label: 'Подписано NDA' },
  { key: 'agreement_count', label: 'Подписано соглашений' },
]

const currentIndex = computed(() => {
  const i = periods.value.findIndex(p => p.year === selectedYear.value)
  return i >= 0 ? i : periods.value.length - 1
})
const current = computed(() => periods.value[currentIndex.value] || null)
const previous = computed(() => (currentIndex.value > 0 ? periods.value[currentIndex.value - 1] : null))

function share(n) { return current.value?.total ? Math.round((n / current.value.total) * 100) : 0 }

function delta(diff) { return diff > 0 ? `+${diff}` : String(diff) }
function arrow(cur, prev) { return cur === prev ? '→' : (cur > prev ? '↑' : '↓') }
function trendClass(cur, prev, better) {
  if (cur === prev) return 'flat'
  const up = cur > prev
  if (better === 'lower') return up ? 'down' : 'up'
  return up ? 'up' : 'down'
}

const KPI_DEFS = [
  { key: 'total', label: 'Всего партнёрств', better: 'higher' },
  { key: 'green', label: 'Норма', better: 'higher', color: 'var(--c-ok)' },
  { key: 'yellow', label: 'Внимание', better: 'lower', color: 'var(--c-warn)' },
  { key: 'red', label: 'Критично', better: 'lower', color: 'var(--c-err)' },
  { key: 'nda_count', label: 'NDA', better: 'higher' },
  { key: 'agreement_count', label: 'Соглашения', better: 'higher' },
]

const kpis = computed(() => KPI_DEFS.map(d => ({
  label: d.label, better: d.better, color: d.color,
  value: current.value?.[d.key] ?? 0,
  prev: previous.value?.[d.key] ?? 0,
})))

const currentProducts = computed(() =>
  Object.entries(current.value?.by_almi_product || {}).sort((a, b) => b[1] - a[1]))

const lightYearOpt = computed(() => ({
  tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
  legend: { data: LIGHTS.map(l => l.label), bottom: 0, textStyle: { fontSize: 10 } },
  grid: { left: 35, right: 12, top: 12, bottom: 48 },
  xAxis: { type: 'category', data: periods.value.map(p => p.label), axisLabel: { fontSize: 10 } },
  yAxis: { type: 'value', minInterval: 1, axisLabel: { fontSize: 10 } },
  series: LIGHTS.map(l => ({
    name: l.label, type: 'bar', stack: 'lights',
    data: periods.value.map(p => p[l.key]),
    itemStyle: { color: lightColor(l.key) },
  })),
}))

const dynamicsOpt = computed(() => ({
  tooltip: { trigger: 'axis' },
  legend: { bottom: 0, textStyle: { fontSize: 10 } },
  grid: { left: 35, right: 12, top: 12, bottom: 40 },
  xAxis: { type: 'category', data: periods.value.map(p => p.label), axisLabel: { fontSize: 10 } },
  yAxis: { type: 'value', minInterval: 1, axisLabel: { fontSize: 10 } },
  series: [
    { name: 'Всего', type: 'line', smooth: true, symbolSize: 6,
      data: periods.value.map(p => p.total), itemStyle: { color: '#1a4f80' } },
    { name: 'NDA', type: 'line', smooth: true, symbolSize: 6,
      data: periods.value.map(p => p.nda_count), itemStyle: { color: '#6b2fa0' } },
    { name: 'Соглашения', type: 'line', smooth: true, symbolSize: 6,
      data: periods.value.map(p => p.agreement_count), itemStyle: { color: '#a06010' } },
  ],
}))

const statusOpt = computed(() => ({
  tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
  legend: { bottom: 0, textStyle: { fontSize: 10 } },
  series: [{
    type: 'pie', radius: ['38%', '58%'], center: ['50%', '44%'], avoidLabelOverlap: true,
    data: Object.entries(current.value?.by_status || {}).map(([name, value]) => ({ name, value })),
    label: { formatter: '{b}\n{d}%', fontSize: 11, lineHeight: 14 },
  }],
}))

function onStatusClick(params) {
  if (params?.name) router.push({ path: '/product/registry', query: { status: params.name } })
}

onMounted(async () => {
  loading.value = true
  try {
    periods.value = await api.get('/partnerships/summary')
    selectedYear.value = periods.value.at(-1)?.year ?? null
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
})
</script>
