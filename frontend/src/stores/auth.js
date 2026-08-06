import { defineStore } from 'pinia'
import { api } from '../api/client.js'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem('hr_token') || '',
    role: localStorage.getItem('hr_role') || '',
    username: localStorage.getItem('hr_username') || '',
    fullName: localStorage.getItem('hr_fullname') || '',
    mustChangePassword: localStorage.getItem('hr_mcp') === '1',
    // Loaded from /auth/me; avatars are too large to keep in localStorage.
    email: '',
    phone: '',
    avatar: '',
    departments: [],
    serviceAccess: [],
    accessLoaded: false,
  }),
  getters: {
    isLoggedIn: (s) => !!s.token,
    isAdmin: (s) => s.role === 'admin',
    canEdit: (s) => s.role === 'admin' || s.role === 'hr_head',
    accessMap: (s) => {
      const map = {}
      for (const row of s.serviceAccess) map[row.service_key] = row.access_level
      return map
    },
  },
  actions: {
    async login(username, password) {
      const data = await api.login(username, password)
      this.token = data.access_token
      this.role = data.role
      this.username = data.username
      this.fullName = data.full_name
      this.mustChangePassword = data.must_change_password
      localStorage.setItem('hr_token', data.access_token)
      localStorage.setItem('hr_role', data.role)
      localStorage.setItem('hr_username', data.username)
      localStorage.setItem('hr_fullname', data.full_name)
      localStorage.setItem('hr_mcp', data.must_change_password ? '1' : '0')
    },
    applyProfile(user) {
      this.username = user.username
      this.fullName = user.full_name
      this.role = user.role
      this.email = user.email || ''
      this.phone = user.phone || ''
      this.avatar = user.avatar || ''
      this.departments = user.departments || []
      if (user.service_access) this.setAccess(user.service_access)
      localStorage.setItem('hr_fullname', user.full_name)
      localStorage.setItem('hr_role', user.role)
    },
    setAccess(list) {
      this.serviceAccess = list || []
      this.accessLoaded = true
    },
    async loadAccess(force = false) {
      if (!this.token) return []
      if (this.accessLoaded && !force) return this.serviceAccess
      this.setAccess(await api.get('/auth/my-access'))
      return this.serviceAccess
    },
    accessLevel(key) {
      return this.isAdmin ? 'admin' : (this.accessMap[key] || '')
    },
    canViewService(key) {
      return !!this.accessLevel(key)
    },
    canEditService(key) {
      return ['edit', 'admin'].includes(this.accessLevel(key))
    },
    canEditMetrics(key) {
      return ['edit_metrics', 'admin'].includes(this.accessLevel(key))
    },
    canAdminService(key) {
      return this.accessLevel(key) === 'admin'
    },
    async loadMe() {
      if (!this.token) return null
      const user = await api.get('/auth/me')
      this.applyProfile(user)
      return user
    },
    async saveProfile(patch) {
      const user = await api.put('/auth/profile', patch)
      this.applyProfile(user)
      return user
    },
    logout() {
      this.token = ''
      this.role = ''
      this.username = ''
      this.fullName = ''
      this.email = ''
      this.phone = ''
      this.avatar = ''
      this.departments = []
      this.serviceAccess = []
      this.accessLoaded = false
      localStorage.removeItem('hr_token')
      localStorage.removeItem('hr_role')
      localStorage.removeItem('hr_username')
      localStorage.removeItem('hr_fullname')
      localStorage.removeItem('hr_mcp')
    },
    async changePassword(oldPwd, newPwd) {
      await api.post('/auth/change-password', { old_password: oldPwd, new_password: newPwd })
      this.mustChangePassword = false
      localStorage.setItem('hr_mcp', '0')
    },
  },
})
