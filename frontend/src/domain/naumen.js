/**
 * Техподдержка: недельный отчёт, заявки Naumen и их сопоставление.
 * Чистые функции подготовки данных для экранов — покрыты тестами (naumen.test.js).
 */
import { formatNumber, plural } from '@/utils/format'

const DAY = 86_400_000
const toNum = (v) => (v === null || v === undefined || v === '' || Number.isNaN(Number(v)) ? null : Number(v))

// ---------------------------------------------------------------------------
// Периоды и быстрый выбор
// ---------------------------------------------------------------------------

export const QUICK_MONTHS = [
  { value: 1, label: 'Последний месяц' },
  { value: 3, label: '3 месяца' },
  { value: 6, label: '6 месяцев' },
  { value: 12, label: '12 месяцев' },
  { value: 0, label: 'Всё время' },
]

export const QUICK_WEEKS = [
  { value: 4, label: '4 недели' },
  { value: 13, label: 'Квартал' },
  { value: 26, label: 'Полгода' },
  { value: 52, label: 'Год' },
  { value: 0, label: 'Всё время' },
]

/** Последние count элементов упорядоченного ряда; 0 — весь ряд. */
export function lastPeriods(rows, count) {
  const list = rows || []
  return count ? list.slice(-count) : [...list]
}

/** Строки выбранного года; пустой год (0, '', null) — все строки. */
export function filterByYear(rows, year) {
  const list = rows || []
  return year ? list.filter((r) => Number(r.year) === Number(year)) : [...list]
}

/** Уникальные годы ряда по возрастанию. */
export function yearsOf(rows) {
  return [...new Set((rows || []).map((r) => Number(r.year)).filter(Boolean))].sort((a, b) => a - b)
}

/** Подпись количества периодов: «12 недель», «3 месяца». */
export function periodCount(n, unit = 'weeks') {
  const forms = unit === 'weeks' ? ['неделя', 'недели', 'недель'] : ['месяц', 'месяца', 'месяцев']
  return `${n} ${plural(n, forms)}`
}

// ---------------------------------------------------------------------------
// ISO-недели
// ---------------------------------------------------------------------------

/** Понедельник ISO-недели (UTC). Неделя 1 — та, в которой 4 января. */
export function isoWeekStart(year, week) {
  const jan4 = Date.UTC(year, 0, 4)
  const weekday = (new Date(jan4).getUTCDay() + 6) % 7
  return new Date(jan4 - weekday * DAY + (week - 1) * 7 * DAY)
}

export function isoWeeksInYear(year) {
  return Math.round((isoWeekStart(year + 1, 1) - isoWeekStart(year, 1)) / (7 * DAY))
}

/** Неделя, следующая за данной: { year, week }. */
export function nextIsoWeek(year, week) {
  return week >= isoWeeksInYear(year) ? { year: year + 1, week: 1 } : { year, week: week + 1 }
}

/** ISO-неделя даты: { year, week } (как Python date.isocalendar()). */
export function isoWeekOf(date) {
  const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()))
  const weekday = (d.getUTCDay() + 6) % 7
  const thursday = new Date(d.getTime() + (3 - weekday) * DAY)
  const year = thursday.getUTCFullYear()
  return { year, week: Math.floor((thursday - isoWeekStart(year, 1)) / (7 * DAY)) + 1 }
}

const MONTHS_GEN = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря']
const pad = (n) => String(n).padStart(2, '0')

/**
 * Даты недели. short: «27.07–02.08»; иначе «27 июля — 2 августа 2026», «6–12 июля 2026»,
 * «29 декабря 2025 — 4 января 2026».
 */
export function weekRangeText(year, week, { short = false } = {}) {
  if (!year || !week) return ''
  const start = isoWeekStart(Number(year), Number(week))
  const end = new Date(start.getTime() + 6 * DAY)
  const [d1, m1, y1] = [start.getUTCDate(), start.getUTCMonth(), start.getUTCFullYear()]
  const [d2, m2, y2] = [end.getUTCDate(), end.getUTCMonth(), end.getUTCFullYear()]
  if (short) return `${pad(d1)}.${pad(m1 + 1)}–${pad(d2)}.${pad(m2 + 1)}`
  if (y1 !== y2) return `${d1} ${MONTHS_GEN[m1]} ${y1} — ${d2} ${MONTHS_GEN[m2]} ${y2}`
  if (m1 !== m2) return `${d1} ${MONTHS_GEN[m1]} — ${d2} ${MONTHS_GEN[m2]} ${y2}`
  return `${d1}–${d2} ${MONTHS_GEN[m2]} ${y2}`
}

