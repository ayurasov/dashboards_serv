import { describe, expect, it } from 'vitest'
import {
  accessLine, ancestorIds, reasonParts, reasonText, buildTree, canEnterCell, cellCounts, cellErrors, cellStateText, cellTooltip, cellView, entryChanges,
  IMPORT_ACTIONS, entryDraft, entryKey, entryOriginal, entryPeriods, entryRows, evaluateRule, expandToDepth, expectedEmpty, filterImportRows,
  filteredCount, groupByClass, hasViolation, importChips, matchesFilter, matrixColumns, matrixRows, noteByline, parseInput,
  ratedIndicators, resolveReportView, ruleBands, ruleSummary, shortNumber, sortIndicators, sourceText, statusSegments,
  templateCsv, toInput, treeDepth, trendOption, trendPointText, unitsByStatus, violationsText,
} from './reports'

const cell = (value, status = 'green', over = {}) => ({
  value, target: null, previous: null, delta: null, status, status_label: { green: 'Норма', yellow: 'Внимание', red: 'Критично', gray: 'Нет оценки' }[status],
  missing: false, deviation: null, source: 'manual', source_label: 'введено', rollup_count: 0, comment: '', ...over,
})
const unit = (id, name, parent_id = null, over = {}) => ({
  id, name, parent_id, code: null, kind: 'service', kind_label: 'Служба', level: 1, depth: 0, path: name, child_ids: [],
  drill_locked: false, status: 'green', status_label: 'Норма', indicator_count: 0, rated_count: 0, missing: [], missing_total: 0,
  note: null, cells: {}, explanation: { status: 'green', text: '', items: [], more: 0 }, ...over,
})

// Компания → Коммерческая (Маркетинг с пропуском) · Техническая (Служба → Группа) · Проектная
const UNITS = [
  unit(8, 'Компания', null, { status: 'red', missing_total: 1, cells: { 'fin.revenue': cell(92.9, 'yellow'), 'ops.plan': cell(96.25) } }),
  unit(10, 'Коммерческая', 8, { status: 'yellow', missing_total: 1, cells: { 'fin.revenue': cell(53.5, 'yellow') } }),
  unit(4, 'Маркетинг', 10, { status: 'yellow', missing: [{ indicator: 'ops.plan', name: 'Выполнение плана работ' }], missing_total: 1, cells: { 'ops.plan': cell(null, 'gray', { missing: true, status_label: 'Нет данных' }) } }),
  unit(11, 'Техническая', 8, { status: 'red', cells: { 'tech.in_work': cell(274, 'red') } }),
  unit(3, 'Служба ТП', 11, { status: 'red', cells: { 'tech.in_work': cell(274, 'red') } }),
  unit(12, 'Группа', 3, { status: 'green', cells: {} }),
  unit(6, 'Проектная', 8, { status: 'yellow', drill_locked: true, missing_total: 2, cells: {} }),
]
const IND = [
  { key: 'fin.revenue', name: 'Выручка', unit: 'млн ₽', direction: 'higher_is_better', rule_type: 'target', green_deviation: 5, yellow_deviation: 15, data_class: 'financial' },
  { key: 'ops.plan', name: 'Выполнение плана работ', unit: '%', direction: 'higher_is_better', rule_type: 'target', green_deviation: 5, yellow_deviation: 15, data_class: 'operational' },
  { key: 'tech.in_work', name: 'Заявки в работе', unit: 'шт.', direction: 'lower_is_better', rule_type: 'threshold', green_threshold: 180, yellow_threshold: 220, data_class: 'operational' },
  { key: 'ops.csat', name: 'Удовлетворённость', unit: 'из 5', direction: 'higher_is_better', rule_type: 'threshold', green_threshold: 4.5, yellow_threshold: 4, data_class: 'operational' },
]

