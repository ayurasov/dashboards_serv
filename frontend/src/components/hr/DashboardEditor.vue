<script setup>
import { computed, nextTick, ref } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import AppModal from '@/components/ui/AppModal.vue'
import { hrApi } from '@/api/services'
import { CATEGORY_LABELS } from '@/domain/hrSummary'
import {
  MAX_WIDGETS, WIDGET_TYPES, changeType, isMulti, moveItem, newWidget, sortWidgets, toEditor, toPayload, validateWidget,
} from '@/domain/hrWidgets'

/**
 * Редактор пользовательского дашборда: название, доступ, список виджетов с настройками.
 * dashboard — существующий дашборд (с id), копия или заготовка нового (без id).
 */
const props = defineProps({
  dashboard: { type: Object, required: true },
  defs: { type: Array, default: () => [] },
  canShare: { type: Boolean, default: false },
})
const emit = defineEmits(['close', 'saved'])

const name = ref(props.dashboard.name || '')
const isShared = ref(!!props.dashboard.is_shared && props.canShare)
const widgets = ref(props.dashboard.widgets?.length ? sortWidgets(props.dashboard.widgets).map(toEditor) : [])
const errors = ref({})
const nameError = ref('')
const formError = ref('')
const saving = ref(false)
const listEl = ref(null)

const categories = computed(() => {
  const out = []
  for (const d of props.defs) {
    let g = out.find((x) => x.key === d.category)
    if (!g) out.push(g = { key: d.category, label: CATEGORY_LABELS[d.category] || d.category, items: [] })
    g.items.push(d)
  }
  return out
})
const defLabel = (key) => props.defs.find((d) => d.key === key)?.label || ''
function titlePlaceholder(w) {
  if (w.widget_type === 'metric_card' && w.metric_key) return defLabel(w.metric_key)
  return WIDGET_TYPES.find((t) => t.value === w.widget_type)?.label || 'Заголовок'
}

function add(type) {
  if (widgets.value.length >= MAX_WIDGETS) return
  widgets.value.push(newWidget(type))
}
function setType(index, type) {
  widgets.value[index] = changeType(widgets.value[index], type)
}
function move(index, step) {
  widgets.value = moveItem(widgets.value, index, step)
}
function removeAt(index) {
  const [w] = widgets.value.splice(index, 1)
  if (w) delete errors.value[w.uid]
}
function toggleMetric(w, key) {
  w.metric_keys = w.metric_keys.includes(key) ? w.metric_keys.filter((k) => k !== key) : [...w.metric_keys, key]
  if (errors.value[w.uid]) errors.value[w.uid] = validateWidget(w)
}

