/**
 * Администрирование: пользователи (список, фильтры, сводка, статусы, формы), разбор записей журнала,
 * правила светофора, палитры. Модель доступа — domain/access.js. Чистые функции — покрыты
 * тестами (admin.test.js).
 */
import { LEVEL_LABELS, SERVICE_LEVEL_LABELS } from '@/domain/access'
import { FALLBACK } from '@/stores/palette'
import { DIRECTION_LABELS } from '@/utils/lights'
import { formatNumber, plural } from '@/utils/format'

// ---------- пользователи ----------

export const ROLE_LABELS = { admin: 'Администратор', user: 'Пользователь' }
export const STATUS_LABELS = { active: 'Активен', disabled: 'Отключён', no_access: 'Без доступа' }
export const AUTH_SOURCE_LABELS = { local: 'Пароль системы', ldap: 'Учётная запись домена' }
/** Логин: латиница, цифры и . _ @ - (как на сервере). */
export const USERNAME_PATTERN = '[A-Za-z0-9._@\\-]+'
const USERNAME_RE = /^[A-Za-z0-9._@-]+$/

export function isValidUsername(value) {
  return typeof value === 'string' && value.length >= 2 && USERNAME_RE.test(value)
}

/** Сначала службы с дашбордом, остальные — в прежнем порядке. */
export function sortServices(services) {
  return [...(services || [])].map((s, i) => ({ s, i }))
    .sort((a, b) => Number(!!b.s.has_dashboard) - Number(!!a.s.has_dashboard) || a.i - b.i)
    .map(({ s }) => s)
}

/** Фильтры списка пользователей (в адресной строке); '' — все. department и profile: id или none. */
export const USER_FILTERS = Object.freeze({ search: '', role: '', status: '', department: '', profile: '', auth: '' })

/** Параметры GET /users из фильтров страницы. */
export function usersParams(f) {
  return {
    search: (f.search || '').trim(),
    role: f.role || '',
    status: f.status || '',
    department_id: f.department || '',
    profile_id: f.profile || '',
    auth_source: f.auth || '',
  }
}

/**
 * Сводка для шапки «N всего · активных · отключено · без доступа · по домену · администраторов»;
 * filter — что выставить в фильтрах по щелчку.
 */
export function summaryParts(summary) {
  if (!summary) return []
  const n = (key) => summary[key] ?? 0
  return [
    { key: 'total', count: n('total'), label: 'всего', filter: {} },
    { key: 'active', count: n('active'), label: plural(n('active'), ['активный', 'активных', 'активных']), filter: { status: 'active' } },
    { key: 'disabled', count: n('disabled'), label: 'отключено', filter: { status: 'disabled' } },
    { key: 'no_access', count: n('no_access'), label: 'без доступа', filter: { status: 'no_access' } },
    { key: 'ldap', count: n('ldap'), label: 'по домену', filter: { auth: 'ldap' } },
    { key: 'admins', count: n('admins'), label: plural(n('admins'), ['администратор', 'администратора', 'администраторов']), filter: { role: 'admin' } },
  ]
}

/** Метки в строке пользователя: «Вы», «домен», «без пароля», «администратор», «временный пароль». */
export function userBadges(user, meId = null) {
  const badges = []
  if (!user) return badges
  if (meId && user.id === meId) badges.push({ key: 'self', label: 'Вы', tone: 'self', title: 'Ваша учётная запись' })
  if (user.role === 'admin') badges.push({ key: 'admin', label: 'администратор', tone: 'brand', title: 'Полный доступ ко всем службам и администрированию' })
  if (user.auth_source === 'ldap') badges.push({ key: 'ldap', label: 'домен', tone: 'blue', title: 'Входит по учётной записи домена; пароль хранит домен' })
  else if (!user.has_password) badges.push({ key: 'no_password', label: 'без пароля', tone: 'yellow', title: 'Пароль не задан — войти не может, пока не выдан доступ' })
  else if (user.must_change_password) badges.push({ key: 'temporary', label: 'временный пароль', tone: 'gray', title: 'При входе пользователь задаст свой пароль' })
  return badges
}

/** Нужен ли «Выдать доступ»: войти не может — нет пароля (не домен). */
export function needsAccess(user) {
  return !!user && user.status === 'no_access'
}