describe('доступ', () => {
  it('убирает перечень скрытых классов из строки доступа и пишет его заметкой', () => {
    const one = accessLine({ text: 'Ваш доступ: своя ветка структуры · детализация без ограничения · скрыты: финансовые', hidden_classes: ['Финансовые'] })
    expect(one).toEqual({ text: 'Ваш доступ: своя ветка структуры · детализация без ограничения', hidden: 'Финансовые показатели скрыты' })
    const two = accessLine({ text: 'Ваш доступ: своё подразделение · без детализации · скрыты: персональные, финансовые', hidden_classes: ['Персональные', 'Финансовые'] })
    expect(two.hidden).toBe('Персональные и финансовые показатели скрыты')
    expect(two.text).toBe('Ваш доступ: своё подразделение · без детализации')
    expect(accessLine({ text: 'Ваш доступ: вся компания', hidden_classes: [] }).hidden).toBe('')
    expect(accessLine(null)).toEqual({ text: '', hidden: '' })
  })
})

describe('дерево отчёта', () => {
  it('строит лес из плоского списка в порядке ответа', () => {
    const forest = buildTree(UNITS)
    expect(forest.map((n) => n.id)).toEqual([8])
    expect(forest[0].children.map((n) => n.id)).toEqual([10, 11, 6])
    expect(forest[0].children[1].children[0].children[0]).toMatchObject({ id: 12, depth: 3 })
    expect(treeDepth(forest)).toBe(4)
    expect(ancestorIds(forest, 12)).toEqual([8, 11, 3])
    expect(ancestorIds(forest, 99)).toEqual([])
  })
  it('родитель вне списка — вершина; цикл не теряет подразделения', () => {
    const forest = buildTree([unit(3, 'Служба', 11), unit(12, 'Группа', 3), unit(13, 'Вторая', 3)])
    expect(forest.map((n) => n.id)).toEqual([3])
    expect(forest[0].children.map((n) => n.depth)).toEqual([1, 1])
    const cyclic = buildTree([unit(1, 'А', 2), unit(2, 'Б', 1)])
    expect(cyclic.map((n) => n.id).sort()).toEqual([1, 2])
  })
  it('раскрывает уровни до заданной глубины', () => {
    const forest = buildTree(UNITS)
    expect([...expandToDepth(forest, 0)]).toEqual([])
    expect([...expandToDepth(forest, 1)]).toEqual([8])
    expect([...expandToDepth(forest, 2)].sort()).toEqual([10, 11, 8])
    expect([...expandToDepth(forest, null)].sort((a, b) => a - b)).toEqual([3, 8, 10, 11])
  })
})

describe('матрица', () => {
  const forest = buildTree(UNITS)
  it('строки по раскрытию', () => {
    expect(matrixRows(forest, new Set([8])).map((r) => r.id)).toEqual([8, 10, 11, 6])
    const rows = matrixRows(forest, expandToDepth(forest, null))
    expect(rows.map((r) => r.id)).toEqual([8, 10, 4, 11, 3, 12, 6])
    expect(rows[0]).toMatchObject({ hasChildren: true, open: true, depth: 0, match: true })
    expect(rows.find((r) => r.id === 12)).toMatchObject({ hasChildren: false, depth: 3 })
  })
  it('фильтр по статусу оставляет предков как контекст и раскрывает ветки', () => {
    const rows = matrixRows(forest, new Set(), { status: 'red' })
    expect(rows.map((r) => [r.id, r.match])).toEqual([[8, true], [11, true], [3, true]])
    const yellow = matrixRows(forest, new Set(), { status: 'yellow' })
    expect(yellow.map((r) => [r.id, r.match])).toEqual([[8, false], [10, true], [4, true], [6, true]])
    expect(matrixRows(forest, new Set(), { status: 'gray' })).toEqual([])
  })
  it('«только с нарушениями»: свои пропуски и пропуски за пределом детализации', () => {
    expect(hasViolation(UNITS[2])).toBe(true)
    expect(hasViolation(UNITS[1])).toBe(false) // пропуск виден ниже — у «Маркетинга»
    expect(hasViolation(UNITS[6])).toBe(true) // детализация недоступна, пропуски внутри
    const rows = matrixRows(forest, new Set(), { violations: true })
    expect(rows.map((r) => [r.id, r.match])).toEqual([[8, false], [10, false], [4, true], [6, true]])
    expect(matrixRows(forest, new Set(), { violations: true, status: 'yellow' }).filter((r) => r.match).map((r) => r.id)).toEqual([4, 6])
    expect(matchesFilter(UNITS[0], {})).toBe(true)
    expect(filteredCount(UNITS, { status: 'yellow' })).toBe(3)
  })
  it('столбцы — показатели со значениями; пустые отдельно', () => {
    const { columns, empty } = matrixColumns(IND, UNITS)
    expect(columns.map((c) => c.key)).toEqual(['fin.revenue', 'ops.plan', 'tech.in_work'])
    expect(empty.map((c) => c.key)).toEqual(['ops.csat'])
    expect(matrixColumns(IND, UNITS, { all: true }).columns).toHaveLength(4)
  })
})

