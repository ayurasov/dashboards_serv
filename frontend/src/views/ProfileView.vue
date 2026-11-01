<script setup>
import { computed, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppIcon from '@/components/ui/AppIcon.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import { api } from '@/api/client'
import { useAsync } from '@/composables/useAsync'
import { confirm } from '@/composables/useConfirm'
import { toastOk } from '@/composables/useToast'
import { useAuthStore, LEVEL_LABELS } from '@/stores/auth'
import { useAppStore } from '@/stores/app'
import { formatDateTime, formatRelative } from '@/utils/format'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const app = useAppStore()
const required = computed(() => auth.mustChangePassword)

const profile = reactive({
  full_name: auth.user?.full_name || '', email: auth.user?.email || '',
  position: auth.user?.position || '', phone: auth.user?.phone || '',
})
const savingProfile = ref(false)
async function saveProfile() {
  savingProfile.value = true
  try {
    await auth.saveProfile({ ...profile })
    toastOk('Профиль сохранён')
  } finally {
    savingProfile.value = false
  }
}

function pickAvatar(event) {
  const file = event.target.files?.[0]
  if (!file) return
  if (file.size > 1.5 * 1024 * 1024) { alert('Изображение больше 1,5 МБ'); return }
  const reader = new FileReader()
  reader.onload = async () => {
    await auth.saveProfile({ avatar: reader.result })
    toastOk('Фото обновлено')
  }
  reader.readAsDataURL(file)
}
async function removeAvatar() {
  await auth.saveProfile({ avatar: '' })
}

const pwd = reactive({ current: '', next: '', repeat: '' })
const pwdError = ref('')
const pwdFields = ref({})
const changing = ref(false)
const strength = computed(() => {
  const p = pwd.next
  let score = 0
  if (p.length >= 8) score++
  if (p.length >= 12) score++
  if (/[a-zа-я]/.test(p) && /[A-ZА-Я]/.test(p)) score++
  if (/\d/.test(p)) score++
  if (/[^\wа-яА-Я]/.test(p)) score++
  return Math.min(score, 4)
})
const STRENGTH = ['Слишком простой', 'Слабый', 'Средний', 'Хороший', 'Надёжный']

async function changePassword() {
  pwdError.value = ''
  pwdFields.value = {}
  if (pwd.next !== pwd.repeat) { pwdError.value = 'Пароли не совпадают'; return }
  changing.value = true
  try {
    const result = await auth.changePassword(pwd.current, pwd.next)
    toastOk(result.message)
    Object.assign(pwd, { current: '', next: '', repeat: '' })
    sessions.reload()
    if (route.query.password) router.replace('/')
  } catch (e) {
    pwdError.value = e.message
    pwdFields.value = e.fields || {}
  } finally {
    changing.value = false
  }
}

const sessions = useAsync(() => api.get('/auth/sessions'))
function device(ua) {
  if (!ua) return 'Неизвестное устройство'
  const browser = /Edg\//.test(ua) ? 'Edge' : /YaBrowser/.test(ua) ? 'Яндекс Браузер' : /Firefox/.test(ua) ? 'Firefox' : /Chrome/.test(ua) ? 'Chrome' : /Safari/.test(ua) ? 'Safari' : 'Браузер'
  const os = /Windows/.test(ua) ? 'Windows' : /Mac OS/.test(ua) ? 'macOS' : /Android/.test(ua) ? 'Android' : /iPhone|iPad/.test(ua) ? 'iOS' : /Linux/.test(ua) ? 'Linux' : ''
  return os ? `${browser}, ${os}` : browser
}
async function closeSession(s) {
  await api.del(`/auth/sessions/${s.id}`)
  sessions.reload()
}
async function closeOthers() {
  if (!await confirm({ title: 'Завершить другие сессии?', message: 'На других устройствах потребуется войти заново.', confirmText: 'Завершить' })) return
  const r = await api.del('/auth/sessions/others')
  toastOk(r.message)
  sessions.reload()
}
</script>

<template>
  <div class="page narrow">
    <PageHeader title="Профиль" description="Личные данные, пароль и активные сессии" />

    <div v-if="required" class="notice">
      <AppIcon name="lock" :size="18" />
      <div><strong>Смените временный пароль</strong><p>Администратор выдал вам временный пароль. Придумайте свой, чтобы продолжить работу.</p></div>
    </div>

    <div class="grid grid-2">
      <section class="card">
        <header class="card-head"><h3>Личные данные</h3></header>
        <div class="card-body stack">
          <div class="avatar-row">
            <span class="avatar"><img v-if="auth.user?.avatar" :src="auth.user.avatar" alt="" /><template v-else>{{ auth.initials }}</template></span>
            <div class="row-wrap">
              <label class="btn btn-sm"><AppIcon name="upload" :size="13" />Загрузить фото<input type="file" accept="image/*" class="sr-only" @change="pickAvatar" /></label>
              <button v-if="auth.user?.avatar" class="btn btn-sm btn-ghost" type="button" @click="removeAvatar">Удалить</button>
            </div>
          </div>
          <form class="form-grid" @submit.prevent="saveProfile">
            <label class="field full"><span>ФИО</span><input v-model="profile.full_name" class="input" required /></label>
            <label class="field"><span>E-mail</span><input v-model="profile.email" class="input" type="email" /></label>
            <label class="field"><span>Телефон</span><input v-model="profile.phone" class="input" /></label>
            <label class="field full"><span>Должность</span><input v-model="profile.position" class="input" /></label>
            <div class="full row"><span class="spacer" /><button class="btn btn-primary" :disabled="savingProfile">Сохранить</button></div>
          </form>
        </div>
      </section>

      <section class="card" :class="{ highlight: required }">
        <header class="card-head"><h3>Смена пароля</h3></header>
        <form class="card-body stack" @submit.prevent="changePassword">
          <label class="field"><span>Текущий пароль</span>
            <input v-model="pwd.current" class="input" :class="{ invalid: pwdFields.current_password }" type="password" autocomplete="current-password" required />
          </label>
          <label class="field"><span>Новый пароль</span>
            <input v-model="pwd.next" class="input" :class="{ invalid: pwdFields.new_password }" type="password" autocomplete="new-password" required />
            <span v-if="pwd.next" class="strength" :data-level="strength"><i v-for="i in 4" :key="i" :class="{ on: i <= strength }" />{{ STRENGTH[strength] }}</span>
            <span class="help">Не короче 8 символов; буквы вместе с цифрами или другими символами.</span>
          </label>
          <label class="field"><span>Повторите пароль</span><input v-model="pwd.repeat" class="input" type="password" autocomplete="new-password" required /></label>
          <p v-if="pwdError" class="error">{{ pwdError }}</p>
          <div class="row"><span class="help muted">Другие сессии будут завершены.</span><span class="spacer" /><button class="btn btn-primary" :disabled="changing">Сменить пароль</button></div>
        </form>
      </section>
    </div>

    <section class="card">
      <header class="card-head">
        <h3>Доступ</h3>
        <span class="hint">{{ auth.isAdmin ? 'Администратор: полный доступ ко всем службам и настройкам' : 'Уровни доступа выдаёт администратор' }}</span>
      </header>
      <div v-if="!auth.isAdmin" class="card-body">
        <div class="row-wrap">
          <span v-for="a in auth.user?.access || []" :key="a.service_key" class="badge">
            {{ app.service(a.service_key)?.title || a.service_key }} — {{ LEVEL_LABELS[a.level] }}<template v-if="a.department_scope"> (свои подразделения)</template>
          </span>
          <span v-if="!auth.user?.access?.length" class="muted">Доступ к службам не выдан</span>
        </div>
      </div>
    </section>

    <section class="card">
      <header class="card-head">
        <h3>Активные сессии</h3>
        <span class="spacer" />
        <button v-if="(sessions.data.value || []).length > 1" class="btn btn-sm" type="button" @click="closeOthers">Завершить другие</button>
      </header>
      <div class="card-body">
        <table class="table table-compact">
          <thead><tr><th>Устройство</th><th>IP-адрес</th><th>Вход</th><th>Активность</th><th /></tr></thead>
          <tbody>
            <tr v-for="s in sessions.data.value || []" :key="s.id">
              <td>{{ device(s.user_agent) }} <span v-if="s.current" class="badge badge-green">Эта сессия</span></td>
              <td class="muted">{{ s.ip_address || '—' }}</td>
              <td class="muted">{{ formatDateTime(s.created_at) }}</td>
              <td class="muted">{{ formatRelative(s.last_seen_at) }}</td>
              <td class="num"><button v-if="!s.current" class="btn btn-sm btn-ghost" type="button" @click="closeSession(s)">Завершить</button></td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>

<style scoped>
.narrow { max-width: 1100px; }
.notice { display: flex; gap: 12px; padding: 14px 16px; border-radius: 12px; background: color-mix(in srgb, var(--light-yellow) 12%, var(--surface)); border: 1px solid color-mix(in srgb, var(--light-yellow) 35%, var(--border)); color: color-mix(in srgb, var(--light-yellow) 70%, var(--text)); }
.notice strong { color: var(--text); }
.notice p { color: var(--text-2); font-size: var(--fs-sm); }
.highlight { border-color: color-mix(in srgb, var(--light-yellow) 50%, var(--border)); box-shadow: 0 0 0 3px color-mix(in srgb, var(--light-yellow) 15%, transparent); }
.avatar-row { display: flex; align-items: center; gap: 16px; }
.avatar { width: 64px; height: 64px; border-radius: 50%; overflow: hidden; display: grid; place-items: center; background: var(--brand-soft); color: var(--brand); font-size: 22px; font-weight: 650; }
.avatar img { width: 100%; height: 100%; object-fit: cover; }
.error { color: var(--light-red); font-size: var(--fs-sm); }
.strength { display: flex; align-items: center; gap: 4px; font-size: var(--fs-xs); color: var(--muted); }
.strength i { width: 28px; height: 4px; border-radius: 4px; background: var(--surface-3); }
.strength[data-level='1'] i.on, .strength[data-level='0'] i.on { background: var(--light-red); }
.strength[data-level='2'] i.on { background: var(--light-yellow); }
.strength[data-level='3'] i.on, .strength[data-level='4'] i.on { background: var(--light-green); }
.help { font-size: var(--fs-xs); }
</style>
