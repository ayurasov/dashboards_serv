<script setup>
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import OrgIcon from '@/components/org/OrgIcon.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import PdfButton from '@/components/ui/PdfButton.vue'
import ReportHero from '@/components/reports/ReportHero.vue'
import ReportList from '@/components/reports/ReportList.vue'
import ReportMatrix from '@/components/reports/ReportMatrix.vue'
import ReportStatusChart from '@/components/reports/ReportStatusChart.vue'
import ReportUnitPanel from '@/components/reports/ReportUnitPanel.vue'
import { reportsApi } from '@/api/reports'
import { useAsync } from '@/composables/useAsync'
import { useQueryState } from '@/composables/useQueryState'
import {
  INDICATOR_FORMS, REPORT_VIEWS, STATUS_FILTERS, accessLine, ancestorIds, buildTree, count, expandToDepth, filteredCount,
  hasViolation, isFiltered, matchesFilter, matrixColumns, matrixRows, ratedIndicators, resolveReportView,
} from '@/domain/reports'
import { monthLabel } from '@/utils/format'

/**
 * Сквозной отчёт (ADR-0010): статус области пользователя и из чего он складывается — сводка вершины,
 * матрица «подразделения × показатели», оргсхема статусов, список (для телефона), панель подразделения
 * с трендами. Вид, период, вершина и выбранное подразделение — в адресе. Состав и глубина видимого —
 * из доступа пользователя (ADR-0009): сервер отдаёт только доступное.
 */
const { state: q } = useQueryState({ view: '', period: '', root: '', unit: '', status: '', violations: false })
const asId = (v) => (/^\d+$/.test(String(v || '')) ? Number(v) : null)
const rootId = computed(() => asId(q.root))
const selectedId = computed(() => asId(q.unit))

// ---------------------------------------------------------------- ширина экрана
const narrowQuery = typeof matchMedia === 'function' ? matchMedia('(max-width: 640px)') : null
const narrow = ref(!!narrowQuery?.matches)
const onNarrow = (e) => { narrow.value = e.matches }
narrowQuery?.addEventListener?.('change', onNarrow)
onBeforeUnmount(() => narrowQuery?.removeEventListener?.('change', onNarrow))
const view = computed(() => resolveReportView(q.view, narrow.value))

// ---------------------------------------------------------------- данные
const periods = useAsync(() => reportsApi.periods())
const { data, loading, error, reload } = useAsync(
  () => reportsApi.scorecard({ period: q.period || undefined, root: rootId.value || undefined }), { immediate: false },
)
watch(() => [q.period, q.root], () => reload(), { immediate: true })

const units = computed(() => data.value?.units || [])
const indicators = computed(() => data.value?.indicators || [])
const me = computed(() => data.value?.me || {})
const access = computed(() => accessLine(data.value?.access))
const listed = computed(() => new Set(units.value.map((u) => u.id)))
const canOpen = (id) => listed.value.has(id)
const hasValues = computed(() => units.value.some((u) => Object.keys(u.cells || {}).length))
const rated = computed(() => ratedIndicators(units.value))
const latestLabel = computed(() => periods.data.value?.periods?.find((p) => p.period === periods.data.value.latest)?.label || '')

const periodModel = computed({
  get: () => q.period || data.value?.period || '',
  set: (value) => { q.period = value },
})
const periodOptions = computed(() => {
  const list = periods.data.value?.periods || []
  const current = periodModel.value
  return current && !list.some((p) => p.period === current) ? [{ period: current, label: monthLabel(current) }, ...list] : list
})
const description = computed(() => {
  if (!data.value) return 'Статус компании сверху вниз: подразделения, показатели, причины'
  return hasValues.value ? `${data.value.period_label} · стрелки в ячейках — изменение к прошлому месяцу` : data.value.period_label
})

