/** Ввод данных месяца: разбор чисел, изменённые строки, светофор и выбор месяца (чистые функции — покрыты тестами). */
import { evaluate } from '@/utils/lights'

/**
 * Число из поля ввода: допускает запятую, пробелы между разрядами и пустое значение (= очистить).
 * Возвращает { value } или { error }.
 */
export function parseNumber(raw) {
  const text = String(raw ?? '').replace(/[\s\u00a0\u202f]/g, '').replace(',', '.').replace('\u2212', '-')
  if (!text) return { value: null }
  if (!/^[-+]?(\d+(\.\d*)?|\.\d+)$/.test(text)) return { error: 'Введите число' }
  const value = Number(text)
  return Number.isFinite(value) ? { value } : { error: 'Введите число' }
}

/** Значение метрики → текст поля ввода (с запятой, без разделителей разрядов). */
export function formatInput(value) {
  if (value === null || value === undefined || value === '') return ''
  return String(value).replace('.', ',')
}

/** Начальное состояние формы по метрикам месяца: { key: { value, source_note } }. */
export function buildForm(metrics) {
  return Object.fromEntries((metrics || []).map((m) => [m.key, { value: formatInput(m.value), source_note: m.source_note || '' }]))
}

/** Ошибки формы: { key: текст } для полей, где введено не число. */
export function formErrors(form) {
  const out = {}
  for (const [key, row] of Object.entries(form || {})) {
    const parsed = parseNumber(row.value)
    if (parsed.error) out[key] = parsed.error
  }
  return out
}

/** Изменилась ли строка формы относительно сохранённой метрики. */
export function isRowChanged(metric, row) {
  if (!metric || !row) return false
  const parsed = parseNumber(row.value)
  if (parsed.error) return true
  const saved = metric.value === undefined ? null : metric.value
  return parsed.value !== saved || row.source_note.trim() !== (metric.source_note || '')
}

/** Тело запроса сохранения — только изменённые строки, в порядке метрик. */
export function changedRows(metrics, form) {
  const out = []
  for (const m of metrics || []) {
    const row = form?.[m.key]
    if (!row || !isRowChanged(m, row)) continue
    const parsed = parseNumber(row.value)
    if (parsed.error) continue
    out.push({ metric_key: m.key, value: parsed.value, source_note: row.source_note.trim() })
  }
  return out
}

/**
 * Ошибки сервера по телу-списку ('2.value') → по ключам метрик, которые были в запросе.
 */
export function mapRowErrors(fields, payload) {
  const out = {}
  for (const [name, message] of Object.entries(fields || {})) {
    const [index] = name.split('.')
    const row = payload?.[Number(index)]
    if (row) out[row.metric_key] = message
  }
  return out
}

/**
 * Светофор значения — как на сервере (services/hr.py, light_for): незаполненная метрика под включённым
 * правилом — красная, метрика без правила — серая.
 */
export function lightFor(value, rule) {
  if (value === null || value === undefined) return rule?.enabled ? 'red' : 'gray'
  return evaluate(value, rule)
}

/** Изменение к прошлому месяцу для введённого значения. */
export function liveDelta(value, previous) {
  if (value === null || value === undefined || previous === null || previous === undefined) return null
  return Math.round((value - previous) * 10000) / 10000
}

export function monthKey(year, month) {
  return `${year}-${String(month).padStart(2, '0')}`
}

/** Месяц, который логично добавить следующим: после последнего, а если месяцев нет — текущий. */
export function nextMonth(months, today = new Date()) {
  const last = months?.length ? months[months.length - 1] : null
  if (!last) return { year: today.getFullYear(), month: today.getMonth() + 1 }
  return last.month === 12 ? { year: last.year + 1, month: 1 } : { year: last.year, month: last.month + 1 }
}

/** Насколько заполнен месяц: full | partial | empty. */
export function fillState(month) {
  if (!month || !month.total_metrics) return 'empty'
  if (month.filled_metrics >= month.total_metrics) return 'full'
  return month.filled_metrics > 0 ? 'partial' : 'empty'
}

/** Месяцы по годам — новые годы сверху, месяцы внутри года по порядку. */
export function groupMonthsByYear(months) {
  const years = new Map()
  for (const m of months || []) {
    if (!years.has(m.year)) years.set(m.year, [])
    years.get(m.year).push(m)
  }
  return [...years.entries()]
    .sort((a, b) => b[0] - a[0])
    .map(([year, items]) => ({ year, months: [...items].sort((a, b) => a.month - b.month) }))
}

/** Какой месяц открыть: из адреса, если он есть в списке, иначе последний. */
export function pickMonth(months, wanted) {
  if (!months?.length) return ''
  if (wanted && months.some((m) => m.key === wanted)) return wanted
  return months[months.length - 1].key
}
