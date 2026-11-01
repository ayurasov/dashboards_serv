/** Технологические партнёрства: подготовка данных экранов (чистые функции — покрыты тестами). */
import { LIGHT_LABELS, LIGHT_ORDER } from '@/utils/lights'
import { MONTHS, formatNumber, plural } from '@/utils/format'

/** Статусы по умолчанию — в порядке жизненного цикла. Значения из базы, которых здесь нет, идут следом. */
export const PARTNERSHIP_STATUSES = ['В работе', 'Завершено', 'Отложено', 'Не подписывают']
export const PARTNERSHIP_TYPES = ['ПО', 'ПАК', 'Оборудование']

/** Части светофора записи — в порядке проверки. */
export const LIGHT_PARTS = [
  { key: 'status', label: 'Статус' },
  { key: 'nda', label: 'NDA' },
  { key: 'agreement', label: 'Соглашение' },
  { key: 'cert_age', label: 'Срок сертификата' },
]
export const LIGHT_GROUP_ORDER = LIGHT_PARTS.map((p) => p.key)

export const LIGHT_FILTERS = [
  { value: 'green', label: 'Норма' },
  { value: 'yellow', label: 'Внимание' },
  { value: 'red', label: 'Критично' },
]

/** Варианты цвета в настройке правил. */
export const LIGHT_CHOICES = [
  { value: 'green', label: 'Норма' },
  { value: 'yellow', label: 'Внимание' },
  { value: 'red', label: 'Критично' },
  { value: 'gray', label: 'Нет оценки' },
]

const collator = new Intl.Collator('ru')

/** Список для выбора: сначала значения по умолчанию, затем остальные из данных по алфавиту. */
export function mergeOptions(base = [], extra = []) {
  const known = new Set(base)
  const rest = [...new Set((extra || []).filter((v) => v && !known.has(v)))].sort(collator.compare)
  return [...base, ...rest]
}

/** Только встречающиеся в данных статусы, в порядке жизненного цикла. */
export function orderStatuses(present = []) {
  const set = new Set(present)
  return mergeOptions(PARTNERSHIP_STATUSES.filter((s) => set.has(s)), present)
}

/** Доля count от total в процентах; total = 0 → 0. */
export function share(count, total, digits = 1) {
  if (!total) return 0
  const k = 10 ** digits
  return Math.round(((count || 0) * 100 * k) / total) / k
}

/** { name: count } → [[name, count]] по убыванию, при равенстве — по алфавиту. */
export function sortedEntries(counts, limit = 0) {
  const list = Object.entries(counts || {}).sort((a, b) => b[1] - a[1] || collator.compare(a[0], b[0]))
  return limit ? list.slice(0, limit) : list
}

export function countWord(n) {
  return plural(n, ['партнёрство', 'партнёрства', 'партнёрств'])
}

/** Строки светофора аналитики → группы (статус, NDA, соглашение, срок сертификата). */
export function groupLightRows(rows = []) {
  const groups = []
  for (const r of rows) {
    let g = groups.find((x) => x.key === r.group_key)
    if (!g) {
      g = { key: r.group_key, label: r.group, items: [], total: 0 }
      groups.push(g)
    }
    g.items.push(r)
    g.total += r.count || 0
  }
  const rank = (k) => {
    const i = LIGHT_GROUP_ORDER.indexOf(k)
    return i < 0 ? LIGHT_GROUP_ORDER.length : i
  }
  return groups.sort((a, b) => rank(a.key) - rank(b.key))
}

/** «NDA подписан» в группе «NDA» → «Подписан»; «Сертификат актуален» → «Актуален». */
export function shortRuleLabel(label = '', group = '') {
  let text = label
  for (const prefix of [group, 'Сертификат']) {
    if (prefix && text.toLowerCase().startsWith(`${prefix.toLowerCase()} `)) text = text.slice(prefix.length + 1)
  }
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : label
}

