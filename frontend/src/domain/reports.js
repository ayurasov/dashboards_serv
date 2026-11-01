/**
 * Сквозные отчёты (ADR-0010): дерево подразделений отчёта, раскрытие уровней, фильтры матрицы,
 * ячейки и подсказки, правила светофора показателей, тренд за 12 месяцев, ввод значений
 * (изменённые ячейки → PUT), загрузка значений (план, шаблон CSV). Вход — ответы /api/reports/*
 * (поля как в API). Чистые функции — покрыты тестами (reports.test.js).
 */
import { LIGHT_LABELS, MISSING_LABEL } from '@/utils/lights'
import { deltaTone, formatCompact, formatDelta, formatNumber, plural } from '@/utils/format'

// ---------------------------------------------------------------- виды и подписи

export const REPORT_VIEWS = [
  { value: 'matrix', label: 'Матрица', icon: 'table', hint: 'Подразделения × показатели: цвет ячейки — статус показателя' },
  { value: 'chart', label: 'Оргсхема статусов', icon: 'org', hint: 'Карточки структуры, окрашенные статусом' },
  { value: 'list', label: 'Список', icon: 'list', hint: 'Подразделения карточками с главными проблемами' },
]
export const REPORT_VIEW_KEYS = REPORT_VIEWS.map((v) => v.value)

/** Вид из адреса; без него — «Список» на телефоне и «Матрица» на остальных экранах. */
export function resolveReportView(value, narrow = false) {
  return REPORT_VIEW_KEYS.includes(value) ? value : narrow ? 'list' : 'matrix'
}

/** Порядок статусов — от худшего. */
export const STATUS_ORDER = ['red', 'yellow', 'green', 'gray']
export const STATUS_RANK = { missing: 0, red: 1, yellow: 2, green: 3, gray: 4 }
export const STATUS_FILTERS = [
  { value: '', label: 'Все' },
  { value: 'red', label: LIGHT_LABELS.red },
  { value: 'yellow', label: LIGHT_LABELS.yellow },
  { value: 'green', label: LIGHT_LABELS.green },
]
export const DATA_CLASS_SHORT = { operational: 'Опер.', personal: 'Перс.', financial: 'Фин.' }
export const UNIT_FORMS = ['подразделение', 'подразделения', 'подразделений']
export const INDICATOR_FORMS = ['показатель', 'показателя', 'показателей']
export const VALUE_FORMS = ['значение', 'значения', 'значений']

export const count = (n, forms) => `${Number(n || 0).toLocaleString('ru-RU')} ${plural(Number(n || 0), forms)}`
const capitalize = (text) => (text ? text[0].toUpperCase() + text.slice(1) : text)
const isNil = (v) => v === null || v === undefined

// ---------------------------------------------------------------- доступ

/**
 * Строка «Ваш доступ: …» без перечня скрытых классов и отдельная заметка о них:
 * «Финансовые показатели скрыты», «Персональные и финансовые показатели скрыты».
 */
export function accessLine(access) {
  if (!access) return { text: '', hidden: '' }
  const text = String(access.text || '').replace(/\s*·\s*скрыты:.*$/u, '')
  const names = (access.hidden_classes || []).map((n, i) => (i ? String(n).toLowerCase() : String(n)))
  const hidden = names.length
    ? `${names.length > 1 ? `${names.slice(0, -1).join(', ')} и ${names.at(-1).toLowerCase()}` : names[0]} показатели скрыты`
    : ''
  return { text, hidden: capitalize(hidden) }
}

// ---------------------------------------------------------------- дерево отчёта

/**
 * Лес подразделений из плоского списка отчёта (порядок ответа — обход дерева, он сохраняется):
 * [{ id, item, depth, children }]. Родитель вне списка — узел становится вершиной.
 */
