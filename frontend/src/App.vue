<template>
  <div v-if="auth.isLoggedIn && !isLoginPage" class="app-layout">
    <button class="ham" @click="sidebarOpen = !sidebarOpen">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18M3 12h18M3 18h18"/></svg>
    </button>
    <aside class="sidebar" :class="{ open: sidebarOpen, collapsed }">
      <div class="slogo">
        <img src="/assets/logo-sidebar.png" width="34" height="34" alt="АЛМИ Партнер">
        <div v-if="!collapsed" class="slogo-txt">
          <div class="logo-text">АЛМИ Партнер</div>
          <div class="logo-sub">{{ activeModuleTitle }}</div>
        </div>
        <button class="scollapse" @click="toggleCollapse" :title="collapsed ? 'Развернуть меню' : 'Свернуть меню'">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
            <path :d="collapsed ? 'M9 6l6 6-6 6' : 'M15 6l-6 6 6 6'"/>
          </svg>
        </button>
      </div>
      <nav class="snav">
        <div v-for="group in navGroups" :key="group.key" class="ngroup">
          <button v-if="!collapsed" class="ngroup-hd" @click="toggleGroup(group.key)">
            <span v-if="group.icon" class="ngroup-ic">{{ group.icon }}</span>
            <span class="ngroup-title">{{ group.title }}</span>
            <span v-if="group.badge" class="ngroup-badge">{{ group.badge }}</span>
            <svg class="ngroup-chev" :class="{ open: isGroupOpen(group.key) }" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M6 9l6 6 6-6"/></svg>
          </button>
          <template v-if="collapsed || isGroupOpen(group.key)">
            <router-link
              v-for="item in group.items"
              :key="item.to"
              :to="item.to"
              class="ni"
              :class="{ active: isActive(item.to) }"
              :title="item.label"
              @click="sidebarOpen=false"
            >
              <span class="ni-ic" v-html="item.icon"></span>
              <span v-if="!collapsed" class="ni-lbl">{{ item.label }}</span>
            </router-link>
          </template>
        </div>
      </nav>
      <div class="sfooter">
        <router-link to="/profile" class="sprofile" :title="auth.fullName + ' — профиль'" @click="sidebarOpen=false">
          <span class="savatar">
            <img v-if="auth.avatar" :src="auth.avatar" alt="">
            <template v-else>{{ initials }}</template>
          </span>
          <span v-if="!collapsed" class="sprofile-info">
            <span class="sprofile-name">{{ auth.fullName }}</span>
            <span class="tag" :class="'tag-'+auth.role">{{ roleLabel }}</span>
          </span>
        </router-link>
        <template v-if="!collapsed">
          <button class="btn btn-g" style="width:100%;font-size:.75rem;padding:4px 8px" @click="logout">Выйти</button>
          <div style="margin-top:8px;font-size:10px">© Alexander Yurasov</div>
        </template>
        <button v-else class="btn btn-g" style="width:100%;justify-content:center;padding:4px" title="Выйти" @click="logout">⏏</button>
      </div>
    </aside>
    <main class="main">
      <div class="topbar">
        <div class="topbar-row">
          <div class="topbar-head">
            <span class="topbar-title">Дашборды</span>
            <span class="topbar-sub">{{ activeModuleTitle }}<template v-if="pageTitle"> · {{ pageTitle }}</template></span>
          </div>
          <div class="topbar-actions">
            <button class="btn btn-g" @click="exportPdf" :disabled="pdfLoading">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>
              {{ pdfLoading ? '...' : 'PDF' }}
            </button>
            <button class="tt" @click="toggleTheme" title="Тема">{{ themeIcon }}</button>
          </div>
        </div>
        <slot name="topbar-extra"></slot>
      </div>
      <router-view />
    </main>

    <!-- Change password modal -->
    <div v-if="showChangePwd" class="modal-overlay" @click.self="showChangePwd=false">
      <div class="modal modal-sm">
        <div class="mh">
          <span class="mt">Смена пароля</span>
          <button class="mc" @click="showChangePwd=false">✕</button>
        </div>
        <form @submit.prevent="doChangePwd">
          <div class="fgi" style="margin-bottom:12px">
            <label class="fl">Текущий пароль</label>
            <input class="fi" type="password" v-model="pwdForm.old" required style="width:100%">
          </div>
          <div class="fgi" style="margin-bottom:12px">
            <label class="fl">Новый пароль (мин. 4 символа)</label>
            <input class="fi" type="password" v-model="pwdForm.new" required minlength="4" style="width:100%">
          </div>
          <div class="err-msg">{{ pwdErr }}</div>
          <div class="fac"><span></span><button type="submit" class="btn btn-p">Изменить</button></div>
        </form>
      </div>
    </div>
  </div>
  <router-view v-else />

  <div class="toasts">
    <div
      v-for="t in toasts"
      :key="t.id"
      class="toast-item"
      :class="'toast-'+t.kind"
      @click="dismissToast(t.id)"
    >{{ t.message }}</div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from './stores/auth.js'
