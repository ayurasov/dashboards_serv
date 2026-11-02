import { defineStore } from 'pinia'
import { api, setCsrfToken } from '@/api/client'
import { hasLevel, LEVEL_LABELS, scopeFor, userAccess } from '@/domain/access'

export { LEVEL_LABELS }

/**
 * Текущий пользователь и его права. Сессия живёт в httpOnly-cookie — в браузере хранится только профиль.
 * Права — действующий доступ из /api/auth/me (effective_access, ADR-0009): уровни служб, область
 * структуры, классы данных, глубина, исходные записи, выгрузка. Интерфейс по ним скрывает разделы
 * и кнопки; сервер всё равно проверяет каждый запрос сам.
 *
 * «Входящие данные» — тоже из /api/auth/me: inbox.available (data.manage или право применять набор)
 * и inbox.pending — сколько ожидающих элементов пользователь может применить (счётчик в меню).
 */
let inboxRefresh = null

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
    /** Действующий доступ (без сервера 0.2.0 — из строк доступа 0.1.0). */
    access: (s) => userAccess(s.user),
    isDomainUser: (s) => s.user?.auth_source === 'ldap',
    profileName() {
      if (this.isAdmin) return 'Администратор'
      return this.access?.profile_name || ''
    },
    canRecords() {
      return this.isAdmin || !!this.access?.can_view_records
    },
    canExport() {
      return this.isAdmin || !!this.access?.can_export
    },
    /** Общая область структуры: company · branch · unit. */
    scope() {
      return this.isAdmin ? 'company' : this.access?.org_scope || 'company'
    },
    /** Глубина детализации; null — без ограничения. */
    drillDepth() {
      return this.isAdmin ? null : this.access?.drill_depth ?? null
    },
    dataClasses() {
      return this.access?.data_classes || ['operational']
    },
    /** «Входящие данные» доступны (с сервера: data.manage или право применять хотя бы один набор). */
    inbox() {
      return !!this.user?.inbox?.available || this.hasCapability('data.manage')
    },
    /** Ожидающие элементы, которые пользователь может применить или отклонить. */
    inboxPending: (s) => Number(s.user?.inbox?.pending) || 0,
  },
  actions: {
    setUser(user) {
      if (user?.id !== this.user?.id) inboxRefresh = null
      this.user = user
      this.loaded = true
      setCsrfToken(user?.csrf_token || '')
    },
    /** Доступ к «Входящим данным» — уже в профиле (/api/auth/me): отдельных запросов нет. */
    async loadInboxAccess() {
      if (!this.user || this.mustChangePassword) return false
      return this.inbox
    },
    /**
     * Обновить счётчик «ожидают» (и доступ) после применения, отклонения или загрузки — тем же лёгким
     * /api/auth/me. Одновременные вызовы сливаются в один запрос.
     */
    async refreshInbox() {
      if (!this.user) return this.inboxPending
      if (!inboxRefresh) {
        const id = this.user.id
        inboxRefresh = api.get('/auth/me', null, { silent: true })
          .then((me) => { if (me?.id === id && this.user?.id === id) this.user = { ...this.user, inbox: me.inbox } })
          .catch(() => {})
          .finally(() => { inboxRefresh = null })
      }
      await inboxRefresh
      return this.inboxPending
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
    /** Уровень доступа к службе или null. */
    level(serviceKey) {
      if (this.isAdmin) return 'manager'
      return this.access?.services?.[serviceKey] || null
    },
    can(serviceKey, minimum = 'viewer') {
      return hasLevel(this.level(serviceKey), minimum)
    },
    /** Класс данных: operational — всегда, personal и financial — по праву. */
    allows(dataClass) {
      if (this.isAdmin || dataClass === 'operational' || !dataClass) return true
      return this.dataClasses.includes(dataClass)
    },
    /** Область для службы: своя у службы или общая. */
    scopeFor(serviceKey) {
      return this.isAdmin ? 'company' : scopeFor(this.access, serviceKey)
    },
    /** Полномочие администрирования (org.manage, users.manage); администратору доступны все. */
    hasCapability(capability) {
      return this.isAdmin || !!this.user?.capabilities?.includes(capability)
    },
    /** Область уже компании: данные службы ограничены подразделениями пользователя. */
    departmentScoped(serviceKey = 'hr') {
      return !this.isAdmin && this.scopeFor(serviceKey) !== 'company'
    },
    /**
     * Почему недоступна страница: '' — доступна; service — нет уровня службы; records — нет права на
     * исходные записи; personal / financial — нет класса данных; export — нет выгрузки.
     */
    denial({ service = null, level = 'viewer', records = false, dataClass = null, exportable = false } = {}) {
      if (service && !this.can(service, level)) return 'service'
      if (records && !this.canRecords) return 'records'
      if (dataClass && !this.allows(dataClass)) return dataClass
      if (exportable && !this.canExport) return 'export'
      return ''
    },
  },
})
