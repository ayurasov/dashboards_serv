import { describe, expect, it } from 'vitest'
import {
  MAX_SCHEDULES, SCOPES, adminOnlyFor, allowedHostsHint, bindingChanges, bindingFields, canAddSchedule, checkDetails, checkHint, currentError, curlExample,
  entryLabel, fieldVisible, healthInfo, initialSecrets, initialValues, intervalText, isLongText, isMonospace, isWideField, jsonRows, jsonText, kindIcon,
  newScheduleEntry, normalizeUrl, parseJsonField, pingExample, quoted, richBlocks, richPreview, rebindSecrets, runCounters, runCountersText, runDuration,
  runStatus, rateLimitText, scheduleDraft, scheduleEntries, scheduleErrors, scheduleLabel, schedulePayload, scheduledActions, settingsPayload, shortError,
  sortIntegrations, toConfigValue, toFormValue, toggleWeekday, urlChanged, validateSettings, visibleFields,
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
    const integration = { has_secret: true, secret_bound_url: 'https://jira.company.ru', config: { base_url: 'https://jira.company.ru' } }
    expect(urlChanged(KIND, { base_url: 'HTTPS://JIRA.company.ru/' }, integration)).toBe(false)
    expect(urlChanged(KIND, { base_url: 'https://jira2.company.ru' }, integration)).toBe(true)
    expect(urlChanged(KIND, { base_url: 'https://jira2.company.ru' }, { has_secret: false })).toBe(false)
    expect(urlChanged({ ...KIND, url_field: null }, { base_url: 'x' }, integration)).toBe(false)
    expect(bindingFields(KIND)).toEqual(['base_url'])
    expect(bindingFields({ ...KIND, secret_url_fields: [] })).toEqual([])
    expect(rebindSecrets({ token: { mode: 'keep', value: '' }, password: { mode: 'clear', value: '' } }))
      .toEqual({ token: { mode: 'replace', value: '' }, password: { mode: 'clear', value: '' } })
    expect(normalizeUrl(' https://Host.RU/path/ ')).toBe('https://host.ru/path')
  })
})

describe('привязка секретов к нескольким адресам (secret_url_fields)', () => {
  const PODELU = {
    kind: 'podelu', url_field: 'base_url', secret_url_fields: ['base_url', 'server_url'],
    fields: [
      { key: 'base_url', label: 'Адрес «По Делу»', type: 'url' },
      { key: 'server_url', label: 'Адрес для запросов сервера', type: 'url' },
      { key: 'login', label: 'Служебная учётная запись', type: 'string' },
      { key: 'password', label: 'Пароль', type: 'password', secret: true },
    ],
  }
  const EXCHANGE = {
    kind: 'exchange', url_field: null, secret_url_fields: ['mode', 'ews_url', 'imap_host', 'imap_port', 'imap_ssl'],
    fields: [
      { key: 'mode', label: 'Подключение', type: 'select', default: 'imap' },
      { key: 'ews_url', label: 'Адрес EWS', type: 'url', show_if: { mode: ['ews'] } },
      { key: 'imap_host', label: 'Сервер IMAP', type: 'string', show_if: { mode: ['imap'] } },
      { key: 'imap_port', label: 'Порт', type: 'int', default: 993, show_if: { mode: ['imap'] } },
      { key: 'imap_ssl', label: 'SSL/TLS', type: 'bool', default: true, show_if: { mode: ['imap'] } },
      { key: 'folder', label: 'Папка', type: 'string' },
      { key: 'password', label: 'Пароль', type: 'password', secret: true },
    ],
  }

  it('любой из адресов «По Делу»; остальные поля секреты не трогают', () => {
    const integration = { has_secret: true, config: { base_url: 'https://podelu.ru', server_url: null, login: 'svc' } }
    const values = initialValues(PODELU.fields, integration.config)
    expect(bindingChanges(PODELU, values, integration)).toEqual([])
    expect(bindingChanges(PODELU, { ...values, login: 'другой' }, integration)).toEqual([])
    expect(bindingChanges(PODELU, { ...values, server_url: 'http://10.0.0.5:5000' }, integration)).toEqual([{ key: 'server_url', label: 'Адрес для запросов сервера' }])
    expect(bindingChanges(PODELU, { ...values, base_url: 'https://PODELU.ru/' }, integration)).toEqual([])
    expect(bindingChanges(PODELU, { ...values, base_url: 'https://new.ru' }, { ...integration, has_secret: false })).toEqual([])
  })

  it('Exchange: способ подключения и поля его адреса; скрытые поля не считаются', () => {
    const integration = { has_secret: true, config: { mode: 'imap', imap_host: 'imap.company.ru', imap_port: 993, imap_ssl: true, ews_url: null, folder: 'Входящие' } }
    const values = initialValues(EXCHANGE.fields, integration.config)
    expect(bindingChanges(EXCHANGE, values, integration)).toEqual([])
    expect(bindingChanges(EXCHANGE, { ...values, folder: 'Входящие/1С' }, integration)).toEqual([])
    expect(bindingChanges(EXCHANGE, { ...values, imap_port: '143', imap_ssl: false }, integration).map((c) => c.key)).toEqual(['imap_port', 'imap_ssl'])
    expect(bindingChanges(EXCHANGE, { ...values, mode: 'ews', ews_url: 'https://mail.company.ru/EWS/Exchange.asmx' }, integration).map((c) => c.key))
      .toEqual(['mode', 'ews_url'])
  })
})

