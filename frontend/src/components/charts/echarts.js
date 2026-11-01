/**
 * ECharts с нужными модулями (tree-shaking) и общая тема: шрифт, цвета осей и подсказок
 * берутся из CSS-токенов текущей темы, серии — из активной палитры.
 */
import * as echarts from 'echarts/core'
import { BarChart, LineChart, PieChart, ScatterChart } from 'echarts/charts'
import {
  DatasetComponent, GridComponent, LegendComponent, MarkLineComponent, TitleComponent, TooltipComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { FALLBACK, usePaletteStore } from '@/stores/palette'
import { formatNumber } from '@/utils/format'

echarts.use([BarChart, LineChart, PieChart, ScatterChart, DatasetComponent, GridComponent, LegendComponent,
  MarkLineComponent, TitleComponent, TooltipComponent, CanvasRenderer])

export { echarts }

export function cssVar(name, fallback = '') {
  if (typeof document === 'undefined') return fallback
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback
}

/**
 * Палитра читается из хранилища (Pinia), а не из CSS: вычисляемые опции графиков, которые
 * вызывают эти функции, зависят от палитры и пересчитываются сразу при её смене.
 */
function activePalette() {
  try {
    return usePaletteStore().colors || FALLBACK
  } catch {
    return FALLBACK // вне приложения (тесты) хранилище не подключено
  }
}

export function chartColors() {
  const charts = activePalette().charts
  return (charts?.length ? charts : FALLBACK.charts).slice(0, 7)
}

export function lightColor(light) {
  const lights = { ...FALLBACK.traffic_light, ...(activePalette().traffic_light || {}) }
  return lights[!light || light === 'gray' ? 'neutral' : light] || lights.neutral
}

/**
 * Подписи числовых осей без своего формата — в ru-RU («1 234», «2,5»): по умолчанию ECharts пишет
 * «1,234» с английской запятой. Категориальные оси (недели, годы, названия) не меняются.
 */
export function ruAxisLabels(option) {
  if (!option) return option
  const fix = (axis) => {
    if (!axis || (axis.type !== 'value' && axis.type !== 'log') || axis.axisLabel?.formatter) return axis
    return { ...axis, axisLabel: { ...axis.axisLabel, formatter: (v) => axisNumber(v) } }
  }
  const out = { ...option }
  for (const key of ['xAxis', 'yAxis']) {
    if (Array.isArray(option[key])) out[key] = option[key].map(fix)
    else if (option[key]) out[key] = fix(option[key])
  }
  return out
}

/** Значение в подсказке по умолчанию: ru-RU, пустое — прочерк. */
export function tooltipValue(value) {
  if (Array.isArray(value)) return value.map(tooltipValue).join(', ')
  if (value === null || value === undefined || value === '' || value === '-') return '—'
  return typeof value === 'number' ? formatNumber(value) : value
}

/** Базовые настройки, общие для всех графиков. */
export function baseOption() {
  const text = cssVar('--text-2', '#4a5263')
  const muted = cssVar('--muted', '#7a8293')
  const border = cssVar('--border', '#e6e8ec')
  const surface = cssVar('--bg-elevated', '#fff')
  return {
    color: chartColors(),
    textStyle: { fontFamily: cssVar('--font-sans'), color: text, fontSize: 12 },
    grid: { left: 8, right: 16, top: 28, bottom: 8, containLabel: true },
    legend: { top: 0, left: 0, icon: 'roundRect', itemWidth: 10, itemHeight: 10, itemGap: 16, textStyle: { color: text, fontSize: 12 } },
    tooltip: {
      trigger: 'axis', confine: true, backgroundColor: surface, borderColor: border, borderWidth: 1, valueFormatter: tooltipValue,
      padding: [8, 12], textStyle: { color: cssVar('--text'), fontSize: 12 },
      extraCssText: 'box-shadow: 0 8px 24px rgba(0,0,0,.12); border-radius: 10px;',
      axisPointer: { type: 'line', lineStyle: { color: border } },
    },
    xAxis: { axisLine: { lineStyle: { color: border } }, axisTick: { show: false }, axisLabel: { color: muted, fontSize: 11 }, splitLine: { show: false } },
    yAxis: { axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: muted, fontSize: 11 }, splitLine: { lineStyle: { color: border, type: [3, 3] } } },
  }
}

