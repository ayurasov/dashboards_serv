<script setup>
import { computed, ref } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import FilterBar from '@/components/ui/FilterBar.vue'
import KpiCard from '@/components/ui/KpiCard.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import ImportDialog from '@/components/ui/ImportDialog.vue'
import LightBadge from '@/components/ui/LightBadge.vue'
import PdfButton from '@/components/ui/PdfButton.vue'
import TpRegWeekDialog from '@/components/tp/TpRegWeekDialog.vue'
import { commonApi, tpApi } from '@/api/services'
import { useAsync } from '@/composables/useAsync'
import { useQueryState } from '@/composables/useQueryState'
import { confirm } from '@/composables/useConfirm'
import { toastOk } from '@/composables/useToast'
import { useAuthStore } from '@/stores/auth'
import { useAppStore } from '@/stores/app'
import { formatDateTime, formatNumber, plural } from '@/utils/format'
import { LIGHT_LABELS, evaluate } from '@/utils/lights'
import {
  DEFAULT_GROUPS, filterByYear, formatMetric, groupColumns, isoWeekOf, matchesSearch, nextIsoWeek, shortLabel,
  sortWeeks, sumBy, weekRangeText, yearsOf,
} from '@/domain/naumen'

const auth = useAuthStore()
const app = useAppStore()
const canEdit = computed(() => auth.can('tech', 'editor'))
const canManage = computed(() => auth.can('tech', 'manager'))
const { state: f } = useQueryState({ year: 0, search: '', groups: [...DEFAULT_GROUPS], sort: 'period', dir: 'desc' })

const columns = useAsync(() => tpApi.columns())
const reports = useAsync(() => tpApi.reports())
const rules = useAsync(() => commonApi.lightRules('tech'))
const imports = useAsync(() => commonApi.imports('tech', 20))

const all = computed(() => reports.data.value || [])
const groups = computed(() => groupColumns(columns.data.value || []))
const visibleGroups = computed(() => groups.value.filter((g) => f.groups.includes(g.key)))
const ruleMap = computed(() => Object.fromEntries((rules.data.value || []).filter((r) => r.enabled).map((r) => [r.metric_key, r])))
const ruleCount = computed(() => Object.keys(ruleMap.value).length)
const years = computed(() => yearsOf(all.value).reverse())

const scoped = computed(() => filterByYear(all.value, f.year).filter((r) => matchesSearch(r, f.search)))
const rows = computed(() => sortWeeks(scoped.value, f.sort, f.dir))
const chronological = computed(() => sortWeeks(scoped.value, 'period', 'asc'))
const filtersActive = computed(() => !!f.year || !!f.search.trim())
const summary = computed(() => (filtersActive.value
  ? `${rows.value.length} из ${all.value.length} ${plural(all.value.length, ['недели', 'недель', 'недель'])}`
  : `${all.value.length} ${plural(all.value.length, ['неделя', 'недели', 'недель'])}`))
function resetFilters() {
  f.year = 0
  f.search = ''
}

// ---------- шапка ----------
const lastImport = computed(() => (imports.data.value || []).find((i) => i.dataset === 'tp_weekly'))
const description = computed(() => {
  const i = lastImport.value
  if (!i) return 'Нагрузка, трудозатраты и поток заявок техподдержки по неделям'
  return `Последняя загрузка: «${i.filename}», ${i.username}, ${formatDateTime(i.created_at)}`
})
const periodText = computed(() => {
  const list = chronological.value
  if (!list.length) return ''
  return list.length === 1 ? list[0].period : `${list[0].period} — ${list[list.length - 1].period}`
})

// ---------- показатели выборки ----------
const latest = computed(() => chronological.value.at(-1) || null)
const previous = computed(() => chronological.value.at(-2) || null)
const received = computed(() => sumBy(scoped.value, 'new_received'))
const solved = computed(() => sumBy(scoped.value, 'total_solved_week'))
const ratio = computed(() => (received.value ? Math.round((solved.value / received.value) * 100) / 100 : null))
const inWork = computed(() => latest.value?.total_in_work ?? null)
const inWorkDelta = computed(() => (inWork.value !== null && previous.value?.total_in_work !== null && previous.value?.total_in_work !== undefined
  ? inWork.value - previous.value.total_in_work : null))
