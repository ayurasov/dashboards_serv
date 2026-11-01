/**
 * Модель доступа 2.0 (ADR-0009): профиль доступа + личные настройки поверх него.
 * Подписи измерений, расчёт действующего доступа так же, как на сервере (services/access.py),
 * редактирование черновика доступа пользователя и профиля, сравнение профилей.
 * Чистые функции — покрыты тестами (access.test.js).
 */
import { plural } from '@/utils/format'

// ---------- справочник ----------

export const LEVEL_RANK = { viewer: 1, editor: 2, manager: 3 }
export const LEVELS = ['viewer', 'editor', 'manager']
export const LEVEL_LABELS = { viewer: 'Просмотр', editor: 'Ввод данных', manager: 'Управление' }
export const SERVICE_LEVEL_LABELS = { none: 'Нет доступа', ...LEVEL_LABELS }
export const LEVEL_HINTS = {
  none: 'Служба скрыта, даже если её даёт профиль',
  viewer: 'Дашборды, отчёты и сводки',
  editor: 'Просмотр, ввод и загрузка данных',
  manager: 'Ввод данных и настройки службы: светофор, цели',
}

export const ORG_SCOPES = ['company', 'branch', 'unit']
export const ORG_SCOPE_LABELS = { company: 'Вся компания', branch: 'Своя ветка структуры', unit: 'Своё подразделение' }
export const ORG_SCOPE_SHORT = { company: 'Вся компания', branch: 'Своя ветка', unit: 'Своё подразделение' }
export const ORG_SCOPE_HINTS = {
  company: 'Данные всех подразделений',
  branch: 'Свои подразделения вместе со всеми вложенными',
  unit: 'Только свои подразделения, без вложенных',
}

export const DATA_CLASSES = ['operational', 'personal', 'financial']
export const DATA_CLASS_LABELS = { operational: 'Операционные', personal: 'Персональные', financial: 'Финансовые' }
export const DATA_CLASS_HINTS = {
  operational: 'Объёмы, сроки, статусы, количество — доступны всегда',
  personal: 'ФИО, должности, причины увольнения в реестрах',
  financial: 'Денежные показатели: выручка, затраты, ФОТ, бюджеты',
}

export const MAX_DRILL_DEPTH = 9

/** Измерения, которые задаются в профиле и переопределяются лично (порядок — как на сервере). */
export const DIMENSIONS = [
  { key: 'org_scope', label: 'Область структуры', hint: 'Данные каких подразделений видны' },
  { key: 'data_classes', label: 'Классы данных', hint: 'Персональные и финансовые — по праву' },
  { key: 'drill_depth', label: 'Глубина детализации', hint: 'Раскрытие отчётов вниз по структуре' },
  { key: 'can_view_records', label: 'Исходные записи', hint: 'Реестры и списки или только дашборды' },
  { key: 'can_export', label: 'Выгрузка', hint: 'Excel, CSV и PDF' },
]
export const DIMENSION_KEYS = DIMENSIONS.map((d) => d.key)
export const DIMENSION_LABELS = Object.fromEntries(DIMENSIONS.map((d) => [d.key, d.label]))

/** Без профиля («Индивидуальная настройка») — как в 0.1.0: ограничивают только уровни служб. */
export const INDIVIDUAL_DEFAULTS = Object.freeze({
  org_scope: 'company', data_classes: [...DATA_CLASSES], drill_depth: null, can_view_records: true, can_export: true,
})
export const INDIVIDUAL_LABEL = 'Индивидуальная настройка'

export const CAPABILITIES = [
  { key: 'org.manage', label: 'Ведёт структуру компании', hint: 'Подразделения, руководители, загрузка и выгрузка структуры' },
  { key: 'users.manage', label: 'Ведёт пользователей и доступ', hint: 'Учётные записи, профили и доступ — кроме администраторов' },
  { key: 'reports.manage', label: 'Ведёт сквозные отчёты', hint: 'Каталог показателей, ввод значений любой службы, заметки о статусе' },
]

