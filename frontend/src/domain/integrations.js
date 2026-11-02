/**
 * Интеграции (ADR-0011): форма настроек по описанию полей вида подключения (типы, show_if,
 * значения по умолчанию, обязательность, секреты «задан / заменить / очистить»), расписание
 * (черновик, проверка, подпись), состояние подключения и журнал запусков. Вход — ответы
 * /api/integrations/* (поля как в API). Чистые функции — покрыты тестами (integrations.test.js).
 */
import { formatNumber, plural } from '@/utils/format'

// ---------------------------------------------------------------- подписи и тона

export const HEALTH = {
  ok: { label: 'Работает', tone: 'green' },
  error: { label: 'Ошибка', tone: 'red' },
  unknown: { label: 'Не проверено', tone: 'yellow' },
  disabled: { label: 'Выключено', tone: 'gray' },
}
export const healthInfo = (health) => HEALTH[health] || HEALTH.unknown

export const RUN_STATUS = {
  running: { label: 'Выполняется', tone: 'blue' },
  ok: { label: 'Успешно', tone: 'green' },
  partial: { label: 'Частично', tone: 'yellow' },
  error: { label: 'Ошибка', tone: 'red' },
  // Процесс остановился посреди запуска (перезапуск, сбой): сервер показывает так запуск старше двух часов
  interrupted: { label: 'Запуск прерван', tone: 'gray' },
}
export const runStatus = (run) => ({ ...(RUN_STATUS[run?.status] || RUN_STATUS.error), label: run?.status_label || RUN_STATUS[run?.status]?.label || run?.status || '—' })

/** Значок вида подключения; неизвестный вид — общий значок подключения. */
export const KIND_ICONS = {
  podelu: 'briefcase', puls: 'activity', jira: 'ticket', confluence: 'book', bitrix24: 'handshake',
  exchange: 'mail', onec: 'wallet', folder: 'folder',
}
export const kindIcon = (kind) => KIND_ICONS[kind] || 'plug'

/**
 * Ограничение частоты вызовов ключа (INBOUND_RATE_LIMIT сервера, приходит в rate_limit ключа):
 * «Частота вызовов ограничена: не больше 120 запросов в минуту на ключ».
 */
export function rateLimitText(limit) {
  const n = Number(limit)
  if (!Number.isFinite(n) || n <= 0) return 'Частота вызовов ограничена настройкой сервера'
  return `Частота вызовов ограничена: не больше ${formatNumber(n)} ${plural(n, ['запроса', 'запросов', 'запросов'])} в минуту на ключ`
}

/**
 * Области ключа. Подписи — с сервера (GET /api/integrations/keys/scopes и scope_labels ключа); этот список —
 * только запасной, пока ответ не пришёл, с теми же подписями.
 */
export const SCOPES = [
  { value: 'files', label: 'Приём файлов', hint: 'POST /api/inbound/v1/files — файлы во «Входящие»' },
  { value: 'status', label: 'Чтение статусов принятых файлов', hint: 'GET /api/inbound/v1/files/{id} — статус файлов, принятых этим ключом' },
]

/**
 * Подписи счётчиков журнала запусков — с сервера: counter_labels вида подключения (GET /kinds: общие подписи
 * каркаса и свои коннектора). Запасные — на случай, если описания вида нет (вид удалён из сервера).
 */
const FALLBACK_COUNTER_LABELS = {
  values: 'значений', created: 'новых', updated: 'изменено', unchanged: 'без изменений', cleared: 'очищено',
  files: 'файлов', added: 'во «Входящие»', seen: 'уже забраны', errors: 'ошибок', skipped: 'пропущено',
  taken: 'взято файлов', applied: 'применено', pending: 'ждут подтверждения', duplicates: 'повторов',
}

/**
 * Сводка запуска: [{ key, label, value }] — ненулевые числовые счётчики с подписью (items — число элементов
 * входящих). labels — counter_labels вида подключения; счётчик без подписи не показывается (служебные числа,
 * например номер элемента, и английские ключи в журнал не попадают).
 */
export function runCounters(summary, { zeros = false, labels = null } = {}) {
  if (!summary || typeof summary !== 'object') return []
  const known = { ...FALLBACK_COUNTER_LABELS, ...(labels || {}) }
  const out = []
  for (const [key, value] of Object.entries(summary)) {
    if (key === 'items' && Array.isArray(value)) out.push({ key, label: known.items || 'элементов входящих', value: value.length })
    else if (typeof value === 'number' && known[key]) out.push({ key, label: known[key], value })
  }
  return zeros ? out : out.filter((c) => c.value)
}

