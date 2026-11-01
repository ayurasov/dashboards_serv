import { defineStore } from 'pinia'
import { api } from '@/api/client'

const THEME_KEY = 'ds_theme'
const SIDEBAR_KEY = 'ds_sidebar_collapsed'
const SEEN_VERSION_KEY = 'ds_seen_version'

function systemDark() {
  return typeof matchMedia === 'function' && matchMedia('(prefers-color-scheme: dark)').matches
}

/** Оформление и общие данные оболочки: тема, боковое меню, службы, версия. */
export const useAppStore = defineStore('app', {
  state: () => ({
    theme: localStorage.getItem(THEME_KEY) || 'system',
    sidebarCollapsed: localStorage.getItem(SIDEBAR_KEY) === '1',
    mobileNavOpen: false,
    services: [],
    version: '',
    seenVersion: localStorage.getItem(SEEN_VERSION_KEY) || '',
    releaseNotesOpen: false,
  }),
  getters: {
    resolvedTheme: (s) => (s.theme === 'system' ? (systemDark() ? 'dark' : 'light') : s.theme),
    dashboards: (s) => s.services.filter((x) => x.has_dashboard),
    hasUnseenRelease: (s) => !!s.version && s.seenVersion !== s.version,
  },
  actions: {
    applyTheme() {
      document.documentElement.dataset.theme = this.resolvedTheme
    },
    setTheme(theme) {
      this.theme = theme
      localStorage.setItem(THEME_KEY, theme)
      this.applyTheme()
    },
    toggleSidebar() {
      this.sidebarCollapsed = !this.sidebarCollapsed
      localStorage.setItem(SIDEBAR_KEY, this.sidebarCollapsed ? '1' : '0')
    },
    async loadServices() {
      try {
        this.services = await api.get('/services', null, { silent: true })
      } catch {
        this.services = []
      }
    },
    async loadVersion() {
      try {
        this.version = (await api.get('/version', null, { silent: true })).version
      } catch {}
    },
    openReleaseNotes() {
      this.releaseNotesOpen = true
      this.seenVersion = this.version
      localStorage.setItem(SEEN_VERSION_KEY, this.version)
    },
    service(key) {
      return this.services.find((s) => s.key === key)
    },
  },
})
