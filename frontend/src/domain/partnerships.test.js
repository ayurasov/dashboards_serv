import { describe, expect, it } from 'vitest'
import {
  certAgeRange, certAgeYears, fitSpans, countByLight, decisiveParts, eventDate, eventKind, filterTimeline, formatYears,
  formatYearsGenitive, groupLightRows, groupTimeline, lightExplanation, lightParts, lightReason, lightRuleChanges,
  lightSegments, mergeOptions, shortRuleLabel, orderStatuses, share, sortPartnerships, sortedEntries, summaryTotals, thresholdErrors,
  yearDelta,
} from './partnerships'

const TODAY = new Date(2026, 10, 1)

const record = (over = {}) => ({
  id: 1, partner: 'Альфа', product: 'Сервер', status: 'Завершено', nda: true, agreement: false, cert_date: '2025-11-01',
  last_modified: null, almi_product: 'АльтерОС', light: 'yellow',
  light_parts: { status: 'green', nda: 'green', agreement: 'yellow', cert_age: 'green' }, ...over,
})

describe('списки и доли', () => {
  it('mergeOptions: значения по умолчанию первыми, остальные по алфавиту без повторов', () => {
    expect(mergeOptions(['ПО', 'ПАК'], ['Железо', 'ПО', '', 'Аппарат', 'Железо'])).toEqual(['ПО', 'ПАК', 'Аппарат', 'Железо'])
  })
  it('orderStatuses: только встречающиеся, в порядке жизненного цикла', () => {
    expect(orderStatuses(['Не подписывают', 'Архив', 'Завершено'])).toEqual(['Завершено', 'Не подписывают', 'Архив'])
  })
  it('share: процент с округлением и защитой от деления на ноль', () => {
    expect(share(73, 142)).toBe(51.4)
    expect(share(1, 3, 0)).toBe(33)
    expect(share(5, 0)).toBe(0)
  })
  it('sortedEntries: по убыванию, при равенстве по алфавиту, с ограничением', () => {
    expect(sortedEntries({ Б: 2, А: 2, В: 5 })).toEqual([['В', 5], ['А', 2], ['Б', 2]])
    expect(sortedEntries({ Б: 2, А: 2, В: 5 }, 1)).toEqual([['В', 5]])
  })
  it('countByLight и lightSegments', () => {
    const counts = countByLight([{ light: 'red' }, { light: 'green' }, { light: 'green' }, { light: 'x' }])
    expect(counts).toEqual({ green: 2, yellow: 0, red: 1, gray: 1 })
    expect(lightSegments(counts).map((s) => s.share)).toEqual([66.7, 0, 33.3])
    expect(lightSegments({}).every((s) => s.share === 0)).toBe(true)
  })
})

describe('группы светофора', () => {
  it('groupLightRows: группы в порядке статус, NDA, соглашение, срок; итог по группе', () => {
    const rows = [
      { key: 'cert_age:fresh', group_key: 'cert_age', group: 'Срок сертификата', count: 3 },
      { key: 'nda:yes', group_key: 'nda', group: 'NDA', count: 2 },
      { key: 'status:Завершено', group_key: 'status', group: 'Статус', count: 4 },
      { key: 'nda:no', group_key: 'nda', group: 'NDA', count: 1 },
    ]
    const groups = groupLightRows(rows)
    expect(groups.map((g) => g.key)).toEqual(['status', 'nda', 'cert_age'])
    expect(groups[1]).toMatchObject({ label: 'NDA', total: 3 })
    expect(groups[1].items).toHaveLength(2)
  })
})

describe('подписи правил', () => {
  it('shortRuleLabel убирает название группы', () => {
    expect(shortRuleLabel('NDA подписан', 'NDA')).toBe('Подписан')
    expect(shortRuleLabel('Соглашение не подписано', 'Соглашение')).toBe('Не подписано')
    expect(shortRuleLabel('Сертификат устарел', 'Срок сертификата')).toBe('Устарел')
    expect(shortRuleLabel('Завершено', 'Статус')).toBe('Завершено')
  })
})

