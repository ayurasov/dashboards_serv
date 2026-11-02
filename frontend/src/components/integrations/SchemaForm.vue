<script setup>
import { computed, useId } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import RichText from '@/components/ui/RichText.vue'
import ToggleSwitch from '@/components/admin/ToggleSwitch.vue'
import { allowedHostsHint, fieldVisible, isChoiceField, isJsonField, isMonospace, isWideField, jsonRows, parseJsonField } from '@/domain/integrations'

/**
 * Форма настроек подключения по описанию полей вида (GET /api/integrations/kinds → fields): типы
 * string · text · url · password · int · bool · select · multiselect · list · time · json, show_if, подсказки,
 * заполнители, значения по умолчанию, обязательность. Выбор из 2–4 вариантов с длинными подписями («Тип
 * подключения») — списком переключателей, остальные длинные списки — на всю ширину: подпись не обрезается. Секретные поля сервер не возвращает: сохранённый
 * секрет — «задан» с «Заменить» и «Очистить».
 */
const props = defineProps({
  kind: { type: Object, required: true },
  values: { type: Object, required: true },
  secrets: { type: Object, required: true },
  errors: { type: Object, default: () => ({}) },
  // Секреты, сохранённые на сервере (secret_fields подключения)
  saved: { type: Array, default: () => [] },
  // Адрес изменён — сохранённые секреты нужно ввести заново
  rebind: { type: Boolean, default: false },
})
const emit = defineEmits(['update:values', 'update:secrets'])
const uid = useId()

const shown = computed(() => (props.kind.fields || []).filter((f) => fieldVisible(f, props.values)))
const idOf = (f) => `${uid}-${f.key}`
const errorOf = (f) => (isJsonField(f) && jsonError(f)) || props.errors[`${f.secret ? 'secrets' : 'config'}.${f.key}`] || (f.secret && props.errors.secrets) || ''

function setValue(key, value) {
  emit('update:values', { ...props.values, [key]: value })
}
function setSecret(key, patch) {
  emit('update:secrets', { ...props.secrets, [key]: { ...(props.secrets[key] || { mode: 'replace', value: '' }), ...patch } })
}
function toggleOption(f, value) {
  const list = Array.isArray(props.values[f.key]) ? props.values[f.key] : []
  setValue(f.key, list.includes(value) ? list.filter((v) => v !== value) : [...list, value])
}
const isSaved = (f) => props.saved.includes(f.key)
// JSON проверяется сразу при вводе: неверный не сохранится
const jsonError = (f) => (isJsonField(f) ? parseJsonField(props.values[f.key]).error : '')
function formatJson(f) {
  const parsed = parseJsonField(props.values[f.key])
  if (parsed.ok && parsed.value !== null) setValue(f.key, JSON.stringify(parsed.value, null, 2))
}
// Узлы, разрешённые на сервере, — под полем адреса; если адрес вычисляется (скрыт), — под полями адресов
const urlShown = computed(() => shown.value.some((f) => f.key === props.kind.url_field))
const hostsHint = (f) => !!props.kind.allowed_hosts_env && (f.key === props.kind.url_field || (!urlShown.value && f.type === 'url'))
const secretMode = (f) => props.secrets[f.key]?.mode || 'replace'
</script>