async function save() {
  nameError.value = name.value.trim() ? '' : 'Введите название'
  errors.value = Object.fromEntries(widgets.value.map((w) => [w.uid, validateWidget(w)]).filter(([, e]) => e))
  formError.value = Object.keys(errors.value).length ? 'Проверьте настройки виджетов, отмеченных красным' : ''
  if (nameError.value || formError.value) {
    await nextTick()
    listEl.value?.querySelector('.wrow.invalid')?.scrollIntoView({ block: 'center', behavior: 'smooth' })
    return
  }
  const body = { name: name.value.trim(), is_shared: isShared.value, widgets: widgets.value.map(toPayload) }
  saving.value = true
  try {
    const saved = props.dashboard.id ? await hrApi.updateDashboard(props.dashboard.id, body) : await hrApi.createDashboard(body)
    emit('saved', saved)
  } catch (e) {
    formError.value = e.message
    nameError.value = e.fields?.name || ''
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <AppModal :title="dashboard.id ? 'Изменить дашборд' : 'Новый дашборд'" subtitle="Соберите подборку из карточек, графиков, таблиц и заметок" :width="760" @close="emit('close')">
    <form id="dashboard-form" class="stack editor" @submit.prevent="save">
      <div class="form-grid">
        <label class="field full"><span>Название</span>
          <input v-model="name" class="input" :class="{ invalid: nameError }" maxlength="200" placeholder="Например, «Найм и адаптация»" />
          <span v-if="nameError" class="error">{{ nameError }}</span>
        </label>
        <label v-if="canShare" class="check full">
          <input v-model="isShared" type="checkbox" />
          <span>Общий дашборд <span class="muted">— виден всем пользователям службы персонала, изменять его можете только вы</span></span>
        </label>
      </div>

      <div class="widgets-head">
        <span class="label">Виджеты</span>
        <span class="muted num">{{ widgets.length }} из {{ MAX_WIDGETS }}</span>
      </div>

      <ol v-if="widgets.length" ref="listEl" class="wlist">
        <li v-for="(w, i) in widgets" :key="w.uid" class="wrow" :class="{ invalid: errors[w.uid] }">
          <div class="wtop">
            <span class="wnum num">{{ i + 1 }}</span>
            <select class="select select-sm wtype" :value="w.widget_type" aria-label="Тип виджета" @change="setType(i, $event.target.value)">
              <option v-for="t in WIDGET_TYPES" :key="t.value" :value="t.value">{{ t.label }}</option>
            </select>
            <input v-model="w.title" class="input input-sm wtitle" maxlength="200" :placeholder="titlePlaceholder(w)" aria-label="Заголовок виджета" />
            <div class="wbtns">
              <button class="btn btn-icon btn-sm btn-ghost" type="button" title="Выше" :disabled="i === 0" @click="move(i, -1)"><AppIcon name="chevron-up" :size="14" /></button>
              <button class="btn btn-icon btn-sm btn-ghost" type="button" title="Ниже" :disabled="i === widgets.length - 1" @click="move(i, 1)"><AppIcon name="chevron-down" :size="14" /></button>
              <button class="btn btn-icon btn-sm btn-ghost" type="button" title="Убрать виджет" @click="removeAt(i)"><AppIcon name="trash" :size="14" /></button>
            </div>
          </div>

          <div class="wconf">
            <select v-if="w.widget_type === 'metric_card'" v-model="w.metric_key" class="select select-sm" aria-label="Метрика" @change="errors[w.uid] && (errors[w.uid] = validateWidget(w))">
              <option value="" disabled>Выберите метрику</option>
              <optgroup v-for="g in categories" :key="g.key" :label="g.label">
                <option v-for="d in g.items" :key="d.key" :value="d.key">{{ d.label }}{{ d.unit ? `, ${d.unit}` : '' }}</option>
              </optgroup>
            </select>

            <div v-else-if="isMulti(w.widget_type)" class="mpick scroll-thin" role="group" aria-label="Метрики">
              <template v-for="g in categories" :key="g.key">
                <span class="mgroup">{{ g.label }}</span>
                <label v-for="d in g.items" :key="d.key" class="mitem" :class="{ on: w.metric_keys.includes(d.key) }">
                  <input type="checkbox" :checked="w.metric_keys.includes(d.key)" @change="toggleMetric(w, d.key)" />
                  <span class="ellipsis" :title="d.label">{{ d.label }}</span><span v-if="d.unit" class="munit">{{ d.unit }}</span>
                </label>
              </template>
            </div>

            <textarea v-else v-model="w.text" class="textarea" rows="3" maxlength="5000" placeholder="Текст заметки" aria-label="Текст заметки"
                      @input="errors[w.uid] && (errors[w.uid] = validateWidget(w))" />
            <span v-if="isMulti(w.widget_type) && w.metric_keys.length" class="help">Выбрано: {{ w.metric_keys.length }}</span>
            <span v-if="errors[w.uid]" class="error">{{ errors[w.uid] }}</span>
          </div>
        </li>
      </ol>
      <p v-else class="empty muted">Виджетов пока нет — добавьте первый.</p>

      <div class="add">
        <span class="muted">Добавить:</span>
        <button v-for="t in WIDGET_TYPES" :key="t.value" class="chip" type="button" :disabled="widgets.length >= MAX_WIDGETS" @click="add(t.value)">
          <AppIcon :name="t.icon" :size="13" />{{ t.label }}
        </button>
      </div>
    </form>
    <p v-if="formError" class="error form-error">{{ formError }}</p>
    <template #footer>
      <button class="btn" type="button" @click="emit('close')">Отмена</button>
      <button class="btn btn-primary" type="submit" form="dashboard-form" :disabled="saving">{{ saving ? 'Сохранение…' : 'Сохранить' }}</button>
    </template>
  </AppModal>
</template>

<style scoped>
.editor { gap: var(--sp-4); }
.check > span { line-height: 1.4; }
.widgets-head { display: flex; align-items: baseline; justify-content: space-between; padding-top: var(--sp-2); border-top: 1px solid var(--border); }
.widgets-head .muted { font-size: var(--fs-sm); }
.wlist { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 10px; }
.wrow { display: flex; flex-direction: column; gap: 10px; padding: 12px; border: 1px solid var(--border); border-radius: var(--radius); background: var(--surface-2); }
.wrow.invalid { border-color: color-mix(in srgb, var(--light-red) 60%, var(--border)); }
.wtop { display: flex; align-items: center; gap: 8px; }
.wnum { width: 22px; height: 22px; flex: 0 0 22px; display: grid; place-items: center; border-radius: 50%; background: var(--surface-3); color: var(--muted); font-size: var(--fs-xs); font-weight: 620; }
.wtype { width: 200px; flex: 0 0 auto; }
.wtitle { flex: 1; min-width: 0; }
.wbtns { display: flex; gap: 2px; }
.wconf { display: flex; flex-direction: column; gap: 6px; padding-left: 30px; }
.mpick { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 2px 12px; max-height: 148px; overflow-y: auto; padding: 8px 10px; border: 1px solid var(--border-strong); border-radius: var(--radius); background: var(--surface); }
.mgroup { grid-column: 1 / -1; margin-top: 6px; font-size: var(--fs-xs); font-weight: 650; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); }
.mgroup:first-child { margin-top: 0; }
.mitem { display: flex; align-items: center; gap: 8px; min-width: 0; padding: 3px 0; font-size: var(--fs-sm); color: var(--text-2); cursor: pointer; }
.mitem.on { color: var(--text); }
.mitem input { width: 15px; height: 15px; flex: 0 0 15px; accent-color: var(--brand); }
.munit { flex: 0 0 auto; font-size: var(--fs-xs); color: var(--faint); }
.add { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; font-size: var(--fs-sm); }
.add .chip:disabled { opacity: .5; cursor: not-allowed; }
.empty { padding: 16px; text-align: center; border: 1px dashed var(--border-strong); border-radius: var(--radius); font-size: var(--fs-sm); }
.help { font-size: var(--fs-xs); color: var(--muted); }
.error { color: var(--light-red); font-size: var(--fs-sm); }
.form-error { margin-top: 10px; }
@media (max-width: 640px) {
  .wtop { flex-wrap: wrap; }
  .wtype { width: 100%; }
  .wconf { padding-left: 0; }
  .mpick { grid-template-columns: minmax(0, 1fr); }
}
</style>
