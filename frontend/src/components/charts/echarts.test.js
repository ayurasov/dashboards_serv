import { describe, expect, it } from 'vitest'
import { fitMarkLines, markLineValues, niceBound, ruAxisLabels, solidSymbols, tooltipValue } from './echarts'

describe('niceBound — «круглая» граница оси', () => {
  it('вверх и вниз для положительных и отрицательных значений', () => {
    expect(niceBound(5.4, 'up')).toBe(6)
    expect(niceBound(3.87, 'up')).toBe(4)
    expect(niceBound(420, 'up')).toBe(500)
    expect(niceBound(0.55, 'up')).toBe(0.6)
    expect(niceBound(5, 'up')).toBe(5)
    expect(niceBound(37, 'down')).toBe(30)
    expect(niceBound(-3.2, 'down')).toBe(-4)
    expect(niceBound(-3.2, 'up')).toBe(-3)
    expect(niceBound(0)).toBe(0)
    expect(niceBound(Number.NaN)).toBe(0)
  })
})

describe('линии целей и порогов на графиках', () => {
  const option = (marks, yAxis = { type: 'value' }) => ({
    yAxis,
    series: [{ type: 'line', data: [1.3, 2.6, 3.87, 2], markLine: { data: marks.map((v) => ({ yAxis: v })) } }],
  })

  it('markLineValues собирает горизонтальные линии по осям', () => {
    const values = markLineValues([
      { markLine: { data: [{ yAxis: 5 }, { yAxis: null }, [{ coord: [0, 1] }, { coord: [1, 2] }]] } },
      { yAxisIndex: 1, markLine: { data: [{ yAxis: '420' }] } },
      { data: [] },
    ])
    expect(values.get(0)).toEqual([5])
    expect(values.get(1)).toEqual([420])
  })

  it('цель выше данных раздвигает ось до круглого значения за ней', () => {
    const fitted = fitMarkLines(option([5]))
    expect(fitted.yAxis.max({ min: 1.3, max: 3.87 })).toBe(6)
    // Цель внутри диапазона — ось как обычно
    expect(fitted.yAxis.max({ min: 1.3, max: 7 })).toBe(null)
    // Ось с нуля не трогается снизу, если линия неотрицательна
    expect(fitted.yAxis.min({ min: 1.3, max: 3.87 })).toBe(null)
  })

  it('порог ниже данных виден на оси с масштабом от данных и при отрицательной линии', () => {
    expect(fitMarkLines(option([30], { type: 'value', scale: true })).yAxis.min({ min: 50, max: 90 })).toBe(25)
    expect(fitMarkLines(option([-2])).yAxis.min({ min: 1, max: 3 })).toBe(-2.5)
  })

  it('явные границы, категориальные оси и графики без линий не меняются', () => {
    const fixed = option([5], { type: 'value', max: 10 })
    expect(fitMarkLines(fixed).yAxis.max).toBe(10)
    const category = option([5], { type: 'category' })
    expect(fitMarkLines(category).yAxis).toEqual({ type: 'category' })
    const plain = { yAxis: { type: 'value' }, series: [{ type: 'bar', data: [1] }] }
    expect(fitMarkLines(plain)).toBe(plain)
  })

  it('несколько осей: раздвигается только ось с линией', () => {
    const multi = { yAxis: [{ type: 'value' }, { type: 'value' }], series: [{ yAxisIndex: 1, markLine: { data: [{ yAxis: 100 }] } }] }
    const fitted = fitMarkLines(multi)
    expect(fitted.yAxis[0]).toEqual({ type: 'value' })
    expect(fitted.yAxis[1].max({ min: 0, max: 50 })).toBe(120)
  })
})

describe('solidSymbols — точки линий в тёмной теме', () => {
  it('пустые кружки по умолчанию заменяются сплошными с обводкой цветом поверхности', () => {
    const out = solidSymbols({ series: [
      { type: 'line', data: [1] },
      { type: 'line', symbol: 'emptyCircle', itemStyle: { color: '#f00' } },
      { type: 'line', symbol: 'none' },
      { type: 'bar', data: [1] },
    ] }, '#161a22')
    expect(out.series[0]).toMatchObject({ symbol: 'circle', itemStyle: { borderColor: '#161a22', borderWidth: 1.5 } })
    expect(out.series[1].itemStyle).toEqual({ borderColor: '#161a22', borderWidth: 1.5, color: '#f00' })
    expect(out.series[2].symbol).toBe('none')
    expect(out.series[3]).toEqual({ type: 'bar', data: [1] })
  })
  it('без серий — без изменений', () => {
    const option = { title: { text: 'x' } }
    expect(solidSymbols(option, '#fff')).toBe(option)
  })
})

describe('подписи осей и подсказок в ru-RU', () => {
  it('ruAxisLabels: числовые оси без формата — ru-RU, категориальные и со своим форматом не меняются', () => {
    const custom = (v) => `${v}%`
    const out = ruAxisLabels({
      xAxis: { type: 'category', data: [2025, 2026] },
      yAxis: [{ type: 'value' }, { type: 'value', axisLabel: { formatter: custom, color: '#000' } }, { type: 'log', axisLabel: { color: '#111' } }],
    })
    expect(out.xAxis).toEqual({ type: 'category', data: [2025, 2026] })
    expect(out.yAxis[0].axisLabel.formatter(1234.5)).toBe('1 234,5')
    expect(out.yAxis[0].axisLabel.formatter(12500)).toBe('12,5 тыс.')
    expect(out.yAxis[1].axisLabel.formatter).toBe(custom)
    expect(out.yAxis[2].axisLabel).toMatchObject({ color: '#111' })
    expect(out.yAxis[2].axisLabel.formatter(0.5)).toBe('0,5')
  })
  it('tooltipValue: числа в ru-RU, пусто — прочерк', () => {
    expect(tooltipValue(1234.567)).toBe('1 234,57')
    expect(tooltipValue(-2)).toBe('−2')
    expect(tooltipValue(null)).toBe('—')
    expect(tooltipValue('-')).toBe('—')
    expect(tooltipValue([1.5, 2])).toBe('1,5, 2')
    expect(tooltipValue('Июль')).toBe('Июль')
  })
})
