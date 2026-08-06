<template>
  <div v-if="loading" class="tempty">Загрузка…</div>
  <template v-else>
    <div class="filters">
      <div class="tinfo" style="flex:1;margin:0">
        Бенчмарков: {{ benchmarks.length }} · с целью и фактом: {{ chartRows.length }}
      </div>
      <button v-if="canEdit" class="btn btn-p" @click="openCreate">Добавить цель</button>
    </div>

    <div class="ccard" style="margin-bottom:16px">
      <div class="ctitle">Цель и факт по ключевым метрикам</div>
      <e-chart :option="chartOpt" :height="280" />
    </div>

    <div class="ccard">
      <div class="ctitle">
        Бенчмарки
        <span v-if="!canEdit" style="font-size:.75rem;color:var(--c-muted);font-weight:400">
          Изменение целей доступно администратору
        </span>
      </div>
      <div class="twrap">
        <div class="tscroll">
          <table>
            <thead>
              <tr>
                <th>Метрика</th><th>Период</th><th>Цель</th><th>Факт</th>
                <th>Отклонение</th><th>Статус</th><th v-if="canEdit"></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="b in benchmarks" :key="b.id">
                <td class="td-p">
                  {{ b.metric_label }}
                  <div v-if="b.description" class="source-note">{{ b.description }}</div>
                </td>
                <td class="td-muted">{{ b.label || b.year }}</td>
                <td class="td-mono">
                  <input v-if="editingId === b.id" class="fi" type="number" step="0.01"
                         v-model="editValue" style="width:90px">
                  <template v-else>{{ fmt(b.target_value, b.unit) }}</template>
                </td>
                <td class="td-mono">
                  {{ fmt(b.current_value, b.unit) }}
                  <span v-if="b.current_month" class="td-muted" style="font-size:.7rem"> · {{ b.current_month }}</span>
                </td>
                <td class="td-mono" :style="{ color: diffColor(b) }">{{ diffText(b) }}</td>
                <td>
                  <span class="light-dot" :class="'light-'+b.status"></span>
                  {{ statusLabel(b) }}
                </td>
                <td v-if="canEdit">
                  <template v-if="editingId === b.id">
                    <button class="btn btn-p" style="font-size:.75rem;padding:2px 8px" @click="saveTarget(b)">✓</button>
                    <button class="btn btn-g" style="font-size:.75rem;padding:2px 8px" @click="editingId = null">✕</button>
                  </template>
                  <button v-else class="btn btn-g" style="font-size:.75rem;padding:2px 6px" @click="startEdit(b)">✎</button>
                </td>
              </tr>
              <tr v-if="!benchmarks.length"><td colspan="7" class="tempty">Нет бенчмарков</td></tr>
            </tbody>
          </table>
        </div>
      </div>
      <p class="source-note">
        Факт берётся из последнего месяца, в котором метрика заполнена. Отклонение считается
        с учётом направления метрики: для «меньше — лучше» цель не должна быть превышена.
      </p>
    </div>

    <div v-if="showModal" class="modal-overlay">
      <div class="modal modal-sm">
        <div class="mh"><span class="mt">Добавить цель</span><button class="mc" @click="showModal = false">✕</button></div>
        <div class="fg">
          <div class="fgi full"><label class="fl">Метрика</label>
            <select class="fs" v-model="form.metric_key">
              <option value="">Выберите метрику</option>
              <option v-for="m in availableMetrics" :key="m.key" :value="m.key">
                {{ m.label }}{{ m.unit ? `, ${m.unit}` : '' }}
              </option>
            </select>
            <span v-if="!availableMetrics.length" class="source-note">
              Для всех метрик уже заданы цели
            </span>
          </div>
          <div class="fgi full"><label class="fl">Целевое значение</label>
            <input class="fi" type="number" step="0.01" v-model="form.target_value">
          </div>
          <div class="fgi full"><label class="fl">Описание</label>
            <input class="fi" v-model="form.description" placeholder="Необязательно">
          </div>
          <div class="fgi full"><label class="fl">Источник</label>
            <input class="fi" v-model="form.source" placeholder="Необязательно">
          </div>
        </div>
        <div class="err-msg">{{ formErr }}</div>
        <div class="fac">
          <span></span>
          <div class="right">
            <button class="btn btn-g" @click="showModal = false">Отмена</button>
            <button class="btn btn-p" :disabled="saving" @click="createBenchmark">Сохранить</button>
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
import { toastOk } from '../composables/useToast.js'
import EChart from '../components/EChart.vue'

