/** Цели и бенчмарки службы персонала: статусы, группировка, шкала выполнения, форма (чистые функции — покрыты тестами). */
import { parseNumber } from './hrDataEntry'

export const TARGET_STATUS_LABELS = { green: 'Цель достигнута', yellow: 'Близко к цели', red: 'Цель не достигнута', gray: 'Нет оценки' }

/** Подпись статуса с учётом справочных строк и строк без факта. */
export function statusLabel(row) {
  if (row.target_value === null || row.target_value === undefined) return 'Справочно'
  if (row.current_value === null || row.current_value === undefined) return 'Нет данных'
  return TARGET_STATUS_LABELS[row.status] || TARGET_STATUS_LABELS.gray
}

/** Строки по годам (новые сверху) со счётчиками статусов. */
export function groupByYear(rows) {
  const years = new Map()
  for (const row of rows || []) {
    if (!years.has(row.year)) years.set(row.year, [])
    years.get(row.year).push(row)
  }
  return [...years.entries()].sort((a, b) => b[0] - a[0]).map(([year, items]) => {
    const counts = { green: 0, yellow: 0, red: 0, gray: 0 }
    for (const r of items) counts[r.status || 'gray'] += 1
    const withTarget = items.filter((r) => r.target_value !== null && r.target_value !== undefined).length
    return { year, items, counts, withTarget }
  })
}

const isNum = (v) => v !== null && v !== undefined && Number.isFinite(Number(v))

/**
 * Позиции на общей шкале от нуля (доли 0–1) для полосы выполнения: факт, цель, справочное значение
 * и зона, где цель выполнена (для «меньше — лучше» — левее цели, для «больше — лучше» — правее).
 */
export function bulletScale(row) {
  const values = [row.current_value, row.target_value, row.reference_value].filter(isNum).map((v) => Math.abs(Number(v)))
  if (!values.length) return null
  const max = Math.max(...values) * 1.15 || 1
  const pos = (v) => (isNum(v) ? Math.min(1, Math.max(0, Number(v) / max)) : null)
  const target = pos(row.target_value)
  let zone = null
  if (target !== null) zone = row.direction === 'lower_is_better' ? { from: 0, to: target } : { from: target, to: 1 }
  return { current: pos(row.current_value), target, reference: pos(row.reference_value), zone }
}

/** Метрики, для которых на год ещё можно задать цель (по одной цели на метрику и год). */
export function availableMetrics(definitions, rows, year, keepKey = '') {
  const used = new Set((rows || []).filter((r) => r.year === Number(year)).map((r) => r.metric_key))
  return (definitions || []).filter((d) => d.key === keepKey || !used.has(d.key))
}

export function emptyTargetForm(year) {
  return { metric_key: '', year, target_value: '', reference_value: '', label: '', description: '', source: '' }
}

export function targetToForm(row) {
  const text = (v) => (isNum(v) ? String(v).replace('.', ',') : '')
  return {
    metric_key: row.metric_key, year: row.year, target_value: text(row.target_value), reference_value: text(row.reference_value),
    label: row.label || '', description: row.description || '', source: row.source || '',
  }
}

/**
 * Проверка и тело запроса формы цели. При изменении (editing) метрика и год не отправляются —
 * сервер их не меняет. Возвращает { body, errors }.
 */
export function targetPayload(form, { editing = false } = {}) {
  const errors = {}
  const target = parseNumber(form.target_value)
  const reference = parseNumber(form.reference_value)
  if (target.error) errors.target_value = target.error
  if (reference.error) errors.reference_value = reference.error
  if (!editing) {
    if (!form.metric_key) errors.metric_key = 'Выберите метрику'
    const year = Number(form.year)
    if (!Number.isInteger(year) || year < 2000 || year > 2100) errors.year = 'Год от 2000 до 2100'
  }
  if (!errors.target_value && !errors.reference_value && target.value === null && reference.value === null) {
    errors.target_value = 'Укажите цель или справочное значение'
  }
  const body = {
    target_value: target.value ?? null,
    reference_value: reference.value ?? null,
    label: form.label.trim(),
    description: form.description.trim(),
    source: form.source.trim(),
  }
  if (!editing) Object.assign(body, { metric_key: form.metric_key, year: Number(form.year) })
  return { body, errors }
}