/** Сколько записей в норме, требуют внимания, критичны. */
export function countByLight(rows = []) {
  const out = { green: 0, yellow: 0, red: 0, gray: 0 }
  for (const r of rows) out[r.light in out ? r.light : 'gray'] += 1
  return out
}

/** Ширины сегментов полосы светофора, % (сумма — 100 или 0). */
export function lightSegments(counts, keys = ['green', 'yellow', 'red']) {
  const total = keys.reduce((s, k) => s + (counts?.[k] || 0), 0)
  return keys.map((k) => ({ light: k, count: counts?.[k] || 0, share: share(counts?.[k] || 0, total) }))
}

// ---------- срок сертификата ----------

function parseDate(value) {
  if (!value) return null
  if (value instanceof Date) return value
  const [y, m, d] = String(value).slice(0, 10).split('-').map(Number)
  return y ? new Date(Date.UTC(y, (m || 1) - 1, d || 1)) : null
}

/** Возраст сертификата в годах (как на сервере: дни / 365,25). */
export function certAgeYears(certDate, today = new Date()) {
  const d = parseDate(certDate)
  if (!d) return null
  const t = Date.UTC(today.getFullYear(), today.getMonth(), today.getDate())
  return (t - d.getTime()) / 86400000 / 365.25
}

/** 1 → «1 год», 2,5 → «2,5 года», 7 → «7 лет». */
export function formatYears(value, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—'
  const n = Math.max(0, Number(value))
  const k = 10 ** digits
  const rounded = Math.round(n * k) / k
  if (rounded < 1 && digits <= 1) {
    const months = Math.max(0, Math.round(n * 12))
    return months < 1 ? 'меньше месяца' : `${months} ${plural(months, ['месяц', 'месяца', 'месяцев'])}`
  }
  const word = Number.isInteger(rounded) ? plural(rounded, ['год', 'года', 'лет']) : 'года'
  return `${formatNumber(rounded, { digits })} ${word}`
}

// ---------- объяснение светофора записи ----------

/** Части оценки записи с понятными подписями. light_parts приходит с сервера. */
export function lightParts(record, today = new Date()) {
  const parts = record?.light_parts || {}
  const out = []
  if (parts.status) {
    out.push({ key: 'status', label: 'Статус', value: record.status || 'не указан', light: parts.status })
  }
  if (parts.nda) out.push({ key: 'nda', label: 'NDA', value: record.nda ? 'подписан' : 'не подписан', light: parts.nda })
  if (parts.agreement) {
    out.push({ key: 'agreement', label: 'Соглашение', value: record.agreement ? 'подписано' : 'не подписано', light: parts.agreement })
  }
  if (parts.cert_age) {
    const age = certAgeYears(record.cert_date, today)
    out.push({ key: 'cert_age', label: 'Срок сертификата', value: age === null ? 'нет даты' : formatYears(age), light: parts.cert_age })
  } else {
    out.push({ key: 'cert_age', label: 'Срок сертификата', value: 'дата не указана', light: 'gray', skipped: true })
  }
  return out
}

/** Какие части определили итоговый цвет (худший из оценённых). */
export function decisiveParts(record) {
  const final = record?.light || 'gray'
  if (final === 'gray') return []
  return lightParts(record).filter((p) => p.light === final)
}

/** Подсказка к точке светофора: итог и вклад каждой части. */
export function lightExplanation(record, today = new Date()) {
  const final = record?.light || 'gray'
  const lines = [`Итог: ${LIGHT_LABELS[final]}${final === 'gray' ? '' : ' — худшая из оценок'}`]
  for (const p of lightParts(record, today)) {
    lines.push(`${p.label}: ${p.value} — ${p.skipped ? 'не учитывается' : LIGHT_LABELS[p.light].toLowerCase()}`)
  }
  return lines.join('\n')
}

