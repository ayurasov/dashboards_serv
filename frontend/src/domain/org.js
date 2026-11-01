/**
 * Структура компании (ADR-0007): представления оргсхемы, поиск, раскрытие уровней, таблица
 * и выгрузка, дерево подразделений в администрировании, планы загрузки и решения по коллизиям.
 * Вход — ответы /api/org/tree, /api/departments и планов загрузки (поля как в API).
 * Чистые функции — покрыты тестами (org.test.js).
 */
import { plural } from '@/utils/format'

// ---------------------------------------------------------------- виды и подписи

export const ORG_VIEWS = [
  { value: 'chart', label: 'Оргсхема', icon: 'org', hint: 'Подразделения карточками с линиями подчинения' },
  { value: 'people', label: 'Люди', icon: 'users', hint: 'Кто кому подчиняется: руководители и их команды' },
  { value: 'tree', label: 'Дерево', icon: 'list', hint: 'Список подразделений: руководители, затем сотрудники' },
  { value: 'table', label: 'Таблица', icon: 'table', hint: 'Подразделения с численностью: сортировка и выгрузка' },
]
export const VIEW_KEYS = ORG_VIEWS.map((v) => v.value)

/** Вид: из адреса, затем сохранённый пользователем, затем из настроек структуры. */
export function resolveView(...candidates) {
  return candidates.find((v) => VIEW_KEYS.includes(v)) || 'chart'
}

export const MANAGER_SOURCE_LABELS = {
  explicit: 'назначен явно',
  structure: 'по структуре',
  top: 'первое лицо',
  none: 'не определён',
}

export const UNIT_FORMS = ['подразделение', 'подразделения', 'подразделений']
export const PEOPLE_FORMS = ['сотрудник', 'сотрудника', 'сотрудников']
export const LEVEL_FORMS = ['уровень', 'уровня', 'уровней']

/** «5 сотрудников» */
export function countText(n, forms) {
  const value = Number(n) || 0
  return `${value.toLocaleString('ru-RU')} ${plural(value, forms)}`
}

export const ZOOM = { min: 0.3, max: 1.6, step: 0.1 }

export function clampZoom(value) {
  const n = Number(value)
  if (!Number.isFinite(n)) return 1
  return Math.round(Math.min(ZOOM.max, Math.max(ZOOM.min, n)) * 100) / 100
}

// ---------------------------------------------------------------- типы уровней

const DEFAULT_KIND_COLOR = '#64748b'

/** Тип уровня по ключу; неизвестный — ключ вместо названия и нейтральный цвет. */
export function kindInfo(kinds, value) {
  const kind = (kinds || []).find((k) => k.value === value)
  return { value, label: kind?.label || value || 'Подразделение', color: kind?.color || DEFAULT_KIND_COLOR }
}

const TRANSLIT = {
  а: 'a', б: 'b', в: 'v', г: 'g', д: 'd', е: 'e', ё: 'e', ж: 'zh', з: 'z', и: 'i', й: 'y', к: 'k', л: 'l', м: 'm',
  н: 'n', о: 'o', п: 'p', р: 'r', с: 's', т: 't', у: 'u', ф: 'f', х: 'h', ц: 'c', ч: 'ch', ш: 'sh', щ: 'sch',
  ъ: '', ы: 'y', ь: '', э: 'e', ю: 'yu', я: 'ya',
}

/** Ключ нового типа уровня из названия: «Сектор продаж» → sektor-prodazh (латиница, как требует сервер). */
export function kindValueFromLabel(label, taken = []) {
  const base = String(label || '').toLocaleLowerCase('ru').split('').map((ch) => TRANSLIT[ch] ?? ch).join('')
    .replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').replace(/^[^a-z]+/, '').slice(0, 28) || 'kind'
  let value = base
  let n = 2
  while (taken.includes(value)) value = `${base}-${n++}`
  return value
}

// ---------------------------------------------------------------- аватар

/** Инициалы по первым буквам слов (скобки и знаки пропускаются). */
export function initials(name) {
  return String(name || '').split(/\s+/).map((w) => w.match(/[\p{L}\p{N}]/u)?.[0]).filter(Boolean)
    .slice(0, 2).map((ch) => ch.toUpperCase()).join('') || '?'
}

/** Номер оттенка аватара (1–7, цвета серий палитры) — постоянный для человека. */
export function avatarTone(seed) {
  let h = 0
  for (const ch of String(seed || '')) h = (h * 31 + ch.charCodeAt(0)) >>> 0
  return (h % 7) + 1
}

