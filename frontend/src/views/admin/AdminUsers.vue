<script setup>
import { computed, ref, watch } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import FilterBar from '@/components/ui/FilterBar.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import SegmentedControl from '@/components/ui/SegmentedControl.vue'
import UserAvatar from '@/components/admin/UserAvatar.vue'
import UserDrawer from '@/components/admin/UserDrawer.vue'
import UserCreateDialog from '@/components/admin/UserCreateDialog.vue'
import OneTimePassword from '@/components/admin/OneTimePassword.vue'
import GrantAccessDialog from '@/components/admin/GrantAccessDialog.vue'
import DeleteUserDialog from '@/components/admin/DeleteUserDialog.vue'
import { adminApi } from '@/api/services'
import { accessApi, directoryApi, usersApi } from '@/api/access'
import { useAsync } from '@/composables/useAsync'
import { useQueryState } from '@/composables/useQueryState'
import { confirm } from '@/composables/useConfirm'
import { toastOk } from '@/composables/useToast'
import { useAuthStore } from '@/stores/auth'
import { INDIVIDUAL_LABEL } from '@/domain/access'
import {
  departmentParts, managerLabel, needsAccess, personalServices, resetAction, summaryParts, USER_FILTERS, userBadges, usersParams,
} from '@/domain/admin'
import { formatDateTime, formatRelative, plural } from '@/utils/format'

const auth = useAuthStore()
const { state: f, reset: resetFilters, isDefault } = useQueryState({ ...USER_FILTERS })

// Справочники: службы и глубина (meta), профили, подразделения, включён ли вход по домену
const meta = useAsync(() => accessApi.meta())
const profiles = useAsync(() => accessApi.profiles())
const departments = useAsync(() => adminApi.departments())
const loginConfig = useAsync(() => directoryApi.loginConfig())
const services = computed(() => meta.data.value?.services || [])
const ldapEnabled = computed(() => !!loginConfig.data.value?.ldap?.enabled)
const ready = computed(() => !!(meta.data.value && profiles.data.value && departments.data.value))

const params = computed(() => usersParams(f))
const { data, loading, reload } = useAsync(() => usersApi.list(params.value), { immediate: false })
let timer
watch(params, (now, before) => {
  clearTimeout(timer)
  timer = setTimeout(reload, before && now.search !== before.search ? 250 : 0)
}, { immediate: true, deep: true })

const users = computed(() => data.value?.items || [])
const summary = computed(() => summaryParts(data.value?.summary))
const found = computed(() => (data.value ? `Показано ${users.value.length} ${plural(users.value.length, ['пользователь', 'пользователя', 'пользователей'])}` : ''))
function applySummary(part) {
  resetFilters()
  Object.assign(f, part.filter)
}
function summaryActive(part) {
  const keys = Object.keys(part.filter)
  return keys.length > 0 && keys.every((k) => f[k] === part.filter[k]) && Object.keys(USER_FILTERS).filter((k) => !keys.includes(k)).every((k) => !f[k])
}

const STATUS_OPTIONS = [
  { value: '', label: 'Все' }, { value: 'active', label: 'Активные' }, { value: 'disabled', label: 'Отключённые' }, { value: 'no_access', label: 'Без доступа' },
]
const deptOptions = computed(() => (departments.data.value || []).map((d) => ({
  id: d.id, path: d.path, label: `${' '.repeat(Math.max(0, (d.level || 1) - 1))}${d.name}`,
})))

// ---------- карточка, создание, действия ----------
const selected = ref(null)
const drawerTab = ref('profile')
const creating = ref(false)
const secret = ref(null)
const granting = ref(null)
const deleting = ref(null)
const busy = ref(false)
const deleteError = ref('')

function open(user, tab = 'profile') {
  if (!ready.value) return
  drawerTab.value = tab
  selected.value = user
}
function replaceRow(user) {
  if (!user || !data.value) return
  data.value = { ...data.value, items: data.value.items.map((u) => (u.id === user.id ? user : u)) }
  if (selected.value?.id === user.id) selected.value = user
}
function afterSave() {
  selected.value = null
  reload()
  profiles.reload()
}
async function afterCreate(result) {
  creating.value = false
  toastOk(`Пользователь ${result.user.username} создан`)
  if (result.temporary_password) secret.value = { title: 'Пользователь создан', password: result.temporary_password, user: result.user }
  await reload()
  profiles.reload()
}

