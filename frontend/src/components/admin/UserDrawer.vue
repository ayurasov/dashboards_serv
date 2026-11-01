<script setup>
import { computed, reactive, ref, watch } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import SegmentedControl from '@/components/ui/SegmentedControl.vue'
import SideDrawer from './SideDrawer.vue'
import UserAvatar from './UserAvatar.vue'
import ToggleSwitch from './ToggleSwitch.vue'
import UnitPicker from './UnitPicker.vue'
import AccessEditor from './AccessEditor.vue'
import AuditDiff from './AuditDiff.vue'
import { accessApi, usersApi } from '@/api/access'
import { confirm } from '@/composables/useConfirm'
import { toastOk } from '@/composables/useToast'
import { useAuthStore } from '@/stores/auth'
import { CAPABILITIES, policyBody, policyDirty, policyDraft } from '@/domain/access'
import {
  actionLabel, ACTION_TONES, AUTH_SOURCE_LABELS, formFieldErrors, managerLabel, needsAccess, profileForm, profilePatch,
  resetAction, ROLE_LABELS, STATUS_LABELS, userBadges, userFormErrors, userHistory,
} from '@/domain/admin'
import { formatDateTime, formatRelative } from '@/utils/format'

/**
 * Карточка пользователя: «Профиль», «Доступ» (профиль доступа, личные настройки, службы,
 * действующий доступ), «Полномочия» и «Журнал» (администратору). Выдать доступ, сбросить пароль
 * и удалить — через страницу (событие action), чтобы окна были общими со строкой списка.
 */
const props = defineProps({
  user: { type: Object, required: true },
  profiles: { type: Array, default: () => [] },
  services: { type: Array, default: () => [] },
  departments: { type: Array, default: () => [] },
  maxDepth: { type: Number, default: 9 },
  initialTab: { type: String, default: 'profile' },
})
const emit = defineEmits(['close', 'saved', 'action'])

const auth = useAuthStore()
const isSelf = computed(() => auth.user?.id === props.user.id)
const actorAdmin = computed(() => auth.isAdmin)
// Администратора меняет только администратор
const readOnly = computed(() => props.user.role === 'admin' && !actorAdmin.value)

const TABS = computed(() => [
  { key: 'profile', label: 'Профиль' },
  { key: 'access', label: 'Доступ' },
  ...(actorAdmin.value ? [{ key: 'capabilities', label: 'Полномочия' }, { key: 'history', label: 'Журнал' }] : []),
])
const tab = ref(TABS.value.some((t) => t.key === props.initialTab) ? props.initialTab : 'profile')

// ---------- карточка ----------
const form = reactive(profileForm(props.user))
const fieldErrors = ref({})
const formError = ref('')
const saving = ref(false)
const patch = computed(() => profilePatch(props.user, form))
const capabilityKeys = ['capabilities']
const profileDirty = computed(() => Object.keys(patch.value).some((k) => !capabilityKeys.includes(k)))
const capsDirty = computed(() => 'capabilities' in patch.value)

// Новые данные строки (выдан доступ, сброшен пароль): нетронутые поля формы следуют за ними
watch(() => props.user, (now, before) => {
  const old = profileForm(before)
  const next = profileForm(now)
  for (const key of Object.keys(next)) if (JSON.stringify(form[key]) === JSON.stringify(old[key])) form[key] = next[key]
})

const ROLE_OPTIONS = [{ value: 'user', label: ROLE_LABELS.user }, { value: 'admin', label: ROLE_LABELS.admin }]
const badges = computed(() => userBadges(props.user, auth.user?.id).filter((b) => b.key !== 'self' && b.key !== 'admin'))

// ---------- доступ ----------
const policy = ref(null)
const savedDraft = ref(null)
const draft = ref(null)
const accessError = ref('')
async function loadAccess() {
  accessError.value = ''
  try {
    policy.value = await accessApi.userAccess(props.user.id)
    savedDraft.value = policyDraft(policy.value)
    draft.value = policyDraft(policy.value)
  } catch (e) {
    accessError.value = e.message
  }
}
loadAccess()
const accessDirty = computed(() => !!draft.value && policyDirty(draft.value, savedDraft.value))
const dirty = computed(() => Object.keys(patch.value).length > 0 || accessDirty.value)

