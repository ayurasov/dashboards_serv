import { describe, expect, it } from 'vitest'
import {
  avgBy, coverageLight, dayText, distribution, escapeHtml, divergence, divergenceRows, filterByYear, formatDeviation, formatHours,
  formatMetric, formatSigned, groupColumns, hoursHint, isoWeekOf, isoWeekStart, isoWeeksInYear, lastPeriods,
  matchesSearch, nextIsoWeek, overdueLight, parseDecimal, parsePeriod, periodCount, share, shortLabel, sortWeeks,
  sumBy, typicalShare, weekAxisLabel, weekRangeText, withBar, withReport, yearsOf,
} from './naumen'

const iso = (d) => d.toISOString().slice(0, 10)

describe('periods', () => {
  const months = [{ month: '2026-01', year: 2026 }, { month: '2026-02', year: 2026 }, { month: '2025-12', year: 2025 }]
  it('takes the last N periods, 0 means all', () => {
    expect(lastPeriods([1, 2, 3, 4], 2)).toEqual([3, 4])
    expect(lastPeriods([1, 2, 3], 0)).toEqual([1, 2, 3])
    expect(lastPeriods([1, 2], 5)).toEqual([1, 2])
    expect(lastPeriods(null, 3)).toEqual([])
  })
  it('filters by year and lists years', () => {
    expect(filterByYear(months, 2026)).toHaveLength(2)
    expect(filterByYear(months, '2025')).toHaveLength(1)
    expect(filterByYear(months, 0)).toHaveLength(3)
    expect(yearsOf(months)).toEqual([2025, 2026])
  })
  it('names period counts', () => {
    expect(periodCount(1)).toBe('1 неделя')
    expect(periodCount(3)).toBe('3 недели')
    expect(periodCount(26)).toBe('26 недель')
    expect(periodCount(5, 'months')).toBe('5 месяцев')
  })
})

describe('ISO weeks', () => {
  it('finds the monday of a week', () => {
    expect(iso(isoWeekStart(2026, 1))).toBe('2025-12-29')
    expect(iso(isoWeekStart(2026, 31))).toBe('2026-07-27')
    expect(iso(isoWeekStart(2021, 1))).toBe('2021-01-04')
  })
  it('knows 53-week years and the next week', () => {
    expect(isoWeeksInYear(2026)).toBe(53)
    expect(isoWeeksInYear(2025)).toBe(52)
    expect(isoWeeksInYear(2020)).toBe(53)
    expect(nextIsoWeek(2025, 52)).toEqual({ year: 2026, week: 1 })
    expect(nextIsoWeek(2026, 52)).toEqual({ year: 2026, week: 53 })
    expect(nextIsoWeek(2026, 53)).toEqual({ year: 2027, week: 1 })
    expect(nextIsoWeek(2026, 31)).toEqual({ year: 2026, week: 32 })
  })
  it('matches Python isocalendar for dates', () => {
    expect(isoWeekOf(new Date(2026, 0, 1))).toEqual({ year: 2026, week: 1 })
    expect(isoWeekOf(new Date(2027, 0, 1))).toEqual({ year: 2026, week: 53 })
    expect(isoWeekOf(new Date(2026, 6, 31))).toEqual({ year: 2026, week: 31 })
  })
  it('formats week dates', () => {
    expect(weekRangeText(2026, 31)).toBe('27 июля — 2 августа 2026')
    expect(weekRangeText(2026, 28)).toBe('6–12 июля 2026')
    expect(weekRangeText(2026, 1)).toBe('29 декабря 2025 — 4 января 2026')
    expect(weekRangeText(2026, 31, { short: true })).toBe('27.07–02.08')
    expect(weekRangeText(null, 3)).toBe('')
  })
  it('formats server dates without timezone shifts and escapes tooltip text', () => {
    expect(dayText('2026-08-04T23:59:00')).toBe('04.08.2026')
    expect(dayText(null)).toBe('—')
    expect(escapeHtml('ООО <«Ромашка»> & "Ко"')).toBe('ООО &lt;«Ромашка»&gt; &amp; &quot;Ко&quot;')
  })
  it('parses periods and builds axis labels', () => {
    expect(parsePeriod('2026-W07')).toEqual({ year: 2026, week: 7 })
    expect(parsePeriod('2026-07')).toBeNull()
    expect(weekAxisLabel('2026-W31')).toBe('W31\n2026')
    expect(weekAxisLabel('2026-07')).toBe('2026-07')
  })
})

