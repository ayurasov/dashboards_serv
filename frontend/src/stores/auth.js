import { defineStore } from 'pinia'
import { api, setCsrfToken } from '@/api/client'

const LEVEL_RANK = { viewer: 1, editor: 2, manager: 3 }
export const LEVEL_LABELS = { viewer: 'Просмотр', editor: 'Ввод данных', manager: 'Управление' }

/** Текущий пользователь и его права. Сессия живёт в httpOnly-cookie — в браузере хранится только профиль. */
export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: null,
    loaded: false,
  }),
  getters: {
    isLoggedIn: (s) => !!s.user,
    isAdmin: (s) => s.user?.role === 'admin',
    mustChangePassword: (s) => !!s.user?.must_change_password,
    fullName: (s) => s.user?.full_name || s.user?.username || '',
    initials: (s) => (s.user?.full_name || s.user?.username || '?')
      .split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join(''),
  },
  actions: {
    setUser(user) {
      this.user = user
      this.loaded = true
      setCsrfToken(user?.csrf_token || '')
    },
    async load() {
      try {
        this.setUser(await api.get('/auth/me', null, { silent: true }))
      } catch {
        this.setUser(null)
      }
      return this.user
    },
    async login(username, password) {
      this.setUser(await api.post('/auth/login', { username, password }, { silent: true }))
      return this.user
    },
    async logout() {
      try { await api.post('/auth/logout', undefined, { silent: true }) } catch {}
      this.setUser(null)
    },
    async saveProfile(patch) {
      this.setUser(await api.put('/auth/profile', patch))
    },
    async changePassword(currentPassword, newPassword) {
      const result = await api.post('/auth/change-password',
        { current_password: currentPassword, new_password: newPassword }, { silent: true })
      await this.load()
      return result
    },
    level(serviceKey) {
      if (this.isAdmin) return 'manager'
      return this.user?.access?.find((a) => a.service_key === serviceKey)?.level || null
    },
    can(serviceKey, minimum = 'viewer') {
      const level = this.level(serviceKey)
      return !!level && LEVEL_RANK[level] >= LEVEL_RANK[minimum]
    },
    /** Полномочие администрирования (org.manage, users.manage); администратору доступны все. */
    hasCapability(capability) {
      return this.isAdmin || !!this.user?.capabilities?.includes(capability)
    },
    departmentScoped(serviceKey = 'hr') {
      return !this.isAdmin && !!this.user?.access?.find((a) => a.service_key === serviceKey && a.department_scope)
    },
  },
})