export function buildTree(units = []) {
  const nodes = new Map(units.map((u) => [u.id, { id: u.id, item: u, depth: 0, children: [] }]))
  const roots = []
  for (const unit of units) {
    const node = nodes.get(unit.id)
    const parent = !isNil(unit.parent_id) && unit.parent_id !== unit.id ? nodes.get(unit.parent_id) : null
    if (parent) parent.children.push(node)
    else roots.push(node)
  }
  const seen = new Set()
  const walk = (list, depth) => {
    for (const node of list) {
      if (seen.has(node.id)) continue
      seen.add(node.id)
      node.depth = depth
      walk(node.children, depth + 1)
    }
  }
  walk(roots, 0)
  // Цикл в данных не прячет подразделения: недостижимые — в вершины, без дочерних
  for (const node of nodes.values()) {
    if (seen.has(node.id)) continue
    seen.add(node.id)
    node.children = []
    roots.push(node)
  }
  return roots
}

/** Раскрытые узлы, чтобы было видно depth уровней под вершинами (null — все уровни). */
export function expandToDepth(forest, depth = null) {
  const result = new Set()
  const walk = (nodes) => {
    for (const node of nodes) {
      if (node.children.length && (depth === null || node.depth < depth)) result.add(node.id)
      walk(node.children)
    }
  }
  walk(forest)
  return result
}

/** Глубина леса: 1 — только вершины. */
export function treeDepth(forest) {
  let depth = 0
  const walk = (nodes) => { for (const n of nodes) { depth = Math.max(depth, n.depth + 1); walk(n.children) } }
  walk(forest)
  return depth
}

/** Предки подразделения в лесу (от вершины), без самого подразделения. */
export function ancestorIds(forest, id) {
  const path = []
  const find = (nodes, trail) => {
    for (const node of nodes) {
      if (node.id === id) { path.push(...trail); return true }
      if (find(node.children, [...trail, node.id])) return true
    }
    return false
  }
  find(forest, [])
  return path
}

// ---------------------------------------------------------------- фильтры матрицы

/** Нарушение полноты у подразделения: свои пропуски или пропуски за пределом детализации. */
export function hasViolation(unit) {
  return (unit?.missing?.length || 0) > 0 || (!!unit?.drill_locked && (unit?.missing_total || 0) > 0)
}

export function isFiltered(filter = {}) {
  return !!filter.status || !!filter.violations
}

export function matchesFilter(unit, { status = '', violations = false } = {}) {
  if (status && unit.status !== status) return false
  if (violations && !hasViolation(unit)) return false
  return true
}

/**
 * Строки матрицы: без фильтра — по раскрытию; с фильтром — подходящие подразделения и их предки
 * (как контекст, match: false), ветки раскрыты до совпадений.
 */
export function matrixRows(forest, expanded = new Set(), filter = {}) {
  const rows = []
  if (!isFiltered(filter)) {
    const walk = (nodes) => {
      for (const node of nodes) {
        const open = node.children.length > 0 && expanded.has(node.id)
        rows.push({ id: node.id, node, unit: node.item, depth: node.depth, hasChildren: node.children.length > 0, open, match: true })
        if (open) walk(node.children)
      }
    }
    walk(forest)
    return rows
  }
  const keep = new Map()
  const mark = (node) => {
    const self = matchesFilter(node.item, filter)
    let any = self
    for (const child of node.children) any = mark(child) || any
    keep.set(node.id, { self, any })
    return any
  }
  forest.forEach(mark)
  const walk = (nodes) => {
    for (const node of nodes) {
      const state = keep.get(node.id)
      if (!state?.any) continue
      const kids = node.children.filter((c) => keep.get(c.id)?.any)
      rows.push({ id: node.id, node, unit: node.item, depth: node.depth, hasChildren: kids.length > 0, open: kids.length > 0, match: state.self, forced: true })
      walk(kids)
    }
  }
  walk(forest)
  return rows
}

/** Подразделения, подходящие под фильтр (без контекста), — для счётчика «показано N из M». */
export function filteredCount(units = [], filter = {}) {
  return units.filter((u) => matchesFilter(u, filter)).length
}

/** Столбцы матрицы: показатели со значением хотя бы у одного подразделения (all — все видимые). */
export function matrixColumns(indicators = [], units = [], { all = false } = {}) {
  const used = new Set()
  for (const unit of units) for (const key of Object.keys(unit.cells || {})) used.add(key)
  return {
    columns: all ? [...indicators] : indicators.filter((i) => used.has(i.key)),
    empty: indicators.filter((i) => !used.has(i.key)),
  }
}

// ---------------------------------------------------------------- ячейки и подсказки

