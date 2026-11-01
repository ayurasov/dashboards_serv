import { describe, expect, it } from 'vitest'
import {
  AVG_METRICS, CLIENTS, QUICK_PERIODS, TABLE_COLUMNS,
  aggregate, avgOf, channelTotals, clientRows, clientShares, compareMetrics, comparePeriods, deltaLabel,
  evaluateInterval, filterRows, groupColumns, intervalDelta, intervalScale, intervalTitle, metricDirection,
  metricDigits, normalizeRows, periodRange, productSummary, projServerSummary, quickSelection, quickWeeks,
  rulesByKey, searchRows, seriesOf, shortLabels, sortRows, sumOf, tableRows, toneCounts, topWeeks, totals,
  trafficCards, weekLight, weeksOf, yearsOf,
} from './tp'

const pad = (n) => String(n).padStart(2, '0')
const row = (year, week, values = {}) => ({ id: year * 100 + week, year, week, period: `${year}-W${pad(week)}`, note: '', ...values })

/** n последовательных недель, начиная с (year, week); values(i) — показатели i-й недели. */
function weeks(n, values = () => ({}), year = 2025, week = 1) {
  const out = []
  let y = year
  let w = week
  for (let i = 0; i < n; i += 1) {
    out.push(row(y, w, values(i)))
    w += 1
    if (w > 52) { w = 1; y += 1 }
  }
  return out
}

const rule = (metric_key, direction, green, yellow, extra = {}) => ({
  metric_key, label: metric_key, unit: '', direction, green_threshold: green, yellow_threshold: yellow, enabled: true,
  updated_at: '2026-01-01T00:00:00', ...extra,
})

describe('quick periods', () => {
  it('lists the legacy quick periods with «all» last', () => {
    expect(QUICK_PERIODS.map((q) => q.value)).toEqual(['1', '2', '4', '8', '13', '26', 'all'])
  })

  it('parses the number of weeks', () => {
    expect(quickWeeks('8')).toBe(8)
    expect(quickWeeks(13)).toBe(13)
    expect(quickWeeks('all')).toBeNull()
    expect(quickWeeks('')).toBeNull()
    expect(quickWeeks('0')).toBeNull()
  })
})

describe('normalizeRows', () => {
  it('drops rows without year/week, rounds and sorts chronologically', () => {
    const out = normalizeRows([
      row(2025, 3), { year: null, week: 2 }, row(2024, 52), { ...row(2025, 1), year: 2025.0, week: 0.9999 }, { year: 2025, week: undefined },
    ])
    expect(out.map((r) => [r.year, r.week])).toEqual([[2024, 52], [2025, 1], [2025, 3]])
  })

  it('handles empty input', () => {
    expect(normalizeRows(null)).toEqual([])
  })
})

describe('years and weeks', () => {
  const rows = [row(2024, 50), row(2024, 51), row(2025, 1), row(2025, 2), row(2025, 51)]
  it('collects unique sorted years and weeks', () => {
    expect(yearsOf(rows)).toEqual([2024, 2025])
    expect(weeksOf(rows)).toEqual([1, 2, 50, 51])
    expect(weeksOf(rows, 2025)).toEqual([1, 2, 51])
    expect(weeksOf(rows, '2024')).toEqual([50, 51])
  })
})

describe('quickSelection (legacy applyQuick)', () => {
  const rows = [row(2024, 50), row(2024, 51), row(2025, 1), row(2025, 2), row(2025, 3)]
  it('«all» selects every year and the full week range', () => {
    expect(quickSelection(rows, 'all')).toEqual({ years: [2024, 2025], weekFrom: 1, weekTo: 51 })
  })
  it('N weeks selects the years and edge weeks of the last N rows', () => {
    expect(quickSelection(rows, '2')).toEqual({ years: [2025], weekFrom: 2, weekTo: 3 })
    expect(quickSelection(rows, '4')).toEqual({ years: [2024, 2025], weekFrom: 51, weekTo: 3 })
  })
  it('works on empty data', () => {
    expect(quickSelection([], '4')).toEqual({ years: [], weekFrom: null, weekTo: null })
    expect(quickSelection([], 'all')).toEqual({ years: [], weekFrom: null, weekTo: null })
  })
})

