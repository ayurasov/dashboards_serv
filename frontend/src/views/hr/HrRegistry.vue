<script setup>
import { computed, reactive, ref, watch } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import AppModal from '@/components/ui/AppModal.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import FilterBar from '@/components/ui/FilterBar.vue'
import KpiCard from '@/components/ui/KpiCard.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import PdfButton from '@/components/ui/PdfButton.vue'
import { hrApi } from '@/api/services'
import { useAsync } from '@/composables/useAsync'
import { useQueryState } from '@/composables/useQueryState'
import { confirm } from '@/composables/useConfirm'
import { toastOk } from '@/composables/useToast'
import { useAuthStore } from '@/stores/auth'
import { ORG_SCOPE_LABELS } from '@/domain/access'
import { formatDate, monthLabel, plural } from '@/utils/format'

const auth = useAuthStore()
const canEdit = computed(() => auth.can('hr', 'editor'))
const { state: f, reset, isDefault } = useQueryState({ month: '', event_type: '', department: '', search: '', sort: 'event_date', dir: 'desc' })

const months = useAsync(() => hrApi.months())
const departments = useAsync(() => hrApi.departments())
const params = computed(() => ({ month: f.month, event_type: f.event_type, department: f.department, search: f.search.trim() }))
const { data, loading, reload } = useAsync(() => hrApi.events(params.value), { immediate: false })
let timer
watch(params, () => { clearTimeout(timer); timer = setTimeout(reload, f.search ? 250 : 0) }, { immediate: true, deep: true })

const COLUMNS = [
  { key: 'event_date', label: 'Дата' }, { key: 'event_type', label: 'Событие' }, { key: 'full_name', label: 'ФИО' },
  { key: 'position', label: 'Должность' }, { key: 'department', label: 'Подразделение' }, { key: 'employment_type', label: 'Тип занятости' },
]
function sortBy(key) {
  if (f.sort === key) f.dir = f.dir === 'asc' ? 'desc' : 'asc'
  else { f.sort = key; f.dir = 'asc' }
}
const rows = computed(() => {
  const list = [...(data.value || [])]
  const dir = f.dir === 'asc' ? 1 : -1
  return list.sort((a, b) => String(a[f.sort] ?? '').localeCompare(String(b[f.sort] ?? ''), 'ru') * dir)
})
const hired = computed(() => rows.value.filter((r) => r.event_type === 'hired').length)
const summary = computed(() => `${rows.value.length} ${plural(rows.value.length, ['запись', 'записи', 'записей'])}`)

// ---------- форма ----------
const editing = ref(null)
const form = reactive({ month: '', event_type: 'hired', event_date: '', full_name: '', position: '', department: '', employment_type: '', reason: '' })
const formError = ref('')
const fieldErrors = ref({})
const saving = ref(false)

function open(row = null) {
  formError.value = ''
  fieldErrors.value = {}
  const lastMonth = months.data.value?.at(-1)?.key || ''
  editing.value = row || {}
  Object.assign(form, row
    ? { ...row, month: row.month_key }
    : { month: f.month || lastMonth, event_type: f.event_type || 'hired', event_date: '', full_name: '', position: '', department: f.department, employment_type: '', reason: '' })
  if (!row && form.month && !form.event_date) form.event_date = `${form.month}-01`
}
async function save() {
  saving.value = true
  formError.value = ''
  fieldErrors.value = {}
  const body = { event_type: form.event_type, event_date: form.event_date, full_name: form.full_name, position: form.position,
    department: form.department, employment_type: form.employment_type, reason: form.reason }
  try {
    if (editing.value.id) await hrApi.updateEvent(editing.value.id, body)
    else await hrApi.addEvent(form.month, body)
    toastOk(editing.value.id ? 'Запись обновлена' : 'Запись добавлена')
    editing.value = null
    reload()
    months.reload()
  } catch (e) {
    formError.value = e.message
    fieldErrors.value = e.fields || {}
  } finally {
    saving.value = false
  }
}
async function remove(row) {
  if (!await confirm({ title: 'Удалить запись?', message: `${row.full_name}, ${formatDate(row.event_date)}`, confirmText: 'Удалить', danger: true })) return
  await hrApi.deleteEvent(row.id)
  toastOk('Запись удалена')
  reload()
}
watch(() => form.month, (m, old) => {
  if (!editing.value?.id && m && (!form.event_date || form.event_date.slice(0, 7) === old)) form.event_date = `${m}-01`
})
</script>

