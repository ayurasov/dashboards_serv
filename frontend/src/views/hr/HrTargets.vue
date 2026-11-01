<script setup>
import { computed, reactive, ref } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import AppModal from '@/components/ui/AppModal.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import KpiCard from '@/components/ui/KpiCard.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import PdfButton from '@/components/ui/PdfButton.vue'
import TargetCard from '@/components/hr/TargetCard.vue'
import { hrApi } from '@/api/services'
import { useAsync } from '@/composables/useAsync'
import { confirm } from '@/composables/useConfirm'
import { toastOk } from '@/composables/useToast'
import { useAuthStore } from '@/stores/auth'
import { plural } from '@/utils/format'
import { CATEGORY_LABELS } from '@/domain/hrSummary'
import { availableMetrics, emptyTargetForm, groupByYear, targetPayload, targetToForm } from '@/domain/hrTargets'

const auth = useAuthStore()
const canManage = computed(() => auth.can('hr', 'manager'))
const { data, loading, reload } = useAsync(() => hrApi.targets())
const defs = useAsync(() => hrApi.metrics())

const groups = computed(() => groupByYear(data.value))
const latest = computed(() => groups.value.find((g) => g.withTarget) || null)
const yearText = (g) => {
  const parts = [`${g.items.length} ${plural(g.items.length, ['показатель', 'показателя', 'показателей'])}`]
  if (g.withTarget) parts.push(`достигнуто ${g.counts.green} из ${g.withTarget}`)
  return parts.join(' · ')
}

// ---------- форма ----------
const editing = ref(null)
const form = reactive(emptyTargetForm(new Date().getFullYear()))
const fieldErrors = ref({})
const formError = ref('')
const saving = ref(false)

const metricOptions = computed(() => {
  const list = availableMetrics(defs.data.value, data.value, form.year, editing.value?.id ? form.metric_key : '')
  const byCategory = []
  for (const d of list) {
    let g = byCategory.find((x) => x.key === d.category)
    if (!g) byCategory.push(g = { key: d.category, label: CATEGORY_LABELS[d.category] || d.category, items: [] })
    g.items.push(d)
  }
  return byCategory
})
const selectedDef = computed(() => (defs.data.value || []).find((d) => d.key === form.metric_key) || null)
const directionHint = computed(() => {
  const d = selectedDef.value?.direction
  if (d === 'lower_is_better') return 'Меньше — лучше: цель достигнута, если факт не выше цели'
  if (d === 'higher_is_better') return 'Больше — лучше: цель достигнута, если факт не ниже цели'
  return selectedDef.value ? 'Направление метрики не задано — для оценки считается «больше — лучше»' : ''
})

function open(row = null) {
  editing.value = row || {}
  Object.assign(form, row ? targetToForm(row) : emptyTargetForm(latest.value?.year || new Date().getFullYear()))
  fieldErrors.value = {}
  formError.value = ''
}
async function save() {
  const isEdit = !!editing.value.id
  const { body, errors } = targetPayload(form, { editing: isEdit })
  fieldErrors.value = errors
  formError.value = ''
  if (Object.keys(errors).length) return
  saving.value = true
  try {
    if (isEdit) await hrApi.updateTarget(editing.value.id, body)
    else await hrApi.createTarget(body)
    toastOk(isEdit ? 'Цель сохранена' : 'Цель добавлена')
    editing.value = null
    reload()
  } catch (e) {
    formError.value = e.message
    fieldErrors.value = e.fields || {}
  } finally {
    saving.value = false
  }
}
async function remove(row) {
  const ok = await confirm({ title: 'Удалить цель?', message: `${row.metric_label} — ${row.label || row.year}`, confirmText: 'Удалить', danger: true })
  if (!ok) return
  try { await hrApi.deleteTarget(row.id) } catch { return } // ошибку показал клиент API
  toastOk('Цель удалена')
  reload()
}
</script>