describe('срок сертификата', () => {
  it('certAgeYears считает годы как сервер (дни / 365,25)', () => {
    expect(certAgeYears('2025-11-01', TODAY)).toBeCloseTo(365 / 365.25, 5)
    expect(certAgeYears(null, TODAY)).toBeNull()
  })
  it('formatYears склоняет и показывает месяцы для сроков меньше года', () => {
    expect(formatYears(1)).toBe('1 год')
    expect(formatYears(2)).toBe('2 года')
    expect(formatYears(5)).toBe('5 лет')
    expect(formatYears(2.46)).toBe('2,5 года')
    expect(formatYears(0.5)).toBe('6 месяцев')
    expect(formatYears(0.01)).toBe('меньше месяца')
  })
  it('formatYearsGenitive и certAgeRange', () => {
    expect(formatYearsGenitive(2)).toBe('2 лет')
    expect(formatYearsGenitive(1)).toBe('1 года')
    expect(formatYearsGenitive(2.5)).toBe('2,5 года')
    const rules = [{ key: 'cert_age:fresh', threshold: 2 }, { key: 'cert_age:aging', threshold: 4 }]
    expect(certAgeRange('cert_age:fresh', rules)).toBe('Не старше 2 лет')
    expect(certAgeRange('cert_age:aging', rules)).toBe('Старше 2 лет, но не старше 4 лет')
    expect(certAgeRange('cert_age:stale', rules)).toBe('Старше 4 лет')
  })
})

describe('объяснение светофора', () => {
  it('lightParts: четыре части с подписями', () => {
    const parts = lightParts(record(), TODAY)
    expect(parts.map((p) => p.key)).toEqual(['status', 'nda', 'agreement', 'cert_age'])
    expect(parts[1].value).toBe('подписан')
    expect(parts[2].value).toBe('не подписано')
    expect(parts[3].value).toBe('1 год')
  })
  it('без даты сертификата срок не учитывается', () => {
    const r = record({ cert_date: null, light_parts: { status: 'green', nda: 'green', agreement: 'green' }, light: 'green' })
    const age = lightParts(r).find((p) => p.key === 'cert_age')
    expect(age).toMatchObject({ skipped: true, light: 'gray' })
    expect(lightExplanation(r)).toContain('Срок сертификата: дата не указана — не учитывается')
  })
  it('decisiveParts и lightReason называют части, определившие итог', () => {
    const r = record({ light: 'yellow', light_parts: { status: 'green', nda: 'yellow', agreement: 'yellow', cert_age: 'green' } })
    expect(decisiveParts(r).map((p) => p.key)).toEqual(['nda', 'agreement'])
    expect(lightReason(r)).toBe('NDA, соглашение')
    expect(lightReason(record({ light: 'gray' }))).toBe('')
    const red = record({ light: 'red', light_parts: { status: 'red', nda: 'red', agreement: 'green', cert_age: 'green' } })
    expect(lightReason(red)).toBe('Статус, NDA')
    expect(lightReason(red, false)).toBe('статус, NDA')
    const green = record({ light: 'green', light_parts: { status: 'green', nda: 'green', agreement: 'green', cert_age: 'green' } })
    expect(lightReason(green)).toBe('Все части')
  })
  it('lightExplanation: итог и каждая часть отдельной строкой', () => {
    const text = lightExplanation(record(), TODAY)
    expect(text.split('\n')).toEqual([
      'Итог: Внимание — худшая из оценок',
      'Статус: Завершено — норма',
      'NDA: подписан — норма',
      'Соглашение: не подписано — внимание',
      'Срок сертификата: 1 год — норма',
    ])
  })
})

describe('сортировка реестра', () => {
  const rows = [
    record({ id: 1, partner: 'Бета', light: 'green', cert_date: '2024-01-01', status: 'Отложено' }),
    record({ id: 2, partner: 'Альфа', light: 'red', cert_date: null, status: 'В работе' }),
    record({ id: 3, partner: 'Гамма', light: 'yellow', cert_date: '2025-01-01', status: 'Завершено' }),
  ]
  it('по строке и по дате, пустые значения в конце', () => {
    expect(sortPartnerships(rows, 'partner').map((r) => r.id)).toEqual([2, 1, 3])
    expect(sortPartnerships(rows, 'cert_date', 'desc').map((r) => r.id)).toEqual([3, 1, 2])
    expect(sortPartnerships(rows, 'cert_date', 'asc').map((r) => r.id)).toEqual([1, 3, 2])
  })
  it('светофор — от критичного к норме, статус — по жизненному циклу', () => {
    expect(sortPartnerships(rows, 'light').map((r) => r.id)).toEqual([2, 3, 1])
    expect(sortPartnerships(rows, 'status').map((r) => r.id)).toEqual([2, 3, 1])
  })
})

