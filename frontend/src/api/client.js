import { toastError } from '../composables/useToast.js'

const BASE = '/api'

const NETWORK_MESSAGE = 'Нет соединения с сервером'

// Statuses where the server's own `detail` is too terse to show a user.
const STATUS_MESSAGES = {
  401: 'Необходима авторизация',
  403: 'Недостаточно прав для выполнения действия',
  404: 'Данные не найдены',
  500: 'Ошибка сервера. Попробуйте позже',
}

function getToken() {
  return localStorage.getItem('hr_token')
}

async function errorMessage(res, raw = false) {
  let detail = ''
  try { detail = (await res.json())?.detail || '' } catch {}
  if (typeof detail !== 'string') detail = ''
  if (res.status >= 500) return STATUS_MESSAGES[500]
  if (raw && detail) return detail
  return STATUS_MESSAGES[res.status] || detail || `Ошибка ${res.status}`
}

/**
 * `raw` opts out of the global toast and keeps the server's own message — used by
 * the login form, where "Неверный логин или пароль" matters more than the generic
 * 401 text and the error is rendered inline anyway.
 */
async function request(method, path, body = null, { raw = false } = {}) {
  const headers = { 'Content-Type': 'application/json' }
  const token = getToken()
  if (token) headers['Authorization'] = `Bearer ${token}`
  const opts = { method, headers }
  if (body !== null) opts.body = JSON.stringify(body)

  let res
  try {
    res = await fetch(`${BASE}${path}`, opts)
  } catch {
    if (!raw) toastError(NETWORK_MESSAGE)
    throw new Error(NETWORK_MESSAGE)
  }

  if (res.status === 401 && !raw) {
    localStorage.removeItem('hr_token')
    localStorage.removeItem('hr_user')
    toastError(STATUS_MESSAGES[401])
    if (location.pathname !== '/login') location.href = '/login'
    throw new Error(STATUS_MESSAGES[401])
  }
  if (!res.ok) {
    let msg
    try { msg = await errorMessage(res, raw) } catch { msg = `Ошибка ${res.status}` }
    if (!raw) toastError(msg)
    throw new Error(msg)
  }
  const ct = res.headers.get('content-type') || ''
  if (ct.includes('application/json')) return res.json()
  if (ct.includes('application/pdf')) return res.blob()
  return res.text()
}

export const api = {
  get: (p) => request('GET', p),
  post: (p, b) => request('POST', p, b),
  put: (p, b) => request('PUT', p, b),
  del: (p) => request('DELETE', p),
  login: (username, password) => request('POST', '/auth/login', { username, password }, { raw: true }),
  /** Fetches any /api/pdf/* report as a Blob. `params` skips empty values. */
  pdfBlob: async (report, params = {}) => {
    const qs = new URLSearchParams()
    for (const [k, v] of Object.entries(params)) {
      if (v !== null && v !== undefined && v !== '') qs.set(k, v)
    }
    const query = qs.toString()
    let res
    try {
      res = await fetch(`${BASE}/pdf/${report}${query ? `?${query}` : ''}`, {
        headers: { 'Authorization': `Bearer ${getToken()}` }
      })
    } catch {
      toastError(NETWORK_MESSAGE)
      throw new Error(NETWORK_MESSAGE)
    }
    if (!res.ok) {
      const msg = await errorMessage(res)
      toastError(msg)
      throw new Error(msg)
    }
    return res.blob()
  },
  downloadPdf: (period = '') => api.pdfBlob('dashboard', { period }),
}