// ---------------------------------------------------------------- леса для схем

const byName = (a, b) => String(a).localeCompare(String(b), 'ru')
const unitOrder = (a, b) => (a.sort_order || 0) - (b.sort_order || 0) || byName(a.name, b.name)

/** Лес подразделений: [{ id, item, depth, children }]; потерявшие родителя — корни. */
export function unitForest(units = []) {
  const ids = new Set(units.map((u) => u.id))
  const children = new Map()
  for (const unit of units) {
    const parent = unit.parent_id != null && ids.has(unit.parent_id) ? unit.parent_id : null
    if (!children.has(parent)) children.set(parent, [])
    children.get(parent).push(unit)
  }
  const seen = new Set()
  const build = (unit, depth) => {
    seen.add(unit.id)
    const kids = (children.get(unit.id) || []).filter((k) => !seen.has(k.id)).sort(unitOrder)
    return { id: unit.id, item: unit, depth, children: kids.map((k) => build(k, depth + 1)) }
  }
  const roots = (children.get(null) || []).sort(unitOrder).map((u) => build(u, 0))
  // Цикл в данных не прячет подразделения: оставшиеся — в корень
  for (const unit of [...units].sort(unitOrder)) if (!seen.has(unit.id)) roots.push(build(unit, 0))
  return roots
}

export const LOOSE_ID = 'loose'

/**
 * Лес «кто кому подчиняется» по непосредственному руководителю (direct_manager_id). Отключённые
 * не показываются; сначала руководители с большей командой. Сотрудники без руководителя и без
 * подчинённых собираются в группу «Вне подчинения» (узел { id: 'loose', group: true }) — иначе
 * они растягивают верхний ряд схемы.
 */
export function peopleForest(people = []) {
  const active = people.filter((p) => p.is_active !== false)
  const ids = new Set(active.map((p) => p.id))
  const children = new Map()
  for (const person of active) {
    const manager = person.direct_manager_id
    const parent = manager != null && manager !== person.id && ids.has(manager) ? manager : null
    if (!children.has(parent)) children.set(parent, [])
    children.get(parent).push(person)
  }
  const order = (a, b) => (b.branch_count || 0) - (a.branch_count || 0) || byName(a.full_name, b.full_name)
  const seen = new Set()
  const build = (person, depth) => {
    seen.add(person.id)
    const kids = (children.get(person.id) || []).filter((k) => !seen.has(k.id)).sort(order)
    return { id: person.id, item: person, depth, children: kids.map((k) => build(k, depth + 1)) }
  }
  const roots = (children.get(null) || []).sort(order).map((p) => build(p, 0))
  // Цикл подчинения (ошибка данных) не прячет людей
  for (const person of active) if (!seen.has(person.id)) roots.push(build(person, 0))
  const leaders = roots.filter((n) => n.children.length)
  const loose = roots.filter((n) => !n.children.length)
  if (!leaders.length || !loose.length) return roots
  const group = { id: LOOSE_ID, group: true, depth: 0, item: { count: loose.length }, children: [] }
  group.children = loose.map((n) => ({ ...n, depth: 1 }))
  return [...leaders, group]
}

/** Индекс узлов леса: id → { node, parentId }. */
export function indexForest(forest) {
  const index = new Map()
  const walk = (nodes, parentId) => {
    for (const node of nodes) {
      index.set(node.id, { node, parentId })
      walk(node.children, node.id)
    }
  }
  walk(forest, null)
  return index
}

/** Предки узла от корня (без самого узла). */
export function ancestorsOf(index, id) {
  const path = []
  const seen = new Set()
  let current = index.get(id)?.parentId ?? null
  while (current !== null && current !== undefined && !seen.has(current)) {
    seen.add(current)
    path.unshift(current)
    current = index.get(current)?.parentId ?? null
  }
  return path
}

/** Путь от корня до узла включительно (пусто, если узла нет). */
export function pathTo(index, id) {
  if (id === null || id === undefined || !index.has(id)) return new Set()
  return new Set([...ancestorsOf(index, id), id])
}

/**
 * Раскрытые узлы, чтобы было видно levels уровней (null — все). leaves — раскрывать и узлы
 * без дочерних (в «Дереве» раскрытое подразделение показывает сотрудников).
 */