/** Число в ячейке: ru-RU, точность по величине (274 · 96,3 · 4,63), крупные — «тыс.», «млн». */
export function shortNumber(value) {
  if (isNil(value) || Number.isNaN(Number(value))) return '—'
  const n = Number(value)
  const abs = Math.abs(n)
  if (abs >= 100000) return formatCompact(n)
  return formatNumber(n, { digits: abs >= 10 ? 1 : 2 })
}

const EPS = 1e-9

/**
 * Вид ячейки: tone — green · yellow · red · gray · missing · none (нет значения и не ожидается),
 * text — значение, arrow — up · down · null, trend — good · bad · flat (по направлению показателя).
 */
export function cellView(cell, indicator = {}) {
  if (!cell) return { tone: 'none', text: '—', arrow: null, trend: 'flat', label: 'Нет значения' }
  if (cell.missing) return { tone: 'missing', text: MISSING_LABEL, arrow: null, trend: 'flat', label: `${MISSING_LABEL}: не заполнено — критичное нарушение полноты` }
  const delta = isNil(cell.delta) || Math.abs(cell.delta) < EPS ? null : cell.delta
  const tone = cell.status || 'gray'
  const text = shortNumber(cell.value)
  const value = isNil(cell.value) ? '—' : formatNumber(cell.value, { unit: indicator.unit || '' })
  return {
    tone, text, arrow: delta === null ? null : delta > 0 ? 'up' : 'down',
    trend: deltaTone(delta, indicator.direction || 'neutral'),
    label: `${value}, ${cell.status_label || LIGHT_LABELS[tone]}`,
  }
}

/** Правило светофора словами: «Норма ≥ 4,5 из 5 · внимание ≥ 4 из 5», «Отклонение от цели: до 5% — норма…». */
export function ruleSummary(ind = {}) {
  if (ind.direction === 'neutral') return 'Без оценки'
  const unit = ind.unit || ''
  if (ind.rule_type === 'target') {
    if (isNil(ind.green_deviation) || isNil(ind.yellow_deviation)) return 'Отклонение от цели не задано'
    return `Отклонение от цели: до ${formatNumber(ind.green_deviation, { unit: '%' })} — норма, до ${formatNumber(ind.yellow_deviation, { unit: '%' })} — внимание`
  }
  const g = ind.green_threshold
  const y = ind.yellow_threshold
  if (isNil(g) && isNil(y)) return 'Без светофора'
  const sign = ind.direction === 'lower_is_better' ? '≤' : '≥'
  const parts = []
  if (!isNil(g)) parts.push(`норма ${sign} ${formatNumber(g, { unit })}`)
  if (!isNil(y)) parts.push(`внимание ${sign} ${formatNumber(y, { unit })}`)
  return capitalize(parts.join(' · '))
}

/**
 * Подсказка ячейки: показатель, подразделение, статус и строки «значение, цель, отклонение,
 * правило, к прошлому месяцу, источник», отдельно — комментарий.
 */
export function cellTooltip(cell, indicator = {}, unitName = '') {
  const unit = indicator.unit || ''
  const head = { title: indicator.name || indicator.key || '', subtitle: unitName }
  if (!cell) {
    return { ...head, tone: 'none', status: 'Нет значения', rows: [], comment: '', note: 'За период значения нет, и оно здесь не ожидается' }
  }
  const rows = []
  const tone = cell.missing ? 'missing' : cell.status || 'gray'
  rows.push({ label: 'Значение', value: cell.missing ? 'Не заполнено' : formatNumber(cell.value, { unit }) })
  if (!isNil(cell.target)) rows.push({ label: 'Цель', value: formatNumber(cell.target, { unit }) })
  if (!isNil(cell.deviation)) rows.push({ label: 'Отклонение от цели', value: formatNumber(cell.deviation, { unit: '%' }) })
  if (indicator.rule_type === 'threshold' && (!isNil(indicator.green_threshold) || !isNil(indicator.yellow_threshold))) {
    rows.push({ label: 'Правило', value: ruleSummary(indicator) })
  }
  if (!isNil(cell.previous)) {
    const delta = isNil(cell.delta) ? '' : `${formatDelta(cell.delta, unit) || '±0'} · `
    rows.push({ label: 'К прошлому месяцу', value: `${delta}было ${formatNumber(cell.previous, { unit })}`, trend: deltaTone(cell.delta, indicator.direction || 'neutral') })
  }
  if (cell.source_label) rows.push({ label: 'Источник', value: cell.source_label })
  return {
    ...head, tone, status: cell.missing ? MISSING_LABEL : cell.status_label || LIGHT_LABELS[tone], rows,
    comment: cell.comment || '',
    note: cell.missing ? 'Значение ожидается, но не заполнено — критичное нарушение полноты данных' : '',
  }
}

