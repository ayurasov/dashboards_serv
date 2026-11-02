<script setup>
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppIcon from '@/components/ui/AppIcon.vue'
import { ADMIN_NAV, HELP_NAV, navItemAllowed, SERVICE_NAV } from '@/router/navigation'
import { useAuthStore, LEVEL_LABELS } from '@/stores/auth'
import { useAppStore } from '@/stores/app'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const app = useAppStore()

const OPEN_KEY = 'ds_nav_closed'
const closed = ref(new Set(JSON.parse(localStorage.getItem(OPEN_KEY) || '[]')))

const groups = computed(() => app.dashboards
  .filter((s) => SERVICE_NAV[s.key])
  .map((s) => ({
    key: s.key,
    title: s.title,
    short: s.short_title,
    icon: s.icon,
    level: s.level,
    items: SERVICE_NAV[s.key].filter((i) => navItemAllowed(auth, s.key, i)),
  })))

// «Входящие данные» — с полномочием data.manage или правом применять набор: сервер сообщает это и число
// ожидающих в профиле (/api/auth/me → inbox), отдельных запросов меню не делает
const showInbox = computed(() => auth.inbox)

const helpItems = computed(() => HELP_NAV.filter((i) => !i.admin || auth.isAdmin))
const adminItems = computed(() => ADMIN_NAV.filter((i) => (i.admin ? auth.isAdmin : auth.hasCapability(i.capability))))

function isActive(item) {
  return item.exact ? route.path === item.to : route.path === item.to || route.path.startsWith(`${item.to}/`)
}

function groupActive(group) {
  return group.items.some(isActive)
}

function isOpen(key) {
  return !closed.value.has(key) || app.sidebarCollapsed
}

function toggle(key) {
  const next = new Set(closed.value)
  next.has(key) ? next.delete(key) : next.add(key)
  closed.value = next
  localStorage.setItem(OPEN_KEY, JSON.stringify([...next]))
}

// Под именем — профиль доступа (у индивидуальной настройки — должность)
const subtitle = computed(() => auth.profileName || auth.user?.position || 'Пользователь')
const meTitle = computed(() => [auth.fullName, auth.profileName ? `профиль доступа «${auth.profileName}»` : '', 'открыть профиль']
  .filter(Boolean).join(' — '))

async function logout() {
  await auth.logout()
  router.push({ name: 'login' })
}
</script>