const REASON_WORDS = { status: 'статус', nda: 'NDA', agreement: 'соглашение', cert_age: 'срок сертификата' }

/** Короткая причина итогового цвета: «NDA, соглашение». */
export function lightReason(record, capitalize = true) {
  const decisive = decisiveParts(record)
  const rated = lightParts(record).filter((p) => !p.skipped && p.light !== 'gray')
  const text = decisive.length > 1 && decisive.length === rated.length
    ? 'все части'
    : decisive.map((p) => REASON_WORDS[p.key]).join(', ')
  return text && capitalize ? text.charAt(0).toUpperCase() + text.slice(1) : text
}

// ---------- сортировка реестра ----------

const SORT_VALUE = {
  light: (r) => LIGHT_ORDER[r.light] ?? 9,
  nda: (r) => (r.nda ? 1 : 0),
  agreement: (r) => (r.agreement ? 1 : 0),
  docs: (r) => (r.nda ? 1 : 0) + (r.agreement ? 1 : 0),
  status: (r) => {
    const i = PARTNERSHIP_STATUSES.indexOf(r.status)
    return i < 0 ? PARTNERSHIP_STATUSES.length : i
  },
}

/** Сортировка с пустыми значениями в конце, при равенстве — по партнёру. */
export function sortPartnerships(rows = [], key = 'partner', dir = 'asc') {
  const sign = dir === 'desc' ? -1 : 1
  const get = SORT_VALUE[key] || ((r) => r[key])
  const empty = (v) => v === null || v === undefined || v === ''
  return [...rows].sort((a, b) => {
    const va = get(a)
    const vb = get(b)
    if (empty(va) !== empty(vb)) return empty(va) ? 1 : -1
    let cmp = 0
    if (!empty(va)) cmp = typeof va === 'number' && typeof vb === 'number' ? va - vb : collator.compare(String(va), String(vb))
    return cmp * sign || collator.compare(a.partner || '', b.partner || '') || (a.id || 0) - (b.id || 0)
  })
}

// ---------- хронология ----------

export function eventDate(record) {
  return record?.last_modified || record?.cert_date || null
}

export function eventKind(record) {
  return record?.last_modified ? 'Изменение' : 'Сертификация'
}

/** Поиск и отбор по продукту АЛМИ и статусу. */
export function filterTimeline(rows = [], { search = '', almi_product = '', status = '' } = {}) {
  const q = search.trim().toLowerCase()
  return rows.filter((r) => {
    if (almi_product && r.almi_product !== almi_product) return false
    if (status && r.status !== status) return false
    if (!q) return true
    return [r.partner, r.product, r.direction, r.almi_version, r.comment].some((v) => v && v.toLowerCase().includes(q))
  })
}

/** Записи → годы → месяцы, от новых к старым. */
export function groupTimeline(rows = []) {
  const sorted = [...rows].filter(eventDate).sort((a, b) => String(eventDate(b)).localeCompare(String(eventDate(a))))
  const years = []
  for (const r of sorted) {
    const date = String(eventDate(r))
    const year = Number(date.slice(0, 4))
    const monthKey = date.slice(0, 7)
    let y = years[years.length - 1]
    if (!y || y.year !== year) {
      y = { year, count: 0, months: [] }
      years.push(y)
    }
    let m = y.months[y.months.length - 1]
    if (!m || m.key !== monthKey) {
      m = { key: monthKey, label: MONTHS[Number(date.slice(5, 7)) - 1] || monthKey, items: [] }
      y.months.push(m)
    }
    m.items.push(r)
    y.count += 1
  }
  return years
}

// ---------- сводка по годам ----------

export function summaryTotals(periods = []) {
  const keys = ['total', 'green', 'yellow', 'red', 'nda_count', 'agreement_count']
  return Object.fromEntries(keys.map((k) => [k, periods.reduce((s, p) => s + (p[k] || 0), 0)]))
}