/** Значки служб (как в справочнике служб на сервере). */
export const SERVICE_ICONS = {
  hr: 'users', tech: 'headset', project_product: 'handshake', apparat_gd: 'building', it: 'monitor',
  commercial: 'briefcase', marketing: 'megaphone', finance: 'wallet', legal: 'scale',
}

// ---------- подписи значений ----------

const capitalize = (text) => (text ? text[0].toUpperCase() + text.slice(1) : text)
const levelsWord = (n) => plural(n, ['уровень', 'уровня', 'уровней'])

/** Глубина детализации: null — без ограничения. */
export function depthLabel(depth) {
  if (depth === null || depth === undefined) return 'Без ограничения'
  if (depth === 0) return 'Только вершина области'
  return `${depth} ${levelsWord(depth)} вниз`
}

/** Варианты выбора глубины: «без ограничения», затем 0…max. Значение null — без ограничения. */
export function depthOptions(max = MAX_DRILL_DEPTH) {
  return [
    { value: null, label: 'Без ограничения' },
    ...Array.from({ length: max + 1 }, (_, i) => ({ value: i, label: i === 0 ? '0 — только вершина области' : `${i} ${levelsWord(i)} вниз` })),
  ]
}

/** Классы данных в порядке справочника; операционные — всегда. */
export function normalizeClasses(values) {
  const chosen = new Set([...(values || []), 'operational'])
  return DATA_CLASSES.filter((k) => chosen.has(k))
}

export function classesLabel(values) {
  const list = normalizeClasses(values)
  if (list.length === 1) return 'Только операционные'
  return capitalize(list.map((k) => DATA_CLASS_LABELS[k].toLowerCase()).join(', '))
}

/** Значение измерения для человека. */
export function dimensionValueLabel(key, value) {
  switch (key) {
    case 'org_scope': return ORG_SCOPE_LABELS[value] || '—'
    case 'data_classes': return classesLabel(value)
    case 'drill_depth': return depthLabel(value)
    case 'can_view_records': return value ? 'Реестры и списки' : 'Только дашборды и сводки'
    case 'can_export': return value ? 'Разрешена' : 'Запрещена'
    default: return value === null || value === undefined ? '—' : String(value)
  }
}

/** Откуда значение: personal · profile · default · admin. */
export function sourceLabel(source, profileName = '') {
  if (source === 'personal') return 'задано лично'
  if (source === 'profile') return profileName ? `из профиля «${profileName}»` : 'из профиля'
  if (source === 'admin') return 'роль администратора'
  return 'по умолчанию'
}

export function levelLabel(level) {
  return SERVICE_LEVEL_LABELS[level] || 'Нет доступа'
}

export function hasLevel(level, minimum = 'viewer') {
  return !!level && !!LEVEL_RANK[level] && LEVEL_RANK[level] >= LEVEL_RANK[minimum]
}

// ---------- действующий доступ (как services/access.py:compute) ----------

/**
 * Действующий доступ по профилю, личным значениям измерений и личным строкам служб.
 * services — { служба: { level, org_scope } } (level '' — как в профиле, 'none' — запрет)
 * или массив строк { service_key, level, org_scope } из API.
 */
