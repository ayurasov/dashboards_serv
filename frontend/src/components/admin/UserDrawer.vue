<script setup>
import { computed, reactive, ref } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import SegmentedControl from '@/components/ui/SegmentedControl.vue'
import SideDrawer from './SideDrawer.vue'
import UserAvatar from './UserAvatar.vue'
import ToggleSwitch from './ToggleSwitch.vue'
import AccessMatrix from './AccessMatrix.vue'
import DepartmentPicker from './DepartmentPicker.vue'
import OneTimePassword from './OneTimePassword.vue'
import { adminApi } from '@/api/services'
import { confirm } from '@/composables/useConfirm'
import { toastOk } from '@/composables/useToast'
import { useAuthStore } from '@/stores/auth'
import { buildAccessRows, formFieldErrors, profileForm, profilePatch, ROLE_LABELS, sameAccess, serializeAccess, userFormErrors } from '@/domain/admin'
import { formatDateTime, formatRelative } from '@/utils/format'

/** Карточка пользователя: вкладки «Профиль» и «Доступ», временный пароль, удаление. */
const props = defineProps({
  user: { type: Object, required: true },
  services: { type: Array, default: () => [] },
  departments: { type: Array, default: () => [] },
})
const emit = defineEmits(['close', 'saved', 'changed', 'deleted'])

const auth = useAuthStore()
const isSelf = computed(() => auth.user?.id === props.user.id)
const tab = ref('profile')
const form = reactive(profileForm(props.user))
const rows = ref(buildAccessRows(props.services, props.user.access))
const saving = ref(false)
const formError = ref('')
const fieldErrors = ref({})
const secret = ref('')

const ROLE_OPTIONS = [{ value: 'user', label: ROLE_LABELS.user }, { value: 'admin', label: ROLE_LABELS.admin }]
const patch = computed(() => profilePatch(props.user, form))
const profileDirty = computed(() => Object.keys(patch.value).length > 0)
// Доступ администратора сервер не показывает; при снятии роли сохраняем то, что видно в матрице
const accessDirty = computed(() => form.role !== 'admin'
  && (props.user.role === 'admin' || !sameAccess(serializeAccess(rows.value), props.user.access)))
const dirty = computed(() => profileDirty.value || accessDirty.value)

async function save() {
  formError.value = ''
  fieldErrors.value = userFormErrors(form)
  if (Object.keys(fieldErrors.value).length) { tab.value = 'profile'; return }
  saving.value = true
  try {
    let updated = props.user
    if (profileDirty.value) updated = await adminApi.updateUser(props.user.id, patch.value)
    if (accessDirty.value) updated = await adminApi.setAccess(props.user.id, serializeAccess(rows.value))
    toastOk('Изменения сохранены')
    emit('saved', updated)
  } catch (e) {
    formError.value = e.message
    fieldErrors.value = formFieldErrors(e.fields)
    if (Object.keys(fieldErrors.value).some((k) => k !== 'access')) tab.value = 'profile'
  } finally {
    saving.value = false
  }
}

async function close() {
  if (dirty.value && !await confirm({ title: 'Закрыть без сохранения?', message: 'Внесённые изменения будут потеряны.', confirmText: 'Закрыть' })) return
  emit('close')
}

async function resetPassword() {
  const ok = await confirm({
    title: 'Выдать временный пароль?',
    message: `${props.user.full_name} (${props.user.username}).\nТекущий пароль перестанет действовать, все сессии пользователя будут завершены. При входе система попросит задать новый пароль.`,
    confirmText: 'Выдать пароль',
  })
  if (!ok) return
  const result = await adminApi.resetPassword(props.user.id)
  secret.value = result.temporary_password
  emit('changed')
}

async function remove() {
  const ok = await confirm({
    title: 'Удалить пользователя?',
    message: `${props.user.full_name} (${props.user.username}) больше не сможет войти. Записи журнала изменений сохранятся.`,
    confirmText: 'Удалить',
    danger: true,
  })
  if (!ok) return
  const result = await adminApi.deleteUser(props.user.id)
  toastOk(result?.message || 'Пользователь удалён')
  emit('deleted', props.user)
}
</script>

