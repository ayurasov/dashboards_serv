<script setup>
import { computed, reactive, ref, watch } from 'vue'
import OrgIcon from './OrgIcon.vue'
import OrgPicker from './OrgPicker.vue'
import SegmentedControl from '@/components/ui/SegmentedControl.vue'
import { orgApi } from '@/api/org'
import { toastOk } from '@/composables/useToast'
import { formatDateTime, formatRelative } from '@/utils/format'
import { historyChanges } from '@/domain/org'

/**
 * Подчинение сотрудника (для ведущих структуру): подразделение, руководитель — по структуре,
 * явно или «первое лицо», должность; ниже — история изменений структуры по сотруднику.
 */
const props = defineProps({
  card: { type: Object, required: true },
  unitItems: { type: Array, required: true },
  people: { type: Array, required: true },
})
const emit = defineEmits(['saved'])

const MODES = [
  { value: 'structure', label: 'По структуре' },
  { value: 'explicit', label: 'Назначить' },
  { value: 'top', label: 'Первое лицо' },
]
const form = reactive({ position: '', department_id: null, mode: 'structure', manager_id: null })
const saving = ref(false)
const error = ref('')
const fieldError = ref('')

function modeOf(card) {
  return card.reports_to_none ? 'top' : card.manager_id ? 'explicit' : 'structure'
}
function fill() {
  Object.assign(form, {
    position: props.card.position || '',
    department_id: props.card.department_id ?? null,
    mode: modeOf(props.card),
    manager_id: props.card.manager_id ?? null,
  })
  error.value = ''
  fieldError.value = ''
}
watch(() => props.card, fill, { immediate: true })

const managerItems = computed(() => props.people
  .filter((p) => p.id !== props.card.id && p.is_active !== false)
  .map((p) => ({ id: p.id, label: p.full_name, sub: p.position || '', person: p })))

const body = computed(() => {
  const patch = {}
  if ((form.position.trim() || null) !== (props.card.position || null)) patch.position = form.position.trim()
  if (form.department_id !== (props.card.department_id ?? null)) patch.department_id = form.department_id
  const mode = modeOf(props.card)
  if (form.mode !== mode || (form.mode === 'explicit' && form.manager_id !== props.card.manager_id)) {
    if (form.mode === 'top') patch.reports_to_none = true
    else if (form.mode === 'explicit') patch.manager_id = form.manager_id
    else Object.assign(patch, { manager_id: null, reports_to_none: false })
  }
  return patch
})
const dirty = computed(() => Object.keys(body.value).length > 0)
const invalid = computed(() => form.mode === 'explicit' && !form.manager_id)

async function save() {
  if (!dirty.value || invalid.value) return
  saving.value = true
  error.value = ''
  fieldError.value = ''
  try {
    const card = await orgApi.updatePerson(props.card.id, body.value)
    toastOk('Подчинение сотрудника изменено')
    emit('saved', card)
    loadHistory()
  } catch (e) {
    error.value = e.message
    fieldError.value = Object.keys(e.fields || {})[0] || ''
  } finally {
    saving.value = false
  }
}

// ---------------------------------------------------------------- история
const history = ref([])
const historyLoading = ref(false)
let seq = 0
async function loadHistory() {
  const id = ++seq
  historyLoading.value = true
  try {
    const rows = await orgApi.history({ entity_type: 'user', entity_id: props.card.id, limit: 20 })
    if (id === seq) history.value = rows
  } catch {
    if (id === seq) history.value = []
  } finally {
    if (id === seq) historyLoading.value = false
  }
}
watch(() => props.card.id, loadHistory, { immediate: true })
</script>