export function computeEffective({ isAdmin = false, profile = null, overrides = {}, services = {}, serviceKeys = null } = {}) {
  if (isAdmin) {
    const keys = serviceKeys || Object.keys(SERVICE_ICONS)
    return {
      is_admin: true, profile_key: null, profile_name: null,
      services: Object.fromEntries(keys.map((k) => [k, 'manager'])), service_scopes: {},
      org_scope: 'company', data_classes: [...DATA_CLASSES], drill_depth: null, can_view_records: true, can_export: true,
      sources: Object.fromEntries(['services', ...DIMENSION_KEYS].map((k) => [k, 'admin'])),
    }
  }
  const values = {}
  const sources = {}
  for (const key of DIMENSION_KEYS) {
    if (overrides && Object.hasOwn(overrides, key)) [values[key], sources[key]] = [overrides[key], 'personal']
    else if (profile) [values[key], sources[key]] = [profile[key], 'profile']
    else [values[key], sources[key]] = [INDIVIDUAL_DEFAULTS[key], 'default']
  }
  const levels = {}
  for (const [key, level] of Object.entries(profile?.service_levels || {})) {
    if (LEVEL_RANK[level]) {
      levels[key] = level
      sources[`service:${key}`] = 'profile'
    }
  }
  const scopes = {}
  for (const row of serviceRowsOf(services)) {
    if (!row.level) continue
    sources[`service:${row.service_key}`] = 'personal'
    if (row.level === 'none') {
      delete levels[row.service_key]
      continue
    }
    levels[row.service_key] = row.level
    if (row.org_scope) scopes[row.service_key] = row.org_scope
  }
  const order = serviceKeys || Object.keys(SERVICE_ICONS)
  const sorted = Object.keys(levels).sort((a, b) => indexOr(order, a) - indexOr(order, b))
  return {
    is_admin: false, profile_key: profile?.key ?? null, profile_name: profile?.name ?? null,
    services: Object.fromEntries(sorted.map((k) => [k, levels[k]])), service_scopes: scopes,
    org_scope: values.org_scope, data_classes: normalizeClasses(values.data_classes), drill_depth: values.drill_depth ?? null,
    can_view_records: !!values.can_view_records, can_export: !!values.can_export, sources,
  }
}

const indexOr = (list, key) => (list.includes(key) ? list.indexOf(key) : list.length)

function serviceRowsOf(services) {
  if (Array.isArray(services)) return services
  return Object.entries(services || {}).map(([service_key, row]) => ({ service_key, level: row?.level || '', org_scope: row?.org_scope || null }))
}

/** Область службы: своя у службы или общая. */
export function scopeFor(effective, serviceKey) {
  if (!effective) return 'company'
  return effective.service_scopes?.[serviceKey] || effective.org_scope || 'company'
}

/**
 * Действующий доступ пользователя для интерфейса: из effective_access (/api/auth/me), а у сервера
 * без него (0.1.0) — из строк доступа к службам и роли.
 */
export function userAccess(user) {
  if (!user) return null
  if (user.effective_access && Object.keys(user.effective_access).length) return user.effective_access
  return computeEffective({ isAdmin: user.role === 'admin', services: user.access || [] })
}

// ---------- область структуры ----------

/**
 * Подразделения действующей области (как scope_units на сервере): вершины — основное подразделение,
 * руководимые и дополнительные; «своя ветка» — вместе со всеми вложенными. null — вся компания.
 * departments — плоский список /api/departments (id, parent_id, path, heads[{user_id}]).
 */
export function scopeUnits(departments, { userId = null, homeId = null, extraIds = [], scope = 'company' } = {}) {
  if (scope === 'company') return null
  const byId = new Map((departments || []).map((d) => [d.id, d]))
  const roots = new Set()
  if (homeId && byId.has(homeId)) roots.add(homeId)
  for (const id of extraIds || []) if (byId.has(id)) roots.add(id)
  if (userId) for (const d of departments || []) if ((d.heads || []).some((h) => h.user_id === userId)) roots.add(d.id)
  let ids = roots
  if (scope === 'branch') {
    const children = new Map()
    for (const d of departments || []) {
      if (!children.has(d.parent_id)) children.set(d.parent_id, [])
      children.get(d.parent_id).push(d.id)
    }
    ids = new Set()
    const queue = [...roots]
    while (queue.length) {
      const id = queue.shift()
      if (ids.has(id)) continue
      ids.add(id)
      queue.push(...(children.get(id) || []))
    }
  }
  return [...ids].map((id) => byId.get(id)).map((d) => ({ id: d.id, name: d.name, path: d.path || d.name }))
    .sort((a, b) => a.path.localeCompare(b.path, 'ru'))
}

/** Руководимые пользователем подразделения (по руководителям в справочнике). */
export function headedUnits(departments, userId) {
  if (!userId) return []
  return (departments || []).filter((d) => (d.heads || []).some((h) => h.user_id === userId))
}