describe('numbers', () => {
  it('parses decimal input with commas and spaces', () => {
    expect(parseDecimal('1 234,5')).toBe(1234.5)
    expect(parseDecimal('0.7')).toBe(0.7)
    expect(parseDecimal('-3')).toBe(-3)
    expect(parseDecimal('')).toBeNull()
    expect(parseDecimal(null)).toBeNull()
    expect(parseDecimal(12)).toBe(12)
    expect(parseDecimal('12a')).toBeNaN()
    expect(parseDecimal('1,2,3')).toBeNaN()
  })
  it('formats hours with a days hint', () => {
    expect(formatHours(153.17)).toBe('153\u00a0ч')
    expect(formatHours(4.25)).toBe('4,3\u00a0ч')
    expect(formatHours(null)).toBe('—')
    expect(hoursHint(1290.78)).toBe('≈ 54 дн.')
    expect(hoursHint(60)).toBe('≈ 2,5 дн.')
    expect(hoursHint(20)).toBe('')
  })
  it('aggregates with nulls', () => {
    const rows = [{ a: 2 }, { a: null }, { a: 4 }, {}]
    expect(sumBy(rows, 'a')).toBe(6)
    expect(avgBy(rows, 'a')).toBe(3)
    expect(avgBy([{ a: null }], 'a')).toBeNull()
    expect(share(1, 3)).toBe(33.3)
    expect(share(1, 0)).toBeNull()
  })
  it('formats signed values and deviations', () => {
    expect(formatSigned(5)).toBe('+5')
    expect(formatSigned(-3.25)).toBe('−3,3')
    expect(formatSigned(0)).toBe('0')
    expect(formatDeviation(-0.62)).toBe('−62%')
    expect(formatDeviation(0.1)).toBe('+10%')
    expect(formatDeviation(null)).toBe('—')
    expect(formatMetric(0.7333, { key: 'ratio_solved_received' })).toBe('0,73')
    expect(formatMetric(1, { key: 'ratio_solved_received' })).toBe('1,00')
    expect(formatMetric(12.34, { key: 'avail_total' })).toBe('12,3')
    expect(formatMetric(null, { key: 'x' })).toBe('—')
  })
})

describe('lights', () => {
  it('rates overdue share', () => {
    expect(overdueLight(4.4)).toBe('green')
    expect(overdueLight(10)).toBe('green')
    expect(overdueLight(13.2)).toBe('yellow')
    expect(overdueLight(25)).toBe('red')
    expect(overdueLight(null)).toBe('gray')
  })
  it('rates coverage', () => {
    expect(coverageLight(90)).toBe('green')
    expect(coverageLight(70)).toBe('yellow')
    expect(coverageLight(38)).toBe('red')
    expect(coverageLight(undefined)).toBe('gray')
  })
  it('prepares bars and distributions', () => {
    expect(withBar([{ total: 10 }, { total: 5 }]).map((r) => r.bar)).toEqual([100, 50])
    const d = distribution([{ channel: 'Почта', count: 1 }, { channel: '', count: 3 }], 'channel')
    expect(d).toEqual([{ name: '—', value: 3, share: 75 }, { name: 'Почта', value: 1, share: 25 }])
  })
})

