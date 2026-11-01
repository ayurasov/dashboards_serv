<script setup>
import { computed, reactive, ref, watch } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import AppModal from '@/components/ui/AppModal.vue'
import SegmentedControl from '@/components/ui/SegmentedControl.vue'
import ToggleSwitch from '@/components/admin/ToggleSwitch.vue'
import RuleBands from './RuleBands.vue'
import StatusChip from './StatusChip.vue'
import { reportsApi } from '@/api/reports'
import { evaluateRule, parseInput, toInput } from '@/domain/reports'

/**
 * Показатель каталога: источник (вводится по подразделениям или вычисляется из данных службы),
 * класс данных, направление, свёртка по структуре, правило светофора (пороги или отклонение от
 * цели) с живым предпросмотром полос, где значение ожидается, служба-владелец. Справочник — /meta.
 */
const props = defineProps({
  indicator: { type: Object, default: null },
  meta: { type: Object, required: true },
})
const emit = defineEmits(['close', 'saved'])
const editing = computed(() => !!props.indicator)

const NUMBERS = ['green_threshold', 'yellow_threshold', 'green_deviation', 'yellow_deviation', 'default_target']
function initial(ind) {
  return {
    source_type: ind?.source_type || 'manual', source_key: ind?.source_key || '',
    key: ind?.key || '', name: ind?.name || '', description: ind?.description || '', unit: ind?.unit || '',
    data_class: ind?.data_class || 'operational', direction: ind?.direction || 'higher_is_better', rollup: ind?.rollup || 'sum',
    rule_type: ind?.rule_type || 'threshold',
    ...Object.fromEntries(NUMBERS.map((k) => [k, toInput(ind?.[k])])),
    owner_service: ind?.owner_service || '', expected_kinds: [...(ind?.expected_kinds || [])],
    sort_order: ind?.sort_order ?? 100, is_active: ind?.is_active ?? true,
  }
}
const form = reactive(initial(props.indicator))
const errors = ref({})
const formError = ref('')
const busy = ref(false)

const sources = computed(() => props.meta.sources || [])
const source = computed(() => sources.value.find((s) => s.key === form.source_key) || null)
const label = (list, key) => (props.meta[list] || []).find((x) => x.key === key)?.label || key
const option = (list) => (props.meta[list] || []).map((x) => ({ value: x.key, label: x.label }))
const sourceOptions = [
  { value: 'manual', label: 'Вводится по подразделениям' },
  { value: 'computed', label: 'Из данных службы' },
]

// Источник вычисляемого показателя задаёт единицу, направление, свёртку и класс данных
watch(() => form.source_key, (key) => {
  if (editing.value) return
  const s = sources.value.find((x) => x.key === key)
  if (!s) return
  Object.assign(form, { unit: s.unit, direction: s.direction, rollup: s.rollup, data_class: s.data_class })
  if (!form.name.trim()) form.name = s.name
  if (!form.key.trim()) form.key = s.key
})

const parsed = computed(() => Object.fromEntries(NUMBERS.map((k) => [k, parseInput(form[k])])))
const rule = computed(() => ({
  direction: form.direction, rule_type: form.rule_type, unit: form.unit,
  ...Object.fromEntries(NUMBERS.map((k) => [k, parsed.value[k].ok ? parsed.value[k].value : null])),
}))
const sample = ref('')
const sampleTarget = ref('')
const sampleStatus = computed(() => {
  const v = parseInput(sample.value)
  if (!v.ok || v.value === null) return null
  const t = parseInput(sampleTarget.value)
  return evaluateRule(rule.value, v.value, t.ok && t.value !== null ? t.value : rule.value.default_target)
})

function toggleKind(value) {
  form.expected_kinds = form.expected_kinds.includes(value) ? form.expected_kinds.filter((k) => k !== value) : [...form.expected_kinds, value]
}

