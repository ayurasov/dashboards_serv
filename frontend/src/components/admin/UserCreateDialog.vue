<script setup>
import { reactive, ref } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import AppModal from '@/components/ui/AppModal.vue'
import SegmentedControl from '@/components/ui/SegmentedControl.vue'
import AccessMatrix from './AccessMatrix.vue'
import DepartmentPicker from './DepartmentPicker.vue'
import { adminApi } from '@/api/services'
import { buildAccessRows, formFieldErrors, ROLE_LABELS, serializeAccess, USERNAME_PATTERN, userFormErrors } from '@/domain/admin'

/** Новый пользователь: учётные данные, роль, подразделения и доступ. Пустой пароль — сервер выдаст временный. */
const props = defineProps({
  services: { type: Array, default: () => [] },
  departments: { type: Array, default: () => [] },
})
const emit = defineEmits(['close', 'created'])

const ROLE_OPTIONS = [{ value: 'user', label: ROLE_LABELS.user }, { value: 'admin', label: ROLE_LABELS.admin }]
const form = reactive({ username: '', full_name: '', email: '', position: '', role: 'user', password: '', department_ids: [] })
const rows = ref(buildAccessRows(props.services, []))
const showPassword = ref(false)
const saving = ref(false)
const formError = ref('')
const fieldErrors = ref({})

async function save() {
  formError.value = ''
  fieldErrors.value = {}
  const username = form.username.trim()
  fieldErrors.value = userFormErrors(form, { isNew: true })
  if (Object.keys(fieldErrors.value).length) return
  saving.value = true
  try {
    const result = await adminApi.createUser({
      username,
      full_name: form.full_name.trim(),
      email: form.email.trim(),
      position: form.position.trim() || null,
      role: form.role,
      password: form.password || null,
      department_ids: form.department_ids,
      access: form.role === 'admin' ? [] : serializeAccess(rows.value),
    })
    emit('created', result)
  } catch (e) {
    formError.value = e.message
    fieldErrors.value = formFieldErrors(e.fields)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <AppModal title="Новый пользователь" subtitle="Учётная запись, роль и доступ к службам" :width="800" @close="emit('close')">
    <form id="user-create" class="stack" autocomplete="off" novalidate @submit.prevent="save">
      <div class="form-grid">
        <label class="field"><span>Логин</span>
          <input v-model="form.username" class="input mono" :class="{ invalid: fieldErrors.username }" required minlength="2" maxlength="100"
                 :pattern="USERNAME_PATTERN" title="Латиница, цифры и . _ @ -" autocapitalize="off" spellcheck="false" placeholder="i.ivanov" />
          <span v-if="fieldErrors.username" class="error">{{ fieldErrors.username }}</span>
          <span v-else class="help">Латиница, цифры и . _ @ -</span>
        </label>
        <label class="field"><span>ФИО</span>
          <input v-model="form.full_name" class="input" :class="{ invalid: fieldErrors.full_name }" required maxlength="200" placeholder="Иванов Иван Иванович" />
          <span v-if="fieldErrors.full_name" class="error">{{ fieldErrors.full_name }}</span>
        </label>
        <label class="field"><span>E-mail</span>
          <input v-model="form.email" class="input" :class="{ invalid: fieldErrors.email }" type="email" placeholder="Необязательно" />
          <span v-if="fieldErrors.email" class="error">{{ fieldErrors.email }}</span>
        </label>
        <label class="field"><span>Должность</span>
          <input v-model="form.position" class="input" :class="{ invalid: fieldErrors.position }" maxlength="200" placeholder="Необязательно" />
        </label>
        <label class="field"><span>Пароль</span>
          <span class="pwd">
            <input v-model="form.password" class="input mono" :class="{ invalid: fieldErrors.password }" :type="showPassword ? 'text' : 'password'"
                   autocomplete="new-password" maxlength="72" placeholder="Оставьте пустым — будет сгенерирован" />
            <button class="btn btn-ghost btn-icon btn-sm eye" type="button" :title="showPassword ? 'Скрыть пароль' : 'Показать пароль'" @click="showPassword = !showPassword">
              <AppIcon :name="showPassword ? 'eye-off' : 'eye'" :size="15" />
            </button>
          </span>
          <span v-if="fieldErrors.password" class="error">{{ fieldErrors.password }}</span>
          <span v-else class="help">Временный: при первом входе пользователь задаст свой</span>
        </label>
        <div class="field"><span>Роль</span>
          <div><SegmentedControl v-model="form.role" :options="ROLE_OPTIONS" /></div>
          <span class="help">{{ form.role === 'admin' ? 'Полный доступ ко всем службам и администрированию' : 'Доступ — по матрице ниже' }}</span>
        </div>
        <div class="field full"><span>Подразделения</span>
          <DepartmentPicker v-model="form.department_ids" :departments="departments" />
        </div>
      </div>

      <section class="access">
        <h3>Доступ к службам</h3>
        <div v-if="form.role === 'admin'" class="note">
          <AppIcon name="shield" :size="16" />Администратор имеет полный доступ ко всем службам
        </div>
        <AccessMatrix v-model="rows" :disabled="form.role === 'admin'" name="new-user" />
        <span v-if="fieldErrors.access" class="error">{{ fieldErrors.access }}</span>
      </section>
    </form>
    <p v-if="formError" class="form-error"><AppIcon name="alert" :size="14" />{{ formError }}</p>
    <template #footer>
      <button class="btn" type="button" @click="emit('close')">Отмена</button>
      <button class="btn btn-primary" type="submit" form="user-create" :disabled="saving">{{ saving ? 'Создание…' : 'Создать пользователя' }}</button>
    </template>
  </AppModal>
</template>

<style scoped>
.mono { font-family: var(--font-mono); font-size: var(--fs-sm); }
.mono::placeholder { font-family: var(--font-sans); font-size: var(--fs-base); }
.pwd { position: relative; display: block; font-size: var(--fs-base); font-weight: 400; color: var(--text); }
.pwd .input { padding-right: 40px; }
.pwd .eye { position: absolute; right: 3px; top: 3px; }
.help { font-size: var(--fs-xs); color: var(--muted); }
.error { font-size: var(--fs-xs); color: var(--light-red); }
.access { display: flex; flex-direction: column; gap: 8px; margin-top: 6px; padding-top: 16px; border-top: 1px solid var(--border); }
.access h3 { font-size: var(--fs-base); }
.note { display: flex; align-items: center; gap: 8px; padding: 10px 12px; border-radius: 10px; background: var(--brand-soft); color: var(--brand); font-size: var(--fs-sm); font-weight: 560; }
.form-error { display: flex; align-items: center; gap: 6px; margin-top: 12px; font-size: var(--fs-sm); color: var(--light-red); }
</style>