import { usePaletteStore } from './stores/palette.js'
import { api } from './api/client.js'
import { toasts, dismissToast, toastOk } from './composables/useToast.js'
import { currentPdfParams } from './composables/usePdfExport.js'

const auth = useAuthStore()
const palette = usePaletteStore()
const router = useRouter()
const route = useRoute()
const modules = ref([])
const sidebarOpen = ref(false)
const showChangePwd = ref(false)
const pwdForm = ref({ old: '', new: '' })
const pwdErr = ref('')
const pdfLoading = ref(false)
const theme = ref(localStorage.getItem('hr_theme') || 'light')
document.documentElement.setAttribute('data-theme', theme.value)

// ---------- Sidebar collapse (manual, independent of the responsive breakpoint) ----------
const COLLAPSE_KEY = 'hr_sidebar_collapsed'
const GROUPS_KEY = 'hr_nav_groups'
const collapsed = ref(localStorage.getItem(COLLAPSE_KEY) === '1')

function applyCollapsed() {
  document.documentElement.setAttribute('data-sidebar', collapsed.value ? 'collapsed' : 'full')
}
applyCollapsed()

function toggleCollapse() {
  collapsed.value = !collapsed.value
  localStorage.setItem(COLLAPSE_KEY, collapsed.value ? '1' : '0')
  applyCollapsed()
}

function readGroupState() {
  try { return JSON.parse(localStorage.getItem(GROUPS_KEY)) || {} } catch { return {} }
}
const groupState = ref(readGroupState())

function isGroupOpen(key) {
  return groupState.value[key] !== false
}

function toggleGroup(key) {
  groupState.value = { ...groupState.value, [key]: !isGroupOpen(key) }
  localStorage.setItem(GROUPS_KEY, JSON.stringify(groupState.value))
}

const isLoginPage = computed(() => route.name === 'login')
const roleLabel = computed(() => ({
  admin: 'Администратор', hr_head: 'Начальник службы персонала', viewer: 'Просмотр', department_viewer: 'Отдел'
}[auth.role] || auth.role))
const initials = computed(() => (auth.fullName || auth.username || '?')
  .split(/\s+/).filter(Boolean).slice(0, 2).map(w => w[0].toUpperCase()).join(''))
const pageTitle = computed(() => route.meta?.title || ({
  dashboard: 'Дашборд', registry: 'Реестр сотрудников', summary: 'Сводка по периодам',
  'custom-dashboards': 'Кастомные дашборды', audit: 'История изменений',
  users: 'Управление пользователями', 'traffic-light': 'Настройка светофора', login: 'Вход',
  'product-dashboard': 'Технологические партнёрства', 'product-registry': 'Реестр партнёрств',
  'product-timeline': 'Хронология партнёрств', 'product-summary': 'Сводка партнёрств',
  palette: 'Цветовая палитра', profile: 'Профиль',
  'data-entry': 'Данные месяца', benchmarks: 'Бенчмарки и цели',
  // ---------- Technical Support ----------
  'tp-dashboard':     'Техническая поддержка',
  'tp-registry':      'Реестр данных ТП',
  'tp-summary':       'Сводка ТП',
  'tp-traffic-light': 'Светофор ТП',
}[route.name] || ''))
const themeIcon = computed(() => theme.value === 'dark' ? '☀' : '🌙')

