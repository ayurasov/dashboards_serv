<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppIcon from '@/components/ui/AppIcon.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import DepartmentDialog from '@/components/org/DepartmentDialog.vue'
import DepartmentHeadsDialog from '@/components/org/DepartmentHeadsDialog.vue'
import OrgIcon from '@/components/org/OrgIcon.vue'
import OrgSettingsDialog from '@/components/org/OrgSettingsDialog.vue'
import { orgApi } from '@/api/org'
import { useAsync } from '@/composables/useAsync'
import { confirm } from '@/composables/useConfirm'
import { toastOk } from '@/composables/useToast'
import { plural } from '@/utils/format'
import {
  LEVEL_FORMS, PEOPLE_FORMS, UNIT_FORMS, canAddChild, countText, deleteMessage, departmentRows, kindInfo,
} from '@/domain/org'

/**
 * Подразделения (ADR-0007): дерево с численностью и руководителями; добавление вложенного уровня,
 * изменение (название, «входит в», тип, код, порядок), руководители с основным, удаление;
 * «Типы уровней и вложенность». Ведут администратор и ведущие структуру (org.manage).
 */
const route = useRoute()
const router = useRouter()
const deps = useAsync(() => orgApi.departments())
const tree = useAsync(() => orgApi.tree())
const settings = useAsync(() => orgApi.settings())

const departments = computed(() => deps.data.value || [])
const people = computed(() => tree.data.value?.people || [])
const kinds = computed(() => settings.data.value?.unit_kinds || tree.data.value?.settings?.unit_kinds || [])
const maxDepth = computed(() => settings.data.value?.max_depth || tree.data.value?.settings?.max_depth || 15)
const currentDepth = computed(() => departments.value.reduce((max, d) => Math.max(max, d.level || 1), 0))
const unitsById = computed(() => new Map((tree.data.value?.units || []).map((u) => [u.id, u])))
const kindOf = (value) => kindInfo(kinds.value, value)
const unassigned = computed(() => people.value.filter((p) => p.is_active !== false && p.home_unit_id == null).length)
const noHeads = computed(() => departments.value.filter((d) => !(d.heads || []).length).length)

function reloadAll() {
  return Promise.all([deps.reload(), tree.reload(), settings.reload()])
}

