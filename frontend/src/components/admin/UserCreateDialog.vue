<script setup>
import { computed, reactive, ref } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import AppModal from '@/components/ui/AppModal.vue'
import SegmentedControl from '@/components/ui/SegmentedControl.vue'
import UnitPicker from './UnitPicker.vue'
import { usersApi } from '@/api/access'
import { useAuthStore } from '@/stores/auth'
import { CAPABILITIES, INDIVIDUAL_LABEL, LEVEL_HINTS, LEVEL_LABELS, LEVELS, profileFacts, SERVICE_ICONS } from '@/domain/access'
import { ACCESS_METHODS, createUserBody, formFieldErrors, newUserForm, ROLE_LABELS, USERNAME_PATTERN, userFormErrors } from '@/domain/admin'

/**
 * Новый пользователь: учётная запись, подразделение, роль, профиль доступа и личные уровни служб,
 * способ входа (временный пароль · вход по домену · без доступа), полномочия (администратору).
 */
const props = defineProps({
  profiles: { type: Array, default: () => [] },
  services: { type: Array, default: () => [] },
  departments: { type: Array, default: () => [] },
  ldapEnabled: { type: Boolean, default: false },
})
const emit = defineEmits(['close', 'created'])

const auth = useAuthStore()
const isAdmin = computed(() => auth.isAdmin)
const ROLE_OPTIONS = [{ value: 'user', label: ROLE_LABELS.user }, { value: 'admin', label: ROLE_LABELS.admin }]
const form = reactive(newUserForm())
const ownPassword = ref(false)
const showPassword = ref(false)
const saving = ref(false)
const formError = ref('')
const fieldErrors = ref({})

const profile = computed(() => props.profiles.find((p) => p.id === form.profile_id) || null)
const facts = computed(() => profileFacts(profile.value, props.services).filter((f) => f.key !== 'services'))
const dashboards = computed(() => props.services.filter((s) => s.has_dashboard))
const methods = computed(() => ACCESS_METHODS.map((m) => ({ ...m, disabled: m.value === 'ldap' && !props.ldapEnabled })))

function inheritedText(key) {
  const level = profile.value?.service_levels?.[key]
  if (!profile.value) return 'Нет доступа'
  return `Как в профиле: ${level ? LEVEL_LABELS[level].toLowerCase() : 'нет'}`
}
function setService(key, level) {
  form.services = { ...form.services, [key]: level }
}
function pickProfile(event) {
  form.profile_id = event.target.value === '' ? null : Number(event.target.value)
}
function toggleCapability(key) {
  form.capabilities = form.capabilities.includes(key) ? form.capabilities.filter((c) => c !== key) : [...form.capabilities, key]
}

