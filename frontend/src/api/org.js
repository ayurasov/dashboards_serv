/**
 * API структуры компании (ADR-0007): оргсхема и карточка сотрудника, подразделения и руководители,
 * настройки структуры, история, перенос структуры и сотрудников, загрузка списком, синхронизация с AD.
 */
import { ApiError, api, download, request } from './client'
import { toastError } from '@/composables/useToast'

function readCsrfCookie() {
  const match = document.cookie.match(/(?:^|;\s*)ds_csrf=([^;]+)/)
  return match ? decodeURIComponent(match[1]) : ''
}

/**
 * Проверка или применение загрузки. Ответ 409 import_has_errors содержит план — он возвращается
 * как результат ({ …план, rejected: true, detail }), а не как ошибка: его показывают на странице.
 * Остальные ошибки — как в общем клиенте (сообщение и ApiError).
 */
export async function postPlan(path, { body, form } = {}) {
  const headers = { Accept: 'application/json', 'X-CSRF-Token': readCsrfCookie() }
  if (!form) headers['Content-Type'] = 'application/json'
  let response
  try {
    response = await fetch(`/api${path}`, { method: 'POST', headers, body: form || JSON.stringify(body), credentials: 'same-origin' })
  } catch {
    const message = 'Нет связи с сервером. Проверьте подключение и повторите'
    toastError(message)
    throw new ApiError(message, { code: 'network' })
  }
  let payload = {}
  try { payload = await response.json() } catch {}
  if (response.ok) return payload
  if (response.status === 409 && payload?.code === 'import_has_errors' && payload.summary) {
    return { ...payload, applied: false, rejected: true }
  }
  if (response.status === 401) {
    // Сессия закончилась — общий клиент сам отправит на страницу входа
    await request('GET', '/auth/me').catch(() => {})
  }
  const message = typeof payload?.detail === 'string' && payload.detail
    ? payload.detail
    : response.status >= 500 ? 'Ошибка сервера. Попробуйте позже' : `Ошибка ${response.status}`
  throw new ApiError(message, { status: response.status, code: payload?.code || 'error', fields: payload?.fields || {} })
}

export function uploadForm(file, fields) {
  const form = new FormData()
  form.append('file', file)
  for (const [key, value] of Object.entries(fields)) {
    if (value !== undefined && value !== null) form.append(key, typeof value === 'object' ? JSON.stringify(value) : String(value))
  }
  return form
}

const today = () => new Date().toISOString().slice(0, 10)

export const orgApi = {
  // оргсхема
  tree: () => api.get('/org/tree'),
  person: (id) => api.get(`/org/people/${id}`, null, { silent: true }),
  avatarUrl: (id) => `/api/org/people/${id}/avatar`,
  updatePerson: (id, body) => api.patch(`/org/people/${id}`, body, { silent: true }),
  history: (params) => api.get('/org/history', params, { silent: true }),

  // настройки структуры
  settings: () => api.get('/org/settings'),
  saveSettings: (body) => api.put('/org/settings', body, { silent: true }),

  // подразделения
  departments: () => api.get('/departments'),
  createDepartment: (body) => api.post('/departments', body, { silent: true }),
  updateDepartment: (id, body) => api.patch(`/departments/${id}`, body, { silent: true }),
  deleteDepartment: (id) => api.del(`/departments/${id}`),
  setHeads: (id, body) => api.put(`/departments/${id}/heads`, body, { silent: true }),

  // перенос структуры
  exportStructure: () => download('/org/export', null, `dashboards-structure-${today()}.json`),
  importStructure: ({ bundle, applySettings = true, apply = false }) =>
    postPlan('/org/import/structure', { body: { bundle, apply_settings: applySettings, apply } }),

  // сотрудники
  exportEmployees: ({ format = 'xlsx', inactive = true } = {}) =>
    download('/org/employees/export', { format, inactive: inactive ? 1 : 0 }, `Сотрудники.${format}`),
  importEmployees: ({ file, apply = false, newUsers = 'no_access', decisions = {} }) =>
    postPlan('/org/employees/import', { form: uploadForm(file, { apply, new_users: newUsers, decisions }) }),

  // быстрая загрузка списком: файл (CSV, Excel) или текст CSV
  importList: ({ file, content, createMissing = false, apply = false }) => (file
    ? postPlan('/org/import/list', { form: uploadForm(file, { apply, create_missing: createMissing }) })
    : postPlan('/org/import/list', { body: { content, create_missing: createMissing, apply } })),

  // Active Directory
  adStatus: () => api.get('/org/sync/ad', null, { silent: true }),
  adSync: ({ createMissing = false, deactivateMissing = false, apply = false }) =>
    postPlan('/org/sync/ad', { body: { create_missing: createMissing, deactivate_missing: deactivateMissing, apply } }),
}
