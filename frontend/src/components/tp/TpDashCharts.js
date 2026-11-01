/**
 * Общие заготовки графиков дашборда и сравнения периодов ТП: цвета темы, оси недель,
 * подсказки с единицами, линии порогов светофора. Базовая тема ECharts подмешивается в EChart.vue.
 */
import { computed } from 'vue'
import { axisNumber, chartColors, cssVar, lightColor } from '@/components/charts/echarts'
import { useAppStore } from '@/stores/app'
import { usePaletteStore } from '@/stores/palette'
import { formatNumber } from '@/utils/format'

/**
 * Цвета текущей темы и палитры. Пересчитываются при смене темы или палитры,
 * поэтому графики, которые от них зависят, перерисовываются с новыми цветами.
 */
export function useChartTheme() {
  const app = useAppStore()
  const palette = usePaletteStore()
  return computed(() => {
    void app.resolvedTheme
    void palette.colors
    const series = chartColors()
    return {
      series,
      /** Цвет серии --chart-N (N с единицы). */
      c: (n) => series[(n - 1) % series.length],
      surface: cssVar('--surface', '#fff'),
      text: cssVar('--text', '#1c2130'),
      text2: cssVar('--text-2', '#4a5263'),
      muted: cssVar('--muted', '#7a8293'),
      border: cssVar('--border', '#e6e8ec'),
      light: (name) => lightColor(name),
    }
  })
}

export function fmtValue(value, unit = '', digits = 1) {
  return formatNumber(value, { digits, unit })
}

/** Ось недель: подписи не налезают друг на друга. */
export function weekAxis(labels, extra = {}) {
  return { type: 'category', data: labels, axisLabel: { hideOverlap: true }, ...extra }
}

export function valueAxis(extra = {}) {
  return { type: 'value', axisLabel: { formatter: (v) => axisNumber(v) }, ...extra }
}

/** Недель много — столбцы тоньше, без зазоров, а поток удобнее показывать линиями. */
export function isDense(count) {
  return count > 30
}

const ROW = 'display:flex;align-items:center;gap:6px;justify-content:space-between;min-width:180px;line-height:1.7'
const NAME = 'flex:1;color:inherit'

function line(marker, name, value) {
  return `<div style="${ROW}"><span style="${NAME}">${marker}${name}</span><b style="font-variant-numeric:tabular-nums">${value}</b></div>`
}

/**
 * Подсказка по оси: заголовок — неделя, строки серий со значениями и единицами.
 * units — единица по имени серии (если у серий разные), total — строка «Всего».
 */
export function axisTooltip({ unit = '', digits = 1, units = null, total = false } = {}) {
  return {
    trigger: 'axis',
    formatter: (params) => {
      const list = (Array.isArray(params) ? params : [params]).filter(Boolean)
      if (!list.length) return ''
      const head = `<div style="margin-bottom:4px;font-weight:600">${list[0].axisValueLabel ?? list[0].name}</div>`
      const rows = list.map((p) => line(p.marker, p.seriesName, fmtValue(p.value, units?.[p.seriesName] ?? unit, digits)))
      if (total && list.length > 1) {
        const sum = list.reduce((s, p) => s + (Number(p.value) || 0), 0)
        const any = list.some((p) => p.value !== null && p.value !== undefined)
        rows.push(`<div style="border-top:1px solid ${cssVar('--border')};margin-top:4px;padding-top:2px">${line('', 'Всего', any ? fmtValue(sum, unit, digits) : '—')}</div>`)
      }
      return head + rows.join('')
    },
  }
}

/**
 * Линии порогов светофора на недельном графике: «норма» — зелёный порог,
 * «критично» — за жёлтым порогом. fallback — линия, если правило не включено.
 */
export function thresholdMarkLine(rule, { unit = '', digits = 1, fallback = null } = {}) {
  const data = []
  const lower = rule?.direction === 'lower_is_better'
  const isSet = (v) => v !== null && v !== undefined
  if (rule?.enabled) {
    if (isSet(rule.green_threshold)) {
      data.push({ yAxis: Number(rule.green_threshold), lineStyle: { color: lightColor('green') },
        label: { formatter: `норма ${lower ? '≤' : '≥'} ${fmtValue(rule.green_threshold, unit, digits)}` } })
    }
    if (isSet(rule.yellow_threshold)) {
      data.push({ yAxis: Number(rule.yellow_threshold), lineStyle: { color: lightColor('red') },
        label: { formatter: `критично ${lower ? '>' : '<'} ${fmtValue(rule.yellow_threshold, unit, digits)}` } })
    }
  } else if (fallback) {
    data.push({ yAxis: fallback.value, lineStyle: { color: cssVar('--faint') }, label: { formatter: fallback.label } })
  }
  if (!data.length) return undefined
  return {
    symbol: 'none', silent: true, animation: false,
    lineStyle: { type: [4, 4], width: 1 },
    label: { position: 'insideEndTop', color: cssVar('--muted'), fontSize: 11, backgroundColor: cssVar('--surface'), padding: [1, 4], borderRadius: 3 },
    data,
  }
}