/** Подразделение: название и путь до него («АЛМИ Партнер / Техническая дирекция»). */
export function departmentParts(department) {
  if (!department) return { name: '', parent: '', path: '' }
  const parts = String(department.path || department.name).split(' / ')
  return { name: department.name || parts.at(-1), parent: parts.slice(0, -1).join(' / '), path: department.path || department.name }
}

/** Руководитель для строки: «Соколова Мария Игоревна», явный — с пометкой. */
export function managerLabel(manager) {
  if (!manager) return ''
  return manager.source === 'explicit' ? `${manager.full_name} · назначен явно` : manager.full_name
}

/** Сброс пароля: у доменной учётной записи — «Перевести на пароль системы». */
export function resetAction(user) {
  const name = user ? `${user.full_name} (${user.username})` : ''
  if (user?.auth_source === 'ldap') {
    return {
      label: 'Перевести на пароль системы', icon: 'key',
      title: 'Перевести на пароль системы?', confirmText: 'Перевести',
      message: `${name} входит по учётной записи домена. Будет создан временный пароль системы — передайте его пользователю; все сессии будут завершены. Вход с паролем домена снова привяжет учётную запись к домену.`,
    }
  }
  return {
    label: 'Сбросить пароль', icon: 'key',
    title: 'Сбросить пароль?', confirmText: 'Сбросить пароль',
    message: `${name}.\nТекущий пароль перестанет действовать, все сессии пользователя будут завершены. Будет создан временный пароль — при входе система попросит задать новый.`,
  }
}

/** Личные уровни служб из строк доступа (UserOut.access) — «лично: Техподдержка — управление». */
export function personalServices(user, services = []) {
  if (!user || user.role === 'admin') return []
  const titles = Object.fromEntries((services || []).map((s) => [s.key, s.short_title || s.title]))
  return (user.access || []).map((a) => ({
    key: a.service_key,
    title: titles[a.service_key] || a.service_key,
    level: a.level,
    label: a.level === 'none' ? 'нет доступа' : (LEVEL_LABELS[a.level] || SERVICE_LEVEL_LABELS[a.level] || a.level).toLowerCase(),
  }))
}

/** Способы входа новой учётной записи. */
export const ACCESS_METHODS = [
  { value: 'password', label: 'Временный пароль', hint: 'Пароль покажется один раз — при первом входе пользователь задаст свой' },
  { value: 'ldap', label: 'Вход по домену', hint: 'Логин и пароль домена; учётная запись сопоставится с каталогом по e-mail' },
  { value: 'none', label: 'Без доступа', hint: 'Учётная запись без пароля — доступ выдадите позже' },
]

/** Форма нового пользователя. */
export function newUserForm() {
  return {
    username: '', full_name: '', email: '', position: '', phone: '', department_id: null, role: 'user',
    profile_id: null, access_method: 'password', password: '', capabilities: [], services: {},
  }
}

/** Тело POST /users. services — личные уровни служб { служба: уровень } ('' — как в профиле). */
export function createUserBody(form, { isAdmin = true } = {}) {
  const role = isAdmin ? form.role : 'user'
  return {
    username: (form.username || '').trim(),
    full_name: (form.full_name || '').trim(),
    email: (form.email || '').trim(),
    position: (form.position || '').trim() || null,
    phone: (form.phone || '').trim() || null,
    role,
    access_method: form.access_method,
    password: form.access_method === 'password' && form.password ? form.password : null,
    department_id: form.department_id ?? null,
    profile_id: form.profile_id ?? null,
    capabilities: isAdmin && role !== 'admin' ? [...(form.capabilities || [])] : [],
    access: role === 'admin' ? [] : Object.entries(form.services || {}).filter(([, level]) => level)
      .map(([service_key, level]) => ({ service_key, level })),
  }
}

const PROFILE_FIELDS = ['full_name', 'email', 'position', 'phone', 'role', 'is_active']

