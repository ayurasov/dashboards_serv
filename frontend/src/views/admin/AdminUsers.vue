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
import { adminApi } from '@/api/services'
import { useAsync } from '@/composables/useAsync'
import { useQueryState } from '@/composables/useQueryState'
import { toastOk } from '@/composables/useToast'
import { useAuthStore } from '@/stores/auth'
import { accessSummary, ROLE_LABELS, sortServices } from '@/domain/admin'
import { formatDateTime, formatRelative, plural } from '@/utils/format'

const auth = useAuthStore()
const { state: f, reset, isDefault } = useQueryState({ search: '', status: 'all', service: '' })

const services = useAsync(() => adminApi.services())
const departments = useAsync(() => adminApi.departments())
const serviceList = computed(() => sortServices(services.data.value || []))

const params = computed(() => ({ search: f.search.trim(), status: f.status === 'all' ? '' : f.status, service: f.service }))
const { data, loading, reload } = useAsync(() => adminApi.users(params.value), { immediate: false })
let timer
watch(params, (now, before) => {
  clearTimeout(timer)
  timer = setTimeout(reload, before && now.search !== before.search ? 250 : 0)
}, { immediate: true, deep: true })

const STATUS_OPTIONS = [{ value: 'all', label: 'Все' }, { value: 'active', label: 'Активные' }, { value: 'disabled', label: 'Отключённые' }]
const users = computed(() => data.value || [])
const summary = computed(() => `${users.value.length} ${plural(users.value.length, ['пользователь', 'пользователя', 'пользователей'])}`)
const MAX_CHIPS = 3
function chips(user) {
  return accessSummary(user, serviceList.value)
}

// ---------- карточка и создание ----------
const selected = ref(null)
const creating = ref(false)
const secret = ref(null)

function open(user) {
  if (!services.data.value || !departments.data.value) return
  selected.value = user
}
function afterSave() {
  selected.value = null
  reload()
}
function afterDelete() {
  selected.value = null
  reload()
}
function afterCreate(result) {
  creating.value = false
  toastOk(`Пользователь ${result.user.username} создан`)
  if (result.temporary_password) secret.value = { password: result.temporary_password, user: result.user }
  reload()
}
</script>

<template>
  <div class="page">
    <PageHeader title="Пользователи" description="Учётные записи, роли и доступ к службам">
      <button class="btn btn-primary" type="button" :disabled="!services.data.value" @click="creating = true">
        <AppIcon name="plus" :size="15" />Добавить пользователя
      </button>
    </PageHeader>

    <FilterBar :summary="data ? summary : ''" :resettable="!isDefault()" @reset="reset">
      <label class="search"><AppIcon name="search" :size="14" /><input v-model="f.search" type="search" placeholder="ФИО, логин или e-mail" aria-label="Поиск" /></label>
      <SegmentedControl v-model="f.status" :options="STATUS_OPTIONS" />
      <label class="field"><span>Служба</span>
        <select v-model="f.service" class="select svc-select">
          <option value="">Все службы</option>
          <option v-for="s in serviceList" :key="s.key" :value="s.key">{{ s.title }}</option>
        </select>
      </label>
    </FilterBar>

    <section class="card">
      <div class="table-wrap">
        <table class="table">
          <thead>
            <tr>
              <th>Пользователь</th>
              <th class="pos-col">Должность</th>
              <th>Роль и доступ</th>
              <th>Последний вход</th>
              <th>Статус</th>
              <th class="chev-col" />
            </tr>
          </thead>
          <tbody v-if="data">
            <tr v-for="u in users" :key="u.id" class="clickable" :class="{ off: !u.is_active }" tabindex="0"
                @click="open(u)" @keydown.enter="open(u)">
              <td>
                <div class="who">
                  <UserAvatar :name="u.full_name" :seed="u.username" :src="u.id === auth.user?.id ? auth.user?.avatar || '' : ''" :muted="!u.is_active" />
                  <div class="who-text">
                    <span class="name">{{ u.full_name }}<span v-if="u.id === auth.user?.id" class="self">вы</span></span>
                    <span class="login">{{ u.username }}<template v-if="u.email"> · {{ u.email }}</template><span v-if="u.position" class="pos-inline"> · {{ u.position }}</span></span>
                  </div>
                </div>
              </td>
              <td class="muted pos pos-col">{{ u.position || '—' }}</td>
              <td>
                <span v-if="u.role === 'admin'" class="admin-role"><span class="badge badge-brand"><AppIcon name="shield" :size="12" />{{ ROLE_LABELS.admin }}</span><span class="muted">все службы</span></span>
                <span v-else-if="!u.access.length" class="faint">Нет доступа</span>
                <div v-else class="acc-list">
                  <span v-for="c in chips(u).slice(0, MAX_CHIPS)" :key="c.key" class="acc" :title="`${c.title}: ${c.label}${c.scoped ? ', только свои подразделения' : ''}`">
                    <b>{{ c.short }}</b><span class="sep">·</span>{{ c.label }}<AppIcon v-if="c.scoped" name="building" :size="12" class="scoped" />
                  </span>
                  <span v-if="chips(u).length > MAX_CHIPS" class="acc more" :title="chips(u).slice(MAX_CHIPS).map((c) => `${c.short}: ${c.label}`).join('\n')">
                    +{{ chips(u).length - MAX_CHIPS }}
                  </span>
                </div>
              </td>
              <td class="nowrap" :title="u.last_login_at ? formatDateTime(u.last_login_at) : ''">
                <span v-if="u.last_login_at">{{ formatRelative(u.last_login_at) }}</span>
                <span v-else class="faint">Не входил</span>
              </td>
              <td class="nowrap">
                <span class="status" :class="u.is_active ? 'on' : ''"><i />{{ u.is_active ? 'Активен' : 'Отключён' }}</span>
                <span v-if="u.must_change_password" class="tmp" title="При входе пользователь должен сменить пароль"><AppIcon name="key" :size="11" />временный пароль</span>
              </td>
              <td class="chev-col"><AppIcon name="chevron-right" :size="16" class="chev" /></td>
            </tr>
          </tbody>
        </table>
        <div v-if="loading && !data" class="skeleton-rows">
          <div v-for="i in 5" :key="i" class="skeleton" />
        </div>
        <EmptyState v-else-if="data && !users.length" compact icon="users" title="Никого не нашли"
                    :text="isDefault() ? 'Добавьте первого пользователя.' : 'Измените поиск или фильтры.'">
          <button v-if="!isDefault()" class="btn btn-sm" type="button" @click="reset">Сбросить фильтры</button>
        </EmptyState>
      </div>
    </section>

    <UserDrawer v-if="selected" :key="selected.id" :user="selected" :services="services.data.value || []" :departments="departments.data.value || []"
                @close="selected = null" @saved="afterSave" @changed="reload" @deleted="afterDelete" />
    <UserCreateDialog v-if="creating" :services="services.data.value || []" :departments="departments.data.value || []"
                      @close="creating = false" @created="afterCreate" />
    <OneTimePassword v-if="secret" title="Пользователь создан" :password="secret.password" :user="secret.user" @close="secret = null" />
  </div>
