<script setup>
import { computed, ref, watch } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import SideDrawer from '@/components/admin/SideDrawer.vue'
import TransferBanner from '@/components/transfer/TransferBanner.vue'
import RichText from '@/components/ui/RichText.vue'
import SchemaForm from './SchemaForm.vue'
import ScheduleEditor from './ScheduleEditor.vue'
import CheckResult from './CheckResult.vue'
import { integrationsApi } from '@/api/integrations'
import { toastOk } from '@/composables/useToast'
import {
  bindingChanges, initialSecrets, initialValues, kindIcon, quoted, rebindSecrets, scheduleDraft, scheduleErrors, schedulePayload,
  settingsPayload, validateSettings,
} from '@/domain/integrations'

/**
 * Настройки подключения: название, поля вида (форма строится по описанию), расписание. «Проверить»
 * проверяет введённые значения до сохранения (у нового — POST /check, у сохранённого — /{id}/check с
 * несохранёнными значениями); подробные ошибки видит администратор. Секреты привязаны к адресу:
 * адрес изменён — секреты нужно ввести заново.
 */
const props = defineProps({
  kind: { type: Object, required: true },
  integration: { type: Object, default: null },
})
const emit = defineEmits(['close', 'saved'])

const isNew = computed(() => !props.integration)
const name = ref(props.integration?.name || props.kind.title)
const values = ref(initialValues(props.kind.fields, props.integration?.config))
const secrets = ref(initialSecrets(props.kind.fields, props.integration))
const schedule = ref(scheduleDraft(props.integration?.schedule, props.kind))
const errors = ref({})
const formError = ref('')
const busy = ref('')
const check = ref(null)
const checkedSignature = ref('')
const saved = computed(() => props.integration?.secret_fields || [])

// Сохранённый секрет не читается (сменился SECRET_KEY, адрес) — его нужно ввести заново. Секреты привязаны
// к адресу из полей secret_url_fields: изменили любое из них — секреты вводятся заново (предупреждение — до сохранения)
const forceRebind = ref(!!props.integration?.secret_problem)
const changedBinding = computed(() => bindingChanges(props.kind, values.value, props.integration))
const rebind = computed(() => forceRebind.value || changedBinding.value.length > 0)
const savedSecretLabels = computed(() => props.kind.fields.filter((f) => f.secret && saved.value.includes(f.key)).map((f) => f.label))
const rebindText = computed(() => {
  const fields = changedBinding.value.map((f) => `«${f.label}»`).join(', ')
  const what = savedSecretLabels.value.map((l) => `«${l}»`).join(', ') || 'секреты'
  return `Изменено: ${fields}. Сохранённые секреты (${what}) привязаны к прежнему адресу и на новый не уйдут — введите их заново, иначе сохранить не получится.`
})
watch(rebind, (now) => {
  if (now) secrets.value = rebindSecrets(secrets.value)
  else secrets.value = Object.fromEntries(Object.entries(secrets.value).map(([k, s]) => [k, saved.value.includes(k) && s.mode === 'replace' && !s.value ? { mode: 'keep', value: '' } : s]))
}, { immediate: true })

const body = computed(() => settingsPayload(props.kind, values.value, secrets.value))
const signature = computed(() => JSON.stringify([body.value.config, body.value.secrets]))
watch(signature, () => { if (checkedSignature.value && signature.value !== checkedSignature.value) check.value = null })

const fieldErrors = (e) => ({ ...(e?.fields || {}) })

async function runCheck() {
  formError.value = ''
  errors.value = validateSettings(props.kind, values.value, secrets.value)
  if (Object.keys(errors.value).length) {
    formError.value = 'Заполните отмеченные поля — проверка без них невозможна'
    return
  }
  busy.value = 'check'
  check.value = null
  try {
    const { config, secrets: entered } = body.value
    check.value = isNew.value
      ? await integrationsApi.checkDraft({ kind: props.kind.kind, config, secrets: entered })
      : await integrationsApi.check(props.integration.id, { config, secrets: entered })
    checkedSignature.value = signature.value
  } catch (e) {
    errors.value = fieldErrors(e)
    check.value = { ok: false, message: e.message, details: { code: e.code } }
  } finally {
    busy.value = ''
  }
}

async function save() {
  formError.value = ''
  errors.value = {
    ...validateSettings(props.kind, values.value, secrets.value, { name: name.value }),
    ...scheduleErrors(schedule.value, props.kind),
  }
  if (Object.keys(errors.value).length) {
    formError.value = 'Проверьте отмеченные поля'
    return
  }
  busy.value = 'save'
  const { config, secrets: entered, clear_secrets: clear } = body.value
  try {
    let row
    if (isNew.value) {
      row = await integrationsApi.create({ kind: props.kind.kind, name: name.value.trim(), config, secrets: entered, schedule: schedulePayload(schedule.value) })
      // Только что проверено с теми же значениями — проверка сохранённого отмечает подключение проверенным
      let verified = false
      if (check.value?.ok && checkedSignature.value === signature.value) {
        try { verified = !!(await integrationsApi.check(row.id)).ok } catch {}
        if (verified) row = await integrationsApi.get(row.id)
      }
      toastOk(verified ? `Подключение ${quoted(row.name)} создано и проверено — его можно включить` : `Подключение ${quoted(row.name)} создано выключенным: проверьте его и включите`)
    } else {
      row = await integrationsApi.update(props.integration.id, { name: name.value.trim(), config, secrets: entered, clear_secrets: clear, schedule: schedulePayload(schedule.value) })
      toastOk(row.enabled && !row.verified_at ? `Сохранено. Настройки изменились — проверьте подключение ${quoted(row.name)} снова` : `Подключение ${quoted(row.name)} сохранено`)
    }
    emit('saved', row)
  } catch (e) {
    // Адрес изменён, а секреты не введены заново: сохранённые к новому адресу не подходят
    if (e.code === 'secret_rebind_required') {
      forceRebind.value = true
      secrets.value = rebindSecrets(secrets.value)
    }
    formError.value = e.message
    errors.value = fieldErrors(e)
  } finally {
    busy.value = ''
  }
}
</script>

