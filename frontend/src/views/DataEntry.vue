<template>
  <div v-if="loading" class="tempty">Загрузка…</div>
  <template v-else>
    <div class="filters">
      <select class="fsel" v-model="activeMonth" style="min-width:180px">
        <option v-for="m in months" :key="m.key" :value="m.key">{{ m.label }}</option>
      </select>
      <button v-if="editable" class="btn btn-g" @click="showNewMonth = true">+ Создать месяц</button>
      <span v-if="!editable" class="tag tag-viewer">Только просмотр</span>
      <span v-else-if="dirty" class="td-muted" style="font-size:.75rem">Есть несохранённые изменения</span>
    </div>

    <div v-if="!months.length" class="tempty">
      Нет ни одного месяца.
      <template v-if="editable">Создайте первый месяц, чтобы начать заполнение.</template>
    </div>

    <template v-else>
      <!-- Metrics -->
      <div class="ccard" style="margin-bottom:16px">
        <div class="ctitle">
          <span>Метрики — {{ currentMonth?.label }}</span>
          <button v-if="editable" class="btn btn-p" style="font-size:.75rem;padding:4px 10px"
                  :disabled="hasErrors" @click="saveMetrics">Сохранить метрики</button>
        </div>
        <p v-if="hasErrors" class="err-msg">Исправьте числовые значения перед сохранением.</p>
        <div v-for="group in metricGroups" :key="group.category" style="margin-bottom:16px">
          <div class="nl" style="padding-left:0">{{ group.title }}</div>
          <div class="twrap">
            <div class="tscroll">
              <table>
                <thead>
                  <tr><th style="min-width:220px">Метрика</th><th style="width:150px">Значение</th>
                      <th>Текстовое значение</th><th>Источник / комментарий</th></tr>
                </thead>
                <tbody>
                  <tr v-for="m in group.metrics" :key="m.key">
                    <td class="td-p">
                      {{ m.label }}
                      <span class="td-muted" style="font-weight:400">{{ m.unit ? ` (${m.unit})` : '' }}</span>
                      <div v-if="m.description" class="source-note">{{ m.description }}</div>
                    </td>
                    <td>
                      <input class="fi" style="width:110px" inputmode="decimal" :disabled="!editable"
                             v-model="form[m.key].numeric_value"
                             :style="errors[m.key] ? 'border-color:var(--c-err)' : ''">
                      <div v-if="errors[m.key]" class="err-msg">{{ errors[m.key] }}</div>
                    </td>
                    <td><input class="fi" style="width:100%" :disabled="!editable" v-model="form[m.key].text_value"></td>
                    <td><input class="fi" style="width:100%" :disabled="!editable" v-model="form[m.key].source_note"></td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>

      <!-- Employee events -->
      <div class="ccard">
        <div class="ctitle">
          <span>События персонала — {{ currentMonth?.label }}
            <span class="td-muted" style="font-weight:400">
              (принято: {{ currentMonth?.hired_count || 0 }}, уволено: {{ currentMonth?.fired_count || 0 }})
            </span>
          </span>
          <button v-if="editable" class="btn btn-g" style="font-size:.75rem;padding:4px 10px" @click="openEvent()">+ Событие</button>
        </div>
        <div class="twrap">
          <div class="tscroll">
            <table>
              <thead>
                <tr><th>Тип</th><th>Дата</th><th>ФИО</th><th>Должность</th><th>Отдел</th>
                    <th>Оформление</th><th v-if="editable"></th></tr>
              </thead>
              <tbody>
                <tr v-for="e in events" :key="e.id">
                  <td><span class="sb" :class="e.event_type === 'hired' ? 's-hired' : 's-fired'">
                    {{ e.event_type === 'hired' ? 'Приём' : 'Увольнение' }}</span></td>
                  <td class="td-mono">{{ e.event_date }}</td>
                  <td class="td-p">{{ e.full_name }}</td>
                  <td class="td-muted">{{ e.position || '—' }}</td>
                  <td class="td-muted">{{ e.department || '—' }}</td>
                  <td class="td-muted">{{ e.employment_type || '—' }}</td>
                  <td v-if="editable">
                    <button class="btn btn-g" style="font-size:.75rem;padding:2px 6px" @click="openEvent(e)">✎</button>
                    <button class="btn btn-d" style="font-size:.75rem;padding:2px 6px" @click="deleteEvent(e)">✕</button>
                  </td>
                </tr>
                <tr v-if="!events.length"><td :colspan="editable ? 7 : 6" class="tempty">Нет событий за месяц</td></tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </template>

    <!-- New month modal -->
    <div v-if="showNewMonth" class="modal-overlay" @click.self="showNewMonth = false">
      <div class="modal modal-sm">
        <div class="mh"><span class="mt">Новый месяц</span><button class="mc" @click="showNewMonth = false">✕</button></div>
        <div class="fg">
          <div class="fgi"><label class="fl">Год</label>
            <input class="fi" type="number" min="2020" max="2035" v-model="newMonthForm.year"></div>
          <div class="fgi"><label class="fl">Месяц</label>
            <select class="fs" v-model="newMonthForm.month">
              <option v-for="i in 12" :key="i" :value="i">{{ MONTH_NAMES[i - 1] }}</option>
            </select>
          </div>
        </div>
        <div class="fac">
          <div class="right">
            <button class="btn btn-g" @click="showNewMonth = false">Отмена</button>
            <button class="btn btn-p" @click="createMonth">Создать</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Employee event modal -->
    <div v-if="showEvent" class="modal-overlay" @click.self="showEvent = false">
      <div class="modal">
        <div class="mh">
          <span class="mt">{{ eventForm.id ? 'Изменить событие' : 'Новое событие' }}</span>
          <button class="mc" @click="showEvent = false">✕</button>
        </div>
        <div class="fg">
          <div class="fgi"><label class="fl">Тип</label>
            <select class="fs" v-model="eventForm.event_type">
              <option value="hired">Приём</option>
              <option value="fired">Увольнение</option>
            </select>
          </div>
          <div class="fgi"><label class="fl">Дата</label><input class="fi" type="date" v-model="eventForm.event_date"></div>
        </div>
        <div class="fgi full" style="margin-top:8px"><label class="fl">ФИО</label>
          <input class="fi" v-model="eventForm.full_name"></div>
        <div class="fg" style="margin-top:8px">
          <div class="fgi"><label class="fl">Должность</label><input class="fi" v-model="eventForm.position"></div>
          <div class="fgi"><label class="fl">Отдел</label><input class="fi" v-model="eventForm.department"></div>
        </div>
        <div class="fgi full" style="margin-top:8px"><label class="fl">Оформление</label>
          <input class="fi" v-model="eventForm.employment_type"></div>
        <p v-if="eventError" class="err-msg">{{ eventError }}</p>
        <div class="fac">
          <div class="right">
            <button class="btn btn-g" @click="showEvent = false">Отмена</button>
            <button class="btn btn-p" @click="saveEvent">Сохранить</button>
          </div>
        </div>
      </div>
    </div>
  </template>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api/client.js'
