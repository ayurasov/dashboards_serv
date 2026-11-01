<script setup>
import { computed, reactive, ref } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import AppModal from '@/components/ui/AppModal.vue'
import { tpApi } from '@/api/services'
import { toastOk } from '@/composables/useToast'
import { formatDateTime } from '@/utils/format'
import { isoWeeksInYear, parseDecimal, shortLabel, weekRangeText } from '@/domain/naumen'

/**
 * Неделя недельного отчёта ТП: год, номер недели, примечание и показатели по группам.
 * row — редактируемая неделя (null — новая), groups — столбцы по группам, defaults — { year, week } новой недели.
 */
const props = defineProps({
  row: { type: Object, default: null },
  groups: { type: Array, required: true },
  defaults: { type: Object, default: () => ({}) },
  canDelete: { type: Boolean, default: false },
})
const emit = defineEmits(['close', 'saved', 'delete'])

const isNew = computed(() => !props.row?.id)
const keys = computed(() => props.groups.flatMap((g) => g.columns.map((c) => c.key)))
const toText = (v) => (v === null || v === undefined ? '' : String(v).replace('.', ','))

const form = reactive({
  year: props.row?.year ?? props.defaults.year ?? new Date().getFullYear(),
  week: props.row?.week ?? props.defaults.week ?? 1,
  note: props.row?.note ?? '',
  values: Object.fromEntries(props.groups.flatMap((g) => g.columns).map((c) => [c.key, toText(props.row?.[c.key])])),
})
const errors = ref({})
const formError = ref('')
const saving = ref(false)

const weeksInYear = computed(() => (form.year >= 2000 && form.year <= 2100 ? isoWeeksInYear(Number(form.year)) : 53))
const weekDates = computed(() => (form.week >= 1 && form.week <= weeksInYear.value ? weekRangeText(form.year, form.week) : ''))
const filled = (g) => g.columns.filter((c) => String(form.values[c.key] ?? '').trim() !== '').length

function validate() {
  const out = {}
  const year = Number(form.year)
  const week = Number(form.week)
  if (!Number.isInteger(year) || year < 2000 || year > 2100) out.year = 'Год от 2000 до 2100'
  if (!Number.isInteger(week) || week < 1) out.week = 'Номер недели — целое число от 1'
  else if (!out.year && week > weeksInYear.value) out.week = `В ${year} году ${weeksInYear.value} недели`
  for (const key of keys.value) {
    if (Number.isNaN(parseDecimal(form.values[key]))) out[key] = 'Введите число'
  }
  return out
}