const lightOf = (key, value) => (ruleMap.value[key] ? evaluate(value, ruleMap.value[key]) : '')

// ---------- таблица ----------
function sortBy(key) {
  if (f.sort === key) f.dir = f.dir === 'asc' ? 'desc' : 'asc'
  else {
    f.sort = key
    f.dir = 'desc'
  }
}
function toggleGroup(key) {
  const set = new Set(f.groups)
  set.has(key) ? set.delete(key) : set.add(key)
  f.groups = groups.value.map((g) => g.key).filter((k) => set.has(k))
}
const allShown = computed(() => groups.value.length > 0 && visibleGroups.value.length === groups.value.length)
const defaultShown = computed(() => f.groups.join(',') === DEFAULT_GROUPS.join(','))
function showAll() {
  f.groups = groups.value.map((g) => g.key)
}
function showDefault() {
  f.groups = [...DEFAULT_GROUPS]
}
function cellLight(column, value) {
  const rule = ruleMap.value[column.key]
  if (!rule || value === null || value === undefined) return ''
  return evaluate(value, rule)
}
function ruleText(rule, unit) {
  const u = unit ? ` ${unit}` : ''
  const sign = rule.direction === 'lower_is_better' ? '≤' : '≥'
  return `Светофор: норма ${sign} ${formatNumber(rule.green_threshold)}${u}, внимание ${sign} ${formatNumber(rule.yellow_threshold)}${u}`
}

// ---------- редактирование ----------
const editing = ref(null)
const importOpen = ref(false)
const newDefaults = computed(() => {
  const last = sortWeeks(all.value, 'period', 'desc')[0]
  return last ? nextIsoWeek(last.year, last.week) : isoWeekOf(new Date())
})
function openRow(row) {
  if (canEdit.value) editing.value = { row }
}
function onSaved() {
  editing.value = null
  reports.reload()
}
async function remove(row) {
  const ok = await confirm({
    title: `Удалить неделю ${row.period}?`,
    message: `${weekRangeText(row.year, row.week)}. Все показатели недели будут удалены; действие попадёт в журнал изменений.`,
    confirmText: 'Удалить',
    danger: true,
  })
  if (!ok) return
  await tpApi.deleteReport(row.id)
  toastOk(`Неделя ${row.period} удалена`)
  editing.value = null
  reports.reload()
}
function onImported() {
  reports.reload()
  imports.reload()
}
</script>