const auth = useAuthStore()
const canEdit = computed(() => auth.isAdmin)
const loading = ref(true)
const benchmarks = ref([])
const editingId = ref(null)
const editValue = ref('')
const metricDefs = ref([])
const showModal = ref(false)
const saving = ref(false)
const formErr = ref('')
const form = ref({ metric_key: '', target_value: '', description: '', source: '' })

// Only metrics that don't have a benchmark yet can get a new target.
const availableMetrics = computed(() => {
  const used = new Set(benchmarks.value.map(b => b.metric_key))
  return metricDefs.value.filter(m => !used.has(m.key))
})

const STATUS_LABELS = { green: 'Цель достигнута', yellow: 'Близко к цели', red: 'Ниже цели' }
function statusLabel(b) {
  if (b.target_value === null || b.target_value === undefined) return 'Справочно'
  if (b.current_value === null || b.current_value === undefined) return 'Нет данных'
  return STATUS_LABELS[b.status] || '—'
}

function fmt(val, unit) {
  if (val === null || val === undefined) return '—'
  const num = unit === 'чел.' || unit === 'шт.' ? Math.round(val) : Number(val.toFixed(2))
  return String(num).replace('.', ',') + (unit ? ` ${unit}` : '')
}

function diffText(b) {
  if (b.diff === null || b.diff === undefined) return '—'
  const sign = b.diff > 0 ? '+' : ''
  return sign + String(Number(b.diff.toFixed(2))).replace('.', ',')
}

function diffColor(b) {
  if (b.diff === null || b.diff === undefined) return 'var(--c-muted)'
  const good = b.direction === 'lower_is_better' ? b.diff <= 0 : b.diff >= 0
  return good ? 'var(--c-ok)' : 'var(--c-err)'
}

// Only rows that actually have both a target and a fact are worth charting.
const chartRows = computed(() =>
  benchmarks.value.filter(b => b.target_value !== null && b.current_value !== null))

const chartOpt = computed(() => ({
  tooltip: { trigger: 'axis' },
  legend: { data: ['Цель', 'Факт'], bottom: 0, textStyle: { fontSize: 11 } },
  grid: { left: 45, right: 12, top: 12, bottom: 60 },
  xAxis: {
    type: 'category',
    data: chartRows.value.map(b => b.metric_label),
    axisLabel: { fontSize: 9, interval: 0, width: 90, overflow: 'break' },
  },
  yAxis: { type: 'value', axisLabel: { fontSize: 10 } },
  series: [
    { name: 'Цель', type: 'bar', data: chartRows.value.map(b => b.target_value), itemStyle: { color: '#6b6a65' } },
    { name: 'Факт', type: 'bar', data: chartRows.value.map(b => b.current_value), itemStyle: { color: '#1a4f80' } },
  ],
}))

function startEdit(b) {
  editingId.value = b.id
  editValue.value = b.target_value ?? ''
}

async function saveTarget(b) {
  const num = Number(editValue.value)
  if (editValue.value === '' || Number.isNaN(num)) return
  try {
    const updated = await api.put(`/hr/benchmarks/${b.id}`, { target_value: num })
    benchmarks.value = benchmarks.value.map(row => (row.id === updated.id ? updated : row))
    editingId.value = null
    toastOk('Цель сохранена')
  } catch { /* the API layer already surfaced the reason as a toast */ }
}

function openCreate() {
  form.value = { metric_key: '', target_value: '', description: '', source: '' }
  formErr.value = ''
  showModal.value = true
}

async function createBenchmark() {
  const num = Number(form.value.target_value)
  if (!form.value.metric_key) { formErr.value = 'Выберите метрику'; return }
  if (form.value.target_value === '' || Number.isNaN(num)) {
    formErr.value = 'Укажите числовое целевое значение'
    return
  }
  formErr.value = ''
  saving.value = true
  try {
    await api.post('/hr/benchmarks', {
      metric_key: form.value.metric_key,
      target_value: num,
      description: form.value.description,
      source: form.value.source,
    })
    showModal.value = false
    await loadData()
    toastOk('Цель добавлена')
  } catch (e) {
    // The API layer already surfaced the reason as a toast; echo it in the modal.
    formErr.value = e?.message || 'Не удалось сохранить цель'
  } finally { saving.value = false }
}

async function loadData() {
  loading.value = true
  try {
    const [rows, defs] = await Promise.all([
      api.get('/hr/benchmarks'),
      api.get('/hr/metric-definitions'),
    ])
    benchmarks.value = rows
    metricDefs.value = defs
  } finally { loading.value = false }
}

onMounted(loadData)
</script>