const isObject = (v) => v && typeof v === 'object' && !Array.isArray(v)

export function mergeOption(base, extra) {
  const out = { ...base }
  for (const [key, value] of Object.entries(extra || {})) {
    if (Array.isArray(value) && (key === 'xAxis' || key === 'yAxis') && isObject(base[key])) {
      out[key] = value.map((axis) => mergeOption(base[key], axis))
    } else if (isObject(value) && isObject(base[key])) {
      out[key] = mergeOption(base[key], value)
    } else {
      out[key] = value
    }
  }
  return out
}

/**
 * «Круглая» граница оси за значением x: 1, 1,2, 1,5, 2, 2,5, 3, 4, 5, 6, 8 × 10ⁿ.
 * direction 'up' — не меньше x, 'down' — не больше x.
 */
export function niceBound(x, direction = 'up') {
  if (!Number.isFinite(x) || x === 0) return 0
  const sign = Math.sign(x)
  const abs = Math.abs(x)
  const away = direction === 'up' ? sign > 0 : sign < 0
  const power = 10 ** Math.floor(Math.log10(abs))
  const m = abs / power
  const steps = [1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]
  const pick = away ? steps.find((v) => v >= m - 1e-9) : [...steps].reverse().find((v) => v <= m + 1e-9)
  return Number((sign * pick * power).toPrecision(12))
}

/** Горизонтальные линии (цели, пороги светофора, средние) по осям Y: Map(номер оси → значения). */
export function markLineValues(series) {
  const out = new Map()
  for (const s of [].concat(series || [])) {
    for (const d of s?.markLine?.data || []) {
      if (!d || Array.isArray(d) || d.yAxis === null || d.yAxis === undefined) continue
      const v = Number(d.yAxis)
      if (!Number.isFinite(v)) continue
      const axis = s.yAxisIndex || 0
      out.set(axis, [...(out.get(axis) || []), v])
    }
  }
  return out
}

/**
 * Линия цели или порога всегда видна: если она выше максимума данных (ниже минимума оси),
 * граница оси раздвигается до «круглого» значения за линией с небольшим запасом под подпись.
 * Явно заданные min / max оси не меняются.
 */
export function fitMarkLines(option) {
  if (!option?.yAxis) return option
  const marks = markLineValues(option.series)
  if (!marks.size) return option
  const axes = [].concat(option.yAxis)
  const fitted = axes.map((axis, i) => {
    const values = marks.get(i)
    if (!values || !axis || axis.type === 'category') return axis
    const hi = Math.max(...values)
    const lo = Math.min(...values)
    const out = { ...axis }
    if (axis.max === undefined) out.max = (v) => (hi > v.max ? niceBound(hi + Math.abs(hi) * 0.08, 'up') : null)
    if (axis.min === undefined) out.min = (v) => (lo < v.min && (axis.scale || lo < 0) ? niceBound(lo - Math.abs(lo) * 0.08, 'down') : null)
    return out
  })
  return { ...option, yAxis: Array.isArray(option.yAxis) ? fitted : fitted[0] }
}

/**
 * Точки линий — сплошные, с обводкой цветом поверхности. Пустые кружки ECharts по умолчанию
 * залиты белым и в тёмной теме светятся белыми пятнами.
 */
export function solidSymbols(option, surface) {
  if (!option?.series) return option
  const series = [].concat(option.series).map((s) => {
    if (!s || s.type !== 'line' || (s.symbol !== undefined && s.symbol !== 'emptyCircle')) return s
    return { ...s, symbol: 'circle', itemStyle: { borderColor: surface, borderWidth: 1.5, ...s.itemStyle } }
  })
  return { ...option, series: Array.isArray(option.series) ? series : series[0] }
}

/** Подпись числа на осях и в подсказках. */
export function axisNumber(value) {
  if (Math.abs(value) >= 10000) return `${(value / 1000).toLocaleString('ru-RU', { maximumFractionDigits: 1 })} тыс.`
  return Number(value).toLocaleString('ru-RU', { maximumFractionDigits: 2 })
}