describe('частота вызовов ключа', () => {
  it('из rate_limit ключа, со склонением', () => {
    expect(rateLimitText(120)).toBe('Частота вызовов ограничена: не больше 120 запросов в минуту на ключ')
    expect(rateLimitText(21)).toBe('Частота вызовов ограничена: не больше 21 запроса в минуту на ключ')
    expect(rateLimitText(undefined)).toBe('Частота вызовов ограничена настройкой сервера')
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
  it('подпись — как на сервере: одна запись и несколько с действиями', () => {
    expect(scheduleLabel(null)).toBe('Вручную')
    expect(scheduleLabel({ mode: 'off' })).toBe('Вручную')
    expect(scheduleLabel([])).toBe('Вручную')
    expect(scheduleLabel({ mode: 'interval', minutes: 60 })).toBe('Каждые 60 мин')
    expect(scheduleLabel([{ mode: 'interval', minutes: 60 }])).toBe('Каждые 60 мин')
    expect(scheduleLabel({ mode: 'daily', time: '06:30', weekdays: [] })).toBe('В 06:30 ежедневно')
    expect(scheduleLabel({ mode: 'daily', time: '06:30', weekdays: [5, 1] })).toBe('В 06:30 (пн, пт)')
    expect(scheduleLabel({ mode: 'daily', time: '06:30', weekdays: [1, 2, 3, 4, 5, 6, 7] })).toBe('В 06:30 ежедневно')
    const two = [{ mode: 'daily', time: '06:00', weekdays: [], actions: ['sync'] }, { mode: 'interval', minutes: 30, actions: ['pull'] }]
    expect(scheduleLabel(two, KIND)).toBe('В 06:00 ежедневно — Синхронизировать; Каждые 30 мин — Забрать данные')
    expect(entryLabel({ mode: 'interval', minutes: 30 })).toBe('Каждые 30 мин')
  })

  it('записи: список 0.4.0 и прежний вид — один объект; вручную — пусто', () => {
    expect(scheduleEntries({ mode: 'interval', minutes: 5, actions: ['pull'] })).toEqual([{ mode: 'interval', minutes: 5, actions: ['pull'] }])
    expect(scheduleEntries({})).toEqual([])
    expect(scheduleEntries({ mode: 'off' })).toEqual([])
    expect(scheduleEntries(null)).toEqual([])
    expect(scheduleEntries([{ mode: 'daily', time: '06:00' }, { mode: 'off' }, null])).toEqual([{ mode: 'daily', time: '06:00' }])
    expect(scheduledActions([{ mode: 'daily', time: '06:00', actions: ['sync'] }, { mode: 'interval', minutes: 30, actions: ['pull', 'sync'] }])).toEqual(['sync', 'pull'])
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

  it('черновик: записи по порядку; действия — сохранённые или первое по расписанию; лишние убираются', () => {
    expect(scheduleDraft(null, KIND)).toEqual([])
    expect(scheduleDraft({ mode: 'daily', time: '07:15', weekdays: [5, 1], actions: ['sync', 'manual'] }, KIND))
      .toEqual([{ mode: 'daily', minutes: '60', time: '07:15', weekdays: [1, 5], actions: ['sync'] }])
    const fromApi = [{ mode: 'interval', minutes: 30, actions: ['pull'], label: 'Каждые 30 мин', next_run_at: '2026-11-02T10:00:00' }, { mode: 'daily', time: '06:00', weekdays: [], actions: [] }]
    expect(scheduleDraft(fromApi, KIND)).toEqual([
      { mode: 'interval', minutes: '30', time: '06:00', weekdays: [], actions: ['pull'] },
      { mode: 'daily', minutes: '60', time: '06:00', weekdays: [], actions: ['pull'] },
    ])
  })

  it('«Добавить расписание»: через интервал 60 минут, действие — ещё не занятое другими записями; не больше 5', () => {
    const first = newScheduleEntry(KIND, [])
    expect(first).toEqual({ mode: 'interval', minutes: '60', time: '06:00', weekdays: [], actions: ['pull'] })
    expect(newScheduleEntry(KIND, [first]).actions).toEqual(['sync'])
    expect(newScheduleEntry(KIND, [first, { ...first, actions: ['sync'] }]).actions).toEqual(['pull'])
    const full = Array.from({ length: MAX_SCHEDULES }, () => first)
    expect(MAX_SCHEDULES).toBe(5)
    expect(canAddSchedule(full.slice(1), KIND)).toBe(true)
    expect(canAddSchedule(full, KIND)).toBe(false)
    expect(canAddSchedule([], { actions: [{ key: 'x', schedulable: false }] })).toBe(false)
  })

  it('проверка записей (поля — как в ошибках сервера) и тело запроса — список', () => {
    const [draft] = scheduleDraft({ mode: 'interval', minutes: 3 }, KIND)
    expect(scheduleErrors([draft], KIND)).toEqual({ 'schedule.0.minutes': 'Целое число минут от 5 до 10\u00a0080 (неделя)' })
    expect(scheduleErrors([{ ...draft, minutes: '30' }, { ...draft, minutes: '30', actions: [] }], KIND)).toEqual({ 'schedule.1.actions': 'Выберите хотя бы одно действие' })
    expect(scheduleErrors([{ mode: 'daily', time: '6:00', actions: ['pull'] }], KIND)).toEqual({ 'schedule.0.time': 'Время в формате ЧЧ:ММ' })
    expect(scheduleErrors([{ mode: 'interval', minutes: '30', actions: [] }], { actions: [{ key: 'x', schedulable: false }] })).toEqual({ schedule: 'У этого подключения нет действий по расписанию' })
    expect(scheduleErrors([], KIND)).toEqual({})
    expect(scheduleErrors(Array.from({ length: 6 }, () => ({ ...draft, minutes: '30' })), KIND)).toEqual({ schedule: 'Не больше 5 расписаний у подключения' })
    expect(schedulePayload([{ ...draft, minutes: ' 30 ' }])).toEqual([{ mode: 'interval', minutes: 30, actions: ['pull'] }])
    expect(schedulePayload([{ mode: 'daily', time: '06:00', weekdays: [5, 1, 5], actions: ['pull', 'sync'] }, { ...draft, minutes: '45' }]))
      .toEqual([{ mode: 'daily', time: '06:00', weekdays: [1, 5], actions: ['pull', 'sync'] }, { mode: 'interval', minutes: 45, actions: ['pull'] }])
    expect(schedulePayload([])).toEqual([])
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
    expect(runStatus({ status: 'interrupted', status_label: 'Запуск прерван' })).toEqual({ label: 'Запуск прерван', tone: 'gray' })
    expect(runStatus({ status: 'interrupted' }).label).toBe('Запуск прерван')
  })

  it('счётчики сводки: подписи вида подключения (counter_labels), без подписи — не показываются', () => {
    const summary = { taken: 2, applied: 1, custom_thing: 3, items: [4, 5], details: { notes: ['x'] }, flag: true }
    expect(runCounters(summary)).toEqual([
      { key: 'taken', label: 'взято файлов', value: 2 }, { key: 'applied', label: 'применено', value: 1 },
      { key: 'items', label: 'элементов входящих', value: 2 },
    ])
    const labels = { tasks: 'задач в списке', candidates: 'задач с новыми вложениями', overspent: 'задач: затрачено больше оценки' }
    expect(runCounters({ tasks: 4, candidates: 1, overspent: 2, structure_item: 17, remaining: 3 }, { labels })).toEqual([
      { key: 'tasks', label: 'задач в списке', value: 4 }, { key: 'candidates', label: 'задач с новыми вложениями', value: 1 },
      { key: 'overspent', label: 'задач: затрачено больше оценки', value: 2 },
    ])
    expect(runCountersText({ files: 1200 })).toBe('файлов: 1\u00a0200')
    expect(runCountersText({ tasks: 3 }, labels)).toBe('задач в списке: 3')
    expect(runCounters({ taken: 0, errors: 1 })).toEqual([{ key: 'errors', label: 'ошибок', value: 1 }])
    expect(runCounters({ taken: 0 }, { zeros: true })).toEqual([{ key: 'taken', label: 'взято файлов', value: 0 }])
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

describe('ошибка, порядок видов, только администратор, области ключа', () => {
  it('ошибка карточки — только если новее последнего успеха', () => {
    expect(currentError({ current_error: '', last_error: 'Старое', last_error_at: '2026-11-01T10:00:00' })).toBe('')
    expect(currentError({ current_error: 'Нет связи' })).toBe('Нет связи')
    // сервер без current_error — по отметкам времени
    expect(currentError({ last_error: 'Старое', last_error_at: '2026-11-01T10:00:00', last_ok_at: '2026-11-01T11:00:00' })).toBe('')
    expect(currentError({ last_error: 'Новое', last_error_at: '2026-11-01T12:00:00', last_ok_at: '2026-11-01T11:00:00' })).toBe('Новое')
    expect(currentError({ last_error: 'Впервые', last_error_at: '2026-11-01T12:00:00' })).toBe('Впервые')
    expect(currentError(null)).toBe('')
  })

  it('карточки — в порядке видов сервера, внутри вида — по названию', () => {
    const kinds = [{ kind: 'podelu' }, { kind: 'puls' }, { kind: 'jira' }, { kind: 'folder' }]
    const list = [{ kind: 'folder', name: 'Папка' }, { kind: 'jira', name: 'Я' }, { kind: 'podelu', name: 'По Делу' }, { kind: 'jira', name: 'Б' }, { kind: 'unknown', name: 'А' }]
    expect(sortIntegrations(list, kinds).map((i) => i.name)).toEqual(['По Делу', 'Б', 'Я', 'Папка', 'А'])
  })

  it('вид «только администратор» и области ключа с подписями сервера', () => {
    expect(adminOnlyFor({ admin_only: true }, false)).toBe(true)
    expect(adminOnlyFor({ admin_only: true }, true)).toBe(false)
    expect(adminOnlyFor({ admin_only: false }, false)).toBe(false)
    expect(SCOPES.find((s) => s.value === 'status').label).toBe('Чтение статусов принятых файлов')
  })

  it('выбор из списка с длинными подписями — на всю ширину формы', () => {
    const select = (labels) => ({ type: 'select', options: labels.map((label, n) => ({ value: String(n), label })) })
    expect(isWideField(select(['Cloud — email и API-токен', 'Server / Data Center — персональный токен (PAT)']))).toBe(true)
    expect(isWideField(select(['NTLM', 'Basic']))).toBe(false)
    expect(isWideField({ type: 'url' })).toBe(true)
    expect(isWideField({ type: 'int' })).toBe(false)
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