<template>
  <div class="page">
    <PageHeader title="Недельный отчёт" :description="description" :updatedAt="app.service('tech')?.data_updated_at">
      <button class="btn" type="button" title="Все недели в формате исходного отчёта" @click="tpApi.exportXlsx()"><AppIcon name="sheet" :size="15" />Excel</button>
      <button class="btn" type="button" title="Все недели, разделитель — точка с запятой" @click="tpApi.exportCsv()"><AppIcon name="file" :size="15" />CSV</button>
      <PdfButton report="tp/dashboard" :params="{ year: f.year || undefined }" />
      <button v-if="canManage" class="btn" type="button" @click="importOpen = true"><AppIcon name="upload" :size="15" />Загрузить файл</button>
      <button v-if="canEdit" class="btn btn-primary" type="button" @click="editing = { row: null }"><AppIcon name="plus" :size="15" />Добавить неделю</button>
    </PageHeader>

    <EmptyState v-if="reports.data.value && !all.length" icon="table" title="Отчёт пока пуст"
                :text="canManage ? 'Загрузите файл «Итоговый отчёт ТП по неделям» или добавьте первую неделю вручную.' : 'Недели появятся, когда ответственный сотрудник загрузит отчёт.'">
      <button v-if="canManage" class="btn" type="button" @click="importOpen = true"><AppIcon name="upload" :size="15" />Загрузить файл</button>
      <button v-if="canEdit" class="btn btn-primary" type="button" @click="editing = { row: null }"><AppIcon name="plus" :size="15" />Добавить неделю</button>
    </EmptyState>

    <template v-else>
      <FilterBar :summary="summary" :resettable="filtersActive" @reset="resetFilters">
        <label class="field"><span>Год</span>
          <select v-model.number="f.year" class="select">
            <option :value="0">Все годы</option>
            <option v-for="y in years" :key="y" :value="y">{{ y }}</option>
          </select>
        </label>
        <label class="search"><AppIcon name="search" :size="14" /><input v-model="f.search" type="search" placeholder="Неделя или примечание" aria-label="Поиск по периоду" /></label>
      </FilterBar>

      <div class="kpis">
        <KpiCard label="Недель в выборке" :value="scoped.length" :hint="periodText" :loading="reports.loading.value && !reports.data.value" />
        <KpiCard label="Принято заявок" :value="received" unit="шт." hint="Сумма «Принято новых заявок» по неделям выборки" :loading="reports.loading.value && !reports.data.value" />
        <KpiCard label="Решено заявок" :value="solved" unit="шт." hint="Сумма «Решено за неделю» по неделям выборки" :loading="reports.loading.value && !reports.data.value" />
        <KpiCard label="Решено к принятому" :value="ratio" :light="lightOf('ratio_solved_received', ratio)" hint="Решено заявок / принято заявок за выборку; больше 1 — очередь сокращается"
                 :loading="reports.loading.value && !reports.data.value" />
        <KpiCard label="В работе на конец периода" :value="inWork" :hint="latest ? `Итого в работе заявок, неделя ${latest.period}` : ''" unit="шт." :light="lightOf('total_in_work', inWork)"
                 :delta="inWorkDelta" deltaLabel="к прошлой неделе" :direction="ruleMap.total_in_work?.direction || 'lower_is_better'" :loading="reports.loading.value && !reports.data.value" />
      </div>

      <section class="card">
        <header class="toolbar">
          <div class="toolbar-top">
            <h3>Показатели в таблице</h3>
            <span class="muted toolbar-hint">{{ visibleGroups.reduce((n, g) => n + g.columns.length, 0) }} из {{ (columns.data.value || []).length }}</span>
            <span class="spacer" />
            <button class="btn btn-ghost btn-sm" type="button" :disabled="allShown" @click="showAll">Показать все</button>
            <button class="btn btn-ghost btn-sm" type="button" :disabled="defaultShown" @click="showDefault">По умолчанию</button>
          </div>
          <div class="row-wrap groups">
            <button v-for="g in groups" :key="g.key" type="button" class="chip" :class="{ active: f.groups.includes(g.key) }" :aria-pressed="f.groups.includes(g.key)" @click="toggleGroup(g.key)">
              {{ g.label }}<span class="chip-count num">{{ g.columns.length }}</span>
            </button>
          </div>
        </header>

        <div class="card-body body">
          <div v-if="reports.loading.value && !reports.data.value" class="skeleton" style="height: 360px" />
          <template v-else>
            <div class="table-wrap reg-wrap scroll-thin">
              <table class="table table-compact reg">
                <thead>
                  <tr class="head-groups">
                    <th rowspan="2" class="sticky-col corner sortable" @click="sortBy('period')">
                      Неделя<AppIcon v-if="f.sort === 'period'" :name="f.dir === 'asc' ? 'arrow-up' : 'arrow-down'" :size="11" class="sort-icon" />
                    </th>
                    <th v-for="g in visibleGroups" :key="g.key" :colspan="g.columns.length" class="group-th"><span class="group-label">{{ g.label }}</span></th>
                    <th v-if="canEdit" rowspan="2" class="actions-col" aria-label="Действия" />
                  </tr>
                  <tr class="head-cols">
                    <template v-for="g in visibleGroups" :key="g.key">
                      <th v-for="(c, i) in g.columns" :key="c.key" class="num sortable col-th" :class="{ 'group-start': i === 0 }" :title="c.label" @click="sortBy(c.key)">
                        <span class="th-inner">
                          <span v-if="ruleMap[c.key]" class="rule-icon" :title="ruleText(ruleMap[c.key], c.unit)"><AppIcon name="traffic" :size="12" /></span>
                          <span class="th-text">{{ shortLabel(c.label, g.label) }}<span v-if="c.unit" class="th-unit">, {{ c.unit }}</span></span>
                          <AppIcon v-if="f.sort === c.key" :name="f.dir === 'asc' ? 'arrow-up' : 'arrow-down'" :size="11" class="sort-icon" />
                        </span>
                      </th>
                    </template>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="r in rows" :key="r.id" :class="{ clickable: canEdit }" @click="openRow(r)">
                    <td class="sticky-col">
                      <div class="period">
                        <span class="period-code num">{{ r.period }}</span>
                        <span v-if="r.note" class="note-icon" :title="r.note"><AppIcon name="note" :size="13" /></span>
                      </div>
                      <div class="period-dates num">{{ weekRangeText(r.year, r.week, { short: true }) }}</div>
                    </td>
                    <template v-for="g in visibleGroups" :key="g.key">
                      <td v-for="(c, i) in g.columns" :key="c.key" class="num" :class="{ 'group-start': i === 0, empty: r[c.key] === null }">
                        <span class="cell">
                          <LightBadge v-if="cellLight(c, r[c.key])" :light="cellLight(c, r[c.key])" dot />
                          {{ formatMetric(r[c.key], c) }}
                        </span>
                      </td>
                    </template>
                    <td v-if="canEdit" class="actions-col" @click.stop>
                      <button class="btn btn-icon btn-sm btn-ghost" type="button" :title="`Удалить неделю ${r.period}`" @click="remove(r)"><AppIcon name="trash" :size="14" /></button>
                    </td>
                  </tr>
                </tbody>
              </table>
              <EmptyState v-if="!rows.length" compact icon="search" title="Нет недель по фильтру" text="Измените год или строку поиска.">
                <button class="btn btn-sm" type="button" @click="resetFilters">Сбросить фильтры</button>
              </EmptyState>
            </div>
            <p v-if="!visibleGroups.length" class="hint-line muted"><AppIcon name="info" :size="14" />Выберите группы показателей, чтобы увидеть значения</p>
          </template>
        </div>

        <footer class="legend">
          <template v-if="ruleCount">
            <span class="muted">Светофор по {{ ruleCount }} {{ plural(ruleCount, ['показателю', 'показателям', 'показателям']) }}:</span>
            <span v-for="l in ['green', 'yellow', 'red']" :key="l" class="legend-item"><LightBadge :light="l" dot />{{ LIGHT_LABELS[l] }}</span>
          </template>
          <span v-else class="muted">Пороги светофора для показателей отчёта не заданы</span>
          <router-link v-if="canManage" to="/settings/traffic-light/tech" class="link">Настроить светофор</router-link>
          <span class="spacer" />
          <span v-if="canEdit" class="muted">Нажмите на строку, чтобы изменить неделю</span>
        </footer>
      </section>
    </template>

    <TpRegWeekDialog v-if="editing" :row="editing.row" :groups="groups" :defaults="newDefaults" :canDelete="canEdit"
                     @close="editing = null" @saved="onSaved" @delete="remove" />

    <ImportDialog v-if="importOpen" title="Загрузка недельного отчёта" :endpoint="tpApi.importEndpoint" accept=".xlsx,.csv"
                  description="Файл «Итоговый отчёт ТП по неделям»: лист «Лист1», четыре строки шапки, данные с пятой строки; в столбцах A и B — год и номер недели. CSV — с заголовками «Год», «Неделя» и названиями показателей."
                  mergeHint="Новые недели добавятся, совпадающие по году и номеру недели обновятся"
                  replaceHint="Отчёт будет заменён содержимым файла целиком"
                  @close="importOpen = false" @done="onImported" />
  </div>
