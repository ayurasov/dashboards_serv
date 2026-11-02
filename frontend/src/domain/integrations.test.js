import { describe, expect, it } from 'vitest'
import {
  allowedHostsHint, checkDetails, checkHint, curlExample, fieldVisible, healthInfo, initialSecrets, initialValues,
  intervalText, isLongText, isMonospace, jsonRows, jsonText, kindIcon, normalizeUrl, parseJsonField, pingExample, quoted, richBlocks, richPreview, rebindSecrets, runCounters, runCountersText, runDuration, runStatus,
  scheduleDraft, scheduleErrors, scheduleLabel, schedulePayload, settingsPayload, shortError, toConfigValue, toFormValue,
  toggleWeekday, urlChanged, validateSettings, visibleFields,
} from './integrations'

// Вид подключения в форме ответа /api/integrations/kinds
const KIND = {
  kind: 'jira',
  title: 'Jira',
  url_field: 'base_url',
  allowed_hosts_env: 'JIRA_ALLOWED_HOSTS',
  fields: [
    { key: 'base_url', label: 'Адрес', type: 'url', required: true, secret: false, default: null },
    { key: 'instance', label: 'Тип', type: 'select', required: true, secret: false, default: 'cloud', options: [{ value: 'cloud', label: 'Cloud' }, { value: 'server', label: 'Server' }] },
    { key: 'login', label: 'Email', type: 'string', required: true, secret: false, default: null, show_if: { instance: ['cloud'] } },
    { key: 'token', label: 'API-токен', type: 'password', required: true, secret: true, default: null },
    { key: 'password', label: 'Пароль', type: 'password', required: false, secret: true, default: null, show_if: { instance: ['server'] } },
    { key: 'batch', label: 'Пачка', type: 'int', required: false, secret: false, default: 50, min: 10, max: 500 },
    { key: 'verify_tls', label: 'Проверять сертификат', type: 'bool', required: false, secret: false, default: true },
    { key: 'projects', label: 'Проекты', type: 'multiselect', required: false, secret: false, default: null, options: [{ value: 'A', label: 'A' }, { value: 'B', label: 'B' }] },
    { key: 'labels', label: 'Метки', type: 'list', required: false, secret: false, default: null },
    { key: 'at', label: 'Время', type: 'time', required: false, secret: false, default: '08:30' },
    { key: 'jql', label: 'JQL', type: 'text', required: false, secret: false, default: null },
  ],
  actions: [
    { key: 'pull', label: 'Забрать данные', schedulable: true },
    { key: 'sync', label: 'Синхронизировать', schedulable: true },
    { key: 'manual', label: 'Только вручную', schedulable: false },
  ],
}

describe('показ полей по show_if', () => {
  it('поле видно, когда другое поле имеет одно из значений', () => {
    const login = KIND.fields[2]
    expect(fieldVisible(login, { instance: 'cloud' })).toBe(true)
    expect(fieldVisible(login, { instance: 'server' })).toBe(false)
    expect(fieldVisible(login, {})).toBe(false)
    expect(fieldVisible(KIND.fields[0], {})).toBe(true)
  })

  it('все условия должны выполняться; булевы значения сравниваются как строки', () => {
    const field = { key: 'x', show_if: { a: ['1'], flag: [true] } }
    expect(fieldVisible(field, { a: '1', flag: true })).toBe(true)
    expect(fieldVisible(field, { a: '1', flag: 'true' })).toBe(true)
    expect(fieldVisible(field, { a: '1', flag: false })).toBe(false)
    expect(fieldVisible(field, { a: '2', flag: true })).toBe(false)
  })

  it('visibleFields оставляет видимые поля в порядке описания', () => {
    expect(visibleFields(KIND.fields, { instance: 'server' }).map((f) => f.key)).toEqual(['base_url', 'instance', 'token', 'password', 'batch', 'verify_tls', 'projects', 'labels', 'at', 'jql'])
  })
})

