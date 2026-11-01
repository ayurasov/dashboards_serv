<script setup>
import { computed, ref, watch } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import FilterBar from '@/components/ui/FilterBar.vue'
import ChartCard from '@/components/ui/ChartCard.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import ImportDialog from '@/components/ui/ImportDialog.vue'
import LightBadge from '@/components/ui/LightBadge.vue'
import PdfButton from '@/components/ui/PdfButton.vue'
import EChart from '@/components/charts/EChart.vue'
import NaumenKpi from '@/components/tp/NaumenKpi.vue'
import { axisNumber, chartColors, cssVar, lightColor } from '@/components/charts/echarts'
import { tpApi } from '@/api/services'
import { useAsync } from '@/composables/useAsync'
import { useQueryState } from '@/composables/useQueryState'
import { useAuthStore } from '@/stores/auth'
import { useAppStore } from '@/stores/app'
import { usePaletteStore } from '@/stores/palette'
import { formatDateTime, formatNumber, formatPercent, monthLabel, plural } from '@/utils/format'
import {
  CLOSED_STATUSES, OVERDUE_LEVELS, QUICK_MONTHS, dayText, distribution, escapeHtml, formatHours, hoursHint,
  overdueLight, periodCount, withBar,
} from '@/domain/naumen'

const auth = useAuthStore()
const app = useAppStore()
const palette = usePaletteStore()
const canManage = computed(() => auth.can('tech', 'manager'))
const { state: f, reset, isDefault } = useQueryState({ months: 12, year: 0, org: '' })

const filters = useAsync(() => tpApi.naumenFilters())
const params = computed(() => ({ year: f.year || undefined, org: f.org || undefined, months: f.months || undefined }))
const { data: raw, loading, reload } = useAsync(() => tpApi.naumenSummary(params.value), { immediate: false })
watch(params, () => reload(), { immediate: true })

const noTickets = computed(() => !!filters.data.value && !filters.data.value.years.length)
const data = computed(() => (raw.value && !raw.value.empty ? raw.value : null))
const nothingFound = computed(() => !!raw.value?.empty && !noTickets.value)
const first = computed(() => loading.value && !raw.value)

function pickQuick(value) {
  f.months = value
}
function pickYear(year) {
  f.year = year
  if (year) f.months = 0
}
function pickOrg(org) {
  f.org = f.org === org ? '' : org
}

const lastImport = computed(() => filters.data.value?.last_import)
const description = computed(() => {
  const i = lastImport.value
  if (!i) return 'Заявки из выгрузки Naumen Service Desk'
  return `Последняя загрузка: «${i.filename}», ${i.username}, ${formatDateTime(i.created_at)} · ${formatNumber(i.rows)} ${plural(i.rows, ['строка', 'строки', 'строк'])}`
})
const summary = computed(() => {
  if (!data.value) return ''
  const m = data.value.months.length
  return `${dayText(data.value.first)} — ${dayText(data.value.last)} · ${m} ${plural(m, ['месяц', 'месяца', 'месяцев'])}`
})
const importOpen = ref(false)
function onImported() {
  filters.reload()
  reload()
}

// ---------- графики ----------
/** Цвета берутся из CSS-токенов; пересчитываются при смене темы и палитры. */
const theme = computed(() => {
  void app.resolvedTheme
  void palette.colors
  return {
    c: chartColors(), green: lightColor('green'), red: lightColor('red'), gray: lightColor('gray'),
    surface: cssVar('--surface'), text: cssVar('--text'), text2: cssVar('--text-2'), muted: cssVar('--muted'),
  }
})
const months = computed(() => data.value?.months || [])
const labels = computed(() => months.value.map((m) => monthLabel(m.month, true)))
const dot = (color) => `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px;background:${color}"></span>`
const tipTitle = (i) => `<div style="margin-bottom:4px;font-weight:600">${monthLabel(months.value[i]?.month)}</div>`
const bar = (color, side = 'top') => ({ color, borderRadius: side === 'top' ? [4, 4, 0, 0] : [0, 4, 4, 0] })
const avgLine = (value, text) => (value === null || value === undefined ? undefined : {
  symbol: 'none', silent: true, data: [{ yAxis: value }],
  lineStyle: { type: 'dashed', width: 1, color: theme.value.muted },
  label: { formatter: text, position: 'insideEndTop', color: theme.value.muted, fontSize: 11 },
})

