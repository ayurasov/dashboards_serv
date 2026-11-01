<script setup>
import { computed, ref } from 'vue'
import AppModal from '@/components/ui/AppModal.vue'
import OrgAvatar from './OrgAvatar.vue'
import OrgIcon from './OrgIcon.vue'
import { orgApi } from '@/api/org'
import { filterPeople, homeOf } from '@/domain/org'

/**
 * Руководители подразделения: поиск, отметки, основной руководитель. Основной — непосредственный
 * руководитель сотрудников уровня; единственный руководитель — основной сам.
 */
const props = defineProps({
  department: { type: Object, required: true },
  people: { type: Array, required: true },
  unitsById: { type: Map, required: true },
})
const emit = defineEmits(['close', 'saved'])

const LIMIT = 50
const byId = computed(() => new Map(props.people.map((p) => [p.id, p])))
const selected = ref((props.department.heads || []).map((h) => h.user_id))
const primary = ref(props.department.primary_head_id ?? (props.department.heads || []).find((h) => h.is_primary)?.user_id ?? null)
const query = ref('')
const saving = ref(false)
const error = ref('')

const person = (id) => byId.value.get(id) || (props.department.heads || []).map((h) => ({ id: h.user_id, full_name: h.full_name, position: h.position, is_active: h.is_active })).find((h) => h.id === id)
const chosen = computed(() => selected.value.map(person).filter(Boolean))
const candidates = computed(() => {
  const list = props.people.filter((p) => p.is_active !== false || selected.value.includes(p.id))
  return filterPeople(list, query.value)
    .sort((a, b) => Number(selected.value.includes(b.id)) - Number(selected.value.includes(a.id)) || a.full_name.localeCompare(b.full_name, 'ru'))
})
const shown = computed(() => candidates.value.slice(0, LIMIT))
const effectivePrimary = computed(() => (selected.value.length === 1 ? selected.value[0] : selected.value.includes(primary.value) ? primary.value : null))

function toggle(id) {
  if (selected.value.includes(id)) {
    selected.value = selected.value.filter((x) => x !== id)
    if (primary.value === id) primary.value = selected.value[0] ?? null
  } else {
    selected.value = [...selected.value, id]
    if (!selected.value.includes(primary.value)) primary.value = id
  }
}
const unitName = (p) => props.unitsById.get(homeOf(p))?.name || ''