async function toggleActive(user) {
  if (user.id === auth.user?.id) return
  if (user.is_active) {
    const ok = await confirm({
      title: 'Отключить пользователя?',
      message: `${user.full_name} не сможет войти в систему, открытые сессии завершатся. Карточка, доступ и место в структуре сохранятся — включить пользователя можно в любой момент.`,
      confirmText: 'Отключить', danger: true,
    })
    if (!ok) return
  }
  replaceRow(await usersApi.update(user.id, { is_active: !user.is_active }))
  toastOk(user.is_active ? `${user.full_name} отключён` : `${user.full_name} включён`)
  reload()
}

async function resetPassword(user) {
  const action = resetAction(user)
  if (!await confirm({ title: action.title, message: action.message, confirmText: action.confirmText })) return
  const result = await usersApi.resetPassword(user.id)
  secret.value = { title: user.auth_source === 'ldap' ? 'Пароль системы выдан' : 'Временный пароль', password: result.temporary_password, user: result.user || user }
  replaceRow(result.user)
  reload()
}

async function grant(method) {
  const user = granting.value
  busy.value = true
  try {
    const result = await usersApi.grantAccess(user.id, method)
    granting.value = null
    replaceRow(result.user)
    if (result.temporary_password) secret.value = { title: 'Доступ выдан', password: result.temporary_password, user: result.user }
    else toastOk(`Доступ выдан: ${user.full_name} входит по учётной записи домена`)
    reload()
  } finally {
    busy.value = false
  }
}

function askDelete(user) {
  deleteError.value = ''
  deleting.value = user
}
async function confirmDelete() {
  const user = deleting.value
  busy.value = true
  deleteError.value = ''
  try {
    await usersApi.remove(user.id)
    toastOk(`Пользователь ${user.username} удалён`)
    deleting.value = null
    if (selected.value?.id === user.id) selected.value = null
    reload()
    profiles.reload()
  } catch (e) {
    deleteError.value = e.message
  } finally {
    busy.value = false
  }
}
async function disableInstead() {
  const user = deleting.value
  busy.value = true
  try {
    replaceRow(await usersApi.update(user.id, { is_active: false }))
    toastOk(`${user.full_name} отключён`)
    deleting.value = null
    reload()
  } catch (e) {
    deleteError.value = e.message
  } finally {
    busy.value = false
  }
}

function onDrawerAction({ type, user }) {
  if (type === 'grant') granting.value = user
  else if (type === 'reset') resetPassword(user)
  else if (type === 'delete') askDelete(user)
}

const isSelf = (u) => u.id === auth.user?.id
// Администратора меняет только администратор
const locked = (u) => u.role === 'admin' && !auth.isAdmin
</script>

