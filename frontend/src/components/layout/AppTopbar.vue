<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import AppIcon from '@/components/ui/AppIcon.vue'
import { routeService } from '@/router'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const app = useAppStore()
const auth = useAuthStore()

const crumbs = computed(() => {
  const out = []
  const key = routeService(route)
  const service = key && app.service(key)
  if (service) out.push({ label: service.title, to: service.route_prefix })
  else if (route.path.startsWith('/admin')) out.push({ label: 'Администрирование' })
  if (route.meta.parent) out.push(route.meta.parent)
  if (route.meta.title && route.path !== '/') out.push({ label: route.meta.title })
  return out
})

const themeIcon = computed(() => ({ light: 'sun', dark: 'moon', system: 'monitor' }[app.theme]))
const themeTitle = computed(() => ({ light: 'Светлая тема', dark: 'Тёмная тема', system: 'Как в системе' }[app.theme]))
function cycleTheme() {
  app.setTheme({ system: 'light', light: 'dark', dark: 'system' }[app.theme])
}
// «?» — раздел руководства о странице; руководство администратора — администратору и тем, у кого есть любое
// полномочие администрирования (они открывают страницы администрирования: «Интеграции», «Пользователи»…)
const adminGuide = computed(() => route.meta.guideKind === 'admin')
const showGuide = computed(() => !!route.meta.guide && (!adminGuide.value || auth.canReadAdminGuide))
const guideLink = computed(() => ({ path: adminGuide.value ? '/guide/admin' : '/guide', hash: route.meta.guide ? `#${route.meta.guide}` : '' }))
</script>

<template>
  <header class="topbar">
    <button class="tb-btn mobile-only" type="button" title="Меню" @click="app.mobileNavOpen = !app.mobileNavOpen">
      <AppIcon name="menu" :size="18" />
    </button>
    <button class="tb-btn desktop-only" type="button" :title="app.sidebarCollapsed ? 'Развернуть меню' : 'Свернуть меню'" @click="app.toggleSidebar()">
      <AppIcon :name="app.sidebarCollapsed ? 'chevron-right' : 'chevron-left'" :size="16" />
    </button>
    <nav class="crumbs" aria-label="Путь">
      <router-link v-if="route.path !== '/'" to="/" class="crumb">Обзор</router-link>
      <template v-for="(c, i) in crumbs" :key="i">
        <AppIcon name="chevron-right" :size="13" class="sep" />
        <router-link v-if="c.to && i < crumbs.length - 1" :to="c.to" class="crumb">{{ c.label }}</router-link>
        <span v-else class="crumb current">{{ c.label }}</span>
      </template>
      <span v-if="route.path === '/'" class="crumb current">Обзор</span>
    </nav>
    <div class="spacer" />
    <router-link v-if="showGuide" :to="guideLink" class="tb-btn" title="Справка по этой странице" aria-label="Справка по этой странице" data-testid="page-help">
      <AppIcon name="help" :size="17" />
    </router-link>
    <button class="tb-btn" type="button" :title="`${themeTitle} — переключить`" @click="cycleTheme">
      <AppIcon :name="themeIcon" :size="17" />
    </button>
  </header>
</template>

<style scoped>
.topbar {
  position: sticky; top: 0; z-index: 30; height: var(--topbar-h); display: flex; align-items: center; gap: 6px;
  padding: 0 var(--sp-6) 0 var(--sp-4); background: color-mix(in srgb, var(--bg) 85%, transparent);
  backdrop-filter: saturate(1.4) blur(10px); border-bottom: 1px solid var(--border);
}
.crumbs { display: flex; align-items: center; gap: 6px; min-width: 0; font-size: var(--fs-sm); }
.crumb { color: var(--muted); white-space: nowrap; }
a.crumb:hover { color: var(--text); }
.crumb.current { color: var(--text); font-weight: 560; overflow: hidden; text-overflow: ellipsis; }
.sep { color: var(--faint); }
.tb-btn { width: 34px; height: 34px; display: grid; place-items: center; border: 0; border-radius: 9px; background: transparent; color: var(--muted); cursor: pointer; }
.tb-btn:hover { background: var(--surface-3); color: var(--text); }
.mobile-only { display: none; }
@media (max-width: 960px) {
  .mobile-only { display: grid; }
  .desktop-only { display: none; }
  .topbar { padding: 0 var(--sp-3); }
}
</style>
