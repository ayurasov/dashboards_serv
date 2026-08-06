<template>
  <div v-if="loading" class="tempty">Загрузка…</div>
  <template v-else>
    <div class="filters">
      <input class="srch" placeholder="Поиск…" v-model="search">
      <button class="btn btn-p" @click="openNew">+ Пользователь</button>
    </div>
    <div class="twrap">
      <div class="tscroll">
        <table>
          <thead><tr><th>Логин</th><th>ФИО</th><th>Email</th><th>Должность</th><th>Роль</th><th>Основная служба</th><th>Активен</th><th></th></tr></thead>
          <tbody>
            <tr v-for="u in filtered" :key="u.id">
              <td class="td-p">{{ u.username }}</td>
              <td class="td-muted">{{ u.full_name }}</td>
              <td class="td-muted">{{ u.email || '—' }}</td>
              <td class="td-muted">{{ u.position || '—' }}</td>
              <td><span class="tag" :class="'tag-'+u.role">{{ roleLabels[u.role] || u.role }}</span></td>
              <td class="td-muted">{{ serviceTitle(primaryServiceOf(u)) }}</td>
              <td>{{ u.is_active ? '✓' : '✗' }}</td>
              <td><button class="btn btn-g" style="font-size:.75rem;padding:2px 6px" @click="openEdit(u)">✎</button></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div v-if="showModal" class="modal-overlay">
      <div class="modal">
        <div class="mh"><span class="mt">{{ editing?.id ? 'Редактировать' : 'Новый пользователь' }}</span><button class="mc" @click="showModal=false">✕</button></div>
        <div class="fg">
          <div class="fgi"><label class="fl">Логин</label><input class="fi" v-model="form.username" :disabled="!!editing?.id"></div>
          <div class="fgi"><label class="fl">ФИО</label><input class="fi" v-model="form.full_name"></div>
          <div class="fgi"><label class="fl">Email</label><input class="fi" type="email" v-model="form.email" placeholder="—"></div>
          <div class="fgi"><label class="fl">Должность</label><input class="fi" v-model="form.position" placeholder="—"></div>
          <div class="fgi"><label class="fl">Телефон</label><input class="fi" v-model="form.phone" placeholder="—"></div>
          <div class="fgi"><label class="fl">Роль</label>
            <select class="fs" v-model="form.role">
              <option value="viewer">Пользователь</option>
              <option value="hr_head">Начальник службы</option>
              <option value="admin">Администратор</option>
              <!-- Only for users who already carry the retired role: without it the
                   select would silently rewrite their role on the next save. -->
              <option v-if="legacyRole" value="department_viewer">Просмотр отдела (устаревшая)</option>
            </select>
            <span v-if="form.role === 'department_viewer'" class="source-note">Устаревшая роль — выберите одну из трёх новых</span>
          </div>
          <div class="fgi full"><label class="fl">Пароль{{ editing?.id ? ' (пусто — без изменений)' : '' }}</label>
            <div style="display:flex;gap:8px;align-items:center">
              <input class="fi" style="flex:1" :type="showPassword ? 'text' : 'password'" v-model="form.password"
                     autocomplete="new-password">
              <button class="btn btn-g" :title="showPassword ? 'Скрыть пароль' : 'Показать пароль'" @click="showPassword = !showPassword">👁</button>
              <button class="btn btn-g" @click="generatePassword">Сгенерировать</button>
            </div>
            <span v-if="editing?.id" class="source-note">Заданный здесь пароль считается временным: при следующем входе пользователю придётся сменить его</span>
          </div>
          <div class="fgi full"><label class="fl">Основная служба</label>
            <select class="fs" v-model="form.primary_service" @change="applyPrimaryToMatrix">
              <option value="">Не выбрана</option>
              <option v-for="s in services" :key="s.key" :value="s.key">{{ s.title }}</option>
            </select>
            <span class="source-note">Выбранной службе автоматически выдаётся уровень «Правка метрик»</span>
          </div>
          <div class="fgi full">
            <label class="fl">Фото</label>
            <div style="display:flex;gap:12px;align-items:center;margin-top:4px">
              <div class="prof-avatar" style="width:64px;height:64px;font-size:1.25rem;margin:0;flex:none">
                <img v-if="form.avatar" :src="form.avatar" alt="Фото пользователя">
                <template v-else>{{ initials }}</template>
              </div>
              <input ref="fileInput" type="file" accept="image/*" hidden @change="pickPhoto">
              <button class="btn btn-g" @click="fileInput.click()">Загрузить фото</button>
              <button v-if="form.avatar" class="btn btn-g" @click="form.avatar = ''">Удалить фото</button>
              <span class="source-note">JPG или PNG, до 1,5 МБ</span>
            </div>
          </div>
        </div>
        <div class="fgi full" style="margin-top:12px">
          <label class="fl">Доступ к службам</label>
          <p v-if="form.role === 'admin'" style="font-size:.75rem;color:var(--c-muted);margin:4px 0 0">
            Администратор имеет полный доступ ко всем службам независимо от этих настроек.
          </p>
          <div class="tscroll" style="max-height:260px;margin-top:4px">
            <table>
              <thead><tr><th>Служба</th><th style="width:150px">Уровень доступа</th></tr></thead>
              <tbody>
                <tr v-for="s in services" :key="s.key">
                  <td class="td-p">
                    {{ s.title }}
                    <span v-if="!s.has_dashboard" class="td-muted" style="font-size:.7rem"> (нет дашборда)</span>
                  </td>
                  <td>
                    <select class="fs" v-model="accessForm[s.key]">
                      <option value="">Нет доступа</option>
                      <option value="read">Чтение</option>
                      <option value="edit">Правка</option>
                      <option value="edit_metrics">Правка метрик</option>
                      <option value="admin">Администратор службы</option>
                    </select>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
        <div class="fac" style="margin-top:16px">
          <button v-if="editing?.id" class="btn btn-d" @click="delUser">Удалить</button>
          <div class="right"><button class="btn btn-g" @click="showModal=false">Отмена</button><button class="btn btn-p" @click="save">Сохранить</button></div>
        </div>
      </div>
    </div>
  </template>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api/client.js'