import { useAuthStore } from '../stores/auth.js'
import { toastOk } from '../composables/useToast.js'

const MONTH_NAMES = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
  'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь']
const CATEGORY_TITLES = { headcount: 'Численность', hiring: 'Найм', adaptation: 'Адаптация', turnover: 'Удержание' }

const route = useRoute()
const auth = useAuthStore()
// Saving month data needs the global edit role or `edit_metrics` on the HR service;
// everyone else lands here read-only.
const editable = computed(() => auth.canEdit || auth.canEditMetrics('hr'))

const loading = ref(true)
const months = ref([])
const defs = ref([])
const activeMonth = ref('')
const form = ref({})
const savedForm = ref({})
const showNewMonth = ref(false)
const newMonthForm = ref({ year: new Date().getFullYear(), month: new Date().getMonth() + 1 })
const showEvent = ref(false)
const eventForm = ref({})
const eventError = ref('')

const currentMonth = computed(() => months.value.find(m => m.key === activeMonth.value))
const events = computed(() => [...(currentMonth.value?.employees || [])]
  .sort((a, b) => String(a.event_date).localeCompare(String(b.event_date))))

const metricGroups = computed(() => {
  const groups = []
  for (const d of defs.value) {
    let g = groups.find(x => x.category === d.category)
    if (!g) {
      g = { category: d.category, title: CATEGORY_TITLES[d.category] || d.category, metrics: [] }
      groups.push(g)
    }
    g.metrics.push(d)
  }
  return groups
})