<template>
  <div class="page">
    <PageHeader title="Пользователи" description="Учётные записи, место в структуре, профили доступа и способ входа">
      <router-link to="/admin/access-profiles" class="btn"><AppIcon name="shield" :size="15" />Профили доступа</router-link>
      <button class="btn btn-primary" type="button" :disabled="!ready" data-testid="user-add" @click="creating = true">
        <AppIcon name="plus" :size="15" />Добавить пользователя
      </button>
    </PageHeader>

    <nav v-if="summary.length" class="summary" aria-label="Сводка" data-testid="users-summary">
      <template v-for="(p, i) in summary" :key="p.key">
        <span v-if="i" class="dot" aria-hidden="true">·</span>
        <button type="button" class="sum" :class="{ zero: !p.count, on: summaryActive(p) }" :aria-pressed="summaryActive(p)"
                :title="p.key === 'total' ? 'Показать всех' : `Показать: ${p.label}`" @click="applySummary(p)">
          <b class="num">{{ p.count }}</b> {{ p.label }}
        </button>
      </template>
    </nav>

    <FilterBar :summary="isDefault() ? '' : found" :resettable="!isDefault()" @reset="resetFilters">
      <label class="search"><AppIcon name="search" :size="14" /><input v-model="f.search" type="search" placeholder="ФИО, логин, e-mail, должность" aria-label="Поиск" /></label>
      <SegmentedControl v-model="f.status" :options="STATUS_OPTIONS" size="sm" />
      <select v-model="f.role" class="select f-role" :class="{ set: f.role }" aria-label="Роль">
        <option value="">Все роли</option><option value="admin">Администраторы</option><option value="user">Пользователи</option>
      </select>
      <select v-model="f.department" class="select f-dept" :class="{ set: f.department }" aria-label="Подразделение">
        <option value="">Все подразделения</option>
        <option value="none">Без подразделения</option>
        <option v-for="d in deptOptions" :key="d.id" :value="String(d.id)" :title="d.path">{{ d.label }}</option>
      </select>
      <select v-model="f.profile" class="select f-profile" :class="{ set: f.profile }" aria-label="Профиль доступа">
        <option value="">Все профили</option>
        <option value="none">{{ INDIVIDUAL_LABEL }}</option>
        <option v-for="p in profiles.data.value || []" :key="p.id" :value="String(p.id)">{{ p.name }}</option>
      </select>
      <select v-model="f.auth" class="select f-auth" :class="{ set: f.auth }" aria-label="Способ входа">
        <option value="">Любой способ входа</option><option value="local">Пароль системы</option><option value="ldap">Вход по домену</option>
      </select>
    </FilterBar>

    <section class="card list" aria-label="Пользователи">
      <div class="grid-head" role="row">
        <span role="columnheader">Пользователь</span>
        <span role="columnheader">Должность и подразделение</span>
        <span role="columnheader">Профиль доступа<span class="and-status"> · статус</span></span>
        <span role="columnheader" class="h-status">Статус</span>
        <span role="columnheader" class="act-head">Действия</span>
      </div>
      <div v-if="loading && !data" class="skeleton-rows"><div v-for="i in 6" :key="i" class="skeleton" /></div>
      <template v-else>
        <div v-for="u in users" :key="u.id" class="urow" role="row" :class="{ off: !u.is_active }" :data-user="u.username" @click="open(u)">
          <div class="c-user" role="cell">
            <UserAvatar :name="u.full_name" :seed="u.username" :src="isSelf(u) ? auth.user?.avatar || '' : ''" :muted="!u.is_active" />
            <div class="who">
              <span class="name">
                <button type="button" class="name-btn" :aria-label="`Открыть карточку: ${u.full_name}`" @click.stop="open(u)">{{ u.full_name }}</button>
                <span v-for="b in userBadges(u, auth.user?.id)" :key="b.key" class="ubadge" :class="`t-${b.tone}`" :title="b.title" :data-badge="b.key">{{ b.label }}</span>
              </span>
              <span class="login">{{ u.username }}<template v-if="u.email"> · {{ u.email }}</template></span>
            </div>
          </div>
          <div class="c-org" role="cell">
            <span class="pos" :class="{ empty: !u.position }">{{ u.position || 'Должность не указана' }}</span>
            <span v-if="u.department" class="dept" :title="u.department.path">
              <b>{{ departmentParts(u.department).name }}</b><template v-if="departmentParts(u.department).parent"> · {{ departmentParts(u.department).parent }}</template>
            </span>
            <span v-else class="dept faint">Без подразделения</span>
            <span v-if="u.manager" class="mgr" :title="u.manager.source === 'explicit' ? 'Руководитель назначен явно' : 'Руководитель по структуре'">
              <AppIcon name="arrow-up" :size="11" />{{ managerLabel(u.manager) }}
            </span>
          </div>
          <div class="c-profile" role="cell">
            <span v-if="u.role === 'admin'" class="prof admin"><AppIcon name="shield" :size="13" />Полный доступ</span>
            <span v-else-if="u.profile" class="prof">{{ u.profile.name }}</span>
            <span v-else class="prof indiv">{{ INDIVIDUAL_LABEL }}</span>
            <span v-if="personalServices(u, services).length" class="personal" :title="personalServices(u, services).map((s) => `${s.title} — ${s.label}`).join('\n')">
              <em>лично:</em> {{ personalServices(u, services).map((s) => `${s.title} — ${s.label}`).join(', ') }}
            </span>
          </div>
          <div class="c-status" role="cell">
            <button type="button" class="pill" :class="u.is_active ? 'on' : 'off'" :disabled="isSelf(u) || locked(u)" :aria-pressed="u.is_active"
                    :title="isSelf(u) ? 'Свою учётную запись отключить нельзя' : u.is_active ? 'Отключить пользователя' : 'Включить пользователя'"
                    data-testid="status-toggle" @click.stop="toggleActive(u)">
              <i />{{ u.is_active ? 'Активен' : 'Отключён' }}
            </button>
            <span class="last" :title="u.last_login_at ? formatDateTime(u.last_login_at) : ''">{{ u.last_login_at ? `вход ${formatRelative(u.last_login_at)}` : 'не входил' }}</span>
          </div>
          <div class="c-actions" role="cell" @click.stop>
            <button type="button" class="ibtn" title="Изменить" :aria-label="`Изменить: ${u.full_name}`" @click="open(u)"><AppIcon name="edit" :size="15" /></button>
            <button type="button" class="ibtn access-btn" title="Доступ" :aria-label="`Доступ: ${u.full_name}`" @click="open(u, 'access')"><AppIcon name="shield" :size="15" /></button>
            <button v-if="needsAccess(u)" type="button" class="ibtn grant" title="Выдать доступ" :aria-label="`Выдать доступ: ${u.full_name}`" :disabled="locked(u)" data-testid="grant-access" @click="granting = u">
              <AppIcon name="key" :size="15" />
            </button>
            <button v-else type="button" class="ibtn" :title="isSelf(u) ? 'Свой пароль меняется в профиле' : resetAction(u).label" :aria-label="`${resetAction(u).label}: ${u.full_name}`"
                    :disabled="isSelf(u) || locked(u)" @click="resetPassword(u)">
              <AppIcon name="lock" :size="15" />
            </button>
            <button type="button" class="ibtn danger" :title="isSelf(u) ? 'Нельзя удалить свою учётную запись' : 'Удалить'" :aria-label="`Удалить: ${u.full_name}`"
                    :disabled="isSelf(u) || locked(u)" @click="askDelete(u)">
              <AppIcon name="trash" :size="15" />
            </button>
          </div>
        </div>
        <EmptyState v-if="data && !users.length" compact icon="users" title="Никого не нашли"
                    :text="isDefault() ? 'Добавьте первого пользователя.' : 'Измените поиск или фильтры.'">
          <button v-if="!isDefault()" class="btn btn-sm" type="button" @click="resetFilters">Сбросить фильтры</button>
        </EmptyState>
      </template>
    </section>

    <UserDrawer v-if="selected" :key="selected.id" :user="selected" :profiles="profiles.data.value || []" :services="services"
                :departments="departments.data.value || []" :max-depth="meta.data.value?.max_drill_depth ?? 9" :initial-tab="drawerTab"
                @close="selected = null" @saved="afterSave" @action="onDrawerAction" />
    <UserCreateDialog v-if="creating" :profiles="profiles.data.value || []" :services="services" :departments="departments.data.value || []"
                      :ldap-enabled="ldapEnabled" @close="creating = false" @created="afterCreate" />
    <GrantAccessDialog v-if="granting" :user="granting" :ldap-enabled="ldapEnabled" :busy="busy" @close="granting = null" @confirm="grant" />
    <DeleteUserDialog v-if="deleting" :user="deleting" :busy="busy" :error="deleteError" @close="deleting = null" @delete="confirmDelete" @disable="disableInstead" />
    <OneTimePassword v-if="secret" :title="secret.title" :password="secret.password" :user="secret.user" @close="secret = null" />
  </div>