describe('значения формы', () => {
  it('начальные значения — сохранённые, иначе по умолчанию; секретов нет', () => {
    expect(initialValues(KIND.fields)).toEqual({
      base_url: '', instance: 'cloud', login: '', batch: '50', verify_tls: true, projects: [], labels: '', at: '08:30', jql: '',
    })
    const saved = initialValues(KIND.fields, { base_url: 'https://jira.company.ru', instance: 'server', batch: 100, verify_tls: false, projects: ['B'], labels: ['a', 'b'] })
    expect(saved).toMatchObject({ base_url: 'https://jira.company.ru', instance: 'server', batch: '100', verify_tls: false, projects: ['B'], labels: 'a\nb' })
  })

  it('приведение к API: пустое — null, список — по строкам и запятым, число — числом', () => {
    const f = (type) => ({ type })
    expect(toConfigValue(f('string'), '  x  ')).toBe('x')
    expect(toConfigValue(f('string'), '  ')).toBeNull()
    expect(toConfigValue(f('int'), ' 42 ')).toBe(42)
    expect(toConfigValue(f('int'), '')).toBeNull()
    expect(toConfigValue(f('bool'), 1)).toBe(true)
    expect(toConfigValue(f('list'), 'a\n b ,c\n\n')).toEqual(['a', 'b', 'c'])
    expect(toConfigValue(f('multiselect'), ['A'])).toEqual(['A'])
    expect(toFormValue(f('bool'), 'true')).toBe(true)
    expect(toFormValue(f('int'), null)).toBe('')
  })
})

describe('секреты: задан / заменить / очистить', () => {
  it('у сохранённого секрета — keep, у остальных — ввести', () => {
    expect(initialSecrets(KIND.fields, { secret_fields: ['token'] })).toEqual({ token: { mode: 'keep', value: '' }, password: { mode: 'replace', value: '' } })
    expect(initialSecrets(KIND.fields)).toEqual({ token: { mode: 'replace', value: '' }, password: { mode: 'replace', value: '' } })
  })

  it('тело запроса: сохранённый без изменений не передаётся, введённый — передаётся, очищенный — в clear_secrets', () => {
    const values = initialValues(KIND.fields, { base_url: 'https://jira.company.ru' })
    const body = settingsPayload(KIND, values, { token: { mode: 'keep', value: '' }, password: { mode: 'clear', value: '' } })
    expect(body.secrets).toEqual({})
    expect(body.clear_secrets).toEqual(['password'])
    expect(body.config).toMatchObject({ base_url: 'https://jira.company.ru', instance: 'cloud', login: null, batch: 50, verify_tls: true, labels: [], projects: [] })
    expect(body.config).not.toHaveProperty('token')
    const replaced = settingsPayload(KIND, values, { token: { mode: 'replace', value: 'abc' } })
    expect(replaced.secrets).toEqual({ token: 'abc' })
    expect(replaced.clear_secrets).toEqual([])
  })

  it('смена адреса: сохранённые секреты привязаны к старому адресу — их нужно ввести заново', () => {
    const integration = { has_secret: true, secret_bound_url: 'https://jira.company.ru' }
    expect(urlChanged(KIND, { base_url: 'HTTPS://JIRA.company.ru/' }, integration)).toBe(false)
    expect(urlChanged(KIND, { base_url: 'https://jira2.company.ru' }, integration)).toBe(true)
    expect(urlChanged(KIND, { base_url: 'https://jira2.company.ru' }, { has_secret: false })).toBe(false)
    expect(urlChanged({ ...KIND, url_field: null }, { base_url: 'x' }, integration)).toBe(false)
    expect(rebindSecrets({ token: { mode: 'keep', value: '' }, password: { mode: 'clear', value: '' } }))
      .toEqual({ token: { mode: 'replace', value: '' }, password: { mode: 'clear', value: '' } })
    expect(normalizeUrl(' https://Host.RU/path/ ')).toBe('https://host.ru/path')
  })
})

describe('проверка формы', () => {
  const ok = { base_url: 'https://jira.company.ru', instance: 'cloud', login: 'svc@company.ru', batch: '50', at: '08:30' }

  it('обязательные видимые поля и секреты', () => {
    expect(validateSettings(KIND, { instance: 'cloud' }, {}, { name: '' })).toEqual({
      name: 'Укажите название', 'config.base_url': 'Обязательное поле', 'config.login': 'Обязательное поле', 'secrets.token': 'Обязательное поле',
    })
    // Скрытое поле (login у server) не проверяется
    expect(validateSettings(KIND, { ...ok, instance: 'server', login: '' }, { token: { mode: 'keep' } })).toEqual({})
    expect(validateSettings(KIND, ok, { token: { mode: 'replace', value: 'x' } })).toEqual({})
    expect(validateSettings(KIND, ok, { token: { mode: 'clear' } })).toEqual({ 'secrets.token': 'Обязательное поле' })
  })

  it('типы: число и пределы, адрес, время, значение из списка', () => {
    const secrets = { token: { mode: 'keep' } }
    expect(validateSettings(KIND, { ...ok, batch: '5' }, secrets)).toEqual({ 'config.batch': 'От 10 до 500' })
    expect(validateSettings(KIND, { ...ok, batch: '1,5' }, secrets)).toEqual({ 'config.batch': 'Нужно целое число' })
    expect(validateSettings(KIND, { ...ok, base_url: 'jira.company.ru' }, secrets)).toEqual({ 'config.base_url': 'Адрес начинается с http:// или https://' })
    expect(validateSettings(KIND, { ...ok, base_url: 'https://u@jira.ru' }, secrets)['config.base_url']).toMatch(/без логина/)
    expect(validateSettings(KIND, { ...ok, base_url: 'https://jira.ru/?a=1' }, secrets)['config.base_url']).toMatch(/«\?»/)
    expect(validateSettings(KIND, { ...ok, at: '25:00' }, secrets)).toEqual({ 'config.at': 'Время в формате ЧЧ:ММ' })
    expect(validateSettings(KIND, { ...ok, instance: 'other' }, secrets)).toEqual({ 'config.instance': 'Выберите значение из списка' })
  })
})