async function save() {
  error.value = ''
  saving.value = true
  try {
    const saved = await orgApi.setHeads(props.department.id, { user_ids: selected.value, primary_id: effectivePrimary.value })
    emit('saved', saved)
  } catch (e) {
    error.value = e.message
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <AppModal title="Руководители" :subtitle="department.path || department.name" :width="580" @close="emit('close')">
    <p class="lead">Руководитель — непосредственный руководитель сотрудников подразделения и подчиняется руководителю вышестоящего. Если руководителей несколько, отметьте основного: он определяет подчинение.</p>

    <div class="chosen" aria-live="polite">
      <span v-if="!chosen.length" class="none"><OrgIcon name="alert" :size="14" />Руководитель не назначен — сотрудники будут подчиняться руководителю вышестоящего уровня</span>
      <span v-for="p in chosen" :key="p.id" class="chosen-chip" :class="{ primary: p.id === effectivePrimary, off: p.is_active === false }">
        <OrgIcon v-if="p.id === effectivePrimary && chosen.length > 1" name="star" :size="12" :stroke="2" />
        {{ p.full_name }}
        <button type="button" :aria-label="`Убрать ${p.full_name}`" @click="toggle(p.id)"><OrgIcon name="x" :size="12" :stroke="2.2" /></button>
      </span>
    </div>

    <label class="search">
      <OrgIcon name="search" :size="15" />
      <input v-model="query" type="search" placeholder="Имя, должность или email" aria-label="Поиск сотрудника" data-testid="heads-search" />
    </label>

    <div class="options scroll-thin" role="group" aria-label="Сотрудники">
      <div v-for="p in shown" :key="p.id" class="option" :class="{ on: selected.includes(p.id) }">
        <label class="pick">
          <input type="checkbox" :checked="selected.includes(p.id)" :aria-label="p.full_name" @change="toggle(p.id)" />
          <OrgAvatar :person="p" :size="30" />
          <span class="text">
            <span class="name">{{ p.full_name }}<span v-if="p.is_active === false" class="badge badge-gray">отключён</span></span>
            <small>{{ [p.position, unitName(p)].filter(Boolean).join(' · ') || 'Без должности и подразделения' }}</small>
          </span>
        </label>
        <label v-if="selected.includes(p.id) && selected.length > 1" class="primary-radio" :class="{ on: effectivePrimary === p.id }" title="Основной руководитель">
          <input v-model="primary" type="radio" name="primary-head" :value="p.id" />основной
        </label>
      </div>
      <p v-if="!shown.length" class="empty">Никого не найдено</p>
      <p v-else-if="candidates.length > shown.length" class="empty">Показаны первые {{ LIMIT }} из {{ candidates.length }} — уточните поиск</p>
    </div>
    <p v-if="error" class="form-error" role="alert"><OrgIcon name="alert" :size="14" />{{ error }}</p>

    <template #footer>
      <span class="count">Выбрано: {{ selected.length }}</span>
      <span class="spacer" />
      <button class="btn" type="button" @click="emit('close')">Отмена</button>
      <button class="btn btn-primary" type="button" :disabled="saving" data-testid="heads-save" @click="save">{{ saving ? 'Сохранение…' : 'Сохранить' }}</button>
    </template>
  </AppModal>
</template>

<style scoped>
.lead { font-size: var(--fs-sm); color: var(--text-2); line-height: 1.5; }
.chosen { display: flex; flex-wrap: wrap; gap: 6px; margin: 14px 0 12px; min-height: 30px; align-items: center; }
.none { display: inline-flex; align-items: center; gap: 6px; font-size: var(--fs-sm); color: color-mix(in srgb, var(--light-yellow) 75%, var(--text)); }
.chosen-chip { display: inline-flex; align-items: center; gap: 5px; height: 30px; padding: 0 4px 0 11px; border-radius: var(--radius-pill); background: var(--surface-3); border: 1px solid var(--border); font-size: var(--fs-sm); font-weight: 560; }
.chosen-chip.primary { background: color-mix(in srgb, var(--light-yellow) 14%, var(--surface)); border-color: color-mix(in srgb, var(--light-yellow) 45%, var(--border)); }
.chosen-chip.primary :deep(svg:first-child) { color: color-mix(in srgb, var(--light-yellow) 85%, var(--text)); }
.chosen-chip.off { color: var(--muted); text-decoration: line-through; }
.chosen-chip button { width: 22px; height: 22px; display: grid; place-items: center; border: 0; border-radius: 50%; background: transparent; color: var(--muted); cursor: pointer; }
.chosen-chip button:hover { background: var(--surface); color: var(--text); }
.search { display: flex; align-items: center; gap: 8px; height: 36px; padding: 0 11px; border: 1px solid var(--border-strong); border-radius: var(--radius); color: var(--muted); }
.search:focus-within { border-color: var(--accent); box-shadow: 0 0 0 3px var(--focus); }
.search input { flex: 1; min-width: 0; border: 0; outline: 0; background: transparent; color: var(--text); }
.options { margin-top: 8px; max-height: 330px; overflow-y: auto; border: 1px solid var(--border); border-radius: 12px; }
.option { display: flex; align-items: center; gap: 8px; padding: 0 12px 0 0; border-bottom: 1px solid var(--border); }
.option:last-of-type { border-bottom: 0; }
.option.on { background: color-mix(in srgb, var(--accent) 6%, transparent); }
.pick { display: flex; align-items: center; gap: 10px; flex: 1; min-width: 0; padding: 8px 0 8px 12px; cursor: pointer; }
.pick input { width: 16px; height: 16px; accent-color: var(--brand); flex: 0 0 auto; }
.text { display: flex; flex-direction: column; min-width: 0; line-height: 1.3; }
.name { display: flex; align-items: center; gap: 6px; font-size: var(--fs-sm); font-weight: 600; }
.text small { font-size: var(--fs-xs); color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.primary-radio { flex: 0 0 auto; display: inline-flex; align-items: center; gap: 5px; height: 26px; padding: 0 9px; border-radius: var(--radius-pill); border: 1px solid var(--border); font-size: var(--fs-xs); color: var(--muted); cursor: pointer; }
.primary-radio input { accent-color: var(--light-yellow); margin: 0; }
.primary-radio.on { border-color: color-mix(in srgb, var(--light-yellow) 50%, var(--border)); color: color-mix(in srgb, var(--light-yellow) 80%, var(--text)); background: color-mix(in srgb, var(--light-yellow) 10%, transparent); font-weight: 600; }
.empty { padding: 12px; text-align: center; font-size: var(--fs-xs); color: var(--muted); }
.count { font-size: var(--fs-sm); color: var(--muted); }
.form-error { display: flex; align-items: flex-start; gap: 6px; margin-top: 12px; font-size: var(--fs-sm); color: var(--light-red); }
</style>