/** Карточка пользователя для формы. */
export function profileForm(user) {
  return {
    full_name: user?.full_name || '',
    email: user?.email || '',
    position: user?.position || '',
    phone: user?.phone || '',
    role: user?.role || 'user',
    is_active: user?.is_active ?? true,
    department_id: user?.department?.id ?? null,
    capabilities: [...(user?.capabilities || [])].sort(),
  }
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

/** Проверка полей формы пользователя до отправки: { поле: сообщение }. */
export function userFormErrors(form, { isNew = false } = {}) {
  const errors = {}
  if (isNew && !isValidUsername((form.username || '').trim())) errors.username = 'Не короче 2 символов: латиница, цифры и . _ @ -'
  if (!(form.full_name || '').trim()) errors.full_name = 'Укажите ФИО'
  const email = (form.email || '').trim()
  if (email && !EMAIL_RE.test(email)) errors.email = 'Некорректный e-mail'
  if (isNew && form.access_method === 'ldap' && !email) errors.email = 'Для входа по домену нужен e-mail: по нему учётная запись сопоставляется с каталогом'
  return errors
}

/** Только изменённые поля карточки — тело PATCH /users/{id}. */
export function profilePatch(user, form) {
  const base = profileForm(user)
  const patch = {}
  for (const key of PROFILE_FIELDS) {
    const value = typeof form[key] === 'string' ? form[key].trim() : form[key]
    if (value !== base[key]) patch[key] = value
  }
  if ((form.department_id ?? null) !== base.department_id) patch.department_id = form.department_id ?? null
  const caps = [...(form.capabilities || [])].sort()
  if (caps.join(',') !== base.capabilities.join(',')) patch.capabilities = caps
  return patch
}

/** Ошибки полей с сервера → поля формы (пароль проверяется общим правилом new_password). */
export function formFieldErrors(fields) {
  const out = {}
  for (const [key, message] of Object.entries(fields || {})) {
    const name = key === 'new_password' ? 'password' : key.split('.')[0]
    if (!out[name]) out[name] = message
  }
  return out
}

/** Журнал пользователя: записи карточки и доступа с его id, без повторов, новые сверху. */
export function userHistory(lists, userId) {
  const seen = new Set()
  return (lists || []).flat().filter((e) => {
    if (!e || seen.has(e.id)) return false
    seen.add(e.id)
    return e.entity_type === 'session' || String(e.entity_id) === String(userId)
  }).sort((a, b) => String(b.occurred_at).localeCompare(String(a.occurred_at)))
}

/** Инициалы по первым буквам слов (скобки и знаки пропускаются). */
export function initials(name) {
  return String(name || '').split(/\s+/).map((w) => w.match(/[\p{L}\p{N}]/u)?.[0]).filter(Boolean)
    .slice(0, 2).map((ch) => ch.toUpperCase()).join('') || '?'
}

/** Номер оттенка аватара (1–7, цвета серий палитры) — постоянный для логина. */
export function avatarTone(seed) {
  let h = 0
  for (const ch of String(seed || '')) h = (h * 31 + ch.charCodeAt(0)) >>> 0
  return (h % 7) + 1
}

// ---------- журнал изменений ----------

export const ACTION_LABELS = {
  create: 'Создание', update: 'Изменение', delete: 'Удаление', login: 'Вход', password: 'Пароль', import: 'Загрузка',
  grant: 'Выдача доступа',
  // входящие данные и интеграции (0.4.0)
  receive: 'Получение', duplicate: 'Повтор файла', apply: 'Применение', reject: 'Отклонение', retry: 'Повторная обработка',
  check: 'Проверка', run: 'Запуск', reissue: 'Выпуск заново', revoke: 'Отзыв',
}
export const ACTION_TONES = {
  create: 'green', update: 'blue', delete: 'red', login: 'gray', password: 'yellow', import: 'dark', grant: 'green',
  receive: 'gray', duplicate: 'gray', apply: 'green', reject: 'yellow', retry: 'blue', check: 'gray', run: 'dark', reissue: 'yellow', revoke: 'red',
}

export const ENTITY_LABELS = {
  indicator: 'Показатель',
  indicator_value: 'Значения показателей',
  unit_status_note: 'Заметка о статусе',
  report_settings: 'Настройки сквозного отчёта',
  user: 'Пользователь',
  user_access: 'Доступ пользователя',
  access_profile: 'Профиль доступа',
  department: 'Подразделение',
  hr_month: 'Месяц HR',
  hr_metrics: 'Метрики месяца',
  hr_event: 'Приём или увольнение',
  hr_note: 'Заметка к месяцу',
  hr_target: 'Цель',
  tp_week: 'Неделя ТП',
  naumen_ticket: 'Заявки Naumen',
  partnership: 'Партнёрство',
  partnership_light_rule: 'Светофор партнёрств',
  traffic_light_rule: 'Правило светофора',
  palette: 'Палитра',
  service_setting: 'Настройка службы',
  custom_dashboard: 'Мой дашборд',
  session: 'Сессия',
  inbox_item: 'Элемент входящих',
  inbox_rule: 'Правила входящих',
  integration: 'Подключение',
  inbound_key: 'Ключ входящих вызовов',
}

export const actionLabel = (action) => ACTION_LABELS[action] || action || '—'
export const entityLabel = (type) => ENTITY_LABELS[type] || type || '—'

/** Подписи полей в «было → стало». Ключи вне словаря показываются как есть. */
export const FIELD_LABELS = {
  username: 'Логин', full_name: 'ФИО', email: 'E-mail', position: 'Должность', phone: 'Телефон', role: 'Роль',
  is_active: 'Активен', departments: 'Подразделения', access: 'Доступ', name: 'Название', code: 'Код',
  direction: 'Направление', green: 'Граница зелёного', yellow: 'Граница жёлтого', red: 'Красный', enabled: 'Включено',
  neutral: 'Без оценки', colors: 'Цвета', traffic_light: 'Светофор', charts: 'Графики', brand: 'Фирменный',
  primary: 'Основной', muted: 'Приглушённый', comment: 'Комментарий', content: 'Текст', value: 'Значение',
  event_type: 'Событие', event_date: 'Дата', department: 'Подразделение', employment_type: 'Тип занятости',
  reason: 'Причина', metric_key: 'Метрика', year: 'Год', target_value: 'Цель', reference_value: 'Ориентир',
  label: 'Подпись', description: 'Описание', source: 'Источник', mode: 'Режим', created: 'Добавлено',
  updated: 'Обновлено', skipped: 'Пропущено', metrics: 'Метрик', events: 'Событий', notes: 'Заметок',
  partner: 'Партнёр', product: 'Продукт', almi_product: 'Продукт АЛМИ', almi_version: 'Версия', status: 'Статус',
  cert_date: 'Дата сертификата', nda: 'NDA', agreement: 'Соглашение', type: 'Тип', bitrix: 'Битрикс',
  website: 'Сайт', last_modified: 'Изменено', is_shared: 'Общий', widgets: 'Виджеты',
  profile: 'Профиль доступа', overrides: 'Личные настройки', services: 'Службы', extra_units: 'Дополнительные подразделения',
  capabilities: 'Полномочия', auth_source: 'Способ входа', has_password: 'Пароль задан', key: 'Ключ', sort_order: 'Порядок',
  org_scope: 'Область структуры', data_classes: 'Классы данных', drill_depth: 'Глубина детализации',
  can_view_records: 'Исходные записи', can_export: 'Выгрузка', service_levels: 'Уровни служб',
}

/** Подписи ключей внутри раздела (green в colors.traffic_light — цвет, а не граница). */
const NESTED_LABELS = {
  traffic_light: { green: 'Норма', yellow: 'Внимание', red: 'Критично', neutral: 'Без оценки' },
}

const VALUE_LABELS = {
  role: ROLE_LABELS,
  direction: DIRECTION_LABELS,
  event_type: { hired: 'Приём', fired: 'Увольнение' },
  mode: { merge: 'Дополнение', replace: 'Замена' },
  auth_source: { local: 'Пароль системы', ldap: 'Учётная запись домена' },
  org_scope: { company: 'Вся компания', branch: 'Своя ветка структуры', unit: 'Своё подразделение' },
}

const isPlainObject = (v) => v !== null && typeof v === 'object' && !Array.isArray(v)
const HEX_RE = /^#(?:[0-9a-f]{3}|[0-9a-f]{6})$/i

export function isHexColor(value) {
  return typeof value === 'string' && HEX_RE.test(value)
}

/** Значение журнала для человека. */
export function formatAuditValue(value, key = '') {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'boolean') return value ? 'Да' : 'Нет'
  if (typeof value === 'number') return formatNumber(value, { digits: 4 })
  if (Array.isArray(value)) return value.length ? value.map((v) => formatAuditValue(v)).join(', ') : '—'
  if (isPlainObject(value)) {
    const entries = Object.entries(value)
    return entries.length ? entries.map(([k, v]) => `${FIELD_LABELS[k] || k}: ${formatAuditValue(v, k)}`).join('; ') : '—'
  }
  const text = String(value)
  const dict = VALUE_LABELS[key]
  if (dict?.[text]) return dict[text]
  // Уровень доступа, возможно с пометкой «(свои подразделения)»
  const level = text.match(/^(none|viewer|editor|manager)(\s.*)?$/)
  if (level) return `${SERVICE_LEVEL_LABELS[level[1]]}${level[2] || ''}`
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(text)) return text.slice(0, 16).replace('T', ' ')
  return text
}