describe('ячейки', () => {
  it('число по величине в ru-RU', () => {
    expect(shortNumber(274)).toBe('274')
    expect(shortNumber(96.25)).toBe('96,3')
    expect(shortNumber(4.6333)).toBe('4,63')
    expect(shortNumber(-1.5)).toBe('−1,5')
    expect(shortNumber(1234567)).toBe('1,2 млн')
    expect(shortNumber(null)).toBe('—')
  })
  it('вид ячейки: статус, стрелка и её оценка по направлению', () => {
    const v = cellView(cell(274, 'red', { delta: -30 }), IND[2])
    expect(v).toMatchObject({ tone: 'red', text: '274', arrow: 'down', trend: 'good' })
    expect(v.label).toBe('274 шт., Критично')
    expect(cellView(cell(53.5, 'yellow', { delta: -5 }), IND[0])).toMatchObject({ arrow: 'down', trend: 'bad' })
    expect(cellView(cell(5, 'gray', { delta: 0 }), { direction: 'neutral' })).toMatchObject({ arrow: null, trend: 'flat', tone: 'gray' })
    expect(cellView(cell(null, 'gray', { missing: true }), IND[1])).toMatchObject({ tone: 'missing', text: 'Нет данных' })
    expect(cellView(undefined, IND[1])).toMatchObject({ tone: 'none', text: '—' })
  })
  it('подсказка: значение, цель, отклонение, изменение, источник, комментарий', () => {
    const tip = cellTooltip(cell(53.5, 'yellow', { target: 60.1, deviation: 11, previous: 58.5, delta: -5, source_label: 'сумма по 1 подразделению', comment: 'Сдвиг оплаты' }), IND[0], 'Коммерческая')
    expect(tip).toMatchObject({ title: 'Выручка', subtitle: 'Коммерческая', tone: 'yellow', status: 'Внимание', comment: 'Сдвиг оплаты' })
    expect(tip.rows).toEqual([
      { label: 'Значение', value: '53,5 млн ₽' },
      { label: 'Цель', value: '60,1 млн ₽' },
      { label: 'Отклонение от цели', value: '11%' },
      { label: 'К прошлому месяцу', value: '−5 млн ₽ · было 58,5 млн ₽', trend: 'bad' },
      { label: 'Источник', value: 'сумма по 1 подразделению' },
    ])
    const threshold = cellTooltip(cell(274, 'red'), IND[2], 'Техническая')
    expect(threshold.rows.find((r) => r.label === 'Правило').value).toBe('Норма ≤ 180 шт. · внимание ≤ 220 шт.')
    const missing = cellTooltip(cell(null, 'gray', { missing: true, target: 100, source_label: '' }), IND[1], 'Маркетинг')
    expect(missing).toMatchObject({ tone: 'missing', status: 'Нет данных' })
    expect(missing.rows[0]).toEqual({ label: 'Значение', value: 'Не заполнено' })
    expect(missing.note).toContain('критичное нарушение')
    expect(cellTooltip(null, IND[1], 'Группа')).toMatchObject({ tone: 'none', rows: [] })
  })
  it('счётчики, полоса статусов, подразделения по статусам, оценённые показатели', () => {
    expect(cellCounts(UNITS[0])).toEqual({ red: 0, yellow: 1, green: 1, gray: 0, missing: 0 })
    expect(cellCounts(UNITS[2])).toMatchObject({ missing: 1, gray: 0 })
    expect(statusSegments({ green: 1, yellow: 2, red: 2, gray: 0 })).toEqual([
      { light: 'red', value: 2, share: 0.4 }, { light: 'yellow', value: 2, share: 0.4 }, { light: 'green', value: 1, share: 0.2 },
    ])
    const by = unitsByStatus(UNITS, [8])
    expect(by.red.map((u) => u.id)).toEqual([11, 3])
    expect(by.yellow.map((u) => u.id)).toEqual([10, 4, 6])
    expect(ratedIndicators(UNITS)).toBe(3)
  })
  it('пропуски: видимые и за пределом детализации', () => {
    expect(violationsText({ violations: [{ unit_id: 4, unit_name: 'Маркетинг', indicator: 'ops.plan', indicator_name: 'План' }], hidden_violations: 0 }))
      .toEqual({ items: [{ unit_id: 4, unit_name: 'Маркетинг', indicator: 'ops.plan', indicator_name: 'План', text: 'План — Маркетинг' }], hidden: '' })
    expect(violationsText({ violations: [], hidden_violations: 1 }).hidden).toBe('1 пропуск во вложенных подразделениях (детализация недоступна)')
    expect(violationsText({ violations: [{ indicator_name: 'А', unit_name: 'Б' }], hidden_violations: 3 }).hidden).toBe('ещё 3 пропуска во вложенных подразделениях (детализация недоступна)')
  })
  it('причины статуса: без цветового префикса, название показателя отдельно', () => {
    expect(reasonText('Красный: Заявки в работе в «Техническая дирекция» — 274 шт.; ещё 2')).toBe('Заявки в работе в «Техническая дирекция» — 274 шт.')
    expect(reasonText('Зелёный: все оценённые показатели в норме')).toBe('Все оценённые показатели в норме')
    expect(reasonParts({ indicator_name: 'Затраты', text: 'Красный: Затраты — во вложенных подразделениях «ТД» (детализация недоступна)' }))
      .toEqual({ lead: 'Затраты', rest: ' — во вложенных подразделениях «ТД» (детализация недоступна)' })
    expect(reasonParts({ indicator_name: 'План', text: 'Жёлтый: Иное' })).toEqual({ lead: '', rest: 'Иное' })
  })
  it('заметка и порядок показателей панели', () => {
    expect(noteByline({ author: { full_name: 'Петров Илья Сергеевич' }, created_at: '2026-11-01T09:30:00' })).toBe('Петров Илья Сергеевич · 01.11.2026')
    expect(noteByline(null)).toBe('')
    const items = [{ key: 'a', cell: cell(1) }, { key: 'b', cell: cell(1, 'red') }, { key: 'c', cell: null }, { key: 'd', cell: cell(null, 'gray', { missing: true }) }, { key: 'e', cell: cell(1, 'yellow') }]
    expect(sortIndicators(items).map((i) => i.key)).toEqual(['d', 'b', 'e', 'a', 'c'])
  })
  it('вид страницы: из адреса, иначе по ширине экрана', () => {
    expect(resolveReportView('chart')).toBe('chart')
    expect(resolveReportView('', true)).toBe('list')
    expect(resolveReportView('bogus')).toBe('matrix')
  })
})