async function save() {
  formError.value = ''
  errors.value = validate()
  if (Object.keys(errors.value).length) {
    formError.value = 'Проверьте отмеченные поля'
    return
  }
  const body = { year: Number(form.year), week: Number(form.week), note: form.note.trim() }
  for (const key of keys.value) body[key] = parseDecimal(form.values[key])
  saving.value = true
  try {
    const saved = isNew.value ? await tpApi.createReport(body) : await tpApi.updateReport(props.row.id, body)
    toastOk(isNew.value ? `Неделя ${saved.period} добавлена` : `Неделя ${saved.period} сохранена`)
    emit('saved', saved)
  } catch (e) {
    errors.value = e.fields || {}
    if (!Object.keys(errors.value).length) formError.value = e.message
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <AppModal :title="isNew ? 'Новая неделя отчёта' : `Неделя ${row.period}`"
            :subtitle="isNew ? 'Пустые поля сохранятся без значения' : row.updated_at ? `Последнее изменение ${formatDateTime(row.updated_at)}` : ''" :width="820" @close="emit('close')">
    <form id="tp-week-form" class="stack form" novalidate @submit.prevent="save">
      <section class="group">
        <div class="base">
          <label class="field"><span>Год</span>
            <input v-model.number="form.year" class="input num" :class="{ invalid: errors.year }" type="number" min="2000" max="2100" required />
            <span v-if="errors.year" class="error">{{ errors.year }}</span>
          </label>
          <label class="field"><span>Номер недели</span>
            <input v-model.number="form.week" class="input num" :class="{ invalid: errors.week }" type="number" min="1" :max="weeksInYear" required />
            <span v-if="errors.week" class="error">{{ errors.week }}</span>
            <span v-else-if="weekDates" class="help">{{ weekDates }}</span>
          </label>
          <label class="field note"><span>Примечание</span>
            <input v-model="form.note" class="input" maxlength="2000" placeholder="Например: праздничная неделя" />
          </label>
        </div>
      </section>

      <section v-for="g in groups" :key="g.key" class="group">
        <header class="group-head">
          <h3>{{ g.label }}</h3>
          <span class="muted num">{{ filled(g) }} из {{ g.columns.length }}</span>
        </header>
        <div class="metrics">
          <label v-for="c in g.columns" :key="c.key" class="field" :title="c.label">
            <span class="metric-label">{{ shortLabel(c.label, g.label) }}</span>
            <span class="affix" :class="{ invalid: errors[c.key] }">
              <input v-model="form.values[c.key]" class="num" inputmode="decimal" autocomplete="off" :aria-label="c.label" />
              <span v-if="c.unit" class="unit">{{ c.unit }}</span>
            </span>
            <span v-if="errors[c.key]" class="error">{{ errors[c.key] }}</span>
          </label>
        </div>
      </section>
    </form>

    <template #footer>
      <button v-if="!isNew && canDelete" class="btn btn-ghost btn-danger" type="button" @click="emit('delete', row)">
        <AppIcon name="trash" :size="14" />Удалить неделю
      </button>
      <span class="spacer" />
      <p v-if="formError" class="form-error" role="alert"><AppIcon name="alert" :size="14" />{{ formError }}</p>
      <button class="btn" type="button" @click="emit('close')">Отмена</button>
      <button class="btn btn-primary" type="submit" form="tp-week-form" :disabled="saving">{{ saving ? 'Сохранение…' : 'Сохранить' }}</button>
    </template>
  </AppModal>
</template>

<style scoped>
.form { gap: var(--sp-5); }
.base { display: grid; grid-template-columns: 120px 160px minmax(0, 1fr); gap: var(--sp-4); align-items: start; }
.group + .group { padding-top: var(--sp-4); border-top: 1px solid var(--border); }
.group-head { display: flex; align-items: baseline; gap: var(--sp-2); margin-bottom: var(--sp-3); }
.group-head h3 { font-size: var(--fs-xs); font-weight: 650; text-transform: uppercase; letter-spacing: .05em; color: var(--text-2); }
.group-head .muted { font-size: var(--fs-xs); }
.metrics { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--sp-3) var(--sp-4); }
.metric-label { font-size: var(--fs-sm); font-weight: 520; color: var(--text-2); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.affix { display: flex; align-items: center; height: 34px; border: 1px solid var(--border-strong); border-radius: var(--radius); background: var(--surface); transition: border-color var(--t-fast), box-shadow var(--t-fast); }
.affix:hover { border-color: var(--faint); }
.affix:focus-within { border-color: var(--accent); box-shadow: 0 0 0 3px var(--focus); }
.affix.invalid { border-color: var(--light-red); }
.affix input { flex: 1; min-width: 0; height: 100%; padding: 0 11px; border: 0; outline: 0; background: transparent; color: var(--text); text-align: right; }
.affix .unit { padding-right: 11px; font-size: var(--fs-sm); color: var(--muted); }
.form-error { display: inline-flex; align-items: center; gap: 6px; margin-right: var(--sp-2); font-size: var(--fs-sm); color: var(--light-red); }
@media (max-width: 720px) {
  .base { grid-template-columns: 1fr 1fr; }
  .base .note { grid-column: 1 / -1; }
  .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