/** Свои показатели подразделения по статусам: { red, yellow, green, gray, missing }. */
export function cellCounts(unit) {
  const out = { red: 0, yellow: 0, green: 0, gray: 0, missing: 0 }
  for (const cell of Object.values(unit?.cells || {})) {
    if (cell.missing) out.missing += 1
    else out[cell.status || 'gray'] += 1
  }
  return out
}

/** Сегменты полосы «подразделения по статусам»: от худшего, нулевые не рисуются. */
export function statusSegments(counts = {}) {
  const total = STATUS_ORDER.reduce((sum, k) => sum + (counts[k] || 0), 0)
  return STATUS_ORDER.filter((k) => counts[k] > 0).map((k) => ({ light: k, value: counts[k], share: total ? counts[k] / total : 0 }))
}

/** Подразделения отчёта по статусам (кроме вершин): { red: [...], yellow: [...] } в порядке отчёта. */
export function unitsByStatus(units = [], rootIds = []) {
  const roots = new Set(rootIds)
  const out = { red: [], yellow: [], green: [], gray: [] }
  for (const unit of units) if (!roots.has(unit.id)) out[unit.status || 'gray'].push(unit)
  return out
}

/** Доступных показателей, по которым подразделения получили оценку светофором (для «статус по N показателям»). */
export function ratedIndicators(units = []) {
  const keys = new Set()
  for (const unit of units) {
    for (const [key, cell] of Object.entries(unit.cells || {})) if (cell.missing || (cell.status && cell.status !== 'gray')) keys.add(key)
  }
  return keys.size
}

/** Пропуски данных словами: видимые — «Показатель — Подразделение», скрытые — числом. */
export function violationsText(summary) {
  if (!summary) return { items: [], hidden: '' }
  const items = (summary.violations || []).map((v) => ({ ...v, text: `${v.indicator_name} — ${v.unit_name}` }))
  const n = summary.hidden_violations || 0
  const hidden = n ? `${items.length ? 'ещё ' : ''}${count(n, ['пропуск', 'пропуска', 'пропусков'])} во вложенных подразделениях (детализация недоступна)` : ''
  return { items, hidden }
}

const LIGHT_PREFIX = /^(Красный|Жёлтый|Желтый|Зелёный|Серый|Нет оценки|Нет данных):\s*/u

/** Текст причины без цветового префикса («Красный: …») и хвоста «; ещё N»: цвет показывает метка рядом. */
export function reasonText(text) {
  return capitalize(String(text || '').replace(LIGHT_PREFIX, '').replace(/;\s*ещё\s+\d+\s*$/u, '').trim())
}

/** Причина статуса для показа: название показателя отдельно (выделяется), остальное — как написал сервер. */
export function reasonParts(item = {}) {
  const text = reasonText(item.text)
  const name = item.indicator_name || ''
  if (name && text.startsWith(name)) return { lead: name, rest: text.slice(name.length) }
  return { lead: '', rest: text }
}

/** «Под контролем · Петров И. С. · 01.11.2026». */
export function noteByline(note) {
  if (!note) return ''
  const parts = [note.author?.full_name]
  if (note.created_at) {
    const d = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(note.created_at) ? note.created_at : `${note.created_at}Z`)
    if (!Number.isNaN(d.getTime())) parts.push(d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' }))
  }
  return parts.filter(Boolean).join(' · ')
}

/** Показатели панели: сначала проблемы (не заполнено, критично, внимание), затем остальные — в порядке каталога. */
export function sortIndicators(items = []) {
  const rank = (i) => (i.cell?.missing ? 0 : STATUS_RANK[i.cell?.status] ?? 5)
  return items.map((item, index) => ({ item, index })).sort((a, b) => rank(a.item) - rank(b.item) || a.index - b.index).map((x) => x.item)
}

