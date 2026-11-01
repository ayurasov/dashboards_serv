<script setup>
import { computed, nextTick, reactive, ref, watch } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import OrgChart from '@/components/org/OrgChart.vue'
import OrgGroupCard from '@/components/org/OrgGroupCard.vue'
import OrgIcon from '@/components/org/OrgIcon.vue'
import OrgPersonNode from '@/components/org/OrgPersonNode.vue'
import OrgPersonPanel from '@/components/org/OrgPersonPanel.vue'
import OrgSearch from '@/components/org/OrgSearch.vue'
import OrgSidePanel from '@/components/org/OrgSidePanel.vue'
import OrgTable from '@/components/org/OrgTable.vue'
import OrgTreeView from '@/components/org/OrgTreeView.vue'
import OrgUnitCard from '@/components/org/OrgUnitCard.vue'
import OrgUnitPanel from '@/components/org/OrgUnitPanel.vue'
import { orgApi } from '@/api/org'
import { useAsync } from '@/composables/useAsync'
import { useQueryState } from '@/composables/useQueryState'
import { useAuthStore } from '@/stores/auth'
import {
  LEVEL_FORMS, LOOSE_ID, ORG_VIEWS, PEOPLE_FORMS, TABLE_CSV_COLUMNS, UNIT_FORMS, countText, expandedToLevel, forestDepth,
  homeOf, indexForest, kindInfo, levelOptions, nextSort, pathTo, peopleForest, resolveView, revealIn, searchOrg, sortRows,
  toCsv, treeRows, unitForest, unitTableRows, ZOOM,
} from '@/domain/org'

/**
 * Структура компании (ADR-0007): четыре вида — «Оргсхема» (подразделения карточками), «Люди»
 * (кто кому подчиняется), «Дерево» (список с сотрудниками), «Таблица» (численность, выгрузка).
 * Вид — в адресе (?view=), затем выбор пользователя, затем настройка структуры. Выбранное
 * подразделение или сотрудник — в адресе (?unit= / ?user=), путь к нему подсвечен; подробности —
 * в боковой панели (на телефоне — лист снизу). Видят все вошедшие; правят ведущие структуру.
 */
const auth = useAuthStore()
const canManage = computed(() => auth.hasCapability('org.manage'))

// ---------------------------------------------------------------- данные
const { data, loading, error, reload } = useAsync(() => orgApi.tree())
const units = computed(() => data.value?.units || [])
const people = computed(() => data.value?.people || [])
const activePeople = computed(() => people.value.filter((p) => p.is_active !== false))
const kinds = computed(() => data.value?.settings?.unit_kinds || [])
const kindMap = computed(() => new Map(kinds.value.map((k) => [k.value, kindInfo(kinds.value, k.value)])))
const kindOf = (value) => kindMap.value.get(value) || kindInfo(kinds.value, value)
const unitsById = computed(() => new Map(units.value.map((u) => [u.id, u])))
const peopleById = computed(() => new Map(people.value.map((p) => [p.id, p])))
const me = computed(() => data.value?.me || null)
const myUnitId = computed(() => me.value?.home_unit_id ?? null)

const forest = computed(() => unitForest(units.value))
const unitIndex = computed(() => indexForest(forest.value))
const team = computed(() => peopleForest(people.value))
const teamIndex = computed(() => indexForest(team.value))
const depth = computed(() => forestDepth(forest.value))

// ---------------------------------------------------------------- личные настройки вида
const PREFS_KEY = 'ds_org_prefs'
function readPrefs() {
  try { return JSON.parse(localStorage.getItem(PREFS_KEY) || '{}') || {} } catch { return {} }
}
const stored = readPrefs()
const prefs = reactive({
  view: typeof stored.view === 'string' ? stored.view : null,
  zoom: typeof stored.zoom === 'number' ? Math.min(ZOOM.max, Math.max(ZOOM.min, stored.zoom)) : 1,
  orientation: stored.orientation === 'horizontal' ? 'horizontal' : 'vertical',
  compact: !!stored.compact,
  stackLeaves: stored.stackLeaves !== false,
  levels: stored.levels === 'all' || Number(stored.levels) > 0 ? stored.levels : 3,
})
watch(prefs, (value) => {
  try { localStorage.setItem(PREFS_KEY, JSON.stringify(value)) } catch {}
}, { deep: true })

