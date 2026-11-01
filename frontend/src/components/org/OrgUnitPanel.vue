<script setup>
import { computed, ref, watch } from 'vue'
import OrgIcon from './OrgIcon.vue'
import OrgPersonRow from './OrgPersonRow.vue'
import { PEOPLE_FORMS, UNIT_FORMS, countText, filterPeople, headsOf, homeOf, membersOf, unitPathNames } from '@/domain/org'
import { plural } from '@/utils/format'

/** Панель подразделения: путь, численность, руководители, вложенные подразделения и сотрудники. */
const props = defineProps({
  unit: { type: Object, required: true },
  kindOf: { type: Function, required: true },
  unitsById: { type: Map, required: true },
  peopleById: { type: Map, required: true },
  people: { type: Array, required: true },
  units: { type: Array, required: true },
  mine: { type: Boolean, default: false },
  canManage: { type: Boolean, default: false },
})
const emit = defineEmits(['select-unit', 'select-person'])

const PAGE = 60
const search = ref('')
const limit = ref(PAGE)
watch(() => props.unit.id, () => { search.value = ''; limit.value = PAGE })

const kind = computed(() => props.kindOf(props.unit.kind))
const trail = computed(() => {
  const ids = []
  let current = props.unitsById.get(props.unit.parent_id)
  const seen = new Set()
  while (current && !seen.has(current.id)) {
    seen.add(current.id)
    ids.unshift(current)
    current = props.unitsById.get(current.parent_id)
  }
  return ids
})
const heads = computed(() => headsOf(props.unit, props.peopleById))
const children = computed(() => props.units.filter((u) => u.parent_id === props.unit.id)
  .sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0) || a.name.localeCompare(b.name, 'ru')))
const members = computed(() => membersOf(props.unit, props.people))
const filtered = computed(() => filterPeople(members.value, search.value))
const shown = computed(() => filtered.value.slice(0, limit.value))
const homeName = (person) => unitPathNames(props.unitsById, homeOf(person)).at(-1) || ''
</script>

<template>
  <div :style="{ '--kind': kind.color }">
    <header class="p-head">
      <span class="p-kind"><i />{{ kind.label }}</span>
      <h2 class="p-title">{{ unit.name }}</h2>
      <div v-if="unit.code || mine" class="p-tags">
        <span v-if="unit.code" class="p-code" title="Код подразделения">{{ unit.code }}</span>
        <span v-if="mine" class="p-you">Вы здесь</span>
      </div>
      <nav v-if="trail.length" class="p-crumbs" aria-label="Путь в структуре">
        <template v-for="(u, i) in trail" :key="u.id">
          <span v-if="i" class="sep">›</span>
          <button type="button" @click="emit('select-unit', u.id)">{{ u.name }}</button>
        </template>
      </nav>
    </header>

    <div class="p-stats">
      <div class="p-stat" title="Числятся в подразделении, включая руководителя"><b>{{ (unit.employee_count || 0).toLocaleString('ru-RU') }}</b><small>на уровне</small></div>
      <div class="p-stat" title="Вместе с вложенными подразделениями"><b>{{ (unit.branch_employee_count || 0).toLocaleString('ru-RU') }}</b><small>{{ plural(unit.branch_employee_count || 0, PEOPLE_FORMS) }} в ветке</small></div>
      <div class="p-stat"><b>{{ unit.child_count || 0 }}</b><small>{{ plural(unit.child_count || 0, ['вложенное', 'вложенных', 'вложенных']) }}<template v-if="unit.branch_unit_count > unit.child_count">, всего {{ unit.branch_unit_count }}</template></small></div>
    </div>

    <section class="p-section">
      <h3>Руководители <span v-if="heads.length" class="count">{{ heads.length }}</span></h3>
      <div v-if="heads.length" class="p-list">
        <OrgPersonRow v-for="h in heads" :key="h.person.id" :person="h.person" :size="36" @select="emit('select-person', $event)">
          <template #badge><span v-if="h.primary && heads.length > 1" class="p-badge primary" title="Основной руководитель: определяет подчинение сотрудников"><OrgIcon name="star" :size="10" :stroke="2" />основной</span></template>
          <template #sub>{{ h.person.position || 'Руководитель' }}<template v-if="h.visiting && homeName(h.person)"> · числится в «{{ homeName(h.person) }}»</template></template>
          <template #aside><span v-if="h.person.branch_count" class="p-badge" :title="`Подчинённых: ${h.person.report_count} прямых, ${h.person.branch_count} в ветке`"><OrgIcon name="users" :size="11" />{{ h.person.branch_count.toLocaleString('ru-RU') }}</span></template>
        </OrgPersonRow>
      </div>
      <p v-else class="p-note warn">Руководитель не назначен — сотрудники уровня подчиняются руководителю вышестоящего подразделения.</p>
    </section>

    <section v-if="children.length" class="p-section">
      <h3>Вложенные подразделения <span class="count">{{ children.length }}</span></h3>
      <div class="p-list">
        <button v-for="c in children" :key="c.id" type="button" class="p-unit-row" :style="{ '--kind': kindOf(c.kind).color }" @click="emit('select-unit', c.id)">
          <span class="dot" />
          <span class="text"><span class="name">{{ c.name }}</span><small>{{ kindOf(c.kind).label }}<template v-if="c.child_count"> · {{ countText(c.child_count, UNIT_FORMS) }}</template></small></span>
          <span class="aside" :title="`В ветке: ${c.branch_employee_count}`">{{ c.branch_employee_count.toLocaleString('ru-RU') }}</span>
        </button>
      </div>
    </section>

    <section class="p-section">
      <h3>Сотрудники <span class="count">{{ members.length.toLocaleString('ru-RU') }}</span></h3>
      <label v-if="members.length > 6" class="p-search">
        <OrgIcon name="search" :size="14" />
        <input v-model="search" type="search" placeholder="Имя или должность" aria-label="Поиск сотрудника подразделения" @input="limit = PAGE" />
      </label>
      <div v-if="shown.length" class="p-list">
        <OrgPersonRow v-for="p in shown" :key="p.id" :person="p" :sub="p.position || 'Должность не указана'" @select="emit('select-person', $event)" />
      </div>
      <p v-else-if="members.length" class="p-muted">Никого не найдено</p>
      <p v-else class="p-muted">На этом уровне нет сотрудников<template v-if="unit.child_count"> — они во вложенных подразделениях</template>.</p>
      <button v-if="filtered.length > shown.length" type="button" class="btn btn-ghost btn-sm p-more" @click="limit += PAGE">
        Показать ещё {{ Math.min(PAGE, filtered.length - shown.length) }} из {{ filtered.length - shown.length }}
      </button>
    </section>

    <div v-if="canManage" class="p-actions">
      <router-link class="btn btn-sm" :to="{ path: '/admin/departments', query: { dep: unit.id } }">
        <OrgIcon name="edit" :size="14" />Изменить подразделение
      </router-link>
    </div>
  </div>
</template>

<style scoped src="./panel.css"></style>