const ic = {
  grid: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="15" height="15"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>',
  list: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="15" height="15"><path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"/></svg>',
  chart: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="15" height="15"><path d="M3 3v18h18M7 14l4-4 4 4 5-6"/></svg>',
  users: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="15" height="15"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2M9 7a4 4 0 100 8 4 4 0 000-8zM23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75"/></svg>',
  light: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="15" height="15"><circle cx="12" cy="6" r="3"/><circle cx="12" cy="14" r="3"/><circle cx="12" cy="20" r="2"/></svg>',
  clock: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="15" height="15"><path d="M12 8v4l3 3M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>',
  handshake: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="15" height="15"><path d="M8 12l3 3 5-5M3 8l4-4 5 3 5-3 4 4v8l-4 4-5-3-5 3-4-4z"/></svg>',
  palette: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="15" height="15"><circle cx="13.5" cy="6.5" r="1.5"/><circle cx="17.5" cy="10.5" r="1.5"/><circle cx="8.5" cy="7.5" r="1.5"/><circle cx="6.5" cy="12.5" r="1.5"/><path d="M12 2a10 10 0 000 20c1.1 0 2-.9 2-2 0-.5-.2-1-.6-1.4-.3-.4-.5-.8-.5-1.3 0-1.1.9-2 2-2h2.4A4.7 4.7 0 0022 12 10 10 0 0012 2z"/></svg>',
  edit: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="15" height="15"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.1 2.1 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>',
  target: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="15" height="15"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/></svg>',
  // ---------- Technical Support ----------
  headset: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="15" height="15"><path d="M3 18v-6a9 9 0 0118 0v6"/><path d="M21 19a2 2 0 01-2 2h-1a2 2 0 01-2-2v-3a2 2 0 012-2h3zM3 19a2 2 0 002 2h1a2 2 0 002-2v-3a2 2 0 00-2-2H3z"/></svg>',
}

// Nav items per module key. `need` gates an item behind a role capability.
const MODULE_NAV = {
  hr: [
    { to: '/', label: 'Дашборд', icon: ic.grid },
    { to: '/registry', label: 'Реестр', icon: ic.list },
    { to: '/hr/data-entry', label: 'Данные месяца', icon: ic.edit, need: 'metrics' },
    { to: '/summary', label: 'Сводка', icon: ic.chart },
    { to: '/hr/benchmarks', label: 'Бенчмарки', icon: ic.target },
    { to: '/custom-dashboards', label: 'Кастомные дашборды', icon: ic.grid },
    { to: '/traffic-light', label: 'Светофор', icon: ic.light, need: 'admin' },
  ],
  project_product: [
    { to: '/product', label: 'Партнёрства', icon: ic.handshake },
    { to: '/product/registry', label: 'Реестр партнёрств', icon: ic.list },
    { to: '/product/summary', label: 'Сводка партнёрств', icon: ic.chart },
    { to: '/product/timeline', label: 'Хронология', icon: ic.clock },
    { to: '/product/traffic-light', label: 'Светофор', icon: ic.light },
  ],
  // ---------- Technical Support ----------
  tech: [
    { to: '/tp',               label: 'Дашборд ТП',    icon: ic.headset },
    { to: '/tp/registry',      label: 'Реестр данных', icon: ic.list },
    { to: '/tp/summary',       label: 'Сводка',        icon: ic.chart },
    { to: '/tp/traffic-light', label: 'Светофор',      icon: ic.light, need: 'admin' },
  ],
}

// Admin-only group; user management and the audit trail live here, not in the modules.
const ADMIN_NAV = [
  { to: '/palette', label: 'Палитра', icon: ic.palette },
  { to: '/users', label: 'Пользователи', icon: ic.users },
  { to: '/audit', label: 'История', icon: ic.clock },
]

const FALLBACK_MODULES = [
  { key: 'hr', title: 'Служба персонала', subtitle: 'Персонал', icon: '📊', route_prefix: '/', sort_order: 0 },
  { key: 'project_product', title: 'Проектный и продуктовый офис', subtitle: 'Технологические партнёрства', icon: '🤝', route_prefix: '/product', sort_order: 1 },
  // ---------- Technical Support ----------
  { key: 'tech', title: 'Техническая поддержка', subtitle: 'Техподдержка', icon: '🎧', route_prefix: '/tp', sort_order: 2 },
]