describe('расписание', () => {
  it('подпись — как на сервере', () => {
    expect(scheduleLabel(null)).toBe('Вручную')
    expect(scheduleLabel({ mode: 'off' })).toBe('Вручную')
    expect(scheduleLabel({ mode: 'interval', minutes: 60 })).toBe('Каждые 60 мин')
    expect(scheduleLabel({ mode: 'daily', time: '06:30', weekdays: [] })).toBe('В 06:30 ежедневно')
    expect(scheduleLabel({ mode: 'daily', time: '06:30', weekdays: [5, 1] })).toBe('В 06:30 (пн, пт)')
    expect(scheduleLabel({ mode: 'daily', time: '06:30', weekdays: [1, 2, 3, 4, 5, 6, 7] })).toBe('В 06:30 ежедневно')
  })

  it('интервал словами', () => {
    expect(intervalText(15)).toBe('каждые 15 минут')
    expect(intervalText(21)).toBe('каждую 21 минуту')
    expect(intervalText(60)).toBe('каждый час')
    expect(intervalText(180)).toBe('каждые 3 часа')
    expect(intervalText(300)).toBe('каждые 5 часов')
    expect(intervalText(1440)).toBe('раз в сутки')
    expect(intervalText(2880)).toBe('каждые 2 суток')
  })

  it('черновик: действия — сохранённые или первое по расписанию; лишние убираются', () => {
    expect(scheduleDraft(null, KIND)).toEqual({ mode: 'off', minutes: '60', time: '06:00', weekdays: [], actions: ['pull'] })
    expect(scheduleDraft({ mode: 'daily', time: '07:15', weekdays: [5, 1], actions: ['sync', 'manual'] }, KIND))
      .toEqual({ mode: 'daily', minutes: '60', time: '07:15', weekdays: [1, 5], actions: ['sync'] })
  })

  it('проверка и тело запроса', () => {
    const draft = scheduleDraft({ mode: 'interval', minutes: 3 }, KIND)
    expect(scheduleErrors(draft, KIND)).toEqual({ 'schedule.minutes': 'Целое число минут от 5 до 10\u00a0080 (неделя)' })
    expect(scheduleErrors({ ...draft, minutes: '30', actions: [] }, KIND)).toEqual({ 'schedule.actions': 'Выберите хотя бы одно действие' })
    expect(scheduleErrors({ mode: 'daily', time: '6:00', actions: ['pull'] }, KIND)).toEqual({ 'schedule.time': 'Время в формате ЧЧ:ММ' })
    expect(scheduleErrors({ mode: 'interval', minutes: '30', actions: [] }, { actions: [{ key: 'x', schedulable: false }] })).toEqual({ schedule: 'У этого подключения нет действий по расписанию' })
    expect(scheduleErrors({ mode: 'off' }, KIND)).toEqual({})
    expect(schedulePayload({ ...draft, minutes: ' 30 ' })).toEqual({ mode: 'interval', minutes: 30, actions: ['pull'] })
    expect(schedulePayload({ mode: 'daily', time: '06:00', weekdays: [5, 1, 5], actions: ['pull', 'sync'] })).toEqual({ mode: 'daily', time: '06:00', weekdays: [1, 5], actions: ['pull', 'sync'] })
    expect(schedulePayload({ mode: 'off', actions: ['pull'] })).toEqual({ mode: 'off' })
    expect(toggleWeekday([1, 5], 3)).toEqual([1, 3, 5])
    expect(toggleWeekday([1, 3, 5], 3)).toEqual([1, 5])
  })
})