describe('divergence', () => {
  it('compares one to one', () => {
    expect(divergence(25, 8)).toMatchObject({ diff: 17, share: 32, level: 'red' })
    expect(divergence(20, 16)).toMatchObject({ diff: 4, share: 80, deviation: -0.2, level: null })
    expect(divergence(60, 42).level).toBe('yellow')
    expect(divergence(20, 35).level).toBe('red')
  })
  it('ignores random noise of small numbers and missing values', () => {
    expect(divergence(3, 0).level).toBeNull()
    expect(divergence(20, 14).level).toBeNull()
    expect(divergence(20, 31).level).toBe('yellow')
    expect(divergence(null, 5)).toEqual({ diff: null, share: null, deviation: null, z: null, level: null })
    expect(divergence(0, 4)).toMatchObject({ diff: -4, share: null, level: null })
  })
  it('compares with the typical share', () => {
    expect(divergence(30, 10, 33.3).level).toBeNull()
    expect(divergence(30, 3, 33.3).level).toBe('yellow')
    expect(divergence(90, 9, 33.3).level).toBe('red')
    expect(divergence(90, 18, 33.3).level).toBe('yellow')
    expect(divergence(30, 6, 33.3).level).toBeNull()
  })
  it('computes the typical share over rows with both sources', () => {
    const rows = [{ t: 20, n: 10 }, { t: 30, n: 5 }, { t: null, n: 7 }]
    expect(typicalShare(rows, 't', 'n')).toBe(30)
    expect(typicalShare([], 't', 'n')).toBeNull()
  })
  it('builds table rows with a worst level per period', () => {
    const rows = [
      { period: 'a', tp_new_received: 90, naumen_registered: 30, tp_solved: 90, naumen_solved: 90 },
      { period: 'b', tp_new_received: 90, naumen_registered: 33, tp_solved: 90, naumen_solved: 36 },
    ]
    const typical = divergenceRows(rows, 'typical')
    expect(Math.round(typical.expected.received)).toBe(35)
    expect(typical.rows[0].received.level).toBeNull()
    expect(typical.rows[0].solved.level).toBe('yellow')
    expect(typical.rows[1].solved.level).toBe('yellow')
    expect(typical.rows[1].level).toBe('yellow')
    const direct = divergenceRows(rows, 'direct')
    expect(direct.expected.received).toBe(100)
    expect(direct.rows[0].level).toBe('red')
    expect(direct.rows[0].solved.level).toBeNull()
  })
  it('drops naumen-only months', () => {
    expect(withReport([{ tp_new_received: null, tp_solved: null }, { tp_new_received: 0, tp_solved: null }])).toHaveLength(1)
  })
})

describe('weekly report table', () => {
  const columns = [
    { key: 'a', label: 'AlterOS · РусГидро · e-mail', group: 'altos_channels', group_label: 'AlterOS: каналы' },
    { key: 'b', label: 'Итого в работе', group: 'load', group_label: 'Нагрузка' },
    { key: 'c', label: 'AlterOS · прочие · телефон', group: 'altos_channels', group_label: 'AlterOS: каналы' },
  ]
  it('groups columns in order', () => {
    const groups = groupColumns(columns)
    expect(groups.map((g) => g.key)).toEqual(['altos_channels', 'load'])
    expect(groups[0].columns.map((c) => c.key)).toEqual(['a', 'c'])
  })
  it('shortens labels inside a group', () => {
    expect(shortLabel('AlterOS · РусГидро · e-mail', 'AlterOS: каналы')).toBe('РусГидро · e-mail')
    expect(shortLabel('Project Server · принято', 'Project Server')).toBe('Принято')
    expect(shortLabel('РусГидро', 'Трудозатраты по клиентам')).toBe('РусГидро')
  })
  it('searches by period and note', () => {
    const row = { period: '2026-W31', note: 'Отпуск инженера' }
    expect(matchesSearch(row, 'w31')).toBe(true)
    expect(matchesSearch(row, '2026-W3')).toBe(true)
    expect(matchesSearch(row, 'отпуск')).toBe(true)
    expect(matchesSearch(row, '2025')).toBe(false)
    expect(matchesSearch(row, '  ')).toBe(true)
  })
  it('sorts weeks with empty values last', () => {
    const rows = [{ year: 2026, week: 2, v: 5 }, { year: 2025, week: 52, v: null }, { year: 2026, week: 1, v: 9 }]
    expect(sortWeeks(rows, 'period', 'desc').map((r) => r.week)).toEqual([2, 1, 52])
    expect(sortWeeks(rows, 'period', 'asc').map((r) => r.week)).toEqual([52, 1, 2])
    expect(sortWeeks(rows, 'v', 'asc').map((r) => r.v)).toEqual([5, 9, null])
    expect(sortWeeks(rows, 'v', 'desc').map((r) => r.v)).toEqual([9, 5, null])
  })
})