describe('правило светофора', () => {
  it('словами', () => {
    expect(ruleSummary(IND[0])).toBe('Отклонение от цели: до 5% — норма, до 15% — внимание')
    expect(ruleSummary(IND[3])).toBe('Норма ≥ 4,5 из 5 · внимание ≥ 4 из 5')
    expect(ruleSummary({ direction: 'neutral' })).toBe('Без оценки')
    expect(ruleSummary({ direction: 'higher_is_better', rule_type: 'threshold' })).toBe('Без светофора')
    expect(sourceText({ source_type: 'computed', source_name: 'Текучесть кадров' })).toBe('Вычисляется: Текучесть кадров')
    expect(sourceText({ source_type: 'manual', owner_service_title: 'Финансовая служба' })).toBe('Вводит: Финансовая служба')
  })
  it('оценка как на сервере', () => {
    const target = { direction: 'higher_is_better', rule_type: 'target', green_deviation: 5, yellow_deviation: 15 }
    expect(evaluateRule(target, 96, 100)).toBe('green')
    expect(evaluateRule(target, 89, 100)).toBe('yellow')
    expect(evaluateRule(target, 78, 100)).toBe('red')
    expect(evaluateRule(target, 120, 100)).toBe('green')
    expect(evaluateRule({ ...target, direction: 'lower_is_better', green_deviation: 3, yellow_deviation: 8 }, 12.4, 11.3)).toBe('red')
    expect(evaluateRule(target, 5, null)).toBe('gray')
    expect(evaluateRule(IND[2], 274)).toBe('red')
    expect(evaluateRule(IND[2], 200)).toBe('yellow')
    expect(evaluateRule(IND[3], 4.6)).toBe('green')
    expect(evaluateRule(IND[3], 3.9)).toBe('red')
    expect(evaluateRule({ direction: 'neutral', rule_type: 'threshold', green_threshold: 1 }, 5)).toBe('gray')
  })
  it('полосы предпросмотра', () => {
    expect(ruleBands({ ...IND[2] }).bands.map((b) => [b.light, b.text])).toEqual([['green', '≤ 180 шт.'], ['yellow', '≤ 220 шт.'], ['red', '> 220 шт.']])
    expect(ruleBands(IND[3]).bands.map((b) => b.light)).toEqual(['red', 'yellow', 'green'])
    expect(ruleBands({ ...IND[3], green_threshold: 3 }).warning).toContain('не меньше')
    const t = ruleBands({ direction: 'higher_is_better', rule_type: 'target', green_deviation: 5, yellow_deviation: 15, default_target: 100, unit: '%' })
    expect(t.bands.map((b) => b.text)).toEqual(['ниже −15%', 'от −15% (85%)', 'от −5% (95%)'])
    const low = ruleBands({ direction: 'lower_is_better', rule_type: 'target', green_deviation: 3, yellow_deviation: 8 })
    expect(low.bands.map((b) => [b.light, b.text])).toEqual([['green', 'до +3%'], ['yellow', 'до +8%'], ['red', 'больше +8%']])
    expect(ruleBands({ direction: 'neutral' }).bands).toEqual([])
    expect(ruleBands({ direction: 'higher_is_better', rule_type: 'threshold' }).empty).toContain('Пороги не заданы')
    expect(ruleBands({ direction: 'higher_is_better', rule_type: 'target', green_deviation: 20, yellow_deviation: 10 }).warning).toContain('Отклонение для нормы')
  })
  it('каталог по классам данных', () => {
    const groups = groupByClass(IND, [{ key: 'financial', label: 'Финансовые' }, { key: 'operational', label: 'Операционные' }, { key: 'personal', label: 'Персональные' }])
    expect(groups.map((g) => [g.label, g.items.length])).toEqual([['Финансовые', 1], ['Операционные', 3]])
  })
})

