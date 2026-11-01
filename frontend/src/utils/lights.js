/** Светофор: подписи, цвета и оценка значения по правилу (та же логика, что на сервере). */

export const LIGHT_LABELS = { green: 'Норма', yellow: 'Внимание', red: 'Критично', gray: 'Нет оценки' }
/** Показатель со включённым правилом не заполнен: светофор — «Нет данных», а пропуск — критичное нарушение. */
export const MISSING_LABEL = 'Нет данных'
export const MISSING_HINT = 'Показатель со светофором не заполнен — критичное нарушение полноты данных'

export function lightLabel(light, missing = false) {
  return missing ? MISSING_LABEL : LIGHT_LABELS[light || 'gray']
}
export const LIGHT_ORDER = { red: 0, yellow: 1, green: 2, gray: 3 }
export const DIRECTION_LABELS = { lower_is_better: 'Меньше — лучше', higher_is_better: 'Больше — лучше', neutral: 'Без оценки' }

export function lightVar(light) {
  return `var(--light-${light || 'gray'})`
}

/** rule: { direction, green_threshold, yellow_threshold, enabled }; scale — множитель порогов (суммы за N недель). */
export function evaluate(value, rule, scale = 1) {
  if (value === null || value === undefined || !rule || !rule.enabled) return 'gray'
  const g = rule.green_threshold ?? rule.green
  const y = rule.yellow_threshold ?? rule.yellow
  if (g === null || g === undefined) {
    if (y === null || y === undefined) return 'gray'
  }
  const green = g === null || g === undefined ? null : Number(g) * scale
  const yellow = y === null || y === undefined ? null : Number(y) * scale
  if (rule.direction === 'lower_is_better') {
    if (green !== null && value <= green) return 'green'
    if (yellow !== null && value <= yellow) return 'yellow'
    return 'red'
  }
  if (green !== null && value >= green) return 'green'
  if (yellow !== null && value >= yellow) return 'yellow'
  return 'red'
}

export function worst(lights) {
  const rated = lights.filter((l) => l && l !== 'gray')
  if (!rated.length) return 'gray'
  return rated.reduce((a, b) => (LIGHT_ORDER[a] <= LIGHT_ORDER[b] ? a : b))
}

export function countLights(lights) {
  const out = { green: 0, yellow: 0, red: 0, gray: 0 }
  for (const l of lights) out[l || 'gray'] += 1
  return out
}
