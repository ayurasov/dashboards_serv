<script setup>
import { computed } from 'vue'
import OrgAvatar from './OrgAvatar.vue'
import OrgIcon from './OrgIcon.vue'
import OrgPersonEditor from './OrgPersonEditor.vue'
import OrgPersonRow from './OrgPersonRow.vue'
import { MANAGER_SOURCE_LABELS, PEOPLE_FORMS, homeOf } from '@/domain/org'
import { plural } from '@/utils/format'

/**
 * Панель сотрудника: путь в структуре, руководитель и откуда он взялся, цепочка подчинения,
 * прямые подчинённые, «Руководит». Ведущим структуру — изменение подчинения и история.
 */
const props = defineProps({
  person: { type: Object, required: true },
  card: { type: Object, default: null },
  loading: { type: Boolean, default: false },
  kindOf: { type: Function, required: true },
  unitsById: { type: Map, required: true },
  peopleById: { type: Map, required: true },
  unitItems: { type: Array, default: () => [] },
  people: { type: Array, default: () => [] },
  me: { type: Boolean, default: false },
  canManage: { type: Boolean, default: false },
})
const emit = defineEmits(['select-unit', 'select-person', 'saved'])

const SOURCE_TONES = { explicit: 'blue', structure: '', top: 'dark', none: '' }
const home = computed(() => props.unitsById.get(homeOf(props.person)) || null)
const path = computed(() => props.card?.home_unit_path || [])
// Цепочка сверху вниз: первое лицо → … → непосредственный руководитель → сотрудник
const chain = computed(() => [...(props.card?.chain || [])].reverse())
const full = (ref) => props.peopleById.get(ref.id) || ref
const reports = computed(() => props.card?.direct_reports || [])
const headOf = computed(() => props.card?.head_of || [])
const reportCount = computed(() => props.person.report_count || 0)
const branchCount = computed(() => props.card?.subordinates_count ?? props.person.branch_count ?? 0)
</script>