// ---------- журнал ----------
const history = ref(null)
const historyLoading = ref(false)
const expanded = ref(null)
async function loadHistory() {
  historyLoading.value = true
  try {
    const id = String(props.user.id)
    const pages = await Promise.all([
      usersApi.history({ entity_type: 'user', search: id, page_size: 200 }),
      usersApi.history({ entity_type: 'user_access', search: id, page_size: 200 }),
      usersApi.history({ entity_type: 'session', username: props.user.username, page_size: 20 }),
    ])
    history.value = userHistory(pages.map((p) => p?.items || []), props.user.id).slice(0, 60)
  } catch {
    history.value = []
  } finally {
    historyLoading.value = false
  }
}
watch(tab, (t) => { if (t === 'history' && !history.value) loadHistory() }, { immediate: true })

// ---------- сохранение ----------
async function save() {
  formError.value = ''
  fieldErrors.value = userFormErrors(form)
  if (Object.keys(fieldErrors.value).length) { tab.value = 'profile'; return }
  saving.value = true
  try {
    let updated = props.user
    if (Object.keys(patch.value).length) updated = await usersApi.update(props.user.id, patch.value)
    if (accessDirty.value) await accessApi.setUserAccess(props.user.id, policyBody(draft.value, savedDraft.value))
    toastOk('Изменения сохранены')
    emit('saved', updated)
  } catch (e) {
    formError.value = e.message
    fieldErrors.value = formFieldErrors(e.fields)
    const keys = Object.keys(fieldErrors.value)
    if (keys.some((k) => ['full_name', 'email', 'phone', 'position', 'department_id', 'role', 'is_active'].includes(k))) tab.value = 'profile'
    else if (keys.some((k) => ['overrides', 'services', 'extra_unit_ids', 'profile_id'].includes(k))) tab.value = 'access'
  } finally {
    saving.value = false
  }
}

async function close() {
  if (dirty.value && !await confirm({ title: 'Закрыть без сохранения?', message: 'Внесённые изменения будут потеряны.', confirmText: 'Закрыть' })) return
  emit('close')
}

function toggleCapability(key) {
  form.capabilities = form.capabilities.includes(key) ? form.capabilities.filter((c) => c !== key) : [...form.capabilities, key].sort()
}

const reset = computed(() => resetAction(props.user))
</script>