/** Название в кавычках «…», если в нём своих кавычек нет: «Jira», но Папка «Входящие». */
export const quoted = (name) => (/[«»"]/.test(String(name || '')) ? String(name) : `«${name}»`)

export function runCountersText(summary, labels = null) {
  return runCounters(summary, { labels }).map((c) => `${c.label}: ${formatNumber(c.value)}`).join(' · ')
}

/**
 * Ошибка для карточки: только если она новее последнего успеха (сервер — current_error). Старая ошибка при
 * «Работает» не показывается — она остаётся в журнале запусков.
 */
export function currentError(integration) {
  const it = integration || {}
  if (typeof it.current_error === 'string') return it.current_error
  if (!it.last_error || !it.last_error_at) return ''
  return !it.last_ok_at || toTime(it.last_error_at) > toTime(it.last_ok_at) ? it.last_error : ''
}

/** Порядок видов — как на сервере (order: «По Делу», «Пульс проекта», Jira, Confluence, Bitrix24, Exchange, 1С, папка). */
export function kindOrder(kinds = []) {
  return (key) => {
    const index = kinds.findIndex((k) => k.kind === key)
    return index === -1 ? kinds.length : index
  }
}

/** Подключения в порядке видов, внутри вида — по названию (как отдаёт сервер). */
export function sortIntegrations(list = [], kinds = []) {
  const order = kindOrder(kinds)
  return [...list].sort((a, b) => order(a.kind) - order(b.kind) || String(a.name).localeCompare(String(b.name), 'ru'))
}

/** Вид только для администратора (admin_only: Confluence публикует полный отчёт) и пользователь — не администратор. */
export const adminOnlyFor = (kind, isAdmin) => !!kind?.admin_only && !isAdmin

/** Длительность запуска: «12 с», «3 мин 5 с», «—» — не закончен. */
export function runDuration(run) {
  if (!run?.started_at || !run?.finished_at) return '—'
  const seconds = Math.max(0, Math.round((toTime(run.finished_at) - toTime(run.started_at)) / 1000))
  if (seconds < 60) return `${seconds} с`
  const minutes = Math.floor(seconds / 60)
  return seconds % 60 ? `${minutes} мин ${seconds % 60} с` : `${minutes} мин`
}

function toTime(value) {
  const text = String(value)
  return new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(text) ? text : `${text}Z`).getTime()
}

/** Короткая ошибка для карточки: первая строка, не длиннее limit символов. */
export function shortError(text, limit = 160) {
  const line = String(text || '').split('\n').map((s) => s.trim()).find(Boolean) || ''
  return line.length > limit ? `${line.slice(0, limit - 1).trimEnd()}…` : line
}

// ---------------------------------------------------------------- поля настроек

export const FIELD_TYPES = ['string', 'text', 'url', 'password', 'int', 'bool', 'select', 'multiselect', 'list', 'time', 'json']

/** Поле JSON (правила Jira, запросы 1С) — или текст с признаком monospace: моноширинное многострочное поле. */
export const isJsonField = (field) => field?.type === 'json'
export const isMonospace = (field) => isJsonField(field) || (field?.type === 'text' && !!field.monospace)

/** Длина подписи варианта, с которой выбор из списка не помещается в половину формы («Server / Data Center — …»). */
export const LONG_OPTION = 26

/**
 * Поле на всю ширину формы: текст, список, адрес, JSON и выбор из списка с длинными подписями вариантов — иначе
 * выбранный вариант обрезается («Тип подключения» Jira и Confluence).
 */
export function isWideField(field) {
  if (['text', 'list', 'url', 'json'].includes(field?.type)) return true
  if (field?.type !== 'select') return false
  return [field.placeholder, ...(field.options || []).map((o) => o.label)].some((t) => String(t || '').length > LONG_OPTION)
}

/**
 * Выбор из 2–4 вариантов с длинными подписями («Тип подключения»: «Server / Data Center — персональный токен
 * (PAT)») — списком переключателей: выпадающий список на телефоне обрезал бы выбранный вариант.
 */
export const isChoiceField = (field) => field?.type === 'select' && (field.options || []).length <= 4 && isWideField(field)

/**
 * Разбор поля JSON: { ok, value, error }. Пусто — ok со значением null. Ошибка — «Ошибка JSON: строка 3,
 * столбец 7 — …» (место считается по позиции, которую сообщает браузер).
 */
export function parseJsonField(text) {
  const source = String(text ?? '')
  if (!source.trim()) return { ok: true, value: null, error: '' }
  try {
    return { ok: true, value: JSON.parse(source), error: '' }
  } catch (e) {
    const message = String(e?.message || 'неверный формат')
    const pos = message.match(/position (\d+)/)
    let where = ''
    const lc = message.match(/line (\d+) column (\d+)/)
    if (lc) where = `строка ${lc[1]}, столбец ${lc[2]}`
    else if (pos) {
      const before = source.slice(0, Number(pos[1]))
      const line = before.split('\n').length
      where = `строка ${line}, столбец ${before.length - before.lastIndexOf('\n')}`
    }
    return { ok: false, value: null, error: `Ошибка JSON: ${where ? `${where} — ` : ''}${jsonReason(message)}` }
  }
}

// Сообщения JSON.parse браузера — по-русски (неизвестное — как есть, без позиции: место уже указано)
const JSON_REASONS = [
  [/Unexpected end of JSON input|Unterminated string|end of data/i, 'JSON обрывается: не хватает закрывающей скобки или кавычки'],
  [/Expected double-quoted property name|property name/i, 'ожидается имя свойства в двойных кавычках (лишняя запятая?)'],
  [/Expected ',' or '}'/i, 'ожидается «,» или «}» после значения'],
  [/Expected ',' or ']'/i, 'ожидается «,» или «]» после элемента списка'],
  [/Unexpected non-whitespace character after JSON/i, 'лишние символы после JSON'],
  [/Bad control character/i, 'недопустимый символ в строке (перенос строки внутри кавычек?)'],
  [/Unexpected token '?(.)'?/i, (m) => `неожиданный символ «${m[1]}»`],
]
function jsonReason(message) {
  for (const [re, text] of JSON_REASONS) {
    const m = message.match(re)
    if (m) return typeof text === 'function' ? text(m) : text
  }
  return message.replace(/\s*\(line \d+ column \d+\)/, '').replace(/\s*in JSON at position \d+/, '').replace(/^JSON\.parse:\s*/, '')
}

/** Значение JSON для поля формы: разобранное — с отступами; строка с JSON — тоже; иначе — как есть. */
export function jsonText(value) {
  if (value === null || value === undefined || value === '') return ''
  if (typeof value === 'string') {
    const parsed = parseJsonField(value)
    return parsed.ok && parsed.value !== null ? JSON.stringify(parsed.value, null, 2) : value
  }
  return JSON.stringify(value, null, 2)
}

/** Высота поля JSON в строках: по содержимому, от 10 до 16. */
export const jsonRows = (text) => Math.min(16, Math.max(10, String(text || '').split('\n').length + 1))
const TIME_RE = /^([01]\d|2[0-3]):[0-5]\d$/
const isEmpty = (v) => v === null || v === undefined || (typeof v === 'string' && v.trim() === '') || (Array.isArray(v) && !v.length)

/**
 * Показывать ли поле: show_if = { поле: [значения] } — все условия выполнены. Значения сравниваются
 * как строки (true и «true» — одно и то же), как настройки приходят из формы.
 */
export function fieldVisible(field, values = {}) {
  const rules = field?.show_if
  if (!rules) return true
  return Object.entries(rules).every(([key, allowed]) => {
    const value = values[key]
    return (allowed || []).some((a) => a === value || String(a) === String(value ?? ''))
  })
}

export const visibleFields = (fields = [], values = {}) => fields.filter((f) => fieldVisible(f, values))

/**
 * Заполнитель поля при этих значениях формы: placeholder_if = { поле: { значение: заполнитель } } — первое
 * подходящее правило (у «По Делу» в режиме ключа «Список задач с данными» — «пусто — все списки ключа»); иначе placeholder.
 */
export function fieldPlaceholder(field, values = {}) {
  for (const [key, byValue] of Object.entries(field?.placeholder_if || {})) {
    const value = values?.[key]
    if (value !== null && value !== undefined && byValue && Object.hasOwn(byValue, String(value))) return byValue[String(value)]
  }
  return field?.placeholder || ''
}

/** Значение поля для формы: список — строками, число — текстом, да/нет — булево. */
export function toFormValue(field, value) {
  switch (field.type) {
    case 'bool': return value === null || value === undefined ? false : value === true || String(value).toLowerCase() === 'true'
    case 'multiselect': return Array.isArray(value) ? value.map(String) : []
    case 'list': return Array.isArray(value) ? value.join('\n') : String(value ?? '')
    case 'json': return jsonText(value)
    default: return value === null || value === undefined ? '' : String(value)
  }
}

/** Значение поля для API (как его приводит сервер): пустое — null, список — по строкам или запятым. */
export function toConfigValue(field, value) {
  switch (field.type) {
    case 'bool': return !!value
    case 'multiselect': return Array.isArray(value) ? [...value] : []
    case 'list': return (Array.isArray(value) ? value : String(value ?? '').split(/[\n,]/)).map((s) => String(s).trim()).filter(Boolean)
    case 'int': {
      const text = String(value ?? '').trim()
      return text === '' ? null : Number(text)
    }
    case 'json': {
      // Неверный JSON не уходит на сервер: форма его не пропускает (validateSettings)
      const parsed = parseJsonField(value)
      return parsed.ok ? parsed.value : String(value)
    }
    default: {
      const text = String(value ?? '').trim()
      return text === '' ? null : text
    }
  }
}

/** Начальные значения настроек (без секретов): сохранённые, иначе значения по умолчанию поля. */
export function initialValues(fields = [], config = {}) {
  const out = {}
  for (const f of fields) {
    if (f.secret) continue
    out[f.key] = toFormValue(f, config && f.key in config ? config[f.key] : f.default)
  }
  return out
}

/**
 * Состояние секретов: keep — сохранён, не меняется («задан»); replace — ввести (value); clear —
 * стереть. У нового подключения и у незаданных — replace с пустым значением.
 */
export function initialSecrets(fields = [], integration = null) {
  const saved = new Set(integration?.secret_fields || [])
  return Object.fromEntries(fields.filter((f) => f.secret).map((f) => [f.key, saved.has(f.key) ? { mode: 'keep', value: '' } : { mode: 'replace', value: '' }]))
}

/** Адрес для сравнения привязки секретов — как на сервере: схема и узел без регистра, без «/» в конце. */
export function normalizeUrl(url) {
  const text = String(url || '').trim()
  if (!text) return ''
  const match = text.match(/^([a-z][a-z0-9+.-]*:\/\/)([^/?#]*)(.*)$/i)
  if (!match) return text.replace(/\/+$/, '')
  return `${match[1].toLowerCase()}${match[2].toLowerCase()}${match[3].replace(/\/+$/, '')}`
}

/**
 * Поля, от которых зависит адрес привязки секретов: secret_url_fields вида подключения (у «По Делу» — оба
 * адреса, у Exchange — способ подключения и его адрес); у сервера без этого списка — url_field.
 */
export function bindingFields(kind) {
  if (Array.isArray(kind?.secret_url_fields)) return kind.secret_url_fields
  return kind?.url_field ? [kind.url_field] : []
}

const bindingValue = (field, value) => {
  const v = toConfigValue(field, value)
  if (v === null || v === undefined || v === '') return ''
  return field.type === 'url' ? normalizeUrl(v) : Array.isArray(v) ? JSON.stringify(v) : String(v)
}

/**
 * Изменённые поля привязки секретов: [{ key, label }] — видимые в форме поля из bindingFields, которые
 * отличаются от сохранённых настроек (адреса сравниваются как на сервере). Если секреты сохранены, после
 * такого изменения сервер потребует ввести их заново (secret_rebind_required) — форма предупреждает заранее.
 */
export function bindingChanges(kind, values, integration) {
  if (!integration?.has_secret) return []
  const saved = integration.config || {}
  const out = []
  for (const key of bindingFields(kind)) {
    const field = (kind?.fields || []).find((f) => f.key === key)
    if (!field || field.secret || !fieldVisible(field, values)) continue
    const before = key in saved ? saved[key] : field.default
    if (bindingValue(field, values?.[key]) !== bindingValue(field, toFormValue(field, before))) out.push({ key, label: field.label })
  }
  return out
}

/** Адрес привязки сохранённых секретов изменён — их нужно ввести заново. */
export const urlChanged = (kind, values, integration) => bindingChanges(kind, values, integration).length > 0

/** Секреты при смене адреса: сохранённые больше не подходят — их нужно ввести заново. */
export function rebindSecrets(secrets) {
  return Object.fromEntries(Object.entries(secrets).map(([k, s]) => [k, s.mode === 'keep' ? { mode: 'replace', value: '' } : s]))
}

/**
 * Ошибки формы до отправки: { 'config.поле' | 'secrets.поле' | 'name': текст }. Скрытые (show_if)
 * поля не проверяются; сервер всё равно проверяет всё сам.
 */
export function validateSettings(kind, values = {}, secrets = {}, { name } = {}) {
  const errors = {}
  if (name !== undefined && !String(name || '').trim()) errors.name = 'Укажите название'
  for (const f of kind?.fields || []) {
    if (!fieldVisible(f, values)) continue
    if (f.secret) {
      const s = secrets[f.key] || { mode: 'replace', value: '' }
      const has = s.mode === 'keep' || (s.mode === 'replace' && String(s.value || '').trim())
      if (f.required && !has) errors[`secrets.${f.key}`] = 'Обязательное поле'
      continue
    }
    const value = values[f.key]
    const key = `config.${f.key}`
    if (f.type === 'bool') continue
    if (isEmpty(value)) {
      if (f.required) errors[key] = 'Обязательное поле'
      continue
    }
    if (f.type === 'int') {
      const text = String(value).trim()
      if (!/^-?\d+$/.test(text)) errors[key] = 'Нужно целое число'
      else if ((f.min !== null && f.min !== undefined && Number(text) < f.min) || (f.max !== null && f.max !== undefined && Number(text) > f.max)) {
        errors[key] = rangeText(f.min, f.max)
      }
    } else if (f.type === 'url') {
      const text = String(value).trim()
      if (!/^https?:\/\//i.test(text)) errors[key] = 'Адрес начинается с http:// или https://'
      else if (/[?#\s@]/.test(text.replace(/^https?:\/\//i, ''))) errors[key] = 'Только https://узел[:порт][/путь] — без логина, «?» и «#»'
    } else if (f.type === 'json') {
      const parsed = parseJsonField(value)
      if (!parsed.ok) errors[key] = parsed.error
    } else if (f.type === 'time' && !TIME_RE.test(String(value).trim())) {
      errors[key] = 'Время в формате ЧЧ:ММ'
    } else if (f.type === 'select' && f.options?.length && !f.options.some((o) => o.value === value)) {
      errors[key] = 'Выберите значение из списка'
    }
  }
  return errors
}

function rangeText(min, max) {
  const has = (v) => v !== null && v !== undefined
  if (has(min) && has(max)) return `От ${formatNumber(min)} до ${formatNumber(max)}`
  return has(min) ? `Не меньше ${formatNumber(min)}` : `Не больше ${formatNumber(max)}`
}

/**
 * Тело запроса из формы: config — все настройки (без секретов), secrets — только введённые
 * значения, clear_secrets — что стереть. Сохранённый секрет без изменений не передаётся.
 */
export function settingsPayload(kind, values = {}, secrets = {}) {
  const config = {}
  const out = {}
  const clear = []
  for (const f of kind?.fields || []) {
    if (!f.secret) {
      config[f.key] = toConfigValue(f, values[f.key])
      continue
    }
    const s = secrets[f.key]
    if (!s) continue
    if (s.mode === 'replace' && String(s.value || '') !== '') out[f.key] = s.value
    else if (s.mode === 'clear') clear.push(f.key)
  }
  return { config, secrets: out, clear_secrets: clear }
}

/** Подсказка к адресу: какой переменной окружения сервер разрешает узлы этого вида. */
export function allowedHostsHint(kind) {
  if (!kind?.allowed_hosts_env) return ''
  return `Узел должен быть разрешён на сервере переменной ${kind.allowed_hosts_env} (через запятую; «.company.ru» — домен и поддомены; пусто — без ограничения)`
}

/**
 * Итог проверки: ok — «Подключено» (зелёный); ok с замечаниями (warnings) — «Подключено с замечаниями» (жёлтый);
 * иначе — ошибка (красный). { tone: 'ok' | 'warn' | 'bad', title, icon }.
 */
export function checkState(result) {
  if (!result?.ok) return { tone: 'bad', title: 'Проверка не прошла', icon: 'alert' }
  if (checkWarnings(result).length) return { tone: 'warn', title: 'Подключено с замечаниями', icon: 'alert' }
  return { tone: 'ok', title: 'Подключение работает', icon: 'check' }
}

/** Фраза с заглавной буквы: замечания сервер пишет со строчной («у ключа нет права …»). */
export const sentence = (text) => {
  const s = String(text ?? '').trim()
  return s ? s[0].toUpperCase() + s.slice(1) : ''
}

/** Замечания проверки списком — фразами с заглавной буквы, без пустых. */
export const checkWarnings = (result) => (Array.isArray(result?.warnings) ? result.warnings : []).map(sentence).filter(Boolean)

/**
 * Подписи подробностей проверки — с сервера: detail_labels вида подключения (GET /kinds: общие подписи каркаса
 * и свои коннектора). Запасные — общие подписи каркаса на случай, если описания вида нет.
 */
const FALLBACK_DETAIL_LABELS = {
  mode: 'Режим подключения', version: 'Версия', user: 'Учётная запись', key: 'Ключ', scopes: 'Права',
  departments: 'Подразделений', lists: 'Списки задач', projects: 'Проектов', role: 'Роль', department: 'Подразделение',
}
// Код ошибки — для подсказки (checkHint), не для показа; заголовок вложенной записи — «Название (id)», без подписей
const HIDDEN_DETAILS = ['code']
const RECORD_TITLE = ['title', 'name', 'label', 'displayName']
const RECORD_REF = ['id', 'login']
const DETAIL_LIST_LIMIT = 30

const isRecord = (v) => !!v && typeof v === 'object' && !Array.isArray(v)
const present = (v) => v !== null && v !== undefined && v !== '' && !(Array.isArray(v) && !v.length) && !(isRecord(v) && !Object.keys(v).length)

/** Подпись внутри строки — со строчной буквы («проектов: 2»), сокращения — как есть («ID пользователя»). */
export function inlineLabel(label) {
  const s = String(label || '')
  return s.length > 1 && /\p{Lu}/u.test(s[0]) && /\p{Ll}/u.test(s[1]) ? s[0].toLowerCase() + s.slice(1) : s
}

function scalarText(value) {
  if (value === true || value === false) return value ? 'да' : 'нет'
  if (typeof value === 'number') return formatNumber(value)
  return String(value)
}

function listText(values, limit = 12) {
  const shown = values.slice(0, limit).map((v) => (isRecord(v) || Array.isArray(v) ? JSON.stringify(v) : scalarText(v)))
  return shown.join(', ') + (values.length > limit ? ` и ещё ${formatNumber(values.length - limit)}` : '')
}

/**
 * Вложенная запись строкой: «Название (id) · подпись: значение · …». Название — title, name, label или displayName;
 * id или login — в скобках (или вместо названия, если его нет); остальные ключи — только подписанные и не служебные.
 */
export function recordText(record, labels = {}, technical = new Set()) {
  const pick = (keys) => keys.map((k) => record[k]).find(present)
  const title = pick(RECORD_TITLE)
  const ref = pick(RECORD_REF)
  const head = present(title) ? (present(ref) && String(ref) !== String(title) ? `${title} (${ref})` : String(title)) : present(ref) ? String(ref) : ''
  const rest = Object.entries(record)
    .filter(([k, v]) => ![...RECORD_TITLE, ...RECORD_REF].includes(k) && !technical.has(k) && labels[k] && present(v))
    .map(([k, v]) => `${inlineLabel(labels[k])}: ${Array.isArray(v) ? listText(v) : isRecord(v) ? JSON.stringify(v) : scalarText(v)}`)
  return [head, ...rest].filter(Boolean).join(' · ')
}

/** Значение поля-выбора подписью варианта: mode «key» — «Ключ интеграции (По Делу 1.4.5 и новее)». */
function optionLabel(kind, key, value) {
  const field = (kind?.fields || []).find((f) => f.key === key && f.options?.length)
  return field?.options.find((o) => o.value === String(value))?.label
}

/** Служебное значение для «Технических подробностей»: как есть, длинное — с многоточием. */
function rawText(value, limit = 300) {
  const text = isRecord(value) || Array.isArray(value) ? JSON.stringify(value) : String(value)
  return text.length > limit ? `${text.slice(0, limit - 1)}…` : text
}

/**
 * Подробности проверки для показа: { main, technical }. main — [{ key, label, text, items }] ключей с русской
 * подписью (detail_labels вида): да/нет, числа, списки через запятую, записи строкой «Название (id) · …», списки
 * записей — items, по строке на запись; поле-выбор (mode) — подписью варианта. technical — [{ key, value }]: служебные
 * (technical_details) и неподписанные ключи — для свёрнутых «Технических подробностей». Пустые значения и код ошибки
 * не показываются.
 */
export function checkDetails(details, kind = null) {
  const out = { main: [], technical: [] }
  if (!isRecord(details)) return out
  const labels = { ...FALLBACK_DETAIL_LABELS, ...(kind?.detail_labels || {}) }
  const technical = new Set(['code', ...(kind?.technical_details || [])])
  for (const [key, value] of Object.entries(details)) {
    if (HIDDEN_DETAILS.includes(key) || !present(value)) continue
    if (technical.has(key) || !labels[key]) {
      out.technical.push({ key, value: rawText(value) })
      continue
    }
    const entry = { key, label: labels[key], text: '', items: null }
    if (Array.isArray(value) && value.some(isRecord)) {
      const lines = value.map((v) => (isRecord(v) ? recordText(v, labels, technical) : scalarText(v))).filter(Boolean)
      entry.items = lines.slice(0, DETAIL_LIST_LIMIT)
      if (lines.length > DETAIL_LIST_LIMIT) entry.items.push(`и ещё ${formatNumber(lines.length - DETAIL_LIST_LIMIT)}`)
    } else if (Array.isArray(value)) entry.text = listText(value)
    else if (isRecord(value)) entry.text = recordText(value, labels, technical)
    else entry.text = optionLabel(kind, key, value) || scalarText(value)
    if (entry.text || entry.items?.length) out.main.push(entry)
  }
  return out
}

/** Что делать, если проверка не прошла, — по коду ошибки. */
export function checkHint(result, kind) {
  const code = result?.details?.code
  if (code === 'host_not_allowed') return allowedHostsHint(kind) || 'Узел запрещён настройками сервера'
  if (['secret_rebind_required', 'secret_unreadable', 'secret_missing'].includes(code)) return 'Введите токен или пароль заново и проверьте снова'
  if (code === 'bad_url' || code === 'config') return 'Проверьте адрес подключения'
  return ''
}

// ---------------------------------------------------------------- длинные описания и подсказки

/**
 * Описание или подсказка коннектора блоками: текст (переносы строк сохраняются) и код из тройных
 * обратных кавычек ```1c … ``` (моноширинно, с отступами). [{ type: 'text' | 'code', value, lang }].
 */
export function richBlocks(text) {
  const source = String(text || '').replace(/\r\n/g, '\n')
  const out = []
  const re = /```([\w+-]*)[ \t]*\n?([\s\S]*?)```/g
  let last = 0
  let m
  while ((m = re.exec(source))) {
    const before = source.slice(last, m.index).replace(/^\n+|\s+$/g, '')
    if (before) out.push({ type: 'text', value: before, lang: '' })
    out.push({ type: 'code', value: m[2].replace(/\s+$/, ''), lang: m[1] || '' })
    last = re.lastIndex
  }
  const rest = source.slice(last).replace(/^\n+|\s+$/g, '')
  if (rest) out.push({ type: 'text', value: rest, lang: '' })
  return out.flatMap((b) => (b.type === 'text' ? splitIndentedCode(b.value) : [b]))
}

/**
 * Код без кавычек: строки после «…:», среди которых не меньше двух с отступом (пример для 1С в описании
 * коннектора), — тоже моноширинным блоком, до пустой строки.
 */
function splitIndentedCode(text) {
  const lines = text.split('\n')
  for (let i = 0; i < lines.length - 1; i += 1) {
    if (!/:\s*$/.test(lines[i])) continue
    let end = i + 1
    while (end < lines.length && lines[end].trim()) end += 1
    const body = lines.slice(i + 1, end)
    if (body.filter((l) => /^(\t| {2,})\S/.test(l)).length < 2) continue
    const before = lines.slice(0, i + 1).join('\n').trim()
    const after = lines.slice(end).join('\n').trim()
    return [
      ...(before ? [{ type: 'text', value: before, lang: '' }] : []),
      { type: 'code', value: body.join('\n'), lang: '' },
      ...(after ? splitIndentedCode(after) : []),
    ]
  }
  return [{ type: 'text', value: text, lang: '' }]
}

/** Длинный текст сворачивается под «Подробнее»: код, несколько абзацев или больше limit символов. */
export function isLongText(text, limit = 220) {
  const source = String(text || '')
  return source.length > limit || source.includes('```') || source.split('\n').filter((l) => l.trim()).length > 2
}

/** Начало текста для свёрнутого вида: первый абзац без кода, не длиннее limit символов. */
export function richPreview(text, limit = 180) {
  const first = richBlocks(text).find((b) => b.type === 'text')?.value.split(/\n\s*\n/)[0].replace(/\s+/g, ' ').trim() || ''
  return first.length > limit ? `${first.slice(0, limit - 1).replace(/\s+\S*$/, '')}…` : first
}

// ---------------------------------------------------------------- расписание

/** Записи расписания одного подключения: у каждой свой вид, время и действия; не больше MAX_SCHEDULES. */
export const MAX_SCHEDULES = 5
export const SCHEDULE_MODES = [
  { value: 'interval', label: 'Через интервал' },
  { value: 'daily', label: 'В заданное время' },
]
export const WEEKDAYS = [
  { value: 1, label: 'пн', full: 'понедельник' }, { value: 2, label: 'вт', full: 'вторник' },
  { value: 3, label: 'ср', full: 'среда' }, { value: 4, label: 'чт', full: 'четверг' },
  { value: 5, label: 'пт', full: 'пятница' }, { value: 6, label: 'сб', full: 'суббота' },
  { value: 7, label: 'вс', full: 'воскресенье' },
]
export const INTERVAL_PRESETS = [15, 30, 60, 180, 720, 1440]
export const MIN_INTERVAL = 5
export const MAX_INTERVAL = 7 * 24 * 60

export const schedulableActions = (kind) => (kind?.actions || []).filter((a) => a.schedulable)

/** «каждые 15 минут», «каждый час», «каждые 3 часа», «раз в сутки». */
export function intervalText(minutes) {
  const n = Number(minutes)
  if (!Number.isFinite(n) || n <= 0) return '—'
  if (n % 1440 === 0) return n === 1440 ? 'раз в сутки' : `каждые ${n / 1440} ${plural(n / 1440, ['сутки', 'суток', 'суток'])}`
  if (n % 60 === 0) {
    const h = n / 60
    return h === 1 ? 'каждый час' : `${plural(h, ['каждый', 'каждые', 'каждые'])} ${h} ${plural(h, ['час', 'часа', 'часов'])}`
  }
  return `${plural(n, ['каждую', 'каждые', 'каждые'])} ${n} ${plural(n, ['минуту', 'минуты', 'минут'])}`
}

/** Записи расписания из API: список (0.4.0) или прежний вид — один объект; {} и mode off — вручную. */
export function scheduleEntries(schedule) {
  const list = Array.isArray(schedule) ? schedule : schedule && typeof schedule === 'object' ? [schedule] : []
  return list.filter((e) => e && ['interval', 'daily'].includes(e.mode))
}

/** Подпись записи — как на сервере: «Каждые 60 мин», «В 06:30 (пн, пт)», «В 06:30 ежедневно». */
export function entryLabel(entry) {
  const s = entry || {}
  if (s.mode === 'interval' && s.minutes) return `Каждые ${s.minutes} мин`
  if (s.mode === 'daily' && s.time) {
    const days = [...(s.weekdays || [])].sort((a, b) => a - b)
    const names = days.map((d) => WEEKDAYS.find((w) => w.value === d)?.label).filter(Boolean)
    return `В ${s.time}${names.length && names.length < 7 ? ` (${names.join(', ')})` : ' ежедневно'}`
  }
  return 'Вручную'
}

const actionNames = (entry, kind) => (entry.actions || []).map((key) => (kind?.actions || []).find((a) => a.key === key)?.label || key)

/**
 * Подпись расписания — как на сервере (schedule_label): «Вручную»; одна запись — её подпись; несколько —
 * через «;» с действиями: «Каждые 30 мин — Забрать данные из задач; В 06:00 ежедневно — Синхронизировать структуру».
 */
export function scheduleLabel(schedule, kind = null) {
  const entries = scheduleEntries(schedule).filter((e) => entryLabel(e) !== 'Вручную')
  if (!entries.length) return 'Вручную'
  if (entries.length === 1) return entryLabel(entries[0])
  return entries.map((e) => {
    const names = actionNames(e, kind)
    return `${entryLabel(e)}${names.length ? ` — ${names.join(', ')}` : ''}`
  }).join('; ')
}

/** Черновик записи для формы; действия — сохранённые (допустимые) или переданные по умолчанию. */
export function entryDraft(entry, kind, fallback = null) {
  const s = entry || {}
  const allowed = schedulableActions(kind).map((a) => a.key)
  const actions = (s.actions || []).filter((a) => allowed.includes(a))
  return {
    mode: s.mode === 'daily' ? 'daily' : 'interval',
    minutes: s.minutes ? String(s.minutes) : '60',
    time: s.time || '06:00',
    weekdays: [...(s.weekdays || [])].sort((a, b) => a - b),
    actions: actions.length ? actions : (fallback || allowed.slice(0, 1)),
  }
}

/** Черновик расписания: список записей (пустой — вручную). */
export function scheduleDraft(schedule, kind) {
  return scheduleEntries(schedule).map((e) => entryDraft(e, kind))
}

/**
 * Новая запись «Добавить расписание»: через интервал 60 минут; действие — первое по расписанию, которого ещё нет
 * в других записях (у «По Делу» вторая запись получает «Забрать данные из задач»), иначе первое.
 */
export function newScheduleEntry(kind, drafts = []) {
  const allowed = schedulableActions(kind).map((a) => a.key)
  const used = new Set(drafts.flatMap((d) => d.actions || []))
  const free = allowed.find((a) => !used.has(a)) || allowed[0]
  return entryDraft({ mode: 'interval', minutes: 60, actions: free ? [free] : [] }, kind)
}

export const canAddSchedule = (drafts = [], kind = null) => drafts.length < MAX_SCHEDULES && schedulableActions(kind).length > 0

/**
 * Ошибки черновика: { 'schedule.<номер записи с 0>.minutes' | '….time' | '….actions' | 'schedule': текст } —
 * те же поля, что в ошибках сервера.
 */
export function scheduleErrors(drafts, kind) {
  const errors = {}
  const list = Array.isArray(drafts) ? drafts : []
  if (!list.length) return errors
  if (!schedulableActions(kind).length) {
    errors.schedule = 'У этого подключения нет действий по расписанию'
    return errors
  }
  if (list.length > MAX_SCHEDULES) errors.schedule = `Не больше ${MAX_SCHEDULES} расписаний у подключения`
  list.forEach((draft, n) => {
    const place = `schedule.${n}`
    if (draft.mode === 'interval') {
      const text = String(draft.minutes ?? '').trim()
      const value = Number(text)
      if (!/^\d+$/.test(text) || value < MIN_INTERVAL || value > MAX_INTERVAL) errors[`${place}.minutes`] = `Целое число минут от ${MIN_INTERVAL} до ${formatNumber(MAX_INTERVAL)} (неделя)`
    }
    if (draft.mode === 'daily' && !TIME_RE.test(String(draft.time || ''))) errors[`${place}.time`] = 'Время в формате ЧЧ:ММ'
    if (!draft.actions?.length) errors[`${place}.actions`] = 'Выберите хотя бы одно действие'
  })
  return errors
}

/** Тело расписания для API: список записей с интервалом или временем, днями и действиями ([] — вручную). */
export function schedulePayload(drafts) {
  return (Array.isArray(drafts) ? drafts : []).map((draft) => {
    const base = { mode: draft.mode, actions: [...(draft.actions || [])] }
    if (draft.mode === 'interval') return { ...base, minutes: Number(String(draft.minutes).trim()) }
    return { ...base, time: draft.time, weekdays: [...new Set(draft.weekdays || [])].sort((a, b) => a - b) }
  })
}

/** Действия, которые выполняются хотя бы одной записью расписания (для отметки «по расписанию» на карточке). */
export const scheduledActions = (schedule) => [...new Set(scheduleEntries(schedule).flatMap((e) => e.actions || []))]

export function toggleWeekday(weekdays = [], day) {
  return weekdays.includes(day) ? weekdays.filter((d) => d !== day) : [...weekdays, day].sort((a, b) => a - b)
}

// ---------------------------------------------------------------- ключи и примеры

export function keyState(key) {
  return key?.active ? { label: 'Действует', tone: 'green' } : { label: 'Отозван', tone: 'gray' }
}

/** Пример вызова приёма файла для 1С, скриптов и других систем. */
export function curlExample({ origin = '', key = 'dash_…', dataset = '', filename = 'выгрузка.xlsx', apply = null } = {}) {
  const parts = [
    `curl -X POST "${origin}/api/inbound/v1/files"`,
    `  -H "Authorization: Bearer ${key}"`,
    `  -F "file=@${filename}"`,
  ]
  if (dataset) parts.push(`  -F "dataset=${dataset}"`)
  if (apply !== null) parts.push(`  -F "apply=${apply ? 'true' : 'false'}"`)
  return parts.join(' \\\n')
}

export function pingExample({ origin = '', key = 'dash_…' } = {}) {
  return `curl "${origin}/api/inbound/v1/ping" -H "Authorization: Bearer ${key}"`
}