<template>
  <SideDrawer :title="user.full_name" :width="720" @close="close">
    <template #header>
      <div class="who">
        <UserAvatar :name="user.full_name" :seed="user.username" :src="isSelf ? auth.user?.avatar || '' : ''" :size="48" :muted="!user.is_active" />
        <div class="who-text">
          <h2>{{ user.full_name }}</h2>
          <p class="login">{{ user.username }}<span v-if="isSelf" class="self">это вы</span></p>
          <div class="row-wrap badges">
            <span class="badge" :class="user.role === 'admin' ? 'badge-brand' : ''">{{ ROLE_LABELS[user.role] }}</span>
            <span class="badge" :class="user.is_active ? 'badge-green' : 'badge-gray'">{{ user.is_active ? 'Активен' : 'Отключён' }}</span>
            <span v-if="user.must_change_password" class="badge badge-yellow" title="При входе пользователь должен сменить пароль">Временный пароль</span>
          </div>
        </div>
      </div>
      <dl class="facts">
        <div><dt>Создан</dt><dd class="num">{{ formatDateTime(user.created_at) }}</dd></div>
        <div><dt>Последний вход</dt><dd :title="user.last_login_at ? formatDateTime(user.last_login_at) : ''">{{ user.last_login_at ? formatRelative(user.last_login_at) : 'Ещё не входил' }}</dd></div>
      </dl>
    </template>

    <template #tabs>
      <nav class="tabs" role="tablist">
        <button type="button" role="tab" :aria-selected="tab === 'profile'" :class="{ active: tab === 'profile' }" @click="tab = 'profile'">
          Профиль<i v-if="profileDirty" class="dirty" title="Есть несохранённые изменения" />
        </button>
        <button type="button" role="tab" :aria-selected="tab === 'access'" :class="{ active: tab === 'access' }" @click="tab = 'access'">
          Доступ<i v-if="accessDirty" class="dirty" title="Есть несохранённые изменения" />
        </button>
      </nav>
    </template>

    <form v-show="tab === 'profile'" id="user-profile" class="form-grid" novalidate @submit.prevent="save">
      <label class="field full"><span>ФИО</span>
        <input v-model="form.full_name" class="input" :class="{ invalid: fieldErrors.full_name }" required maxlength="200" />
        <span v-if="fieldErrors.full_name" class="error">{{ fieldErrors.full_name }}</span>
      </label>
      <label class="field"><span>E-mail</span>
        <input v-model="form.email" class="input" :class="{ invalid: fieldErrors.email }" type="email" placeholder="name@company.ru" />
        <span v-if="fieldErrors.email" class="error">{{ fieldErrors.email }}</span>
      </label>
      <label class="field"><span>Телефон</span>
        <input v-model="form.phone" class="input" :class="{ invalid: fieldErrors.phone }" maxlength="50" />
        <span v-if="fieldErrors.phone" class="error">{{ fieldErrors.phone }}</span>
      </label>
      <label class="field full"><span>Должность</span>
        <input v-model="form.position" class="input" :class="{ invalid: fieldErrors.position }" maxlength="200" />
      </label>

      <div class="field full">
        <span>Роль</span>
        <fieldset class="bare" :disabled="isSelf" :class="{ locked: isSelf }"><SegmentedControl v-model="form.role" :options="ROLE_OPTIONS" /></fieldset>
        <span class="help">{{ isSelf ? 'Свою роль изменить нельзя' : form.role === 'admin' ? 'Полный доступ ко всем службам и разделу администрирования' : 'Доступ к службам задаётся на вкладке «Доступ»' }}</span>
      </div>

      <div class="field full">
        <span>Статус</span>
        <ToggleSwitch v-model="form.is_active" :disabled="isSelf" :label="form.is_active ? 'Активен — может входить в систему' : 'Отключён — вход запрещён'" />
        <span class="help">{{ isSelf ? 'Свою учётную запись отключить нельзя' : 'При отключении все сессии пользователя завершаются' }}</span>
      </div>

      <div class="field full">
        <span>Подразделения</span>
        <DepartmentPicker v-model="form.department_ids" :departments="departments" />
        <span class="help">Нужны для ограничения «только свои подразделения» в службе персонала</span>
      </div>
    </form>

    <div v-show="tab === 'access'" class="stack">
      <div v-if="form.role === 'admin'" class="note">
        <AppIcon name="shield" :size="18" />
        <div><strong>Администратор имеет полный доступ ко всем службам</strong><p>Уровни ниже не применяются, пока у пользователя роль «Администратор».</p></div>
      </div>
      <p v-else class="muted intro">
        «Просмотр» — дашборды и отчёты, «Ввод данных» — ещё и добавление данных, «Управление» — ещё и настройки службы: светофор и цели.
      </p>
      <AccessMatrix v-model="rows" :disabled="form.role === 'admin'" :name="`access-${user.id}`" />
      <span v-if="fieldErrors.access" class="error">{{ fieldErrors.access }}</span>
    </div>

    <p v-if="formError" class="form-error"><AppIcon name="alert" :size="14" />{{ formError }}</p>

    <template #footer>
      <button class="btn btn-ghost" type="button" :disabled="isSelf" :title="isSelf ? 'Свой пароль меняется в профиле' : 'Сгенерировать новый пароль и завершить сессии пользователя'" @click="resetPassword">
        <AppIcon name="key" :size="15" />Выдать временный пароль
      </button>
      <button class="btn btn-ghost btn-danger" type="button" :disabled="isSelf" :title="isSelf ? 'Нельзя удалить свою учётную запись' : 'Удалить пользователя'" @click="remove">
        <AppIcon name="trash" :size="15" />Удалить
      </button>
      <span class="spacer" />
      <button class="btn" type="button" @click="close">Отмена</button>
      <button class="btn btn-primary" type="button" :disabled="saving || !dirty" @click="save">{{ saving ? 'Сохранение…' : 'Сохранить' }}</button>
    </template>
  </SideDrawer>

  <OneTimePassword v-if="secret" :password="secret" :user="user" @close="secret = ''" />