<template>
  <div class="page">
    <PageHeader title="Цели" description="Целевые и справочные значения метрик и их выполнение по последним данным">
      <PdfButton report="hr/targets" />
      <button v-if="canManage" class="btn btn-primary" type="button" @click="open()"><AppIcon name="plus" :size="15" />Добавить цель</button>
    </PageHeader>

    <div v-if="loading && !data" class="grid grid-kpi"><div v-for="i in 4" :key="i" class="skeleton" style="height: 112px" /></div>

    <EmptyState v-else-if="data && !data.length" icon="target" title="Целей пока нет"
                :text="canManage ? 'Задайте целевые значения метрик на год — здесь появится их выполнение по последним данным.' : 'Цели задаёт пользователь с уровнем доступа «Управление».'">
      <button v-if="canManage" class="btn btn-primary" type="button" @click="open()"><AppIcon name="plus" :size="15" />Добавить цель</button>
    </EmptyState>

    <template v-else-if="data">
      <section v-if="latest" class="stack">
        <div class="section-title"><h2>Выполнение целей {{ latest.year }} года</h2><span class="muted">по последнему заполненному месяцу года</span></div>
        <div class="grid grid-kpi">
          <KpiCard :label="`Целей на ${latest.year} год`" :value="latest.withTarget" />
          <KpiCard label="Цель достигнута" :value="latest.counts.green" :light="latest.counts.green ? 'green' : ''" :caption="`из ${latest.withTarget}`" />
          <KpiCard label="Близко к цели" :value="latest.counts.yellow" :light="latest.counts.yellow ? 'yellow' : ''" :caption="`из ${latest.withTarget}`" hint="Отклонение от цели не больше 10%" />
          <KpiCard label="Цель не достигнута" :value="latest.counts.red" :light="latest.counts.red ? 'red' : ''" :caption="`из ${latest.withTarget}`" />
        </div>
      </section>

      <section v-for="g in groups" :key="g.year" class="stack">
        <div class="section-title"><h2>{{ g.year }} год</h2><span class="muted">{{ yearText(g) }}</span></div>
        <div class="targets">
          <TargetCard v-for="row in g.items" :key="row.id" :row="row" :editable="canManage" @edit="open" @remove="remove" />
        </div>
      </section>

      <p class="footnote muted">
        <AppIcon name="info" :size="14" />
        Факт цели — значение из последнего заполненного месяца того же года: цель прошлого года не оценивается
        данными текущего, у цели будущего года факта ещё нет. Статус учитывает направление метрики; «Близко к цели» —
        отклонение не больше 10%. Справочные значения (например, факт прошлого года) не оцениваются и сравниваются
        с последним фактом.
      </p>
    </template>

    <AppModal v-if="editing" :title="editing.id ? 'Изменить цель' : 'Новая цель'" :subtitle="editing.id ? `${editing.metric_label}, ${editing.year} год` : ''" :width="560" @close="editing = null">
      <form id="target-form" class="form-grid" @submit.prevent="save">
        <label class="field full"><span>Метрика</span>
          <select v-model="form.metric_key" class="select" :class="{ invalid: fieldErrors.metric_key }" :disabled="!!editing.id">
            <option value="" disabled>Выберите метрику</option>
            <optgroup v-for="g in metricOptions" :key="g.key" :label="g.label">
              <option v-for="d in g.items" :key="d.key" :value="d.key">{{ d.label }}{{ d.unit ? `, ${d.unit}` : '' }}</option>
            </optgroup>
          </select>
          <span v-if="fieldErrors.metric_key" class="error">{{ fieldErrors.metric_key }}</span>
          <span v-else-if="directionHint" class="help">{{ directionHint }}</span>
          <span v-else-if="!editing.id && !metricOptions.length" class="help">На этот год цели заданы для всех метрик</span>
        </label>
        <label class="field"><span>Год</span>
          <input v-model.number="form.year" class="input num" :class="{ invalid: fieldErrors.year }" type="number" min="2000" max="2100" :disabled="!!editing.id" />
          <span v-if="fieldErrors.year" class="error">{{ fieldErrors.year }}</span>
        </label>
        <label class="field"><span>Подпись</span>
          <input v-model="form.label" class="input" :class="{ invalid: fieldErrors.label }" maxlength="200" :placeholder="`Цель ${form.year || ''}`" />
          <span v-if="fieldErrors.label" class="error">{{ fieldErrors.label }}</span>
        </label>
        <label class="field"><span>Целевое значение{{ selectedDef?.unit ? `, ${selectedDef.unit}` : '' }}</span>
          <input v-model="form.target_value" class="input num" :class="{ invalid: fieldErrors.target_value }" inputmode="decimal" autocomplete="off" />
          <span v-if="fieldErrors.target_value" class="error">{{ fieldErrors.target_value }}</span>
        </label>
        <label class="field"><span>Справочное значение{{ selectedDef?.unit ? `, ${selectedDef.unit}` : '' }}</span>
          <input v-model="form.reference_value" class="input num" :class="{ invalid: fieldErrors.reference_value }" inputmode="decimal" autocomplete="off" placeholder="Например, факт прошлого года" />
          <span v-if="fieldErrors.reference_value" class="error">{{ fieldErrors.reference_value }}</span>
        </label>
        <label class="field full"><span>Описание</span>
          <textarea v-model="form.description" class="textarea" :class="{ invalid: fieldErrors.description }" rows="2" maxlength="2000" placeholder="Необязательно" />
          <span v-if="fieldErrors.description" class="error">{{ fieldErrors.description }}</span>
        </label>
        <label class="field full"><span>Источник</span>
          <input v-model="form.source" class="input" :class="{ invalid: fieldErrors.source }" maxlength="300" placeholder="Например, план службы персонала на год" />
          <span v-if="fieldErrors.source" class="error">{{ fieldErrors.source }}</span>
        </label>
      </form>
      <p v-if="formError" class="error form-error">{{ formError }}</p>
      <template #footer>
        <button class="btn" type="button" @click="editing = null">Отмена</button>
        <button class="btn btn-primary" type="submit" form="target-form" :disabled="saving">{{ saving ? 'Сохранение…' : 'Сохранить' }}</button>
      </template>
    </AppModal>
  </div>
</template>

<style scoped>
.targets { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: var(--sp-4); }
.footnote { display: flex; align-items: flex-start; gap: 8px; font-size: var(--fs-sm); max-width: 860px; }
.footnote svg { margin-top: 3px; }
.error { color: var(--light-red); font-size: var(--fs-sm); }
.form-error { margin-top: 10px; }
.input:disabled, .select:disabled { opacity: .6; cursor: not-allowed; background-color: var(--surface-2); }
</style>