describe('хронология', () => {
  const rows = [
    record({ id: 1, cert_date: '2025-07-14', last_modified: null }),
    record({ id: 2, cert_date: '2024-03-01', last_modified: '2025-07-20' }),
    record({ id: 3, cert_date: '2026-02-10', almi_product: 'АльтерОфис', partner: 'Дельта', comment: 'пилот' }),
    record({ id: 4, cert_date: null, last_modified: null }),
  ]
  it('eventDate и eventKind', () => {
    expect(eventDate(rows[1])).toBe('2025-07-20')
    expect(eventKind(rows[1])).toBe('Изменение')
    expect(eventKind(rows[0])).toBe('Сертификация')
  })
  it('groupTimeline: годы и месяцы от новых к старым, без записей без даты', () => {
    const years = groupTimeline(rows)
    expect(years.map((y) => y.year)).toEqual([2026, 2025])
    expect(years[1]).toMatchObject({ count: 2 })
    expect(years[1].months).toHaveLength(1)
    expect(years[1].months[0]).toMatchObject({ key: '2025-07', label: 'Июль' })
    expect(years[1].months[0].items.map((r) => r.id)).toEqual([2, 1])
  })
  it('filterTimeline: по продукту АЛМИ, статусу и тексту', () => {
    expect(filterTimeline(rows, { almi_product: 'АльтерОфис' }).map((r) => r.id)).toEqual([3])
    expect(filterTimeline(rows, { search: '  ПИЛОТ ' }).map((r) => r.id)).toEqual([3])
    expect(filterTimeline(rows, { status: 'Отложено' })).toEqual([])
  })
})

describe('сводка по годам', () => {
  const periods = [
    { year: 2025, total: 10, green: 2, yellow: 5, red: 3, nda_count: 4, agreement_count: 1 },
    { year: 2026, total: 12, green: 6, yellow: 6, red: 0, nda_count: 9, agreement_count: 5 },
  ]
  it('summaryTotals складывает годы', () => {
    expect(summaryTotals(periods)).toEqual({ total: 22, green: 8, yellow: 11, red: 3, nda_count: 13, agreement_count: 6 })
  })
  it('yearDelta: разница к предыдущему году или null', () => {
    expect(yearDelta(periods[1], periods[0], 'red')).toBe(-3)
    expect(yearDelta(periods[0], null, 'red')).toBeNull()
  })
})

describe('правила светофора', () => {
  const saved = [
    { key: 'status:Завершено', light: 'green', threshold: null },
    { key: 'cert_age:fresh', light: 'green', threshold: 2 },
    { key: 'cert_age:aging', light: 'yellow', threshold: 4 },
  ]
  it('lightRuleChanges отправляет только изменения', () => {
    const draft = [
      { key: 'status:Завершено', light: 'yellow', threshold: null },
      { key: 'cert_age:fresh', light: 'green', threshold: '3' },
      { key: 'cert_age:aging', light: 'yellow', threshold: 4 },
    ]
    expect(lightRuleChanges(draft, saved)).toEqual([
      { key: 'status:Завершено', light: 'yellow' },
      { key: 'cert_age:fresh', threshold: 3 },
    ])
    expect(lightRuleChanges(saved.map((r) => ({ ...r })), saved)).toEqual([])
  })
  it('thresholdErrors: «актуален» меньше «устаревает», значения в допустимых пределах', () => {
    expect(thresholdErrors(saved)).toEqual({})
    expect(thresholdErrors([{ ...saved[1], threshold: 5 }, saved[2]])).toEqual({ 'cert_age:aging': 'Должен быть больше срока «актуален»' })
    expect(thresholdErrors([{ ...saved[1], threshold: 0 }, saved[2]])).toHaveProperty('cert_age:fresh')
    expect(thresholdErrors([saved[1], { ...saved[2], threshold: '' }])).toHaveProperty('cert_age:aging')
    expect(thresholdErrors([saved[1], { ...saved[2], threshold: 60 }])).toEqual({ 'cert_age:aging': 'Не больше 50 лет' })
  })
})

describe('раскладка дашборда', () => {
  it('fitSpans: полные ряды не меняются, неполные растягиваются', () => {
    const b = (key, span) => ({ key, span })
    expect(fitSpans([b('kpi', 12), b('a', 6), b('b', 6), b('c', 4), b('d', 4), b('e', 4)]))
      .toEqual({ kpi: 12, a: 6, b: 6, c: 4, d: 4, e: 4 })
    expect(fitSpans([b('a', 6), b('lights', 12), b('c', 4), b('d', 4)])).toEqual({ a: 12, lights: 12, c: 6, d: 6 })
    expect(fitSpans([b('a', 4), b('b', 4), b('c', 4), b('d', 6)])).toEqual({ a: 4, b: 4, c: 4, d: 12 })
  })
})
