import { describe, expect, it } from 'vitest'
import { availableMetrics, bulletScale, emptyTargetForm, groupByYear, statusLabel, targetPayload, targetToForm } from './hrTargets'

const row = (over = {}) => ({
  id: 1, metric_key: 'turnover', metric_label: 'Текучесть', unit: '%', year: 2026, label: 'Цель 2026', reference_value: null,
  target_value: 5, current_value: 2, current_month: 'Июль 2026', diff: -3, status: 'green', direction: 'lower_is_better',
  description: '', source: '', ...over,
})

describe('статусы', () => {
  it('statusLabel: справочно, нет данных, по статусу', () => {
    expect(statusLabel(row())).toBe('Цель достигнута')
    expect(statusLabel(row({ status: 'yellow' }))).toBe('Близко к цели')
    expect(statusLabel(row({ status: 'red' }))).toBe('Цель не достигнута')
    expect(statusLabel(row({ target_value: null, status: 'gray' }))).toBe('Справочно')
    expect(statusLabel(row({ current_value: null, status: 'gray' }))).toBe('Нет данных')
  })
  it('groupByYear: новые годы сверху, счётчики статусов и целей', () => {
    const groups = groupByYear([
      row({ id: 1, year: 2025, target_value: null, status: 'gray' }),
      row({ id: 2 }), row({ id: 3, status: 'yellow' }), row({ id: 4, status: 'red' }),
    ])
    expect(groups.map((g) => g.year)).toEqual([2026, 2025])
    expect(groups[0].counts).toEqual({ green: 1, yellow: 1, red: 1, gray: 0 })
    expect(groups[0].withTarget).toBe(3)
    expect(groups[1].withTarget).toBe(0)
    expect(groupByYear(null)).toEqual([])
  })
})

describe('шкала выполнения', () => {
  it('bulletScale: доли от общего максимума с запасом', () => {
    const s = bulletScale(row({ current_value: 33, target_value: 30, direction: 'lower_is_better' }))
    expect(s.current).toBeCloseTo(33 / (33 * 1.15))
    expect(s.target).toBeCloseTo(30 / (33 * 1.15))
    expect(s.reference).toBeNull()
    expect(s.zone).toEqual({ from: 0, to: s.target })
  })
  it('bulletScale: зона выполнения для «больше — лучше» — правее цели', () => {
    const s = bulletScale(row({ current_value: 80, target_value: 90, reference_value: 70, direction: 'higher_is_better' }))
    expect(s.zone).toEqual({ from: s.target, to: 1 })
    expect(s.reference).toBeLessThan(s.current)
  })
  it('bulletScale: без цели — без зоны; без значений — null; нули не ломают шкалу', () => {
    expect(bulletScale(row({ target_value: null, reference_value: 5.17 })).zone).toBeNull()
    expect(bulletScale(row({ current_value: null, target_value: null }))).toBeNull()
    const zero = bulletScale(row({ current_value: 0, target_value: 0 }))
    expect(zero.current).toBe(0)
    expect(zero.target).toBe(0)
  })
  it('bulletScale: отрицательные значения прижимаются к нулю', () => {
    expect(bulletScale(row({ current_value: -2, target_value: 4 })).current).toBe(0)
  })
})

describe('форма цели', () => {
  const defs = [{ key: 'turnover' }, { key: 'avg_time_to_fill' }, { key: 'offers' }]
  const rows = [row(), row({ id: 2, metric_key: 'offers', year: 2025 })]
  it('availableMetrics: без метрик, у которых уже есть цель на этот год', () => {
    expect(availableMetrics(defs, rows, 2026).map((d) => d.key)).toEqual(['avg_time_to_fill', 'offers'])
    expect(availableMetrics(defs, rows, '2025').map((d) => d.key)).toEqual(['turnover', 'avg_time_to_fill'])
    expect(availableMetrics(defs, rows, 2026, 'turnover').map((d) => d.key)).toEqual(['turnover', 'avg_time_to_fill', 'offers'])
  })
  it('targetToForm: числа с запятой, пустые — пустые строки', () => {
    expect(targetToForm(row({ target_value: 92.5, reference_value: null, description: 'Описание' }))).toEqual({
      metric_key: 'turnover', year: 2026, target_value: '92,5', reference_value: '', label: 'Цель 2026', description: 'Описание', source: '',
    })
  })
  it('targetPayload: новая цель', () => {
    const form = { ...emptyTargetForm(2027), metric_key: 'turnover', target_value: '4,5', label: '  План ' }
    expect(targetPayload(form)).toEqual({
      errors: {},
      body: { metric_key: 'turnover', year: 2027, target_value: 4.5, reference_value: null, label: 'План', description: '', source: '' },
    })
  })
  it('targetPayload: при изменении метрика и год не отправляются', () => {
    const { body, errors } = targetPayload({ ...targetToForm(row()), reference_value: '5,17' }, { editing: true })
    expect(errors).toEqual({})
    expect(body).toEqual({ target_value: 5, reference_value: 5.17, label: 'Цель 2026', description: '', source: '' })
  })
  it('targetPayload: ошибки полей', () => {
    expect(targetPayload({ ...emptyTargetForm(1999), target_value: 'x' }).errors)
      .toEqual({ target_value: 'Введите число', metric_key: 'Выберите метрику', year: 'Год от 2000 до 2100' })
    expect(targetPayload({ ...emptyTargetForm(2026), metric_key: 'turnover' }).errors)
      .toEqual({ target_value: 'Укажите цель или справочное значение' })
  })
})
