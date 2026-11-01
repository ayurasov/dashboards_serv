import { describe, expect, it } from 'vitest'
import {
  FLOW_ROWS, alignRange, chartKind, focusIndex, isFlowKey, isPartial, lightTotals, monthsCaption, periodDelta,
  periodLight, periodValue, rangeText, rowDefinition, rowSeries, shortLabel, sliceRange, summaryGroups,
} from './hrSummary'

const period = (key, over = {}) => ({
  key, label: key, year: 2026, index: 1, months: [], months_count: 3, hired: 0, fired: 0, net: 0,
  metrics: {}, lights: {}, light_counts: { green: 0, yellow: 0, red: 0, gray: 0 }, ...over,
})

const PERIODS = [
  period('2026-Q1', { label: '1 кв. 2026', index: 1, hired: 9, fired: 10, net: -1, metrics: { turnover: 1.9, avg: 37.3333 }, lights: { turnover: 'green' }, light_counts: { green: 6, yellow: 1, red: 0, gray: 9 } }),
  period('2026-Q2', { label: '2 кв. 2026', index: 2, hired: 12, fired: 10, net: 2, metrics: { turnover: 2.4, avg: null }, lights: { turnover: 'yellow' }, light_counts: { green: 4, yellow: 2, red: 1, gray: 9 } }),
  period('2026-Q3', { label: '3 кв. 2026', index: 3, months_count: 2, hired: 4, fired: 3, net: 1, metrics: { turnover: 2 }, lights: {}, light_counts: { green: 5, yellow: 0, red: 2, gray: 9 } }),
]

describe('диапазон периодов', () => {
  it('sliceRange: без границ — все периоды', () => {
    expect(sliceRange(PERIODS, '', '').map((p) => p.key)).toEqual(['2026-Q1', '2026-Q2', '2026-Q3'])
  })
  it('sliceRange: границы включительно', () => {
    expect(sliceRange(PERIODS, '2026-Q2', '').map((p) => p.key)).toEqual(['2026-Q2', '2026-Q3'])
    expect(sliceRange(PERIODS, '', '2026-Q2').map((p) => p.key)).toEqual(['2026-Q1', '2026-Q2'])
    expect(sliceRange(PERIODS, '2026-Q2', '2026-Q2').map((p) => p.key)).toEqual(['2026-Q2'])
  })
  it('sliceRange: перевёрнутый диапазон выравнивается, неизвестная граница игнорируется', () => {
    expect(sliceRange(PERIODS, '2026-Q3', '2026-Q1').map((p) => p.key)).toEqual(['2026-Q1', '2026-Q2', '2026-Q3'])
    expect(sliceRange(PERIODS, '2025-H1', '2026-Q1').map((p) => p.key)).toEqual(['2026-Q1'])
  })
  it('sliceRange: пустой список', () => {
    expect(sliceRange([], 'x', 'y')).toEqual([])
    expect(sliceRange(null, '', '')).toEqual([])
  })
  it('alignRange: вторая граница подтягивается за сдвинутой', () => {
    expect(alignRange(PERIODS, '2026-Q3', '2026-Q1', 'from')).toEqual({ from: '2026-Q3', to: '2026-Q3' })
    expect(alignRange(PERIODS, '2026-Q3', '2026-Q1', 'to')).toEqual({ from: '2026-Q1', to: '2026-Q1' })
    expect(alignRange(PERIODS, '2026-Q1', '2026-Q2', 'from')).toEqual({ from: '2026-Q1', to: '2026-Q2' })
    expect(alignRange(PERIODS, '', '2026-Q2', 'to')).toEqual({ from: '', to: '2026-Q2' })
  })
  it('rangeText: один период или «с — по»', () => {
    expect(rangeText(PERIODS)).toBe('1 кв. 2026 — 3 кв. 2026')
    expect(rangeText(PERIODS.slice(1, 2))).toBe('2 кв. 2026')
    expect(rangeText([])).toBe('')
  })
})

