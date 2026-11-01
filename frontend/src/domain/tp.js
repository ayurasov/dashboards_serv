/**
 * Техническая поддержка, недельный отчёт: подготовка данных дашборда и сравнения периодов.
 * Чистые функции — покрыты тестами (tp.test.js). Логика перенесена из прежних TpDashboard/TpSummary.
 *
 * Строка отчёта: { id, year, week, period: '2026-W31', note, ...39 показателей (число или null) }.
 * Интервал агрегируется так: показатели уровня и отношения (AVG_METRICS) — среднее за недели,
 * остальные — сумма. Пороги светофора задаются на одну неделю, поэтому для сумм они
 * умножаются на число недель интервала.
 */
import { evaluate } from '@/utils/lights'
import { deltaTone, formatNumber, pctChange, plural } from '@/utils/format'

/** Быстрые периоды: последние N недель с данными или всё время. */
export const QUICK_PERIODS = [
  { value: '1', label: 'Последняя неделя' },
  { value: '2', label: '2 недели' },
  { value: '4', label: 'Месяц' },
  { value: '8', label: '8 недель' },
  { value: '13', label: '13 недель' },
  { value: '26', label: 'Полгода' },
  { value: 'all', label: 'Всё время' },
]

/** Показатели, которые за интервал усредняются (остальные суммируются). */
export const AVG_METRICS = new Set(['total_in_work', 'ratio_solved_received', 'altos_avg_time', 'altoffice_avg_time'])

/** Клиенты: показатель трудозатрат, подпись (short — для легенд) и номер цвета серии (--chart-N, порядок фиксирован). */
export const CLIENTS = [
  { key: 'rushydro_hours', label: 'РусГидро', color: 1 },
  { key: 'transneft_hours', label: 'Транснефть', color: 2 },
  { key: 'roscosmos_hours', label: 'Роскосмос', color: 3 },
  { key: 'bryansk_hours', label: 'Брянск', color: 4 },
  { key: 'mchs_hours', label: 'МЧС', color: 5 },
  { key: 'internal_sales_hours', label: 'Внутренние задачи и продажи', short: 'Внутр. и продажи', color: 6 },
]

/** Короткие подписи карточек светофора (порядок карточек); прочие правила — подпись с сервера. */
export const TRAFFIC_METRICS = [
  { key: 'total_in_work', label: 'В работе, в среднем' },
  { key: 'avail_total', label: 'Трудозатраты' },
  { key: 'new_received', label: 'Принято новых заявок' },
  { key: 'total_solved_week', label: 'Решено заявок' },
  { key: 'ratio_solved_received', label: 'Решено / получено' },
  { key: 'altos_avg_time', label: 'AlterOS: ср. время решения' },
  { key: 'altoffice_avg_time', label: 'AlterOffice: ср. время решения' },
  { key: 'altos_avail_total', label: 'AlterOS: доступно' },
  { key: 'altoffice_avail_total', label: 'AlterOffice: доступно' },
]

/** Направление оценки, если правило светофора для показателя не задано (как в прежней версии). */
export const METRIC_DIRECTIONS = {
  total_in_work: 'lower_is_better',
  avail_total: 'lower_is_better',
  new_received: 'lower_is_better',
  total_solved_week: 'higher_is_better',
  ratio_solved_received: 'higher_is_better',
  altos_avg_time: 'lower_is_better',
  altoffice_avg_time: 'lower_is_better',
  altos_avail_total: 'higher_is_better',
  altoffice_avail_total: 'higher_is_better',
}

/** Столбцы детальной таблицы; dot — точка светофора по неделе. */
export const TABLE_COLUMNS = [
  { key: 'period', label: 'Неделя' },
  { key: 'total_in_work', label: 'В работе', unit: 'шт.', dot: true },
  { key: 'avail_total', label: 'Трудозатраты', unit: 'ч', dot: true },
  { key: 'new_received', label: 'Принято', unit: 'шт.', dot: true },
  { key: 'total_solved_week', label: 'Решено', unit: 'шт.', dot: true },
  { key: 'ratio_solved_received', label: 'Решено / получено', dot: true },
  ...CLIENTS.map((c) => ({ key: c.key, label: c.short || c.label, unit: 'ч', client: true })),
  { key: 'altos_avg_time', label: 'AlterOS, ср. время', unit: 'ч', dot: true },
  { key: 'altoffice_avg_time', label: 'AlterOffice, ср. время', unit: 'ч', dot: true },
]