/** '' clears the value; anything that is not a number is an inline error. */
function parseNumeric(raw) {
  const s = String(raw ?? '').trim().replace(',', '.')
  if (!s) return { value: null }
  if (!/^-?\d+(\.\d+)?$/.test(s)) return { error: 'Введите число' }
  return { value: Number(s) }
}

const errors = computed(() => {
  const out = {}
  for (const d of defs.value) {
    const parsed = parseNumeric(form.value[d.key]?.numeric_value)
    if (parsed.error) out[d.key] = parsed.error
  }
  return out
})
const hasErrors = computed(() => Object.keys(errors.value).length > 0)
const dirty = computed(() => JSON.stringify(form.value) !== JSON.stringify(savedForm.value))

function buildForm() {
  const values = {}
  for (const mv of currentMonth.value?.metrics || []) values[mv.metric_key] = mv
  const next = {}
  for (const d of defs.value) {
    const mv = values[d.key]
    next[d.key] = {
      numeric_value: mv && mv.numeric_value !== null ? String(mv.numeric_value) : '',
      text_value: mv?.text_value || '',
      source_note: mv?.source_note || '',
    }
  }
  form.value = next
  savedForm.value = JSON.parse(JSON.stringify(next))
}

async function loadMonths() {
  months.value = await api.get('/hr/months')
  if (!months.value.some(m => m.key === activeMonth.value)) {
    activeMonth.value = months.value.length ? months.value[months.value.length - 1].key : ''
  }
}

async function loadData() {
  loading.value = true
  try {
    defs.value = await api.get('/hr/metric-definitions')
    await loadMonths()
    const wanted = route.query.month
    if (wanted && months.value.some(m => m.key === wanted)) activeMonth.value = wanted
    buildForm()
  } finally { loading.value = false }
}

watch(activeMonth, buildForm)

async function saveMetrics() {
  if (hasErrors.value) return
  const payload = defs.value.map(d => ({
    metric_key: d.key,
    numeric_value: parseNumeric(form.value[d.key].numeric_value).value,
    text_value: form.value[d.key].text_value || '',
    source_note: form.value[d.key].source_note || '',
  })).filter(m => m.numeric_value !== null || m.text_value || m.source_note)
  try {
    await api.put(`/hr/months/${activeMonth.value}/metrics`, payload)
    await loadMonths()
    buildForm()
    toastOk('Данные сохранены')
  } catch { /* the API layer already surfaced the reason as a toast */ }
}

async function createMonth() {
  try {
    const { year, month } = newMonthForm.value
    await api.post('/hr/months', { year: Number(year), month: Number(month), notes: '' })
    const key = `${year}-${String(month).padStart(2, '0')}`
    await loadMonths()
    activeMonth.value = key
    buildForm()
    showNewMonth.value = false
    toastOk('Месяц создан')
  } catch { /* the API layer already surfaced the reason as a toast */ }
}

function openEvent(e) {
  eventError.value = ''
  eventForm.value = e
    ? { ...e }
    : { event_type: 'hired', event_date: '', full_name: '', position: '', department: '', employment_type: '' }
  showEvent.value = true
}

async function saveEvent() {
  const f = eventForm.value
  if (!f.full_name?.trim()) { eventError.value = 'Укажите ФИО'; return }
  if (!f.event_date) { eventError.value = 'Укажите дату'; return }
  const body = {
    event_type: f.event_type, event_date: f.event_date, full_name: f.full_name.trim(),
    position: f.position || '', department: f.department || '', employment_type: f.employment_type || '',
  }
  try {
    if (f.id) await api.put(`/hr/employees/${f.id}`, body)
    else await api.post(`/hr/months/${activeMonth.value}/employees`, body)
    await loadMonths()
    showEvent.value = false
    toastOk('Данные сохранены')
  } catch { /* the API layer already surfaced the reason as a toast */ }
}

async function deleteEvent(e) {
  if (!confirm(`Удалить запись «${e.full_name}»?`)) return
  try {
    await api.del(`/hr/employees/${e.id}`)
    await loadMonths()
    toastOk('Запись удалена')
  } catch { /* the API layer already surfaced the reason as a toast */ }
}

onMounted(loadData)
</script>