describe('тренд за 12 месяцев', () => {
  const trend = [
    { period: '2026-05', label: 'Май 2026', value: 93, target: 100, status: 'yellow', missing: false },
    { period: '2026-06', label: 'Июнь 2026', value: 94, target: 100, status: 'yellow', missing: false },
    { period: '2026-07', label: 'Июль 2026', value: null, target: 100, status: 'gray', missing: true },
  ]
  it('линия значений с цветом статуса, пунктир цели и отметка пропуска', () => {
    const option = trendOption(trend, { unit: '%', colors: { light: (s) => `c-${s}`, line: 'L', target: 'T', missing: 'M', surface: 'S' } })
    const [values, target, gaps] = option.series
    expect(option.xAxis.data).toEqual(['Май 2026', 'Июнь 2026', 'Июль 2026'])
    expect(values.data[0]).toMatchObject({ value: 93, itemStyle: { color: 'c-yellow' }, symbolSize: 5 })
    expect(values.data[2]).toBeNull()
    expect(values.connectNulls).toBe(false)
    expect(values.markLine.data).toEqual([{ xAxis: 'Июль 2026' }])
    expect(values.markLine.lineStyle.color).toBe('M')
    expect(target).toMatchObject({ name: 'Цель', data: [100, 100, 100], symbol: 'none' })
    expect(target.lineStyle).toMatchObject({ color: 'T' })
    // Кольцо пропуска — на уровне цели месяца
    expect(gaps).toMatchObject({ name: 'Не заполнено', type: 'scatter', data: [null, null, 100] })
    expect(gaps.itemStyle).toMatchObject({ color: 'S', borderColor: 'M' })
    expect(option.tooltip.formatter([{ dataIndex: 2 }])).toBe('<b>Июль 2026</b><br/>Не заполнено — критичное нарушение<br/>Цель: 100%')
  })
  it('пропуск без цели — кольцо на уровне последнего значения', () => {
    const option = trendOption([{ label: 'А', value: 5, status: 'green' }, { label: 'Б', value: null, target: null, status: 'gray', missing: true }])
    expect(option.series.at(-1).data).toEqual([null, 5])
  })
  it('без цели — одна линия, последняя точка крупнее, без пропусков — без полос', () => {
    const option = trendOption([{ label: 'А', value: 1, status: 'green' }, { label: 'Б', value: 2, status: 'red' }])
    expect(option.series).toHaveLength(1)
    expect(option.series[0].markLine).toBeUndefined()
    expect(option.series[0].data[1]).toMatchObject({ symbolSize: 8 })
    expect(trendPointText({ label: 'Б', value: 2, target: null, status: 'red' }, 'шт.')).toEqual(['Б', 'Значение: 2 шт.', 'Критично'])
  })
})