import { toastError } from '../composables/useToast.js'

const MAX_AVATAR_BYTES = 1_500_000
const PWD_ALPHABET = 'abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'
const PWD_LENGTH = 8

const loading = ref(true)
const users = ref([])
const search = ref('')
const showModal = ref(false)
const editing = ref(null)
const form = ref({})
const services = ref([])
const fileInput = ref(null)
const showPassword = ref(false)
// service_key -> access level ('' = no access); `savedAccess` is the server state,
// so only the rows the admin actually changed get written back.
const accessForm = ref({})
const savedAccess = ref({})
const prevPrimary = ref('')
const roleLabels = { admin: 'Администратор', hr_head: 'Начальник службы', viewer: 'Пользователь', department_viewer: 'Просмотр отдела' }

// The retired role has no option of its own; show one while the edited user still has it.
const legacyRole = computed(() => editing.value?.role === 'department_viewer')

const initials = computed(() => (form.value.full_name || form.value.username || '?')
  .split(/\s+/).filter(Boolean).slice(0, 2).map(w => w[0].toUpperCase()).join(''))

const filtered = computed(() => {
  if (!search.value) return users.value
  const s = search.value.toLowerCase()
  return users.value.filter(u => [u.username, u.full_name, u.email, u.position]
    .some(v => v?.toLowerCase().includes(s)))
})

/** There is no `primary_service` column: it is the service granted `edit_metrics`.
 *  Ties are broken by the services order so the value never jumps around. */
function primaryServiceOf(u) {
  const granted = new Set((u.service_access || [])
    .filter(a => a.access_level === 'edit_metrics').map(a => a.service_key))
  return services.value.find(s => granted.has(s.key))?.key || ''
}

function serviceTitle(key) {
  return services.value.find(s => s.key === key)?.title || '—'
}

async function loadData() {
  loading.value = true
  try {
    users.value = await api.get('/users')
    services.value = await api.get('/services')
  } finally { loading.value = false }
}

function blankAccess() {
  return Object.fromEntries(services.value.map(s => [s.key, '']))
}