/** Изменение показателя к предыдущему году (null — сравнивать не с чем). */
export function yearDelta(current, previous, key) {
  if (!current || !previous) return null
  return (current[key] || 0) - (previous[key] || 0)
}

// ---------- правила светофора ----------

/** Изменённые правила для сохранения: [{ key, light?, threshold? }]. */
export function lightRuleChanges(draft = [], saved = []) {
  const before = Object.fromEntries(saved.map((r) => [r.key, r]))
  const out = []
  for (const r of draft) {
    const b = before[r.key]
    if (!b) continue
    const item = { key: r.key }
    if (r.light !== b.light) item.light = r.light
    if (r.threshold !== null && r.threshold !== undefined && r.threshold !== '' && Number(r.threshold) !== b.threshold) {
      item.threshold = Number(r.threshold)
    }
    if ('light' in item || 'threshold' in item) out.push(item)
  }
  return out
}

/** Проверка порогов срока сертификата: { key: текст ошибки }. */
export function thresholdErrors(rules = []) {
  const errors = {}
  const byKey = Object.fromEntries(rules.map((r) => [r.key, r]))
  for (const key of ['cert_age:fresh', 'cert_age:aging']) {
    const r = byKey[key]
    if (!r) continue
    const v = r.threshold
    if (v === null || v === undefined || v === '' || Number.isNaN(Number(v))) errors[key] = 'Укажите срок в годах'
    else if (Number(v) <= 0) errors[key] = 'Срок должен быть больше нуля'
    else if (Number(v) > 50) errors[key] = 'Не больше 50 лет'
  }
  const fresh = Number(byKey['cert_age:fresh']?.threshold)
  const aging = Number(byKey['cert_age:aging']?.threshold)
  if (!errors['cert_age:fresh'] && !errors['cert_age:aging'] && byKey['cert_age:fresh'] && byKey['cert_age:aging'] && fresh >= aging) {
    errors['cert_age:aging'] = 'Должен быть больше срока «актуален»'
  }
  return errors
}

/** Число лет в родительном падеже: «2 лет», «2,5 года», «1 года», «21 года». */
export function formatYearsGenitive(value) {
  if (value === null || value === undefined || value === '' || Number.isNaN(Number(value))) return '…'
  const n = Number(value)
  const word = Number.isInteger(n) ? plural(n, ['года', 'лет', 'лет']) : 'года'
  return `${formatNumber(n, { digits: 2 })} ${word}`
}

/** Подпись диапазона возраста для правила срока сертификата. */
export function certAgeRange(key, rules = []) {
  const byKey = Object.fromEntries(rules.map((r) => [r.key, r]))
  const fresh = formatYearsGenitive(byKey['cert_age:fresh']?.threshold)
  const aging = formatYearsGenitive(byKey['cert_age:aging']?.threshold)
  if (key === 'cert_age:fresh') return `Не старше ${fresh}`
  if (key === 'cert_age:aging') return `Старше ${fresh}, но не старше ${aging}`
  if (key === 'cert_age:stale') return `Старше ${aging}`
  return ''
}

// ---------- раскладка дашборда ----------

/**
 * Ширина блоков в сетке из columns колонок с учётом порядка и видимости:
 * ряд, который блоки не заполнили, делится между ними поровну. blocks: [{ key, span }] → { key: span }.
 */
export function fitSpans(blocks = [], columns = 12) {
  const out = {}
  let row = []
  let used = 0
  const flush = () => {
    if (!row.length) return
    const free = columns - used
    const extra = Math.floor(free / row.length)
    let rest = free - extra * row.length
    for (const b of row) {
      out[b.key] = b.span + extra + (rest > 0 ? 1 : 0)
      rest -= 1
    }
    row = []
    used = 0
  }
  for (const b of blocks) {
    const span = Math.min(b.span, columns)
    if (used + span > columns) flush()
    row.push({ key: b.key, span })
    used += span
  }
  flush()
  return out
}