// ---------------------------------------------------------------- дерево и раскрытие
const forest = computed(() => buildTree(units.value))
const expanded = reactive(new Set())
function syncSet(target, next) {
  for (const id of [...target]) if (!next.has(id)) target.delete(id)
  for (const id of next) target.add(id)
}
let shape = ''
watch(forest, (value) => {
  const key = units.value.map((u) => u.id).join(',')
  if (key === shape) return
  shape = key
  syncSet(expanded, expandToDepth(value, 2))
  if (selectedId.value) reveal(selectedId.value)
})
function toggle(id) { expanded.has(id) ? expanded.delete(id) : expanded.add(id) }
function expandAll() { syncSet(expanded, expandToDepth(forest.value, null)) }
function collapse() { syncSet(expanded, expandToDepth(forest.value, 1)) }
function reveal(id) { for (const a of ancestorIds(forest.value, id)) expanded.add(a) }
const allOpen = computed(() => expandToDepth(forest.value, null))

const filter = computed(() => ({ status: q.status, violations: q.violations }))
const filtered = computed(() => isFiltered(filter.value))
const rows = computed(() => matrixRows(forest.value, expanded, filter.value))
const listRows = computed(() => matrixRows(forest.value, allOpen.value, filter.value))
const statusCounts = computed(() => {
  const out = { '': units.value.length }
  for (const s of STATUS_FILTERS) if (s.value) out[s.value] = filteredCount(units.value, { status: s.value })
  return out
})
const violationCount = computed(() => units.value.filter(hasViolation).length)
const dimmed = computed(() => new Set(filtered.value ? units.value.filter((u) => !matchesFilter(u, filter.value)).map((u) => u.id) : []))
const shown = computed(() => filteredCount(units.value, filter.value))
function resetFilters() {
  q.status = ''
  q.violations = false
}

const showEmpty = ref(false)
const cols = computed(() => matrixColumns(indicators.value, units.value, { all: showEmpty.value }))
const pathSet = computed(() => new Set(selectedId.value ? [...ancestorIds(forest.value, selectedId.value), selectedId.value] : []))

// ---------------------------------------------------------------- выбор и вершина
const focusIndicator = ref('')
const chart = ref(null)
function select(id, indicator = '') {
  focusIndicator.value = indicator
  q.unit = id ? String(id) : ''
  if (id && listed.value.has(id)) {
    reveal(id)
    if (view.value === 'chart') nextTick(() => chart.value?.focus(id))
  }
}
function setRoot(id) {
  q.root = id ? String(id) : ''
  q.status = ''
}
const rootUnit = computed(() => (rootId.value ? units.value.find((u) => u.id === rootId.value) : null))
function setView(value) { q.view = value }
</script>

