<script setup>
import { computed, reactive, ref, watch } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import AppModal from '@/components/ui/AppModal.vue'
import DimensionControl from './DimensionControl.vue'
import { accessApi } from '@/api/access'
import {
  accessProfileBody, accessProfileErrors, accessProfileForm, DIMENSIONS, LEVEL_HINTS, LEVEL_LABELS, LEVELS, MAX_DRILL_DEPTH,
  SERVICE_ICONS, suggestProfileKey,
} from '@/domain/access'
import { formFieldErrors } from '@/domain/admin'
import { plural } from '@/utils/format'

/** Профиль доступа: название, ключ (при создании), описание, измерения доступа и уровни служб. */
const props = defineProps({
  profile: { type: Object, default: null },
  services: { type: Array, default: () => [] },
  maxDepth: { type: Number, default: MAX_DRILL_DEPTH },
})
const emit = defineEmits(['close', 'saved'])

const isNew = computed(() => !props.profile)
const form = reactive(accessProfileForm(props.profile))
const keyTouched = ref(false)
const saving = ref(false)
const formError = ref('')
const fieldErrors = ref({})
const showLater = ref(false)

watch(() => form.name, (name) => {
  if (isNew.value && !keyTouched.value) form.key = suggestProfileKey(name)
})

const dashboards = computed(() => props.services.filter((s) => s.has_dashboard))
const later = computed(() => props.services.filter((s) => !s.has_dashboard))
const shownLater = computed(() => (showLater.value ? later.value : later.value.filter((s) => form.service_levels[s.key])))
const dirty = computed(() => isNew.value || Object.keys(accessProfileBody(form, props.profile)).length > 0)
const usersWord = (n) => plural(n, ['пользователя', 'пользователей', 'пользователей'])

function setLevel(key, level) {
  const next = { ...form.service_levels }
  if (level) next[key] = level
  else delete next[key]
  form.service_levels = next
}