/**
 * Предупреждение: область уже компании, а вершин нет — данные подразделений пользователю не видны.
 * scopes — общая область и области служб.
 */
export function scopeWarning({ scopes = [], homeId = null, extraIds = [], headedCount = 0 } = {}) {
  const narrow = scopes.filter((s) => s && s !== 'company')
  if (!narrow.length || homeId || (extraIds || []).length || headedCount) return ''
  return 'Область ограничена своими подразделениями, но у пользователя нет ни основного, ни дополнительных подразделений — данные подразделений ему не видны. Укажите подразделение на вкладке «Профиль» или добавьте дополнительные.'
}

// ---------- черновик доступа пользователя ----------

/** Черновик из ответа GET /users/{id}/access. */
export function policyDraft(policy) {
  const services = {}
  for (const row of policy?.services || []) services[row.service_key] = { level: row.level || '', org_scope: row.org_scope || '' }
  return {
    profileId: policy?.profile?.id ?? null,
    overrides: clone(policy?.overrides || {}),
    services,
    extraUnitIds: (policy?.extra_units || []).map((u) => u.id),
  }
}

const clone = (value) => JSON.parse(JSON.stringify(value ?? null))

/** Строки служб для PUT: только заданные лично, в порядке справочника. */
export function serviceRowsBody(services, order = Object.keys(SERVICE_ICONS)) {
  return Object.entries(services || {})
    .filter(([, row]) => row?.level)
    .sort(([a], [b]) => indexOr(order, a) - indexOr(order, b))
    .map(([service_key, row]) => ({ service_key, level: row.level, org_scope: row.level !== 'none' && row.org_scope ? row.org_scope : null }))
}

const sameJson = (a, b) => JSON.stringify(a) === JSON.stringify(b)
const sortedIds = (ids) => [...(ids || [])].sort((a, b) => a - b)

function normalizedOverrides(overrides) {
  const out = {}
  for (const key of DIMENSION_KEYS) {
    if (!overrides || !Object.hasOwn(overrides, key)) continue
    out[key] = key === 'data_classes' ? normalizeClasses(overrides[key]) : overrides[key]
  }
  return out
}

/** Тело PUT /users/{id}/access — только изменённые части; {} — изменений нет. */
export function policyBody(draft, saved) {
  const base = saved || policyDraft(null)
  const body = {}
  if ((draft.profileId ?? null) !== (base.profileId ?? null)) body.profile_id = draft.profileId ?? null
  const overrides = normalizedOverrides(draft.overrides)
  if (!sameJson(overrides, normalizedOverrides(base.overrides))) body.overrides = overrides
  const rows = serviceRowsBody(draft.services)
  if (!sameJson(rows, serviceRowsBody(base.services))) body.services = rows
  if (!sameJson(sortedIds(draft.extraUnitIds), sortedIds(base.extraUnitIds))) body.extra_unit_ids = sortedIds(draft.extraUnitIds)
  return body
}

export function policyDirty(draft, saved) {
  return Object.keys(policyBody(draft, saved)).length > 0
}

/** Значение измерения «как в профиле»: из профиля или по умолчанию. */
export function inheritedValue(key, profile) {
  return clone(profile ? profile[key] : INDIVIDUAL_DEFAULTS[key])
}

/** Строка измерения в карточке пользователя: лично ли задано, действующее и унаследованное значения. */
export function dimensionView(key, overrides, profile) {
  const personal = !!overrides && Object.hasOwn(overrides, key)
  const inherited = inheritedValue(key, profile)
  const value = personal ? overrides[key] : inherited
  return {
    key,
    label: DIMENSION_LABELS[key],
    personal,
    value,
    inherited,
    inheritedSource: profile ? 'profile' : 'default',
    source: personal ? 'personal' : profile ? 'profile' : 'default',
    valueText: dimensionValueLabel(key, value),
    inheritedText: dimensionValueLabel(key, inherited),
    differs: personal && !sameJson(normalizeValue(key, value), normalizeValue(key, inherited)),
  }
}