describe('filterRows', () => {
  const rows = [row(2024, 50), row(2024, 51), row(2025, 1), row(2025, 2), row(2025, 3), row(2025, 4)]

  it('quick N returns the last N rows regardless of year filters', () => {
    expect(filterRows(rows, { quick: '3', years: ['2024'] }).map((r) => r.period)).toEqual(['2025-W02', '2025-W03', '2025-W04'])
    expect(filterRows(rows, { quick: '26' })).toHaveLength(6)
  })

  it('«all» without years returns everything', () => {
    expect(filterRows(rows, { quick: 'all' })).toHaveLength(6)
    expect(filterRows(rows)).toHaveLength(6)
  })

  it('filters by selected years (numbers or strings from the URL)', () => {
    expect(filterRows(rows, { years: [2024] }).map((r) => r.week)).toEqual([50, 51])
    expect(filterRows(rows, { years: ['2025'] }).map((r) => r.week)).toEqual([1, 2, 3, 4])
  })

  it('applies the week range only when exactly one year is selected', () => {
    expect(filterRows(rows, { years: ['2025'], weekFrom: 2, weekTo: 3 }).map((r) => r.week)).toEqual([2, 3])
    expect(filterRows(rows, { years: ['2024', '2025'], weekFrom: 2, weekTo: 3 })).toHaveLength(6)
    expect(filterRows(rows, { years: ['2025'], weekFrom: 3 }).map((r) => r.week)).toEqual([3, 4])
    expect(filterRows(rows, { years: ['2025'], weekFrom: 0, weekTo: 0 })).toHaveLength(4)
  })

  it('treats a single-year data set as one selected year', () => {
    const one = rows.filter((r) => r.year === 2025)
    expect(filterRows(one, { weekFrom: 2, weekTo: 2 }).map((r) => r.week)).toEqual([2])
  })
})

describe('clientRows', () => {
  it('keeps weeks where the client has hours', () => {
    const rows = [row(2025, 1, { mchs_hours: 0 }), row(2025, 2, { mchs_hours: 4 }), row(2025, 3, { mchs_hours: null })]
    expect(clientRows(rows, 'mchs_hours').map((r) => r.week)).toEqual([2])
    expect(clientRows(rows, '')).toHaveLength(3)
  })
})

describe('aggregation', () => {
  const rows = [
    row(2025, 1, { total_in_work: 100, new_received: 10, ratio_solved_received: 1.2 }),
    row(2025, 2, { total_in_work: 200, new_received: null, ratio_solved_received: 0.8 }),
    row(2025, 3, { total_in_work: null, new_received: 30, ratio_solved_received: null }),
  ]

  it('declares the average metrics', () => {
    expect([...AVG_METRICS].sort()).toEqual(['altoffice_avg_time', 'altos_avg_time', 'ratio_solved_received', 'total_in_work'])
  })

  it('sums and averages only non-empty values', () => {
    expect(sumOf(rows, 'new_received')).toBe(40)
    expect(avgOf(rows, 'total_in_work')).toBe(150)
    expect(sumOf(rows, 'renewed')).toBeNull()
    expect(avgOf(rows, 'renewed')).toBeNull()
  })

  it('aggregates: averages for level/ratio metrics, sums for the rest', () => {
    expect(aggregate(rows, 'total_in_work')).toBe(150)
    expect(aggregate(rows, 'ratio_solved_received')).toBeCloseTo(1.0)
    expect(aggregate(rows, 'new_received')).toBe(40)
    expect(aggregate([], 'new_received')).toBeNull()
  })

  it('totals use the same rules', () => {
    expect(totals(rows, ['total_in_work', 'new_received', 'renewed'])).toEqual({ total_in_work: 150, new_received: 40, renewed: null })
  })

  it('scales thresholds only for sum metrics', () => {
    expect(intervalScale('new_received', 8)).toBe(8)
    expect(intervalScale('total_in_work', 8)).toBe(1)
    expect(intervalScale('new_received', 0)).toBe(1)
  })

  it('series keep gaps as null', () => {
    expect(seriesOf(rows, 'new_received')).toEqual([10, null, 30])
    expect(seriesOf(rows, 'missing')).toEqual([null, null, null])
  })

  it('digits per metric', () => {
    expect(metricDigits('ratio_solved_received')).toBe(2)
    expect(metricDigits('altos_avg_time')).toBe(1)
  })
})