<template>
  <div>
    <header class="p-head person-head">
      <OrgAvatar :person="person" :size="56" ring />
      <div class="who">
        <h2 class="p-title">{{ person.full_name }}</h2>
        <p class="pos">{{ person.position || 'Должность не указана' }}</p>
        <div v-if="me || person.is_active === false" class="p-tags">
          <span v-if="me" class="p-you">Это вы</span>
          <span v-if="person.is_active === false" class="badge badge-gray">Отключён</span>
        </div>
      </div>
    </header>
    <nav v-if="path.length" class="p-crumbs" aria-label="Подразделение">
      <OrgIcon name="building" :size="13" />
      <template v-for="(u, i) in path" :key="u.id">
        <span v-if="i" class="sep">›</span>
        <button type="button" @click="emit('select-unit', u.id)">{{ u.name }}</button>
      </template>
    </nav>
    <p v-else-if="card && !home" class="p-crumbs">Вне структуры — подразделение не указано</p>

    <div class="p-stats two">
      <div class="p-stat"><b>{{ reportCount }}</b><small>{{ plural(reportCount, ['прямой подчинённый', 'прямых подчинённых', 'прямых подчинённых']) }}</small></div>
      <div class="p-stat"><b>{{ branchCount.toLocaleString('ru-RU') }}</b><small>{{ plural(branchCount, PEOPLE_FORMS) }} в ветке</small></div>
    </div>

    <template v-if="card">
      <section class="p-section">
        <h3>Руководитель</h3>
        <div v-if="card.manager" class="p-list">
          <OrgPersonRow :person="full(card.manager)" :size="36" :sub="card.manager.position || ''" @select="emit('select-person', $event)">
            <template #aside><span class="p-badge" :class="SOURCE_TONES[card.manager_source]">{{ MANAGER_SOURCE_LABELS[card.manager_source] }}</span></template>
          </OrgPersonRow>
        </div>
        <p v-else-if="card.manager_source === 'top'" class="p-note"><span class="p-badge dark">первое лицо</span> Никому не подчиняется.</p>
        <p v-else class="p-note">Руководитель не определён: {{ home ? 'у подразделения и вышестоящих нет руководителя' : 'сотрудник не входит в подразделение' }}.</p>
        <p v-if="card.manager_source === 'explicit' && card.structure_manager && card.structure_manager.id !== card.manager?.id" class="hint">
          По структуре руководителем был бы {{ card.structure_manager.full_name }}.
        </p>
      </section>

      <section v-if="chain.length > 1" class="p-section">
        <h3>Цепочка подчинения</h3>
        <ol class="chain">
          <li v-for="c in chain" :key="c.id">
            <button type="button" @click="emit('select-person', c.id)"><span class="nm">{{ c.full_name }}</span><small v-if="c.position">{{ c.position }}</small></button>
          </li>
          <li class="self"><span class="nm">{{ person.full_name }}</span></li>
        </ol>
      </section>

      <section class="p-section">
        <h3>Прямые подчинённые <span v-if="reports.length" class="count">{{ reports.length }}</span></h3>
        <div v-if="reports.length" class="p-list">
          <OrgPersonRow v-for="r in reports" :key="r.id" :person="full(r)" :sub="r.position || 'Должность не указана'" @select="emit('select-person', $event)">
            <template #aside><span v-if="full(r).branch_count" class="p-badge" :title="`В ветке: ${full(r).branch_count}`"><OrgIcon name="users" :size="11" />{{ full(r).branch_count }}</span></template>
          </OrgPersonRow>
        </div>
        <p v-else class="p-muted">Нет подчинённых.</p>
      </section>

      <section v-if="headOf.length" class="p-section">
        <h3>Руководит <span class="count">{{ headOf.length }}</span></h3>
        <div class="p-list">
          <button v-for="u in headOf" :key="u.id" type="button" class="p-unit-row" :style="{ '--kind': kindOf(u.kind).color }" @click="emit('select-unit', u.id)">
            <span class="dot" />
            <span class="text">
              <span class="name">{{ u.name }}<span v-if="u.primary && (unitsById.get(u.id)?.head_ids || []).length > 1" class="p-badge primary"><OrgIcon name="star" :size="10" :stroke="2" />основной</span></span>
              <small :title="u.path">{{ kindOf(u.kind).label }} · {{ u.path }}</small>
            </span>
          </button>
        </div>
      </section>

      <OrgPersonEditor v-if="canManage" :card="card" :unit-items="unitItems" :people="people" @saved="emit('saved', $event)" />
    </template>
    <div v-else-if="loading" class="loading">
      <div v-for="i in 4" :key="i" class="skeleton" />
    </div>
  </div>
</template>

<style scoped src="./panel.css"></style>
<style scoped>
.person-head { display: flex; align-items: center; gap: 14px; }
.who { min-width: 0; }
.who .p-title { margin-top: 0; }
.pos { margin-top: 2px; font-size: var(--fs-sm); color: var(--text-2); }
.p-crumbs :deep(svg) { color: var(--faint); margin-right: 2px; }
.hint { margin-top: 6px; font-size: var(--fs-xs); color: var(--muted); }
.chain { list-style: none; margin: 0; padding: 0; position: relative; }
.chain::before { content: ''; position: absolute; left: 7px; top: 12px; bottom: 12px; width: 2px; background: var(--border); border-radius: 2px; }
.chain li { position: relative; padding-left: 26px; }
.chain li::before { content: ''; position: absolute; left: 2px; top: 50%; width: 12px; height: 12px; margin-top: -6px; border-radius: 50%; background: var(--surface); border: 2px solid var(--border-strong); box-sizing: border-box; }
.chain li.self::before { background: var(--accent); border-color: var(--accent); }
.chain button { display: flex; flex-direction: column; width: 100%; padding: 6px 8px; border: 0; border-radius: 8px; background: transparent; text-align: left; color: var(--text); cursor: pointer; line-height: 1.3; }
.chain button:hover { background: var(--surface-3); }
.chain .nm { font-size: var(--fs-sm); font-weight: 560; }
.chain small { font-size: var(--fs-xs); color: var(--muted); }
.chain .self { padding-top: 6px; padding-bottom: 6px; }
.chain .self .nm { display: block; padding: 0 8px; font-weight: 680; }
.loading { display: flex; flex-direction: column; gap: 10px; margin-top: 20px; }
.loading .skeleton { height: 44px; }
</style>