<template>
  <div class="page">
    <PageHeader title="Приёмы и увольнения" description="Реестр кадровых событий по месяцам">
      <button v-if="auth.canExport" class="btn" type="button" @click="hrApi.exportEvents(params)"><AppIcon name="sheet" :size="15" />Excel</button>
      <PdfButton report="hr/registry" :params="params" />
      <button v-if="canEdit" class="btn btn-primary" type="button" @click="open()"><AppIcon name="plus" :size="15" />Добавить</button>
    </PageHeader>

    <p v-if="auth.departmentScoped('hr')" class="scope muted"><AppIcon name="info" :size="14" />Показаны только записи подразделений вашей области: {{ ORG_SCOPE_LABELS[auth.scopeFor('hr')].toLowerCase() }}</p>

    <FilterBar :summary="summary" :resettable="!isDefault()" @reset="reset">
      <label class="field"><span>Месяц</span>
        <select v-model="f.month" class="select"><option value="">Все месяцы</option><option v-for="m in months.data.value || []" :key="m.key" :value="m.key">{{ m.label }}</option></select>
      </label>
      <label class="field"><span>Событие</span>
        <select v-model="f.event_type" class="select"><option value="">Все</option><option value="hired">Приёмы</option><option value="fired">Увольнения</option></select>
      </label>
      <label class="field"><span>Подразделение</span>
        <select v-model="f.department" class="select"><option value="">Все</option><option v-for="d in departments.data.value || []" :key="d" :value="d">{{ d }}</option></select>
      </label>
      <label class="search"><AppIcon name="search" :size="14" /><input v-model="f.search" type="search" placeholder="ФИО или должность" /></label>
    </FilterBar>

    <div class="grid grid-kpi">
      <KpiCard label="Записей" :value="rows.length" />
      <KpiCard label="Приёмов" :value="hired" unit="чел." />
      <KpiCard label="Увольнений" :value="rows.length - hired" unit="чел." />
      <KpiCard label="Чистый прирост" :value="hired * 2 - rows.length" unit="чел." />
    </div>

    <section class="card">
      <div class="table-wrap">
        <table class="table">
          <thead>
            <tr>
              <th v-for="c in COLUMNS" :key="c.key" class="sortable" @click="sortBy(c.key)">
                {{ c.label }}<AppIcon v-if="f.sort === c.key" :name="f.dir === 'asc' ? 'arrow-up' : 'arrow-down'" :size="11" class="sort-icon" />
              </th>
              <th v-if="canEdit" />
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in rows" :key="r.id" :class="{ clickable: canEdit }" @click="canEdit && open(r)">
              <td class="nowrap num">{{ formatDate(r.event_date) }}</td>
              <td><span class="badge" :class="r.event_type === 'hired' ? 'badge-green' : 'badge-red'">{{ r.event_type === 'hired' ? 'Приём' : 'Увольнение' }}</span></td>
              <td class="strong">{{ r.full_name }}</td>
              <td class="muted">{{ r.position || '—' }}</td>
              <td>{{ r.department || '—' }}</td>
              <td class="muted">{{ r.employment_type || '—' }}</td>
              <td v-if="canEdit" class="num" @click.stop>
                <button class="btn btn-icon btn-sm btn-ghost" type="button" title="Удалить" @click="remove(r)"><AppIcon name="trash" :size="14" /></button>
              </td>
            </tr>
          </tbody>
        </table>
        <EmptyState v-if="!loading && !rows.length" compact icon="search" title="Ничего не найдено" text="Измените фильтры или добавьте запись." />
        <div v-if="loading && !data" class="skeleton" style="height: 240px; margin: 12px" />
      </div>
    </section>

    <AppModal v-if="editing" :title="editing.id ? 'Запись реестра' : 'Новая запись'" @close="editing = null">
      <form id="event-form" class="form-grid" @submit.prevent="save">
        <label class="field"><span>Месяц</span>
          <select v-model="form.month" class="select" :disabled="!!editing.id" required>
            <option v-for="m in months.data.value || []" :key="m.key" :value="m.key">{{ m.label }}</option>
          </select>
          <span v-if="!months.data.value?.length" class="help">Сначала добавьте месяц в разделе «Ввод данных»</span>
        </label>
        <label class="field"><span>Событие</span>
          <select v-model="form.event_type" class="select"><option value="hired">Приём</option><option value="fired">Увольнение</option></select>
        </label>
        <label class="field full"><span>ФИО</span><input v-model="form.full_name" class="input" :class="{ invalid: fieldErrors.full_name }" required /></label>
        <label class="field"><span>Дата</span>
          <input v-model="form.event_date" class="input" :class="{ invalid: fieldErrors.event_date }" type="date" required />
          <span v-if="fieldErrors.event_date" class="error">{{ fieldErrors.event_date }} ({{ monthLabel(form.month) }})</span>
        </label>
        <label class="field"><span>Тип занятости</span><input v-model="form.employment_type" class="input" list="emp-types" placeholder="ТД, ГПХ, самозанятый" /></label>
        <label class="field full"><span>Должность</span><input v-model="form.position" class="input" /></label>
        <label class="field full"><span>Подразделение</span><input v-model="form.department" class="input" list="departments" /></label>
        <label v-if="form.event_type === 'fired'" class="field full"><span>Причина увольнения</span><input v-model="form.reason" class="input" placeholder="Необязательно" /></label>
        <datalist id="departments"><option v-for="d in departments.data.value || []" :key="d" :value="d" /></datalist>
        <datalist id="emp-types"><option value="ТД" /><option value="ГПХ" /><option value="Самозанятый" /></datalist>
      </form>
      <p v-if="formError" class="error">{{ formError }}</p>
      <template #footer>
        <button class="btn" type="button" @click="editing = null">Отмена</button>
        <button class="btn btn-primary" type="submit" form="event-form" :disabled="saving">{{ saving ? 'Сохранение…' : 'Сохранить' }}</button>
      </template>
    </AppModal>
  </div>
</template>

<style scoped>
.scope { display: flex; align-items: center; gap: 6px; font-size: var(--fs-sm); margin-top: -8px; }
.search { display: flex; align-items: center; gap: 8px; height: 32px; padding: 0 10px; border: 1px solid var(--border-strong); border-radius: var(--radius); color: var(--muted); min-width: 220px; background: var(--surface); }
.search input { border: 0; outline: 0; background: transparent; width: 100%; color: var(--text); font-size: var(--fs-sm); }
.search:focus-within { border-color: var(--accent); box-shadow: 0 0 0 3px var(--focus); }
.sort-icon { display: inline-block; margin-left: 4px; vertical-align: -1px; }
.strong { font-weight: 560; }
.error { color: var(--light-red); font-size: var(--fs-sm); margin-top: 10px; }
</style>
