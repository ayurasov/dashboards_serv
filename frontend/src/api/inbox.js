/**
 * API входящих данных (ADR-0011): элементы, план и применение, загрузка файла, наборы, правила
 * «применять сразу», папка «Входящие». Пути совпадают с backend/app/api/routers/inbox.py.
 */
import { api, download, request } from './client'

const PLAN_ERRORS = ['import_has_errors']
const UPLOAD_ERRORS = ['dataset_forbidden', 'payload_too_large', 'validation_error']

/**
 * Применение плана. 409 import_has_errors — не ошибка экрана: в ответе свежий план элемента
 * (данные успели измениться), он возвращается как { item, rejected: true, detail }.
 */
export async function applyItem(id, options) {
  try {
    const item = await api.post(`/inbox/${id}/apply`, options ? { options } : {}, { handled: PLAN_ERRORS })
    return { item, rejected: false, detail: '' }
  } catch (e) {
    if (e.status === 409 && e.code === 'import_has_errors' && e.body?.item) return { item: e.body.item, rejected: true, detail: e.message }
    throw e
  }
}

/** Правила приходят списком строк «источник × набор» (на случай обёртки { rules } — тоже). */
export const ruleList = (data) => (Array.isArray(data) ? data : data?.rules || [])

export const inboxApi = {
  /** ?status=a,b&dataset=x|none&source&q&date_from&date_to&integration_id&page&page_size → { items, total, counts }. */
  list: (params) => api.get('/inbox', params),
  /** Элемент с планом, итогом и параметрами набора. */
  item: (id) => api.get(`/inbox/${id}`),
  /** Наборы (с can_apply и правилами), источники, статусы, предел размера, срок хранения, can_manage. */
  datasets: (options = {}) => api.get('/inbox/datasets', null, options),
  /**
   * Загрузка файла: dataset — набор (пусто — распознать), apply — применить, если план без ошибок,
   * options — параметры набора. Ошибки файла (набор недоступен, размер, формат) окно показывает само.
   */
  upload: ({ file, dataset = '', apply = false, options = null }) => {
    const form = new FormData()
    form.append('file', file)
    form.append('dataset', dataset || '')
    form.append('apply', apply ? 'true' : 'false')
    if (options && Object.keys(options).length) form.append('options', JSON.stringify(options))
    return request('POST', '/inbox', { form, handled: UPLOAD_ERRORS })
  },
  apply: applyItem,
  reject: (id, reason = '') => api.post(`/inbox/${id}/reject`, { reason }),
  /** Заново распознать (или с указанным набором) и построить план; apply — применить, если без ошибок. */
  retry: (id, { dataset = null, options = null, apply = false } = {}) =>
    api.post(`/inbox/${id}/retry`, { dataset: dataset || null, options: options || null, apply }),
  download: (item) => download(`/inbox/${item.id}/file`, null, item.filename || `inbox-${item.id}`),

  rules: () => api.get('/inbox/rules').then(ruleList),
  /** Меняются только переданные правила; ответ — все правила. */
  saveRules: (rules) => api.put('/inbox/rules', { rules }).then(ruleList),

  folder: () => api.get('/inbox/folder'),
  scan: () => api.post('/inbox/folder/scan'),
}