<template>
  <section class="editor" data-testid="org-person-editor">
    <h3 class="title"><OrgIcon name="edit" :size="13" />Подчинение и должность</h3>
    <form class="stack" novalidate @submit.prevent="save">
      <label class="field"><span>Должность</span>
        <input v-model="form.position" class="input" maxlength="200" placeholder="Например, Ведущий инженер" :class="{ invalid: fieldError === 'position' }" />
      </label>
      <div class="field"><span>Подразделение</span>
        <OrgPicker v-model="form.department_id" :items="unitItems" null-label="Без подразделения" search-placeholder="Найти подразделение" label="Подразделение"
                   :invalid="fieldError === 'department_id'" />
      </div>
      <div class="field"><span>Руководитель</span>
        <SegmentedControl v-model="form.mode" :options="MODES" size="sm" class="modes" />
        <OrgPicker v-if="form.mode === 'explicit'" v-model="form.manager_id" :items="managerItems" placeholder="Выберите руководителя"
                   search-placeholder="Имя или должность" label="Руководитель" :invalid="fieldError === 'manager_id' || invalid" />
        <span class="help">
          <template v-if="form.mode === 'structure'">Руководитель определяется по подразделению<template v-if="card.structure_manager">: сейчас {{ card.structure_manager.full_name }}</template>.</template>
          <template v-else-if="form.mode === 'explicit'">Явный руководитель важнее структуры — например, для сотрудника, работающего на другое подразделение.</template>
          <template v-else>Первое лицо никому не подчиняется — даже внутри подразделения.</template>
        </span>
      </div>
      <p v-if="error" class="form-error" role="alert"><OrgIcon name="alert" :size="14" />{{ error }}</p>
      <div class="actions">
        <button class="btn btn-ghost btn-sm" type="button" :disabled="!dirty || saving" @click="fill">Отменить</button>
        <button class="btn btn-primary btn-sm" type="submit" :disabled="!dirty || invalid || saving">{{ saving ? 'Сохранение…' : 'Сохранить' }}</button>
      </div>
    </form>

    <h3 class="title history-title"><OrgIcon name="history" :size="13" />История в структуре</h3>
    <div v-if="historyLoading && !history.length" class="skeleton hist-skel" />
    <ol v-else-if="history.length" class="history">
      <li v-for="h in history" :key="h.id">
        <div class="when"><span :title="formatDateTime(h.occurred_at)">{{ formatRelative(h.occurred_at) }}</span> · {{ h.username }}</div>
        <div class="what">{{ h.summary }}</div>
        <ul v-if="historyChanges(h).length" class="changes">
          <li v-for="c in historyChanges(h)" :key="c.key"><span class="lbl">{{ c.label }}:</span> <s>{{ c.old }}</s> → {{ c.new }}</li>
        </ul>
      </li>
    </ol>
    <p v-else class="muted small">Изменений пока не было.</p>
  </section>
</template>

<style scoped>
.editor { margin-top: 22px; padding-top: 18px; border-top: 1px solid var(--border); }
.title { display: flex; align-items: center; gap: 6px; margin-bottom: 12px; font-size: var(--fs-xs); font-weight: 650; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); }
.stack { gap: 14px; }
.modes { align-self: flex-start; }
.field .help { line-height: 1.4; }
.form-error { display: flex; align-items: flex-start; gap: 6px; font-size: var(--fs-sm); color: var(--light-red); line-height: 1.4; }
.form-error :deep(svg) { margin-top: 2px; }
.actions { display: flex; justify-content: flex-end; gap: 8px; }
.history-title { margin-top: 24px; }
.hist-skel { height: 60px; }
.history { list-style: none; margin: 0; padding: 0 0 0 14px; border-left: 2px solid var(--border); display: flex; flex-direction: column; gap: 12px; }
.history > li { position: relative; font-size: var(--fs-sm); }
.history > li::before { content: ''; position: absolute; left: -19px; top: 6px; width: 8px; height: 8px; border-radius: 50%; background: var(--surface); border: 2px solid var(--border-strong); }
.when { font-size: var(--fs-xs); color: var(--muted); }
.what { margin-top: 1px; color: var(--text); }
.changes { margin: 4px 0 0; padding: 0; list-style: none; font-size: var(--fs-xs); color: var(--text-2); }
.changes .lbl { color: var(--muted); }
.changes s { color: var(--muted); }
.small { font-size: var(--fs-sm); }
</style>