</template>

<style scoped>
.summary { display: flex; flex-wrap: wrap; align-items: center; gap: 2px 4px; margin-top: -8px; font-size: var(--fs-sm); color: var(--muted); }
.dot { color: var(--faint); }
.sum { display: inline-flex; align-items: baseline; gap: 4px; padding: 2px 6px; border: 0; border-radius: 6px; background: transparent; color: var(--text-2); font-size: var(--fs-sm); cursor: pointer; }
.sum b { color: var(--text); font-weight: 650; }
.sum:hover { background: var(--surface-3); }
.sum.zero { color: var(--faint); }
.sum.zero b { color: var(--faint); font-weight: 560; }
.sum.on { background: var(--brand-soft); color: var(--brand); }
.sum.on b { color: var(--brand); }
.search { display: flex; align-items: center; gap: 8px; height: 32px; padding: 0 10px; border: 1px solid var(--border-strong); border-radius: var(--radius); color: var(--muted); min-width: 240px; background: var(--surface); }
.search input { border: 0; outline: 0; background: transparent; width: 100%; color: var(--text); font-size: var(--fs-sm); }
.search:focus-within { border-color: var(--accent); box-shadow: 0 0 0 3px var(--focus); }
.f-role { width: 150px !important; min-width: 0 !important; }
.f-dept { width: 220px !important; min-width: 0 !important; }
.f-profile { width: 220px !important; min-width: 0 !important; }
.f-auth { width: 190px !important; min-width: 0 !important; }
.select.set { border-color: color-mix(in srgb, var(--accent) 55%, var(--border-strong)); background-color: color-mix(in srgb, var(--accent) 5%, var(--surface)); }

