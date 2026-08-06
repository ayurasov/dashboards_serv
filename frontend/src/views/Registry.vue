<template>
  <div v-if="loading" class="tempty">Загрузка…</div>
  <template v-else>
    <div class="filters">
      <input class="srch" placeholder="Поиск по имени…" v-model="f.search">
      <button class="btn btn-g" :disabled="!active.length" @click="reset">Сбросить фильтры</button>
      <button v-if="canEdit" class="btn btn-p" @click="openNew">+ Сотрудник</button>
    </div>

    <div class="tinfo">
      Показано {{ filteredEmployees.length }} из {{ employees.length }}
      <span v-if="active.length"> · фильтров: {{ active.length }}</span>
    </div>

    <div class="twrap">
      <div class="tscroll">
        <table>
          <thead>
            <tr>
              <th v-for="c in COLUMNS" :key="c.key" @click="setSort(c.key)">
                {{ c.label }}<span class="smark">{{ sortMark(c.key) }}</span>
              </th>
              <th v-if="canEdit"></th>
            </tr>
            <tr class="frow">
              <th v-for="c in COLUMNS" :key="c.key">
                <select v-if="c.options" class="cfsel" v-model="f[c.key]" @click.stop>
                  <option value="">Все</option>
                  <option v-for="o in c.options()" :key="o.value ?? o" :value="o.value ?? o">
                    {{ o.label ?? o }}
                  </option>
                </select>
                <input v-else class="cfin" v-model="f[c.key]" :placeholder="c.ph || '…'" @click.stop>
              </th>
              <th v-if="canEdit"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="e in filteredEmployees" :key="e.id">
              <td><span class="sb" :class="e.event_type==='hired'?'s-hired':'s-fired'">{{ e.event_type==='hired'?'Приём':'Увольнение' }}</span></td>
              <td class="td-p">{{ e.full_name }}</td>
              <td class="td-muted">{{ formatDate(e.event_date) }}</td>
              <td class="td-muted">{{ e.position || '—' }}</td>
              <td class="td-muted">{{ e.department || '—' }}</td>
              <td class="td-muted">{{ monthLabel(e.month_key) }}</td>
              <td v-if="canEdit"><button class="btn btn-g" style="font-size:.75rem;padding:2px 6px" @click="openEdit(e)">✎</button></td>
            </tr>
            <tr v-if="!filteredEmployees.length"><td :colspan="canEdit ? 7 : 6" class="tempty">Нет данных</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Edit/Create modal -->
    <div v-if="showModal" class="modal-overlay" @click.self="showModal=false">
      <div class="modal">
        <div class="mh"><span class="mt">{{ editing?.id ? 'Редактировать' : 'Новый сотрудник' }}</span><button class="mc" @click="showModal=false">✕</button></div>
        <div class="fg">
          <div class="fgi">
            <label class="fl">Тип события</label>
            <select class="fs" v-model="form.event_type">
              <option value="hired">Приём</option>
              <option value="fired">Увольнение</option>
            </select>
          </div>
          <div class="fgi">
            <label class="fl">Дата</label>
            <input class="fi" type="date" v-model="form.event_date">
          </div>
        </div>
        <div class="fgi full" style="margin-top:8px">
          <label class="fl">ФИО</label>
          <input class="fi" v-model="form.full_name" style="width:100%">
        </div>
        <div class="fg" style="margin-top:8px">
          <div class="fgi"><label class="fl">Должность</label><input class="fi" v-model="form.position"></div>
          <div class="fgi"><label class="fl">Отдел</label><input class="fi" v-model="form.department"></div>
        </div>
        <div v-if="!editing?.id" class="fgi full" style="margin-top:8px">
          <label class="fl">Месяц</label>
          <select class="fs" v-model="form.month_key">
            <option v-for="m in months" :key="m.key" :value="m.key">{{ m.label }}</option>
          </select>
        </div>
        <div class="fac" style="margin-top:16px">
          <button v-if="editing?.id" class="btn btn-d" @click="deleteEmp">Удалить</button>
          <div class="right">
            <button class="btn btn-g" @click="showModal=false">Отмена</button>
            <button class="btn btn-p" @click="saveEmp">Сохранить</button>
          </div>
        </div>
      </div>
    </div>
  </template>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api/client.js'
