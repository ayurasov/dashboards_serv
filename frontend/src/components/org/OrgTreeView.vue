<script setup>
import { nextTick, onBeforeUnmount, ref } from 'vue'
import OrgAvatar from './OrgAvatar.vue'
import OrgIcon from './OrgIcon.vue'
import OrgVirtualList from './OrgVirtualList.vue'
import { PEOPLE_FORMS, countText, homeOf } from '@/domain/org'

/**
 * Вид «Дерево»: подразделения с отступами; под раскрытым — руководители (основной отмечен),
 * сотрудники уровня и вложенные подразделения. Строки отрисовываются только видимые.
 */
const props = defineProps({
  rows: { type: Array, required: true },
  kindOf: { type: Function, required: true },
  unitsById: { type: Map, required: true },
  selected: { type: Object, default: null },
  myUnitId: { type: Number, default: null },
  meId: { type: Number, default: null },
})
const emit = defineEmits(['toggle', 'select-unit', 'select-person'])

const HEIGHTS = { unit: 46, person: 50, group: 46 }
const heightOf = (row) => HEIGHTS[row.type]
const list = ref(null)
const flashKey = ref('')
let timer = null
onBeforeUnmount(() => clearTimeout(timer))

const isSelected = (row) => !!props.selected && (row.type === 'unit'
  ? props.selected.type === 'unit' && props.selected.id === row.id
  : row.type === 'person' && props.selected.type === 'person' && props.selected.id === row.id)

/** Прокрутить к подразделению или сотруднику и подсветить строку. */
async function focus(type, id, { flash = false } = {}) {
  await nextTick()
  let index
  if (type === 'unit') index = props.rows.findIndex((r) => r.type === 'unit' && r.id === id)
  else {
    index = props.rows.findIndex((r) => r.type === 'person' && r.id === id && r.role !== 'visiting')
    if (index < 0) index = props.rows.findIndex((r) => r.type === 'person' && r.id === id)
  }
  if (index < 0) return
  list.value?.scrollToIndex(index, { force: true })
  if (flash) {
    flashKey.value = ''
    await nextTick()
    flashKey.value = props.rows[index].key
    clearTimeout(timer)
    timer = setTimeout(() => { flashKey.value = '' }, 1800)
  }
}
function scrollTop() {
  list.value?.el?.scrollTo({ top: 0 })
}
defineExpose({ focus, scrollTop })

function homeName(person) {
  return props.unitsById.get(homeOf(person))?.name || ''
}
</script>

<template>
  <section class="org-tree card" aria-label="Подразделения и сотрудники">
    <OrgVirtualList ref="list" class="tree-scroll" :items="rows" :height="heightOf" role="tree" label="Структура компании списком">
      <template #default="{ item: row }">
        <div v-if="row.type === 'unit'" class="tr unit" :class="{ selected: isSelected(row), flash: flashKey === row.key }"
             :style="{ '--depth': row.depth, '--kind': kindOf(row.unit.kind).color }" role="treeitem" :aria-level="row.depth + 1"
             :aria-expanded="row.expandable ? row.open : undefined" :aria-selected="isSelected(row)" :data-row="row.key">
          <span class="indent" aria-hidden="true" />
          <button v-if="row.expandable" type="button" class="chev" :class="{ open: row.open }"
                  :aria-label="row.open ? `Свернуть «${row.unit.name}»` : `Развернуть «${row.unit.name}»`" @click="emit('toggle', row.id)">
            <OrgIcon name="chevron-right" :size="14" :stroke="2.2" />
          </button>
          <span v-else class="chev-space" />
          <button type="button" class="main" @click="emit('select-unit', row.id)">
            <span class="kind-dot" aria-hidden="true" />
            <span class="unit-name">{{ row.unit.name }}</span>
            <span class="kind-label">{{ kindOf(row.unit.kind).label }}</span>
            <span v-if="row.id === myUnitId" class="you">Вы здесь</span>
          </button>
          <span class="count num" :title="row.unit.child_count ? 'Штат уровня (без руководителей) · вся ветка' : 'Штат уровня (без руководителей)'">
            {{ (row.unit.employee_count || 0).toLocaleString('ru-RU') }}<span class="w"> на уровне</span><template v-if="row.unit.child_count"><span class="sep">·</span>{{ row.unit.branch_employee_count.toLocaleString('ru-RU') }}<span class="w"> в ветке</span></template>
          </span>
        </div>

        <div v-else-if="row.type === 'group'" class="tr unit group" :style="{ '--depth': 0 }" role="treeitem" aria-level="1" :aria-expanded="row.open">
          <span class="indent" aria-hidden="true" />
          <button type="button" class="chev" :class="{ open: row.open }" :aria-label="row.open ? 'Свернуть «Вне структуры»' : 'Развернуть «Вне структуры»'" @click="emit('toggle', row.id)">
            <OrgIcon name="chevron-right" :size="14" :stroke="2.2" />
          </button>
          <button type="button" class="main" @click="emit('toggle', row.id)">
            <OrgIcon name="users" :size="14" class="group-icon" />
            <span class="unit-name">Вне структуры</span>
            <span class="kind-label">без подразделения</span>
          </button>
          <span class="count num">{{ countText(row.count, PEOPLE_FORMS) }}</span>
        </div>

        <div v-else class="tr person" :class="{ selected: isSelected(row), flash: flashKey === row.key, head: row.role !== 'member' }"
             :style="{ '--depth': row.depth }" role="treeitem" :aria-level="row.depth + 1" :aria-selected="isSelected(row)" :data-row="row.key">
          <span class="indent" aria-hidden="true" />
          <span class="chev-space" />
          <button type="button" class="main" @click="emit('select-person', row.id)">
            <OrgAvatar :person="row.person" :size="30" />
            <span class="text">
              <span class="line">
                <span class="person-name">{{ row.person.full_name }}</span>
                <span v-if="row.role !== 'member'" class="role" :class="{ primary: row.primary }" :title="row.primary ? 'Основной руководитель' : 'Руководитель'">
                  <OrgIcon v-if="row.primary" name="star" :size="11" :stroke="2" /><span class="w">Руководитель</span>
                </span>
                <span v-if="row.id === meId" class="you">Вы</span>
              </span>
              <small>
                {{ row.person.position || 'Должность не указана' }}<template v-if="row.role === 'visiting' && homeName(row.person)"> · числится в «{{ homeName(row.person) }}»</template>
              </small>
            </span>
          </button>
          <span v-if="row.person.report_count" class="count num" title="Прямые подчинённые · вся ветка">
            {{ row.person.report_count }} прямых<template v-if="row.person.branch_count > row.person.report_count"><span class="sep">·</span>{{ row.person.branch_count.toLocaleString('ru-RU') }} в ветке</template>
          </span>
        </div>
      </template>
    </OrgVirtualList>
    <p v-if="!rows.length" class="empty">Подразделений пока нет</p>
  </section>