describe('evaluateInterval', () => {
  const solved = rule('total_solved_week', 'higher_is_better', 25, 18)
  const avgTime = rule('altos_avg_time', 'lower_is_better', 24, 48)
  const rows = weeks(4, (i) => ({ total_solved_week: [20, 22, 24, 30][i], altos_avg_time: [20, 30, 40, 50][i] }))

  it('multiplies sum thresholds by the number of weeks', () => {
    // сумма 96: зелёный порог 25 × 4 = 100, жёлтый 18 × 4 = 72
    expect(evaluateInterval(rows, 'total_solved_week', solved)).toBe('yellow')
    expect(evaluateInterval(rows.slice(-1), 'total_solved_week', solved)).toBe('green')
    expect(evaluateInterval(rows.slice(0, 2), 'total_solved_week', solved)).toBe('yellow')
  })

  it('does not scale average metrics', () => {
    // среднее 35: 24 < 35 ≤ 48
    expect(evaluateInterval(rows, 'altos_avg_time', avgTime)).toBe('yellow')
    expect(evaluateInterval(rows.slice(0, 1), 'altos_avg_time', avgTime)).toBe('green')
    expect(evaluateInterval(rows.slice(-1), 'altos_avg_time', avgTime)).toBe('red')
  })

  it('returns gray without data or with a disabled rule', () => {
    expect(evaluateInterval(rows, 'renewed', rule('renewed', 'lower_is_better', 1, 2))).toBe('gray')
    expect(evaluateInterval(rows, 'total_solved_week', { ...solved, enabled: false })).toBe('gray')
  })
})