describe('ввод значений', () => {
  const values = [
    { indicator_id: 5, department_id: 3, value: 96, target: null, comment: '' },
    { indicator_id: 6, department_id: 12, value: 4.3, target: null, comment: 'Рост времени решения' },
  ]
  it('ввод числа в ru-RU', () => {
    expect(parseInput('96,5')).toEqual({ ok: true, value: 96.5 })
    expect(parseInput(' 1 234,5 ')).toEqual({ ok: true, value: 1234.5 })
    expect(parseInput('−3')).toEqual({ ok: true, value: -3 })
    expect(parseInput('')).toEqual({ ok: true, value: null })
    expect(parseInput('abc').ok).toBe(false)
    expect(parseInput('1,2,3').ok).toBe(false)
    expect(toInput(4.3)).toBe('4,3')
    expect(toInput(null)).toBe('')
  })
  it('только изменённые ячейки → элементы PUT', () => {
    const original = entryOriginal(values)
    expect(entryDraft(original, entryKey(6, 12))).toEqual({ value: '4,3', target: '', comment: 'Рост времени решения' })
    const drafts = new Map([
      [entryKey(5, 3), { value: '96', target: '', comment: '' }], // без изменений
      [entryKey(6, 12), { value: '4,5', target: '', comment: 'Рост времени решения ' }], // значение
      [entryKey(5, 13), { value: '88', target: '100', comment: 'Догнали план' }], // новая ячейка
      [entryKey(5, 2), { value: 'много', target: 'x', comment: '' }], // ошибка ввода
      [entryKey(5, 12), { value: '', target: '', comment: '' }], // пустая и была пустой
    ])
    const { items, keys, invalid } = entryChanges(original, drafts)
    expect(items).toEqual([
      { indicator_id: 6, department_id: 12, value: 4.5, target: null, comment: 'Рост времени решения' },
      { indicator_id: 5, department_id: 13, value: 88, target: 100, comment: 'Догнали план' },
    ])
    expect(keys).toEqual(['6:12', '5:13'])
    expect(invalid).toEqual({ '5:2': { value: 'Нужно число', target: 'Нужно число' } })
    // Очистка ячейки — элемент с пустыми полями (сервер удаляет запись)
    const cleared = entryChanges(original, new Map([[entryKey(5, 3), { value: '', target: '', comment: '' }]]))
    expect(cleared.items).toEqual([{ indicator_id: 5, department_id: 3, value: null, target: null, comment: '' }])
  })
  it('ошибки сервера по ячейкам', () => {
    const errors = cellErrors({ 'items.1.value': 'Значение больше допустимого', 'items.0.department_id': 'Вне области ввода', 'comment': 'x', 'items.9.value': 'нет такой' }, ['6:12', '5:13'])
    expect(errors).toEqual({ '5:13': { value: 'Значение больше допустимого' }, '6:12': { cell: 'Вне области ввода' } })
  })
  it('где можно вводить и где значение ожидается', () => {
    const ind = { id: 5, unit_ids: [3, 12], expected_kinds: ['service', 'group'] }
    expect(canEnterCell(ind, { id: 3 })).toBe(true)
    expect(canEnterCell(ind, { id: 4 })).toBe(false)
    expect(canEnterCell({ unit_ids: null }, { id: 4 })).toBe(true)
    expect(expectedEmpty(ind, { kind: 'group' }, { value: '' })).toBe(true)
    expect(expectedEmpty(ind, { kind: 'group' }, { value: '97' })).toBe(false)
    expect(expectedEmpty(ind, { kind: 'division' }, { value: '' })).toBe(false)
  })
  it('строки формы и месяцы ввода', () => {
    expect(entryRows([{ id: 1, level: 2 }, { id: 2, level: 4 }]).map((u) => u.indent)).toEqual([0, 2])
    expect(entryPeriods('2026-02', 3)).toEqual(['2026-02', '2026-01', '2025-12'])
    expect(entryPeriods('')).toEqual([])
  })
})

