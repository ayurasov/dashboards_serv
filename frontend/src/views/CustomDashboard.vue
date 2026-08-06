<template>
  <div v-if="loading" class="tempty">Загрузка…</div>
  <template v-else>
    <div class="filters">
      <select class="fsel" v-model="selectedId" v-if="dashboards.length">
        <option v-for="d in dashboards" :key="d.id" :value="d.id">{{ d.name }}</option>
      </select>
      <div class="tinfo" style="flex:1;margin:0" v-if="active">
        {{ active.is_shared ? 'Общий дашборд' : 'Личный дашборд' }} · виджетов: {{ active.widgets?.length || 0 }}
      </div>
      <template v-if="canEdit">
        <button v-if="active" class="btn btn-g" @click="openEdit(active)">✎ Редактировать</button>
        <button v-if="active" class="btn btn-d" @click="del(active)">✕ Удалить</button>
        <button class="btn btn-p" @click="openNew">+ Новый дашборд</button>
      </template>
    </div>

    <div v-if="!dashboards.length" class="ccard">
      <div class="tempty" v-if="canEdit">Нет кастомных дашбордов. Создайте первый — соберите его из карточек метрик, графиков, таблиц и заметок.</div>
      <div class="tempty" v-else>Нет доступных кастомных дашбордов.</div>
    </div>

    <template v-else-if="active">
      <div v-if="!sortedWidgets.length" class="ccard">
        <div class="tempty">В этом дашборде пока нет виджетов.<template v-if="canEdit"> Нажмите «Редактировать», чтобы добавить.</template></div>
      </div>
      <div v-else class="cd-grid">
        <custom-widget
          v-for="w in sortedWidgets"
          :key="w.id ?? w.sort_order"
          :widget="w"
          :months="months"
          :analytics="analytics"
          :defs="defs"
        />
      </div>
    </template>

    <!-- Create/Edit modal with live preview -->
    <div v-if="showModal" class="modal-overlay" @click.self="close">
      <div class="modal modal-lg">
        <div class="mh">
          <span class="mt">{{ editing?.id ? 'Редактировать дашборд' : 'Новый дашборд' }}</span>
          <button class="mc" @click="close">✕</button>
        </div>

        <div class="fg">
          <div class="fgi"><label class="fl">Название</label><input class="fi" v-model="form.name" placeholder="Например: Найм и адаптация"></div>
          <div class="fgi">
            <label class="fl">Доступ</label>
            <select class="fs" v-model="form.is_shared">
              <option :value="false">Личный</option>
              <option :value="true">Общий</option>
            </select>
          </div>
        </div>

        <div style="margin-top:12px">
          <label class="fl">Виджеты ({{ form.widgets.length }})</label>
          <div v-for="(w, i) in form.widgets" :key="i" class="wrow">
            <div class="wrow-hd">
              <select class="fs" v-model="w.widget_type" style="width:170px" @change="onTypeChange(w)">
                <option v-for="t in WIDGET_TYPES" :key="t.value" :value="t.value">{{ t.label }}</option>
              </select>
              <input class="fi" v-model="w.title" placeholder="Заголовок виджета" style="flex:1">
              <button class="btn btn-g" style="font-size:.75rem;padding:2px 6px" :disabled="i===0" @click="swap(i, i-1)">↑</button>
              <button class="btn btn-g" style="font-size:.75rem;padding:2px 6px" :disabled="i===form.widgets.length-1" @click="swap(i, i+1)">↓</button>
              <button class="btn btn-d" style="font-size:.75rem;padding:2px 6px" @click="form.widgets.splice(i,1)">✕</button>
            </div>

            <textarea v-if="w.widget_type === 'note'" class="fi" v-model="w.text"
                      rows="3" placeholder="Текст заметки" style="width:100%;margin-top:6px"></textarea>

            <div v-else-if="w.widget_type === 'metric_card'" style="margin-top:6px">
              <label class="fl">Метрика</label>
              <select class="fs" v-model="w.metric_key" style="width:100%">
                <option value="">— выберите метрику —</option>
                <option v-for="d in defs" :key="d.key" :value="d.key">{{ d.label }}</option>
              </select>
            </div>

            <div v-else style="margin-top:6px">
              <label class="fl">Метрики ({{ w.metric_keys.length }})</label>
              <div class="mpick">
                <label v-for="d in defs" :key="d.key" class="mpick-item">
                  <input type="checkbox" :value="d.key" v-model="w.metric_keys">
                  {{ d.label }}
                </label>
              </div>
            </div>
          </div>
          <button class="btn btn-g" style="font-size:.75rem;margin-top:8px" @click="addWidget">+ Виджет</button>
        </div>

        <div style="margin-top:16px">
          <label class="fl">
            Предпросмотр
            <button class="btn btn-g" style="font-size:.7rem;padding:1px 6px;margin-left:8px" @click="showPreview = !showPreview">
              {{ showPreview ? 'Скрыть' : 'Показать' }}
            </button>
          </label>
          <div v-if="showPreview" class="cd-grid" style="margin-top:8px">
            <custom-widget
              v-for="(w, i) in previewWidgets"
              :key="i"
              :widget="w"
              :months="months"
              :analytics="analytics"
              :defs="defs"
              :height="180"
            />
            <div v-if="!previewWidgets.length" class="ccard cd-wide"><div class="cd-empty">Добавьте виджет, чтобы увидеть предпросмотр</div></div>
          </div>
        </div>

        <div class="fac" style="margin-top:16px">
          <span></span>
          <div class="right">
            <button class="btn btn-g" @click="close">Отмена</button>
            <button class="btn btn-p" :disabled="!form.name.trim()" @click="save">Сохранить</button>
          </div>
        </div>
      </div>
    </div>
  </template>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api/client.js'