// ---------------------------------------------------------------- вид и выбор в адресе
const { state: q } = useQueryState({ view: '', unit: '', user: '' })
const view = computed(() => resolveView(q.view, prefs.view, data.value?.settings?.default_view))
const isCanvas = computed(() => view.value === 'chart' || view.value === 'people')
function setView(value) {
  prefs.view = value
  q.view = value
}

const selection = computed(() => {
  const id = (v) => (/^\d+$/.test(v) ? Number(v) : null)
  if (id(q.user) !== null) return { type: 'person', id: id(q.user) }
  if (id(q.unit) !== null) return { type: 'unit', id: id(q.unit) }
  return null
})
const selectedUnit = computed(() => (selection.value?.type === 'unit' ? unitsById.value.get(selection.value.id) || null : null))
const selectedPerson = computed(() => (selection.value?.type === 'person' ? peopleById.value.get(selection.value.id) || null : null))

/*
 * Раскрытие, путь и выбор — реактивные множества, которые меняются на месте: перерисовываются только
 * узлы, чьё «раскрыт / на пути / выбран» изменилось (на схеме «Люди» — тысячи карточек).
 */
function syncSet(target, next) {
  for (const id of [...target]) if (!next.has(id)) target.delete(id)
  for (const id of next) if (!target.has(id)) target.add(id)
}
const unitPath = reactive(new Set())
const teamPath = reactive(new Set())
const selectedKeys = reactive(new Set())
watch([selection, unitIndex, teamIndex, peopleById], () => {
  const unitId = selection.value?.type === 'unit' ? selection.value.id : selectedPerson.value ? homeOf(selectedPerson.value) : null
  syncSet(unitPath, pathTo(unitIndex.value, unitId))
  syncSet(teamPath, selection.value?.type === 'person' ? pathTo(teamIndex.value, selection.value.id) : new Set())
  syncSet(selectedKeys, new Set(selection.value ? [`${selection.value.type}:${selection.value.id}`] : []))
}, { immediate: true })

// ---------------------------------------------------------------- раскрытие
const unitExpanded = reactive(new Set())
const teamExpanded = reactive(new Set())
const treeExpanded = reactive(new Set())
const levelsValue = computed(() => (prefs.levels === 'all' ? null : Number(prefs.levels) || 3))
const levelChoices = computed(() => levelOptions(view.value === 'people' ? forestDepth(team.value) : depth.value))

function resetExpansion() {
  syncSet(unitExpanded, expandedToLevel(forest.value, levelsValue.value))
  const teamOpen = expandedToLevel(team.value, levelsValue.value)
  teamOpen.delete(LOOSE_ID)
  syncSet(teamExpanded, teamOpen)
  syncSet(treeExpanded, expandedToLevel(forest.value, levelsValue.value, { leaves: true }))
}
function setLevels(value) {
  prefs.levels = value === 'all' ? 'all' : Number(value)
  resetExpansion()
  refocus()
}
function expandAll() { setLevels('all') }
function collapseAll() { setLevels(1) }
const toggle = (set, id) => (set.has(id) ? set.delete(id) : set.add(id))
const toggleUnit = (id) => toggle(unitExpanded, id)
const toggleTeam = (id) => toggle(teamExpanded, id)
const toggleTree = (id) => toggle(treeExpanded, id)

// ---------------------------------------------------------------- переход к узлу
const canvas = ref(null)
const treeView = ref(null)
const tableView = ref(null)
const panel = ref(null)

/** Раскрыть ветки до подразделения или сотрудника во всех видах. */
function reveal(target) {
  if (!target) return
  if (target.type === 'unit') {
    syncSet(unitExpanded, revealIn(unitExpanded, unitIndex.value, target.id))
    syncSet(treeExpanded, revealIn(treeExpanded, unitIndex.value, target.id))
    return
  }
  if (teamIndex.value.has(target.id)) syncSet(teamExpanded, revealIn(teamExpanded, teamIndex.value, target.id))
  const home = homeOf(peopleById.value.get(target.id))
  if (home != null && unitIndex.value.has(home)) {
    syncSet(unitExpanded, revealIn(unitExpanded, unitIndex.value, home))
    syncSet(treeExpanded, revealIn(treeExpanded, unitIndex.value, home))
    treeExpanded.add(home)
  } else {
    treeExpanded.add('unassigned')
  }
}