<template>
  <SideDrawer :title="isNew ? `Подключить: ${kind.title}` : `Настройки: ${integration.name}`" :width="720" sheet @close="emit('close')">
    <template #header>
      <div class="eh">
        <span class="k-icon"><AppIcon :name="kindIcon(kind.kind)" :size="18" /></span>
        <div class="eh-text">
          <h2>{{ isNew ? 'Новое подключение' : integration.name }}</h2>
          <p class="muted">{{ kind.title }}</p>
        </div>
      </div>
    </template>

    <form class="editor" novalidate @submit.prevent="save">
      <RichText v-if="kind.description" :text="kind.description" class="kdesc" data-testid="kind-description" />
      <TransferBanner v-if="integration?.secret_problem" tone="warn" title="Сохранённый секрет не подходит" :text="`${integration.secret_problem}. Введите его заново и сохраните.`" data-testid="editor-secret-problem" />
      <TransferBanner v-else-if="changedBinding.length" tone="warn" title="Секреты нужно ввести заново" :text="rebindText" data-testid="editor-rebind" />

      <section class="sec">
        <h3>Название</h3>
        <label class="field">
          <input v-model="name" class="input" :class="{ invalid: errors.name }" maxlength="200" placeholder="Например, «Jira — поддержка»" aria-label="Название подключения" data-testid="integration-name" />
          <small v-if="errors.name" class="error">{{ errors.name }}</small>
        </label>
      </section>

      <section class="sec">
        <h3>Подключение</h3>
        <SchemaForm v-model:values="values" v-model:secrets="secrets" :kind="kind" :errors="errors" :saved="saved" :rebind="rebind" />
      </section>

      <section class="sec check-sec">
        <div class="row-wrap">
          <button type="button" class="btn" :disabled="!!busy" data-testid="editor-check" @click="runCheck"><AppIcon name="activity" :size="15" />{{ busy === 'check' ? 'Проверяю…' : 'Проверить' }}</button>
          <span class="muted">{{ isNew ? 'Проверка введённых значений — до сохранения, ничего не записывается' : 'Проверка с введёнными значениями; без изменений — сохранённых' }}</span>
        </div>
        <CheckResult v-if="check" :result="check" :kind="kind" data-testid="editor-check-result" />
      </section>

      <section class="sec">
        <h3>Расписание</h3>
        <ScheduleEditor v-model="schedule" :kind="kind" :errors="errors" />
      </section>

      <p v-if="formError" class="form-error" role="alert" data-testid="editor-error"><AppIcon name="alert" :size="14" />{{ formError }}</p>
      <button type="submit" class="sr-only" tabindex="-1">Сохранить</button>
    </form>

    <template #footer>
      <span class="foot-note">{{ isNew ? 'Подключение создаётся выключенным: включить можно после успешной проверки.' : 'Изменение адреса или секретов снимает отметку проверки.' }}</span>
      <span class="spacer" />
      <button type="button" class="btn" @click="emit('close')">Отмена</button>
      <button type="button" class="btn btn-primary" :disabled="!!busy" data-testid="editor-save" @click="save"><AppIcon name="check" :size="15" />{{ busy === 'save' ? 'Сохраняю…' : isNew ? 'Создать' : 'Сохранить' }}</button>
    </template>
  </SideDrawer>
</template>

<style scoped>
.eh { display: flex; align-items: center; gap: 12px; min-width: 0; }
.k-icon { width: 38px; height: 38px; flex: 0 0 38px; display: grid; place-items: center; border-radius: 10px; background: var(--brand-soft); color: var(--brand); }
.eh-text { min-width: 0; }
.eh-text h2 { font-size: 16px; overflow-wrap: anywhere; }
.eh-text p { font-size: var(--fs-xs); }
.muted { color: var(--muted); font-size: var(--fs-sm); }
.editor { display: flex; flex-direction: column; gap: 22px; }
.sec { display: flex; flex-direction: column; gap: 10px; }
.sec h3 { font-size: var(--fs-xs); font-weight: 650; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); }
.check-sec { padding: 14px 16px; border: 1px solid var(--border); border-radius: 12px; background: var(--surface-2); }
.error { font-size: var(--fs-xs); color: var(--light-red); }
.form-error { display: flex; align-items: flex-start; gap: 6px; font-size: var(--fs-sm); color: var(--light-red); line-height: 1.45; }
.form-error :deep(svg) { margin-top: 2px; flex: 0 0 auto; }
.foot-note { font-size: var(--fs-xs); color: var(--muted); max-width: 320px; }
@media (max-width: 720px) { .foot-note { display: none; } }
</style>