// ---------------------------------------------------------------- правило светофора (редактор)

/** Статус значения по правилу показателя — как evaluate на сервере (services/reports.py). */
export function evaluateRule(rule = {}, value, target = rule.default_target) {
  if (isNil(value) || Number.isNaN(Number(value)) || rule.direction === 'neutral') return 'gray'
  const v = Number(value)
  if (rule.rule_type === 'target') {
    const g = rule.green_deviation
    const y = rule.yellow_deviation
    if (isNil(target) || isNil(g) || isNil(y)) return 'gray'
    const higher = rule.direction === 'higher_is_better'
    const t = Number(target)
    const deviation = t === 0
      ? ((higher ? v < 0 : v > 0) ? Infinity : 0)
      : Math.max(0, ((higher ? t - v : v - t) / Math.abs(t)) * 100)
    return deviation <= g ? 'green' : deviation <= y ? 'yellow' : 'red'
  }
  const g = rule.green_threshold
  const y = rule.yellow_threshold
  if (isNil(g) && isNil(y)) return 'gray'
  if (rule.direction === 'lower_is_better') {
    if (!isNil(g) && v <= g) return 'green'
    if (!isNil(y) && v <= y) return 'yellow'
    return 'red'
  }
  if (!isNil(g) && v >= g) return 'green'
  if (!isNil(y) && v >= y) return 'yellow'
  return 'red'
}

/**
 * Полосы светофора для предпросмотра: зоны по возрастанию значения с подписями границ.
 * Для правила «от цели» границы — в % от цели и, если цель по умолчанию задана, в единицах.
 * warning — правило противоречиво (зона нормы шире зоны внимания).
 */
export function ruleBands(rule = {}) {
  const unit = rule.unit || ''
  const f = (v) => formatNumber(v, { unit })
  const pct = (v) => formatNumber(v, { unit: '%' })
  if (rule.direction === 'neutral') return { bands: [], warning: '', empty: 'Без оценки: показатель не окрашивается' }
  const lower = rule.direction === 'lower_is_better'
  if (rule.rule_type === 'target') {
    const g = rule.green_deviation
    const y = rule.yellow_deviation
    if (isNil(g) || isNil(y)) return { bands: [], warning: '', empty: 'Задайте допустимые отклонения от цели' }
    const warning = g > y ? 'Отклонение для нормы больше, чем для внимания — зона внимания не наступит' : ''
    const t = rule.default_target
    const at = (p) => (isNil(t) ? '' : ` (${f(Math.round(Number(t) * (1 + p / 100) * 1000) / 1000)})`)
    if (lower) {
      return {
        warning,
        bands: [
          { light: 'green', text: `до +${pct(g)}${at(g)}` },
          { light: 'yellow', text: `до +${pct(y)}${at(y)}` },
          { light: 'red', text: `больше +${pct(y)}` },
        ],
      }
    }
    return {
      warning,
      bands: [
        { light: 'red', text: `ниже −${pct(y)}` },
        { light: 'yellow', text: `от −${pct(y)}${at(-y)}` },
        { light: 'green', text: `от −${pct(g)}${at(-g)}` },
      ],
    }
  }
  const g = rule.green_threshold
  const y = rule.yellow_threshold
  if (isNil(g) && isNil(y)) return { bands: [], warning: '', empty: 'Пороги не заданы — показатель без светофора' }
  if (isNil(g) || isNil(y)) {
    const only = isNil(g) ? y : g
    const light = isNil(g) ? 'yellow' : 'green'
    return {
      warning: '',
      bands: lower
        ? [{ light, text: `≤ ${f(only)}` }, { light: 'red', text: `> ${f(only)}` }]
        : [{ light: 'red', text: `< ${f(only)}` }, { light, text: `≥ ${f(only)}` }],
    }
  }
  const warning = (lower ? g > y : g < y) ? `Порог нормы должен быть ${lower ? 'не больше' : 'не меньше'} порога внимания` : ''
  if (lower) {
    return { warning, bands: [{ light: 'green', text: `≤ ${f(g)}` }, { light: 'yellow', text: `≤ ${f(y)}` }, { light: 'red', text: `> ${f(y)}` }] }
  }
  return { warning, bands: [{ light: 'red', text: `< ${f(y)}` }, { light: 'yellow', text: `≥ ${f(y)}` }, { light: 'green', text: `≥ ${f(g)}` }] }
}