/** Прокрутить текущий вид к цели (подразделение или сотрудник). */
async function focusOn(target, { flash = false, smooth = true, ifHidden = false } = {}) {
  await nextTick()
  if (!target) return
  const person = target.type === 'person' ? peopleById.value.get(target.id) : null
  const unitId = target.type === 'unit' ? target.id : homeOf(person)
  if (view.value === 'chart') {
    if (unitId != null) canvas.value?.focus(unitId, { flash, smooth, ifHidden })
  } else if (view.value === 'people') {
    const id = person ? target.id : unitsById.value.get(target.id)?.primary_head_id
    if (id != null && teamIndex.value.has(id)) canvas.value?.focus(id, { flash, smooth, ifHidden })
  } else if (view.value === 'tree') {
    treeView.value?.focus(target.type, target.id, { flash })
  } else if (unitId != null) {
    tableView.value?.focus(unitId, { flash })
  }
}

const canLocate = computed(() => (view.value === 'people' ? !!me.value && teamIndex.value.has(me.value.id) : myUnitId.value != null))
function whereAmI({ flash = true, smooth = true } = {}) {
  const target = view.value === 'people' ? { type: 'person', id: me.value?.id } : { type: 'unit', id: myUnitId.value }
  if (target.id == null) return false
  reveal(target)
  focusOn(target, { flash, smooth })
  return true
}

/** После смены вида или уровней — к выбранному, иначе к себе, иначе к началу схемы. */
function refocus() {
  if (selection.value) {
    reveal(selection.value)
    focusOn(selection.value, { smooth: false })
  } else if (!canLocate.value || !whereAmI({ flash: false, smooth: false })) {
    // Себя в структуре нет — к самому крупному корню (на схеме «Люди» корни уже по размеру команды)
    const root = view.value === 'people' ? team.value[0]
      : [...forest.value].sort((a, b) => (b.item.branch_employee_count || 0) - (a.item.branch_employee_count || 0))[0]
    nextTick(() => {
      if (root) canvas.value?.focus(root.id, { smooth: false })
      treeView.value?.scrollTop()
    })
  }
}

// ---------------------------------------------------------------- выбор
function select(type, id, { reveal: show = false, flash = false } = {}) {
  const opening = !selection.value
  q.unit = type === 'unit' ? String(id) : ''
  q.user = type === 'person' ? String(id) : ''
  const target = { type, id }
  if (show) {
    reveal(target)
    focusOn(target, { flash })
  } else if (opening && isCanvas.value) {
    // Панель сужает схему — выбранная карточка не должна уйти за край
    focusOn(target, { ifHidden: true })
  }
  nextTick(() => panel.value?.scrollTop())
}
const selectUnit = (id, options) => select('unit', id, options)
const selectPerson = (id, options) => select('person', id, options)
const fromPanel = { reveal: true, flash: true }
function clearSelection() {
  q.unit = ''
  q.user = ''
}

// Первая загрузка: раскрыть уровни и показать выбранное или своё место
let initialized = false
watch(data, (value) => {
  if (!value) return
  if (!initialized) {
    initialized = true
    resetExpansion()
    refocus()
  }
})
watch(view, () => { if (initialized) refocus() })

// ---------------------------------------------------------------- карточка сотрудника
const card = ref(null)
const cardLoading = ref(false)
let cardSeq = 0
async function loadCard(id) {
  const seq = ++cardSeq
  cardLoading.value = true
  try {
    const result = await orgApi.person(id)
    if (seq === cardSeq) card.value = result
  } catch {
    if (seq === cardSeq) card.value = null
  } finally {
    if (seq === cardSeq) cardLoading.value = false
  }
}
watch(() => selectedPerson.value?.id, (id) => {
  card.value = null
  if (id != null) loadCard(id)
}, { immediate: true })
async function onPersonSaved(next) {
  card.value = next
  await reload()
}

// Подразделения для выбора в панели (порядок дерева, с отступом)
const unitItems = computed(() => {
  const items = []
  const walk = (nodes, trail) => {
    for (const node of nodes) {
      items.push({ id: node.id, label: node.item.name, depth: node.depth, color: kindOf(node.item.kind).color, sub: trail.join(' / ') })
      walk(node.children, [...trail, node.item.name])
    }
  }
  walk(forest.value, [])
  return items
})