export function expandedToLevel(forest, levels, { leaves = false } = {}) {
  const result = new Set()
  const walk = (nodes) => {
    for (const node of nodes) {
      if ((node.children.length || leaves) && (levels === null || node.depth + 1 < levels)) result.add(node.id)
      walk(node.children)
    }
  }
  walk(forest)
  return result
}

/** Раскрыть предков узла (и сам узел — with self), не трогая остальное. */
export function revealIn(expanded, index, id, { self = false } = {}) {
  const next = new Set(expanded)
  for (const ancestor of ancestorsOf(index, id)) next.add(ancestor)
  if (self && index.get(id)?.node.children.length) next.add(id)
  return next
}

export function toggleIn(set, id) {
  const next = new Set(set)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  return next
}

/** Глубина леса (1 — только корни). */
export function forestDepth(forest) {
  let depth = 0
  const walk = (nodes) => { for (const node of nodes) { depth = Math.max(depth, node.depth + 1); walk(node.children) } }
  walk(forest)
  return depth
}

/** Узлов в лесу (без групп). */
export function forestSize(forest) {
  let size = 0
  const walk = (nodes) => { for (const node of nodes) { if (!node.group) size += 1; walk(node.children) } }
  walk(forest)
  return size
}

/** Сколько карточек будет видно при данном раскрытии. */
export function visibleCount(forest, expanded) {
  let count = 0
  const walk = (nodes) => {
    for (const node of nodes) {
      count += 1
      if (expanded.has(node.id)) walk(node.children)
    }
  }
  walk(forest)
  return count
}

/** Варианты «Уровней»: 1…глубина (не больше 12) и «все». */
export function levelOptions(depth) {
  const n = Math.max(1, Math.min(12, Number(depth) || 1))
  return [...Array.from({ length: n }, (_, i) => ({ value: i + 1, label: String(i + 1) })), { value: 'all', label: 'все' }]
}

/** Дочерние без своих дочерних — столбиком под родителем, чтобы схема не росла в ширину. */
export function isStackable(node) {
  return node.children.length > 1 && node.children.every((child) => !child.children.length)
}

// ---------------------------------------------------------------- подразделения и люди

/** Имена подразделений от корня до id. */
export function unitPathNames(unitsById, id) {
  const names = []
  const seen = new Set()
  let current = unitsById.get(id)
  while (current && !seen.has(current.id)) {
    seen.add(current.id)
    names.unshift(current.name)
    current = current.parent_id != null ? unitsById.get(current.parent_id) : null
  }
  return names
}

export const homeOf = (person) => person?.home_unit_id ?? person?.department_id ?? null

/** Сотрудники уровня без его руководителей (это и есть «штат уровня»), по имени. */
export function membersOf(unit, people) {
  if (!unit) return []
  const heads = new Set(unit.head_ids || [])
  return people
    .filter((p) => p.is_active !== false && homeOf(p) === unit.id && !heads.has(p.id))
    .sort((a, b) => byName(a.full_name, b.full_name))
}

/**
 * Руководители уровня: основной первым, затем по имени. visiting — числится в другом
 * подразделении (руководит здесь, а штатно — там).
 */
export function headsOf(unit, peopleById) {
  if (!unit) return []
  return (unit.head_ids || [])
    .map((id) => peopleById.get(id))
    .filter((p) => p && p.is_active !== false)
    .sort((a, b) => (b.id === unit.primary_head_id) - (a.id === unit.primary_head_id) || byName(a.full_name, b.full_name))
    .map((person) => ({ person, primary: person.id === unit.primary_head_id, visiting: homeOf(person) !== unit.id }))
}

/** Активные сотрудники без подразделения. */
export function unassignedPeople(people) {
  return people.filter((p) => p.is_active !== false && homeOf(p) == null)
    .sort((a, b) => byName(a.full_name, b.full_name))
}

/** Поиск в списке людей по имени и должности (панель подразделения, выбор руководителей). */
export function filterPeople(people, query) {
  const needle = normalize(query)
  if (!needle) return people
  return people.filter((p) => [p.full_name, p.position, p.email].some((v) => normalize(v).includes(needle)))
}

/**
 * Строки вида «Дерево»: подразделение, под раскрытым — руководители, сотрудники уровня,
 * затем вложенные подразделения. Последняя группа — «Вне структуры» (id 'unassigned').
 * Строка: { key, type: 'unit' | 'person' | 'group', id, depth, … }.
 */