/** Продукты с линиями поддержки: префикс показателей. */
export const PRODUCTS = [
  { key: 'altos', label: 'AlterOS' },
  { key: 'altoffice', label: 'AlterOffice' },
]

/** Каналы обращений по продукту: суффикс показателя, клиентская группа и способ. */
export const CHANNELS = [
  { suffix: 'rusg_email', label: 'РусГидро · e-mail', group: 'rushydro', channel: 'email' },
  { suffix: 'rusg_tf', label: 'РусГидро · телефон', group: 'rushydro', channel: 'phone' },
  { suffix: 'other_email', label: 'Прочие · e-mail', group: 'other', channel: 'email' },
  { suffix: 'other_tf', label: 'Прочие · телефон', group: 'other', channel: 'phone' },
]

/** Сложность заявок для доступности по срокам. */
export const COMPLEXITY = [
  { suffix: '1_3', label: 'Сложность 1–3', short: '1–3' },
  { suffix: '4_7', label: 'Сложность 4–7', short: '4–7' },
  { suffix: '8_10', label: 'Сложность 8–10', short: '8–10' },
]

// ---------- выборка недель ----------

/** '8' → 8; 'all' и всё нечисловое → null. */
export function quickWeeks(quick) {
  const n = Number.parseInt(quick, 10)
  return Number.isFinite(n) && n > 0 ? n : null
}

/** Отбрасывает строки без года или недели, округляет их и сортирует по времени. */
export function normalizeRows(rows) {
  return (rows || [])
    .filter((r) => r && r.year !== null && r.year !== undefined && r.week !== null && r.week !== undefined)
    .map((r) => ({ ...r, year: Math.round(r.year), week: Math.round(r.week) }))
    .sort((a, b) => a.year - b.year || a.week - b.week)
}

export function yearsOf(rows) {
  return [...new Set(rows.map((r) => r.year))].sort((a, b) => a - b)
}

/** Номера недель с данными: всех лет или одного года. */
export function weeksOf(rows, year = null) {
  const list = year === null || year === undefined ? rows : rows.filter((r) => r.year === Number(year))
  return [...new Set(list.map((r) => r.week))].sort((a, b) => a - b)
}

/**
 * Годы и диапазон недель, которые соответствуют быстрому периоду (прежняя applyQuick):
 * «всё время» — все годы и все недели; N недель — годы и крайние недели последних N строк.
 */
export function quickSelection(rows, quick) {
  const n = quickWeeks(quick)
  if (!n) {
    const weeks = weeksOf(rows)
    return { years: yearsOf(rows), weekFrom: weeks[0] ?? null, weekTo: weeks.at(-1) ?? null }
  }
  const last = rows.slice(-n)
  return { years: [...new Set(last.map((r) => r.year))], weekFrom: last[0]?.week ?? null, weekTo: last.at(-1)?.week ?? null }
}

/**
 * Строки выбранного периода. Быстрый период N — последние N недель. Иначе — выбранные годы
 * (пустой список — все годы); диапазон недель действует, только когда выбран ровно один год.
 * weekFrom / weekTo: null или 0 — без границы.
 */
export function filterRows(rows, { quick = 'all', years = [], weekFrom = null, weekTo = null } = {}) {
  const n = quickWeeks(quick)
  if (n) return rows.slice(-n)
  const ys = years.length ? years.map(Number) : yearsOf(rows)
  const single = ys.length === 1
  return rows.filter((r) => {
    if (!ys.includes(r.year)) return false
    if (!single) return true
    if (weekFrom && r.week < weekFrom) return false
    if (weekTo && r.week > weekTo) return false
    return true
  })
}

/** Недели, в которых у клиента есть трудозатраты (фильтр «Клиент» для таблицы). */
export function clientRows(rows, clientKey) {
  if (!clientKey) return rows
  return rows.filter((r) => r[clientKey] !== null && r[clientKey] !== undefined && r[clientKey] > 0)
}

export function clientInfo(clientKey) {
  return CLIENTS.find((c) => c.key === clientKey) || null
}

// ---------- агрегирование ----------

export function isAvgMetric(key) {
  return AVG_METRICS.has(key)
}

function values(rows, key) {
  return rows.map((r) => r[key]).filter((v) => v !== null && v !== undefined && Number.isFinite(Number(v))).map(Number)
}

/** Сумма непустых значений; null — если значений нет совсем. */
export function sumOf(rows, key) {
  const vals = values(rows, key)
  return vals.length ? vals.reduce((a, b) => a + b, 0) : null
}