function accessMap(rows) {
  const map = blankAccess()
  for (const r of rows || []) map[r.service_key] = r.access_level
  return map
}

/** Mirrors the grant the backend will make, and drops the previous primary's grant
 *  so switching services does not leave the old one with edit_metrics. */
function applyPrimaryToMatrix() {
  const key = form.value.primary_service
  if (prevPrimary.value && accessForm.value[prevPrimary.value] === 'edit_metrics') {
    accessForm.value[prevPrimary.value] = ''
  }
  if (key) accessForm.value[key] = 'edit_metrics'
  prevPrimary.value = key
}

function openNew() {
  editing.value = {}
  form.value = { username: '', full_name: '', email: '', position: '', phone: '', avatar: '', role: 'viewer', password: '', primary_service: '' }
  accessForm.value = blankAccess()
  savedAccess.value = blankAccess()
  prevPrimary.value = ''
  showPassword.value = false
  showModal.value = true
}

async function openEdit(u) {
  editing.value = { ...u }
  form.value = { ...u, password: '', primary_service: primaryServiceOf(u) }
  prevPrimary.value = form.value.primary_service
  accessForm.value = accessMap(u.service_access)
  savedAccess.value = { ...accessForm.value }
  showPassword.value = false
  showModal.value = true
  try {
    const rows = await api.get(`/users/${u.id}/access`)
    accessForm.value = accessMap(rows)
    savedAccess.value = { ...accessForm.value }
    form.value.primary_service = primaryServiceOf({ service_access: rows })
    prevPrimary.value = form.value.primary_service
  } catch { /* the API layer already surfaced the reason as a toast */ }
}

function generatePassword() {
  const bytes = crypto.getRandomValues(new Uint32Array(PWD_LENGTH))
  form.value.password = Array.from(bytes, b => PWD_ALPHABET[b % PWD_ALPHABET.length]).join('')
  showPassword.value = true
}

function pickPhoto(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return
  if (file.size > MAX_AVATAR_BYTES) {
    toastError('Файл слишком большой (максимум 1,5 МБ)')
    return
  }
  const reader = new FileReader()
  reader.onload = () => { form.value.avatar = String(reader.result) }
  reader.onerror = () => { toastError('Не удалось прочитать файл') }
  reader.readAsDataURL(file)
}

async function saveAccess(userId) {
  for (const [key, level] of Object.entries(accessForm.value)) {
    if (level === savedAccess.value[key]) continue
    await api.put(`/users/${userId}/access`, { service_key: key, access_level: level || null })
  }
}

async function save() {
  try {
    const f = form.value
    // Empty strings rather than null: the backend skips null fields, so null would
    // make clearing an email/phone/photo impossible.
    const body = {
      full_name: f.full_name, email: f.email || '', position: f.position || '',
      phone: f.phone || '', avatar: f.avatar || '', role: f.role,
      primary_service: f.primary_service || '',
    }
    let saved
    if (editing.value.id) {
      // `password` is the one field that must be omitted rather than sent as '':
      // a blank value means "keep the current password", and the backend flags the
      // user to change any password an admin sets here.
      if (f.password) body.password = f.password
      saved = await api.put(`/users/${editing.value.id}`, body)
    } else {
      if (!f.username || !f.password) {
        toastError('Укажите логин и пароль')
        return
      }
      saved = await api.post('/users', { ...body, username: f.username, password: f.password })
    }
    // `primary_service` grants edit_metrics server-side, so the response — not the
    // matrix loaded when the modal opened — is the state `saveAccess` must diff against.
    savedAccess.value = accessMap(saved.service_access)
    await saveAccess(saved.id)
    users.value = await api.get('/users')
    showModal.value = false
  } catch { /* the API layer already surfaced the reason as a toast */ }
}

async function delUser() {
  if (!confirm('Удалить пользователя?')) return
  try {
    await api.del(`/users/${editing.value.id}`)
    users.value = await api.get('/users')
    showModal.value = false
  } catch { /* the API layer already surfaced the reason as a toast */ }
}

onMounted(loadData)
</script>