const normalizeValue = (key, value) => (key === 'data_classes' ? normalizeClasses(value) : value ?? null)

/** «Задать лично»: личное значение начинается с унаследованного — действующий доступ не меняется. */
export function startOverride(overrides, key, profile) {
  return { ...(overrides || {}), [key]: inheritedValue(key, profile) }
}

export function setOverride(overrides, key, value) {
  return { ...(overrides || {}), [key]: key === 'data_classes' ? normalizeClasses(value) : value }
}

/** «Вернуть как в профиле». */
export function clearOverride(overrides, key) {
  const next = { ...(overrides || {}) }
  delete next[key]
  return next
}

/** Переключить класс данных (операционные не снимаются). */
export function toggleClass(classes, key) {
  if (key === 'operational') return normalizeClasses(classes)
  const set = new Set(normalizeClasses(classes))
  set.has(key) ? set.delete(key) : set.add(key)
  return normalizeClasses([...set])
}

/** Строка службы: уровень профиля, личный уровень ('' — как в профиле), действующий уровень и источник. */
export function serviceView(service, draft, profile) {
  const row = draft?.services?.[service.key] || { level: '', org_scope: '' }
  const profileLevel = profile?.service_levels?.[service.key] || null
  const personal = !!row.level
  const level = personal ? (row.level === 'none' ? null : row.level) : profileLevel
  return {
    key: service.key,
    title: service.title,
    short_title: service.short_title || service.title,
    icon: SERVICE_ICONS[service.key] || 'grid',
    has_dashboard: !!service.has_dashboard,
    profileLevel,
    personalLevel: row.level || '',
    scope: personal && row.level !== 'none' ? row.org_scope || '' : '',
    level,
    personal,
    source: personal ? 'personal' : profileLevel ? 'profile' : 'none',
  }
}

/** Личный уровень службы: '' — как в профиле (личная область службы тогда тоже снимается). */
export function setServiceLevel(services, key, level) {
  const next = { ...(services || {}) }
  if (!level) delete next[key]
  else next[key] = { level, org_scope: level === 'none' ? '' : next[key]?.org_scope || '' }
  return next
}

/**
 * Своя область службы. Задаётся строкой службы — если уровень был «как в профиле», он фиксируется лично
 * (иначе области не к чему относиться). Без доступа к службе область не задаётся.
 */
export function setServiceScope(services, key, scope, profile) {
  const current = services?.[key]?.level || ''
  const level = current || profile?.service_levels?.[key] || ''
  if (!level || level === 'none') return { ...(services || {}) }
  return { ...(services || {}), [key]: { level, org_scope: scope || '' } }
}

/** «Просмотр всех дашбордов»: службам с дашбордом без доступа — просмотр (выданный уровень сохраняется). */
export function grantViewAll(services, serviceList, profile) {
  let next = { ...(services || {}) }
  for (const s of serviceList || []) {
    if (!s.has_dashboard) continue
    const view = serviceView(s, { services: next }, profile)
    if (!view.level) next = setServiceLevel(next, s.key, 'viewer')
  }
  return next
}

// ---------- сводка действующего доступа ----------

/**
 * Строки «Действующего доступа» с источниками: службы, затем измерения.
 * serviceList — справочник служб (порядок и названия).
 */
