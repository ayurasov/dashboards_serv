import { describe, expect, it } from 'vitest'
import {
  WIDGET_SPAN, WIDGET_TYPES, changeType, isMulti, latestFilled, moveItem, newWidget, sortWidgets, splitDashboards, toEditor,
  toPayload, unitAxes, validateWidget, valuesOf, widgetKeys, widgetTitle,
} from './hrWidgets'

const defs = [
  { key: 'turnover', label: 'Текучесть кадров', unit: '%' },
  { key: 'offers', label: 'Принятые офферы', unit: '%' },
  { key: 'time', label: 'Время закрытия', unit: 'дн.' },
  { key: 'count', label: 'Нанято', unit: 'чел.' },
]

const month = (key, values) => ({ key, label: key, metrics: Object.entries(values).map(([k, value]) => ({ key: k, value, light: 'green' })) })
const SERIES = [month('2026-01', { turnover: 1, time: 30 }), month('2026-02', { turnover: 1.5, time: null }), month('2026-03', { turnover: null })]

describe('виджеты', () => {
  it('у каждого типа есть подпись и ширина', () => {
    for (const t of WIDGET_TYPES) expect(WIDGET_SPAN[t.value]).toBeGreaterThan(0)
    expect(WIDGET_TYPES.filter((t) => isMulti(t.value)).map((t) => t.value)).toEqual(['line_chart', 'bar_chart', 'table'])
  })
  it('widgetKeys: метрики по типу виджета', () => {
    expect(widgetKeys({ widget_type: 'metric_card', config: { metric_key: 'turnover' } })).toEqual(['turnover'])
    expect(widgetKeys({ widget_type: 'metric_card', config: {} })).toEqual([])
    expect(widgetKeys({ widget_type: 'line_chart', config: { metric_keys: ['a', '', 'b'] } })).toEqual(['a', 'b'])
    expect(widgetKeys({ widget_type: 'table', config: { metric_keys: 'a' } })).toEqual([])
    expect(widgetKeys({ widget_type: 'note', config: { text: 'x', metric_keys: ['a'] } })).toEqual([])
  })
  it('widgetTitle: свой заголовок, название метрики или тип', () => {
    expect(widgetTitle({ widget_type: 'table', title: '  Найм ' }, defs)).toBe('Найм')
    expect(widgetTitle({ widget_type: 'metric_card', title: '', config: { metric_key: 'time' } }, defs)).toBe('Время закрытия')
    expect(widgetTitle({ widget_type: 'bar_chart', title: '' }, defs)).toBe('Столбчатая диаграмма')
    expect(widgetTitle({ widget_type: 'unknown' }, defs)).toBe('Виджет')
  })
  it('sortWidgets: по sort_order без изменения исходного списка', () => {
    const list = [{ id: 1, sort_order: 2 }, { id: 2, sort_order: 0 }, { id: 3, sort_order: 1 }]
    expect(sortWidgets(list).map((w) => w.id)).toEqual([2, 3, 1])
    expect(list[0].id).toBe(1)
  })
})

describe('редактор', () => {
  it('toEditor → toPayload: туда и обратно по каждому типу', () => {
    const widgets = [
      { widget_type: 'metric_card', title: 'Текучесть', config: { metric_key: 'turnover' } },
      { widget_type: 'line_chart', title: '', config: { metric_keys: ['turnover', 'offers'] } },
      { widget_type: 'note', title: 'Важно', config: { text: 'Сверить с 1С' } },
    ]
    for (const w of widgets) expect(toPayload(toEditor(w))).toEqual(w)
  })
  it('toEditor: у строк разные uid, списки метрик копируются', () => {
    const source = { widget_type: 'table', config: { metric_keys: ['a'] } }
    const a = toEditor(source)
    const b = toEditor(source)
    expect(a.uid).not.toBe(b.uid)
    a.metric_keys.push('b')
    expect(source.config.metric_keys).toEqual(['a'])
  })
  it('toPayload: текст заметки и заголовок без пробелов по краям', () => {
    expect(toPayload({ ...newWidget('note'), title: ' Итог ', text: ' Текст ' })).toEqual({ widget_type: 'note', title: 'Итог', config: { text: 'Текст' } })
  })
  it('changeType: выбранные метрики переносятся', () => {
    const card = { ...newWidget('metric_card'), metric_key: 'turnover' }
    expect(changeType(card, 'line_chart').metric_keys).toEqual(['turnover'])
    const chart = { ...newWidget('bar_chart'), metric_keys: ['offers', 'time'] }
    expect(changeType(chart, 'metric_card').metric_key).toBe('offers')
    expect(changeType(chart, 'table').metric_keys).toEqual(['offers', 'time'])
  })
  it('validateWidget: метрики и текст обязательны', () => {
    expect(validateWidget(newWidget('metric_card'))).toBe('Выберите метрику')
    expect(validateWidget(newWidget('table'))).toBe('Выберите хотя бы одну метрику')
    expect(validateWidget({ ...newWidget('note'), text: '  ' })).toBe('Введите текст заметки')
    expect(validateWidget({ ...newWidget('line_chart'), metric_keys: ['a'] })).toBe('')
  })
  it('moveItem: перестановка с соседом, за край — без изменений', () => {
    expect(moveItem(['a', 'b', 'c'], 0, 1)).toEqual(['b', 'a', 'c'])
    expect(moveItem(['a', 'b', 'c'], 2, -1)).toEqual(['a', 'c', 'b'])
    const list = ['a', 'b']
    expect(moveItem(list, 0, -1)).toBe(list)
    expect(moveItem(list, 1, 1)).toBe(list)
  })
})

describe('данные виджетов', () => {
  it('latestFilled: последний месяц, где метрика заполнена', () => {
    expect(latestFilled(SERIES, 'turnover').month.key).toBe('2026-02')
    expect(latestFilled(SERIES, 'time').metric.value).toBe(30)
    expect(latestFilled(SERIES, 'count')).toBeNull()
    expect(latestFilled([], 'turnover')).toBeNull()
  })
  it('valuesOf: значения по месяцам, пропуски — null', () => {
    expect(valuesOf(SERIES, 'turnover')).toEqual([1, 1.5, null])
    expect(valuesOf(SERIES, 'count')).toEqual([null, null, null])
  })
  it('unitAxes: одна единица — одна ось, две — две, больше — общая', () => {
    const one = unitAxes(defs.slice(0, 2))
    expect(one.units).toEqual(['%'])
    expect(one.axisOf(defs[1])).toBe(0)
    const two = unitAxes(defs.slice(0, 3))
    expect(two.units).toEqual(['%', 'дн.'])
    expect(two.axisOf(defs[2])).toBe(1)
    const many = unitAxes(defs)
    expect(many.units).toEqual([''])
    expect(many.axisOf(defs[3])).toBe(0)
  })
  it('splitDashboards: свои и общие чужие', () => {
    const list = [{ id: 1, owner_id: 7 }, { id: 2, owner_id: 3, is_shared: true }, { id: 3, owner_id: 7, is_shared: true }]
    const { mine, shared } = splitDashboards(list, 7)
    expect(mine.map((d) => d.id)).toEqual([1, 3])
    expect(shared.map((d) => d.id)).toEqual([2])
  })
})