describe('значения строк', () => {
  it('periodValue: метрики и движение персонала, пустые — null', () => {
    expect(periodValue(PERIODS[0], 'turnover')).toBe(1.9)
    expect(periodValue(PERIODS[0], 'hired')).toBe(9)
    expect(periodValue(PERIODS[0], 'net')).toBe(-1)
    expect(periodValue(PERIODS[1], 'avg')).toBeNull()
    expect(periodValue(PERIODS[2], 'unknown')).toBeNull()
    expect(periodValue(null, 'hired')).toBeNull()
  })
  it('periodLight: у движения персонала светофора нет, у метрики без оценки — серый', () => {
    expect(periodLight(PERIODS[0], 'turnover')).toBe('green')
    expect(periodLight(PERIODS[2], 'turnover')).toBe('gray')
    expect(periodLight(PERIODS[0], 'hired')).toBe('')
  })
  it('rowSeries: значения по периодам', () => {
    expect(rowSeries(PERIODS, 'turnover')).toEqual([1.9, 2.4, 2])
    expect(rowSeries(PERIODS, 'fired')).toEqual([10, 10, 3])
  })
  it('periodDelta: к предыдущему периоду, без пары — null', () => {
    expect(periodDelta(PERIODS, 1, 'turnover')).toBe(0.5)
    expect(periodDelta(PERIODS, 2, 'hired')).toBe(-8)
    expect(periodDelta(PERIODS, 0, 'hired')).toBeNull()
    expect(periodDelta(PERIODS, 1, 'avg')).toBeNull()
    expect(periodDelta(PERIODS, 5, 'hired')).toBeNull()
  })
  it('focusIndex: выбранный период или последний', () => {
    expect(focusIndex(PERIODS, '2026-Q2')).toBe(1)
    expect(focusIndex(PERIODS, '')).toBe(2)
    expect(focusIndex(PERIODS, '2020-Q1')).toBe(2)
    expect(focusIndex([], '')).toBe(-1)
  })
  it('lightTotals: сумма оценок по диапазону', () => {
    expect(lightTotals(PERIODS)).toEqual({ green: 15, yellow: 3, red: 3, gray: 27 })
    expect(lightTotals([])).toEqual({ green: 0, yellow: 0, red: 0, gray: 0 })
  })
})

describe('строки и подписи таблицы', () => {
  const defs = [
    { key: 'turnover', label: 'Текучесть', category: 'turnover', sort_order: 140, aggregation: 'latest' },
    { key: 'total', label: 'Всего', category: 'headcount', sort_order: 0, aggregation: 'latest' },
    { key: 'resumes', label: 'Резюме', category: 'hiring', sort_order: 20, aggregation: 'sum' },
    { key: 'custom', label: 'Своя', category: 'other', sort_order: 150, aggregation: 'avg' },
  ]
  it('summaryGroups: движение персонала первым, затем категории по sort_order', () => {
    const groups = summaryGroups(defs)
    expect(groups.map((g) => g.key)).toEqual(['flow', 'headcount', 'hiring', 'turnover', 'other'])
    expect(groups.map((g) => g.label)).toEqual(['Движение персонала', 'Численность', 'Подбор', 'Текучесть', 'other'])
    expect(groups[0].items.map((r) => r.key)).toEqual(['hired', 'fired', 'net'])
    expect(defs[0].key).toBe('turnover') // исходный список не сортируется на месте
  })
  it('rowDefinition и isFlowKey', () => {
    expect(rowDefinition(defs, 'hired')).toBe(FLOW_ROWS[0])
    expect(rowDefinition(defs, 'resumes').label).toBe('Резюме')
    expect(rowDefinition(defs, 'nope')).toBeNull()
    expect(isFlowKey('net')).toBe(true)
    expect(isFlowKey('turnover')).toBe(false)
  })
  it('chartKind: суммы — столбцы, остальное — линия', () => {
    expect(chartKind(defs[2])).toBe('bar')
    expect(chartKind(FLOW_ROWS[0])).toBe('bar')
    expect(chartKind(defs[0])).toBe('line')
    expect(chartKind(null)).toBe('line')
  })
  it('isPartial и monthsCaption: неполные периоды', () => {
    expect(isPartial(PERIODS[2], 'quarter')).toBe(true)
    expect(isPartial(PERIODS[0], 'quarter')).toBe(false)
    expect(isPartial(period('m', { months_count: 1 }), 'month')).toBe(false)
    expect(monthsCaption(PERIODS[2], 'quarter')).toBe('2 из 3 мес.')
    expect(monthsCaption(PERIODS[0], 'quarter')).toBe('3 мес.')
    expect(monthsCaption(period('y', { months_count: 8 }), 'year')).toBe('8 из 12 мес.')
    expect(monthsCaption(period('m', { months_count: 1 }), 'month')).toBe('')
  })
  it('shortLabel: короткие подписи для оси', () => {
    expect(shortLabel(period('2026-M3', { index: 3 }), 'month')).toBe('мар 26')
    expect(shortLabel(period('2026-Q2', { index: 2 }), 'quarter')).toBe('2 кв. 26')
    expect(shortLabel(period('2026-H2', { index: 2 }), 'half')).toBe('II пол. 26')
    expect(shortLabel(period('2026-Y1'), 'year')).toBe('2026')
    expect(shortLabel(null, 'year')).toBe('')
  })
})
