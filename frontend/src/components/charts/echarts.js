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

echarts.use([BarChart, LineChart, PieChart, ScatterChart, DatasetComponent, GridComponent, LegendComponent,
  MarkLineComponent, TitleComponent, TooltipComponent, CanvasRenderer])

export { echarts }

export function cssVar(name, fallback = '') {
  if (typeof document === 'undefined') return fallback
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback
}

export function chartColors() {
  return [1, 2, 3, 4, 5, 6, 7].map((i) => cssVar(`--chart-${i}`))
}

export function lightColor(light) {
  return cssVar(`--light-${light || 'gray'}`)
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
      trigger: 'axis', confine: true, backgroundColor: surface, borderColor: border, borderWidth: 1,
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

/** Подпись числа на осях и в подсказках. */
export function axisNumber(value) {
  if (Math.abs(value) >= 10000) return `${(value / 1000).toLocaleString('ru-RU', { maximumFractionDigits: 1 })} тыс.`
  return Number(value).toLocaleString('ru-RU', { maximumFractionDigits: 2 })
}