describe('состояние и журнал запусков', () => {
  it('тона состояния и итога запуска', () => {
    expect(healthInfo('ok')).toEqual({ label: 'Работает', tone: 'green' })
    expect(healthInfo('error').tone).toBe('red')
    expect(healthInfo('disabled').tone).toBe('gray')
    expect(healthInfo('что-то').label).toBe('Не проверено')
    expect(runStatus({ status: 'partial', status_label: 'Частично' })).toEqual({ label: 'Частично', tone: 'yellow' })
    expect(runStatus({ status: 'ok' })).toEqual({ label: 'Успешно', tone: 'green' })
  })

  it('счётчики сводки: известные — подписями, items — числом элементов, вложенное не показывается', () => {
    const summary = { taken: 2, applied: 1, custom_thing: 3, items: [4, 5], details: { notes: ['x'] }, flag: true }
    expect(runCounters(summary)).toEqual([
      { key: 'taken', label: 'взято', value: 2 }, { key: 'applied', label: 'применено', value: 1 },
      { key: 'custom_thing', label: 'custom thing', value: 3 }, { key: 'items', label: 'элементов входящих', value: 2 },
    ])
    expect(runCountersText({ files: 1200 })).toBe('файлов: 1\u00a0200')
    expect(runCounters({ taken: 0, errors: 1 })).toEqual([{ key: 'errors', label: 'ошибок', value: 1 }])
    expect(runCounters({ taken: 0 }, { zeros: true })).toEqual([{ key: 'taken', label: 'взято', value: 0 }])
    expect(quoted('Jira')).toBe('«Jira»')
    expect(quoted('Папка «Входящие»')).toBe('Папка «Входящие»')
    expect(runCounters(null)).toEqual([])
  })

  it('длительность и короткая ошибка', () => {
    expect(runDuration({ started_at: '2026-11-01T10:00:00', finished_at: '2026-11-01T10:00:12' })).toBe('12 с')
    expect(runDuration({ started_at: '2026-11-01T10:00:00', finished_at: '2026-11-01T10:03:05' })).toBe('3 мин 5 с')
    expect(runDuration({ started_at: '2026-11-01T10:00:00', finished_at: '2026-11-01T10:02:00' })).toBe('2 мин')
    expect(runDuration({ started_at: '2026-11-01T10:00:00' })).toBe('—')
    expect(shortError('\n  Нет связи\nподробности')).toBe('Нет связи')
    expect(shortError('x'.repeat(200), 20)).toHaveLength(20)
  })

  it('подсказки проверки и подробности', () => {
    expect(allowedHostsHint(KIND)).toMatch(/JIRA_ALLOWED_HOSTS/)
    expect(allowedHostsHint({ allowed_hosts_env: null })).toBe('')
    expect(checkHint({ ok: false, details: { code: 'host_not_allowed' } }, KIND)).toMatch(/JIRA_ALLOWED_HOSTS/)
    expect(checkHint({ ok: false, details: { code: 'secret_rebind_required' } }, KIND)).toMatch(/заново/)
    expect(checkHint({ ok: false, details: {} }, KIND)).toBe('')
    expect(checkDetails({ code: 'x', version: '9.4', empty: '', nested: { a: 1 } })).toEqual([{ key: 'version', value: '9.4' }, { key: 'nested', value: '{"a":1}' }])
    expect(checkDetails({ ok: true, folders: [{ a: 1 }, { a: 2 }], tags: ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'] })).toEqual([
      { key: 'ok', value: 'да' }, { key: 'folders', value: '2 записи' }, { key: 'tags', value: 'a, b, c, d, e, f и ещё 2' },
    ])
    expect(kindIcon('jira')).toBe('ticket')
    expect(kindIcon('новое')).toBe('plug')
  })
})

describe('пример вызова', () => {
  it('curl с ключом, набором и признаком применения', () => {
    expect(curlExample({ origin: 'https://dash.company.ru', key: 'dash_abc', dataset: 'tp-weekly', filename: 'отчёт.xlsx', apply: false })).toBe([
      'curl -X POST "https://dash.company.ru/api/inbound/v1/files" \\',
      '  -H "Authorization: Bearer dash_abc" \\',
      '  -F "file=@отчёт.xlsx" \\',
      '  -F "dataset=tp-weekly" \\',
      '  -F "apply=false"',
    ].join('\n'))
    expect(curlExample({ origin: '' }).split('\n')).toHaveLength(3)
    expect(pingExample({ origin: 'https://x', key: 'dash_k' })).toBe('curl "https://x/api/inbound/v1/ping" -H "Authorization: Bearer dash_k"')
  })
})

describe('поле JSON (правила Jira, запросы 1С)', () => {
  const RULES = { key: 'rules', label: 'Правила', type: 'json', required: true, secret: false, default: null }
  const kind = { fields: [RULES] }

  it('значение для формы — с отступами; строка с JSON — тоже; разобранное — уходит на сервер', () => {
    const value = [{ indicator: 'jira.open', measure: 'count', jql: 'project = SUP' }]
    expect(jsonText(value)).toBe(JSON.stringify(value, null, 2))
    expect(jsonText('[{"a":1}]')).toBe('[\n  {\n    "a": 1\n  }\n]')
    expect(jsonText('не json')).toBe('не json')
    expect(jsonText(null)).toBe('')
    expect(initialValues([RULES], { rules: value }).rules).toBe(JSON.stringify(value, null, 2))
    expect(toConfigValue(RULES, ' [ {"a": 1} ] ')).toEqual([{ a: 1 }])
    expect(toConfigValue(RULES, '  ')).toBeNull()
    expect(settingsPayload(kind, { rules: '{"x": true}' }, {}).config).toEqual({ rules: { x: true } })
  })

  it('ошибка разбора — «Ошибка JSON: …» с местом; форма не сохраняется', () => {
    const bad = parseJsonField('[\n  {"a": 1,}\n]')
    expect(bad.ok).toBe(false)
    expect(bad.error).toMatch(/^Ошибка JSON: /)
    expect(bad.error).toMatch(/строка 2/)
    expect(bad.error).toMatch(/ожидается имя свойства/)
    expect(parseJsonField('[1, 2').error).toMatch(/JSON обрывается|ожидается «,» или «]»/)
    expect(parseJsonField('{"a": 1} x').error).toMatch(/лишние символы|неожиданный символ/)
    expect(parseJsonField('')).toEqual({ ok: true, value: null, error: '' })
    expect(validateSettings(kind, { rules: '[{]' }, {})['config.rules']).toMatch(/^Ошибка JSON: /)
    expect(validateSettings(kind, { rules: '' }, {})).toEqual({ 'config.rules': 'Обязательное поле' })
    expect(validateSettings(kind, { rules: '[]' }, {})).toEqual({})
  })

  it('моноширинно — JSON и текст с признаком monospace; высота 10–16 строк', () => {
    expect(isMonospace(RULES)).toBe(true)
    expect(isMonospace({ type: 'text', monospace: true })).toBe(true)
    expect(isMonospace({ type: 'text' })).toBe(false)
    expect(jsonRows('')).toBe(10)
    expect(jsonRows('a\n'.repeat(12))).toBe(14)
    expect(jsonRows('a\n'.repeat(40))).toBe(16)
  })
})