/** Вложенные объекты → плоские пути (colors.traffic_light.green); массивы остаются значениями. */
function flatten(obj, prefix = [], out = {}) {
  for (const [k, v] of Object.entries(obj || {})) {
    const path = [...prefix, k]
    if (isPlainObject(v) && Object.keys(v).length) flatten(v, path, out)
    else out[path.join('.')] = v
  }
  return out
}

function same(a, b) {
  return JSON.stringify(a ?? null) === JSON.stringify(b ?? null)
}

/**
 * «Было → стало» для раскрытой записи журнала: строки { path, label, before, after, beforeText, afterText,
 * changed, colors }. Если есть оба снимка, показываются только изменённые поля (unchanged — сколько скрыто).
 * labels — дополнительные подписи ключей (например, названия служб для доступа).
 */
export function auditDiff(before, after, { labels = {} } = {}) {
  const b = flatten(before)
  const a = flatten(after)
  const keys = [...new Set([...Object.keys(a), ...Object.keys(b)])]
  const both = !!before && !!after
  const rows = []
  let unchanged = 0
  for (const path of keys) {
    const changed = !same(b[path], a[path])
    if (both && !changed) { unchanged += 1; continue }
    const parts = path.split('.')
    const last = parts.at(-1)
    const label = parts.map((p, i) => labels[p] || NESTED_LABELS[parts[i - 1]]?.[p] || FIELD_LABELS[p] || p).join(' · ')
    const colorsOf = (v) => (Array.isArray(v) && v.length && v.every(isHexColor) ? v : isHexColor(v) ? [v] : null)
    rows.push({
      path, label, changed, known: parts.every((p) => labels[p] || FIELD_LABELS[p]),
      before: b[path], after: a[path],
      beforeText: formatAuditValue(b[path], last), afterText: formatAuditValue(a[path], last),
      beforeColors: colorsOf(b[path]), afterColors: colorsOf(a[path]),
    })
  }
  return { rows, unchanged, mode: both ? 'diff' : after ? 'after' : before ? 'before' : 'none' }
}