<template>
  <div class="schema-form">
    <template v-for="f in shown" :key="f.key">
      <!-- да / нет -->
      <div v-if="f.type === 'bool'" class="sf-field sf-bool" :data-field="f.key">
        <ToggleSwitch :model-value="!!values[f.key]" :label="f.label" @update:model-value="setValue(f.key, $event)" />
        <RichText v-if="f.hint" :text="f.hint" compact :limit="160" />
        <small v-if="errorOf(f)" class="error">{{ errorOf(f) }}</small>
      </div>

      <!-- несколько из списка -->
      <fieldset v-else-if="f.type === 'multiselect'" class="sf-field sf-multi" :data-field="f.key">
        <legend>{{ f.label }}<span v-if="f.required" class="req" aria-hidden="true">*</span></legend>
        <div class="opts">
          <label v-for="o in f.options" :key="o.value" class="opt" :class="{ on: (values[f.key] || []).includes(o.value) }">
            <input type="checkbox" :checked="(values[f.key] || []).includes(o.value)" @change="toggleOption(f, o.value)" />{{ o.label }}
          </label>
        </div>
        <RichText v-if="f.hint" :text="f.hint" compact :limit="160" />
        <small v-if="errorOf(f)" class="error">{{ errorOf(f) }}</small>
      </fieldset>

      <!-- один из 2–4 вариантов с длинными подписями -->
      <fieldset v-else-if="isChoiceField(f)" class="sf-field sf-choice" :data-field="f.key">
        <legend>{{ f.label }}<span v-if="f.required" class="req" aria-hidden="true">*</span></legend>
        <div class="choice-list" role="radiogroup" :aria-label="f.label">
          <label v-for="o in f.options" :key="o.value" class="choice" :class="{ on: values[f.key] === o.value, invalid: errorOf(f) }">
            <input type="radio" :name="idOf(f)" :value="o.value" :checked="values[f.key] === o.value" :data-testid="`choice-${f.key}-${o.value}`" @change="setValue(f.key, o.value)" />
            <span>{{ o.label }}</span>
          </label>
        </div>
        <RichText v-if="f.hint" :text="f.hint" compact :limit="160" />
        <small v-if="errorOf(f)" class="error">{{ errorOf(f) }}</small>
      </fieldset>

      <!-- секрет: задан / заменить / очистить -->
      <div v-else-if="f.secret" class="sf-field sf-secret" :data-field="f.key">
        <label :for="idOf(f)" class="sf-label">{{ f.label }}<span v-if="f.required" class="req" aria-hidden="true">*</span><span class="lock"><AppIcon name="lock" :size="12" />секрет</span></label>
        <div v-if="secretMode(f) === 'keep'" class="secret-state">
          <span class="badge badge-green" :data-testid="`secret-set-${f.key}`"><AppIcon name="check" :size="12" />задан</span>
          <span class="muted">значение хранится зашифрованным и не показывается</span>
          <span class="spacer" />
          <button type="button" class="btn btn-sm" @click="setSecret(f.key, { mode: 'replace', value: '' })">Заменить</button>
          <button v-if="!f.required" type="button" class="btn btn-sm btn-danger" @click="setSecret(f.key, { mode: 'clear', value: '' })">Очистить</button>
        </div>
        <div v-else-if="secretMode(f) === 'clear'" class="secret-state">
          <span class="badge badge-red">будет очищен</span>
          <span class="spacer" />
          <button type="button" class="btn btn-sm" @click="setSecret(f.key, { mode: 'keep' })">Отменить</button>
        </div>
        <div v-else class="secret-input">
          <input :id="idOf(f)" class="input" type="password" autocomplete="new-password" spellcheck="false" :class="{ invalid: errorOf(f) }"
                 :value="secrets[f.key]?.value || ''" :placeholder="isSaved(f) && !rebind ? 'Новое значение' : f.placeholder || ''" :data-testid="`secret-${f.key}`"
                 @input="setSecret(f.key, { mode: 'replace', value: $event.target.value })" />
          <button v-if="isSaved(f) && !rebind" type="button" class="btn btn-sm btn-ghost" @click="setSecret(f.key, { mode: 'keep', value: '' })">Оставить прежнее</button>
        </div>
        <small v-if="rebind && isSaved(f)" class="warn"><AppIcon name="alert" :size="12" />Адрес изменён — секрет привязан к прежнему адресу, введите его заново</small>
        <RichText v-if="f.hint" :text="f.hint" compact :limit="160" />
        <small v-if="errorOf(f)" class="error">{{ errorOf(f) }}</small>
      </div>

      <!-- остальные типы -->
      <div v-else class="sf-field" :class="{ wide: isWideField(f) }" :data-field="f.key">
        <label :for="idOf(f)" class="sf-label">{{ f.label }}<span v-if="f.required" class="req" aria-hidden="true">*</span></label>
        <select v-if="f.type === 'select'" :id="idOf(f)" class="select" :class="{ invalid: errorOf(f) }" :value="values[f.key]" :required="f.required"
                @change="setValue(f.key, $event.target.value)">
          <option v-if="(!f.required && (f.default === null || f.default === undefined || f.default === '')) || !values[f.key]" value="">{{ f.placeholder || 'Не выбрано' }}</option>
          <option v-for="o in f.options" :key="o.value" :value="o.value">{{ o.label }}</option>
        </select>
        <template v-else-if="isMonospace(f)">
          <textarea :id="idOf(f)" class="textarea mono" :class="{ invalid: errorOf(f) }" :rows="jsonRows(values[f.key])" spellcheck="false" autocapitalize="off"
                    :value="values[f.key]" :placeholder="f.placeholder || ''" :required="f.required" :data-testid="`field-${f.key}`"
                    @input="setValue(f.key, $event.target.value)" />
          <div v-if="isJsonField(f)" class="json-bar">
            <span v-if="values[f.key] && !jsonError(f)" class="json-ok">JSON без ошибок</span>
            <button type="button" class="btn btn-sm btn-ghost" :disabled="!values[f.key] || !!jsonError(f)" @click="formatJson(f)">Выровнять</button>
          </div>
        </template>
        <textarea v-else-if="f.type === 'text' || f.type === 'list'" :id="idOf(f)" class="textarea" :class="{ invalid: errorOf(f) }" rows="3" spellcheck="false"
                  :value="values[f.key]" :placeholder="f.placeholder || (f.type === 'list' ? 'По одному значению в строке' : '')" :required="f.required"
                  @input="setValue(f.key, $event.target.value)" />
        <input v-else :id="idOf(f)" class="input" :class="{ invalid: errorOf(f), num: f.type === 'int' }" spellcheck="false" autocomplete="off"
               :type="f.type === 'int' ? 'number' : f.type === 'time' ? 'time' : f.type === 'password' ? 'password' : f.type === 'url' ? 'url' : 'text'"
               :inputmode="f.type === 'int' ? 'numeric' : undefined" :min="f.min ?? undefined" :max="f.max ?? undefined" :step="f.type === 'int' ? 1 : undefined"
               :value="values[f.key]" :placeholder="f.placeholder || (f.type === 'url' ? 'https://' : '')" :required="f.required"
               :data-testid="`field-${f.key}`" @input="setValue(f.key, $event.target.value)" />
        <small v-if="f.type === 'list' && !f.hint" class="help">По одному значению в строке или через запятую</small>
        <small v-if="f.type === 'int' && (f.min !== null && f.min !== undefined || f.max !== null && f.max !== undefined)" class="help">
          <template v-if="f.min !== null && f.min !== undefined && f.max !== null && f.max !== undefined">От {{ f.min }} до {{ f.max }}</template>
          <template v-else-if="f.min !== null && f.min !== undefined">Не меньше {{ f.min }}</template>
          <template v-else>Не больше {{ f.max }}</template>
        </small>
        <RichText v-if="f.hint" :text="f.hint" compact :limit="160" />
        <small v-if="hostsHint(f)" class="help hosts" :class="{ hot: errors[`config.${f.key}`] && /запрещено/.test(errors[`config.${f.key}`]) }">
          <AppIcon name="shield" :size="12" />{{ allowedHostsHint(kind) }}
        </small>
        <small v-if="errorOf(f)" class="error">{{ errorOf(f) }}</small>
      </div>
    </template>
    <p v-if="!shown.length" class="muted none">У этого вида подключения нет настроек.</p>
  </div>