// ---------------------------------------------------------------- дерево
const collapsed = ref(new Set())
const query = ref('')
const rows = computed(() => departmentRows(departments.value, collapsed.value, query.value))
const expandable = computed(() => departments.value.filter((d) => d.child_count))
function toggle(id) {
  const next = new Set(collapsed.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  collapsed.value = next
}
const expandAll = () => { collapsed.value = new Set() }
const collapseAll = () => { collapsed.value = new Set(expandable.value.map((d) => d.id)) }
function revealRow(id) {
  const byId = new Map(departments.value.map((d) => [d.id, d]))
  const next = new Set(collapsed.value)
  for (let d = byId.get(byId.get(id)?.parent_id); d; d = byId.get(d.parent_id)) next.delete(d.id)
  collapsed.value = next
}

const highlight = ref(null)
let highlightTimer = null
async function flashRow(id) {
  revealRow(id)
  await nextTick()
  document.querySelector(`tr[data-department-id="${id}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  highlight.value = id
  clearTimeout(highlightTimer)
  highlightTimer = setTimeout(() => { highlight.value = null }, 1800)
}

// ---------------------------------------------------------------- диалоги
const editing = ref(null)            // { department } | { parentId } — новое
const heads = ref(null)
const settingsOpen = ref(false)

function openCreate(parentId = null) { editing.value = { department: null, parentId } }
function openEdit(department) { editing.value = { department, parentId: null } }
async function onSaved(saved) {
  const isNew = !editing.value?.department
  editing.value = null
  toastOk(isNew ? `Подразделение «${saved.name}» добавлено` : 'Подразделение сохранено')
  await reloadAll()
  flashRow(saved.id)
}
async function onHeadsSaved(saved) {
  heads.value = null
  toastOk(`Руководители «${saved.name}» сохранены`)
  await reloadAll()
  flashRow(saved.id)
}
async function onSettingsSaved() {
  settingsOpen.value = false
  toastOk('Настройки структуры сохранены')
  await reloadAll()
}
async function remove(department) {
  if (department.child_count) return
  const ok = await confirm({
    title: `Удалить «${department.name}»?`, message: deleteMessage(department, people.value), confirmText: 'Удалить', danger: true,
  })
  if (!ok) return
  try {
    const result = await orgApi.deleteDepartment(department.id)
    toastOk(result?.message || 'Подразделение удалено')
    await reloadAll()
  } catch {}
}

// Переход из оргсхемы («Изменить подразделение»): ?dep=ID открывает его
watch(() => [route.query.dep, departments.value.length], ([dep]) => {
  const id = Number(dep)
  const department = id && departments.value.find((d) => d.id === id)
  if (!department) return
  router.replace({ query: { ...route.query, dep: undefined } })
  flashRow(id)
  openEdit(department)
}, { immediate: true })

const addTitle = (d) => (canAddChild(d, maxDepth.value)
  ? `Добавить подразделение в «${d.name}»`
  : `Достигнут предел вложенности (${maxDepth.value}) — увеличьте его в «Типы уровней и вложенность»`)
const deleteTitle = (d) => (d.child_count ? 'Сначала перенесите или удалите вложенные подразделения' : `Удалить «${d.name}»`)
const heads0 = (d) => [...(d.heads || [])].sort((a, b) => Number(b.is_primary) - Number(a.is_primary) || a.full_name.localeCompare(b.full_name, 'ru'))
</script>

<template>
  <div class="page">
    <PageHeader title="Подразделения" description="Дерево структуры: уровни, руководители и численность">
      <button class="btn" type="button" :disabled="!settings.data.value" data-testid="org-settings-open" @click="settingsOpen = true">
        <AppIcon name="settings" :size="15" />Типы уровней и вложенность
      </button>
      <button class="btn btn-primary" type="button" :disabled="!deps.data.value" data-testid="department-add" @click="openCreate()">
        <AppIcon name="plus" :size="15" />Добавить подразделение
      </button>
    </PageHeader>

    <p v-if="deps.data.value" class="summary">
      <span><b>{{ countText(departments.length, UNIT_FORMS) }}</b></span>
      <span>вложенность <b>{{ currentDepth }}</b> из {{ maxDepth }} {{ plural(maxDepth, LEVEL_FORMS) }}</span>
      <span v-if="noHeads" class="warn-text">без руководителя: {{ noHeads }}</span>
      <router-link v-if="unassigned" :to="{ path: '/org', query: { view: 'tree' } }">{{ countText(unassigned, PEOPLE_FORMS) }} без подразделения</router-link>
      <router-link to="/org"><OrgIcon name="org" :size="13" />Оргсхема</router-link>
      <router-link to="/admin/org-transfer"><OrgIcon name="upload" :size="13" />Импорт и экспорт</router-link>
    </p>

    <section class="card">
      <div class="tools">
        <label class="search">
          <OrgIcon name="search" :size="14" />
          <input v-model="query" type="search" placeholder="Название или код" aria-label="Поиск подразделения" />
        </label>
        <span class="spacer" />
        <button type="button" class="btn btn-ghost btn-sm" :disabled="!!query" @click="expandAll"><OrgIcon name="expand-all" :size="14" />Развернуть всё</button>
        <button type="button" class="btn btn-ghost btn-sm" :disabled="!!query || !expandable.length" @click="collapseAll"><OrgIcon name="collapse-all" :size="14" />Свернуть всё</button>
      </div>

      <div class="table-wrap">
        <table v-if="rows.length" class="table deps" role="treegrid" aria-label="Подразделения">
          <thead>
            <tr><th>Подразделение</th><th class="num">Сотрудники</th><th>Руководители</th><th class="actions-col"><span class="sr-only">Действия</span></th></tr>
          </thead>
          <tbody>
            <tr v-for="row in rows" :key="row.dep.id" :data-department-id="row.dep.id" :aria-level="row.depth + 1"
                :aria-expanded="row.dep.child_count && !query ? !collapsed.has(row.dep.id) : undefined"
                :class="{ flash: highlight === row.dep.id, dim: query && !row.match }" :style="{ '--depth': row.depth, '--kind': kindOf(row.dep.kind).color }">
              <td class="name-cell">
                <span class="guides" aria-hidden="true" />
                <div class="name-line">
                  <button v-if="row.dep.child_count && !query" type="button" class="chev" :class="{ open: !collapsed.has(row.dep.id) }"
                          :aria-label="collapsed.has(row.dep.id) ? `Развернуть «${row.dep.name}»` : `Свернуть «${row.dep.name}»`" @click="toggle(row.dep.id)">
                    <OrgIcon name="chevron-right" :size="14" :stroke="2.2" />
                  </button>
                  <span v-else class="chev-space" />
                  <span class="dep-name">{{ row.dep.name }}</span>
                  <span class="kind"><i />{{ kindOf(row.dep.kind).label }}</span>
                  <span v-if="row.dep.code" class="code">{{ row.dep.code }}</span>
                </div>
              </td>
              <td class="num staff" :title="row.dep.child_count ? 'Сотрудники подразделения (с руководителем) / вся ветка' : 'Сотрудники подразделения (с руководителем)'">
                <b>{{ row.dep.employee_count }}</b><span v-if="row.dep.child_count" class="branch"> / {{ row.dep.branch_employee_count }} в ветке</span>
              </td>
              <td class="heads-cell">
                <span v-for="h in heads0(row.dep)" :key="h.user_id" class="head-chip" :class="{ primary: h.is_primary && row.dep.heads.length > 1, off: !h.is_active }"
                      :title="`${h.full_name}${h.position ? ` — ${h.position}` : ''}${h.is_primary ? ' · основной' : ''}${h.is_active ? '' : ' · отключён'}`">
                  <OrgIcon v-if="h.is_primary && row.dep.heads.length > 1" name="star" :size="11" :stroke="2" />{{ h.full_name }}
                </span>
                <span v-if="!row.dep.heads.length" class="no-head" :title="row.dep.parent_id ? 'Сотрудники подчиняются руководителю вышестоящего подразделения' : ''">
                  <OrgIcon name="alert" :size="12" />Руководитель не назначен
                </span>
              </td>
              <td class="actions-col">
                <button type="button" class="btn btn-ghost btn-icon btn-sm" :disabled="!canAddChild(row.dep, maxDepth)" :title="addTitle(row.dep)"
                        :aria-label="`Добавить вложенное в «${row.dep.name}»`" @click="openCreate(row.dep.id)"><OrgIcon name="plus" :size="15" /></button>
                <button type="button" class="btn btn-ghost btn-sm" :aria-label="`Руководители «${row.dep.name}»`" @click="heads = row.dep">
                  <OrgIcon name="users" :size="14" /><span class="lbl">Руководители</span>
                </button>
                <button type="button" class="btn btn-ghost btn-icon btn-sm" title="Изменить" :aria-label="`Изменить «${row.dep.name}»`" @click="openEdit(row.dep)"><OrgIcon name="edit" :size="14" /></button>
                <button type="button" class="btn btn-ghost btn-icon btn-sm btn-danger" :disabled="row.dep.child_count > 0" :title="deleteTitle(row.dep)"
                        :aria-label="`Удалить «${row.dep.name}»`" @click="remove(row.dep)"><OrgIcon name="trash" :size="14" /></button>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-else-if="deps.loading.value && !deps.data.value" class="skeleton-rows"><div v-for="i in 6" :key="i" class="skeleton" /></div>
        <EmptyState v-else-if="query" compact icon="search" title="Ничего не найдено" text="Измените запрос." />
        <EmptyState v-else icon="building" title="Подразделений пока нет" text="Добавьте верхний уровень — компанию — и вкладывайте в него подразделения. Или загрузите структуру из файла.">
          <button class="btn btn-primary btn-sm" type="button" @click="openCreate()">Добавить подразделение</button>
          <router-link to="/admin/org-transfer" class="btn btn-sm">Загрузить из файла</router-link>
        </EmptyState>
      </div>
    </section>

    <p class="note muted"><AppIcon name="info" :size="14" />Сотрудника в подразделение и явного руководителя назначают в карточке сотрудника на странице «Структура компании».</p>

    <DepartmentDialog v-if="editing" :department="editing.department" :parent-id="editing.parentId" :departments="departments"
                      :kinds="kinds" :max-depth="maxDepth" @close="editing = null" @saved="onSaved" />
    <DepartmentHeadsDialog v-if="heads" :department="heads" :people="people" :units-by-id="unitsById" @close="heads = null" @saved="onHeadsSaved" />
    <OrgSettingsDialog v-if="settingsOpen" :settings="settings.data.value" @close="settingsOpen = false" @saved="onSettingsSaved" />
  </div>
</template>

<style scoped>
.summary { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 18px; margin-top: -8px; font-size: var(--fs-sm); color: var(--muted); }
.summary b { color: var(--text); font-weight: 650; }
.summary a { display: inline-flex; align-items: center; gap: 5px; color: var(--accent); }
.summary a:hover { text-decoration: underline; }
.warn-text { color: color-mix(in srgb, var(--light-yellow) 75%, var(--text)); }
.tools { display: flex; align-items: center; gap: 8px; padding: 12px 14px; border-bottom: 1px solid var(--border); flex-wrap: wrap; }
.search { display: flex; align-items: center; gap: 8px; height: 32px; width: 280px; max-width: 100%; padding: 0 10px; border: 1px solid var(--border-strong); border-radius: var(--radius); color: var(--muted); background: var(--surface); }
.search:focus-within { border-color: var(--accent); box-shadow: 0 0 0 3px var(--focus); }
.search input { flex: 1; min-width: 0; border: 0; outline: 0; background: transparent; color: var(--text); font-size: var(--fs-sm); }
.tools .btn-ghost { color: var(--text-2); }
.table-wrap { border-radius: 0 0 var(--radius-lg) var(--radius-lg); }
.deps th { background: var(--surface-2); }
.deps td { padding-top: 8px; padding-bottom: 8px; }
.deps tbody tr.flash { animation: row-flash 1.7s var(--ease); }
@keyframes row-flash { 15%, 55% { background: color-mix(in srgb, var(--accent) 16%, transparent); } }
.deps tbody tr.dim .dep-name { color: var(--muted); font-weight: 500; }
.name-cell { position: relative; min-width: 320px; padding-left: calc(10px + var(--depth) * 24px) !important; }
.name-line { display: flex; align-items: center; gap: 8px; }
.guides { position: absolute; left: 10px; top: 0; bottom: 0; width: calc(var(--depth) * 24px); pointer-events: none;
  background: repeating-linear-gradient(to right, transparent 0 11px, var(--border) 11px 12px, transparent 12px 24px); }
.chev, .chev-space { width: 24px; height: 24px; flex: 0 0 24px; }
.chev { display: grid; place-items: center; padding: 0; border: 0; border-radius: 6px; background: transparent; color: var(--muted); cursor: pointer; transition: transform var(--t-fast), background var(--t-fast); }
.chev:hover { background: var(--surface-3); color: var(--text); }
.chev.open { transform: rotate(90deg); }
.dep-name { min-width: 0; font-weight: 620; overflow-wrap: anywhere; }
.kind { flex: 0 0 auto; display: inline-flex; align-items: center; gap: 5px; height: 21px; padding: 0 8px; border-radius: var(--radius-pill);
  background: color-mix(in srgb, var(--kind) 12%, transparent); color: color-mix(in srgb, var(--kind) 78%, var(--text)); font-size: var(--fs-xs); font-weight: 600; }
.kind i { width: 6px; height: 6px; border-radius: 50%; background: var(--kind); }
.code { flex: 0 0 auto; padding: 1px 6px; border-radius: 5px; background: var(--surface-3); font-family: var(--font-mono); font-size: var(--fs-xs); color: var(--text-2); }
.staff { white-space: nowrap; }
.staff b { font-weight: 650; }
.branch { color: var(--muted); font-size: var(--fs-sm); }
.heads-cell { min-width: 220px; }
.head-chip { display: inline-flex; align-items: center; gap: 4px; max-width: 280px; height: 24px; margin: 2px 4px 2px 0; padding: 0 9px; border-radius: var(--radius-pill);
  background: var(--surface-3); color: var(--text); font-size: var(--fs-sm); font-weight: 520; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; vertical-align: middle; }
.head-chip.primary { background: color-mix(in srgb, var(--light-yellow) 15%, var(--surface)); box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--light-yellow) 40%, transparent); }
.head-chip.primary :deep(svg) { color: color-mix(in srgb, var(--light-yellow) 85%, var(--text)); }
.head-chip.off { color: var(--muted); text-decoration: line-through; }
.no-head { white-space: nowrap; display: inline-flex; align-items: center; gap: 5px; height: 24px; padding: 0 9px; border-radius: var(--radius-pill);
  background: color-mix(in srgb, var(--light-yellow) 13%, transparent); color: color-mix(in srgb, var(--light-yellow) 78%, var(--text)); font-size: var(--fs-xs); font-weight: 600; }
.actions-col { width: 1%; white-space: nowrap; text-align: right; }
.actions-col .btn { color: var(--text-2); }
.actions-col .btn-danger { color: var(--light-red); }
.deps tbody tr .actions-col .btn:not(:disabled) { opacity: .7; }
.deps tbody tr:hover .actions-col .btn:not(:disabled), .deps tbody tr:focus-within .actions-col .btn:not(:disabled) { opacity: 1; }
.skeleton-rows { display: flex; flex-direction: column; gap: 10px; padding: 14px; }
.skeleton-rows .skeleton { height: 40px; }
.note { display: flex; align-items: center; gap: 6px; font-size: var(--fs-sm); margin-top: -8px; }
@media (max-width: 900px) {
  .deps thead { display: none; }
  .deps, .deps tbody, .deps tr, .deps td { display: block; }
  .deps tr { display: grid; grid-template-columns: minmax(0, 1fr) auto; padding: 8px 0; border-bottom: 1px solid var(--border); }
  .deps td { border: 0; padding: 4px 12px !important; }
  .name-cell { grid-column: 1 / -1; min-width: 0; padding-left: calc(8px + var(--depth) * 14px) !important; }
  .guides { display: none; }
  .staff { grid-column: 2; grid-row: 2; text-align: right; }
  .heads-cell { grid-column: 1; grid-row: 2; min-width: 0; padding-left: calc(40px + var(--depth) * 14px) !important; }
  .actions-col { grid-column: 1 / -1; width: auto; text-align: left; padding-left: calc(36px + var(--depth) * 14px) !important; }
  .deps tbody tr .actions-col .btn:not(:disabled) { opacity: 1; }
  .search { width: 100%; }
}
</style>
