/**
 * Per-chart appearance overrides stored in the dashboard preferences JSON.
 *
 * A settings object is `{ type, colors, legend, legendPos, height }`; every field
 * is optional and an absent field means "keep whatever the chart already does".
 */

export const CHART_TYPES = [
  { value: 'bar', label: 'Столбцы' },
  { value: 'line', label: 'Линии' },
  { value: 'pie', label: 'Круговая' },
  { value: 'doughnut', label: 'Кольцевая' },
]

export const LEGEND_POSITIONS = [
  { value: 'top', label: 'Сверху' },
  { value: 'bottom', label: 'Снизу' },
  { value: 'right', label: 'Справа' },
  { value: 'left', label: 'Слева' },
]

export const HEIGHT_MIN = 200
export const HEIGHT_MAX = 500

const CARTESIAN = new Set(['bar', 'line'])
const ROUND = new Set(['pie', 'doughnut'])

function legendBlock(pos) {
  const base = { type: 'scroll', textStyle: { fontSize: 9 }, itemWidth: 10, itemHeight: 10, itemGap: 8 }
  if (pos === 'right') return { ...base, orient: 'vertical', right: 0, top: 'center' }
  if (pos === 'left') return { ...base, orient: 'vertical', left: 0, top: 'center' }
  if (pos === 'top') return { ...base, orient: 'horizontal', top: 0 }
  return { ...base, orient: 'horizontal', bottom: 0 }
}

/** Whether the chart can be switched between the four types at all. */
export function isSwitchable(option) {
  const series = option?.series
  if (!Array.isArray(series) || !series.length) return false
  return series.every(s => CARTESIAN.has(s.type) || ROUND.has(s.type))
}

function convertSeries(s, type, hasAxis) {
  // Round charts carry no axis data, so a cartesian series is only convertible
  // when its data is a flat value list we can pair with the category axis.
  if (ROUND.has(type)) {
    if (ROUND.has(s.type)) {
      return { ...s, type: 'pie', radius: type === 'doughnut' ? ['45%', '70%'] : '68%' }
    }
    if (!hasAxis) return s
    return {
      name: s.name, type: 'pie',
      radius: type === 'doughnut' ? ['45%', '70%'] : '68%',
      center: ['50%', '50%'],
      label: { show: false },
      data: hasAxis.map((name, i) => ({ name, value: numeric(s.data?.[i]) })),
    }
  }
  if (ROUND.has(s.type)) {
    return { name: s.name, type, data: (s.data || []).map(d => numeric(d)) }
  }
  return { ...s, type, areaStyle: undefined, smooth: type === 'line' ? s.smooth : undefined }
}

function numeric(d) {
  if (d && typeof d === 'object') return d.value
  return d
}

function categories(option) {
  const ax = Array.isArray(option?.xAxis) ? option.xAxis[0] : option?.xAxis
  return Array.isArray(ax?.data) ? ax.data : null
}

/**
 * Returns a new option object with the chart's own overrides applied. ECharts
 * options hold formatter functions, so the clone is manual rather than
 * `structuredClone`.
 */
export function applyChartSettings(option, settings) {
  if (!option || !settings || !Object.keys(settings).length) return option
  const out = { ...option }
  const { type, colors, legend, legendPos } = settings

  if (type && isSwitchable(option)) {
    const cats = categories(option)
    out.series = option.series.map(s => convertSeries(s, type, cats))
    if (ROUND.has(type)) {
      out.xAxis = undefined
      out.yAxis = undefined
      out.grid = undefined
      out.dataZoom = undefined
    } else if (ROUND.has(option.series[0]?.type) && cats === null) {
      // Coming from a pie: rebuild a category axis out of the slice names.
      const names = (option.series[0].data || []).map(d => (d && typeof d === 'object' ? d.name : d))
      out.xAxis = { type: 'category', data: names, axisLabel: { fontSize: 9 } }
      out.yAxis = { type: 'value' }
    }
  }

  if (legend === false) {
    out.legend = { show: false }
  } else if (legendPos) {
    out.legend = { ...legendBlock(legendPos), show: true }
    if (legendPos === 'right' || legendPos === 'left') {
      // Vertical legends eat horizontal room, so give the plot area a matching inset.
      const side = legendPos === 'right' ? 'right' : 'left'
      out.grid = { ...(out.grid || {}), [side]: 96, bottom: 28 }
    }
  } else if (legend === true && out.legend?.show === false) {
    out.legend = { ...legendBlock('bottom'), show: true }
  }

  if (Array.isArray(colors) && colors.length) {
    out.color = colors
    // A hard-coded itemStyle colour beats the palette, so it has to go for the
    // picker to have any visible effect.
    out.series = (out.series || []).map(s => stripColors(s))
  }
  return out
}

function stripColors(s) {
  const out = { ...s }
  if (out.itemStyle) out.itemStyle = { ...out.itemStyle, color: undefined }
  if (out.lineStyle) out.lineStyle = { ...out.lineStyle, color: undefined }
  if (out.areaStyle) out.areaStyle = { ...out.areaStyle, color: undefined }
  if (Array.isArray(out.data)) {
    out.data = out.data.map(d => (d && typeof d === 'object' && d.itemStyle
      ? { ...d, itemStyle: { ...d.itemStyle, color: undefined } }
      : d))
  }
  return out
}

/** How many colour swatches the popover should offer for this chart. */
export function seriesColorCount(option) {
  const series = option?.series
  if (!Array.isArray(series) || !series.length) return 0
  const first = series[0]
  if (ROUND.has(first.type)) return Math.min(first.data?.length || 0, 8)
  return Math.min(series.length, 8)
}

export function chartHeightOf(settings, fallback) {
  const h = Number(settings?.height)
  if (!h) return fallback
  return Math.min(Math.max(h, HEIGHT_MIN), HEIGHT_MAX)
}