const ACCESS_LABELS = {
  read: 'чтение', edit: 'правка', edit_metrics: 'метрики', admin: 'админ',
}

function allowed(item, serviceKey) {
  if (item.need === 'admin') return auth.isAdmin
  if (item.need === 'edit') return auth.canEdit
  if (item.need === 'metrics') return auth.canEdit || auth.canEditMetrics(serviceKey)
  return true
}

const navGroups = computed(() => {
  const groups = modules.value
    .map(m => ({
      key: m.key,
      title: m.title,
      icon: m.icon,
      badge: ACCESS_LABELS[auth.accessLevel(m.key)] || '',
      items: (MODULE_NAV[m.key] || []).filter(i => allowed(i, m.key)),
    }))
    .filter(g => g.items.length)
  if (auth.isAdmin) {
    groups.push({ key: '__admin', title: 'Настройки', icon: '⚙', items: ADMIN_NAV })
  }
  return groups
})

/** Longest matching module prefix wins, so /product beats the '/' service prefix. */
const activeModule = computed(() => {
  const path = route.path
  let best = null
  for (const m of modules.value) {
    const p = m.route_prefix || '/'
    const hit = p === '/' ? true : path === p || path.startsWith(p + '/')
    if (hit && (!best || p.length > (best.route_prefix || '/').length)) best = m
  }
  return best
})

const activeModuleTitle = computed(() => activeModule.value?.title || 'Служба персонала')

function isActive(to) {
  return to === '/' ? route.path === '/' : route.path === to
}

function toggleTheme() {
  theme.value = theme.value === 'dark' ? 'light' : 'dark'
  document.documentElement.setAttribute('data-theme', theme.value)
  localStorage.setItem('hr_theme', theme.value)
  palette.apply()
}

async function loadShell() {
  if (!auth.isLoggedIn) return
  try {
    await auth.loadAccess(true)
  } catch {
    // Badges degrade to none; the API stays the real gate.
  }
  try {
    modules.value = await api.get('/modules') || []
  } catch {
    modules.value = FALLBACK_MODULES
  }
  await palette.load()
  await auth.loadMe()
}

onMounted(loadShell)
watch(() => auth.isLoggedIn, (v) => { if (v) loadShell() })

async function doChangePwd() {
  pwdErr.value = ''
  try {
    await auth.changePassword(pwdForm.value.old, pwdForm.value.new)
    showChangePwd.value = false
    pwdForm.value = { old: '', new: '' }
    toastOk('Пароль изменён')
  } catch (e) {
    pwdErr.value = e.message
  }
}

function logout() {
  auth.logout()
  router.push('/login')
}

// Which backend report the topbar button pulls, per route.
const PDF_REPORTS = {
  registry: ['registry', 'hr_registry'],
  summary: ['summary', 'hr_summary'],
  benchmarks: ['benchmarks', 'hr_benchmarks'],
  'product-dashboard': ['partnerships', 'partnerships_dashboard'],
  'product-registry': ['partnerships', 'partnerships_registry'],
  'product-summary': ['partnerships-summary', 'partnerships_summary'],
  'product-timeline': ['partnerships', 'partnerships_timeline'],
  // ---------- Technical Support ----------
  'tp-dashboard':     ['tp', 'tp_dashboard'],
  'tp-registry':      ['tp', 'tp_registry'],
  'tp-summary':       ['tp-summary', 'tp_summary'],
}

async function exportPdf() {
  const [report, prefix] = PDF_REPORTS[route.name] || ['dashboard', 'hr_dashboard']
  pdfLoading.value = true
  try {
    const blob = await api.pdfBlob(report, currentPdfParams())
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${prefix}_${new Date().toISOString().slice(0,10)}.pdf`
    a.click()
    URL.revokeObjectURL(url)
    toastOk('PDF выгружен')
  } catch {
    // The API layer already surfaced the reason as a toast.
  } finally {
    pdfLoading.value = false
  }
}

// force password change
watch(() => auth.mustChangePassword && auth.isLoggedIn, (v) => {
  if (v) showChangePwd.value = true
}, { immediate: true })
</script>