<template>
  <aside class="sidebar" :class="{ collapsed: app.sidebarCollapsed, open: app.mobileNavOpen }" aria-label="Главное меню">
    <div class="brand">
      <img src="/logo.png" width="30" height="30" alt="" class="logo" />
      <div v-if="!app.sidebarCollapsed" class="brand-text">
        <strong>Дашборды</strong>
        <span>АЛМИ Партнер</span>
      </div>
    </div>

    <nav class="nav scroll-thin">
      <router-link to="/" class="item" :class="{ active: route.path === '/' }" title="Обзор">
        <AppIcon name="home" :size="17" /><span class="label">Обзор</span>
      </router-link>
      <router-link to="/org" class="item" :class="{ active: route.path === '/org' }" title="Структура компании">
        <AppIcon name="org" :size="17" /><span class="label">Структура компании</span>
      </router-link>
      <router-link to="/reports" class="item" :class="{ active: route.path === '/reports' || route.path.startsWith('/reports/') }" title="Сквозной отчёт">
        <AppIcon name="traffic" :size="17" /><span class="label">Сквозной отчёт</span>
      </router-link>
      <router-link v-if="showInbox" to="/inbox" class="item" :class="{ active: route.path === '/inbox' }" title="Входящие данные" data-testid="nav-inbox">
        <AppIcon name="inbox" :size="17" /><span class="label">Входящие данные</span>
        <span v-if="auth.inboxPending" class="count num" :title="`Ожидают подтверждения: ${auth.inboxPending}`">{{ auth.inboxPending > 99 ? '99+' : auth.inboxPending }}</span>
      </router-link>

      <div class="section-label">Службы</div>
      <div v-for="g in groups" :key="g.key" class="group" :class="{ current: groupActive(g) }">
        <button class="group-head" type="button" :title="g.title" @click="toggle(g.key)">
          <AppIcon :name="g.icon" :size="17" />
          <span class="label">{{ g.short }}</span>
          <span v-if="g.level && !auth.isAdmin" class="level" :title="`Уровень доступа: ${LEVEL_LABELS[g.level]}`">{{ LEVEL_LABELS[g.level] }}</span>
          <AppIcon v-if="!app.sidebarCollapsed" class="chev" :class="{ open: isOpen(g.key) }" name="chevron-down" :size="14" />
        </button>
        <div v-show="isOpen(g.key)" class="group-items">
          <router-link v-for="item in g.items" :key="item.to" :to="item.to" class="item sub" :class="{ active: isActive(item) }" :title="item.label">
            <AppIcon :name="item.icon" :size="16" /><span class="label">{{ item.label }}</span>
          </router-link>
        </div>
      </div>
      <p v-if="!groups.length && !app.sidebarCollapsed" class="empty">Нет доступных служб. Обратитесь к администратору.</p>

      <template v-if="adminItems.length">
        <div class="section-label">Администрирование</div>
        <router-link v-for="item in adminItems" :key="item.to" :to="item.to" class="item" :class="{ active: isActive(item) }" :title="item.label">
          <AppIcon :name="item.icon" :size="17" /><span class="label">{{ item.label }}</span>
        </router-link>
      </template>

      <div class="section-label">Справка</div>
      <router-link v-for="item in helpItems" :key="item.to" :to="item.to" class="item" :class="{ active: route.path === item.to }" :title="item.label">
        <AppIcon :name="item.icon" :size="17" /><span class="label">{{ item.label }}</span>
      </router-link>
      <button class="item" type="button" title="Что нового" @click="app.openReleaseNotes()">
        <AppIcon name="sparkles" :size="17" /><span class="label">Что нового</span>
        <span v-if="app.hasUnseenRelease" class="dot" />
      </button>
    </nav>

    <div class="footer">
      <router-link to="/profile" class="me" :title="meTitle">
        <span class="avatar">
          <img v-if="auth.user?.avatar" :src="auth.user.avatar" alt="" />
          <template v-else>{{ auth.initials }}</template>
        </span>
        <span v-if="!app.sidebarCollapsed" class="me-text">
          <strong class="ellipsis">{{ auth.fullName }}</strong>
          <span data-testid="sidebar-profile">{{ subtitle }}</span>
        </span>
      </router-link>
      <button class="icon-btn" type="button" title="Выйти" @click="logout"><AppIcon name="logout" :size="16" /></button>
    </div>
  </aside>
</template>

