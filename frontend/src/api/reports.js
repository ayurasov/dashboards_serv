/**
 * API сквозных отчётов (ADR-0010). Пути и параметры совпадают с backend/app/api/routers/reports.py.
 * period — ГГГГ-ММ (без него — последний месяц с данными, видимыми пользователю).
 */
import { api } from './client'
import { postPlan, uploadForm } from './org'

export const reportsApi = {
  /** Отчёт: вершины области (или видимый уровень root) с уровнями до предела глубины. */
  scorecard: ({ period, root } = {}) => api.get('/reports/scorecard', { period, root }),
  /** Подразделение: показатели с трендом за 12 месяцев, дочерние, объяснение, ссылки. Ошибки — в панели. */
  unit: (id, { period } = {}) => api.get(`/reports/units/${id}`, { period }, { silent: true }),
  periods: () => api.get('/reports/periods'),
  /** Карточка «Обзора»: статус области пользователя. */
  summary: (period) => api.get('/reports/summary', { period }, { silent: true }),
  meta: () => api.get('/reports/meta'),

  // каталог показателей
  indicators: () => api.get('/reports/indicators'),
  createIndicator: (body) => api.post('/reports/indicators', body),
  updateIndicator: (id, body) => api.patch(`/reports/indicators/${id}`, body),
  /** Без force при сохранённых значениях — 409 indicator_has_values. */
  deleteIndicator: (id, force = false) => api.del(`/reports/indicators/${id}`, { params: { force: force || undefined }, silent: true }),

  // ввод значений
  values: ({ period, indicator, unit } = {}) => api.get('/reports/values', { period, indicator, unit }, { silent: true }),
  saveValues: (period, items) => api.put('/reports/values', { period, items }),
  /** Загрузка файла: apply = false — проверка (план), true — применение. 409 с планом — { …план, rejected }. */
  importValues: ({ file, content, apply = false }) => (file
    ? postPlan('/reports/values/import', { form: uploadForm(file, { apply }) })
    : postPlan('/reports/values/import', { body: { content, apply } })),

  // заметка «под контролем»
  saveNote: (unitId, body) => api.put(`/reports/units/${unitId}/note`, body),

  // подразделения служб
  settings: () => api.get('/reports/settings'),
  saveSettings: (units) => api.put('/reports/settings', { report_service_units: units }),
}