</template>

<style scoped>
.schema-form { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px 18px; }
.sf-field { display: flex; flex-direction: column; gap: 5px; min-width: 0; margin: 0; padding: 0; border: 0; }
.sf-field .select { width: 100%; min-width: 0; text-overflow: ellipsis; }
.sf-field.wide, .sf-secret, .sf-multi, .sf-choice, .none { grid-column: 1 / -1; }
.choice-list { display: flex; flex-direction: column; gap: 4px; }
.choice { display: flex; align-items: flex-start; gap: 9px; padding: 8px 11px; border: 1px solid var(--border-strong); border-radius: var(--radius); font-size: var(--fs-sm); line-height: 1.4; cursor: pointer; overflow-wrap: anywhere; }
.choice input { margin-top: 2px; flex: 0 0 auto; accent-color: var(--accent); }
.choice.on { border-color: var(--accent); background: color-mix(in srgb, var(--accent) 7%, transparent); }
.choice.invalid { border-color: var(--light-red); }
.choice:focus-within { box-shadow: 0 0 0 3px var(--focus); }
.sf-label, legend { display: flex; align-items: center; gap: 4px; font-size: var(--fs-sm); font-weight: 560; color: var(--text-2); padding: 0; }
legend { margin-bottom: 5px; }
.req { color: var(--brand); font-weight: 700; }
.lock { display: inline-flex; align-items: center; gap: 3px; margin-left: 6px; font-size: var(--fs-xs); font-weight: 500; color: var(--muted); }
.help { font-size: var(--fs-xs); color: var(--muted); line-height: 1.4; }
.error { font-size: var(--fs-xs); color: var(--light-red); }
.warn { display: flex; align-items: center; gap: 5px; font-size: var(--fs-xs); color: color-mix(in srgb, var(--light-yellow) 80%, var(--text)); }
.hosts { display: flex; align-items: flex-start; gap: 5px; }
.hosts :deep(svg) { flex: 0 0 auto; margin-top: 1px; }
.hosts.hot { color: var(--light-red); }
.sf-bool { justify-content: center; }
.opts { display: flex; flex-wrap: wrap; gap: 6px; }
.opt { display: inline-flex; align-items: center; gap: 7px; height: 30px; padding: 0 11px; border: 1px solid var(--border-strong); border-radius: var(--radius-pill); font-size: var(--fs-sm); cursor: pointer; }
.opt.on { border-color: var(--accent); background: color-mix(in srgb, var(--accent) 8%, transparent); }
.opt input { accent-color: var(--accent); }
.opt:focus-within { box-shadow: 0 0 0 3px var(--focus); }
.secret-state { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; min-height: 34px; padding: 4px 4px 4px 10px; border: 1px dashed var(--border-strong); border-radius: var(--radius); background: var(--surface-2); }
.secret-state .muted { font-size: var(--fs-xs); color: var(--muted); }
.secret-input { display: flex; gap: 8px; align-items: center; }
.mono { font-family: var(--font-mono); font-size: 12px; line-height: 1.5; white-space: pre; overflow-x: auto; tab-size: 2; }
.json-bar { display: flex; align-items: center; justify-content: flex-end; gap: 10px; margin-top: -2px; }
.json-ok { font-size: var(--fs-xs); color: color-mix(in srgb, var(--light-green) 70%, var(--text)); }
.secret-input .input { flex: 1; }
.muted { color: var(--muted); font-size: var(--fs-sm); }
@media (max-width: 640px) {
  .schema-form { grid-template-columns: minmax(0, 1fr); }
  .secret-state .muted { display: none; }
}
</style>