import { useAuthStore } from '../stores/auth.js'
import { useTableFilters, textMatch } from '../composables/useTableFilters.js'
import { setPdfParams } from '../composables/usePdfExport.js'

const auth = useAuthStore()
const canEdit = computed(() => auth.canEdit)
const loading = ref(true)
const months = ref([])
const employees = ref([])
const showModal = ref(false)
const editing = ref(null)
const form = ref({})

const departments = computed(() =>
  [...new Set(employees.value.map(e => e.department).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'ru')))

const TYPE_OPTIONS = [{ value: 'hired', label: 'Приём' }, { value: 'fired', label: 'Увольнение' }]

const COLUMNS = [
  { key: 'event_type', label: 'Тип', options: () => TYPE_OPTIONS },
  { key: 'full_name', label: 'ФИО', ph: 'ФИО' },
  { key: 'event_date', label: 'Дата', ph: 'дата' },
  { key: 'position', label: 'Должность', ph: 'должность' },
  { key: 'department', label: 'Отдел', options: () => departments.value },
  { key: 'month', label: 'Месяц', options: () => months.value.map(m => ({ value: m.key, label: m.label })) },
]

const DEFAULTS = { search: '' }
for (const c of COLUMNS) DEFAULTS[c.key] = ''

const { f, setSort, sortMark, reset, active, sortRows } =
  useTableFilters(DEFAULTS, { sortKey: 'event_date', sortDir: 'desc' })

function monthLabel(key) {
  return months.value.find(m => m.key === key)?.label || key || '—'
}

const filteredEmployees = computed(() => {
  const list = employees.value.filter(e => {
    if (f.search && !textMatch(e.full_name, f.search)) return false
    if (f.month && e.month_key !== f.month) return false
    if (f.event_type && e.event_type !== f.event_type) return false
    if (f.department && (e.department || '') !== f.department) return false
    if (!textMatch(e.full_name, f.full_name)) return false
    if (!textMatch(e.position, f.position)) return false
    if (!textMatch(formatDate(e.event_date), f.event_date) && !textMatch(e.event_date, f.event_date)) return false
    return true
  })
  return sortRows(list, (row, key) => (key === 'month' ? monthLabel(row.month_key) : row[key]))
})

// The topbar PDF button reads these, so its export honours the page filters.
setPdfParams(() => ({
  month: f.month, event_type: f.event_type,
  department: f.department, search: f.search || f.full_name,
}))

function formatDate(d) { return d ? new Date(d).toLocaleDateString('ru-RU') : '' }

// Employee events are only exposed nested inside months; flatten them and carry
// the month key down so the month filter has something to match on.
async function loadEmployees() {
  const list = await api.get('/hr/months')
  months.value = list
  employees.value = list.flatMap(m => (m.employees || []).map(e => ({ ...e, month_key: m.key })))
}

async function loadData() {
  loading.value = true
  try {
    await loadEmployees()
  } finally { loading.value = false }
}

function openNew() {
  editing.value = {}
  form.value = { event_type: 'hired', event_date: new Date().toISOString().slice(0,10), full_name: '', position: '', department: '', month_key: f.month || months.value[0]?.key || '' }
  showModal.value = true
}

function openEdit(e) {
  editing.value = { ...e }
  form.value = { ...e, event_date: e.event_date?.slice(0,10), month_key: e.month_key }
  showModal.value = true
}

function payload() {
  return {
    event_type: form.value.event_type,
    event_date: form.value.event_date,
    full_name: form.value.full_name?.trim() || '',
    position: form.value.position || '',
    department: form.value.department || '',
    employment_type: form.value.employment_type || '',
  }
}

async function saveEmp() {
  try {
    if (editing.value.id) {
      await api.put(`/hr/employees/${editing.value.id}`, payload())
    } else {
      await api.post(`/hr/months/${form.value.month_key}/employees`, payload())
    }
    await loadEmployees()
    showModal.value = false
  } catch { /* the API layer already surfaced the reason as a toast */ }
}

async function deleteEmp() {
  if (!confirm('Удалить запись?')) return
  try {
    await api.del(`/hr/employees/${editing.value.id}`)
    await loadEmployees()
    showModal.value = false
  } catch { /* the API layer already surfaced the reason as a toast */ }
}

onMounted(loadData)
</script>