/** Среднее непустых значений; null — если значений нет. */
export function avgOf(rows, key) {
  const vals = values(rows, key)
  return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null
}

/** Значение показателя за интервал: среднее для AVG_METRICS, иначе сумма. */
export function aggregate(rows, key) {
  if (!rows?.length) return null
  return isAvgMetric(key) ? avgOf(rows, key) : sumOf(rows, key)
}

/** Множитель порогов светофора: для сумм — число недель интервала, для средних — 1. */
export function intervalScale(key, weeks) {
  return isAvgMetric(key) ? 1 : Math.max(1, weeks || 0)
}

/** Светофор значения за интервал (пороги сумм умножены на число недель). */
export function evaluateInterval(rows, key, rule) {
  return evaluate(aggregate(rows, key), rule, intervalScale(key, rows.length))
}

/** Итоги таблицы по выбранным строкам: суммы и средние по тем же правилам. */
export function totals(rows, keys) {
  return Object.fromEntries(keys.map((k) => [k, aggregate(rows, k)]))
}

/** Значения показателя по неделям для графика (пропуски — null). */
export function seriesOf(rows, key) {
  return rows.map((r) => (r[key] === undefined ? null : r[key]))
}

/**
 * Ячейка детальной таблицы. Отношение «решено / получено» — всегда с двумя знаками («1,00», «0,95»),
 * как в недельном отчёте: иначе в столбце смешиваются «1», «1,9» и «1,38».
 */
export function tableCell(value, key) {
  if (value === null || value === undefined || value === '' || !Number.isFinite(Number(value))) return '—'
  if (key === 'ratio_solved_received') {
    return Number(value).toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).replace('-', '−')
  }
  return formatNumber(value, { digits: metricDigits(key) })
}

/** Знаков после запятой: отношение — 2, остальное — 1 (целые выводятся без дробной части). */
export function metricDigits(key) {
  return key === 'ratio_solved_received' ? 2 : 1
}

// ---------- сравнение интервалов ----------

/**
 * Текущий и предыдущий интервалы одинаковой длины — суммы за разное число недель не сравниваются:
 * быстрый период N — последние N недель и N недель перед ними (если истории меньше N недель,
 * сравнивать не с чем — prev пустой); «всё время» — вторая половина выбранных недель против первой,
 * при нечётном числе недель средняя неделя не входит ни в одну половину.
 */
export function comparePeriods(rows, filtered, quick) {
  const n = quickWeeks(quick)
  if (n) {
    return { mode: 'quick', weeks: n, now: rows.slice(-n), prev: rows.length >= 2 * n ? rows.slice(-2 * n, -n) : [] }
  }
  const half = Math.floor(filtered.length / 2)
  if (!half) return { mode: 'halves', weeks: null, now: [], prev: [] }
  return { mode: 'halves', weeks: half, now: filtered.slice(-half), prev: filtered.slice(0, half) }
}

/** Изменение показателя: значения интервалов, разница и процент (null — сравнить нельзя). */
export function intervalDelta(pair, key) {
  const now = aggregate(pair.now, key)
  const prev = aggregate(pair.prev, key)
  const delta = now !== null && prev !== null ? now - prev : null
  return { now, prev, delta, pct: pctChange(now, prev) }
}

/** Подпись к изменению в карточке. */
export function deltaLabel(pair) {
  if (pair.mode === 'halves') return 'к 1-й половине периода'
  return pair.weeks === 1 ? 'к пред. неделе' : `к пред. ${pair.weeks} нед.`
}

/** Заголовок интервала: «Последние 8 недель», «Предыдущая неделя», «2-я половина периода». */
export function intervalTitle(pair, which) {
  if (pair.mode === 'halves') return which === 'now' ? '2-я половина периода' : '1-я половина периода'
  const n = which === 'now' ? pair.weeks : (pair.prev.length || pair.weeks)
  const adjective = which === 'now'
    ? plural(n, ['Последняя', 'Последние', 'Последние'])
    : plural(n, ['Предыдущая', 'Предыдущие', 'Предыдущие'])
  return n === 1 ? `${adjective} неделя` : `${adjective} ${n} ${plural(n, ['неделя', 'недели', 'недель'])}`
}

/** '2025-W01 — 2025-W52' или одна неделя. */
export function periodRange(rows) {
  if (!rows?.length) return ''
  return rows.length === 1 ? rows[0].period : `${rows[0].period} — ${rows.at(-1).period}`
}

