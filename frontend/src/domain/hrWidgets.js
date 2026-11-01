/** Пользовательские дашборды: виджеты, их настройки и данные (чистые функции — покрыты тестами). */

export const WIDGET_TYPES = [
  { value: 'metric_card', label: 'Карточка метрики', icon: 'activity', multi: false },
  { value: 'line_chart', label: 'Линейный график', icon: 'chart', multi: true },
  { value: 'bar_chart', label: 'Столбчатая диаграмма', icon: 'bars', multi: true },
  { value: 'table', label: 'Таблица', icon: 'table', multi: true },
  { value: 'note', label: 'Заметка', icon: 'note', multi: false },
]
export const WIDGET_LABELS = Object.fromEntries(WIDGET_TYPES.map((t) => [t.value, t.label]))
export const MAX_WIDGETS = 40

/** Сколько колонок сетки (из четырёх) занимает виджет. */
export const WIDGET_SPAN = { metric_card: 1, note: 1, line_chart: 2, bar_chart: 2, table: 4 }

export function isMulti(type) {
  return type === 'line_chart' || type === 'bar_chart' || type === 'table'
}

/** Метрики виджета: карточка — одна (config.metric_key), графики и таблица — список (config.metric_keys). */
export function widgetKeys(widget) {
  const cfg = widget?.config || {}
  if (widget?.widget_type === 'note') return []
  if (widget?.widget_type === 'metric_card') return cfg.metric_key ? [cfg.metric_key] : []
  return Array.isArray(cfg.metric_keys) ? cfg.metric_keys.filter(Boolean) : []
}

export function sortWidgets(widgets) {
  return [...(widgets || [])].sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0))
}

/** Заголовок виджета: свой, иначе название метрики (для карточки) или тип. */
export function widgetTitle(widget, defs) {
  if (widget?.title?.trim()) return widget.title.trim()
  if (widget?.widget_type === 'metric_card') {
    const key = widget.config?.metric_key
    const d = (defs || []).find((x) => x.key === key)
    if (d) return d.label
  }
  return WIDGET_LABELS[widget?.widget_type] || 'Виджет'
}

let uid = 0

/** Виджет → строка редактора с плоскими полями (их удобно связывать с полями формы). */
export function toEditor(widget) {
  const cfg = widget?.config || {}
  return {
    uid: ++uid,
    widget_type: widget?.widget_type || 'metric_card',
    title: widget?.title || '',
    metric_key: cfg.metric_key || '',
    metric_keys: Array.isArray(cfg.metric_keys) ? [...cfg.metric_keys] : [],
    text: cfg.text || '',
  }
}

export function newWidget(type = 'metric_card', defaults = {}) {
  return { ...toEditor({ widget_type: type }), ...defaults }
}

/** Смена типа: выбранные метрики переносятся между карточкой и графиками. */
export function changeType(row, type) {
  const next = { ...row, widget_type: type }
  if (type === 'metric_card' && !next.metric_key) next.metric_key = row.metric_keys[0] || ''
  if (isMulti(type) && !next.metric_keys.length && row.metric_key) next.metric_keys = [row.metric_key]
  return next
}

/** Строка редактора → тело виджета для API. */
export function toPayload(row) {
  const config = row.widget_type === 'note'
    ? { text: row.text.trim() }
    : row.widget_type === 'metric_card' ? { metric_key: row.metric_key } : { metric_keys: [...row.metric_keys] }
  return { widget_type: row.widget_type, title: row.title.trim(), config }
}

/** Ошибка строки редактора или пустая строка. */
export function validateWidget(row) {
  if (row.widget_type === 'note') return row.text.trim() ? '' : 'Введите текст заметки'
  if (row.widget_type === 'metric_card') return row.metric_key ? '' : 'Выберите метрику'
  return row.metric_keys.length ? '' : 'Выберите хотя бы одну метрику'
}

export function moveItem(list, index, step) {
  const target = index + step
  if (target < 0 || target >= list.length) return list
  const out = [...list]
  ;[out[index], out[target]] = [out[target], out[index]]
  return out
}

/** Свои дашборды и общие дашборды других пользователей. */
export function splitDashboards(list, userId) {
  const mine = []
  const shared = []
  for (const d of list || []) (d.owner_id === userId ? mine : shared).push(d)
  return { mine, shared }
}

/** Метрика месяца из ряда дашборда (/hr/analytics/dashboard → series[i]). */
export function monthMetric(month, key) {
  return month?.metrics?.find((m) => m.key === key) || null
}

/** Последний месяц, где метрика заполнена: { month, metric } или null. */
export function latestFilled(series, key) {
  for (let i = (series?.length || 0) - 1; i >= 0; i -= 1) {
    const metric = monthMetric(series[i], key)
    if (metric && metric.value !== null && metric.value !== undefined) return { month: series[i], metric }
  }
  return null
}

/** Значения метрики по месяцам — для графиков. */
export function valuesOf(series, key) {
  return (series || []).map((s) => monthMetric(s, key)?.value ?? null)
}

/**
 * Оси значений для графика нескольких метрик: метрики с одной единицей — на одной оси.
 * Две разные единицы — две оси (вторая справа); больше — общая ось. Возвращает { units, axisOf }.
 */
export function unitAxes(defs) {
  const units = [...new Set((defs || []).map((d) => d.unit || ''))]
  const split = units.length === 2
  return { units: split ? units : [units.length === 1 ? units[0] : ''], axisOf: (d) => (split ? units.indexOf(d.unit || '') : 0) }
}
