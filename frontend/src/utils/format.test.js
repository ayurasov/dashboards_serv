import { describe, expect, it } from 'vitest'
import { deltaTone, formatDate, formatDelta, formatNumber, formatPercent, formatRelative, monthLabel, pctChange, plural } from './format'

describe('formatNumber', () => {
  it('formats Russian numbers with units', () => {
    expect(formatNumber(1234.5)).toBe('1 234,5')
    expect(formatNumber(12, { unit: 'чел.' })).toBe('12 чел.')
    expect(formatNumber(3.87, { unit: '%' })).toBe('3,87%')
    expect(formatNumber(2)).toBe('2')
  })
  it('shows a dash for empty values', () => {
    for (const v of [null, undefined, '', 'abc']) expect(formatNumber(v)).toBe('—')
  })
  it('limits fraction digits', () => {
    expect(formatNumber(1.23456, { digits: 1 })).toBe('1,2')
  })
})

describe('delta helpers', () => {
  it('evaluates change by metric direction', () => {
    expect(deltaTone(-1, 'lower_is_better')).toBe('good')
    expect(deltaTone(1, 'lower_is_better')).toBe('bad')
    expect(deltaTone(1, 'higher_is_better')).toBe('good')
    expect(deltaTone(1, 'neutral')).toBe('flat')
    expect(deltaTone(0.2, 'higher_is_better', 0.5)).toBe('flat')
    expect(deltaTone(null, 'higher_is_better')).toBe('flat')
  })
  it('formats signed deltas, percents use percentage points', () => {
    expect(formatDelta(-1.87, '%')).toBe('−1,87 п.п.')
    expect(formatDelta(3, 'чел.')).toBe('+3 чел.')
    expect(formatDelta(0)).toBe('±0')
    expect(formatDelta(null)).toBe('')
  })
  it('computes percent change', () => {
    expect(pctChange(110, 100)).toBeCloseTo(10)
    expect(pctChange(1, 0)).toBeNull()
    expect(pctChange(null, 5)).toBeNull()
  })
})

describe('dates and words', () => {
  it('formats dates from server UTC strings', () => {
    expect(formatDate('2026-07-20')).toBe('20.07.2026')
    expect(formatDate(null)).toBe('—')
  })
  it('formats relative time', () => {
    const now = new Date('2026-11-01T12:00:00Z')
    expect(formatRelative('2026-11-01T11:59:40', now)).toBe('только что')
    expect(formatRelative('2026-11-01T11:55:00', now)).toBe('5 минут назад')
    expect(formatRelative('2026-11-01T09:00:00', now)).toBe('3 часа назад')
    expect(formatRelative('2026-10-30T12:00:00', now)).toBe('2 дня назад')
  })
  it('picks Russian plural forms', () => {
    const forms = ['неделя', 'недели', 'недель']
    expect([1, 2, 5, 11, 21, 22, 25].map((n) => plural(n, forms))).toEqual(['неделя', 'недели', 'недель', 'недель', 'неделя', 'недели', 'недель'])
  })
  it('labels months', () => {
    expect(monthLabel('2026-06')).toBe('Июнь 2026')
    expect(monthLabel('2026-06', true)).toBe('июн 26')
    expect(formatPercent(12.345)).toBe('12,3%')
  })
})

describe('negative numbers', () => {
  it('use the typographic minus like deltas do', () => {
    expect(formatNumber(-1)).toBe('−1')
    expect(formatNumber(-2.5, { unit: '%' })).toBe('−2,5%')
  })
})