// ---------- светофор ----------

export function rulesByKey(rules) {
  return Object.fromEntries((rules || []).map((r) => [r.metric_key, r]))
}

/** Направление показателя: из сохранённого правила, иначе из METRIC_DIRECTIONS, иначе без оценки. */
export function metricDirection(key, rule) {
  const stored = rule && (rule.updated_at || isSet(rule.green_threshold) || isSet(rule.yellow_threshold))
  if (stored && rule.direction) return rule.direction
  return METRIC_DIRECTIONS[key] || 'neutral'
}

function isSet(v) {
  return v !== null && v !== undefined
}

const TRAFFIC_ORDER = Object.fromEntries(TRAFFIC_METRICS.map((m, i) => [m.key, i]))
const TRAFFIC_LABELS = Object.fromEntries(TRAFFIC_METRICS.map((m) => [m.key, m.label]))

/**
 * Карточки светофора: включённые правила, значение за интервал, оценка с масштабированными
 * порогами и изменение к предыдущему интервалу той же длины (pair из comparePeriods).
 */
export function trafficCards(rows, rules, pair = null) {
  if (!rows?.length) return []
  return (rules || [])
    .map((rule, i) => ({ rule, i }))
    .filter(({ rule }) => rule.enabled)
    .sort((a, b) => (TRAFFIC_ORDER[a.rule.metric_key] ?? 100 + a.i) - (TRAFFIC_ORDER[b.rule.metric_key] ?? 100 + b.i))
    .map(({ rule }) => {
      const key = rule.metric_key
      const value = aggregate(rows, key)
      const scale = intervalScale(key, rows.length)
      const scaled = (t) => (isSet(t) ? Number(t) * scale : null)
      return {
        key,
        label: TRAFFIC_LABELS[key] || rule.label,
        unit: rule.unit || '',
        value,
        digits: metricDigits(key),
        light: evaluate(value, rule, scale),
        direction: rule.direction,
        aggregation: isAvgMetric(key) ? 'avg' : 'sum',
        weeks: rows.length,
        green: scaled(rule.green_threshold),
        yellow: scaled(rule.yellow_threshold),
        deltaPct: pair ? intervalDelta(pair, key).pct : null,
      }
    })
}

/** Светофор значения одной недели (точки в таблице). */
export function weekLight(row, key, rule) {
  if (!rule?.enabled) return null
  return evaluate(row[key] ?? null, rule)
}

// ---------- детальная таблица ----------

/** Поиск по неделе ('2025-W24', '2025-24') и примечанию. */
export function searchRows(rows, text) {
  const q = String(text || '').trim().toLowerCase()
  if (!q) return rows
  return rows.filter((r) => `${r.period} ${r.year}-${r.week} ${r.note || ''}`.toLowerCase().includes(q))
}

/** Сортировка: пустые значения всегда в конце; неделя — по году и номеру. */
export function sortRows(rows, key, dir = 'asc') {
  const sign = dir === 'desc' ? -1 : 1
  const pick = (r) => (key === 'period' ? r.year * 100 + r.week : r[key])
  return [...rows].sort((a, b) => {
    const av = pick(a)
    const bv = pick(b)
    const an = av === null || av === undefined
    const bn = bv === null || bv === undefined
    if (an && bn) return 0
    if (an) return 1
    if (bn) return -1
    if (typeof av === 'string') return av.localeCompare(bv, 'ru') * sign
    return (av - bv) * sign
  })
}

/** Строки таблицы: поиск, фильтр клиента, сортировка. */
export function tableRows(rows, { search = '', client = '', sortKey = 'period', sortDir = 'asc' } = {}) {
  return sortRows(clientRows(searchRows(rows, search), client), sortKey, sortDir)
}

// ---------- данные графиков ----------

/**
 * Трудозатраты по клиентам за период. С выбранным клиентом — клиент и «Остальные клиенты»
 * (всего доступно минус клиент). share — доля, %.
 */
export function clientShares(rows, clientKey = '') {
  const client = clientInfo(clientKey)
  let items
  if (client) {
    const value = sumOf(rows, client.key) || 0
    const rest = Math.max(0, (sumOf(rows, 'avail_total') || 0) - value)
    items = [{ key: client.key, label: client.label, color: client.color, value }, { key: 'rest', label: 'Остальные клиенты', color: null, value: rest }]
  } else {
    items = CLIENTS.map((c) => ({ key: c.key, label: c.label, color: c.color, value: sumOf(rows, c.key) || 0 }))
  }
  const total = items.reduce((s, x) => s + x.value, 0)
  return items.map((x) => ({ ...x, share: total > 0 ? (x.value / total) * 100 : 0 }))
}