<template>
  <SideDrawer :title="user.full_name" :width="980" @close="close">
    <template #header>
      <div class="who">
        <UserAvatar :name="user.full_name" :seed="user.username" :src="isSelf ? auth.user?.avatar || '' : ''" :size="48" :muted="!user.is_active" />
        <div class="who-text">
          <h2>{{ user.full_name }}</h2>
          <p class="login">{{ user.username }}<template v-if="user.email"> · {{ user.email }}</template><span v-if="isSelf" class="self">это вы</span></p>
          <div class="row-wrap badges">
            <span class="badge" :class="user.role === 'admin' ? 'badge-brand' : ''">{{ ROLE_LABELS[user.role] }}</span>
            <span class="badge" :class="{ active: 'badge-green', disabled: 'badge-gray', no_access: 'badge-yellow' }[user.status] || 'badge-gray'">{{ STATUS_LABELS[user.status] || STATUS_LABELS.active }}</span>
            <span v-for="b in badges" :key="b.key" class="badge" :class="`tone-${b.tone}`" :title="b.title">{{ b.label }}</span>
            <span v-if="user.profile" class="badge badge-outline" title="Профиль доступа"><AppIcon name="shield" :size="11" />{{ user.profile.name }}</span>
          </div>
        </div>
      </div>
      <dl class="facts">
        <div><dt>Создан</dt><dd class="num">{{ formatDateTime(user.created_at) }}</dd></div>
        <div><dt>Последний вход</dt><dd :title="user.last_login_at ? formatDateTime(user.last_login_at) : ''">{{ user.last_login_at ? formatRelative(user.last_login_at) : 'Ещё не входил' }}</dd></div>
        <div><dt>Способ входа</dt><dd>{{ AUTH_SOURCE_LABELS[user.auth_source] || AUTH_SOURCE_LABELS.local }}<template v-if="user.auth_source === 'ldap' && user.auth_linked_at"> с {{ formatDateTime(user.auth_linked_at).slice(0, 10) }}</template></dd></div>
      </dl>
    </template>

    <template #tabs>
      <nav class="tabs" role="tablist">
        <button v-for="t in TABS" :key="t.key" type="button" role="tab" :aria-selected="tab === t.key" :class="{ active: tab === t.key }" @click="tab = t.key">
          {{ t.label }}
          <i v-if="(t.key === 'profile' && profileDirty) || (t.key === 'access' && accessDirty) || (t.key === 'capabilities' && capsDirty)" class="dirty" title="Есть несохранённые изменения" />
        </button>
      </nav>
    </template>

    <p v-if="readOnly" class="readonly"><AppIcon name="lock" :size="14" />Изменять администратора может только администратор</p>

    <!-- Профиль -->
    <form v-show="tab === 'profile'" id="user-profile" class="form-grid profile-tab" novalidate @submit.prevent="save">
      <fieldset class="bare full form-grid" :disabled="readOnly">
        <label class="field full"><span>ФИО</span>
          <input v-model="form.full_name" class="input" :class="{ invalid: fieldErrors.full_name }" required maxlength="200" />
          <span v-if="fieldErrors.full_name" class="error">{{ fieldErrors.full_name }}</span>
        </label>
        <label class="field"><span>E-mail</span>
          <input v-model="form.email" class="input" :class="{ invalid: fieldErrors.email }" type="email" placeholder="name@company.ru" />
          <span v-if="fieldErrors.email" class="error">{{ fieldErrors.email }}</span>
          <span v-else-if="user.auth_source === 'ldap'" class="help">По e-mail учётная запись сопоставляется с каталогом домена</span>
        </label>
        <label class="field"><span>Телефон</span>
          <input v-model="form.phone" class="input" :class="{ invalid: fieldErrors.phone }" maxlength="50" />
          <span v-if="fieldErrors.phone" class="error">{{ fieldErrors.phone }}</span>
        </label>
        <label class="field"><span>Должность</span>
          <input v-model="form.position" class="input" :class="{ invalid: fieldErrors.position }" maxlength="200" />
        </label>
        <div class="field"><span>Подразделение</span>
          <UnitPicker v-model="form.department_id" :departments="departments" :disabled="readOnly" :invalid="!!fieldErrors.department_id" label="Подразделение" />
          <span v-if="fieldErrors.department_id" class="error">{{ fieldErrors.department_id }}</span>
          <span v-else class="help">Основное подразделение — вершина области доступа</span>
        </div>
        <div class="field full"><span>Руководитель</span>
          <p class="static">
            <template v-if="user.manager"><AppIcon name="user" :size="13" />{{ managerLabel(user.manager) }}</template>
            <span v-else class="muted">Не определён — у подразделения нет руководителя</span>
          </p>
          <span class="help">По структуре компании; назначается в разделе «Структура компании»</span>
        </div>

        <div v-if="actorAdmin" class="field"><span>Роль</span>
          <fieldset class="bare" :disabled="isSelf" :class="{ locked: isSelf }"><SegmentedControl v-model="form.role" :options="ROLE_OPTIONS" /></fieldset>
          <span class="help">{{ isSelf ? 'Свою роль изменить нельзя' : form.role === 'admin' ? 'Полный доступ ко всем службам и администрированию' : 'Доступ — на вкладке «Доступ»' }}</span>
        </div>
        <div class="field" :class="{ full: !actorAdmin }"><span>Статус</span>
          <ToggleSwitch v-model="form.is_active" :disabled="isSelf || readOnly" :label="form.is_active ? 'Активен — может входить в систему' : 'Отключён — вход запрещён'" />
          <span class="help">{{ isSelf ? 'Свою учётную запись отключить нельзя' : 'При отключении все сессии пользователя завершаются' }}</span>
        </div>
      </fieldset>
    </form>

    <!-- Доступ -->
    <div v-show="tab === 'access'" class="access-tab">
      <p v-if="accessError" class="form-error"><AppIcon name="alert" :size="14" />{{ accessError }}</p>
      <div v-else-if="!draft" class="stack"><div class="skeleton" style="height: 120px" /><div class="skeleton" style="height: 260px" /></div>
      <AccessEditor v-else v-model="draft" :profiles="profiles" :services="services" :departments="departments" :user-id="user.id"
                    :home-id="form.department_id" :is-admin="form.role === 'admin'" :disabled="readOnly" :max-depth="maxDepth" />
    </div>

    <!-- Полномочия -->
    <div v-if="actorAdmin" v-show="tab === 'capabilities'" class="stack">
      <p class="muted intro">Полномочия дают часть администрирования без роли администратора. Выдаёт их только администратор.</p>
      <div v-if="form.role === 'admin'" class="admin-note"><AppIcon name="shield" :size="16" />Администратору доступно всё — полномочия не нужны</div>
      <label v-for="c in CAPABILITIES" :key="c.key" class="cap" :class="{ on: form.capabilities.includes(c.key), off: form.role === 'admin' }">
        <input type="checkbox" :checked="form.capabilities.includes(c.key)" :disabled="form.role === 'admin'" @change="toggleCapability(c.key)" />
        <span class="cap-box"><AppIcon v-if="form.capabilities.includes(c.key)" name="check" :size="13" :stroke="2.6" /></span>
        <span class="cap-text"><b>{{ c.label }}</b><small>{{ c.hint }}</small><code>{{ c.key }}</code></span>
      </label>
    </div>

    <!-- Журнал -->
    <div v-if="actorAdmin" v-show="tab === 'history'" class="history">
      <div v-if="historyLoading && !history" class="stack"><div v-for="i in 4" :key="i" class="skeleton" style="height: 44px" /></div>
      <p v-else-if="history && !history.length" class="muted">Записей пока нет</p>
      <ol v-else-if="history" class="events">
        <li v-for="e in history" :key="e.id" :class="{ open: expanded === e.id }">
          <button type="button" class="event" :aria-expanded="expanded === e.id" @click="expanded = expanded === e.id ? null : e.id">
            <span class="badge" :class="`tone-${ACTION_TONES[e.action] || 'gray'}`">{{ actionLabel(e.action) }}</span>
            <span class="ev-text">{{ e.summary }}</span>
            <span class="ev-meta" :title="formatDateTime(e.occurred_at)">{{ e.username || 'система' }} · {{ formatRelative(e.occurred_at) }}</span>
            <AppIcon name="chevron-down" :size="14" class="ev-chev" />
          </button>
          <div v-if="expanded === e.id" class="ev-body"><AuditDiff :entry="e" /></div>
        </li>
      </ol>
      <router-link v-if="history?.length" :to="{ path: '/admin/audit', query: { search: user.username } }" class="link small">Весь журнал изменений</router-link>
    </div>

    <p v-if="formError" class="form-error"><AppIcon name="alert" :size="14" />{{ formError }}</p>

    <template #footer>
      <button v-if="needsAccess(user)" class="btn btn-ghost grant" type="button" :disabled="readOnly" @click="emit('action', { type: 'grant', user })">
        <AppIcon name="key" :size="15" />Выдать доступ
      </button>
      <button v-else class="btn btn-ghost" type="button" :disabled="isSelf || readOnly" :title="isSelf ? 'Свой пароль меняется в профиле' : reset.label" @click="emit('action', { type: 'reset', user })">
        <AppIcon name="key" :size="15" /><span class="hide-sm">{{ reset.label }}</span>
      </button>
      <button class="btn btn-ghost btn-danger" type="button" :disabled="isSelf || readOnly" :title="isSelf ? 'Нельзя удалить свою учётную запись' : 'Удалить пользователя'" @click="emit('action', { type: 'delete', user })">
        <AppIcon name="trash" :size="15" /><span class="hide-sm">Удалить</span>
      </button>
      <span class="spacer" />
      <button class="btn" type="button" @click="close">Отмена</button>
      <button class="btn btn-primary" type="button" :disabled="saving || !dirty || readOnly" data-testid="user-save" @click="save">{{ saving ? 'Сохранение…' : 'Сохранить' }}</button>
    </template>
  </SideDrawer>