const flowOption = computed(() => {
  const { c } = theme.value
  return {
    legend: { data: ['Зарегистрировано', 'Решено'] },
    tooltip: {
      formatter: (items) => tipTitle(items[0].dataIndex) + items.map((p) => `${dot(p.color)}${p.seriesName}: <b>${formatNumber(p.value)}</b>`).join('<br>'),
    },
    xAxis: { type: 'category', data: labels.value },
    yAxis: { type: 'value', minInterval: 1, axisLabel: { formatter: axisNumber } },
    series: [
      { name: 'Зарегистрировано', type: 'bar', barMaxWidth: 18, barGap: '20%', itemStyle: bar(c[1]), data: months.value.map((m) => m.registered) },
      { name: 'Решено', type: 'bar', barMaxWidth: 18, itemStyle: bar(c[2]), data: months.value.map((m) => m.solved) },
    ],
  }
})

const shareOption = computed(() => {
  const { c } = theme.value
  const fmt = (p, key) => {
    const m = months.value[p.dataIndex]
    return `${dot(p.color)}${p.seriesName}: <b>${formatPercent(p.value)}</b> <span style="color:${theme.value.muted}">${formatNumber(m[key])} из ${formatNumber(m.registered)}</span>`
  }
  return {
    legend: { data: ['Просрочено', 'Возобновлено'] },
    tooltip: { formatter: (items) => tipTitle(items[0].dataIndex) + items.map((p) => fmt(p, p.seriesIndex === 0 ? 'overdue' : 'reopened')).join('<br>') },
    xAxis: { type: 'category', data: labels.value, boundaryGap: false },
    yAxis: { type: 'value', axisLabel: { formatter: '{value}%' } },
    series: [
      { name: 'Просрочено', type: 'line', smooth: 0.25, smoothMonotone: 'x', showSymbol: months.value.length <= 18, symbolSize: 7, lineStyle: { width: 2 }, itemStyle: { color: c[0] },
        areaStyle: { opacity: 0.08 }, data: months.value.map((m) => m.overdue_pct),
        markLine: avgLine(data.value?.overdue_pct, `За период ${formatPercent(data.value?.overdue_pct)}`) },
      { name: 'Возобновлено', type: 'line', smooth: 0.25, smoothMonotone: 'x', showSymbol: months.value.length <= 18, symbolSize: 7, lineStyle: { width: 2 }, itemStyle: { color: c[3] },
        data: months.value.map((m) => m.reopened_pct) },
    ],
  }
})

function hoursOption(key, color, total, title) {
  return {
    legend: { show: false },
    grid: { top: 16 },
    tooltip: {
      formatter: (items) => {
        const p = items[0]
        return `${tipTitle(p.dataIndex)}${dot(p.color)}${title}: <b>${formatHours(p.value)}</b> <span style="color:${theme.value.muted}">${hoursHint(p.value)}</span>`
      },
    },
    xAxis: { type: 'category', data: labels.value, boundaryGap: false },
    yAxis: { type: 'value', axisLabel: { formatter: axisNumber } },
    series: [{
      name: title, type: 'line', smooth: 0.25, smoothMonotone: 'x', showSymbol: months.value.length <= 18, symbolSize: 7, connectNulls: true, lineStyle: { width: 2 },
      itemStyle: { color }, areaStyle: { opacity: 0.1 }, data: months.value.map((m) => m[key]),
      markLine: avgLine(total, `За период ${formatHours(total)}`),
    }],
  }
}
const procOption = computed(() => hoursOption('avg_proc_hours', theme.value.c[4], data.value?.avg_proc_hours, 'Обработка'))
const resolveOption = computed(() => hoursOption('avg_resolve_hours', theme.value.c[5], data.value?.avg_resolve_hours, 'Решение'))