describe('comparePeriods and intervalDelta', () => {
  const rows = weeks(20, (i) => ({ new_received: i + 1, total_in_work: 100 + i }))

  it('quick N compares the last N weeks with the N weeks before', () => {
    const pair = comparePeriods(rows, rows.slice(-4), '4')
    expect(pair.mode).toBe('quick')
    expect(pair.weeks).toBe(4)
    expect(pair.now.map((r) => r.new_received)).toEqual([17, 18, 19, 20])
    expect(pair.prev.map((r) => r.new_received)).toEqual([13, 14, 15, 16])
  })

  it('quick N without enough history gives a partial or empty previous interval', () => {
    expect(comparePeriods(rows, rows, '26').prev).toEqual([])
    expect(comparePeriods(rows, rows, '12').prev.map((r) => r.new_received)).toEqual([1, 2, 3, 4, 5, 6, 7, 8])
  })

  it('«all» compares the second half of the selection with the first half', () => {
    const selection = rows.slice(0, 7)
    const pair = comparePeriods(rows, selection, 'all')
    expect(pair.mode).toBe('halves')
    expect(pair.prev.map((r) => r.new_received)).toEqual([1, 2, 3])
    expect(pair.now.map((r) => r.new_received)).toEqual([4, 5, 6, 7])
  })

  it('«all» with a single week has nothing to compare', () => {
    const pair = comparePeriods(rows, rows.slice(0, 1), 'all')
    expect(pair.prev).toHaveLength(1)
    expect(pair.now).toHaveLength(0)
    expect(intervalDelta(pair, 'new_received').pct).toBeNull()
  })

  it('computes sum and average deltas', () => {
    const pair = comparePeriods(rows, rows, '4')
    const sum = intervalDelta(pair, 'new_received')
    expect(sum.now).toBe(74)
    expect(sum.prev).toBe(58)
    expect(sum.delta).toBe(16)
    expect(sum.pct).toBeCloseTo((16 / 58) * 100)
    const avg = intervalDelta(pair, 'total_in_work')
    expect(avg.now).toBeCloseTo(117.5)
    expect(avg.prev).toBeCloseTo(113.5)
  })

  it('returns no percentage when the previous value is zero or missing', () => {
    const zero = weeks(4, (i) => ({ new_received: i < 2 ? 0 : 5 }))
    const pair = comparePeriods(zero, zero, '2')
    expect(intervalDelta(pair, 'new_received')).toEqual({ now: 10, prev: 0, delta: 10, pct: null })
    expect(intervalDelta(pair, 'renewed')).toEqual({ now: null, prev: null, delta: null, pct: null })
  })

  it('labels the intervals', () => {
    expect(deltaLabel({ mode: 'quick', weeks: 8 })).toBe('к пред. 8 нед.')
    expect(deltaLabel({ mode: 'quick', weeks: 1 })).toBe('к пред. неделе')
    expect(deltaLabel({ mode: 'halves' })).toBe('ко 1-й половине периода')
    const pair = comparePeriods(rows, rows, '8')
    expect(intervalTitle(pair, 'now')).toBe('Последние 8 недель')
    expect(intervalTitle(pair, 'prev')).toBe('Предыдущие 8 недель')
    expect(intervalTitle(comparePeriods(rows, rows, '1'), 'now')).toBe('Последняя неделя')
    expect(intervalTitle(comparePeriods(rows, rows, '1'), 'prev')).toBe('Предыдущая неделя')
    expect(intervalTitle(comparePeriods(rows, rows, '2'), 'now')).toBe('Последние 2 недели')
    expect(intervalTitle(comparePeriods(rows, rows, '12'), 'prev')).toBe('Предыдущие 8 недель')
    expect(intervalTitle(comparePeriods(rows, rows, 'all'), 'now')).toBe('2-я половина периода')
    expect(intervalTitle(comparePeriods(rows, rows, 'all'), 'prev')).toBe('1-я половина периода')
  })

  it('formats the period range', () => {
    expect(periodRange(rows.slice(0, 3))).toBe('2025-W01 — 2025-W03')
    expect(periodRange(rows.slice(0, 1))).toBe('2025-W01')
    expect(periodRange([])).toBe('')
  })
})

describe('traffic rules', () => {
  it('indexes rules by metric key', () => {
    expect(Object.keys(rulesByKey([rule('a', 'lower_is_better', 1, 2), rule('b', 'lower_is_better', 1, 2)]))).toEqual(['a', 'b'])
    expect(rulesByKey(null)).toEqual({})
  })

  it('direction comes from a stored rule, then from the legacy map, else neutral', () => {
    expect(metricDirection('new_received', rule('new_received', 'higher_is_better', 1, 2))).toBe('higher_is_better')
    const unset = { metric_key: 'new_received', direction: 'higher_is_better', green_threshold: null, yellow_threshold: null, enabled: false, updated_at: null }
    expect(metricDirection('new_received', unset)).toBe('lower_is_better')
    expect(metricDirection('rushydro_hours', { ...unset, metric_key: 'rushydro_hours' })).toBe('neutral')
    expect(metricDirection('rushydro_hours', undefined)).toBe('neutral')
  })

  it('evaluates a single week without scaling', () => {
    const r = rule('total_solved_week', 'higher_is_better', 25, 18)
    expect(weekLight({ total_solved_week: 20 }, 'total_solved_week', r)).toBe('yellow')
    expect(weekLight({ total_solved_week: null }, 'total_solved_week', r)).toBe('gray')
    expect(weekLight({ total_solved_week: 20 }, 'total_solved_week', { ...r, enabled: false })).toBeNull()
  })
})