</template>

<style scoped>
.who { display: flex; gap: 14px; align-items: flex-start; }
.who-text { min-width: 0; }
.who h2 { font-size: 18px; line-height: 1.25; }
.login { margin-top: 1px; font-size: var(--fs-sm); color: var(--muted); overflow-wrap: anywhere; }
.self { margin-left: 8px; font-size: var(--fs-xs); color: var(--text-2); }
.badges { margin-top: 8px; gap: 6px; }
.badge-outline { background: transparent; border: 1px solid var(--border-strong); color: var(--text-2); }
.tone-blue { background: color-mix(in srgb, var(--accent) 13%, transparent); color: var(--accent); }
.tone-yellow { background: color-mix(in srgb, var(--light-yellow) 16%, transparent); color: color-mix(in srgb, var(--light-yellow) 80%, var(--text)); }
.tone-green { background: color-mix(in srgb, var(--light-green) 14%, transparent); color: var(--light-green); }
.tone-red { background: color-mix(in srgb, var(--light-red) 13%, transparent); color: var(--light-red); }
.tone-dark { background: var(--surface-3); color: var(--text); }
.facts { display: flex; flex-wrap: wrap; gap: 8px 28px; margin: 16px 0 0; padding-top: 12px; border-top: 1px dashed var(--border); }
.facts dt { font-size: var(--fs-xs); color: var(--muted); }
.facts dd { margin: 2px 0 0; font-size: var(--fs-sm); color: var(--text); }
.tabs { display: flex; gap: 4px; padding: 0 22px; border-bottom: 1px solid var(--border); overflow-x: auto; scrollbar-width: none; }
.tabs button { position: relative; display: inline-flex; align-items: center; gap: 6px; height: 38px; padding: 0 12px; border: 0; background: transparent; color: var(--text-2); font-weight: 560; cursor: pointer; white-space: nowrap; }
.tabs button:hover { color: var(--text); }
.tabs button.active { color: var(--text); }
.tabs button.active::after { content: ''; position: absolute; left: 8px; right: 8px; bottom: -1px; height: 2px; border-radius: 2px; background: var(--brand); }
.dirty { width: 6px; height: 6px; border-radius: 50%; background: var(--light-yellow); }
.readonly { display: flex; align-items: center; gap: 8px; margin-bottom: 14px; padding: 9px 12px; border-radius: var(--radius); background: var(--surface-2); color: var(--text-2); font-size: var(--fs-sm); }
.bare { margin: 0; padding: 0; border: 0; min-width: 0; }
.locked { opacity: .55; }
.help { font-size: var(--fs-xs); color: var(--muted); }
.error { font-size: var(--fs-xs); color: var(--light-red); }
.static { display: flex; align-items: center; gap: 7px; min-height: 34px; font-size: var(--fs-base); color: var(--text); }
.static :deep(svg) { color: var(--muted); }
.intro { font-size: var(--fs-sm); }
.admin-note { display: flex; align-items: center; gap: 8px; padding: 10px 12px; border-radius: 10px; background: var(--brand-soft); color: var(--brand); font-size: var(--fs-sm); font-weight: 560; }
.cap { display: flex; gap: 12px; align-items: flex-start; padding: 14px 16px; border: 1px solid var(--border); border-radius: var(--radius-lg); cursor: pointer; transition: border-color var(--t-fast), background var(--t-fast); max-width: 640px; }
.cap:hover { border-color: var(--border-strong); }
.cap.on { border-color: color-mix(in srgb, var(--brand) 40%, var(--border)); background: color-mix(in srgb, var(--brand) 3%, var(--surface)); }
.cap.off { opacity: .55; cursor: not-allowed; }
.cap input { position: absolute; opacity: 0; width: 1px; height: 1px; }
.cap-box { width: 18px; height: 18px; flex: 0 0 18px; margin-top: 1px; display: grid; place-items: center; border-radius: 5px; border: 1.5px solid var(--border-strong); color: #fff; background: var(--surface); }
.cap.on .cap-box { background: var(--brand); border-color: var(--brand); }
.cap:has(input:focus-visible) .cap-box { outline: 2px solid var(--focus); outline-offset: 2px; }
.cap-text { display: flex; flex-direction: column; gap: 2px; }
.cap-text b { font-weight: 600; }
.cap-text small { font-size: var(--fs-sm); color: var(--muted); }
.cap-text code { font-family: var(--font-mono); font-size: var(--fs-xs); color: var(--faint); }
.history { display: flex; flex-direction: column; gap: 12px; }
.events { list-style: none; margin: 0; padding: 0; border: 1px solid var(--border); border-radius: var(--radius-lg); overflow: hidden; }
.events li { border-bottom: 1px solid var(--border); }
.events li:last-child { border-bottom: 0; }
.event { display: grid; grid-template-columns: auto minmax(0, 1fr) auto 16px; gap: 10px; align-items: center; width: 100%; padding: 9px 12px; border: 0; background: transparent; text-align: left; cursor: pointer; color: var(--text); font-size: var(--fs-sm); }
.event:hover { background: var(--row-hover); }
.ev-text { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ev-meta { font-size: var(--fs-xs); color: var(--muted); white-space: nowrap; }
.ev-chev { color: var(--faint); transition: transform var(--t-fast); }
.open .ev-chev { transform: rotate(180deg); }
.ev-body { padding: 0 12px 12px; }
.small { font-size: var(--fs-sm); }
.form-error { display: flex; align-items: center; gap: 6px; margin-top: 16px; font-size: var(--fs-sm); color: var(--light-red); }
.grant { color: var(--light-green); }
@media (max-width: 640px) {
  .hide-sm { display: none; }
  .facts { display: none; }
  .who h2 { font-size: 16px; }
  .event { grid-template-columns: auto minmax(0, 1fr) 16px; }
  .ev-meta { grid-column: 2; grid-row: 2; }
}
</style>