import CustomWidget from '../components/CustomWidget.vue'
import { useAuthStore } from '../stores/auth.js'
import { toastOk } from '../composables/useToast.js'

const auth = useAuthStore()
const canEdit = computed(() => auth.canEdit)

const WIDGET_TYPES = [
  { value: 'metric_card', label: 'Карточка метрики' },
  { value: 'line_chart', label: 'Линейный график' },
  { value: 'bar_chart', label: 'Столбчатый график' },
  { value: 'table', label: 'Таблица метрик' },
  { value: 'note', label: 'Заметка' },
]

const loading = ref(true)
const dashboards = ref([])
const selectedId = ref(null)
const showModal = ref(false)
const showPreview = ref(true)
const editing = ref(null)
const form = ref({ name: '', is_shared: false, widgets: [] })

const defs = ref([])
const months = ref([])
const analytics = ref({})

const active = computed(() =>
  dashboards.value.find(d => d.id === selectedId.value) || dashboards.value[0] || null)

const sortedWidgets = computed(() =>
  [...(active.value?.widgets || [])].sort((a, b) => a.sort_order - b.sort_order))

// The editor keeps config fields flat (metric_key / metric_keys / text) so inputs can
// v-model them directly; they are folded back into `config` on save.
function toEditor(w) {
  return {
    widget_type: w.widget_type,
    title: w.title || '',
    metric_key: w.config?.metric_key || '',
    metric_keys: Array.isArray(w.config?.metric_keys) ? [...w.config.metric_keys] : [],
    text: w.config?.text || '',
  }
}

function toConfig(w) {
  if (w.widget_type === 'note') return { text: w.text || '' }
  if (w.widget_type === 'metric_card') return { metric_key: w.metric_key || '' }
  return { metric_keys: w.metric_keys || [] }
}

const previewWidgets = computed(() => form.value.widgets.map((w, i) => ({
  widget_type: w.widget_type, title: w.title, config: toConfig(w), sort_order: i,
})))

function addWidget() {
  form.value.widgets.push({ widget_type: 'metric_card', title: '', metric_key: '', metric_keys: [], text: '' })
}

function onTypeChange(w) {
  if (w.widget_type === 'metric_card' && !w.metric_key) w.metric_key = w.metric_keys[0] || ''
  if ((w.widget_type === 'line_chart' || w.widget_type === 'bar_chart' || w.widget_type === 'table')
      && !w.metric_keys.length && w.metric_key) {
    w.metric_keys = [w.metric_key]
  }
}

function swap(i, j) {
  const list = form.value.widgets
  ;[list[i], list[j]] = [list[j], list[i]]
}

function openNew() {
  editing.value = {}
  form.value = { name: '', is_shared: false, widgets: [] }
  addWidget()
  showModal.value = true
}

function openEdit(d) {
  editing.value = { ...d }
  form.value = {
    name: d.name,
    is_shared: d.is_shared,
    widgets: [...(d.widgets || [])].sort((a, b) => a.sort_order - b.sort_order).map(toEditor),
  }
  showModal.value = true
}

function close() { showModal.value = false }

async function reload(keepId) {
  dashboards.value = await api.get('/dashboards')
  if (keepId && dashboards.value.some(d => d.id === keepId)) selectedId.value = keepId
  else if (!dashboards.value.some(d => d.id === selectedId.value)) selectedId.value = dashboards.value[0]?.id ?? null
}

async function save() {
  const body = {
    name: form.value.name,
    is_shared: form.value.is_shared,
    widgets: form.value.widgets.map((w, i) => ({
      widget_type: w.widget_type,
      title: w.title,
      config: toConfig(w),
      sort_order: i,
    })),
  }
  try {
    const saved = editing.value.id
      ? await api.put(`/dashboards/${editing.value.id}`, body)
      : await api.post('/dashboards', body)
    await reload(saved.id)
    showModal.value = false
    toastOk('Дашборд сохранён')
  } catch { /* the API layer already surfaced the reason as a toast */ }
}

async function del(d) {
  if (!confirm(`Удалить дашборд «${d.name}»?`)) return
  try {
    await api.del(`/dashboards/${d.id}`)
    selectedId.value = null
    await reload()
    toastOk('Дашборд удалён')
  } catch { /* the API layer already surfaced the reason as a toast */ }
}

async function loadMetricData() {
  defs.value = await api.get('/hr/metric-definitions')
  months.value = await api.get('/hr/months')
  for (const m of months.value) {
    try {
      analytics.value[m.key] = await api.get(`/hr/analytics/month/${m.key}`)
    } catch { /* a single failing month must not blank the whole page */ }
  }
}

onMounted(async () => {
  loading.value = true
  try {
    await Promise.all([reload(), loadMetricData()])
  } finally { loading.value = false }
})
</script>