describe('trafficCards', () => {
  const rules = [
    rule('altoffice_avg_time', 'lower_is_better', 36, 72, { label: 'AlterOffice · среднее время решения', unit: 'ч' }),
    rule('total_solved_week', 'higher_is_better', 25, 18, { label: 'Решено за неделю', unit: 'шт.' }),
    rule('renewed', 'lower_is_better', 2, 4, { label: 'Возобновлено', unit: 'шт.' }),
    rule('new_received', 'lower_is_better', 25, 35, { enabled: false }),
    rule('total_in_work', 'lower_is_better', 180, 220, { label: 'Итого в работе заявок', unit: 'шт.' }),
  ]
  const all = weeks(8, (i) => ({ total_solved_week: 20 + i, total_in_work: 200 + i * 10, altoffice_avg_time: 30, renewed: 1 }))
  const now = all.slice(-4)
  const pair = comparePeriods(all, now, '4')

  it('shows enabled rules only, in the legacy order, unknown metrics last', () => {
    const cards = trafficCards(now, rules, pair)
    expect(cards.map((c) => c.key)).toEqual(['total_in_work', 'total_solved_week', 'altoffice_avg_time', 'renewed'])
    expect(cards[0].label).toBe('В работе, в среднем')
    expect(cards[3].label).toBe('Возобновлено')
  })

  it('aggregates the interval and scales sum thresholds', () => {
    const cards = Object.fromEntries(trafficCards(now, rules, pair).map((c) => [c.key, c]))
    // решено: 24+25+26+27 = 102 ≥ 25×4 → зелёный
    expect(cards.total_solved_week).toMatchObject({ value: 102, aggregation: 'sum', weeks: 4, green: 100, yellow: 72, light: 'green', unit: 'шт.' })
    // в работе: среднее 255 > 220 → красный, пороги не масштабируются
    expect(cards.total_in_work).toMatchObject({ value: 255, aggregation: 'avg', green: 180, yellow: 220, light: 'red' })
    expect(cards.altoffice_avg_time.light).toBe('green')
  })

  it('adds the delta to the previous interval of the same length', () => {
    const cards = Object.fromEntries(trafficCards(now, rules, pair).map((c) => [c.key, c]))
    // решено: 102 против 20+21+22+23 = 86
    expect(cards.total_solved_week.deltaPct).toBeCloseTo(((102 - 86) / 86) * 100)
    expect(cards.altoffice_avg_time.deltaPct).toBe(0)
    expect(trafficCards(now, rules).every((c) => c.deltaPct === null)).toBe(true)
  })

  it('returns nothing for an empty interval', () => {
    expect(trafficCards([], rules, pair)).toEqual([])
  })

  it('gives a gray light when the interval has no values for the metric', () => {
    const empty = weeks(2, () => ({ total_solved_week: null }))
    const card = trafficCards(empty, [rules[1]])[0]
    expect(card.value).toBeNull()
    expect(card.light).toBe('gray')
  })
})