<style scoped>
.sidebar {
  position: fixed; inset: 0 auto 0 0; z-index: 50; width: var(--sb); display: flex; flex-direction: column;
  background: var(--sidebar-bg); border-right: 1px solid var(--border); transition: width var(--t), transform var(--t);
}
.brand { display: flex; align-items: center; gap: 10px; height: var(--topbar-h); padding: 0 18px; border-bottom: 1px solid var(--border); }
.logo { border-radius: 8px; }
.brand-text { display: flex; flex-direction: column; line-height: 1.15; }
.brand-text strong { font-size: 15px; letter-spacing: -0.01em; }
.brand-text span { font-size: var(--fs-xs); color: var(--muted); }
.nav { flex: 1; overflow-y: auto; padding: 10px 10px 16px; display: flex; flex-direction: column; gap: 1px; }
.section-label { margin: 16px 10px 6px; font-size: 10.5px; font-weight: 650; letter-spacing: .08em; text-transform: uppercase; color: var(--faint); }
.item, .group-head {
  position: relative; display: flex; align-items: center; gap: 10px; width: 100%; height: 34px; padding: 0 10px;
  border: 0; border-radius: 8px; background: transparent; color: var(--text-2); font-size: var(--fs-base); font-weight: 520;
  cursor: pointer; text-align: left; transition: background var(--t-fast), color var(--t-fast);
  flex-shrink: 0; /* длинное меню прокручивается, пункты не сжимаются */
}
.item:hover, .group-head:hover { background: var(--surface-3); color: var(--text); }
.item.active { background: var(--brand-soft); color: var(--brand); font-weight: 600; }
.item.sub { height: 31px; padding-left: 36px; font-size: var(--fs-sm); }
.item.sub.active::before { content: ''; position: absolute; left: 18px; top: 9px; bottom: 9px; width: 2px; border-radius: 2px; background: var(--brand); }
.group.current .group-head { color: var(--text); font-weight: 600; }
.group-items { display: flex; flex-direction: column; gap: 1px; margin: 1px 0 4px; }
.label { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.level { font-size: 10px; font-weight: 600; color: var(--muted); background: var(--surface-3); padding: 1px 6px; border-radius: 99px; }
.chev { color: var(--faint); transition: transform var(--t); transform: rotate(-90deg); }
.chev.open { transform: rotate(0); }
.dot { width: 7px; height: 7px; border-radius: 50%; background: var(--brand); }
.count { min-width: 20px; height: 18px; padding: 0 6px; border-radius: 99px; background: var(--surface-3); color: var(--text-2); font-size: 10.5px; font-weight: 650; line-height: 18px; text-align: center; }
.item.active .count { background: var(--brand); color: #fff; }
.empty { margin: 8px 12px; font-size: var(--fs-sm); color: var(--muted); }
.footer { display: flex; align-items: center; gap: 8px; padding: 12px; border-top: 1px solid var(--border); }
.me { flex: 1; min-width: 0; display: flex; align-items: center; gap: 10px; padding: 4px; border-radius: 10px; }
.me:hover { background: var(--surface-3); }
.avatar { width: 34px; height: 34px; flex: 0 0 34px; border-radius: 50%; overflow: hidden; display: grid; place-items: center; background: var(--brand-soft); color: var(--brand); font-weight: 650; font-size: 13px; }
.avatar img { width: 100%; height: 100%; object-fit: cover; }
.me-text { display: flex; flex-direction: column; min-width: 0; line-height: 1.25; }
.me-text strong { font-size: var(--fs-sm); }
.me-text span { font-size: var(--fs-xs); color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.icon-btn { width: 32px; height: 32px; display: grid; place-items: center; border: 0; border-radius: 8px; background: transparent; color: var(--muted); cursor: pointer; }
.icon-btn:hover { background: var(--surface-3); color: var(--text); }

.collapsed .brand { justify-content: center; padding: 0; }
.collapsed .label, .collapsed .section-label, .collapsed .level { display: none; }
.collapsed .item, .collapsed .group-head { justify-content: center; padding: 0; }
.collapsed .item.sub { padding: 0; }
.collapsed .item.sub.active::before { display: none; }
.collapsed .section-label { display: block; height: 1px; margin: 10px 8px; background: var(--border); font-size: 0; }
.collapsed .footer { flex-direction: column; padding: 10px 6px; }
.collapsed .dot { position: absolute; top: 6px; right: 12px; }
.collapsed .count { position: absolute; top: 3px; right: 6px; min-width: 16px; height: 15px; padding: 0 4px; line-height: 15px; font-size: 9.5px; }

@media (max-width: 960px) {
  .sidebar { width: var(--sidebar-w); transform: translateX(-100%); box-shadow: var(--shadow-lg); }
  .sidebar.open { transform: translateX(0); }
  .collapsed .label, .collapsed .section-label, .collapsed .level { display: revert; }
}
</style>