</template>

<style scoped>
.org-tree { display: flex; flex-direction: column; min-height: 0; overflow: hidden; }
.tree-scroll { flex: 1; min-height: 0; padding: 6px 0; }
.tr { position: relative; display: flex; align-items: center; gap: 6px; height: 100%; padding: 0 14px 0 calc(12px + var(--depth) * 24px); border-radius: 0; transition: background var(--t-fast); }
.tr:hover { background: var(--row-hover); }
.tr.selected { background: color-mix(in srgb, var(--accent) 10%, transparent); }
.tr.selected::before { content: ''; position: absolute; left: 0; top: 6px; bottom: 6px; width: 3px; border-radius: 0 3px 3px 0; background: var(--accent); }
.tr.flash { animation: row-flash 1.7s var(--ease); }
@keyframes row-flash { 15%, 55% { background: color-mix(in srgb, var(--accent) 18%, transparent); } }
/* Направляющие уровней */
.indent { position: absolute; left: 12px; top: 0; bottom: 0; width: calc(var(--depth) * 24px); pointer-events: none;
  background: repeating-linear-gradient(to right, transparent 0 10px, var(--border) 10px 11px, transparent 11px 24px); }
.chev, .chev-space { width: 24px; height: 24px; flex: 0 0 24px; }
.chev { display: grid; place-items: center; padding: 0; border: 0; border-radius: 6px; background: transparent; color: var(--muted); cursor: pointer; transition: transform var(--t-fast), background var(--t-fast), color var(--t-fast); }
.chev:hover { background: var(--surface-3); color: var(--text); }
.chev.open { transform: rotate(90deg); }
.chev:focus-visible, .main:focus-visible { outline: 2px solid var(--focus); outline-offset: 0; }
.main { display: flex; align-items: center; gap: 9px; flex: 1; min-width: 0; height: 100%; padding: 0 4px; border: 0; background: transparent; color: inherit; text-align: left; cursor: pointer; border-radius: 6px; }
.kind-dot { width: 9px; height: 9px; flex: 0 0 9px; border-radius: 3px; background: var(--kind); }
.unit-name { font-size: var(--fs-base); font-weight: 620; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; }
.kind-label { flex: 0 0 auto; font-size: var(--fs-xs); color: var(--muted); }
.group-icon { color: var(--muted); }
.group .unit-name { color: var(--text-2); }
.you { flex: 0 0 auto; height: 18px; padding: 0 7px; display: inline-flex; align-items: center; border-radius: var(--radius-pill); background: var(--text); color: var(--bg-elevated); font-size: 10.5px; font-weight: 650; }
.count { flex: 0 0 auto; font-size: var(--fs-xs); color: var(--muted); white-space: nowrap; }
.unit .count { color: var(--text-2); font-weight: 560; }
.sep { margin: 0 5px; color: var(--faint); }
.text { display: flex; flex-direction: column; min-width: 0; line-height: 1.3; }
.line { display: flex; align-items: center; gap: 7px; min-width: 0; }
.person-name { font-size: var(--fs-sm); font-weight: 560; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.head .person-name { font-weight: 640; }
.role { flex: 0 0 auto; display: inline-flex; align-items: center; gap: 3px; height: 18px; padding: 0 7px; border-radius: var(--radius-pill); background: var(--surface-3); color: var(--text-2); font-size: 10.5px; font-weight: 620; }
.role.primary { background: color-mix(in srgb, var(--light-yellow) 16%, transparent); color: color-mix(in srgb, var(--light-yellow) 75%, var(--text)); }
.text small { font-size: var(--fs-xs); color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.empty { padding: 32px; text-align: center; color: var(--muted); }
@media (max-width: 640px) {
  .tr { padding-left: calc(6px + var(--depth) * 14px); padding-right: 10px; }
  .indent { left: 6px; width: calc(var(--depth) * 14px); background: repeating-linear-gradient(to right, transparent 0 6px, var(--border) 6px 7px, transparent 7px 14px); }
  .kind-label, .person .count, .w { display: none; }
  .role { padding: 0 5px; }
}
</style>