<template>
  <div class="page reports">
    <PageHeader title="Сквозной отчёт" :description="description">
      <label class="period" :class="{ busy: loading && data }" title="Период отчёта">
        <AppIcon name="calendar" :size="15" />
        <select v-model="periodModel" class="select" aria-label="Период" data-testid="report-period" :disabled="!periodOptions.length">
          <option v-for="p in periodOptions" :key="p.period" :value="p.period">{{ p.label }}</option>
        </select>
      </label>
      <router-link v-if="me.can_enter" :to="{ path: '/reports/entry', query: data ? { period: data.period } : {} }" class="btn" data-testid="report-entry-link">
        <AppIcon name="edit" :size="15" />Ввод показателей
      </router-link>
      <PdfButton v-if="data && me.can_export" report="reports/scorecard" :params="{ period: data.period, root: rootId || undefined }" />
    </PageHeader>

    <div v-if="data" class="access-line" data-testid="report-access">
      <span class="al-text"><AppIcon name="shield" :size="14" />{{ access.text }}</span>
      <span v-if="access.hidden" class="al-hidden" data-testid="report-hidden"><AppIcon name="eye-off" :size="14" />{{ access.hidden }}</span>
      <router-link to="/profile#my-access" class="al-link">Мой доступ</router-link>
    </div>

    <template v-if="loading && !data">
      <div class="skeleton" style="height: 236px; border-radius: var(--radius-lg)" />
      <div class="skeleton" style="height: 420px; border-radius: var(--radius-lg)" />
    </template>

    <EmptyState v-else-if="error && !data && error.code === 'unit_out_of_scope'" class="card" icon="lock" title="Ветка недоступна" :text="error.message">
      <button class="btn btn-primary btn-sm" type="button" @click="setRoot(null)">Вся область</button>
    </EmptyState>
    <EmptyState v-else-if="error && !data" class="card" icon="alert" title="Не удалось загрузить отчёт" :text="error.message">
      <button class="btn btn-sm" type="button" @click="reload()"><AppIcon name="refresh" :size="14" />Повторить</button>
    </EmptyState>

    <EmptyState v-else-if="data && !units.length" class="card" icon="org" title="Область отчёта пуста" data-testid="report-empty"
                :text="`Ваша область — «${data.access.scope_label.toLowerCase()}», но за вами не закреплено подразделение структуры. Попросите администратора указать ваше подразделение или дополнительные подразделения.`">
      <router-link to="/profile#my-access" class="btn btn-sm">Мой доступ</router-link>
    </EmptyState>
    <EmptyState v-else-if="data && !indicators.length" class="card" icon="layers" title="Нет доступных показателей" data-testid="report-empty"
                :text="`В каталоге пока нет показателей тех классов данных, что вам доступны. ${access.hidden ? `${access.hidden}. ` : ''}Статусы появятся, когда такие показатели добавят.`" />
    <EmptyState v-else-if="data && !hasValues" class="card" icon="calendar" :title="`Нет данных за ${data.period_label.toLowerCase()}`" data-testid="report-empty"
                text="За этот месяц у доступных вам показателей нет ни одного значения. Выберите другой период.">
      <button v-if="periods.data.value?.latest && periods.data.value.latest !== data.period" class="btn btn-primary btn-sm" type="button" @click="q.period = periods.data.value.latest">
        Показать {{ latestLabel.toLowerCase() }}
      </button>
    </EmptyState>

    <template v-else-if="data">
      <div :class="{ refreshing: loading }" class="report-body">
        <ReportHero :data="data" :rated="rated" :hidden-note="access.hidden" :can-enter="!!me.can_enter" :can-open="canOpen" @select="select" />

        <div class="toolbar card" role="toolbar" aria-label="Вид и фильтры отчёта">
          <div class="views" role="tablist" aria-label="Вид отчёта">
            <button v-for="v in REPORT_VIEWS" :key="v.value" type="button" role="tab" class="view-tab" :class="{ active: view === v.value }"
                    :aria-selected="view === v.value" :title="v.hint" :data-testid="`report-view-${v.value}`" @click="setView(v.value)">
              <AppIcon :name="v.icon" :size="15" /><span>{{ narrow && v.value === 'chart' ? 'Схема' : v.label }}</span>
            </button>
          </div>
          <div v-if="units.length > 1" class="filters" role="group" aria-label="Фильтр по статусу">
            <button v-for="s in STATUS_FILTERS" :key="s.value" type="button" class="chip f-chip" :class="[{ active: q.status === s.value }, s.value ? `f-${s.value}` : '']"
                    :aria-pressed="q.status === s.value" :disabled="s.value && !statusCounts[s.value]" @click="q.status = s.value">
              <i v-if="s.value" aria-hidden="true" />{{ s.label }}<b class="num">{{ statusCounts[s.value] }}</b>
            </button>
            <button type="button" class="chip f-chip f-miss" :class="{ active: q.violations }" :aria-pressed="q.violations" :disabled="!violationCount && !q.violations"
                    title="Подразделения с незаполненными обязательными показателями" data-testid="report-violations" @click="q.violations = !q.violations">
              <AppIcon name="alert" :size="13" />Только с нарушениями<b class="num">{{ violationCount }}</b>
            </button>
          </div>
          <span class="spacer" />
          <span v-if="filtered" class="shown">Показано {{ shown }} из {{ units.length }} <button type="button" class="link-btn" @click="resetFilters">Сбросить</button></span>
          <template v-if="view === 'matrix' && !filtered && forest.length">
            <div class="tree-tools" role="group" aria-label="Уровни">
              <button type="button" class="icon-tool" title="Развернуть все уровни" aria-label="Развернуть всё" @click="expandAll"><OrgIcon name="expand-all" :size="16" /></button>
              <button type="button" class="icon-tool" title="Свернуть до вершин и уровня под ними" aria-label="Свернуть" @click="collapse"><OrgIcon name="collapse-all" :size="16" /></button>
            </div>
          </template>
          <span v-if="rootUnit" class="root-chip" data-testid="report-root">
            <AppIcon name="layers" :size="13" />Ветка «{{ rootUnit.name }}»
            <button type="button" aria-label="Показать всю область" title="Вся область" @click="setRoot(null)"><AppIcon name="x" :size="13" /></button>
          </span>
        </div>

        <EmptyState v-if="filtered && !rows.length && view !== 'chart'" class="card" compact icon="filter" title="Нет подразделений по фильтру" text="Измените фильтр по статусу или снимите «Только с нарушениями».">
          <button class="btn btn-sm" type="button" @click="resetFilters">Сбросить фильтры</button>
        </EmptyState>

        <section v-else-if="view === 'matrix'" class="card matrix-card">
          <ReportMatrix :rows="rows" :columns="cols.columns" :selected-id="selectedId" :filtered="filtered" @select="select" @toggle="toggle" />
          <footer class="legend">
            <span class="lg"><i class="sw green" />Норма</span>
            <span class="lg"><i class="sw yellow" />Внимание</span>
            <span class="lg"><i class="sw red" />Критично</span>
            <span class="lg"><i class="sw missing" />Нет данных — не заполнено, критичное нарушение</span>
            <span class="lg"><AppIcon name="arrow-up" :size="11" :stroke="2.6" class="delta-good" /><AppIcon name="arrow-down" :size="11" :stroke="2.6" class="delta-bad" />к прошлому месяцу: зелёная — к лучшему</span>
            <span class="lg"><AppIcon name="lock" :size="12" />детализация недоступна</span>
            <span class="lg"><AppIcon name="eye" :size="12" />под контролем</span>
            <span class="spacer" />
            <button v-if="cols.empty.length || showEmpty" type="button" class="link-btn" :title="cols.empty.map((i) => i.name).join(', ')" @click="showEmpty = !showEmpty">
              {{ showEmpty ? 'Скрыть показатели без значений' : `Ещё ${count(cols.empty.length, INDICATOR_FORMS)} без значений за период` }}
            </button>
          </footer>
        </section>

        <ReportStatusChart v-else-if="view === 'chart'" ref="chart" :forest="forest" :expanded="expanded" :selected-id="selectedId" :path="pathSet" :dimmed="dimmed"
                           @select="select" @toggle="toggle" @expand-all="expandAll" @collapse="collapse" />

        <ReportList v-else :rows="listRows" :selected-id="selectedId" @select="select" />
      </div>
    </template>

    <ReportUnitPanel v-if="selectedId && data" :unit-id="selectedId" :period="data.period" :root-id="rootId" :can-open="canOpen" :hidden-note="access.hidden"
                     :focus-indicator="focusIndicator" @close="select(null)" @select="(id) => select(id)" @root="setRoot" @changed="reload()" />
  </div>
