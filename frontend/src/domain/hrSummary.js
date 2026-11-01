/** Сводка службы персонала по периодам: таблица, диапазон, графики (чистые функции — покрыты тестами). */
import { MONTHS_SHORT } from '@/utils/format'

export const PERIOD_TYPES = [
  { value: 'month', label: 'Месяц' },
  { value: 'quarter', label: 'Квартал' },
  { value: 'half', label: 'Полугодие' },
  { value: 'year', label: 'Год' },
]

/** Сколько месяцев в полном периоде. */
export const PERIOD_LENGTH = { month: 1, quarter: 3, half: 6, year: 12 }

/** Категории метрик — те же подписи, что на сервере (services/registry.py). */
export const CATEGORY_LABELS = { headcount: 'Численность', hiring: 'Подбор', adaptation: 'Адаптация', turnover: 'Текучесть' }

/** Как метрика сводится за период (поле aggregation определения метрики). */
export const AGGREGATION_LABELS = {
  sum: 'сумма за период',
  avg: 'среднее за период',
  latest: 'на конец периода',
  max: 'максимум за период',
}

/** Движение персонала — строки сводки, которые считаются по реестру, а не по метрикам. */
export const FLOW_ROWS = [
  { key: 'hired', label: 'Принято', unit: 'чел.', direction: 'higher_is_better', aggregation: 'sum', flow: true, description: 'Приёмы по реестру за период' },
  { key: 'fired', label: 'Уволено', unit: 'чел.', direction: 'lower_is_better', aggregation: 'sum', flow: true, description: 'Увольнения по реестру за период' },
  { key: 'net', label: 'Чистый прирост', unit: 'чел.', direction: 'higher_is_better', aggregation: 'sum', flow: true, description: 'Принято минус уволено' },
]
const FLOW_KEYS = new Set(FLOW_ROWS.map((r) => r.key))

/** Метрики в карточках итогов периода. */
export const SUMMARY_KPIS = ['turnover', 'avg_time_to_fill', 'offers_accepted_pct', 'probation_pass_rate']

export function isFlowKey(key) {
  return FLOW_KEYS.has(key)
}

/**
 * Периоды с «с» по «по» включительно (ключи периодов). Пустая или неизвестная граница — без ограничения;
 * перевёрнутый диапазон выравнивается.
 */
export function sliceRange(periods, from, to) {
  if (!periods?.length) return []
  let lo = from ? periods.findIndex((p) => p.key === from) : 0
  let hi = to ? periods.findIndex((p) => p.key === to) : periods.length - 1
  if (lo < 0) lo = 0
  if (hi < 0) hi = periods.length - 1
  if (lo > hi) [lo, hi] = [hi, lo]
  return periods.slice(lo, hi + 1)
}

/** Границы после того, как пользователь сдвинул одну из них: вторая подтягивается, чтобы диапазон не перевернулся. */
export function alignRange(periods, from, to, edited) {
  const lo = periods.findIndex((p) => p.key === from)
  const hi = periods.findIndex((p) => p.key === to)
  if (lo >= 0 && hi >= 0 && lo > hi) return edited === 'from' ? { from, to: from } : { from: to, to }
  return { from, to }
}

/** Значение строки сводки в периоде: метрика или движение персонала. */
export function periodValue(period, key) {
  if (!period) return null
  const value = isFlowKey(key) ? period[key] : period.metrics?.[key]
  return value === undefined ? null : value
}

export function periodLight(period, key) {
  if (!period || isFlowKey(key)) return ''
  return period.lights?.[key] || 'gray'
}

/** Значения строки по периодам — для графика. */
export function rowSeries(periods, key) {
  return (periods || []).map((p) => periodValue(p, key))
}

/** Изменение к предыдущему периоду диапазона (null, если сравнивать не с чем). */
export function periodDelta(periods, index, key) {
  if (!periods || index <= 0 || index >= periods.length) return null
  const now = periodValue(periods[index], key)
  const prev = periodValue(periods[index - 1], key)
  if (now === null || prev === null) return null
  return Math.round((now - prev) * 10000) / 10000
}

/** Индекс периода «в фокусе»: выбранный ключ, иначе последний в диапазоне. */
export function focusIndex(periods, key) {
  const index = (periods || []).findIndex((p) => p.key === key)
  return index >= 0 ? index : (periods?.length || 0) - 1
}

/** Строки таблицы: сначала движение персонала, затем метрики по категориям в порядке sort_order. */
export function summaryGroups(definitions) {
  const groups = [{ key: 'flow', label: 'Движение персонала', items: FLOW_ROWS }]
  const sorted = [...(definitions || [])].sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0))
  for (const d of sorted) {
    let group = groups.find((g) => g.key === d.category)
    if (!group) {
      group = { key: d.category, label: CATEGORY_LABELS[d.category] || d.category, items: [] }
      groups.push(group)
    }
    group.items.push(d)
  }
  return groups
}

/** Определение строки по ключу: метрика или движение персонала. */
export function rowDefinition(definitions, key) {
  return FLOW_ROWS.find((r) => r.key === key) || (definitions || []).find((d) => d.key === key) || null
}

/** Неполный период: месяцев с данными меньше, чем в периоде (суммы за него ещё растут). */
export function isPartial(period, type) {
  return !!period && period.months_count < (PERIOD_LENGTH[type] || 1)
}

/** Подпись периода для оси графика — короче полной. */
export function shortLabel(period, type) {
  if (!period) return ''
  const yy = String(period.year).slice(2)
  if (type === 'month') return `${MONTHS_SHORT[period.index - 1]} ${yy}`
  if (type === 'quarter') return `${period.index} кв. ${yy}`
  if (type === 'half') return `${period.index === 1 ? 'I' : 'II'} пол. ${yy}`
  return String(period.year)
}

/** Подпись под заголовком столбца: сколько месяцев вошло в период. */
export function monthsCaption(period, type) {
  if (!period) return ''
  const full = PERIOD_LENGTH[type] || 1
  if (full === 1) return ''
  return period.months_count < full ? `${period.months_count} из ${full} мес.` : `${full} мес.`
}

/** Текст диапазона для заголовка: «1 кв. 2026 — 3 кв. 2026». */
export function rangeText(periods) {
  if (!periods?.length) return ''
  const first = periods[0].label
  const last = periods[periods.length - 1].label
  return first === last ? first : `${first} — ${last}`
}

/** Сумма оценок светофора по периодам диапазона. */
export function lightTotals(periods) {
  const out = { green: 0, yellow: 0, red: 0, gray: 0 }
  for (const p of periods || []) {
    for (const light of Object.keys(out)) out[light] += p.light_counts?.[light] || 0
  }
  return out
}

/** Сводимые за период суммы удобнее показывать столбцами, уровни и средние — линией. */
export function chartKind(definition) {
  return definition?.aggregation === 'sum' ? 'bar' : 'line'
}
