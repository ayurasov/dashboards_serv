<template>
  <div v-if="loading" class="tempty">Загрузка…</div>
  <div v-else class="prof-grid">
    <div class="ccard">
      <div class="prof-avatar">
        <img v-if="form.avatar" :src="form.avatar" alt="Фото профиля">
        <template v-else>{{ initials }}</template>
      </div>
      <input ref="fileInput" type="file" accept="image/*" hidden @change="pickPhoto">
      <button class="btn btn-g" style="width:100%;justify-content:center" @click="fileInput.click()">Загрузить фото</button>
      <button v-if="form.avatar" class="btn btn-g" style="width:100%;justify-content:center;margin-top:8px" @click="form.avatar = ''">Удалить фото</button>
      <div class="source-note" style="text-align:center">JPG или PNG, до 1,5 МБ</div>
    </div>

    <div>
      <div class="ccard" style="margin-bottom:16px">
        <div class="ctitle">Учётная запись</div>
        <div class="prof-row">
          <span class="prof-row-lbl">Логин</span>
          <span class="prof-row-val td-mono">{{ user.username }}</span>
        </div>
        <div class="prof-row">
          <span class="prof-row-lbl">Роль</span>
          <span class="prof-row-val"><span class="tag" :class="'tag-'+user.role">{{ roleLabel }}</span></span>
        </div>
        <div class="prof-row">
          <span class="prof-row-lbl">Подразделения</span>
          <span class="prof-row-val">{{ departments }}</span>
        </div>
      </div>

      <div class="ccard" style="margin-bottom:16px">
        <div class="ctitle">Личные данные</div>
        <div class="fg">
          <div class="fgi full">
            <label class="fl">ФИО</label>
            <input class="fi" v-model="form.full_name" maxlength="200">
          </div>
          <div class="fgi">
            <label class="fl">E-mail</label>
            <input class="fi" type="email" v-model="form.email" placeholder="—">
          </div>
          <div class="fgi">
            <label class="fl">Телефон</label>
            <input class="fi" v-model="form.phone" placeholder="—">
          </div>
        </div>
        <div class="err-msg">{{ err }}</div>
        <div class="fac">
          <span></span>
          <div class="right">
            <button class="btn btn-g" :disabled="!dirty || saving" @click="reset">Отменить</button>
            <button class="btn btn-p" :disabled="!dirty || saving" @click="save">{{ saving ? 'Сохранение…' : 'Сохранить' }}</button>
          </div>
        </div>
      </div>

      <div class="ccard">
        <div class="ctitle">Смена пароля</div>
        <form @submit.prevent="changePassword">
          <div class="fg">
            <div class="fgi full">
              <label class="fl">Текущий пароль</label>
              <input class="fi" type="password" v-model="pwd.old" autocomplete="current-password" required>
            </div>
            <div class="fgi">
              <label class="fl">Новый пароль (мин. 4 символа)</label>
              <input class="fi" type="password" v-model="pwd.next" autocomplete="new-password" minlength="4" required>
            </div>
            <div class="fgi">
              <label class="fl">Повторите новый пароль</label>
              <input class="fi" type="password" v-model="pwd.confirm" autocomplete="new-password" minlength="4" required>
            </div>
          </div>
          <div class="err-msg">{{ pwdErr }}</div>
          <div class="fac">
            <span></span>
            <button type="submit" class="btn btn-p" :disabled="pwdSaving">
              {{ pwdSaving ? 'Сохранение…' : 'Изменить пароль' }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useAuthStore } from '../stores/auth.js'
import { toastOk } from '../composables/useToast.js'

const MAX_AVATAR_BYTES = 1_500_000

const auth = useAuthStore()
const loading = ref(true)
const saving = ref(false)
const err = ref('')
const user = ref({})
const form = ref({ full_name: '', email: '', phone: '', avatar: '' })
const fileInput = ref(null)
const pwd = ref({ old: '', next: '', confirm: '' })
const pwdErr = ref('')
const pwdSaving = ref(false)

const roleLabel = computed(() => ({
  admin: 'Администратор', hr_head: 'Начальник службы персонала',
  viewer: 'Просмотр', department_viewer: 'Отдел',
}[user.value.role] || user.value.role || '—'))

const departments = computed(() => {
  const list = (user.value.departments || []).map(d => d.name)
  return list.length ? list.join(', ') : 'Все'
})

const initials = computed(() => (form.value.full_name || user.value.username || '?')
  .split(/\s+/).filter(Boolean).slice(0, 2).map(w => w[0].toUpperCase()).join(''))

const dirty = computed(() => ['full_name', 'email', 'phone', 'avatar']
  .some(k => form.value[k] !== (user.value[k] || '')))

function reset() {
  form.value = {
    full_name: user.value.full_name || '',
    email: user.value.email || '',
    phone: user.value.phone || '',
    avatar: user.value.avatar || '',
  }
  err.value = ''
}

function pickPhoto(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return
  if (file.size > MAX_AVATAR_BYTES) {
    err.value = 'Файл слишком большой (максимум 1,5 МБ)'
    return
  }
  const reader = new FileReader()
  reader.onload = () => { form.value.avatar = String(reader.result); err.value = '' }
  reader.onerror = () => { err.value = 'Не удалось прочитать файл' }
  reader.readAsDataURL(file)
}

async function save() {
  err.value = ''
  saving.value = true
  try {
    user.value = await auth.saveProfile({
      full_name: form.value.full_name,
      email: form.value.email,
      phone: form.value.phone,
      avatar: form.value.avatar,
    })
    reset()
    toastOk('Профиль сохранён')
  } catch (e) {
    err.value = e.message
  } finally {
    saving.value = false
  }
}

async function changePassword() {
  pwdErr.value = ''
  if (pwd.value.next !== pwd.value.confirm) {
    pwdErr.value = 'Новые пароли не совпадают'
    return
  }
  pwdSaving.value = true
  try {
    await auth.changePassword(pwd.value.old, pwd.value.next)
    pwd.value = { old: '', next: '', confirm: '' }
    toastOk('Пароль изменён')
  } catch (e) {
    pwdErr.value = e.message
  } finally {
    pwdSaving.value = false
  }
}

onMounted(async () => {
  try {
    user.value = await auth.loadMe() || {}
    reset()
  } finally {
    loading.value = false
  }
})
</script>