export function effectiveRows(effective, serviceList = [], { profileName = '' } = {}) {
  if (!effective) return { services: [], dimensions: [] }
  const name = profileName || effective.profile_name || ''
  const titles = Object.fromEntries((serviceList || []).map((s) => [s.key, s]))
  const services = Object.entries(effective.services || {}).map(([key, level]) => ({
    key,
    title: titles[key]?.title || key,
    short_title: titles[key]?.short_title || titles[key]?.title || key,
    level,
    levelText: LEVEL_LABELS[level] || level,
    scope: effective.service_scopes?.[key] || '',
    scopeText: effective.service_scopes?.[key] ? ORG_SCOPE_SHORT[effective.service_scopes[key]] : '',
    source: effective.is_admin ? 'admin' : effective.sources?.[`service:${key}`] || 'profile',
    sourceText: sourceLabel(effective.is_admin ? 'admin' : effective.sources?.[`service:${key}`] || 'profile', name),
  }))
  const dimensions = DIMENSIONS.map((d) => {
    const source = effective.sources?.[d.key] || (effective.is_admin ? 'admin' : 'default')
    return { key: d.key, label: d.label, value: effective[d.key], valueText: dimensionValueLabel(d.key, effective[d.key]), source, sourceText: sourceLabel(source, name) }
  })
  return { services, dimensions }
}

/** Службы, которые явно запрещены лично («Нет доступа» поверх профиля). */
export function deniedServices(effective, serviceList = []) {
  const titles = Object.fromEntries((serviceList || []).map((s) => [s.key, s.title]))
  return Object.entries(effective?.sources || {})
    .filter(([key, source]) => key.startsWith('service:') && source === 'personal' && !effective.services?.[key.slice(8)])
    .map(([key]) => ({ key: key.slice(8), title: titles[key.slice(8)] || key.slice(8) }))
}

/** Доступ простыми словами — для «Мой доступ» в профиле пользователя. */
export function plainAccess(effective, serviceList = []) {
  if (!effective) return { admin: false, profile: '', services: [], lines: [] }
  const titles = Object.fromEntries((serviceList || []).map((s) => [s.key, s]))
  const services = Object.entries(effective.services || {})
    .map(([key, level]) => ({
      key, title: titles[key]?.title || key, level, levelText: LEVEL_LABELS[level] || level, hint: LEVEL_HINTS[level] || '',
      scopeText: effective.service_scopes?.[key] ? `область — ${ORG_SCOPE_SHORT[effective.service_scopes[key]].toLowerCase()}` : '',
    }))
  const classes = normalizeClasses(effective.data_classes)
  // Область «своё подразделение» не раскрывается вниз в отчётах, какой бы ни была глубина в профиле
  const depth = effective.org_scope === 'unit' ? 0 : effective.drill_depth
  const lines = [
    { key: 'org_scope', label: 'Область', ok: true, value: ORG_SCOPE_LABELS[effective.org_scope] || '—',
      text: { company: 'Вы видите данные всех подразделений компании.',
        branch: 'Вы видите данные своих подразделений и всех вложенных в них.',
        unit: 'Вы видите данные только своих подразделений, без вложенных.' }[effective.org_scope] || '' },
    { key: 'data_classes', label: 'Классы данных', ok: true, value: classesLabel(classes),
      text: [
        'Операционные показатели доступны всегда.',
        classes.includes('personal') ? 'Персональные данные (ФИО, должности, причины увольнения) — доступны.' : 'Персональные данные (ФИО, должности, причины увольнения) скрыты.',
        classes.includes('financial') ? 'Финансовые показатели — доступны.' : 'Денежные показатели скрыты.',
      ].join(' ') },
    { key: 'drill_depth', label: 'Глубина детализации', ok: depth !== 0, value: depthLabel(depth),
      text: depth === null || depth === undefined ? 'Отчёты раскрываются на любую глубину вашей области.'
        : depth === 0 ? 'Отчёты показывают итог по вершине вашей области, без раскрытия по подразделениям.'
          : `Отчёты раскрываются на ${depth} ${levelsWord(depth)} структуры ниже вершины вашей области.` },
    { key: 'can_view_records', label: 'Исходные записи', ok: !!effective.can_view_records, value: effective.can_view_records ? 'Доступны' : 'Недоступны',
      text: effective.can_view_records ? 'Реестры и списки служб открыты вам целиком.' : 'Вам доступны дашборды и сводки; реестры и списки скрыты.' },
    { key: 'can_export', label: 'Выгрузка', ok: !!effective.can_export, value: effective.can_export ? 'Разрешена' : 'Недоступна',
      text: effective.can_export ? 'Можно выгружать отчёты в Excel, CSV и PDF.' : 'Кнопки выгрузки в Excel, CSV и PDF скрыты.' },
  ]
  return { admin: !!effective.is_admin, profile: effective.profile_name || '', services, lines }
}