describe('detailed table', () => {
  const rows = [
    row(2025, 10, { new_received: 5, rushydro_hours: 10, note: 'Праздники' }),
    row(2024, 52, { new_received: null, rushydro_hours: 0 }),
    row(2025, 2, { new_received: 9, rushydro_hours: 3 }),
  ]

  it('searches by period in both formats and by note', () => {
    expect(searchRows(rows, '2025-W10').map((r) => r.week)).toEqual([10])
    expect(searchRows(rows, '2025-2').map((r) => r.week)).toEqual([2])
    expect(searchRows(rows, 'праздн').map((r) => r.week)).toEqual([10])
    expect(searchRows(rows, '  ')).toHaveLength(3)
  })

  it('sorts by period chronologically and keeps empty values last', () => {
    expect(sortRows(rows, 'period').map((r) => r.period)).toEqual(['2024-W52', '2025-W02', '2025-W10'])
    expect(sortRows(rows, 'period', 'desc').map((r) => r.period)).toEqual(['2025-W10', '2025-W02', '2024-W52'])
    expect(sortRows(rows, 'new_received', 'asc').map((r) => r.new_received)).toEqual([5, 9, null])
    expect(sortRows(rows, 'new_received', 'desc').map((r) => r.new_received)).toEqual([9, 5, null])
    expect(sortRows(rows, 'note', 'desc')[0].note).toBe('Праздники')
  })

  it('does not mutate the input', () => {
    const copy = [...rows]
    sortRows(rows, 'period')
    expect(rows).toEqual(copy)
  })

  it('combines search, client filter and sort', () => {
    expect(tableRows(rows, { client: 'rushydro_hours', sortKey: 'rushydro_hours', sortDir: 'desc' }).map((r) => r.week)).toEqual([10, 2])
    expect(tableRows(rows, { search: '2025', sortDir: 'desc' }).map((r) => r.week)).toEqual([10, 2])
    expect(tableRows(rows).map((r) => r.week)).toEqual([52, 2, 10])
  })

  it('table columns: period first, client columns flagged, traffic dots on key metrics', () => {
    expect(TABLE_COLUMNS[0].key).toBe('period')
    expect(TABLE_COLUMNS.filter((c) => c.client).map((c) => c.key)).toEqual(CLIENTS.map((c) => c.key))
    expect(TABLE_COLUMNS.filter((c) => c.dot).map((c) => c.key)).toEqual(['total_in_work', 'avail_total', 'new_received', 'total_solved_week', 'ratio_solved_received', 'altos_avg_time', 'altoffice_avg_time'])
  })
})

describe('chart data', () => {
  const rows = [
    row(2025, 1, { avail_total: 100, rushydro_hours: 60, transneft_hours: 20, mchs_hours: null, internal_sales_hours: 20,
      altos_rusg_email: 3, altos_rusg_tf: 1, altos_other_email: 2, altos_other_tf: null, altoffice_rusg_email: 4, altoffice_other_tf: 2,
      altos_total: 10, altos_1_2line: 7, altos_3line: 3, altos_avg_time: 20, altos_avail_total: 40,
      projserver_taken: 4, projserver_solved: 3, projserver_avail: 12 }),
    row(2025, 2, { avail_total: 100, rushydro_hours: 40, transneft_hours: 40, mchs_hours: 0, internal_sales_hours: 20,
      altos_total: 6, altos_1_2line: 3, altos_3line: 3, altos_avg_time: 30, altos_avail_total: 20,
      projserver_taken: 6, projserver_solved: 5, projserver_avail: null }),
  ]

  it('client shares over the period', () => {
    const shares = clientShares(rows)
    expect(shares.map((s) => s.key)).toEqual(CLIENTS.map((c) => c.key))
    expect(shares[0]).toMatchObject({ label: 'РусГидро', value: 100, share: 50, color: 1 })
    expect(shares.find((s) => s.key === 'mchs_hours').value).toBe(0)
    expect(shares.reduce((s, x) => s + x.share, 0)).toBeCloseTo(100)
  })

  it('client shares with a selected client: client vs the rest of the labour', () => {
    expect(clientShares(rows, 'transneft_hours')).toEqual([
      { key: 'transneft_hours', label: 'Транснефть', color: 2, value: 60, share: 30 },
      { key: 'rest', label: 'Остальные клиенты', color: null, value: 140, share: 70 },
    ])
  })

  it('client shares on empty data', () => {
    expect(clientShares([]).every((s) => s.value === 0 && s.share === 0)).toBe(true)
  })

  it('top weeks by value, non-zero only', () => {
    expect(topWeeks(rows, 'rushydro_hours')).toEqual([{ period: '2025-W01', value: 60 }, { period: '2025-W02', value: 40 }])
    expect(topWeeks(rows, 'mchs_hours')).toEqual([])
    expect(topWeeks(rows, 'rushydro_hours', 1)).toHaveLength(1)
  })

  it('channel totals across products', () => {
    expect(channelTotals(rows)).toEqual({ email: 9, phone: 3 })
  })

  it('product summary', () => {
    expect(productSummary(rows, 'altos')).toEqual({ total: 16, l12: 10, l3: 6, l12Share: 62.5, l3Share: 37.5, avgTime: 25, avail: 60 })
    expect(productSummary([], 'altoffice')).toMatchObject({ total: null, l12Share: null, avgTime: null })
  })

  it('Project Server summary takes availability of the last week with data', () => {
    expect(projServerSummary(rows)).toEqual({ taken: 10, solved: 8, solvedShare: 80, availLast: 12, availLastPeriod: '2025-W01', availAvg: 12 })
    expect(projServerSummary([])).toMatchObject({ taken: null, solvedShare: null, availLast: null })
  })
})