async function save() {
  formError.value = ''
  fieldErrors.value = accessProfileErrors(form, { isNew: isNew.value })
  if (Object.keys(fieldErrors.value).length) return
  saving.value = true
  try {
    const body = accessProfileBody(form, props.profile)
    const saved = isNew.value ? await accessApi.createProfile(body) : await accessApi.updateProfile(props.profile.id, body)
    emit('saved', saved)
  } catch (e) {
    formError.value = e.message
    fieldErrors.value = formFieldErrors(e.fields)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <AppModal :title="isNew ? 'Новый профиль доступа' : `Профиль «${profile.name}»`"
            :subtitle="isNew ? 'Шаблон прав для группы сотрудников' : profile.users_count ? `Изменения сразу действуют на ${profile.users_count} ${usersWord(profile.users_count)}` : 'Профиль пока никому не назначен'"
            :width="'min(780px, calc(100vw - 48px))'" @close="emit('close')">
    <form id="profile-form" class="sections" novalidate @submit.prevent="save">
      <section class="form-grid">
        <label class="field"><span>Название</span>
          <input v-model="form.name" name="name" class="input" :class="{ invalid: fieldErrors.name }" maxlength="120" required placeholder="Финансовый контролёр" />
          <span v-if="fieldErrors.name" class="error">{{ fieldErrors.name }}</span>
        </label>
        <label class="field"><span>Ключ</span>
          <input v-model="form.key" name="key" class="input mono" :class="{ invalid: fieldErrors.key }" :disabled="!isNew" maxlength="40" placeholder="fin-control"
                 autocapitalize="off" spellcheck="false" @input="keyTouched = true" />
          <span v-if="fieldErrors.key" class="error">{{ fieldErrors.key }}</span>
          <span v-else class="help">{{ isNew ? 'Латиница; по ключу профиль назначается группам домена' : 'Ключ не меняется — на него ссылаются настройки входа по домену' }}</span>
        </label>
        <label class="field full"><span>Описание</span>
          <textarea v-model="form.description" class="textarea" rows="2" maxlength="2000" placeholder="Кому подходит и что даёт" />
        </label>
      </section>

      <section class="sect">
        <h3>Что видит</h3>
        <ul class="dims">
          <li v-for="d in DIMENSIONS" :key="d.key" class="dim-row" :data-dimension="d.key">
            <div class="dim-title"><b>{{ d.label }}</b><small>{{ d.hint }}</small></div>
            <DimensionControl v-model="form[d.key]" :dimension="d.key" :max-depth="maxDepth" :name="d.label" />
          </li>
        </ul>
      </section>

      <section class="sect">
        <h3>Службы</h3>
        <div class="svc-list">
          <label v-for="s in [...dashboards, ...shownLater]" :key="s.key" class="svc" :class="{ chosen: form.service_levels[s.key] }" :data-service="s.key">
            <span class="svc-name"><AppIcon :name="SERVICE_ICONS[s.key] || 'grid'" :size="14" />{{ s.title }}<small v-if="!s.has_dashboard">дашборд позже</small></span>
            <select class="select select-sm" :value="form.service_levels[s.key] || ''" :aria-label="`${s.title}: уровень доступа`" @change="setLevel(s.key, $event.target.value)">
              <option value="">Нет доступа</option>
              <option v-for="l in LEVELS" :key="l" :value="l" :title="LEVEL_HINTS[l]">{{ LEVEL_LABELS[l] }}</option>
            </select>
          </label>
        </div>
        <button v-if="later.length" class="link-btn" type="button" @click="showLater = !showLater">
          <AppIcon :name="showLater ? 'chevron-up' : 'chevron-down'" :size="13" />{{ showLater ? 'Скрыть службы без дашборда' : `Службы без дашборда (${later.length})` }}
        </button>
        <p class="help">Службы без уровня в профиле выдаются пользователю лично; «Нет доступа» лично скрывает службу, даже если её даёт профиль.</p>
      </section>
    </form>
    <p v-if="formError" class="form-error" role="alert"><AppIcon name="alert" :size="14" />{{ formError }}</p>
    <template #footer>
      <button class="btn" type="button" @click="emit('close')">Отмена</button>
      <button class="btn btn-primary" type="submit" form="profile-form" :disabled="saving || !dirty" data-testid="profile-save">
        {{ saving ? 'Сохранение…' : isNew ? 'Создать профиль' : 'Сохранить' }}
      </button>
    </template>
  </AppModal>
</template>

<style scoped>
.sections { display: flex; flex-direction: column; gap: 20px; }
.sect { display: flex; flex-direction: column; gap: 10px; }
.sect h3 { font-size: var(--fs-base); font-weight: 650; }
.mono { font-family: var(--font-mono); font-size: var(--fs-sm); }
.help { font-size: var(--fs-xs); color: var(--muted); }
.error { font-size: var(--fs-xs); color: var(--light-red); }
.dims { list-style: none; margin: 0; padding: 0; border: 1px solid var(--border); border-radius: var(--radius-lg); overflow: hidden; }
.dim-row { display: grid; grid-template-columns: minmax(170px, 230px) minmax(0, 1fr); gap: 8px 16px; align-items: center; padding: 11px 14px; border-bottom: 1px solid var(--border); }
.dim-row:last-child { border-bottom: 0; }
.dim-title { display: flex; flex-direction: column; line-height: 1.3; }
.dim-title b { font-size: var(--fs-sm); font-weight: 600; }
.dim-title small { font-size: var(--fs-xs); color: var(--muted); }
.svc-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 8px; }
.svc { display: flex; flex-direction: column; gap: 6px; padding: 10px 12px; border: 1px solid var(--border); border-radius: var(--radius); transition: border-color var(--t-fast), background var(--t-fast); }
.svc.chosen { border-color: color-mix(in srgb, var(--brand) 40%, var(--border)); background: color-mix(in srgb, var(--brand) 3%, var(--surface)); }
.svc-name { display: flex; align-items: center; gap: 7px; font-size: var(--fs-sm); font-weight: 600; }
.svc-name :deep(svg) { color: var(--muted); flex: 0 0 auto; }
.svc-name small { margin-left: auto; font-weight: 500; font-size: var(--fs-xs); color: var(--faint); }
.link-btn { align-self: flex-start; display: inline-flex; align-items: center; gap: 4px; padding: 0; border: 0; background: none; color: var(--accent); font-size: var(--fs-sm); cursor: pointer; }
.link-btn:hover { text-decoration: underline; }
.form-error { display: flex; align-items: center; gap: 6px; margin-top: 12px; font-size: var(--fs-sm); color: var(--light-red); }
@media (max-width: 640px) {
  .dim-row { grid-template-columns: minmax(0, 1fr); }
}
</style>