function body() {
  const bad = {}
  for (const k of NUMBERS) if (!parsed.value[k].ok) bad[k] = 'Нужно число'
  if (!form.name.trim()) bad.name = 'Обязательное поле'
  if (!editing.value && !/^[a-z][a-z0-9_.-]{1,79}$/.test(form.key.trim())) bad.key = 'Латиница, цифры, «.», «_», «-»; начинается с буквы'
  if (form.source_type === 'manual' && !form.owner_service) bad.owner_service = 'Выберите службу, которая вводит значения'
  if (form.source_type === 'computed' && !form.source_key) bad.source_key = 'Выберите источник'
  errors.value = bad
  if (Object.keys(bad).length) return null
  const out = {
    name: form.name.trim(), description: form.description.trim(), unit: form.unit.trim(),
    data_class: form.data_class, direction: form.direction, rollup: form.rollup, rule_type: form.rule_type,
    ...Object.fromEntries(NUMBERS.map((k) => [k, parsed.value[k].value])),
    expected_kinds: form.expected_kinds, sort_order: Number(form.sort_order) || 0, is_active: form.is_active,
  }
  if (form.source_type === 'manual') out.owner_service = form.owner_service
  if (!editing.value) Object.assign(out, { key: form.key.trim(), source_type: form.source_type, source_key: form.source_type === 'computed' ? form.source_key : null })
  return out
}

/** Изменение: только поля, которые отличаются от сохранённых. */
function patchOf(full) {
  const before = initial(props.indicator)
  const patch = {}
  for (const [k, v] of Object.entries(full)) {
    const was = NUMBERS.includes(k) ? parseInput(before[k]).value : before[k]
    if (JSON.stringify(was) !== JSON.stringify(v)) patch[k] = v
  }
  return patch
}