export function treeRows(forest, expanded, people, peopleById) {
  const rows = []
  const membersByUnit = new Map()
  for (const person of people) {
    const home = homeOf(person)
    if (person.is_active === false || home == null) continue
    if (!membersByUnit.has(home)) membersByUnit.set(home, [])
    membersByUnit.get(home).push(person)
  }
  const walk = (nodes) => {
    for (const node of nodes) {
      const unit = node.item
      const heads = headsOf(unit, peopleById)
      const headIds = new Set(heads.map((h) => h.person.id))
      const members = (membersByUnit.get(unit.id) || []).filter((p) => !headIds.has(p.id))
        .sort((a, b) => byName(a.full_name, b.full_name))
      const open = expanded.has(unit.id)
      rows.push({
        key: `u${unit.id}`, type: 'unit', id: unit.id, depth: node.depth, unit, open,
        expandable: !!(node.children.length || heads.length || members.length),
      })
      if (!open) continue
      for (const head of heads) {
        rows.push({ key: `h${unit.id}-${head.person.id}`, type: 'person', id: head.person.id, depth: node.depth + 1,
          person: head.person, unitId: unit.id, role: head.visiting ? 'visiting' : 'head', primary: head.primary })
      }
      for (const person of members) {
        rows.push({ key: `p${person.id}`, type: 'person', id: person.id, depth: node.depth + 1, person, unitId: unit.id, role: 'member' })
      }
      walk(node.children)
    }
  }
  walk(forest)
  const loose = unassignedPeople(people)
  if (loose.length) {
    const open = expanded.has('unassigned')
    rows.push({ key: 'g-unassigned', type: 'group', id: 'unassigned', depth: 0, open, count: loose.length, expandable: true })
    if (open) for (const person of loose) rows.push({ key: `p${person.id}`, type: 'person', id: person.id, depth: 1, person, unitId: null, role: 'member' })
  }
  return rows
}

// ---------------------------------------------------------------- поиск

/** Нижний регистр, «ё» как «е», лишние пробелы убраны. */
export function normalize(text) {
  return String(text ?? '').toLocaleLowerCase('ru').replace(/ё/g, 'е').replace(/\s+/g, ' ').trim()
}