const channels = computed(() => distribution(data.value?.channels, 'channel'))
const channelsOption = computed(() => {
  const { c, surface, text, muted } = theme.value
  const colors = [c[1], c[3], c[4], c[5], c[2], c[6], c[0]]
  const byName = Object.fromEntries(channels.value.map((ch) => [ch.name, ch]))
  return {
    color: colors,
    xAxis: { show: false },
    yAxis: { show: false },
    tooltip: { trigger: 'item', formatter: (p) => `${dot(p.color)}${escapeHtml(p.name)}: <b>${formatNumber(p.value)}</b> · ${formatPercent(byName[p.name]?.share)}` },
    title: {
      text: formatNumber(data.value?.total), subtext: plural(data.value?.total || 0, ['заявка', 'заявки', 'заявок']),
      left: '29%', top: '41%', textAlign: 'center', itemGap: 2,
      textStyle: { fontSize: 20, fontWeight: 650, color: text }, subtextStyle: { fontSize: 11, color: muted },
    },
    legend: {
      orient: 'vertical', top: 'middle', left: '60%', itemGap: 12, icon: 'circle', itemWidth: 8, itemHeight: 8,
      formatter: (name) => `{n|${name}}\n{v|${formatNumber(byName[name]?.value)} · ${formatPercent(byName[name]?.share)}}`,
      textStyle: { rich: { n: { fontSize: 12, color: text, lineHeight: 18 }, v: { fontSize: 11, color: muted, lineHeight: 16 } } },
    },
    series: [{
      type: 'pie', radius: ['56%', '80%'], center: ['30%', '50%'], avoidLabelOverlap: true, label: { show: false },
      itemStyle: { borderColor: surface, borderWidth: 2, borderRadius: 4 },
      emphasis: { scale: true, scaleSize: 4 },
      data: channels.value.map((ch) => ({ name: ch.name, value: ch.value })),
    }],
  }
})

const statuses = computed(() => distribution(data.value?.statuses, 'status'))
const statusesOption = computed(() => {
  const { c, green, text2 } = theme.value
  return {
    legend: { show: false },
    grid: { left: 8, right: 84, top: 8, bottom: 8, containLabel: true },
    tooltip: { trigger: 'item', formatter: (p) => `${dot(p.color)}${escapeHtml(p.name)}: <b>${formatNumber(p.value)}</b> · ${formatPercent(statuses.value[p.dataIndex]?.share)}` },
    xAxis: { type: 'value', show: false },
    yAxis: { type: 'category', inverse: true, data: statuses.value.map((s) => s.name), axisLine: { show: false }, axisLabel: { color: text2, fontSize: 12, width: 150, overflow: 'truncate' } },
    series: [{
      type: 'bar', barWidth: 14, barMinHeight: 3,
      data: statuses.value.map((s) => ({ value: s.value, itemStyle: bar(CLOSED_STATUSES.includes(s.name) ? green : c[1], 'right') })),
      label: { show: true, position: 'right', color: text2, fontSize: 11, formatter: (p) => `${formatNumber(p.value)} · ${formatPercent(statuses.value[p.dataIndex]?.share)}` },
    }],
  }
})
const statusesHeight = computed(() => Math.max(180, Math.min(320, statuses.value.length * 34 + 24)))

// ---------- таблицы ----------
const TOP = 10
const showAllOrgs = ref(false)
const showAllPeople = ref(false)
const orgs = computed(() => withBar(data.value?.orgs || []))
const orgRows = computed(() => (showAllOrgs.value ? orgs.value : orgs.value.slice(0, TOP)))
const people = computed(() => withBar(data.value?.responsibles || []))
const peopleRows = computed(() => (showAllPeople.value ? people.value : people.value.slice(0, TOP)))
const overdueNote = `Просрочка: до ${OVERDUE_LEVELS.yellow}% — норма, до ${OVERDUE_LEVELS.red}% — внимание, выше — критично`
</script>

