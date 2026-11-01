/**
 * HTTP-клиент API: сессионная cookie (её ставит сервер) + CSRF-токен в заголовке для
 * изменяющих запросов. Ошибки приводятся к ApiError с текстом для человека; по умолчанию
 * показываются всплывающим сообщением (silent: true — без него).
 */
import { toastError } from '@/composables/useToast'

const BASE = '/api'
const NETWORK_MESSAGE = 'Нет связи с сервером. Проверьте подключение и повторите'

let csrfToken = ''
let onUnauthorized = () => {}
let onPasswordChangeRequired = () => {}

export function setCsrfToken(token) {
  csrfToken = token || ''
}

function readCsrfCookie() {
  const match = document.cookie.match(/(?:^|;\s*)ds_csrf=([^;]+)/)
  return match ? decodeURIComponent(match[1]) : ''
}

export function configureClient({ unauthorized, passwordChangeRequired } = {}) {
  if (unauthorized) onUnauthorized = unauthorized
  if (passwordChangeRequired) onPasswordChangeRequired = passwordChangeRequired
}

export class ApiError extends Error {
  constructor(message, { status = 0, code = 'error', fields = {} } = {}) {
    super(message)
    this.status = status
    this.code = code
    this.fields = fields
  }
}

function query(params) {
  if (!params) return ''
  const qs = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined || value === '' || (Array.isArray(value) && !value.length)) continue
    qs.set(key, Array.isArray(value) ? value.join(',') : String(value))
  }
  const text = qs.toString()
  return text ? `?${text}` : ''
}

async function parseError(response) {
  let body = {}
  try { body = await response.json() } catch {}
  const message = typeof body.detail === 'string' && body.detail
    ? body.detail
    : response.status >= 500 ? 'Ошибка сервера. Попробуйте позже' : `Ошибка ${response.status}`
  return new ApiError(message, { status: response.status, code: body.code || 'error', fields: body.fields || {} })
}

export async function request(method, path, { body, params, silent = false, raw = false, form } = {}) {
  const headers = { Accept: 'application/json' }
  if (method !== 'GET' && method !== 'HEAD') headers['X-CSRF-Token'] = csrfToken || readCsrfCookie()
  let payload
  if (form) payload = form
  else if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }
  let response
  try {
    response = await fetch(`${BASE}${path}${query(params)}`, { method, headers, body: payload, credentials: 'same-origin' })
  } catch {
    const error = new ApiError(NETWORK_MESSAGE, { code: 'network' })
    if (!silent) toastError(error.message)
    throw error
  }
  if (!response.ok) {
    const error = await parseError(response)
    if (response.status === 401 && error.code === 'not_authenticated') {
      // Тихие запросы (проверка сессии при открытии) сами решают, что делать
      if (!silent) onUnauthorized()
      throw error
    }
    if (error.code === 'password_change_required') {
      onPasswordChangeRequired()
      throw error
    }
    if (!silent) toastError(error.message)
    throw error
  }
  if (raw) return response
  if (response.status === 204) return null
  const type = response.headers.get('content-type') || ''
  return type.includes('application/json') ? response.json() : response.text()
}

function filenameFrom(response, fallback) {
  const header = response.headers.get('content-disposition') || ''
  const star = header.match(/filename\*=UTF-8''([^;]+)/i)
  if (star) return decodeURIComponent(star[1])
  const plain = header.match(/filename="?([^";]+)"?/i)
  return plain ? plain[1] : fallback
}

/** Скачивает файл (PDF, Excel, CSV) с именем, которое предложил сервер. */
export async function download(path, params, fallback = 'file') {
  const response = await request('GET', path, { params, raw: true })
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filenameFrom(response, fallback)
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export function upload(path, file, fields = {}) {
  const form = new FormData()
  form.append('file', file)
  for (const [key, value] of Object.entries(fields)) form.append(key, value)
  return request('POST', path, { form })
}

export const api = {
  get: (path, params, options = {}) => request('GET', path, { params, ...options }),
  post: (path, body, options = {}) => request('POST', path, { body, ...options }),
  put: (path, body, options = {}) => request('PUT', path, { body, ...options }),
  patch: (path, body, options = {}) => request('PATCH', path, { body, ...options }),
  del: (path, options = {}) => request('DELETE', path, options),
  download,
  upload,
}