</template>

<style scoped>
.search { display: flex; align-items: center; gap: 8px; height: 32px; padding: 0 10px; border: 1px solid var(--border-strong); border-radius: var(--radius); color: var(--muted); min-width: 240px; background: var(--surface); }
.svc-select { max-width: 210px; }
.search input { border: 0; outline: 0; background: transparent; width: 100%; color: var(--text); font-size: var(--fs-sm); }
.search:focus-within { border-color: var(--accent); box-shadow: 0 0 0 3px var(--focus); }
.who { display: flex; align-items: center; gap: 11px; }
.who-text { display: flex; flex-direction: column; min-width: 0; line-height: 1.3; }
.name { font-weight: 580; color: var(--text); white-space: nowrap; }
.self { margin-left: 6px; padding: 0 6px; border-radius: 99px; background: var(--surface-3); font-size: 10.5px; font-weight: 600; color: var(--muted); vertical-align: 1px; }
.login { font-size: var(--fs-xs); color: var(--muted); }
.pos { min-width: 130px; max-width: 190px; font-size: var(--fs-sm); line-height: 1.35; }
.acc-list { display: flex; flex-wrap: wrap; gap: 4px; min-width: 330px; max-width: 420px; }
.acc { display: inline-flex; align-items: center; gap: 5px; height: 22px; padding: 0 8px; border-radius: 6px; border: 1px solid var(--border); background: var(--surface-2); font-size: var(--fs-xs); color: var(--muted); white-space: nowrap; }
.acc b { font-weight: 600; color: var(--text-2); }
.acc .sep { margin: 0 -1px; color: var(--faint); }
.admin-role { display: inline-flex; align-items: center; gap: 8px; font-size: var(--fs-sm); }
.acc.more { color: var(--text-2); font-weight: 600; }
.scoped { color: var(--text-2); }
.status { display: inline-flex; align-items: center; gap: 6px; font-size: var(--fs-sm); color: var(--muted); }
.status i { width: 7px; height: 7px; border-radius: 50%; background: var(--light-gray); }
.status.on { color: var(--text-2); }
.status.on i { background: var(--light-green); }
.tmp { display: flex; align-items: center; gap: 4px; margin-top: 2px; font-size: var(--fs-xs); color: color-mix(in srgb, var(--light-yellow) 75%, var(--text)); }
tr.off td { color: var(--muted); }
tr.off .name { color: var(--text-2); }
.pos-inline { display: none; }
@media (max-width: 1360px) {
  .pos-col { display: none; }
  .pos-inline { display: inline; }
  .name { white-space: normal; }
  .acc-list { min-width: 250px; }
}
.chev-col { width: 36px; padding-left: 0; text-align: right; }
.chev { color: var(--faint); transition: transform var(--t-fast), color var(--t-fast); }
tr:hover .chev { color: var(--text-2); transform: translateX(2px); }
tr.clickable:focus-visible { outline: 2px solid var(--focus); outline-offset: -2px; }
.skeleton-rows { display: flex; flex-direction: column; gap: 10px; padding: 14px; }
.skeleton-rows .skeleton { height: 40px; }
</style>