// ---------------------------------------------------------------- поиск
const query = ref('')
const results = computed(() => searchOrg(query.value, units.value, people.value, {
  unitsById: unitsById.value, includeInactive: canManage.value,
}))
function pick(result) {
  query.value = ''
  select(result.type, result.id, { reveal: true, flash: true })
}

// ---------------------------------------------------------------- «Дерево»
const rowsOfTree = computed(() => treeRows(forest.value, treeExpanded, people.value, peopleById.value))

// ---------------------------------------------------------------- «Таблица»
const tableSort = ref({ key: 'path', dir: 'asc' })
const kindFilter = ref('')
const allTableRows = computed(() => unitTableRows(units.value, peopleById.value, kinds.value))
const tableRows = computed(() => sortRows(
  allTableRows.value.filter((r) => !kindFilter.value || r.kind === kindFilter.value), tableSort.value.key, tableSort.value.dir,
))
const usedKinds = computed(() => kinds.value.filter((k) => units.value.some((u) => u.kind === k.value)))
const tableIndent = computed(() => tableSort.value.key === 'path' && tableSort.value.dir === 'asc' && !kindFilter.value)
const tableTotals = computed(() => ({
  label: countText(tableRows.value.length, UNIT_FORMS),
  staff: tableRows.value.reduce((sum, r) => sum + r.staff, 0),
  branch: kindFilter.value ? null : forest.value.reduce((sum, n) => sum + (n.item.branch_employee_count || 0), 0),
}))
function sortTable(key) {
  tableSort.value = nextSort(tableSort.value, key)
}
function exportTable() {
  const blob = new Blob([toCsv(tableRows.value, TABLE_CSV_COLUMNS)], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `Структура компании ${new Date().toISOString().slice(0, 10)}.csv`
  a.style.display = 'none'
  document.body.appendChild(a)
  a.click()
  setTimeout(() => { a.remove(); URL.revokeObjectURL(url) }, 1500)
}

// ---------------------------------------------------------------- заголовок
const summary = computed(() => [
  countText(units.value.length, UNIT_FORMS),
  countText(activePeople.value.length, PEOPLE_FORMS),
  depth.value ? countText(depth.value, LEVEL_FORMS) : '',
].filter(Boolean).join(' · '))
const zoomPercent = computed(() => `${Math.round(prefs.zoom * 100)} %`)
</script>

<template>
  <div class="org-page" :class="`view-${view}`">
    <PageHeader title="Структура компании" :description="data ? summary : 'Подразделения, руководители и сотрудники'">
      <router-link v-if="canManage" to="/admin/departments" class="btn btn-ghost admin-link" title="Изменить структуру: подразделения и руководители"><OrgIcon name="edit" :size="15" /><span>Подразделения</span></router-link>
      <router-link v-if="canManage" to="/admin/org-transfer" class="btn btn-ghost admin-link" title="Загрузка и выгрузка структуры и сотрудников"><OrgIcon name="upload" :size="15" /><span>Импорт и экспорт</span></router-link>
      <div class="views" role="tablist" aria-label="Вид структуры">
        <button v-for="v in ORG_VIEWS" :key="v.value" type="button" role="tab" class="view-tab" :class="{ active: view === v.value }"
                :aria-selected="view === v.value" :title="v.hint" :data-testid="`org-view-${v.value}`" @click="setView(v.value)">
          <OrgIcon :name="v.icon" :size="15" /><span>{{ v.label }}</span>
        </button>
      </div>
    </PageHeader>

    <div class="toolbar card" role="toolbar" aria-label="Инструменты структуры">
      <OrgSearch v-model="query" :results="results" :kind-of="kindOf" @pick="pick" />
      <template v-if="view !== 'table'">
        <label class="levels" title="Сколько уровней раскрыть">
          <span>Уровней</span>
          <select class="select select-sm" :value="prefs.levels" aria-label="Сколько уровней раскрыть" data-testid="org-levels" @change="setLevels($event.target.value)">
            <option v-for="o in levelChoices" :key="o.value" :value="o.value">{{ o.label }}</option>
          </select>
        </label>
        <button type="button" class="btn btn-ghost btn-sm" aria-label="Развернуть всё" @click="expandAll"><OrgIcon name="expand-all" :size="14" /><span class="lbl">Развернуть всё</span></button>
        <button type="button" class="btn btn-ghost btn-sm" aria-label="Свернуть" @click="collapseAll"><OrgIcon name="collapse-all" :size="14" /><span class="lbl">Свернуть</span></button>
      </template>
      <select v-else v-model="kindFilter" class="select select-sm kind-filter" aria-label="Тип подразделения" :class="{ set: kindFilter }">
        <option value="">Все типы</option>
        <option v-for="k in usedKinds" :key="k.value" :value="k.value">{{ k.label }}</option>
      </select>
      <button type="button" class="btn btn-ghost btn-sm" :disabled="!canLocate"
              :title="canLocate ? 'Показать ваше место в структуре' : 'Вас нет в структуре'" data-testid="org-where-am-i" @click="whereAmI()">
        <OrgIcon name="locate" :size="14" /><span class="lbl">Где я</span>
      </button>
      <span class="spacer" />

      <template v-if="isCanvas">
        <div class="tool-group" role="group" aria-label="Вид схемы">
          <button type="button" class="icon-tool" :title="prefs.orientation === 'vertical' ? 'Расположить слева направо' : 'Расположить сверху вниз'"
                  :aria-label="prefs.orientation === 'vertical' ? 'Расположить слева направо' : 'Расположить сверху вниз'" data-testid="org-orientation"
                  @click="prefs.orientation = prefs.orientation === 'vertical' ? 'horizontal' : 'vertical'">
            <OrgIcon :name="prefs.orientation === 'vertical' ? 'orient-v' : 'orient-h'" :size="17" />
          </button>
          <button type="button" class="icon-tool" :class="{ on: prefs.stackLeaves }" :disabled="prefs.orientation !== 'vertical'"
                  title="Нижний уровень столбиком — схема уже" aria-label="Нижний уровень столбиком" :aria-pressed="prefs.stackLeaves"
                  @click="prefs.stackLeaves = !prefs.stackLeaves">
            <OrgIcon name="stack" :size="17" />
          </button>
          <button type="button" class="icon-tool" :class="{ on: prefs.compact }" title="Компактные карточки" aria-label="Компактные карточки"
                  :aria-pressed="prefs.compact" @click="prefs.compact = !prefs.compact">
            <OrgIcon name="compact" :size="17" />
          </button>
        </div>
        <div class="tool-group zoom" role="group" aria-label="Масштаб">
          <button type="button" class="icon-tool" aria-label="Уменьшить" title="Уменьшить (−)" :disabled="prefs.zoom <= ZOOM.min" @click="canvas?.zoomBy(-ZOOM.step)"><OrgIcon name="zoom-out" :size="17" /></button>
          <button type="button" class="zoom-value num" title="Масштаб 100 %" data-testid="org-zoom" @click="canvas?.zoomTo(1)">{{ zoomPercent }}</button>
          <button type="button" class="icon-tool" aria-label="Увеличить" title="Увеличить (+)" :disabled="prefs.zoom >= ZOOM.max" @click="canvas?.zoomBy(ZOOM.step)"><OrgIcon name="zoom-in" :size="17" /></button>
          <button type="button" class="btn btn-ghost btn-sm fit" title="Вписать схему в окно" aria-label="Вписать схему в окно" @click="canvas?.fit()"><OrgIcon name="fit" :size="14" /><span class="lbl">Вписать</span></button>
        </div>
      </template>
      <template v-else-if="view === 'table'">
        <button type="button" class="btn btn-sm" data-testid="org-export" :disabled="!tableRows.length" @click="exportTable">
          <AppIcon name="download" :size="14" />Выгрузить в Excel
        </button>
      </template>
    </div>

    <div v-if="loading && !data" class="org-body">
      <div class="skeleton canvas-skel" />
    </div>
    <EmptyState v-else-if="error && !data" icon="alert" title="Не удалось загрузить структуру" :text="error.message" class="card">
      <button class="btn btn-sm" type="button" @click="reload()">Повторить</button>
    </EmptyState>
    <EmptyState v-else-if="data && !units.length" icon="org" title="Структура ещё не заполнена"
                :text="canManage ? 'Добавьте подразделения или загрузите структуру из файла.' : 'Подразделения появятся, когда их заведут ведущие структуру.'" class="card">
      <router-link v-if="canManage" to="/admin/departments" class="btn btn-primary btn-sm">Добавить подразделения</router-link>
      <router-link v-if="canManage" to="/admin/org-transfer" class="btn btn-sm">Загрузить из файла</router-link>
    </EmptyState>

    <div v-else-if="data" class="org-body" :class="{ 'with-panel': selection }">
      <div class="org-main">
        <OrgChart v-if="view === 'chart'" ref="canvas" v-model:zoom="prefs.zoom" class="org-canvas" label="Оргсхема подразделений"
                  :forest="forest" :expanded="unitExpanded" :path="unitPath" :orientation="prefs.orientation" :stack-leaves="prefs.stackLeaves">
          <template #default="{ node, expanded, onPath }">
            <OrgUnitCard :unit="node.item" :kind="kindOf(node.item.kind)" :head="peopleById.get(node.item.primary_head_id) || null"
                         :expanded="expanded" :on-path="onPath" :selected="selectedKeys.has(`unit:${node.id}`)"
                         :mine="node.id === myUnitId" :compact="prefs.compact"
                         @select="selectUnit" @toggle="toggleUnit" @select-person="selectPerson" />
          </template>
        </OrgChart>

        <OrgChart v-else-if="view === 'people'" ref="canvas" v-model:zoom="prefs.zoom" class="org-canvas" label="Схема подчинения"
                  :forest="team" :expanded="teamExpanded" :path="teamPath" :orientation="prefs.orientation" :stack-leaves="prefs.stackLeaves">
          <template #default="{ node, expanded, onPath }">
            <OrgGroupCard v-if="node.group" :count="node.item.count" :expanded="expanded" @toggle="toggleTeam(node.id)" />
            <OrgPersonNode v-else :person="node.item" :unit-name="unitsById.get(homeOf(node.item))?.name || ''" :child-count="node.children.length"
                           :expanded="expanded" :on-path="onPath" :selected="selectedKeys.has(`person:${node.id}`)"
                           :me="node.id === me?.id" :compact="prefs.compact" @select="selectPerson" @toggle="toggleTeam" />
          </template>
        </OrgChart>

        <OrgTreeView v-else-if="view === 'tree'" ref="treeView" class="org-fill" :rows="rowsOfTree" :kind-of="kindOf" :units-by-id="unitsById"
                     :selected="selection" :my-unit-id="myUnitId" :me-id="me?.id ?? null"
                     @toggle="toggleTree" @select-unit="selectUnit" @select-person="selectPerson" />

        <OrgTable v-else ref="tableView" class="org-fill" :rows="tableRows" :sort="tableSort" :indent="tableIndent" :totals="tableTotals"
                  :selected-id="selection?.type === 'unit' ? selection.id : (selectedPerson ? homeOf(selectedPerson) : null)"
                  :my-unit-id="myUnitId" @sort="sortTable" @select-unit="selectUnit" @select-person="(id) => selectPerson(id)" />
      </div>

      <OrgSidePanel v-if="selection" ref="panel" :label="selectedUnit ? `Подразделение «${selectedUnit.name}»` : 'Сотрудник'" @close="clearSelection">
        <OrgUnitPanel v-if="selectedUnit" :unit="selectedUnit" :kind-of="kindOf" :units-by-id="unitsById" :people-by-id="peopleById"
                      :people="people" :units="units" :mine="selectedUnit.id === myUnitId" :can-manage="canManage"
                      @select-unit="(id) => selectUnit(id, fromPanel)" @select-person="(id) => selectPerson(id, fromPanel)" />
        <OrgPersonPanel v-else-if="selectedPerson" :person="selectedPerson" :card="card" :loading="cardLoading" :kind-of="kindOf"
                        :units-by-id="unitsById" :people-by-id="peopleById" :unit-items="unitItems" :people="activePeople"
                        :me="selectedPerson.id === me?.id" :can-manage="canManage"
                        @select-unit="(id) => selectUnit(id, fromPanel)" @select-person="(id) => selectPerson(id, fromPanel)" @saved="onPersonSaved" />
        <EmptyState v-else compact icon="search" title="Не найдено" text="Подразделение или сотрудник удалены либо недоступны." />
      </OrgSidePanel>
    </div>
  </div>
</template>

<style scoped>
.org-page {
  display: flex; flex-direction: column; gap: var(--sp-4); max-width: var(--content-max); margin: 0 auto;
  height: calc(100dvh - var(--topbar-h) - var(--sp-6) - var(--sp-10)); min-height: 560px;
}
.admin-link { color: var(--text-2); }
.views { display: inline-flex; gap: 2px; padding: 3px; border-radius: 11px; background: var(--surface-3); border: 1px solid var(--border); }
.view-tab {
  display: inline-flex; align-items: center; gap: 7px; height: 30px; padding: 0 12px; border: 0; border-radius: 8px;
  background: transparent; color: var(--text-2); font-size: var(--fs-sm); font-weight: 560; cursor: pointer; white-space: nowrap;
  transition: background var(--t-fast), color var(--t-fast), box-shadow var(--t-fast);
}
.view-tab:hover { color: var(--text); }
.view-tab.active { background: var(--bg-elevated); color: var(--text); box-shadow: var(--shadow-sm); font-weight: 620; }
.view-tab:focus-visible { outline: 2px solid var(--focus); outline-offset: 1px; }

.toolbar { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; padding: 10px 12px; position: relative; z-index: 5; }
.toolbar .btn-sm { padding: 0 9px; gap: 6px; }
.levels { display: inline-flex; align-items: center; gap: 7px; margin: 0 2px 0 6px; font-size: var(--fs-xs); font-weight: 620; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); }
.levels .select { width: 66px; height: 30px; text-transform: none; letter-spacing: 0; font-weight: 500; color: var(--text); }
.kind-filter { width: auto; min-width: 160px; height: 30px; }
.kind-filter.set { border-color: color-mix(in srgb, var(--accent) 45%, var(--border-strong)); }
.toolbar .btn-ghost { color: var(--text-2); }
.toolbar .btn-ghost:hover:not(:disabled) { color: var(--text); }
.tool-group { display: inline-flex; align-items: center; gap: 1px; padding-left: 6px; border-left: 1px solid var(--border); }
.icon-tool { width: 32px; height: 32px; display: grid; place-items: center; border: 0; border-radius: 8px; background: transparent; color: var(--text-2); cursor: pointer; transition: background var(--t-fast), color var(--t-fast); }
.icon-tool:hover:not(:disabled) { background: var(--surface-3); color: var(--text); }
.icon-tool.on { background: color-mix(in srgb, var(--accent) 12%, transparent); color: var(--accent); }
.icon-tool:disabled { opacity: .4; cursor: not-allowed; }
.icon-tool:focus-visible, .zoom-value:focus-visible { outline: 2px solid var(--focus); outline-offset: 0; }
.zoom-value { min-width: 50px; height: 30px; border: 0; border-radius: 8px; background: transparent; color: var(--text-2); font-size: var(--fs-sm); font-weight: 560; cursor: pointer; }
.zoom-value:hover { background: var(--surface-3); color: var(--text); }
.fit { margin-left: 2px; }