function scoreText(text, needle) {
  const value = normalize(text)
  if (!value || !needle) return 0
  if (value.startsWith(needle)) return 3
  if (value.split(/[\s«»"(),./-]+/).some((word) => word.startsWith(needle))) return 2
  return value.includes(needle) ? 1 : 0
}

/**
 * Поиск по подразделениям (название, код) и людям (ФИО, должность, email): до limit результатов,
 * сначала совпадения с начала. Результат: { type: 'unit' | 'person', id, title, subtitle, inactive }.
 */
export function searchOrg(query, units = [], people = [], { unitsById = new Map(), limit = 12, includeInactive = false } = {}) {
  const needle = normalize(query)
  if (!needle) return []
  const results = []
  for (const unit of units) {
    const score = Math.max(scoreText(unit.name, needle), unit.code && normalize(unit.code).startsWith(needle) ? 2 : 0)
    if (!score) continue
    const path = unitPathNames(unitsById, unit.id).slice(0, -1)
    results.push({ type: 'unit', id: unit.id, title: unit.name, subtitle: path.slice(-2).join(' / '), kind: unit.kind, score })
  }
  for (const person of people) {
    if (person.is_active === false && !includeInactive) continue
    const score = Math.max(scoreText(person.full_name, needle), Math.min(1, scoreText(person.position, needle)),
      person.email && normalize(person.email).startsWith(needle) ? 1 : 0)
    if (!score) continue
    const unit = unitsById.get(homeOf(person))
    results.push({
      type: 'person', id: person.id, title: person.full_name, subtitle: [person.position, unit?.name].filter(Boolean).join(' · '),
      inactive: person.is_active === false, person, score,
    })
  }
  return results
    .sort((a, b) => b.score - a.score || (a.type === b.type ? 0 : a.type === 'unit' ? -1 : 1) || byName(a.title, b.title))
    .slice(0, limit)
}

// ---------------------------------------------------------------- таблица

/** Строки таблицы подразделений: путь, тип, уровень, руководитель, численность. */
export function unitTableRows(units = [], peopleById = new Map(), kinds = []) {
  const unitsById = new Map(units.map((u) => [u.id, u]))
  const treeOrder = new Map()
  const walk = (nodes) => { for (const node of nodes) { treeOrder.set(node.id, treeOrder.size); walk(node.children) } }
  walk(unitForest(units))
  return units.map((unit) => {
    const path = unitPathNames(unitsById, unit.id)
    const head = peopleById.get(unit.primary_head_id) || null
    const kind = kindInfo(kinds, unit.kind)
    return {
      id: unit.id,
      name: unit.name,
      code: unit.code || '',
      path: path.join(' / '),
      parentPath: path.slice(0, -1).join(' / '),
      level: unit.level || path.length,
      kind: unit.kind,
      kindLabel: kind.label,
      kindColor: kind.color,
      headId: head?.id ?? null,
      headName: head?.full_name || '',
      headPosition: head?.position || '',
      headCount: (unit.head_ids || []).length,
      staff: unit.staff_count ?? 0,
      employees: unit.employee_count ?? 0,
      branch: unit.branch_employee_count ?? 0,
      nested: unit.child_count ?? 0,
      branchUnits: unit.branch_unit_count ?? 0,
      treeOrder: treeOrder.get(unit.id) ?? treeOrder.size,
    }
  })
}

export const TABLE_COLUMNS = [
  { key: 'path', label: 'Подразделение' },
  { key: 'kindLabel', label: 'Тип' },
  { key: 'level', label: 'Уровень', num: true },
  { key: 'headName', label: 'Руководитель' },
  { key: 'staff', label: 'Штат', num: true, hint: 'Сотрудники уровня без руководителей' },
  { key: 'branch', label: 'В ветке', num: true, hint: 'Вместе с вложенными подразделениями' },
  { key: 'nested', label: 'Вложенных', num: true, hint: 'Подразделений на уровень ниже' },
]

export const TABLE_CSV_COLUMNS = [
  { key: 'path', label: 'Путь' },
  { key: 'name', label: 'Подразделение' },
  { key: 'code', label: 'Код' },
  { key: 'kindLabel', label: 'Тип' },
  { key: 'level', label: 'Уровень' },
  { key: 'headName', label: 'Руководитель' },
  { key: 'headPosition', label: 'Должность руководителя' },
  { key: 'headCount', label: 'Руководителей' },
  { key: 'staff', label: 'Штат уровня' },
  { key: 'employees', label: 'Сотрудников с руководителями' },
  { key: 'branch', label: 'Всего в ветке' },
  { key: 'nested', label: 'Вложенных' },
  { key: 'branchUnits', label: 'Всего вложенных' },
]

/** Сортировка: путь — порядок дерева, числа — по величине, строки — по алфавиту; равные — по пути. */
export function sortRows(rows, key, dir = 'asc') {
  const sign = dir === 'desc' ? -1 : 1
  if (key === 'path') return [...rows].sort((a, b) => (a.treeOrder - b.treeOrder) * sign)
  return [...rows].sort((a, b) => {
    const x = a[key]
    const y = b[key]
    const primary = typeof x === 'number' && typeof y === 'number' ? x - y : byName(x ?? '', y ?? '')
    // Пустые строки — в конце при любом направлении
    if (typeof x === 'string' && (x === '') !== (y === '')) return x === '' ? 1 : -1
    return primary * sign || a.treeOrder - b.treeOrder
  })
}

/** Направление по умолчанию при выборе столбца: числа — сначала большие. */
export function nextSort(current, key, columns = TABLE_COLUMNS) {
  if (current.key === key) return { key, dir: current.dir === 'asc' ? 'desc' : 'asc' }
  return { key, dir: columns.find((c) => c.key === key)?.num ? 'desc' : 'asc' }
}

/** CSV для Excel: BOM, разделитель «;», кавычки по необходимости, строки через CRLF. */
export function toCsv(rows, columns) {
  const cell = (value) => {
    const text = String(value ?? '')
    return /[;"\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
  }
  const lines = [columns.map((c) => cell(c.label)).join(';'), ...rows.map((row) => columns.map((c) => cell(row[c.key])).join(';'))]
  return `\uFEFF${lines.join('\r\n')}\r\n`
}

// ---------------------------------------------------------------- администрирование подразделений

/** Дочерние подразделения по родителю. */
function childrenIndex(departments) {
  const map = new Map()
  for (const d of departments) {
    if (d.parent_id == null) continue
    if (!map.has(d.parent_id)) map.set(d.parent_id, [])
    map.get(d.parent_id).push(d.id)
  }
  return map
}

/** Подразделение и все вложенные (id). */
export function subtreeIds(departments, id) {
  const children = childrenIndex(departments)
  const result = new Set()
  const stack = [id]
  while (stack.length) {
    const current = stack.pop()
    if (result.has(current)) continue
    result.add(current)
    stack.push(...(children.get(current) || []))
  }
  return result
}

/** Высота ветки: 1 — без вложенных. */
export function subtreeHeight(departments, id) {
  const children = childrenIndex(departments)
  const height = (current, seen) => {
    if (seen.has(current)) return 0
    seen.add(current)
    const kids = children.get(current) || []
    return 1 + (kids.length ? Math.max(...kids.map((k) => height(k, seen))) : 0)
  }
  return height(id, new Set())
}

/**
 * Куда можно вложить подразделение: не в себя и не во вложенные, и так, чтобы ветка не вышла
 * за предел вложенности. editingId = null — новое подразделение.
 */
export function parentOptions(departments, editingId, maxDepth) {
  const excluded = editingId != null ? subtreeIds(departments, editingId) : new Set()
  const height = editingId != null ? subtreeHeight(departments, editingId) : 1
  return departments
    .filter((d) => !excluded.has(d.id) && (d.level || 1) + height <= maxDepth)
    .map((d) => ({ id: d.id, name: d.name, level: d.level || 1, path: d.path || d.name, kind: d.kind }))
}

export const canAddChild = (department, maxDepth) => (department.level || 1) < maxDepth

/**
 * Видимые строки дерева подразделений: свёрнутые ветки скрыты; при поиске — совпадения
 * и их предки (свёрнутость не учитывается).
 */
export function departmentRows(departments = [], collapsed = new Set(), query = '') {
  const byId = new Map(departments.map((d) => [d.id, d]))
  const needle = normalize(query)
  if (needle) {
    const keep = new Set()
    for (const d of departments) {
      if (!normalize(d.name).includes(needle) && !normalize(d.code).includes(needle)) continue
      let current = d
      const seen = new Set()
      while (current && !seen.has(current.id)) {
        seen.add(current.id)
        keep.add(current.id)
        current = current.parent_id != null ? byId.get(current.parent_id) : null
      }
    }
    return departments.filter((d) => keep.has(d.id)).map((d) => ({ dep: d, depth: (d.level || 1) - 1, match: normalize(d.name).includes(needle) || normalize(d.code).includes(needle) }))
  }
  const rows = []
  const hiddenUnder = []
  for (const d of departments) {
    const depth = (d.level || 1) - 1
    while (hiddenUnder.length && hiddenUnder[hiddenUnder.length - 1] >= depth) hiddenUnder.pop()
    if (hiddenUnder.length) continue
    if (collapsed.has(d.id) && d.child_count) hiddenUnder.push(depth)
    rows.push({ dep: d, depth, match: false })
  }
  return rows
}

/** Текст подтверждения удаления: кого затронет. people — сотрудники из /api/org/tree. */
export function deleteMessage(department, people = []) {
  const listed = people.filter((p) => p.department_id === department.id).sort((a, b) => byName(a.full_name, b.full_name))
  const parts = []
  if (listed.length) {
    const names = listed.slice(0, 5).map((p) => p.full_name)
    const rest = listed.length - names.length
    parts.push(`В подразделении ${listed.length === 1 ? 'числится' : 'числятся'} ${countText(listed.length, PEOPLE_FORMS)}: `
      + `${names.join(', ')}${rest > 0 ? ` и ещё ${rest}` : ''}. ${listed.length === 1 ? 'Он останется' : 'Они останутся'} без подразделения.`)
  } else {
    parts.push('В подразделении никто не числится.')
  }
  const heads = (department.heads || []).filter((h) => !listed.some((p) => p.id === h.user_id))
  if (heads.length) {
    parts.push(`${heads.length === 1 ? 'Руководитель' : 'Руководители'} ${heads.map((h) => h.full_name).join(', ')} `
      + `${heads.length === 1 ? 'перестанет' : 'перестанут'} им руководить.`)
  }
  parts.push('Удаление попадёт в журнал изменений.')
  return parts.join('\n\n')
}

/** Сотрудники в численности: «12» или «12 / 48 в ветке». */
export function headcountText(department) {
  const own = department.employee_count || 0
  return department.child_count ? `${own} / ${department.branch_employee_count || 0} в ветке` : String(own)
}

// ---------------------------------------------------------------- планы загрузки

export const PLAN_FILTERS = [
  { value: 'changes', label: 'Изменения и ошибки' },
  { value: 'errors', label: 'Ошибки' },
  { value: 'all', label: 'Все' },
]

export const PLAN_ACTIONS = {
  create: { label: 'Новый', tone: 'green' },
  update: { label: 'Изменится', tone: 'blue' },
  unchanged: { label: 'Без изменений', tone: 'gray' },
  skip: { label: 'Пропущен', tone: 'gray' },
  error: { label: 'Ошибка', tone: 'red' },
  add: { label: 'Назначить', tone: 'green' },
  exists: { label: 'Уже назначен', tone: 'gray' },
  pending: { label: 'Нет в системе', tone: 'yellow' },
}

const hasErrors = (row) => row.action === 'error' || (row.errors || []).length > 0 || !!row.unresolved

/** Строки загрузки списком и AD: изменения и ошибки / только ошибки / все. */
export function filterPlanUsers(users = [], filter = 'changes') {
  if (filter === 'errors') return users.filter(hasErrors)
  if (filter === 'changes') return users.filter((u) => u.action !== 'unchanged' || hasErrors(u) || (u.warnings || []).length)
  return users
}

/** Подразделения в плане структуры (ошибки у этого плана — общие, не по строкам). */
export function filterStructureDepartments(departments = [], filter = 'changes') {
  if (filter === 'errors') return []
  if (filter === 'changes') return departments.filter((d) => d.action !== 'unchanged')
  return departments
}

export function needsAttention(record) {
  return !!record.unresolved || (record.errors || []).length > 0 || (record.conflicts || []).length > 0
    || (record.warnings || []).length > 0
}

/** Записи загрузки сотрудников: изменения, коллизии и ошибки / только ошибки / все. */
export function filterEmployeeRecords(records = [], filter = 'changes') {
  if (filter === 'errors') return records.filter(hasErrors)
  if (filter === 'changes') return records.filter((r) => r.action === 'create' || r.action === 'update' || needsAttention(r))
  return records
}

function chip(label, value, tone = 'gray', show = true) {
  return show ? [{ label, value, tone: value ? tone : 'gray' }] : []
}

export function structureChips(summary) {
  if (!summary) return []
  return [
    ...chip('В файле', summary.departments),
    ...chip('Новых', summary.create, 'green'),
    ...chip('Изменится', summary.update, 'blue'),
    ...chip('Без изменений', summary.unchanged),
    ...chip('Настроек изменится', summary.settings, 'blue', summary.settings > 0),
    ...chip('Назначить руководителей', summary.add_heads, 'green', summary.add_heads > 0),
    ...chip('Руководителей нет в системе', summary.pending_heads, 'yellow', summary.pending_heads > 0),
    ...chip('Нет в файле', summary.missing_in_file, 'gray', summary.missing_in_file > 0),
    ...chip('Ошибок', summary.errors, 'red'),
  ]
}

export function listChips(summary) {
  if (!summary) return []
  return [
    ...chip('Строк', summary.rows),
    ...chip('Новых подразделений', summary.create_departments, 'green', summary.create_departments > 0),
    ...chip('Новых сотрудников', summary.create_users, 'green'),
    ...chip('Изменится', summary.update_users, 'blue'),
    ...chip('Без изменений', summary.unchanged),
    ...chip('Отключить', summary.deactivate_users, 'yellow', summary.deactivate_users > 0),
    ...chip('Предупреждений', summary.warnings, 'yellow', summary.warnings > 0),
    ...chip('Ошибок', summary.errors, 'red'),
  ]
}

export function employeeChips(summary) {
  if (!summary) return []
  return [
    ...chip('Записей', summary.records),
    ...chip('Новых', summary.create, 'green'),
    ...chip('Изменится', summary.update, 'blue'),
    ...chip('Без изменений', summary.unchanged),
    ...chip('Пропущено', summary.skip, 'gray', summary.skip > 0),
    ...chip('Различий', summary.conflicts, 'yellow', summary.conflicts > 0),
    ...chip('Нужно решение', summary.unresolved, 'red', summary.unresolved > 0),
    ...chip('Новых подразделений', summary.create_departments, 'green', summary.create_departments > 0),
    ...chip('Ошибок', summary.errors, 'red'),
  ]
}

/** Значение в плане для показа: списки через «; », пустое — «—». */
export function displayValue(value) {
  if (Array.isArray(value)) return value.length ? value.join('; ') : '—'
  if (value === true) return 'да'
  if (value === false) return 'нет'
  return value === '' || value === null || value === undefined ? '—' : String(value)
}

// ---------------------------------------------------------------- история изменений

export const HISTORY_FIELDS = {
  department: 'Подразделение', manager: 'Руководитель (явно)', reports_to_none: 'Первое лицо', position: 'Должность',
  head_of: 'Руководит', name: 'Название', parent: 'Входит в', kind: 'Тип', code: 'Код', sort_order: 'Порядок',
  heads: 'Руководители',
}

/** Изменённые поля записи журнала: [{ key, label, old, new }]. */
export function historyChanges(entry) {
  const before = entry?.before || {}
  const after = entry?.after || {}
  const keys = [...new Set([...Object.keys(before), ...Object.keys(after)])]
  return keys
    .filter((key) => JSON.stringify(before[key] ?? null) !== JSON.stringify(after[key] ?? null))
    .map((key) => ({ key, label: HISTORY_FIELDS[key] || key, old: displayValue(before[key]), new: displayValue(after[key]) }))
}

// ---------------------------------------------------------------- решения по сотрудникам

export const CHOICE_LABELS = { current: 'Система', incoming: 'Файл', merge: 'Объединить', custom: 'Своё' }

export const NEW_USER_MODES = [
  { value: 'no_access', label: 'Без доступа', hint: 'Видны в структуре; войти не смогут, пока им не выдадут доступ' },
  { value: 'active', label: 'Активные', hint: 'Вход по учётной записи домена — с паролем домена' },
  { value: 'inactive', label: 'Отключённые', hint: 'Не видны в структуре; включить можно в разделе «Пользователи»' },
]

export function decisionFor(decisions, record, conflict) {
  return decisions[record.key]?.fields?.[conflict.field]?.choice || conflict.choice || 'current'
}

/** Своё значение: сохранённое, иначе из файла, иначе из системы (списки — через « | » или «, »). */
export function customValueFor(decisions, record, conflict) {
  const stored = decisions[record.key]?.fields?.[conflict.field]
  if (stored && 'value' in stored) return stored.value ?? ''
  const source = conflict.value ?? (conflict.incoming !== '' && conflict.incoming != null ? conflict.incoming : conflict.current)
  return Array.isArray(source) ? source.join(conflict.field === 'heads' ? ' | ' : ', ') : (source ?? '')
}

export function withFieldChoice(decisions, key, field, choice, value) {
  const record = decisions[key] || {}
  const fields = { ...(record.fields || {}), [field]: value === undefined ? { choice } : { choice, value } }
  return { ...decisions, [key]: { ...record, fields } }
}

export function withIdentity(decisions, key, identity) {
  return { ...decisions, [key]: { ...(decisions[key] || {}), identity } }
}

/** «Везде оставить значения системы» / «везде взять из файла» — где этот выбор возможен. */
export function withBulkChoice(decisions, plan, choice) {
  let next = { ...decisions }
  for (const record of plan?.records || []) {
    for (const conflict of record.conflicts || []) {
      if (conflict.choices.includes(choice)) next = withFieldChoice(next, record.key, conflict.field, choice)
    }
  }
  return next
}

/** Варианты решения: «своё» для да/нет не нужно. */
export function visibleChoices(conflict) {
  return conflict.kind === 'bool' ? conflict.choices.filter((c) => c !== 'custom') : conflict.choices
}

// ---------------------------------------------------------------- быстрая загрузка списком

export const LIST_SAMPLE = [
  'email;ФИО;Подразделение;Должность;Руководитель;Руководит',
  'director@company.ru;Иванов Иван Иванович;Компания;Генеральный директор;;да',
  'sales.head@company.ru;Петрова Анна Сергеевна;Компания / Коммерческая дирекция / Отдел продаж;Начальник отдела;;да',
  'manager@company.ru;Сидоров Пётр Олегович;Компания / Коммерческая дирекция / Отдел продаж;Менеджер по продажам;;',
  'analyst@company.ru;Козлова Мария Андреевна;Компания / Коммерческая дирекция / Отдел продаж;Аналитик;director@company.ru;',
].join('\n')