/** Номера страниц для пагинации: 1 … 4 5 6 … 20. */
export function pageRange(page, pageCount, around = 1) {
  if (pageCount <= 1) return [1]
  const out = []
  for (let p = 1; p <= pageCount; p += 1) {
    if (p === 1 || p === pageCount || Math.abs(p - page) <= around) out.push(p)
    else if (out.at(-1) !== '…') out.push('…')
  }
  return out
}

// ---------- светофор служб ----------

/** '' → null, '1,5' → 1.5; нечисло → NaN. */
export function parseThreshold(value) {
  if (value === null || value === undefined) return null
  const text = String(value).trim().replace(',', '.').replace(/\s/g, '')
  if (!text) return null
  const n = Number(text)
  return Number.isFinite(n) ? n : NaN
}

/** Та же проверка, что на сервере: '' — правило корректно. */
export function ruleProblem(rule) {
  const g = parseThreshold(rule.green_threshold)
  const y = parseThreshold(rule.yellow_threshold)
  if (Number.isNaN(g) || Number.isNaN(y)) return 'Границы должны быть числами'
  if (rule.enabled && (g === null || y === null)) return 'Для включённого правила задайте обе границы'
  if (g !== null && y !== null) {
    if (rule.direction === 'lower_is_better' && g > y) return '«Меньше — лучше»: граница зелёного должна быть не больше границы жёлтого'
    if (rule.direction === 'higher_is_better' && g < y) return '«Больше — лучше»: граница зелёного должна быть не меньше границы жёлтого'
  }
  return ''
}