/** '2026-W31' → { year: 2026, week: 31 } или null. */
export function parsePeriod(period) {
  const m = /^(\d{4})-W(\d{1,2})$/.exec(String(period || ''))
  return m ? { year: Number(m[1]), week: Number(m[2]) } : null
}

/** Подпись недели на оси: '2026-W31' → 'W31\n2026'. */
export function weekAxisLabel(period) {
  const p = parsePeriod(period)
  return p ? `W${pad(p.week)}\n${p.year}` : String(period ?? '')
}

/** Дата из строки сервера без пересчёта часового пояса: '2026-08-04T14:02:37' → '04.08.2026'. */
export function dayText(value) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(value || ''))
  return m ? `${m[3]}.${m[2]}.${m[1]}` : '—'
}

/** Текст для HTML-подсказок графиков (названия организаций приходят из выгрузки). */
export function escapeHtml(text) {
  return String(text ?? '').replace(/[&<>"']/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[ch])
}

// ---------------------------------------------------------------------------
// Числа и часы
// ---------------------------------------------------------------------------

/** Ввод числа: «1 234,5» → 1234.5; пусто → null; не число → NaN. */
export function parseDecimal(text) {
  if (text === null || text === undefined) return null
  if (typeof text === 'number') return Number.isFinite(text) ? text : NaN
  const clean = String(text).replace(/\s/g, '').replace(',', '.')
  if (clean === '' || clean === '-' || clean === '—') return null
  return /^-?\d*\.?\d+$|^-?\d+\.$/.test(clean) ? Number(clean) : NaN
}

/** Часы: 153.17 → «153 ч», 4.25 → «4,3 ч». */
export function formatHours(value) {
  const n = toNum(value)
  if (n === null) return '—'
  return formatNumber(Math.abs(n) >= 100 ? Math.round(n) : Math.round(n * 10) / 10, { unit: 'ч' })
}

/** Пояснение к длительности в часах: от двух суток — в днях («≈ 54 дн.»). */
export function hoursHint(value) {
  const n = toNum(value)
  if (n === null || n < 48) return ''
  const days = n / 24
  return `≈ ${formatNumber(days >= 10 ? Math.round(days) : Math.round(days * 10) / 10)} дн.`
}

export function sumBy(rows, key) {
  return (rows || []).reduce((s, r) => s + (toNum(r[key]) ?? 0), 0)
}

/** Среднее по непустым значениям; нет значений — null. */
export function avgBy(rows, key) {
  const values = (rows || []).map((r) => toNum(r[key])).filter((v) => v !== null)
  return values.length ? values.reduce((a, b) => a + b, 0) / values.length : null
}

/** Доля part от whole, % (одна десятая); whole = 0 — null. */
export function share(part, whole) {
  const p = toNum(part)
  const w = toNum(whole)
  if (p === null || !w) return null
  return Math.round((p / w) * 1000) / 10
}

// ---------------------------------------------------------------------------
// Оценки
// ---------------------------------------------------------------------------

/** Доля просроченных заявок: до 10% — норма, до 20% — внимание, больше — критично. */
export const OVERDUE_LEVELS = { yellow: 10, red: 20 }

export function overdueLight(pct) {
  const n = toNum(pct)
  if (n === null) return 'gray'
  return n > OVERDUE_LEVELS.red ? 'red' : n > OVERDUE_LEVELS.yellow ? 'yellow' : 'green'
}

/** Покрытие отчёта заявками Naumen: от 85% — норма, от 60% — внимание. */
export const COVERAGE_LEVELS = { green: 85, yellow: 60 }

export function coverageLight(pct) {
  const n = toNum(pct)
  if (n === null) return 'gray'
  return n >= COVERAGE_LEVELS.green ? 'green' : n >= COVERAGE_LEVELS.yellow ? 'yellow' : 'red'
}

/** Закрытые статусы Naumen (как на сервере). */
export const CLOSED_STATUSES = ['Закрыта', 'Выполнена']

/** Строки «топа» с долей от максимума — для полосок в таблицах. */
export function withBar(rows, key = 'total') {
  const max = Math.max(0, ...(rows || []).map((r) => toNum(r[key]) ?? 0))
  return (rows || []).map((r) => ({ ...r, bar: max ? Math.round(((toNum(r[key]) ?? 0) / max) * 1000) / 10 : 0 }))
}

/** Каналы и статусы: { name, value, share } по убыванию. */
export function distribution(items, nameKey, valueKey = 'count') {
  const list = (items || []).map((i) => ({ name: i[nameKey] || '—', value: toNum(i[valueKey]) ?? 0 }))
  const total = list.reduce((s, i) => s + i.value, 0)
  return list
    .sort((a, b) => b.value - a.value)
    .map((i) => ({ ...i, share: total ? Math.round((i.value / total) * 1000) / 10 : 0 }))
}

// ---------------------------------------------------------------------------
// Отчёт и Naumen: расхождения
// ---------------------------------------------------------------------------

/** Пары «показатель отчёта — показатель Naumen», по которым считается расхождение. */
export const MATCH_PAIRS = {
  received: { tp: 'tp_new_received', naumen: 'naumen_registered' },
  solved: { tp: 'tp_solved', naumen: 'naumen_solved' },
}

/**
 * Пороги подсветки: доля Naumen отличается от ожидаемой больше чем на 25% — внимание, на 50% — сильное
 * расхождение. Чтобы не подсвечивать случайные колебания малых чисел, разница с ожиданием должна
 * выходить за обычный разброс счётных данных: |Naumen − ожидание| / √ожидание не меньше zYellow (zRed).
 * Периоды, где по отчёту меньше minBase заявок, не оцениваются.
 */
export const DIVERGENCE = { yellow: 0.25, red: 0.5, zYellow: 2, zRed: 3, minBase: 5 }

/** Периоды, по которым есть недельный отчёт (месяцы только с заявками Naumen отбрасываются). */
export function withReport(rows) {
  return (rows || []).filter((r) => toNum(r.tp_new_received) !== null || toNum(r.tp_solved) !== null)
}

/** Обычная доля Naumen от отчёта по выборке, %: Σ Naumen / Σ отчёт по периодам, где есть оба значения. */
export function typicalShare(rows, tpKey, nmKey) {
  let tp = 0
  let nm = 0
  for (const r of rows || []) {
    const a = toNum(r[tpKey])
    const b = toNum(r[nmKey])
    if (a === null || b === null) continue
    tp += a
    nm += b
  }
  return tp > 0 ? (nm / tp) * 100 : null
}

/**
 * Расхождение отчёта и Naumen за период.
 * expected — ожидаемая доля Naumen от отчёта, % (100 — «один к одному», либо обычная доля по выборке).
 * → { diff: отчёт − Naumen, share: доля Naumen от отчёта, %, deviation: отклонение доли от ожидаемой
 *     (−0.5 — вдвое меньше ожидаемого), z: разница с ожиданием в единицах обычного разброса,
 *     level: 'red' | 'yellow' | null }
 */
export function divergence(tp, nm, expected = 100, limits = DIVERGENCE) {
  const a = toNum(tp)
  const b = toNum(nm)
  const out = { diff: null, share: null, deviation: null, z: null, level: null }
  if (a === null || b === null) return out
  out.diff = Math.round((a - b) * 100) / 100
  if (a <= 0) return out
  out.share = Math.round((b / a) * 1000) / 10
  if (!expected) return out
  const actual = (b / a) * 100
  out.deviation = Math.round(((actual - expected) / expected) * 1000) / 1000
  const expectedCount = (a * expected) / 100
  out.z = Math.round(((b - expectedCount) / Math.sqrt(Math.max(expectedCount, 1))) * 100) / 100
  if (a >= limits.minBase) {
    const dev = Math.abs(out.deviation)
    const z = Math.abs(out.z)
    out.level = dev >= limits.red && z >= limits.zRed ? 'red' : dev >= limits.yellow && z >= limits.zYellow ? 'yellow' : null
  }
  return out
}

/**
 * Строки таблицы сопоставления с расхождениями по принятым и решённым заявкам.
 * basis: 'typical' — сравнение с обычной долей по выборке, 'direct' — один к одному.
 */
export function divergenceRows(rows, basis = 'typical') {
  const expected = {}
  for (const [name, pair] of Object.entries(MATCH_PAIRS)) {
    expected[name] = basis === 'direct' ? 100 : typicalShare(rows, pair.tp, pair.naumen)
  }
  const list = (rows || []).map((r) => {
    const out = { ...r }
    for (const [name, pair] of Object.entries(MATCH_PAIRS)) out[name] = divergence(r[pair.tp], r[pair.naumen], expected[name])
    out.level = [out.received.level, out.solved.level].includes('red') ? 'red'
      : [out.received.level, out.solved.level].includes('yellow') ? 'yellow' : null
    return out
  })
  return { rows: list, expected }
}

/** Отклонение в подписи: −0.62 → «−62%». */
export function formatDeviation(dev) {
  const n = toNum(dev)
  if (n === null) return '—'
  const pct = Math.round(n * 100)
  return `${pct > 0 ? '+' : pct < 0 ? '−' : '±'}${Math.abs(pct)}%`
}

/** Разница со знаком: 5 → «+5», −3 → «−3». */
export function formatSigned(value) {
  const n = toNum(value)
  if (n === null) return '—'
  if (n === 0) return '0'
  return `${n > 0 ? '+' : '−'}${formatNumber(Math.abs(n), { digits: 1 })}`
}

// ---------------------------------------------------------------------------
// Недельный отчёт: столбцы, поиск, сортировка
// ---------------------------------------------------------------------------

/** Группы, видимые в таблице по умолчанию. */
export const DEFAULT_GROUPS = ['load', 'client_hours', 'tickets']

/** Столбцы [{ key, label, group, group_label, unit }] → группы в исходном порядке. */
export function groupColumns(columns) {
  const groups = []
  for (const c of columns || []) {
    let g = groups.find((x) => x.key === c.group)
    if (!g) {
      g = { key: c.group, label: c.group_label, columns: [] }
      groups.push(g)
    }
    g.columns.push(c)
  }
  return groups
}

/**
 * Короткая подпись столбца внутри своей группы: продукт из названия группы не повторяется.
 * «AlterOS · РусГидро · e-mail» в группе «AlterOS: каналы» → «РусГидро · e-mail».
 */
export function shortLabel(label, groupLabel = '') {
  const text = String(label || '')
  const product = String(groupLabel || '').split(':')[0].trim()
  if (product && text.startsWith(`${product} · `)) {
    const rest = text.slice(product.length + 3)
    return rest.charAt(0).toUpperCase() + rest.slice(1)
  }
  return text
}

/** Поиск по периоду («2026-W3», «w31», «2025») и примечанию. */
export function matchesSearch(row, query) {
  const q = String(query || '').trim().toLowerCase().replace(/\s+/g, '')
  if (!q) return true
  const period = String(row.period || '').toLowerCase()
  return period.includes(q) || String(row.note || '').toLowerCase().replace(/\s+/g, '').includes(q)
}

const periodKey = (r) => Number(r.year) * 100 + Number(r.week)

/** Сортировка недель: 'period' — по году и неделе; иначе по значению, пустые всегда в конце. */
export function sortWeeks(rows, key = 'period', dir = 'desc') {
  const sign = dir === 'asc' ? 1 : -1
  return [...(rows || [])].sort((a, b) => {
    if (key === 'period') return (periodKey(a) - periodKey(b)) * sign
    const x = toNum(a[key])
    const y = toNum(b[key])
    if (x === null && y === null) return (periodKey(b) - periodKey(a))
    if (x === null) return 1
    if (y === null) return -1
    return (x - y) * sign || periodKey(b) - periodKey(a)
  })
}

/** Значение показателя в таблице: доли — два знака, остальное — до одного. */
export function formatMetric(value, column) {
  const n = toNum(value)
  if (n === null) return '—'
  if (column?.key?.startsWith('ratio')) return n.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return formatNumber(n, { digits: 1 })
}