/** Линия недельного ряда: 2px, точки только при небольшом числе недель. */
export function lineSeries(name, data, color, { area = false, count = data.length, ...extra } = {}) {
  return {
    name, type: 'line', data, connectNulls: true, smooth: 0.25,
    showSymbol: count <= 26, symbol: 'circle', symbolSize: 7,
    lineStyle: { width: 2, color }, itemStyle: { color, borderColor: cssVar('--surface'), borderWidth: 1.5 },
    areaStyle: area ? { color, opacity: 0.08 } : undefined,
    emphasis: { focus: 'none' },
    ...extra,
  }
}

/** Столбцы недельного ряда; stack — для накопления (зазор цветом поверхности). */
export function barSeries(name, data, color, { stack = null, count = data.length, opacity = 1, ...extra } = {}) {
  const dense = isDense(count)
  return {
    name, type: 'bar', data, stack: stack || undefined,
    barMaxWidth: stack ? 22 : 14, barGap: '20%',
    itemStyle: stack
      ? { color, opacity, borderColor: cssVar('--surface'), borderWidth: dense ? 0 : 1 }
      : { color, opacity, borderRadius: [3, 3, 0, 0] },
    emphasis: { focus: 'none' },
    ...extra,
  }
}

/**
 * Слагаемое накопленного ряда: столбцы, а при большом числе недель — накопленные области
 * (сотня узких столбцов читается хуже, чем сплошная форма).
 */
export function stackSeries(name, data, color, { stack, count = data.length, opacity = 1, ...extra } = {}) {
  if (!isDense(count)) return barSeries(name, data, color, { stack, count, opacity, ...extra })
  return {
    name, type: 'line', data, stack, symbol: 'circle', showSymbol: false, symbolSize: 6, smooth: false,
    lineStyle: { width: 1, color, opacity }, itemStyle: { color, opacity },
    areaStyle: { color, opacity: 0.82 * opacity },
    emphasis: { focus: 'none' },
    ...extra,
  }
}

/**
 * Кольцевая диаграмма с итогом в центре. items: [{ name, value, color }].
 * narrow — легенда под кольцом (узкая карточка), иначе справа: имя и доля.
 */
export function donutOption(items, { unit = '', total = null, totalLabel = '', theme, narrow = false }) {
  const sum = items.reduce((s, x) => s + (x.value || 0), 0)
  const share = Object.fromEntries(items.map((x) => [x.name, sum > 0 ? (x.value / sum) * 100 : 0]))
  const pct = (name) => `${formatNumber(share[name] ?? 0, { digits: 1 })}%`
  const cx = narrow ? '50%' : '28%'
  const cy = narrow ? '40%' : '50%'
  return {
    // Базовая тема задаёт оси — у кольца их быть не должно.
    xAxis: { show: false },
    yAxis: { show: false },
    tooltip: {
      trigger: 'item',
      formatter: (p) => `${p.marker}${p.name}<br><b style="font-variant-numeric:tabular-nums">${fmtValue(p.value, unit, 1)}</b> · ${formatNumber(p.percent, { digits: 1 })}%`,
    },
    legend: narrow
      ? { orient: 'horizontal', left: 'center', top: 'auto', bottom: 0, itemGap: 12, formatter: (name) => `${name} {v|${pct(name)}}`,
          textStyle: { rich: { v: { color: theme.text, fontWeight: 600, fontSize: 12 } } } }
      : { orient: 'vertical', left: '58%', top: 'middle', itemGap: 10,
          formatter: (name) => `{n|${name}}{v|${pct(name)}}`,
          textStyle: { rich: { n: { width: 150, overflow: 'truncate', ellipsis: '…', color: theme.text2, fontSize: 12 }, v: { width: 44, align: 'right', color: theme.text, fontSize: 12, fontWeight: 600 } } } },
    title: total === null ? undefined : {
      text: total, subtext: totalLabel, left: cx, top: narrow ? '31%' : '41%', textAlign: 'center', itemGap: 2,
      textStyle: { fontSize: 18, fontWeight: 650, color: theme.text },
      subtextStyle: { fontSize: 11, color: theme.muted },
    },
    series: [{
      type: 'pie', radius: narrow ? ['44%', '64%'] : ['56%', '80%'], center: [cx, cy], avoidLabelOverlap: true,
      label: { show: false }, labelLine: { show: false },
      itemStyle: { borderColor: theme.surface, borderWidth: 2, borderRadius: 4 },
      emphasis: { scale: true, scaleSize: 4 },
      data: items.map((x) => ({ name: x.name, value: x.value, itemStyle: { color: x.color } })),
    }],
  }
}