/** Тело PUT /traffic-light/{service}/{metric}. */
export function ruleBody(rule) {
  return {
    direction: rule.direction,
    green_threshold: parseThreshold(rule.green_threshold),
    yellow_threshold: parseThreshold(rule.yellow_threshold),
    enabled: !!rule.enabled,
  }
}

export function ruleDirty(rule, saved) {
  return JSON.stringify(ruleBody(rule)) !== JSON.stringify(ruleBody(saved))
}

/** Зоны шкалы слева направо (по возрастанию значения) с подписями границ. */
export function ruleZones(rule, unit = '') {
  const g = parseThreshold(rule.green_threshold)
  const y = parseThreshold(rule.yellow_threshold)
  if (g === null || y === null || Number.isNaN(g) || Number.isNaN(y)) return []
  const f = (v) => formatNumber(v, { unit })
  if (rule.direction === 'lower_is_better') {
    return [
      { light: 'green', text: `≤ ${f(g)}` },
      { light: 'yellow', text: `≤ ${f(y)}` },
      { light: 'red', text: `> ${f(y)}` },
    ]
  }
  return [
    { light: 'red', text: `< ${f(y)}` },
    { light: 'yellow', text: `≥ ${f(y)}` },
    { light: 'green', text: `≥ ${f(g)}` },
  ]
}

/** Группы правил в исходном порядке. */
export function groupRules(rules) {
  const groups = []
  for (const r of rules || []) {
    const name = r.group || 'Прочее'
    let g = groups.find((x) => x.name === name)
    if (!g) groups.push((g = { name, items: [] }))
    g.items.push(r)
  }
  return groups
}

// ---------- палитры ----------

export const LIGHT_SLOTS = [
  { key: 'green', label: 'Норма' },
  { key: 'yellow', label: 'Внимание' },
  { key: 'red', label: 'Критично' },
  { key: 'neutral', label: 'Без оценки' },
]
export const BRAND_SLOTS = [
  { key: 'primary', label: 'Основной' },
  { key: 'muted', label: 'Вторичный' },
]
export const CHART_SLOTS = 7

function hex6(value, fallback) {
  if (!isHexColor(value)) return fallback
  const v = value.toLowerCase()
  return v.length === 4 ? `#${v[1]}${v[1]}${v[2]}${v[2]}${v[3]}${v[3]}` : v
}

/** Полный набор цветов палитры (недостающие — из палитры по умолчанию), все в виде #rrggbb. */
export function normalizePalette(colors = {}) {
  const tl = colors.traffic_light || {}
  const brand = colors.brand || {}
  const charts = Array.isArray(colors.charts) ? colors.charts : []
  return {
    traffic_light: Object.fromEntries(LIGHT_SLOTS.map(({ key }) => [key, hex6(tl[key], FALLBACK.traffic_light[key])])),
    charts: Array.from({ length: CHART_SLOTS }, (_, i) => hex6(charts[i], FALLBACK.charts[i])),
    brand: Object.fromEntries(BRAND_SLOTS.map(({ key }) => [key, hex6(brand[key], FALLBACK.brand[key])])),
  }
}

/** Первый некорректный цвет или ''. */
export function paletteProblem(colors) {
  const all = [...Object.values(colors.traffic_light || {}), ...(colors.charts || []), ...Object.values(colors.brand || {})]
  const bad = all.find((c) => !isHexColor(c))
  return bad === undefined ? '' : `Некорректный цвет: ${bad || 'пусто'}`
}

// ---------- система ----------

export function formatMinutes(minutes) {
  if (minutes === null || minutes === undefined) return '—'
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  if (!h) return `${m} мин`
  return m ? `${h} ч ${m} мин` : `${h} ${plural(h, ['час', 'часа', 'часов'])}`
}