</template>

<style scoped>
.who { display: flex; gap: 14px; align-items: flex-start; }
.who-text { min-width: 0; }
.who h2 { font-size: 18px; line-height: 1.25; }
.login { margin-top: 1px; font-family: var(--font-mono); font-size: var(--fs-sm); color: var(--muted); }
.self { margin-left: 8px; font-family: var(--font-sans); font-size: var(--fs-xs); color: var(--text-2); }
.badges { margin-top: 8px; gap: 6px; }
.facts { display: flex; gap: 28px; margin: 16px 0 0; padding-top: 12px; border-top: 1px dashed var(--border); }
.facts dt { font-size: var(--fs-xs); color: var(--muted); }
.facts dd { margin: 2px 0 0; font-size: var(--fs-sm); color: var(--text); }
.tabs { display: flex; gap: 4px; padding: 0 22px; border-bottom: 1px solid var(--border); }
.tabs button { position: relative; display: inline-flex; align-items: center; gap: 6px; height: 38px; padding: 0 12px; border: 0; background: transparent; color: var(--text-2); font-weight: 560; cursor: pointer; }
.tabs button:hover { color: var(--text); }
.tabs button.active { color: var(--text); }
.tabs button.active::after { content: ''; position: absolute; left: 8px; right: 8px; bottom: -1px; height: 2px; border-radius: 2px; background: var(--brand); }
.dirty { width: 6px; height: 6px; border-radius: 50%; background: var(--light-yellow); }
.help { font-size: var(--fs-xs); color: var(--muted); }
.error { font-size: var(--fs-xs); color: var(--light-red); }
.note { display: flex; gap: 12px; padding: 14px 16px; border-radius: 12px; background: var(--brand-soft); color: var(--brand); }
.note strong { color: var(--text); }
.note p { margin-top: 2px; font-size: var(--fs-sm); color: var(--text-2); }
.intro { font-size: var(--fs-sm); }
.form-error { display: flex; align-items: center; gap: 6px; margin-top: 16px; font-size: var(--fs-sm); color: var(--light-red); }
.bare { margin: 0; padding: 0; border: 0; min-width: 0; }
.locked { opacity: .55; }
</style>
