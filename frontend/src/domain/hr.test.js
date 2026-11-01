import { describe, expect, it } from 'vitest'
import { FUNNEL, KEY_METRICS, QUICK_PERIODS, funnelSteps, groupByCategory, kpiHint, kpiLabel, lastMonths, metricMap, metricSeries } from './hr'

const metric = (key, value, over = {}) => ({ key, value, label: key, category: 'hiring', category_label: 'Подбор', ...over })

describe('периоды', () => {
  const keys = ['2026-01', '2026-02', '2026-03', '2026-04']
  it('lastMonths: последние N месяцев, 0 — все', () => {
    expect(lastMonths(keys, 2)).toEqual(['2026-03', '2026-04'])
    expect(lastMonths(keys, 12)).toEqual(keys)
    expect(lastMonths(keys, 0)).toEqual(keys)
    expect(lastMonths(keys, 0)).not.toBe(keys)
    expect(lastMonths([], 3)).toEqual([])
  })
  it('QUICK_PERIODS: «Все» — последний вариант, значения уникальны', () => {
    expect(QUICK_PERIODS.at(-1)).toEqual({ value: 0, label: 'Все' })
    expect(new Set(QUICK_PERIODS.map((q) => q.value)).size).toBe(QUICK_PERIODS.length)
  })
})

describe('метрики месяца', () => {
  const latest = { metrics: [metric('turnover', 2, { category: 'turnover', category_label: 'Текучесть' }), metric('resumes_screened', 200)] }
  it('metricMap: словарь по ключу, пустой ряд — пустой словарь', () => {
    expect(metricMap(latest).turnover.value).toBe(2)
    expect(metricMap(null)).toEqual({})
    expect(metricMap({})).toEqual({})
  })
  it('metricSeries: значения метрики по месяцам, нет метрики — null', () => {
    const series = [{ metrics: [metric('turnover', 1)] }, { metrics: [metric('turnover', null)] }, { metrics: [] }]
    expect(metricSeries(series, 'turnover')).toEqual([1, null, null])
  })
  it('groupByCategory: группы в порядке появления, метрики внутри — по порядку', () => {
    const groups = groupByCategory([
      metric('a', 1), metric('b', 2, { category: 'turnover', category_label: 'Текучесть' }), metric('c', 3),
    ])
    expect(groups.map((g) => [g.key, g.label, g.items.map((m) => m.key)])).toEqual([
      ['hiring', 'Подбор', ['a', 'c']], ['turnover', 'Текучесть', ['b']],
    ])
    expect(groupByCategory([])).toEqual([])
  })
  it('KEY_METRICS: без повторов', () => {
    expect(new Set(KEY_METRICS).size).toBe(KEY_METRICS.length)
  })
})

describe('воронка найма', () => {
  it('funnelSteps: доля к первому шагу с одним знаком после запятой', () => {
    const latest = { metrics: [metric('resumes_screened', 300), metric('interviews_hr', 75), metric('interviews_hm', 20), metric('hired_count', 4)] }
    const steps = funnelSteps(latest)
    expect(steps.map((s) => s.key)).toEqual(FUNNEL.map((s) => s.key))
    expect(steps.map((s) => s.share)).toEqual([100, 25, 6.7, 1.3])
    expect(steps[0].label).toBe('Отобрано резюме')
  })
  it('funnelSteps: без первого шага доли не считаются, пропуски — null', () => {
    const steps = funnelSteps({ metrics: [metric('interviews_hr', 10)] })
    expect(steps.map((s) => s.value)).toEqual([null, 10, null, null])
    expect(steps.every((s) => s.share === null)).toBe(true)
  })
  it('funnelSteps: нулевой первый шаг не делит на ноль', () => {
    const steps = funnelSteps({ metrics: [metric('resumes_screened', 0), metric('interviews_hr', 0)] })
    expect(steps.every((s) => s.share === null)).toBe(true)
  })
  it('funnelSteps: пустой месяц', () => {
    expect(funnelSteps(null).map((s) => s.value)).toEqual([null, null, null, null])
  })
})

describe('подписи карточек ключевых показателей', () => {
  it('kpiLabel: длинные названия заменяются короткими и различимыми', () => {
    const general = { key: 'probation_pass_rate', label: 'Прохождение испытательного срока (общее)' }
    const adaptation = { key: 'probation_pass_rate_adaptation', label: 'Прохождение испытательного срока (адаптация)' }
    expect(kpiLabel(general)).not.toBe(kpiLabel(adaptation))
    // Первые 30 символов (две строки карточки) у подписей разные
    expect(kpiLabel(general).slice(0, 30)).not.toBe(kpiLabel(adaptation).slice(0, 30))
    expect(kpiLabel({ key: 'turnover', label: 'Текучесть кадров' })).toBe('Текучесть кадров')
    expect(kpiLabel(null)).toBe('')
  })
  it('у каждой метрики KEY_METRICS короткая подпись не длиннее 40 символов', () => {
    for (const key of KEY_METRICS) expect(kpiLabel({ key, label: key }).length).toBeLessThanOrEqual(40)
  })
  it('kpiHint: полное название и описание без повторов', () => {
    expect(kpiHint({ label: 'Текучесть', description: 'Доля уволенных' })).toBe('Текучесть — Доля уволенных')
    expect(kpiHint({ label: 'Текучесть', description: 'Текучесть' })).toBe('Текучесть')
    expect(kpiHint({ label: 'Текучесть' })).toBe('Текучесть')
  })
})