<template>
  <div class="page">
    <PageHeader title="Заявки Naumen" :description="description">
      <PdfButton report="tp/naumen" :params="params" />
      <button v-if="canManage" class="btn" type="button" @click="importOpen = true"><AppIcon name="upload" :size="15" />Загрузить выгрузку</button>
    </PageHeader>

    <EmptyState v-if="noTickets" icon="ticket" title="Заявок пока нет"
                :text="canManage ? 'Загрузите выгрузку «Все заявки» из Naumen Service Desk в формате xlsx — после этого здесь появится аналитика.' : 'Аналитика появится, когда ответственный сотрудник загрузит выгрузку из Naumen.'">
      <button v-if="canManage" class="btn btn-primary" type="button" @click="importOpen = true"><AppIcon name="upload" :size="15" />Загрузить выгрузку</button>
    </EmptyState>

    <template v-else>
      <FilterBar :summary="summary" :resettable="!isDefault()" @reset="reset">
        <div class="field"><span>Период</span>
          <div class="row-wrap chips">
            <button v-for="q in QUICK_MONTHS" :key="q.value" type="button" class="chip" :class="{ active: f.months === q.value }" @click="pickQuick(q.value)">{{ q.label }}</button>
          </div>
        </div>
        <div class="field"><span>Год</span>
          <div class="row-wrap chips">
            <button type="button" class="chip" :class="{ active: !f.year }" @click="pickYear(0)">Все</button>
            <button v-for="y in filters.data.value?.years || []" :key="y" type="button" class="chip num" :class="{ active: f.year === y }" @click="pickYear(y)">{{ y }}</button>
          </div>
        </div>
        <label class="field"><span>Организация</span>
          <select v-model="f.org" class="select org-select">
            <option value="">Все организации</option>
            <option v-if="f.org && !(filters.data.value?.orgs || []).some((o) => o.org === f.org)" :value="f.org">{{ f.org }}</option>
            <option v-for="o in filters.data.value?.orgs || []" :key="o.org" :value="o.org">{{ o.org }} · {{ formatNumber(o.count) }}</option>
          </select>
        </label>
      </FilterBar>

      <EmptyState v-if="nothingFound" icon="filter" title="Нет заявок по выбранным фильтрам" text="Расширьте период, выберите другой год или организацию.">
        <button class="btn" type="button" @click="reset"><AppIcon name="refresh" :size="14" />Сбросить фильтры</button>
      </EmptyState>

      <div v-else class="blocks" :class="{ refreshing: loading && !first }">
        <div class="kpis">
          <NaumenKpi label="Всего заявок" :value="data?.total" :caption="data ? `зарегистрировано за ${periodCount(data.months.length, 'months')}` : ''" :loading="first" />
          <NaumenKpi label="Закрыто" :value="data?.closed" :caption="data ? `${formatPercent(data.closed_pct)} · в работе ${formatNumber(data.in_progress)}` : ''"
                     hint="Статусы «Закрыта» и «Выполнена»" :loading="first" />
          <NaumenKpi label="Просрочено" :value="data?.overdue" :light="data ? overdueLight(data.overdue_pct) : ''" :caption="data ? `${formatPercent(data.overdue_pct)} от всех заявок` : ''"
                     :hint="overdueNote" :loading="first" />
          <NaumenKpi label="Возобновлено" :value="data?.reopened" :caption="data ? `${formatPercent(data.reopened_pct)} от всех заявок` : ''" :loading="first" />
          <NaumenKpi label="Среднее время обработки" :value="data?.avg_proc_hours" unit="ч" :digits="0" :caption="data ? hoursHint(data.avg_proc_hours) || 'в среднем на заявку' : ''"
                     hint="Поле «Время обработки заявки» из выгрузки" :loading="first" />
          <NaumenKpi label="Среднее время решения" :value="data?.avg_resolve_hours" unit="ч" :digits="0" :caption="data ? `${hoursHint(data.avg_resolve_hours) || 'от регистрации'} до решения` : ''"
                     hint="От даты регистрации до даты решения, календарное время" :loading="first" />
        </div>

        <div class="section-title"><h2>Динамика по месяцам</h2><span class="muted">по дате регистрации; решённые — по дате решения</span></div>
        <div class="grid grid-2">
          <ChartCard title="Зарегистрировано и решено" hint="Количество заявок за месяц" :empty="!first && !months.length">
            <div v-if="first" class="skeleton fill" />
            <EChart v-else :option="flowOption" />
          </ChartCard>
          <ChartCard title="Просроченные и возобновлённые" hint="Доля от зарегистрированных за месяц, %" :empty="!first && !months.length">
            <div v-if="first" class="skeleton fill" />
            <EChart v-else :option="shareOption" />
          </ChartCard>
          <ChartCard title="Среднее время обработки" hint="Часы, по месяцу регистрации" :height="260" :empty="!first && !months.length">
            <div v-if="first" class="skeleton fill" />
            <EChart v-else :option="procOption" />
          </ChartCard>
          <ChartCard title="Среднее время решения" hint="Часы от регистрации до решения, по месяцу решения" :height="260" :empty="!first && !months.length">
            <div v-if="first" class="skeleton fill" />
            <EChart v-else :option="resolveOption" />
          </ChartCard>
        </div>

        <div class="section-title"><h2>Структура обращений</h2></div>
        <div class="grid grid-2">
          <ChartCard title="Каналы обращений" hint="Способ обращения из выгрузки" :height="statusesHeight" :empty="!first && !channels.length">
            <div v-if="first" class="skeleton fill" />
            <EChart v-else :option="channelsOption" />
          </ChartCard>
          <ChartCard title="Статусы заявок" hint="Зелёным — закрытые («Закрыта», «Выполнена»)" :height="statusesHeight" :empty="!first && !statuses.length">
            <div v-if="first" class="skeleton fill" />
            <EChart v-else :option="statusesOption" />
          </ChartCard>
        </div>

        <div class="section-title"><h2>Организации и исполнители</h2><span class="muted">{{ overdueNote }}</span></div>
        <div class="tables">
          <section class="card">
            <header class="card-head">
              <div><h3>Организации</h3><p class="hint">Нажмите на строку, чтобы показать заявки только этой организации</p></div>
              <span class="spacer" />
              <span v-if="orgs.length" class="muted count">{{ orgs.length }} {{ plural(orgs.length, ['организация', 'организации', 'организаций']) }}</span>
            </header>
            <div class="card-body flush">
              <div v-if="first" class="skeleton" style="height: 320px; margin: 0 16px" />
              <div v-else class="table-wrap scroll-thin">
                <table class="table table-compact">
                  <thead>
                    <tr><th class="org-col">Организация</th><th class="num">Заявок</th><th class="num">Закрыто</th><th class="num">Просрочено</th><th class="num" title="Доля просроченных заявок">Доля</th><th class="num" title="Среднее время обработки заявки">Обработка</th></tr>
                  </thead>
                  <tbody>
                    <tr v-for="o in orgRows" :key="o.org" class="clickable" :class="{ selected: f.org === o.org }" :title="f.org === o.org ? 'Показать все организации' : 'Показать только эту организацию'" @click="pickOrg(o.org)">
                      <td class="org-col">
                        <span class="org-name">
                          <span class="ellipsis">{{ o.org }}</span>
                          <AppIcon v-if="f.org === o.org" name="filter" :size="12" class="org-filter" />
                        </span>
                      </td>
                      <td class="num">
                        <div class="with-bar"><span class="strong">{{ formatNumber(o.total) }}</span><span class="track"><span class="fill-bar" :style="{ width: `${o.bar}%` }" /></span></div>
                      </td>
                      <td class="num muted">{{ formatNumber(o.closed) }}</td>
                      <td class="num">{{ formatNumber(o.overdue) }}</td>
                      <td class="num"><LightBadge :light="overdueLight(o.overdue_pct)" :label="formatPercent(o.overdue_pct)" /></td>
                      <td class="num muted" :title="hoursHint(o.avg_proc_hours)">{{ formatHours(o.avg_proc_hours) }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div v-if="orgs.length > TOP || f.org" class="table-foot">
                <button v-if="orgs.length > TOP" class="btn btn-ghost btn-sm" type="button" @click="showAllOrgs = !showAllOrgs">
                  <AppIcon :name="showAllOrgs ? 'chevron-up' : 'chevron-down'" :size="13" />{{ showAllOrgs ? 'Свернуть' : `Показать все ${orgs.length}` }}
                </button>
                <button v-if="f.org" class="btn btn-ghost btn-sm" type="button" @click="f.org = ''"><AppIcon name="x" :size="13" />Все организации</button>
              </div>
            </div>
          </section>

          <section class="card">
            <header class="card-head">
              <div><h3>Ответственные</h3><p class="hint">Сотрудники с наибольшим числом заявок</p></div>
            </header>
            <div class="card-body flush">
              <div v-if="first" class="skeleton" style="height: 320px; margin: 0 16px" />
              <div v-else-if="!people.length" class="muted empty-line">Ответственные в выгрузке не указаны</div>
              <div v-else class="table-wrap scroll-thin">
                <table class="table table-compact">
                  <thead><tr><th>Сотрудник</th><th class="num">Заявок</th><th class="num">Просрочено</th><th class="num" title="Доля просроченных заявок">Доля</th></tr></thead>
                  <tbody>
                    <tr v-for="p in peopleRows" :key="p.name">
                      <td class="person ellipsis" :title="p.name">{{ p.name }}</td>
                      <td class="num">
                        <div class="with-bar"><span class="strong">{{ formatNumber(p.total) }}</span><span class="track"><span class="fill-bar" :style="{ width: `${p.bar}%` }" /></span></div>
                      </td>
                      <td class="num">{{ formatNumber(p.overdue) }}</td>
                      <td class="num"><LightBadge :light="overdueLight(p.overdue_pct)" :label="formatPercent(p.overdue_pct)" /></td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div v-if="people.length > TOP" class="table-foot">
                <button class="btn btn-ghost btn-sm" type="button" @click="showAllPeople = !showAllPeople">
                  <AppIcon :name="showAllPeople ? 'chevron-up' : 'chevron-down'" :size="13" />{{ showAllPeople ? 'Свернуть' : `Показать все ${people.length}` }}
                </button>
              </div>
            </div>
          </section>
        </div>
      </div>
    </template>

    <ImportDialog v-if="importOpen" title="Загрузка выгрузки Naumen" :endpoint="tpApi.naumenImportEndpoint" accept=".xlsx"
                  description="Отчёт «Все заявки» из Naumen Service Desk, xlsx с заголовками в первой строке. Обязателен столбец «Дата регистрации»; номер, статус, организация, ответственный, способ обращения, просрочка и время обработки читаются по названиям столбцов."
                  mergeHint="Заявки сопоставляются по номеру: новые добавятся, известные обновятся"
                  replaceHint="Все заявки будут заменены содержимым файла"
                  @close="importOpen = false" @done="onImported" />
  </div>
</template>

<style scoped>
.chips { gap: 6px; }
.org-select { max-width: 320px; }
.blocks { display: flex; flex-direction: column; gap: var(--sp-4); transition: opacity var(--t); }
.blocks.refreshing { opacity: .6; pointer-events: none; }
.blocks .section-title { margin-top: var(--sp-3); }
.kpis { display: grid; gap: var(--sp-4); grid-template-columns: repeat(6, minmax(0, 1fr)); }
@media (max-width: 1360px) { .kpis { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
@media (max-width: 640px) { .kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
.fill { height: 100%; }

.tables { display: grid; gap: var(--sp-4); grid-template-columns: minmax(0, 1fr); align-items: start; }
@media (min-width: 1600px) { .tables { grid-template-columns: minmax(0, 3fr) minmax(0, 2fr); } }
.card-head .hint { margin-top: 2px; font-size: var(--fs-xs); color: var(--muted); }
.count { font-size: var(--fs-sm); }
.flush { padding: var(--sp-3) 0 0; }
.flush .table-wrap { border-radius: 0; }
.org-col { max-width: 340px; }
.org-name { display: flex; align-items: center; gap: 6px; min-width: 0; font-weight: 520; }
.org-filter { color: var(--chart-2); flex: 0 0 auto; }
.person { max-width: 300px; }
tr.selected td { background: color-mix(in srgb, var(--chart-2) 8%, transparent); }
.with-bar { display: inline-flex; flex-direction: column; align-items: flex-end; gap: 3px; min-width: 64px; }
.track { display: block; width: 64px; height: 3px; border-radius: 2px; background: var(--surface-3); overflow: hidden; }
.fill-bar { display: block; height: 100%; border-radius: 2px; background: var(--chart-2); }
.strong { font-weight: 600; }
.table-foot { display: flex; gap: var(--sp-2); padding: 8px 10px; border-top: 1px solid var(--border); }
.empty-line { padding: 24px 20px; font-size: var(--fs-sm); }
</style>