// ---------- профили доступа ----------

export const PROFILE_KEY_RE = /^[a-z][a-z0-9_-]{1,39}$/

/** Ключ профиля из названия: транслитерация, латиница в нижнем регистре. */
export function suggestProfileKey(name) {
  const map = { а: 'a', б: 'b', в: 'v', г: 'g', д: 'd', е: 'e', ё: 'e', ж: 'zh', з: 'z', и: 'i', й: 'y', к: 'k', л: 'l', м: 'm', н: 'n', о: 'o', п: 'p', р: 'r', с: 's', т: 't', у: 'u', ф: 'f', х: 'h', ц: 'ts', ч: 'ch', ш: 'sh', щ: 'sch', ъ: '', ы: 'y', ь: '', э: 'e', ю: 'yu', я: 'ya' }
  const latin = String(name || '').toLowerCase().split('').map((ch) => map[ch] ?? ch).join('')
  const key = latin.replace(/[^a-z0-9]+/g, '-').replace(/^[^a-z]+/, '').replace(/-+$/, '').slice(0, 40).replace(/-+$/, '')
  return key.length >= 2 ? key : ''
}

/** Форма профиля. */
export function accessProfileForm(profile = null) {
  return {
    key: profile?.key || '',
    name: profile?.name || '',
    description: profile?.description || '',
    sort_order: profile?.sort_order ?? 100,
    org_scope: profile?.org_scope || 'unit',
    data_classes: normalizeClasses(profile?.data_classes || ['operational']),
    drill_depth: profile ? profile.drill_depth ?? null : null,
    can_view_records: profile ? !!profile.can_view_records : true,
    can_export: profile ? !!profile.can_export : true,
    service_levels: { ...(profile?.service_levels || {}) },
  }
}

export function accessProfileErrors(form, { isNew = false } = {}) {
  const errors = {}
  if (isNew && !PROFILE_KEY_RE.test(form.key || '')) errors.key = 'Латинские строчные буквы, цифры, «_» и «-»; начинается с буквы, 2–40 символов'
  if (!(form.name || '').trim()) errors.name = 'Укажите название'
  return errors
}

const PROFILE_FIELDS = ['name', 'description', 'sort_order', 'org_scope', 'data_classes', 'drill_depth', 'can_view_records', 'can_export', 'service_levels']

function profileValues(form) {
  const levels = Object.fromEntries(Object.entries(form.service_levels || {}).filter(([, v]) => LEVEL_RANK[v]))
  return {
    name: (form.name || '').trim().replace(/\s+/g, ' '),
    description: (form.description || '').trim(),
    sort_order: Number(form.sort_order) || 0,
    org_scope: form.org_scope,
    data_classes: normalizeClasses(form.data_classes),
    drill_depth: form.drill_depth ?? null,
    can_view_records: !!form.can_view_records,
    can_export: !!form.can_export,
    service_levels: levels,
  }
}

/** Тело POST (все поля и ключ) или PATCH (только изменённые поля) профиля. */
export function accessProfileBody(form, saved = null) {
  const values = profileValues(form)
  if (!saved) return { key: (form.key || '').trim(), ...values }
  const base = profileValues(accessProfileForm(saved))
  return Object.fromEntries(PROFILE_FIELDS.filter((k) => !sameJson(values[k], base[k])).map((k) => [k, values[k]]))
}

/** Короткое значение для таблицы сравнения профилей. */
function compareCell(key, value) {
  if (key === 'can_view_records' || key === 'can_export') return { text: value ? 'Да' : 'Нет', tone: value ? 'on' : 'off' }
  if (key === 'org_scope') return { text: ORG_SCOPE_SHORT[value] || '—', tone: value === 'company' ? 'on' : 'mid' }
  if (key === 'drill_depth') return { text: value === null || value === undefined ? 'Без ограничения' : String(value), tone: value === 0 ? 'off' : value === null || value === undefined ? 'on' : 'mid' }
  return { text: String(value ?? '—'), tone: '' }
}