describe('period comparison page', () => {
  const columns = [
    { key: 'new_received', label: 'Принято новых заявок', group: 'tickets', group_label: 'Поток заявок', unit: 'шт.' },
    { key: 'total_in_work', label: 'Итого в работе заявок', group: 'load', group_label: 'Нагрузка', unit: 'шт.' },
    { key: 'rushydro_hours', label: 'РусГидро', group: 'client_hours', group_label: 'Трудозатраты по клиентам', unit: 'ч' },
    { key: 'total_solved_week', label: 'Решено за неделю', group: 'tickets', group_label: 'Поток заявок', unit: 'шт.' },
  ]
  const rows = weeks(4, (i) => ({ new_received: [10, 10, 12, 12][i], total_in_work: [200, 200, 150, 150][i], rushydro_hours: [5, 5, 9, 9][i], total_solved_week: [20, 20, 20, 20][i] }))
  const pair = comparePeriods(rows, rows, '2')
  const rules = rulesByKey([rule('total_in_work', 'lower_is_better', 180, 220), rule('total_solved_week', 'higher_is_better', 25, 18, { enabled: false })])

  it('groups columns in order of appearance', () => {
    const groups = groupColumns(columns)
    expect(groups.map((g) => [g.key, g.items.length])).toEqual([['tickets', 2], ['load', 1], ['client_hours', 1]])
    expect(groups[0].label).toBe('Поток заявок')
  })

  it('builds comparison rows with tone and light', () => {
    const items = Object.fromEntries(compareMetrics(columns, pair, rules).map((m) => [m.key, m]))
    expect(items.new_received).toMatchObject({ now: 24, prev: 20, delta: 4, direction: 'lower_is_better', tone: 'bad', light: null })
    expect(items.new_received.pct).toBeCloseTo(20)
    expect(items.total_in_work).toMatchObject({ now: 150, prev: 200, delta: -50, pct: -25, tone: 'good', light: 'green' })
    expect(items.rushydro_hours).toMatchObject({ direction: 'neutral', tone: 'flat' })
    expect(items.total_solved_week).toMatchObject({ delta: 0, tone: 'flat', light: null })
  })

  it('counts improved and worsened metrics, ignoring neutral ones', () => {
    expect(toneCounts(compareMetrics(columns, pair, rules))).toEqual({ good: 1, bad: 1, flat: 1 })
  })

  it('shortens labels with a common prefix', () => {
    expect(shortLabels(['AlterOS · 1–2 линия', 'AlterOS · 3 линия'])).toEqual(['1–2 линия', '3 линия'])
    expect(shortLabels(['Project Server · принято', 'Project Server · решено'])).toEqual(['Принято', 'Решено'])
    expect(shortLabels(['AlterOS · РусГидро · e-mail', 'AlterOS · прочие · телефон'])).toEqual(['РусГидро · e-mail', 'Прочие · телефон'])
    expect(shortLabels(['РусГидро', 'Транснефть'])).toEqual(['РусГидро', 'Транснефть'])
    expect(shortLabels(['AlterOS · 1–2 линия'])).toEqual(['AlterOS · 1–2 линия'])
  })
})