/** Источник показателя каталога словами. */
export function sourceText(ind = {}) {
  if (ind.source_type === 'computed') return `Вычисляется: ${ind.source_name || ind.source_key || '—'}`
  return ind.owner_service_title ? `Вводит: ${ind.owner_service_title}` : 'Вводится по подразделениям'
}

/** Каталог по классам данных: [{ key, label, items }] в порядке справочника. */
export function groupByClass(indicators = [], classes = []) {
  const order = classes.length ? classes : [{ key: 'financial', label: 'Финансовые' }, { key: 'operational', label: 'Операционные' }, { key: 'personal', label: 'Персональные' }]
  const known = new Set(order.map((c) => c.key))
  const groups = order.map((c) => ({ key: c.key, label: c.label, items: indicators.filter((i) => i.data_class === c.key) }))
  const rest = indicators.filter((i) => !known.has(i.data_class))
  if (rest.length) groups.push({ key: 'other', label: 'Прочие', items: rest })
  return groups.filter((g) => g.items.length)
}

// ---------------------------------------------------------------- тренд за 12 месяцев

/** Текст подсказки точки тренда. */
export function trendPointText(point, unit = '') {
  if (!point) return []
  const lines = [point.label]
  if (point.missing) lines.push('Не заполнено — критичное нарушение')
  else lines.push(`Значение: ${formatNumber(point.value, { unit })}`)
  if (!isNil(point.target)) lines.push(`Цель: ${formatNumber(point.target, { unit })}`)
  if (!point.missing && !isNil(point.value)) lines.push(LIGHT_LABELS[point.status || 'gray'])
  return lines
}

/**
 * Настройки ECharts для спарклайна: линия значений (точки — цветом статуса, последняя крупнее),
 * пунктир цели; месяц, где обязательное значение не заполнено, — красная вертикаль и пустое кольцо
 * на уровне цели (или последнего значения). colors: { light(status), line, target, missing, surface }.
 */
export function trendOption(trend = [], { unit = '', colors = {} } = {}) {
  const light = colors.light || ((s) => s)
  const red = colors.missing || '#d1495b'
  const labels = trend.map((t) => t.label)
  const last = trend.length - 1
  const hasTarget = trend.some((t) => !isNil(t.target))
  const values = trend.map((t, i) => (isNil(t.value) ? null : {
    value: t.value,
    symbolSize: i === last ? 8 : 5,
    itemStyle: { color: light(t.status || 'gray') },
  }))
  // Уровень кольца пропуска: цель месяца, иначе последнее известное значение до него
  const known = (i) => { for (let j = i; j >= 0; j--) if (!isNil(trend[j].value)) return trend[j].value; return null }
  const gaps = trend.map((t, i) => (t.missing ? (t.target ?? known(i) ?? null) : null))
  const missing = trend.filter((t) => t.missing).map((t) => t.label)
  const series = [{
    name: 'Значение', type: 'line', data: values, connectNulls: false, showSymbol: true, symbol: 'circle',
    lineStyle: { width: 2, color: colors.line || '#64748b' }, z: 3,
    markLine: missing.length ? {
      silent: true, symbol: 'none', label: { show: false }, lineStyle: { color: red, type: [3, 3], width: 1.2 },
      data: missing.map((label) => ({ xAxis: label })),
    } : undefined,
  }]
  if (hasTarget) {
    series.push({
      name: 'Цель', type: 'line', data: trend.map((t) => (isNil(t.target) ? null : t.target)), symbol: 'none',
      lineStyle: { width: 1.2, type: [4, 3], color: colors.target || '#94a3b8' }, z: 2, silent: true,
    })
  }
  if (gaps.some((v) => v !== null)) {
    series.push({
      name: 'Не заполнено', type: 'scatter', data: gaps, symbol: 'circle', symbolSize: 9, z: 4, silent: true,
      itemStyle: { color: colors.surface || '#fff', borderColor: red, borderWidth: 2 },
    })
  }
  return {
    animation: false,
    grid: { left: 6, right: 6, top: 7, bottom: 5, containLabel: false },
    legend: { show: false },
    xAxis: { type: 'category', data: labels, show: false, boundaryGap: true },
    yAxis: { type: 'value', show: false, scale: true },
    tooltip: {
      trigger: 'axis', confine: true, axisPointer: { type: 'line' },
      formatter: (params) => {
        const index = [].concat(params)[0]?.dataIndex
        return trendPointText(trend[index], unit).map((line, i) => (i ? line : `<b>${line}</b>`)).join('<br/>')
      },
    },
    series,
  }
}