async function save() {
  formError.value = ''
  fieldErrors.value = userFormErrors(form, { isNew: true })
  if (Object.keys(fieldErrors.value).length) return
  saving.value = true
  try {
    const body = createUserBody({ ...form, password: ownPassword.value ? form.password : '' }, { isAdmin: isAdmin.value })
    emit('created', await usersApi.create(body))
  } catch (e) {
    formError.value = e.message
    fieldErrors.value = formFieldErrors(e.fields)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <AppModal title="Новый пользователь" subtitle="Учётная запись, место в структуре, доступ и способ входа" :width="'min(820px, calc(100vw - 48px))'" @close="emit('close')">
    <form id="user-create" class="sections" autocomplete="off" novalidate @submit.prevent="save">
      <section class="sect">
        <h3>Учётная запись</h3>
        <div class="form-grid">
          <label class="field"><span>Логин</span>
            <input v-model="form.username" name="username" class="input mono" :class="{ invalid: fieldErrors.username }" required minlength="2" maxlength="100"
                   :pattern="USERNAME_PATTERN" title="Латиница, цифры и . _ @ -" autocapitalize="off" spellcheck="false" placeholder="i.ivanov" />
            <span v-if="fieldErrors.username" class="error">{{ fieldErrors.username }}</span>
            <span v-else class="help">Латиница, цифры и . _ @ -</span>
          </label>
          <label class="field"><span>ФИО</span>
            <input v-model="form.full_name" name="full_name" class="input" :class="{ invalid: fieldErrors.full_name }" required maxlength="200" placeholder="Иванов Иван Иванович" />
            <span v-if="fieldErrors.full_name" class="error">{{ fieldErrors.full_name }}</span>
          </label>
          <label class="field"><span>E-mail</span>
            <input v-model="form.email" name="email" class="input" :class="{ invalid: fieldErrors.email }" type="email" :placeholder="form.access_method === 'ldap' ? 'Обязательно для входа по домену' : 'Необязательно'" />
            <span v-if="fieldErrors.email" class="error">{{ fieldErrors.email }}</span>
          </label>
          <label class="field"><span>Телефон</span>
            <input v-model="form.phone" name="phone" class="input" maxlength="50" placeholder="Необязательно" />
          </label>
          <label class="field"><span>Должность</span>
            <input v-model="form.position" name="position" class="input" maxlength="200" placeholder="Необязательно" />
          </label>
          <div class="field"><span>Подразделение</span>
            <UnitPicker v-model="form.department_id" :departments="departments" :invalid="!!fieldErrors.department_id" label="Подразделение" />
            <span v-if="fieldErrors.department_id" class="error">{{ fieldErrors.department_id }}</span>
          </div>
        </div>
      </section>

      <section class="sect">
        <h3>Доступ</h3>
        <div class="form-grid">
          <div v-if="isAdmin" class="field"><span>Роль</span>
            <div><SegmentedControl v-model="form.role" :options="ROLE_OPTIONS" /></div>
            <span class="help">{{ form.role === 'admin' ? 'Полный доступ ко всем службам и администрированию' : 'Доступ — по профилю и личным настройкам' }}</span>
          </div>
          <label class="field" :class="{ full: !isAdmin }"><span>Профиль доступа</span>
            <select class="select" :value="form.profile_id ?? ''" :disabled="form.role === 'admin'" data-testid="create-profile" @change="pickProfile">
              <option value="">{{ INDIVIDUAL_LABEL }}</option>
              <option v-for="p in profiles" :key="p.id" :value="p.id">{{ p.name }}</option>
            </select>
            <span class="help">{{ profile ? profile.description : 'Как в версии 0.1.0: вся компания, все данные, реестры и выгрузка' }}</span>
          </label>
        </div>
        <ul v-if="profile && form.role !== 'admin'" class="facts">
          <li v-for="f in facts" :key="f.key" :class="{ off: f.off }"><span>{{ f.label }}</span><b>{{ f.text }}</b></li>
        </ul>
        <div v-if="form.role !== 'admin'" class="svc">
          <span class="label">Службы</span>
          <div class="svc-list">
            <label v-for="s in dashboards" :key="s.key" class="svc-item" :class="{ chosen: form.services[s.key] }">
              <span class="svc-name"><AppIcon :name="SERVICE_ICONS[s.key] || 'grid'" :size="14" />{{ s.short_title || s.title }}</span>
              <select class="select select-sm" :value="form.services[s.key] || ''" :aria-label="`${s.title}: уровень доступа`" :data-service="s.key" @change="setService(s.key, $event.target.value)">
                <option value="">{{ inheritedText(s.key) }}</option>
                <option v-if="profile" value="none" :title="LEVEL_HINTS.none">Нет доступа</option>
                <option v-for="l in LEVELS" :key="l" :value="l" :title="LEVEL_HINTS[l]">{{ LEVEL_LABELS[l] }}</option>
              </select>
            </label>
          </div>
          <span class="help">Остальное — области, классы данных, записи и выгрузку — можно задать лично в карточке пользователя после создания.</span>
        </div>
      </section>

      <section class="sect">
        <h3>Способ входа</h3>
        <div class="methods" role="radiogroup" aria-label="Способ входа">
          <label v-for="m in methods" :key="m.value" class="method" :class="{ on: form.access_method === m.value, off: m.disabled }" :data-method="m.value">
            <input v-model="form.access_method" type="radio" name="access-method" :value="m.value" :disabled="m.disabled" />
            <span class="radio" />
            <span class="m-text"><b>{{ m.label }}</b><small>{{ m.disabled ? 'Вход по домену не настроен на сервере' : m.hint }}</small></span>
          </label>
        </div>
        <span v-if="fieldErrors.access_method" class="error">{{ fieldErrors.access_method }}</span>
        <div v-if="form.access_method === 'password'" class="own">
          <label class="check"><input v-model="ownPassword" type="checkbox" />Задать временный пароль самому</label>
          <span v-if="ownPassword" class="pwd">
            <input v-model="form.password" class="input mono" :class="{ invalid: fieldErrors.password }" :type="showPassword ? 'text' : 'password'"
                   autocomplete="new-password" maxlength="72" placeholder="Не короче 8 символов" aria-label="Временный пароль" />
            <button class="btn btn-ghost btn-icon btn-sm eye" type="button" :title="showPassword ? 'Скрыть пароль' : 'Показать пароль'" @click="showPassword = !showPassword">
              <AppIcon :name="showPassword ? 'eye-off' : 'eye'" :size="15" />
            </button>
          </span>
          <span v-if="fieldErrors.password" class="error">{{ fieldErrors.password }}</span>
        </div>
      </section>

      <section v-if="isAdmin && form.role !== 'admin'" class="sect">
        <h3>Полномочия</h3>
        <div class="caps">
          <label v-for="c in CAPABILITIES" :key="c.key" class="check cap" :title="c.hint">
            <input type="checkbox" :checked="form.capabilities.includes(c.key)" @change="toggleCapability(c.key)" />
            <span><b>{{ c.label }}</b><small>{{ c.hint }}</small></span>
          </label>
        </div>
      </section>
    </form>
    <p v-if="formError" class="form-error" role="alert"><AppIcon name="alert" :size="14" />{{ formError }}</p>
    <template #footer>
      <button class="btn" type="button" @click="emit('close')">Отмена</button>
      <button class="btn btn-primary" type="submit" form="user-create" :disabled="saving" data-testid="create-submit">{{ saving ? 'Создание…' : 'Создать пользователя' }}</button>
    </template>
  </AppModal>
</template>

<style scoped>
.sections { display: flex; flex-direction: column; gap: 22px; }
.sect { display: flex; flex-direction: column; gap: 12px; }
.sect + .sect { padding-top: 18px; border-top: 1px solid var(--border); }
.sect h3 { font-size: var(--fs-base); font-weight: 650; }
.mono { font-family: var(--font-mono); font-size: var(--fs-sm); }
.mono::placeholder { font-family: var(--font-sans); font-size: var(--fs-base); }
.help { font-size: var(--fs-xs); color: var(--muted); }
.error { font-size: var(--fs-xs); color: var(--light-red); }
.facts { list-style: none; margin: 0; padding: 10px 14px; display: grid; grid-template-columns: repeat(auto-fit, minmax(128px, 1fr)); gap: 8px 16px; border-radius: var(--radius); background: var(--surface-2); border: 1px solid var(--border); }
.facts li { display: flex; flex-direction: column; min-width: 0; line-height: 1.3; }
.facts span { font-size: var(--fs-xs); color: var(--muted); }
.facts b { font-size: var(--fs-sm); font-weight: 560; }
.facts li.off b { color: var(--muted); font-weight: 500; }
.svc { display: flex; flex-direction: column; gap: 6px; }
.svc-list { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
.svc-item { display: flex; flex-direction: column; gap: 6px; padding: 10px 12px; border: 1px solid var(--border); border-radius: var(--radius); transition: border-color var(--t-fast), background var(--t-fast); }
.svc-item.chosen { border-color: color-mix(in srgb, var(--brand) 40%, var(--border)); background: color-mix(in srgb, var(--brand) 3%, var(--surface)); }
.svc-name { display: flex; align-items: center; gap: 7px; font-size: var(--fs-sm); font-weight: 600; color: var(--text); }
.svc-name :deep(svg) { color: var(--muted); }
.methods { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
.method { position: relative; display: flex; gap: 10px; align-items: flex-start; padding: 12px; border: 1px solid var(--border); border-radius: var(--radius-lg); cursor: pointer; transition: border-color var(--t-fast), background var(--t-fast); }
.method:hover:not(.off) { border-color: var(--border-strong); }
.method.on { border-color: color-mix(in srgb, var(--brand) 45%, var(--border)); background: color-mix(in srgb, var(--brand) 3%, var(--surface)); }
.method.off { opacity: .55; cursor: not-allowed; }
.method input { position: absolute; opacity: 0; width: 1px; height: 1px; }
.radio { width: 17px; height: 17px; flex: 0 0 17px; margin-top: 1px; border-radius: 50%; border: 1.5px solid var(--border-strong); background: var(--surface); }
.on .radio { border-color: var(--brand); box-shadow: inset 0 0 0 3.5px var(--surface), inset 0 0 0 9px var(--brand); }
.method:has(input:focus-visible) .radio { outline: 2px solid var(--focus); outline-offset: 2px; }
.m-text { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.m-text b { font-weight: 600; font-size: var(--fs-sm); }
.m-text small { font-size: var(--fs-xs); color: var(--muted); line-height: 1.4; }
.own { display: flex; flex-direction: column; gap: 8px; }
.pwd { position: relative; display: block; max-width: 340px; }
.pwd .input { padding-right: 40px; }
.pwd .eye { position: absolute; right: 3px; top: 3px; }
.caps { display: flex; flex-direction: column; gap: 10px; }
.cap { align-items: flex-start; }
.cap input { margin-top: 2px; }
.cap span { display: flex; flex-direction: column; }
.cap b { font-weight: 560; }
.cap small { font-size: var(--fs-xs); color: var(--muted); }
.form-error { display: flex; align-items: center; gap: 6px; margin-top: 12px; font-size: var(--fs-sm); color: var(--light-red); }
@media (max-width: 720px) {
  .svc-list, .methods { grid-template-columns: minmax(0, 1fr); }
}
</style>