.list { overflow: hidden; container-type: inline-size; }
.grid-head, .urow {
  display: grid; grid-template-columns: minmax(230px, 1.45fr) minmax(190px, 1.3fr) minmax(160px, 1fr) 124px 150px;
  grid-template-areas: 'user org profile status actions'; gap: 14px; align-items: center; padding: 0 16px;
}
.c-user { grid-area: user; }
.c-org { grid-area: org; }
.c-profile { grid-area: profile; }
.c-status { grid-area: status; }
.c-actions { grid-area: actions; }
.h-status { grid-area: status; }
.and-status { display: none; }
.grid-head { height: 38px; background: var(--surface-2); border-bottom: 1px solid var(--border); font-size: var(--fs-xs); font-weight: 620; text-transform: uppercase; letter-spacing: .04em; color: var(--muted); }
.act-head { text-align: right; }
.urow { padding-top: 11px; padding-bottom: 11px; border-bottom: 1px solid var(--border); cursor: pointer; transition: background var(--t-fast); }
.urow:last-of-type { border-bottom: 0; }
.urow:hover { background: var(--row-hover); }
.urow.off .c-user, .urow.off .c-org, .urow.off .c-profile { opacity: .6; }
.c-user { display: flex; align-items: center; gap: 11px; min-width: 0; }
.who { display: flex; flex-direction: column; min-width: 0; line-height: 1.3; }
.name { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 6px; }
.name-btn { padding: 0; border: 0; background: none; color: var(--text); font-weight: 600; font-size: var(--fs-base); text-align: left; cursor: pointer; overflow-wrap: anywhere; }
.name-btn:hover { color: var(--brand); }
.ubadge { display: inline-flex; align-items: center; height: 18px; padding: 0 7px; border-radius: 99px; font-size: 10.5px; font-weight: 650; white-space: nowrap; background: var(--surface-3); color: var(--muted); }
.t-self { background: var(--surface-3); color: var(--text-2); }
.t-brand { background: var(--brand-soft); color: var(--brand); }
.t-blue { background: color-mix(in srgb, var(--accent) 13%, transparent); color: var(--accent); }
.t-yellow { background: color-mix(in srgb, var(--light-yellow) 17%, transparent); color: color-mix(in srgb, var(--light-yellow) 78%, var(--text)); }
.t-gray { background: var(--surface-3); color: var(--muted); }
.login { font-size: var(--fs-xs); color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.c-org { display: flex; flex-direction: column; min-width: 0; line-height: 1.35; font-size: var(--fs-sm); }
.pos { color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pos.empty { color: var(--faint); font-style: italic; }
.dept { color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dept b { color: var(--text-2); font-weight: 560; }
.mgr { display: inline-flex; align-items: center; gap: 4px; font-size: var(--fs-xs); color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mgr :deep(svg) { flex: 0 0 auto; }
.c-profile { display: flex; flex-direction: column; min-width: 0; line-height: 1.35; }
.prof { font-size: var(--fs-sm); font-weight: 560; color: var(--text); }
.prof.admin { display: inline-flex; align-items: center; gap: 5px; color: var(--brand); }
.prof.indiv { color: var(--text-2); font-weight: 500; }
.personal { font-size: var(--fs-xs); color: var(--text-2); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.personal em { font-style: normal; font-weight: 600; color: var(--accent); }
.c-status { display: flex; flex-direction: column; align-items: flex-start; gap: 3px; }
.pill { display: inline-flex; align-items: center; gap: 6px; height: 26px; padding: 0 11px; border: 1px solid transparent; border-radius: 99px; font-size: var(--fs-xs); font-weight: 620; cursor: pointer; white-space: nowrap; transition: border-color var(--t-fast), background var(--t-fast); }
.pill i { width: 7px; height: 7px; border-radius: 50%; background: currentColor; }
.pill.on { background: color-mix(in srgb, var(--light-green) 13%, transparent); color: var(--light-green); }
.pill.off { background: var(--surface-3); color: var(--muted); border-color: var(--border); }
.pill:hover:not(:disabled) { border-color: currentColor; }
.pill:disabled { cursor: not-allowed; opacity: .75; }
.pill:focus-visible { outline: 2px solid var(--focus); outline-offset: 1px; }
.last { font-size: var(--fs-xs); color: var(--faint); white-space: nowrap; }
.c-actions { display: flex; justify-content: flex-end; gap: 2px; cursor: default; }
.ibtn { width: 30px; height: 30px; display: grid; place-items: center; border: 0; border-radius: 8px; background: transparent; color: var(--muted); cursor: pointer; transition: background var(--t-fast), color var(--t-fast); }
.ibtn:hover:not(:disabled) { background: var(--surface-3); color: var(--text); }
.ibtn.grant { color: var(--light-green); }
.ibtn.grant:hover:not(:disabled) { background: color-mix(in srgb, var(--light-green) 12%, transparent); color: var(--light-green); }
.ibtn.danger:hover:not(:disabled) { background: color-mix(in srgb, var(--light-red) 10%, transparent); color: var(--light-red); }
.ibtn:disabled { opacity: .3; cursor: not-allowed; }
.ibtn:focus-visible, .name-btn:focus-visible { outline: 2px solid var(--focus); outline-offset: 1px; }
.skeleton-rows { display: flex; flex-direction: column; gap: 10px; padding: 14px; }
.skeleton-rows .skeleton { height: 46px; }

@container (max-width: 1080px) {
  .grid-head, .urow { grid-template-columns: minmax(210px, 1.3fr) minmax(170px, 1.2fr) minmax(170px, 1fr) auto; grid-template-areas: 'user org profile actions'; gap: 12px; }
  .urow { grid-template-areas: 'user org profile actions' 'user org status actions'; row-gap: 6px; }
  .h-status { display: none; }
  .and-status { display: inline; }
  .c-status { flex-direction: row; align-items: center; gap: 8px; }
  .ibtn { width: 28px; }
}
@container (max-width: 780px) {
  .grid-head { display: none; }
  .urow { grid-template-columns: minmax(0, 1fr) auto; grid-template-areas: 'user actions' 'org org' 'profile status'; gap: 8px 10px; padding: 14px; }
  .c-actions { align-self: start; }
  .c-org { padding-left: 45px; }
  .c-profile { padding-left: 45px; }
  .c-status { flex-direction: column; align-items: flex-end; gap: 3px; }
  .access-btn { display: none; }
}
@media (max-width: 860px) {
  .search { min-width: 0; flex: 1 1 100%; }
  .f-role, .f-dept, .f-profile, .f-auth { width: calc(50% - 6px) !important; }
}
@media (max-width: 640px) {
  .ibtn { width: 34px; height: 34px; }
  .pill { height: 30px; }
}
</style>
