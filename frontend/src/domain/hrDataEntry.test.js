import { describe, expect, it } from 'vitest'
import {
  buildForm, changedRows, fillState, formErrors, formatInput, groupMonthsByYear, isRowChanged, lightFor, liveDelta,
  mapRowErrors, monthKey, nextMonth, parseNumber, pickMonth,
} from './hrDataEntry'

describe('разбор чисел', () => {
  it('parseNumber: запятая, пробелы, знак, пустое значение', () => {
    expect(parseNumber('12,5')).toEqual({ value: 12.5 })
    expect(parseNumber(' 1 234,75 ')).toEqual({ value: 1234.75 })
    expect(parseNumber('1 234')).toEqual({ value: 1234 })
    expect(parseNumber('-3')).toEqual({ value: -3 })
    expect(parseNumber('−3,5')).toEqual({ value: -3.5 })
    expect(parseNumber('.5')).toEqual({ value: 0.5 })
    expect(parseNumber('7.')).toEqual({ value: 7 })
    expect(parseNumber('')).toEqual({ value: null })
    expect(parseNumber('   ')).toEqual({ value: null })
    expect(parseNumber(null)).toEqual({ value: null })
    expect(parseNumber(0)).toEqual({ value: 0 })
  })
  it('parseNumber: не число — ошибка', () => {
    for (const raw of ['abc', '1,2,3', '12%', '1e5', '--1', ',']) expect(parseNumber(raw)).toEqual({ error: 'Введите число' })
  })
  it('formatInput: запятая вместо точки, пусто для null', () => {
    expect(formatInput(37.3333)).toBe('37,3333')
    expect(formatInput(0)).toBe('0')
    expect(formatInput(null)).toBe('')
    expect(formatInput(undefined)).toBe('')
  })
})

describe('форма метрик', () => {
  const metrics = [
    { key: 'a', value: 10, source_note: '' },
    { key: 'b', value: null, source_note: '' },
    { key: 'c', value: 2.5, source_note: 'отчёт' },
  ]
  it('buildForm: текст полей из значений', () => {
    expect(buildForm(metrics)).toEqual({
      a: { value: '10', source_note: '' }, b: { value: '', source_note: '' }, c: { value: '2,5', source_note: 'отчёт' },
    })
    expect(buildForm(null)).toEqual({})
  })
  it('без правок изменений нет', () => {
    const form = buildForm(metrics)
    expect(changedRows(metrics, form)).toEqual([])
    expect(metrics.some((m) => isRowChanged(m, form[m.key]))).toBe(false)
  })
  it('changedRows: только изменённые строки, значения разобраны, комментарии без пробелов по краям', () => {
    const form = buildForm(metrics)
    form.a.value = '10,0' // то же число — не изменение
    form.b.value = '7'
    form.c.source_note = '  отчёт за месяц '
    expect(changedRows(metrics, form)).toEqual([
      { metric_key: 'b', value: 7, source_note: '' },
      { metric_key: 'c', value: 2.5, source_note: 'отчёт за месяц' },
    ])
  })
  it('changedRows: очистка значения отправляет null, ошибочные строки не отправляются', () => {
    const form = buildForm(metrics)
    form.a.value = ''
    form.c.value = 'много'
    expect(changedRows(metrics, form)).toEqual([{ metric_key: 'a', value: null, source_note: '' }])
    expect(isRowChanged(metrics[2], form.c)).toBe(true)
    expect(formErrors(form)).toEqual({ c: 'Введите число' })
  })
  it('mapRowErrors: ошибки по номерам строк запроса → по метрикам', () => {
    const payload = [{ metric_key: 'b' }, { metric_key: 'c' }]
    expect(mapRowErrors({ '1.value': 'Нужно число', '0.source_note': 'Слишком длинное значение', body: 'x' }, payload))
      .toEqual({ c: 'Нужно число', b: 'Слишком длинное значение' })
    expect(mapRowErrors(undefined, payload)).toEqual({})
  })
})

describe('светофор и изменение', () => {
  const rule = { direction: 'lower_is_better', green_threshold: 5, yellow_threshold: 7, enabled: true }
  it('lightFor: как на сервере', () => {
    expect(lightFor(4, rule)).toBe('green')
    expect(lightFor(6, rule)).toBe('yellow')
    expect(lightFor(9, rule)).toBe('red')
    expect(lightFor(null, rule)).toBe('red')
    expect(lightFor(null, { ...rule, enabled: false })).toBe('gray')
    expect(lightFor(4, { ...rule, enabled: false })).toBe('gray')
    expect(lightFor(null, undefined)).toBe('gray')
    expect(lightFor(4, undefined)).toBe('gray')
  })
  it('liveDelta: разница с прошлым месяцем', () => {
    expect(liveDelta(12.5, 10)).toBe(2.5)
    expect(liveDelta(0.3, 0.1)).toBe(0.2)
    expect(liveDelta(null, 10)).toBeNull()
    expect(liveDelta(3, null)).toBeNull()
  })
})

describe('месяцы', () => {
  const months = [
    { key: '2025-11', year: 2025, month: 11, filled_metrics: 16, total_metrics: 16 },
    { key: '2025-12', year: 2025, month: 12, filled_metrics: 4, total_metrics: 16 },
    { key: '2026-01', year: 2026, month: 1, filled_metrics: 0, total_metrics: 16 },
  ]
  it('monthKey: ключ ГГГГ-ММ', () => {
    expect(monthKey(2026, 3)).toBe('2026-03')
    expect(monthKey(2026, 11)).toBe('2026-11')
  })
  it('nextMonth: после последнего, с переходом года; без месяцев — текущий', () => {
    expect(nextMonth(months)).toEqual({ year: 2026, month: 2 })
    expect(nextMonth(months.slice(0, 2))).toEqual({ year: 2026, month: 1 })
    expect(nextMonth([], new Date(2026, 10, 1))).toEqual({ year: 2026, month: 11 })
  })
  it('fillState: полностью, частично, пусто', () => {
    expect(months.map(fillState)).toEqual(['full', 'partial', 'empty'])
    expect(fillState({ filled_metrics: 0, total_metrics: 0 })).toBe('empty')
    expect(fillState(null)).toBe('empty')
  })
  it('groupMonthsByYear: новые годы сверху, месяцы по порядку', () => {
    const shuffled = [months[2], months[1], months[0]]
    expect(groupMonthsByYear(shuffled).map((g) => [g.year, g.months.map((m) => m.month)])).toEqual([[2026, [1]], [2025, [11, 12]]])
    expect(groupMonthsByYear([])).toEqual([])
  })
  it('pickMonth: из адреса, иначе последний', () => {
    expect(pickMonth(months, '2025-12')).toBe('2025-12')
    expect(pickMonth(months, '2024-01')).toBe('2026-01')
    expect(pickMonth(months, '')).toBe('2026-01')
    expect(pickMonth([], '2025-12')).toBe('')
  })
})