/**
 * Сравнение профилей «кто что видит»: столбцы — профили и «Индивидуальная настройка» (по умолчанию),
 * строки — область, классы данных, глубина, записи, выгрузка и уровни служб с дашбордом.
 */
export function profileComparison(profiles, serviceList = [], { includeIndividual = true } = {}) {
  const columns = (profiles || []).map((p) => ({ key: p.key, id: p.id, name: p.name, is_system: !!p.is_system, users_count: p.users_count ?? 0, values: p }))
  if (includeIndividual) {
    columns.push({ key: '', id: null, name: INDIVIDUAL_LABEL, is_system: false, individual: true, users_count: null, values: { ...INDIVIDUAL_DEFAULTS, service_levels: {} } })
  }
  const rows = []
  rows.push({ key: 'org_scope', group: 'dimensions', label: DIMENSION_LABELS.org_scope, cells: columns.map((c) => compareCell('org_scope', c.values.org_scope)) })
  for (const cls of DATA_CLASSES) {
    rows.push({
      key: `class:${cls}`, group: 'dimensions', label: `${DATA_CLASS_LABELS[cls]} данные`, hint: DATA_CLASS_HINTS[cls],
      cells: columns.map((c) => {
        const on = normalizeClasses(c.values.data_classes).includes(cls)
        return { text: on ? 'Да' : 'Нет', tone: on ? 'on' : 'off' }
      }),
    })
  }
  for (const key of ['drill_depth', 'can_view_records', 'can_export']) {
    rows.push({ key, group: 'dimensions', label: DIMENSION_LABELS[key], cells: columns.map((c) => compareCell(key, c.values[key])) })
  }
  for (const s of (serviceList || []).filter((x) => x.has_dashboard)) {
    rows.push({
      key: `service:${s.key}`, group: 'services', label: s.title,
      cells: columns.map((c) => {
        const level = c.values.service_levels?.[s.key]
        return level ? { text: LEVEL_LABELS[level], tone: 'on' } : { text: c.individual ? 'Лично' : '—', tone: 'off' }
      }),
    })
  }
  return { columns, rows }
}

/** Краткие факты профиля для карточки. */
export function profileFacts(profile, serviceList = []) {
  if (!profile) return []
  const titles = Object.fromEntries((serviceList || []).map((s) => [s.key, s.short_title || s.title]))
  const levels = Object.entries(profile.service_levels || {}).filter(([, v]) => LEVEL_RANK[v])
  const sameLevel = levels.length && levels.every(([, v]) => v === levels[0][1])
  const dashboards = (serviceList || []).filter((s) => s.has_dashboard).map((s) => s.key)
  const all = dashboards.length && dashboards.every((k) => levels.some(([key]) => key === k))
  let servicesText = 'Выдаются лично'
  if (levels.length && all && sameLevel) servicesText = `${LEVEL_LABELS[levels[0][1]]} всех дашбордов`
  else if (levels.length) servicesText = levels.map(([k, v]) => `${titles[k] || k} — ${LEVEL_LABELS[v].toLowerCase()}`).join(', ')
  return [
    { key: 'org_scope', label: 'Область', text: ORG_SCOPE_LABELS[profile.org_scope] || '—' },
    { key: 'data_classes', label: 'Данные', text: classesLabel(profile.data_classes) },
    { key: 'drill_depth', label: 'Глубина', text: depthLabel(profile.drill_depth) },
    { key: 'can_view_records', label: 'Записи', text: profile.can_view_records ? 'Реестры и списки' : 'Только дашборды', off: !profile.can_view_records },
    { key: 'can_export', label: 'Выгрузка', text: profile.can_export ? 'Разрешена' : 'Запрещена', off: !profile.can_export },
    { key: 'services', label: 'Службы', text: servicesText, off: !levels.length },
  ]
}