</template>

<style scoped>
.reports { gap: var(--sp-4); }
.period { position: relative; display: inline-flex; align-items: center; }
.period :deep(svg) { position: absolute; left: 11px; color: var(--muted); pointer-events: none; }
.period .select { width: auto; min-width: 170px; padding-left: 33px; font-weight: 560; }
.period.busy .select { opacity: .7; }

.access-line { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 16px; margin-top: calc(var(--sp-2) * -1); font-size: var(--fs-sm); color: var(--text-2); }
.access-line > span { display: inline-flex; align-items: center; gap: 7px; }
.access-line :deep(svg) { color: var(--muted); flex: 0 0 auto; }
.al-hidden { padding: 2px 10px 2px 8px; border-radius: var(--radius-pill); background: var(--surface-3); color: var(--text-2); font-size: var(--fs-xs); font-weight: 560; }
.al-link { font-size: var(--fs-xs); color: var(--accent); }
.al-link:hover { text-decoration: underline; }

.report-body { display: flex; flex-direction: column; gap: var(--sp-4); transition: opacity var(--t); }
.report-body.refreshing { opacity: .62; }

.toolbar { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 10px; padding: 10px 12px; }
.views { display: inline-flex; gap: 2px; padding: 3px; border-radius: 11px; background: var(--surface-3); border: 1px solid var(--border); }
.view-tab {
  display: inline-flex; align-items: center; gap: 7px; height: 30px; padding: 0 12px; border: 0; border-radius: 8px;
  background: transparent; color: var(--text-2); font-size: var(--fs-sm); font-weight: 560; cursor: pointer; white-space: nowrap;
  transition: background var(--t-fast), color var(--t-fast), box-shadow var(--t-fast);
}
.view-tab:hover { color: var(--text); }
.view-tab.active { background: var(--bg-elevated); color: var(--text); box-shadow: var(--shadow-sm); font-weight: 620; }
.filters { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; padding-left: 10px; border-left: 1px solid var(--border); }
.f-chip { --c: var(--text-2); height: 30px; gap: 6px; }
.f-chip i { width: 7px; height: 7px; border-radius: 50%; background: var(--c); }
.f-chip b { font-weight: 680; color: var(--muted); }
.f-chip.active b { color: inherit; opacity: .8; }
.f-chip:disabled { opacity: .45; cursor: not-allowed; }
.f-red { --c: var(--light-red); }
.f-yellow { --c: var(--light-yellow); }
.f-green { --c: var(--light-green); }
.f-miss :deep(svg) { color: var(--light-red); }
.f-miss.active { background: var(--light-red); border-color: var(--light-red); color: #fff; }
.f-miss.active :deep(svg) { color: #fff; }
.tree-tools { display: inline-flex; gap: 1px; }
.icon-tool { width: 32px; height: 32px; display: grid; place-items: center; border: 0; border-radius: 8px; background: transparent; color: var(--text-2); cursor: pointer; }
.icon-tool:hover { background: var(--surface-3); color: var(--text); }
.shown { font-size: var(--fs-sm); color: var(--muted); white-space: nowrap; }
.link-btn { padding: 0; border: 0; background: transparent; color: var(--accent); font-size: var(--fs-sm); cursor: pointer; }
.link-btn:hover { text-decoration: underline; }
.root-chip { display: inline-flex; align-items: center; gap: 6px; height: 30px; padding: 0 4px 0 10px; border-radius: var(--radius-pill); background: color-mix(in srgb, var(--accent) 12%, transparent); color: var(--accent); font-size: var(--fs-sm); font-weight: 600; }
.root-chip button { width: 24px; height: 24px; display: grid; place-items: center; border: 0; border-radius: 50%; background: transparent; color: inherit; cursor: pointer; }
.root-chip button:hover { background: color-mix(in srgb, var(--accent) 18%, transparent); }

.matrix-card { overflow: hidden; }
.legend { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 16px; padding: 10px 16px; border-top: 1px solid var(--border); background: var(--surface-2); font-size: var(--fs-xs); color: var(--muted); }
.lg { display: inline-flex; align-items: center; gap: 5px; }
.lg :deep(svg) { color: var(--text-2); }
.lg :deep(svg.delta-good) { color: var(--light-green); }
.lg :deep(svg.delta-bad) { color: var(--light-red); }
.sw { width: 14px; height: 10px; border-radius: 3px; }
.sw.green { background: color-mix(in srgb, var(--light-green) 35%, var(--surface)); box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--light-green) 50%, transparent); }
.sw.yellow { background: color-mix(in srgb, var(--light-yellow) 40%, var(--surface)); box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--light-yellow) 55%, transparent); }
.sw.red { background: color-mix(in srgb, var(--light-red) 35%, var(--surface)); box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--light-red) 50%, transparent); }
.sw.missing { background: repeating-linear-gradient(135deg, color-mix(in srgb, var(--light-red) 30%, var(--surface)) 0 3px, var(--surface) 3px 6px); box-shadow: inset 0 0 0 1px var(--light-red); }
.legend .link-btn { font-size: var(--fs-xs); }

@media (max-width: 1100px) {
  .filters { border-left: 0; padding-left: 0; }
}
@media (max-width: 640px) {
  .reports :deep(.page-actions) { width: 100%; }
  .period { flex: 1; }
  .period .select { width: 100%; }
  .toolbar { padding: 8px; }
  .views { width: 100%; }
  .view-tab { flex: 1; justify-content: center; padding: 0 6px; }
  .filters { width: 100%; }
  .f-chip { height: 28px; padding: 0 9px; }
  .lbl { display: none; }
  .legend { gap: 4px 12px; }
}
</style>