/** Недели с наибольшим значением показателя (по убыванию), только ненулевые. */
export function topWeeks(rows, key, limit = 15) {
  return rows
    .filter((r) => r[key] !== null && r[key] !== undefined && r[key] > 0)
    .sort((a, b) => b[key] - a[key] || a.year - b.year || a.week - b.week)
    .slice(0, limit)
    .map((r) => ({ period: r.period, value: r[key] }))
}

/** Обращения по способу за период: e-mail и телефон по обоим продуктам. */
export function channelTotals(rows) {
  const out = { email: 0, phone: 0 }
  for (const p of PRODUCTS) {
    for (const c of CHANNELS) out[c.channel] += sumOf(rows, `${p.key}_${c.suffix}`) || 0
  }
  return out
}

/** Итоги продукта за период: решено всего и по линиям, среднее время, доступность. */
export function productSummary(rows, product) {
  const l12 = sumOf(rows, `${product}_1_2line`)
  const l3 = sumOf(rows, `${product}_3line`)
  const lines = (l12 || 0) + (l3 || 0)
  return {
    total: sumOf(rows, `${product}_total`),
    l12,
    l3,
    l12Share: lines > 0 ? ((l12 || 0) / lines) * 100 : null,
    l3Share: lines > 0 ? ((l3 || 0) / lines) * 100 : null,
    avgTime: avgOf(rows, `${product}_avg_time`),
    avail: sumOf(rows, `${product}_avail_total`),
  }
}

/** Project Server за период: принято, решено, доля решённых, доступно на последней неделе с данными. */
export function projServerSummary(rows) {
  const taken = sumOf(rows, 'projserver_taken')
  const solved = sumOf(rows, 'projserver_solved')
  const withAvail = rows.filter((r) => r.projserver_avail !== null && r.projserver_avail !== undefined)
  const last = withAvail.at(-1)
  return {
    taken,
    solved,
    solvedShare: taken ? ((solved || 0) / taken) * 100 : null,
    availLast: last ? last.projserver_avail : null,
    availLastPeriod: last ? last.period : '',
    availAvg: avgOf(rows, 'projserver_avail'),
  }
}

// ---------- сравнение периодов (отдельная страница) ----------

/** Показатели по группам в порядке столбцов: [{ key, label, items }]. */
export function groupColumns(columns) {
  const groups = []
  for (const c of columns || []) {
    let g = groups.find((x) => x.key === c.group)
    if (!g) {
      g = { key: c.group, label: c.group_label, items: [] }
      groups.push(g)
    }
    g.items.push(c)
  }
  return groups
}

/**
 * Таблица сравнения: для каждого показателя — значения интервалов, изменение, оценка
 * изменения по направлению и светофор текущего интервала.
 */
export function compareMetrics(columns, pair, rules = {}) {
  return (columns || []).map((c) => {
    const rule = rules[c.key]
    const d = intervalDelta(pair, c.key)
    const direction = metricDirection(c.key, rule)
    return {
      key: c.key,
      label: c.label,
      unit: c.unit || '',
      group: c.group,
      group_label: c.group_label,
      ...d,
      digits: metricDigits(c.key),
      direction,
      tone: deltaTone(d.delta, direction),
      light: rule?.enabled ? evaluateInterval(pair.now, c.key, rule) : null,
    }
  })
}

/** Сводка оценок изменения: сколько показателей улучшились, ухудшились, не изменились. */
export function toneCounts(items) {
  const out = { good: 0, bad: 0, flat: 0 }
  for (const m of items) {
    if (m.direction === 'neutral' || m.delta === null) continue
    out[m.tone] += 1
  }
  return out
}

/**
 * Короткие подписи для осей графика: общий начальный фрагмент «AlterOS · …» убирается.
 * ['AlterOS · 1–2 линия', 'AlterOS · 3 линия'] → ['1–2 линия', '3 линия'].
 */
export function shortLabels(labels) {
  const parts = labels.map((l) => String(l).split(' · '))
  if (labels.length > 1 && parts.every((p) => p.length > 1 && p[0] === parts[0][0])) {
    return parts.map((p) => {
      const rest = p.slice(1).join(' · ')
      return rest.charAt(0).toUpperCase() + rest.slice(1)
    })
  }
  return labels.map(String)
}