async function save() {
  const full = body()
  if (!full) return
  busy.value = true
  formError.value = ''
  try {
    let saved
    if (editing.value) {
      const patch = patchOf(full)
      saved = Object.keys(patch).length ? await reportsApi.updateIndicator(props.indicator.id, patch) : props.indicator
    } else {
      saved = await reportsApi.createIndicator(full)
    }
    emit('saved', saved)
  } catch (e) {
    errors.value = e.fields || {}
    formError.value = e.message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <AppModal :title="editing ? `Показатель «${indicator.name}»` : 'Новый показатель'" :subtitle="editing ? `Ключ ${indicator.key} · источник не меняется` : 'Показатель сквозного отчёта: откуда значение, как оценивается и сворачивается по структуре'" :width="780" @close="emit('close')">
    <form id="indicator-form" class="ed" novalidate @submit.prevent="save">
      <section class="blk">
        <h3>Источник</h3>
        <SegmentedControl v-if="!editing" v-model="form.source_type" :options="sourceOptions" />
        <p v-else class="fixed"><AppIcon :name="form.source_type === 'computed' ? 'refresh' : 'edit'" :size="14" />{{ form.source_type === 'computed' ? `Из данных службы: ${indicator.source_name || indicator.source_key}` : 'Вводится по подразделениям' }}</p>
        <div v-if="form.source_type === 'computed' && !editing" class="field">
          <span>Данные службы</span>
          <select v-model="form.source_key" class="select" :class="{ invalid: errors.source_key }" data-testid="ind-source">
            <option value="" disabled>Выберите источник</option>
            <optgroup v-for="svc in [...new Set(sources.map((s) => s.service_title))]" :key="svc" :label="svc">
              <option v-for="s in sources.filter((x) => x.service_title === svc)" :key="s.key" :value="s.key">{{ s.name }}</option>
            </optgroup>
          </select>
          <span v-if="errors.source_key" class="error">{{ errors.source_key }}</span>
          <span v-else-if="source" class="help">{{ source.description }}</span>
        </div>
        <div v-if="form.source_type === 'manual'" class="field">
          <span>Служба-владелец</span>
          <select v-model="form.owner_service" class="select" :class="{ invalid: errors.owner_service }" data-testid="ind-owner">
            <option value="" disabled>Выберите службу</option>
            <option v-for="s in meta.services" :key="s.key" :value="s.key">{{ s.title }}</option>
          </select>
          <span v-if="errors.owner_service" class="error">{{ errors.owner_service }}</span>
          <span v-else class="help">Значения вводят сотрудники с уровнем «Ввод данных» к этой службе — в своей области структуры.</span>
        </div>
      </section>

      <section class="blk form-grid">
        <label class="field">
          <span>Название</span>
          <input v-model="form.name" class="input" :class="{ invalid: errors.name }" maxlength="200" data-testid="ind-name" />
          <span v-if="errors.name" class="error">{{ errors.name }}</span>
        </label>
        <label class="field">
          <span>Ключ</span>
          <input v-model="form.key" class="input mono" :class="{ invalid: errors.key }" :readonly="editing" maxlength="80" placeholder="ops.quality" data-testid="ind-key" />
          <span v-if="errors.key" class="error">{{ errors.key }}</span>
          <span v-else class="help">{{ editing ? 'Ключ не меняется — по нему значения в файлах загрузки' : 'Латиница: fin.margin, ops.sla' }}</span>
        </label>
        <label class="field full">
          <span>Описание</span>
          <textarea v-model="form.description" class="textarea" rows="2" maxlength="2000" placeholder="Что измеряет показатель и откуда берутся данные" />
        </label>
        <label class="field">
          <span>Единица</span>
          <input v-model="form.unit" class="input" maxlength="30" placeholder="%, шт., млн ₽" data-testid="ind-unit" />
        </label>
        <label class="field">
          <span>Класс данных</span>
          <select v-model="form.data_class" class="select" :class="{ invalid: errors.data_class }" data-testid="ind-class">
            <option v-for="o in option('data_classes')" :key="o.value" :value="o.value">{{ o.label }}</option>
          </select>
          <span class="help">Видят пользователи с доступом к этому классу; операционные — все.</span>
        </label>
        <div class="field">
          <span>Направление</span>
          <SegmentedControl v-model="form.direction" :options="option('directions')" size="sm" />
        </div>
        <div class="field">
          <span>Свёртка по структуре</span>
          <SegmentedControl v-model="form.rollup" :options="option('rollups')" size="sm" />
          <span class="help">{{ form.rollup === 'none' ? 'Только собственные значения уровня' : `Нет своего значения — ${label('rollups', form.rollup).toLowerCase()} по вложенным подразделениям` }}</span>
        </div>
      </section>

      <section class="blk">
        <div class="blk-head">
          <h3>Светофор</h3>
          <SegmentedControl v-model="form.rule_type" :options="option('rule_types')" size="sm" />
        </div>
        <div v-if="form.direction === 'neutral'" class="fixed muted">Направление «без оценки» — показатель не окрашивается, правило не применяется.</div>
        <div class="form-grid rule">
          <template v-if="form.rule_type === 'threshold'">
            <label class="field">
              <span>Граница нормы {{ form.direction === 'lower_is_better' ? '(не больше)' : '(не меньше)' }}</span>
              <input v-model="form.green_threshold" class="input num" :class="{ invalid: errors.green_threshold }" inputmode="decimal" data-testid="ind-green" />
              <span v-if="errors.green_threshold" class="error">{{ errors.green_threshold }}</span>
            </label>
            <label class="field">
              <span>Граница внимания {{ form.direction === 'lower_is_better' ? '(не больше)' : '(не меньше)' }}</span>
              <input v-model="form.yellow_threshold" class="input num" :class="{ invalid: errors.yellow_threshold }" inputmode="decimal" data-testid="ind-yellow" />
              <span v-if="errors.yellow_threshold" class="error">{{ errors.yellow_threshold }}</span>
            </label>
          </template>
          <template v-else>
            <label class="field">
              <span>Норма — отклонение от цели до, %</span>
              <input v-model="form.green_deviation" class="input num" :class="{ invalid: errors.green_deviation }" inputmode="decimal" data-testid="ind-green-dev" />
              <span v-if="errors.green_deviation" class="error">{{ errors.green_deviation }}</span>
            </label>
            <label class="field">
              <span>Внимание — отклонение до, %</span>
              <input v-model="form.yellow_deviation" class="input num" :class="{ invalid: errors.yellow_deviation }" inputmode="decimal" data-testid="ind-yellow-dev" />
              <span v-if="errors.yellow_deviation" class="error">{{ errors.yellow_deviation }}</span>
            </label>
          </template>
          <label class="field">
            <span>Цель по умолчанию</span>
            <input v-model="form.default_target" class="input num" :class="{ invalid: errors.default_target }" inputmode="decimal" placeholder="—" />
            <span v-if="errors.default_target" class="error">{{ errors.default_target }}</span>
            <span v-else class="help">Цель уровня и месяца вводится вместе со значением.</span>
          </label>
        </div>
        <div class="preview">
          <RuleBands :rule="rule" />
          <div class="try">
            <span>Проверить:</span>
            <input v-model="sample" class="input input-sm num" inputmode="decimal" placeholder="значение" aria-label="Значение для проверки" />
            <input v-if="form.rule_type === 'target'" v-model="sampleTarget" class="input input-sm num" inputmode="decimal" :placeholder="form.default_target || 'цель'" aria-label="Цель для проверки" />
            <StatusChip v-if="sampleStatus" :status="sampleStatus" />
          </div>
        </div>
      </section>

      <section class="blk">
        <h3>Где ожидается значение</h3>
        <div class="kinds" role="group" aria-label="Типы уровней структуры">
          <button v-for="k in meta.unit_kinds" :key="k.value" type="button" class="kind" :class="{ on: form.expected_kinds.includes(k.value) }" :style="{ '--kind': k.color }"
                  :aria-pressed="form.expected_kinds.includes(k.value)" @click="toggleKind(k.value)">
            <i />{{ k.label }}
          </button>
        </div>
        <p class="help">{{ form.expected_kinds.length ? 'Незаполненное значение у этих уровней — «Нет данных» и критичное нарушение полноты.' : 'Не выбрано — значение ожидается только там, где оно есть: пропуски не отмечаются.' }}</p>
      </section>

      <section class="blk row-end">
        <label class="field order"><span>Порядок</span><input v-model="form.sort_order" class="input num" type="number" min="0" max="100000" /></label>
        <ToggleSwitch v-model="form.is_active" label="Показатель активен" title="Выключенный показатель не попадает в отчёты; значения сохраняются" />
      </section>

      <p v-if="formError" class="form-error" role="alert"><AppIcon name="alert" :size="14" />{{ formError }}</p>
    </form>
    <template #footer>
      <button class="btn" type="button" @click="emit('close')">Отмена</button>
      <button class="btn btn-primary" type="submit" form="indicator-form" :disabled="busy" data-testid="ind-save">{{ busy ? 'Сохраняю…' : editing ? 'Сохранить' : 'Добавить показатель' }}</button>
    </template>
  </AppModal>
</template>

<style scoped>
.ed { display: flex; flex-direction: column; gap: 18px; }
.blk { display: flex; flex-direction: column; gap: 10px; }
.blk.form-grid { display: grid; }
.blk h3 { font-size: var(--fs-xs); font-weight: 650; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); }
.blk-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; }
.fixed { display: flex; align-items: center; gap: 7px; padding: 8px 12px; border-radius: var(--radius); background: var(--surface-2); font-size: var(--fs-sm); color: var(--text-2); }
.mono { font-family: var(--font-mono); font-size: var(--fs-sm); }
.num { text-align: right; font-variant-numeric: tabular-nums; }
.rule { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.preview { display: flex; flex-direction: column; gap: 10px; padding: 14px; border-radius: 12px; border: 1px solid var(--border); background: var(--surface-2); }
.try { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; font-size: var(--fs-sm); color: var(--muted); }
.try .input { width: 110px; }
.kinds { display: flex; flex-wrap: wrap; gap: 6px; }
.kind { display: inline-flex; align-items: center; gap: 6px; height: 28px; padding: 0 11px; border-radius: var(--radius-pill); border: 1px solid var(--border); background: var(--surface); color: var(--text-2); font-size: var(--fs-sm); cursor: pointer; }
.kind i { width: 7px; height: 7px; border-radius: 50%; background: var(--kind); }
.kind.on { border-color: color-mix(in srgb, var(--kind) 60%, var(--border)); background: color-mix(in srgb, var(--kind) 12%, var(--surface)); color: var(--text); font-weight: 600; }
.help { font-size: var(--fs-xs); color: var(--muted); }
.field :deep(.seg), .blk > :deep(.seg) { align-self: flex-start; }
.row-end { flex-direction: row; align-items: flex-end; justify-content: space-between; gap: 16px; }
.order { width: 140px; }
.form-error { display: flex; align-items: flex-start; gap: 6px; font-size: var(--fs-sm); color: var(--light-red); }
@media (max-width: 640px) {
  .rule { grid-template-columns: minmax(0, 1fr); }
}
</style>