.org-body { flex: 1; min-height: 0; display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--sp-4); }
.org-body.with-panel { grid-template-columns: minmax(0, 1fr) 380px; }
.org-main { min-width: 0; min-height: 0; display: flex; flex-direction: column; }
.org-canvas, .org-fill { flex: 1; min-height: 0; }
.canvas-skel { height: 100%; border-radius: var(--radius-lg); }

@media (max-width: 1280px) {
  .org-body.with-panel { grid-template-columns: minmax(0, 1fr) 340px; }
}
@media (max-width: 1100px) {
  .admin-link span { display: none; }
  .admin-link { width: 34px; padding: 0; }
}
@media (max-width: 960px) {
  .org-page { height: calc(100dvh - var(--topbar-h) - var(--sp-4) - var(--sp-8)); min-height: 520px; }
}
@media (max-width: 900px) {
  .org-body.with-panel { grid-template-columns: minmax(0, 1fr); }
}
@media (max-width: 640px) {
  .org-page { gap: var(--sp-3); }
  .org-page :deep(.page-actions) { width: 100%; }
  .views { width: 100%; }
  .view-tab { flex: 1; justify-content: center; padding: 0 6px; }
  .view-tab :deep(svg) { display: none; }
  .admin-link { display: none; }
  .toolbar { padding: 8px; gap: 4px; }
  .levels { margin-left: 0; }
  .levels span, .toolbar .lbl { display: none; }
  .toolbar .btn-ghost.btn-sm { width: 32px; padding: 0; }
  .tool-group { border-left: 0; padding-left: 0; }
  .zoom-value { min-width: 46px; }
}
</style>