// ---------------------------------------------------------------- ввод значений

export const entryKey = (indicatorId, unitId) => `${indicatorId}:${unitId}`

/** Сохранённые значения: ключ ячейки → { value, target, comment }. */
export function entryOriginal(values = []) {
  const map = new Map()
  for (const v of values) map.set(entryKey(v.indicator_id, v.department_id), { value: v.value ?? null, target: v.target ?? null, comment: v.comment || '' })
  return map
}

/** Число для поля ввода: 96.5 → «96,5», пусто — ''. */
export function toInput(value) {
  return isNil(value) ? '' : String(value).replace('.', ',')
}

/** Ввод числа: «1 234,5», «−3», «96.5»; пусто — null; не число — { ok: false }. */
export function parseInput(text) {
  const clean = String(text ?? '').replace(/[\s\u00a0\u202f]/g, '').replace(/\u2212/g, '-').replace(',', '.')
  if (!clean) return { ok: true, value: null }
  if (!/^-?(\d+\.?\d*|\.\d+)(e[+-]?\d+)?$/i.test(clean)) return { ok: false, value: null }
  const value = Number(clean)
  return Number.isFinite(value) ? { ok: true, value } : { ok: false, value: null }
}

/** Черновик ячейки (строки полей) по сохранённому значению. */
export function entryDraft(original, key) {
  const v = original?.get(key)
  return { value: toInput(v?.value), target: toInput(v?.target), comment: v?.comment || '' }
}

const sameNumber = (a, b) => (isNil(a) && isNil(b)) || (!isNil(a) && !isNil(b) && Math.abs(a - b) < 1e-9)

/**
 * Изменённые ячейки → элементы PUT /api/reports/values. drafts: ключ → { value, target, comment } (строки).
 * Возвращает items, keys (ключ ячейки для каждого элемента — по нему разбираются ошибки сервера «items.N.*»)
 * и invalid — ячейки с нечисловым вводом (их в items нет).
 */
export function entryChanges(original, drafts) {
  const items = []
  const keys = []
  const invalid = {}
  for (const [key, draft] of drafts || []) {
    const [indicatorId, unitId] = key.split(':').map(Number)
    const value = parseInput(draft.value)
    const target = parseInput(draft.target)
    if (!value.ok || !target.ok) {
      invalid[key] = { ...(value.ok ? {} : { value: 'Нужно число' }), ...(target.ok ? {} : { target: 'Нужно число' }) }
      continue
    }
    const comment = String(draft.comment || '').trim()
    const before = original?.get(key) || { value: null, target: null, comment: '' }
    if (sameNumber(value.value, before.value) && sameNumber(target.value, before.target) && comment === (before.comment || '').trim()) continue
    items.push({ indicator_id: indicatorId, department_id: unitId, value: value.value, target: target.value, comment })
    keys.push(key)
  }
  return { items, keys, invalid }
}

/** Ошибки сервера по ячейкам: fields["items.N.поле"] → { ключ: { value | target | comment | cell } }. */
export function cellErrors(fields = {}, keys = []) {
  const out = {}
  for (const [name, message] of Object.entries(fields || {})) {
    const match = /^items\.(\d+)\.?(\w+)?$/.exec(name)
    if (!match) continue
    const key = keys[Number(match[1])]
    if (!key) continue
    const field = ['value', 'target', 'comment'].includes(match[2]) ? match[2] : 'cell'
    out[key] = { ...out[key], [field]: message }
  }
  return out
}

