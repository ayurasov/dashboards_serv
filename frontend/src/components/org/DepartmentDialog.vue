<script setup>
import { computed, reactive, ref, watch } from 'vue'
import AppModal from '@/components/ui/AppModal.vue'
import OrgIcon from './OrgIcon.vue'
import OrgPicker from './OrgPicker.vue'
import { orgApi } from '@/api/org'
import { kindInfo, parentOptions } from '@/domain/org'

/**
 * Новое подразделение или изменение: название, «Входит в» (недопустимые варианты скрыты —
 * само подразделение, его вложенные и те, где ветка выйдет за предел вложенности), тип, код,
 * порядок среди соседних.
 */
const props = defineProps({
  department: { type: Object, default: null },
  parentId: { type: Number, default: null },
  departments: { type: Array, required: true },
  kinds: { type: Array, required: true },
  maxDepth: { type: Number, required: true },
})
const emit = defineEmits(['close', 'saved'])

const isNew = computed(() => !props.department)
const form = reactive({ name: '', parent_id: null, kind: 'department', code: '', sort_order: 0 })
const orderTouched = ref(false)
const saving = ref(false)
const error = ref('')
const fieldErrors = ref({})

const nextOrder = (parentId) => {
  const siblings = props.departments.filter((d) => (d.parent_id ?? null) === parentId)
  return siblings.length ? Math.max(...siblings.map((d) => d.sort_order || 0)) + 1 : 0
}
function fill() {
  const d = props.department
  const fallbackKind = props.kinds.some((k) => k.value === 'department') ? 'department' : props.kinds[0]?.value || 'department'
  Object.assign(form, d
    ? { name: d.name, parent_id: d.parent_id ?? null, kind: d.kind, code: d.code || '', sort_order: d.sort_order || 0 }
    : { name: '', parent_id: props.parentId, kind: fallbackKind, code: '', sort_order: nextOrder(props.parentId) })
}
fill()
// Новое подразделение — в конец соседей, пока порядок не задан вручную
watch(() => form.parent_id, (id) => { if (isNew.value && !orderTouched.value) form.sort_order = nextOrder(id) })

const parents = computed(() => parentOptions(props.departments, props.department?.id ?? null, props.maxDepth)
  .map((p) => ({ id: p.id, label: p.name, sub: p.path.split(' / ').slice(0, -1).join(' / '), depth: p.level - 1, color: kindInfo(props.kinds, p.kind).color })))
const kindKnown = computed(() => props.kinds.some((k) => k.value === form.kind))
const parentPath = computed(() => props.departments.find((d) => d.id === form.parent_id)?.path || '')
const title = computed(() => (isNew.value ? 'Новое подразделение' : 'Подразделение'))
const subtitle = computed(() => (isNew.value ? (parentPath.value ? `Внутри «${parentPath.value}»` : 'Верхний уровень структуры') : props.department.path))

function body() {
  const values = { name: form.name.trim(), parent_id: form.parent_id, kind: form.kind, code: form.code.trim() || null, sort_order: Number(form.sort_order) || 0 }
  if (isNew.value) return values
  const d = props.department
  const patch = {}
  if (values.name !== d.name) patch.name = values.name
  if (values.parent_id !== (d.parent_id ?? null)) patch.parent_id = values.parent_id
  if (values.kind !== d.kind) patch.kind = values.kind
  if (values.code !== (d.code || null)) patch.code = values.code
  if (values.sort_order !== (d.sort_order || 0)) patch.sort_order = values.sort_order
  return patch
}
const FIELD_BY_CODE = { department_name_taken: 'name', department_code_taken: 'code', org_cycle: 'parent_id', org_too_deep: 'parent_id' }

async function save() {
  error.value = ''
  fieldErrors.value = {}
  if (!form.name.trim()) {
    fieldErrors.value = { name: 'Укажите название' }
    return
  }
  const payload = body()
  if (!isNew.value && !Object.keys(payload).length) {
    emit('close')
    return
  }
  saving.value = true
  try {
    const saved = isNew.value ? await orgApi.createDepartment(payload) : await orgApi.updateDepartment(props.department.id, payload)
    emit('saved', saved)
  } catch (e) {
    error.value = e.message
    const field = FIELD_BY_CODE[e.code] || Object.keys(e.fields || {})[0]
    if (field) fieldErrors.value = { [field]: true }
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <AppModal :title="title" :subtitle="subtitle" :width="520" @close="emit('close')">
    <form id="department-form" class="stack form" novalidate @submit.prevent="save">
      <label class="field"><span>Название</span>
        <input v-model="form.name" class="input" :class="{ invalid: fieldErrors.name }" maxlength="200" placeholder="Например, Отдел продаж"
               autofocus data-testid="department-name" />
        <span v-if="typeof fieldErrors.name === 'string'" class="error">{{ fieldErrors.name }}</span>
      </label>
      <div class="field"><span>Входит в</span>
        <OrgPicker v-model="form.parent_id" :items="parents" null-label="Верхний уровень" search-placeholder="Найти подразделение"
                   label="Входит в" :invalid="!!fieldErrors.parent_id" data-testid="department-parent" />
        <span class="help">Нельзя вложить подразделение в само себя, во вложенное или глубже {{ maxDepth }} уровней — такие варианты скрыты.</span>
      </div>
      <div class="form-grid">
        <label class="field"><span>Тип</span>
          <select v-model="form.kind" class="select" data-testid="department-kind">
            <option v-for="k in kinds" :key="k.value" :value="k.value">{{ k.label }}</option>
            <option v-if="!kindKnown" :value="form.kind">{{ form.kind }} (нет в настройках)</option>
          </select>
        </label>
        <label class="field"><span>Код <em class="opt">необязательно</em></span>
          <input v-model="form.code" class="input mono" :class="{ invalid: fieldErrors.code }" maxlength="50" placeholder="SALES" spellcheck="false" />
        </label>
      </div>
      <label class="field order"><span>Порядок среди соседних</span>
        <input v-model.number="form.sort_order" class="input num" type="number" min="-100000" max="100000" step="1" @input="orderTouched = true" />
        <span class="help">Меньшее число — левее на оргсхеме и выше в списке; при равном — по алфавиту.</span>
      </label>
    </form>
    <p v-if="error" class="form-error" role="alert"><OrgIcon name="alert" :size="14" />{{ error }}</p>
    <template #footer>
      <button class="btn" type="button" @click="emit('close')">Отмена</button>
      <button class="btn btn-primary" type="submit" form="department-form" :disabled="saving" data-testid="department-save">
        {{ saving ? 'Сохранение…' : isNew ? 'Добавить' : 'Сохранить' }}
      </button>
    </template>
  </AppModal>
</template>

<style scoped>
.form { gap: 16px; }
.opt { font-style: normal; font-weight: 400; color: var(--muted); margin-left: 4px; }
.mono { font-family: var(--font-mono); letter-spacing: .03em; }
.mono::placeholder { font-family: var(--font-sans); letter-spacing: 0; }
.order .input { width: 140px; }
.form-error { display: flex; align-items: flex-start; gap: 6px; margin-top: 14px; font-size: var(--fs-sm); color: var(--light-red); line-height: 1.45; }
.form-error :deep(svg) { margin-top: 2px; }
</style>
