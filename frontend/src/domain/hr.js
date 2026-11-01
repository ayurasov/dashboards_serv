/** Служба персонала: подготовка данных дашборда (чистые функции — покрыты тестами). */

export const KEY_METRICS = ['turnover', 'turnover_company', 'avg_time_to_fill', 'offers_accepted_pct',
  'probation_pass_rate', 'probation_pass_rate_adaptation', 'adaptation_dismissals']

/**
 * Короткие подписи карточек ключевых показателей. Полные названия обрезаются на второй строке
 * одинаково («Прохождение испытательного срока…» у общего и у адаптационного) — карточки не различить.
 * Полное название остаётся в подсказке карточки.
 */
export const KPI_SHORT_LABELS = {
  avg_time_to_fill: 'Время закрытия позиции',
  probation_pass_rate: 'Испытательный срок пройден, всего',
  probation_pass_rate_adaptation: 'Испытательный срок пройден, адаптация',
}

export function kpiLabel(metric) {
  return KPI_SHORT_LABELS[metric?.key] || metric?.label || ''
}

/** Подсказка карточки: полное название метрики и её описание. */
export function kpiHint(metric) {
  return [metric?.label, metric?.description].filter(Boolean).filter((v, i, a) => a.indexOf(v) === i).join(' — ')
}

export const FUNNEL = [
  { key: 'resumes_screened', label: 'Отобрано резюме' },
  { key: 'interviews_hr', label: 'Интервью с HR' },
  { key: 'interviews_hm', label: 'Интервью с заказчиком' },
  { key: 'hired_count', label: 'Нанято' },
]

/** Быстрые периоды: последние N месяцев с данными. */
export const QUICK_PERIODS = [
  { value: 1, label: 'Последний месяц' },
  { value: 3, label: '3 месяца' },
  { value: 6, label: '6 месяцев' },
  { value: 12, label: '12 месяцев' },
  { value: 0, label: 'Все' },
]

export function lastMonths(allKeys, count) {
  if (!count) return [...allKeys]
  return allKeys.slice(-count)
}

export function metricMap(series) {
  return Object.fromEntries((series?.metrics || []).map((m) => [m.key, m]))
}

/** Значения одной метрики по месяцам выборки — для графиков. */
export function metricSeries(series, key) {
  return series.map((s) => s.metrics.find((m) => m.key === key)?.value ?? null)
}

export function groupByCategory(metrics) {
  const groups = []
  for (const m of metrics) {
    let g = groups.find((x) => x.key === m.category)
    if (!g) {
      g = { key: m.category, label: m.category_label, items: [] }
      groups.push(g)
    }
    g.items.push(m)
  }
  return groups
}

/** Доля конверсии воронки к первому шагу, %. */
export function funnelSteps(latest) {
  const map = metricMap(latest)
  const first = map[FUNNEL[0].key]?.value
  return FUNNEL.map((step) => {
    const value = map[step.key]?.value ?? null
    return { ...step, value, share: first && value !== null ? Math.round((value / first) * 1000) / 10 : null }
  })
}