describe('загрузка значений', () => {
  const rows = [
    { line: 2, action: 'update', errors: [] },
    { line: 3, action: 'unchanged', errors: [] },
    { line: 4, action: 'error', errors: ['Подразделение не найдено'] },
    { line: 5, action: 'create', errors: [] },
  ]
  it('фильтры плана', () => {
    expect(filterImportRows(rows, 'changes').map((r) => r.line)).toEqual([2, 4, 5])
    expect(filterImportRows(rows, 'errors').map((r) => r.line)).toEqual([4])
    expect(filterImportRows(rows, 'all')).toHaveLength(4)
  })
  it('сводка чипами', () => {
    expect(importChips({ rows: 4, create: 1, update: 1, unchanged: 1, errors: 0 })).toEqual([
      { label: 'Строк', value: 4, tone: 'gray' }, { label: 'Новых', value: 1, tone: 'green' }, { label: 'Изменится', value: 1, tone: 'blue' },
      { label: 'Без изменений', value: 1, tone: 'gray' }, { label: 'Ошибок', value: 0, tone: 'gray' },
    ])
    expect(importChips(null)).toEqual([])
  })
  it('строка «очистить»: видна среди изменений, в сводке — «Очистится»', () => {
    const withClear = [...rows, { line: 6, action: 'clear', clear: true, errors: [] }]
    expect(filterImportRows(withClear, 'changes').map((r) => r.line)).toEqual([2, 4, 5, 6])
    expect(IMPORT_ACTIONS.clear).toEqual({ label: 'Очистить', tone: 'red' })
    expect(importChips({ rows: 2, create: 0, update: 1, cleared: 1, unchanged: 0, errors: 0 }).map((c) => [c.label, c.value, c.tone]))
      .toEqual([['Строк', 2, 'gray'], ['Новых', 0, 'gray'], ['Изменится', 1, 'blue'], ['Очистится', 1, 'red'], ['Без изменений', 0, 'gray'], ['Ошибок', 0, 'gray']])
  })
  it('шаблон CSV: заголовки, строки по ячейкам формы, сохранённые значения', () => {
    const csv = templateCsv({
      period: '2026-07',
      indicators: [{ id: 5, name: 'Выполнение плана работ', unit_ids: null }, { id: 6, name: 'Удовлетворённость; оценка', unit_ids: [3] }],
      units: [{ id: 3, name: 'Служба', path: 'Компания / Служба' }, { id: 12, name: 'Группа', path: 'Компания / Служба / Группа' }],
      values: [{ indicator_id: 5, department_id: 3, value: 96.5, target: 100, comment: 'Сказал "да"' }],
    })
    expect(csv.charCodeAt(0)).toBe(0xfeff)
    expect(csv.slice(1).split('\r\n')).toEqual([
      'Подразделение;Показатель;Период;Значение;Цель;Комментарий',
      'Компания / Служба;Выполнение плана работ;2026-07;96,5;100;"Сказал ""да"""',
      'Компания / Служба;"Удовлетворённость; оценка";2026-07;;;',
      'Компания / Служба / Группа;Выполнение плана работ;2026-07;;;',
      '',
    ])
  })
  it('состояние ячейки в плане', () => {
    expect(cellStateText({ value: 96, target: 100, comment: 'тест' }, '%')).toBe('96% · цель 100% · «тест»')
    expect(cellStateText(null)).toBe('—')
  })
})