</template>

<style scoped>
.search { display: flex; align-items: center; gap: 8px; height: 32px; padding: 0 10px; border: 1px solid var(--border-strong); border-radius: var(--radius); color: var(--muted); min-width: 280px; background: var(--surface); }
.search input { border: 0; outline: 0; background: transparent; width: 100%; color: var(--text); font-size: var(--fs-sm); }
.search:focus-within { border-color: var(--chart-2); box-shadow: 0 0 0 3px var(--focus); }

.kpis { display: grid; gap: var(--sp-4); grid-template-columns: repeat(5, minmax(0, 1fr)); }
@media (max-width: 1100px) { .kpis { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
@media (max-width: 640px) { .kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
.toolbar { display: flex; flex-direction: column; gap: var(--sp-3); padding: var(--sp-4) var(--sp-5); border-bottom: 1px solid var(--border); }
.toolbar-top { display: flex; align-items: center; gap: var(--sp-2); }
.toolbar-top h3 { font-size: var(--fs-md); font-weight: 620; }
.toolbar-hint { font-size: var(--fs-sm); }
.groups { gap: 6px; }
.chip-count { margin-left: 2px; font-size: var(--fs-xs); opacity: .6; }
.body { padding: 0; }

.reg-wrap { max-height: min(72vh, 820px); border-radius: 0; }
.reg { font-size: var(--fs-sm); }
.reg th { white-space: normal; vertical-align: bottom; }
.reg .head-groups th { top: 0; height: 34px; line-height: 18px; vertical-align: middle; }
.reg .head-cols th { top: 34px; }
.group-label { position: sticky; left: 140px; }
.reg .group-th { text-align: left; color: var(--text-2); letter-spacing: .05em; border-left: 1px solid var(--border); }
.reg .col-th { min-width: 92px; max-width: 150px; text-transform: none; letter-spacing: 0; font-size: var(--fs-xs); font-weight: 560; color: var(--text-2); line-height: 1.3; }
.th-inner { display: inline-flex; align-items: flex-end; gap: 4px; justify-content: flex-end; }
.th-text { text-align: right; }
.th-unit { color: var(--muted); font-weight: 450; white-space: nowrap; }
.rule-icon { color: var(--muted); margin-bottom: 1px; }
.sort-icon { display: inline-block; margin-left: 2px; vertical-align: -1px; flex: 0 0 auto; }
.group-start { border-left: 1px solid var(--border); }

.sticky-col { position: sticky; left: 0; z-index: 2; background: var(--surface); box-shadow: inset -1px 0 0 var(--border); min-width: 128px; }
.reg thead th.sticky-col { z-index: 4; background: var(--surface-2); vertical-align: bottom; }
.reg tbody tr:hover td.sticky-col { background: var(--row-hover); }
.period { display: flex; align-items: center; gap: 6px; line-height: 1.3; }
.period-code { font-weight: 620; color: var(--text); white-space: nowrap; }
.period-dates { font-size: var(--fs-xs); line-height: 1.3; color: var(--muted); }
.note-icon { color: var(--muted); }

.cell { display: inline-flex; align-items: center; gap: 6px; white-space: nowrap; }
td.empty { color: var(--faint); }
.actions-col { position: sticky; right: 0; z-index: 2; width: 44px; text-align: right; background: var(--surface); box-shadow: inset 1px 0 0 var(--border); }
.reg thead th.actions-col { z-index: 4; background: var(--surface-2); }
.reg tbody tr:hover td.actions-col { background: var(--row-hover); }
.actions-col .btn { opacity: 0; transition: opacity var(--t-fast); }
tr:hover .actions-col .btn, .actions-col .btn:focus-visible { opacity: 1; }

.hint-line { display: flex; align-items: center; gap: 6px; padding: 10px 16px; font-size: var(--fs-sm); }
.legend { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 14px; padding: 10px var(--sp-5); border-top: 1px solid var(--border); font-size: var(--fs-xs); }
.legend-item { display: inline-flex; align-items: center; gap: 6px; color: var(--text-2); }
@media (hover: none) { .actions-col .btn { opacity: 1; } }
</style>