describe('длинные описания и подсказки', () => {
  const ONEC = 'Значения показателей из 1С.\n\nПример для 1С:\n```1c\nФункция Отправить()\n    Возврат Истина;\nКонецФункции\n```\nКлюч — в «Интеграциях».'
  it('блоки: текст с переносами и код из тройных кавычек', () => {
    expect(richBlocks(ONEC)).toEqual([
      { type: 'text', value: 'Значения показателей из 1С.\n\nПример для 1С:', lang: '' },
      { type: 'code', value: 'Функция Отправить()\n    Возврат Истина;\nКонецФункции', lang: '1c' },
      { type: 'text', value: 'Ключ — в «Интеграциях».', lang: '' },
    ])
    expect(richBlocks('Просто текст')).toEqual([{ type: 'text', value: 'Просто текст', lang: '' }])
    // Пример кода без кавычек: после «…:» строки с отступами
    expect(richBlocks('Пример для 1С:\nФункция Ф()\n    А = 1;\n    Возврат А;\nКонецФункции\n\nДальше текст')).toEqual([
      { type: 'text', value: 'Пример для 1С:', lang: '' },
      { type: 'code', value: 'Функция Ф()\n    А = 1;\n    Возврат А;\nКонецФункции', lang: '' },
      { type: 'text', value: 'Дальше текст', lang: '' },
    ])
    expect(richBlocks('Варианты:\nодин\nдва')).toEqual([{ type: 'text', value: 'Варианты:\nодин\nдва', lang: '' }])
    expect(richBlocks('')).toEqual([])
  })

  it('длинное сворачивается; в свёрнутом — первый абзац', () => {
    expect(isLongText(ONEC)).toBe(true)
    expect(isLongText('Коротко')).toBe(false)
    expect(isLongText('а'.repeat(300))).toBe(true)
    expect(isLongText('строка 1\nстрока 2\nстрока 3')).toBe(true)
    expect(richPreview(ONEC)).toBe('Значения показателей из 1С.')
    const long = richPreview('слово '.repeat(60), 40)
    expect(long.length).toBeLessThanOrEqual(40)
    expect(long.endsWith('…')).toBe(true)
  })
})
