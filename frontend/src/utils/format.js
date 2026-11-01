/** Форматирование чисел, дат и изменений для русского интерфейса. */

const NBSP = ' '

export function formatNumber(value, { digits = 2, unit = '' } = {}) {
  if (value === null || value === undefined || value === '' || Number.isNaN(Number(value))) return '—'
  const n = Number(value)
  // Типографский минус, как в изменениях (formatDelta)
  const text = n.toLocaleString('ru-RU', { maximumFractionDigits: Number.isInteger(n) ? 0 : digits }).replace('-', '−')
  if (!unit) return text
  if (unit === '%') return `${text}%`
  return `${text}${NBSP}${unit}`
}

export function formatCompact(value) {
  if (value === null || value === undefined) return '—'
  const n = Number(value)
  if (Math.abs(n) >= 1_000_000) return `${(n / 1_000_000).toLocaleString('ru-RU', { maximumFractionDigits: 1 })}${NBSP}млн`
  if (Math.abs(n) >= 10_000) return `${(n / 1000).toLocaleString('ru-RU', { maximumFractionDigits: 1 })}${NBSP}тыс.`
  return formatNumber(n)
}

export function formatPercent(value, digits = 1) {
  if (value === null || value === undefined) return '—'
  return `${Number(value).toLocaleString('ru-RU', { maximumFractionDigits: digits })}%`
}

function toDate(value) {
  if (!value) return null
  if (value instanceof Date) return value
  // Сервер отдаёт время UTC без зоны
  const text = String(value)
  return new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(text) || text.length <= 10 ? text : `${text}Z`)
}

export function formatDate(value) {
  const d = toDate(value)
  return d ? d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' }) : '—'
}

export function formatDateTime(value) {
  const d = toDate(value)
  if (!d) return '—'
  return d.toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

const PLURALS = new Intl.PluralRules('ru-RU')

/** plural(5, ['неделя', 'недели', 'недель']) → «недель» */
export function plural(n, [one, few, many]) {
  const rule = PLURALS.select(Math.abs(n))
  return rule === 'one' ? one : rule === 'few' ? few : many
}

export function formatRelative(value, now = new Date()) {
  const d = toDate(value)
  if (!d) return '—'
  const minutes = Math.round((now - d) / 60000)
  if (minutes < 1) return 'только что'
  if (minutes < 60) return `${minutes} ${plural(minutes, ['минуту', 'минуты', 'минут'])} назад`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours} ${plural(hours, ['час', 'часа', 'часов'])} назад`
  const days = Math.round(hours / 24)
  if (days < 30) return `${days} ${plural(days, ['день', 'дня', 'дней'])} назад`
  return formatDate(d)
}

/**
 * Оценка изменения с учётом направления метрики:
 * lower_is_better — рост плох; higher_is_better — рост хорош; neutral — без оценки.
 */
export function deltaTone(delta, direction, threshold = 0) {
  if (delta === null || delta === undefined || Math.abs(delta) <= threshold) return 'flat'
  if (direction === 'lower_is_better') return delta < 0 ? 'good' : 'bad'
  if (direction === 'higher_is_better') return delta > 0 ? 'good' : 'bad'
  return 'flat'
}

export function formatDelta(delta, unit = '', digits = 2) {
  if (delta === null || delta === undefined) return ''
  const sign = delta > 0 ? '+' : delta < 0 ? '−' : '±'
  return `${sign}${formatNumber(Math.abs(delta), { digits, unit: unit === '%' ? ' п.п.' : unit }).replace(`${NBSP} п.п.`, ' п.п.')}`
}

export function pctChange(now, prev) {
  if (now === null || now === undefined || prev === null || prev === undefined || prev === 0) return null
  return ((now - prev) / Math.abs(prev)) * 100
}

export const MONTHS = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь']
export const MONTHS_SHORT = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек']

/** '2026-06' → 'Июнь 2026' */
export function monthLabel(key, short = false) {
  const [y, m] = String(key).split('-').map(Number)
  if (!y || !m) return key
  return short ? `${MONTHS_SHORT[m - 1]} ${String(y).slice(2)}` : `${MONTHS[m - 1]} ${y}`
}