/** Можно ли вводить показатель в подразделении (unit_ids: null — во всех подразделениях формы). */
export function canEnterCell(indicator, unit) {
  return !indicator?.unit_ids || indicator.unit_ids.includes(unit?.id)
}

/** Значение ожидается (тип уровня из «где ожидается»), а ячейка пуста. */
export function expectedEmpty(indicator, unit, draft) {
  const kinds = indicator?.expected_kinds || []
  if (!kinds.includes(unit?.kind)) return false
  return !String(draft?.value ?? '').trim()
}

/** Строки формы ввода: отступ — от верхнего уровня формы. */
export function entryRows(units = []) {
  const min = Math.min(...units.map((u) => u.level || 1))
  return units.map((u) => ({ ...u, indent: Math.max(0, (u.level || 1) - (Number.isFinite(min) ? min : 1)) }))
}

/** Месяцы для ввода: от текущего назад (YYYY-MM). */
export function entryPeriods(current, count = 24) {
  const [y, m] = String(current || '').split('-').map(Number)
  if (!y || !m) return []
  const out = []
  for (let i = 0; i < count; i++) {
    const d = new Date(Date.UTC(y, m - 1 - i, 1))
    out.push(`${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}`)
  }
  return out
}

// ---------------------------------------------------------------- загрузка значений

export const IMPORT_COLUMNS = ['Подразделение', 'Показатель', 'Период', 'Значение', 'Цель', 'Комментарий']
export const IMPORT_FILTERS = [
  { value: 'changes', label: 'Изменения и ошибки' },
  { value: 'errors', label: 'Ошибки' },
  { value: 'all', label: 'Все' },
]
export const IMPORT_ACTIONS = {
  create: { label: 'Новое', tone: 'green' },
  update: { label: 'Изменится', tone: 'blue' },
  unchanged: { label: 'Без изменений', tone: 'gray' },
  error: { label: 'Ошибка', tone: 'red' },
}

const rowHasErrors = (row) => row.action === 'error' || (row.errors || []).length > 0

/** Строки плана загрузки: изменения и ошибки / только ошибки / все. */
export function filterImportRows(rows = [], filter = 'changes') {
  if (filter === 'errors') return rows.filter(rowHasErrors)
  if (filter === 'changes') return rows.filter((r) => r.action === 'create' || r.action === 'update' || rowHasErrors(r))
  return rows
}

/** Сводка плана чипами (как в «Импорт и экспорт»). */
export function importChips(summary) {
  if (!summary) return []
  const chip = (label, value, tone = 'gray') => ({ label, value: value || 0, tone: value ? tone : 'gray' })
  return [
    chip('Строк', summary.rows),
    chip('Новых', summary.create, 'green'),
    chip('Изменится', summary.update, 'blue'),
    chip('Без изменений', summary.unchanged),
    chip('Ошибок', summary.errors, 'red'),
  ]
}

function csvCell(value) {
  const text = isNil(value) ? '' : typeof value === 'number' ? String(value).replace('.', ',') : String(value)
  return /[;"\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text
}

/**
 * Шаблон загрузки CSV (UTF-8 с BOM, разделитель «;»): строка на каждую ячейку формы, которую можно
 * вводить, с сохранёнными значениями. Подразделение — путь через «/», показатель — название.
 */
export function templateCsv({ period, indicators = [], units = [], values = [] }) {
  const saved = entryOriginal(values)
  const lines = [IMPORT_COLUMNS.join(';')]
  for (const unit of units) {
    for (const ind of indicators) {
      if (!canEnterCell(ind, unit)) continue
      const v = saved.get(entryKey(ind.id, unit.id))
      lines.push([unit.path || unit.name, ind.name, period, v?.value, v?.target, v?.comment].map(csvCell).join(';'))
    }
  }
  return `\ufeff${lines.join('\r\n')}\r\n`
}

/** Состояние ячейки в плане словами: «96 · цель 100 · «комментарий»». */
export function cellStateText(state, unit = '') {
  if (!state) return '—'
  const parts = []
  parts.push(isNil(state.value) ? '—' : formatNumber(state.value, { unit }))
  if (!isNil(state.target)) parts.push(`цель ${formatNumber(state.target, { unit })}`)
  if (state.comment) parts.push(`«${state.comment}»`)
  return parts.join(' · ')
}
