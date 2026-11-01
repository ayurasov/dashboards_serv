import { describe, expect, it } from 'vitest'
import {
  LOOSE_ID, ancestorsOf, avatarTone, canAddChild, clampZoom, countText, customValueFor, decisionFor, deleteMessage,
  departmentRows, displayValue, employeeChips, expandedToLevel, filterEmployeeRecords, filterPeople, filterPlanUsers,
  filterStructureDepartments, forestDepth, historyChanges, forestSize, headcountText, headsOf, indexForest, initials, isStackable,
  kindInfo, kindValueFromLabel, levelOptions, listChips, membersOf, needsAttention, nextSort, normalize, parentOptions,
  pathTo, peopleForest, resolveView, revealIn, searchOrg, sortRows, structureChips, subtreeHeight, subtreeIds, toCsv,
  toggleIn, treeRows, unassignedPeople, unitForest, unitPathNames, unitTableRows, visibleChoices, visibleCount,
  withBulkChoice, withFieldChoice, withIdentity,
} from './org'

const KINDS = [
  { value: 'company', label: 'Компания', color: '#7c3aed' },
  { value: 'division', label: 'Дирекция', color: '#0369a1' },
  { value: 'department', label: 'Отдел', color: '#4f7cff' },
]

const unit = (id, name, parent_id = null, over = {}) => ({
  id, name, parent_id, kind: 'department', sort_order: 0, level: 1, child_count: 0, head_ids: [], primary_head_id: null,
  staff_count: 0, employee_count: 0, branch_employee_count: 0, branch_unit_count: 0, code: null, ...over,
})
const person = (id, full_name, over = {}) => ({
  id, full_name, position: null, department_id: null, home_unit_id: null, direct_manager_id: null, is_active: true,
  report_count: 0, branch_count: 0, head_of: [], ...over,
})

// Компания → Дирекция (продажи, финансы) → Отдел
const UNITS = [
  unit(1, 'Компания', null, { kind: 'company', level: 1, child_count: 2, head_ids: [10], primary_head_id: 10, branch_employee_count: 6, code: 'CO' }),
  unit(2, 'Финансы', 1, { kind: 'division', level: 2, sort_order: 2, head_ids: [11], primary_head_id: 11, staff_count: 1, employee_count: 2, branch_employee_count: 2 }),
  unit(3, 'Продажи', 1, { kind: 'division', level: 2, sort_order: 1, child_count: 1, head_ids: [12, 13], primary_head_id: 13, staff_count: 0, employee_count: 2, branch_employee_count: 3, branch_unit_count: 1 }),
  unit(4, 'Отдел Ёлок', 3, { level: 3, staff_count: 1, employee_count: 1, branch_employee_count: 1, code: 'ELK' }),
]
const PEOPLE = [
  person(10, 'Громов Андрей', { position: 'Генеральный директор', home_unit_id: 1, department_id: 1, report_count: 3, branch_count: 5 }),
  person(11, 'Белова Ирина', { position: 'Финансовый директор', home_unit_id: 2, department_id: 2, direct_manager_id: 10, report_count: 1, branch_count: 1 }),
  person(12, 'Антонов Олег', { position: 'Заместитель', home_unit_id: 3, department_id: 3, direct_manager_id: 13 }),
  person(13, 'Яковлева Ольга', { position: 'Коммерческий директор', home_unit_id: 3, department_id: 3, direct_manager_id: 10, report_count: 2, branch_count: 2 }),
  person(14, 'Ёлкин Пётр', { position: 'Бухгалтер', home_unit_id: 2, department_id: 2, direct_manager_id: 11 }),
  person(15, 'Смирнов Иван', { position: 'Менеджер', home_unit_id: 4, department_id: 4, direct_manager_id: 13 }),
  person(16, 'Отключённый Сотрудник', { home_unit_id: 4, department_id: 4, is_active: false, direct_manager_id: 13 }),
  person(17, 'Администратор системы', { position: 'Администратор' }),
]
const unitsById = new Map(UNITS.map((u) => [u.id, u]))
const peopleById = new Map(PEOPLE.map((p) => [p.id, p]))

describe('виды и масштаб', () => {
  it('resolveView: первый допустимый вариант, иначе оргсхема', () => {
    expect(resolveView('table', 'people')).toBe('table')
    expect(resolveView('', 'people', 'chart')).toBe('people')
    expect(resolveView(undefined, 'bogus', 'tree')).toBe('tree')
    expect(resolveView(null, null)).toBe('chart')
  })
  it('clampZoom: 30–160 %, округление до сотых', () => {
    expect(clampZoom(0.1)).toBe(0.3)
    expect(clampZoom(2)).toBe(1.6)
    expect(clampZoom(0.8999999)).toBe(0.9)
    expect(clampZoom('abc')).toBe(1)
  })
  it('countText: число и форма слова', () => {
    expect(countText(1, ['сотрудник', 'сотрудника', 'сотрудников'])).toBe('1 сотрудник')
    expect(countText(3, ['сотрудник', 'сотрудника', 'сотрудников'])).toBe('3 сотрудника')
    expect(countText(1250, ['сотрудник', 'сотрудника', 'сотрудников']).replace(/\s/g, ' ')).toBe('1 250 сотрудников')
  })
  it('levelOptions: 1…глубина (до 12) и «все»', () => {
    expect(levelOptions(3).map((o) => o.value)).toEqual([1, 2, 3, 'all'])
    expect(levelOptions(0).map((o) => o.value)).toEqual([1, 'all'])
    expect(levelOptions(40)).toHaveLength(13)
  })
})

describe('типы уровней и аватар', () => {
  it('kindInfo: название и цвет; неизвестный — ключ и нейтральный цвет', () => {
    expect(kindInfo(KINDS, 'division')).toEqual({ value: 'division', label: 'Дирекция', color: '#0369a1' })
    expect(kindInfo(KINDS, 'lab')).toEqual({ value: 'lab', label: 'lab', color: '#64748b' })
    expect(kindInfo([], undefined).label).toBe('Подразделение')
  })
  it('kindValueFromLabel: латиница, без повторов', () => {
    expect(kindValueFromLabel('Сектор продаж')).toBe('sektor-prodazh')
    expect(kindValueFromLabel('Отдел', ['otdel'])).toBe('otdel-2')
    expect(kindValueFromLabel('123 Лаборатория')).toBe('laboratoriya')
    expect(kindValueFromLabel('!!!')).toBe('kind')
    expect(kindValueFromLabel('Ёжик')).toMatch(/^[a-z][a-z0-9_-]{0,31}$/)
  })
  it('initials и avatarTone', () => {
    expect(initials('Громов Андрей Викторович')).toBe('ГА')
    expect(initials('  «Пётр»  ')).toBe('П')
    expect(initials('')).toBe('?')
    expect(avatarTone('Громов')).toBe(avatarTone('Громов'))
    expect(avatarTone('x')).toBeGreaterThanOrEqual(1)
    expect(avatarTone('x')).toBeLessThanOrEqual(7)
  })
})

describe('лес подразделений', () => {
  const forest = unitForest(UNITS)
  const index = indexForest(forest)
  it('корни, порядок соседей по sort_order, глубина', () => {
    expect(forest.map((n) => n.id)).toEqual([1])
    expect(forest[0].children.map((n) => n.item.name)).toEqual(['Продажи', 'Финансы'])
    expect(forest[0].children[0].children[0].depth).toBe(2)
    expect(forestDepth(forest)).toBe(3)
    expect(forestSize(forest)).toBe(4)
  })
  it('потерянный родитель и цикл не прячут подразделения', () => {
    const odd = unitForest([unit(1, 'А', 99), unit(2, 'Б', 3), unit(3, 'В', 2)])
    expect(forestSize(odd)).toBe(3)
    expect(odd[0].id).toBe(1)
  })
  it('ancestorsOf и pathTo', () => {
    expect(ancestorsOf(index, 4)).toEqual([1, 3])
    expect(ancestorsOf(index, 1)).toEqual([])
    expect([...pathTo(index, 4)]).toEqual([1, 3, 4])
    expect(pathTo(index, 999).size).toBe(0)
    expect(pathTo(index, null).size).toBe(0)
  })
  it('expandedToLevel: видно N уровней, null — все', () => {
    expect([...expandedToLevel(forest, 1)]).toEqual([])
    expect([...expandedToLevel(forest, 2)]).toEqual([1])
    expect([...expandedToLevel(forest, null)].sort()).toEqual([1, 3])
    expect([...expandedToLevel(forest, 2, { leaves: true })]).toEqual([1])
    expect([...expandedToLevel(forest, 3, { leaves: true })].sort()).toEqual([1, 2, 3])
    expect([...expandedToLevel(forest, null, { leaves: true })].sort()).toEqual([1, 2, 3, 4])
  })
  it('revealIn раскрывает предков, toggleIn переключает', () => {
    expect([...revealIn(new Set(), index, 4)].sort()).toEqual([1, 3])
    expect([...revealIn(new Set(), index, 3, { self: true })].sort()).toEqual([1, 3])
    expect([...revealIn(new Set(), index, 2, { self: true })]).toEqual([1])
    expect([...toggleIn(new Set([1]), 1)]).toEqual([])
    expect([...toggleIn(new Set(), 2)]).toEqual([2])
  })
  it('visibleCount: карточки при данном раскрытии', () => {
    expect(visibleCount(forest, new Set())).toBe(1)
    expect(visibleCount(forest, new Set([1]))).toBe(3)
    expect(visibleCount(forest, new Set([1, 3]))).toBe(4)
  })
  it('isStackable: несколько дочерних без своих дочерних', () => {
    expect(isStackable(forest[0])).toBe(false)
    expect(isStackable(forest[0].children[0])).toBe(false) // один дочерний
    expect(isStackable({ children: [{ children: [] }, { children: [] }] })).toBe(true)
  })
  it('unitPathNames', () => {
    expect(unitPathNames(unitsById, 4)).toEqual(['Компания', 'Продажи', 'Отдел Ёлок'])
    expect(unitPathNames(unitsById, 999)).toEqual([])
  })
})

describe('лес людей', () => {
  const forest = peopleForest(PEOPLE)
  it('по непосредственному руководителю, без отключённых, команды крупнее — первыми', () => {
    expect(forest[0].id).toBe(10)
    expect(forest[0].children.map((n) => n.id)).toEqual([13, 11])
    expect(forest[0].children[0].children.map((n) => n.id)).toEqual([12, 15])
    expect(indexForest(forest).has(16)).toBe(false)
  })
  it('без руководителя и подчинённых — в группе «Вне подчинения»', () => {
    const group = forest.at(-1)
    expect(group.id).toBe(LOOSE_ID)
    expect(group.group).toBe(true)
    expect(group.item.count).toBe(1)
    expect(group.children[0]).toMatchObject({ id: 17, depth: 1 })
  })
  it('если руководителей нет вовсе — группы нет', () => {
    const flat = peopleForest([person(1, 'А'), person(2, 'Б')])
    expect(flat.map((n) => n.id)).toEqual([1, 2])
  })
  it('цикл подчинения не прячет людей', () => {
    const cyc = peopleForest([person(1, 'А', { direct_manager_id: 2 }), person(2, 'Б', { direct_manager_id: 1 })])
    expect(forestSize(cyc)).toBe(2)
  })
})

describe('состав подразделения', () => {
  it('membersOf: штат уровня без руководителей и отключённых', () => {
    expect(membersOf(unitsById.get(2), PEOPLE).map((p) => p.id)).toEqual([14])
    expect(membersOf(unitsById.get(3), PEOPLE)).toEqual([])
    expect(membersOf(unitsById.get(4), PEOPLE).map((p) => p.id)).toEqual([15])
    expect(membersOf(null, PEOPLE)).toEqual([])
  })
  it('headsOf: основной первым, отметка «числится в другом»', () => {
    const heads = headsOf(unitsById.get(3), peopleById)
    expect(heads.map((h) => [h.person.id, h.primary, h.visiting])).toEqual([[13, true, false], [12, false, false]])
    const visiting = headsOf(unit(9, 'Х', null, { head_ids: [10], primary_head_id: 10 }), peopleById)
    expect(visiting[0].visiting).toBe(true)
  })
  it('unassignedPeople и filterPeople', () => {
    expect(unassignedPeople(PEOPLE).map((p) => p.id)).toEqual([17])
    expect(filterPeople(PEOPLE, 'ДИРЕКТОР').map((p) => p.id)).toEqual([10, 11, 13])
    expect(filterPeople(PEOPLE, 'елкин').map((p) => p.id)).toEqual([14])
    expect(filterPeople(PEOPLE, '')).toBe(PEOPLE)
  })
  it('treeRows: руководители, затем сотрудники, затем вложенные; «Вне структуры» в конце', () => {
    const forest = unitForest(UNITS)
    const closed = treeRows(forest, new Set(), PEOPLE, peopleById)
    expect(closed.map((r) => r.key)).toEqual(['u1', 'g-unassigned'])
    const rows = treeRows(forest, new Set([1, 3, 'unassigned']), PEOPLE, peopleById)
    expect(rows.map((r) => r.key)).toEqual([
      'u1', 'h1-10', 'u3', 'h3-13', 'h3-12', 'u4', 'u2', 'g-unassigned', 'p17',
    ])
    expect(rows.find((r) => r.key === 'h3-13')).toMatchObject({ role: 'head', primary: true, depth: 2 })
    expect(rows.find((r) => r.key === 'u4')).toMatchObject({ expandable: true, open: false })
    const open4 = treeRows(forest, new Set([1, 3, 4]), PEOPLE, peopleById)
    expect(open4.filter((r) => r.unitId === 4).map((r) => r.id)).toEqual([15])
  })
})

describe('поиск', () => {
  const search = (q, opts = {}) => searchOrg(q, UNITS, PEOPLE, { unitsById, ...opts })
  it('normalize: регистр, «ё», пробелы', () => {
    expect(normalize('  Ёлкин   Пётр ')).toBe('елкин петр')
    expect(normalize(null)).toBe('')
  })
  it('люди по ФИО и должности, подразделения по названию и коду', () => {
    expect(search('ёлк').map((r) => [r.type, r.id])).toEqual([['person', 14]])
    expect(search('елок').map((r) => [r.type, r.id])).toEqual([['unit', 4]])
    expect(search('директор').map((r) => r.id)).toEqual([11, 10, 13])
    expect(search('elk')[0]).toMatchObject({ type: 'unit', id: 4, title: 'Отдел Ёлок', subtitle: 'Компания / Продажи' })
    expect(search('смир')[0]).toMatchObject({ type: 'person', id: 15, subtitle: 'Менеджер · Отдел Ёлок' })
  })
  it('с начала — выше, чем в середине; пустой запрос — пусто; предел', () => {
    expect(search('про')[0].title).toBe('Продажи')
    expect(search('   ')).toEqual([])
    expect(search('о', { limit: 2 })).toHaveLength(2)
  })
  it('отключённые — только по запросу', () => {
    expect(search('отключ')).toEqual([])
    expect(search('отключ', { includeInactive: true })[0]).toMatchObject({ id: 16, inactive: true })
  })
})

describe('таблица', () => {
  const rows = unitTableRows(UNITS, peopleById, KINDS)
  it('путь, тип, руководитель, численность', () => {
    const sales = rows.find((r) => r.id === 3)
    expect(sales).toMatchObject({
      path: 'Компания / Продажи', parentPath: 'Компания', level: 2, kindLabel: 'Дирекция', kindColor: '#0369a1',
      headId: 13, headName: 'Яковлева Ольга', headCount: 2, staff: 0, employees: 2, branch: 3, nested: 1, branchUnits: 1,
    })
    expect(rows.find((r) => r.id === 4)).toMatchObject({ headName: '', code: 'ELK' })
  })
  it('sortRows: путь — порядок дерева, числа, строки; пустые — в конце', () => {
    expect(sortRows(rows, 'path').map((r) => r.id)).toEqual([1, 3, 4, 2])
    expect(sortRows(rows, 'path', 'desc').map((r) => r.id)).toEqual([2, 4, 3, 1])
    expect(sortRows(rows, 'branch', 'desc').map((r) => r.id)).toEqual([1, 3, 2, 4])
    expect(sortRows(rows, 'headName', 'asc').map((r) => r.id)).toEqual([2, 1, 3, 4])
    expect(sortRows(rows, 'headName', 'desc').map((r) => r.id)).toEqual([3, 1, 2, 4])
    expect(sortRows(rows, 'kindLabel').map((r) => r.id)).toEqual([3, 2, 1, 4])
  })
  it('nextSort: повторный щелчок меняет направление, числа — сначала большие', () => {
    expect(nextSort({ key: 'path', dir: 'asc' }, 'path')).toEqual({ key: 'path', dir: 'desc' })
    expect(nextSort({ key: 'path', dir: 'asc' }, 'staff')).toEqual({ key: 'staff', dir: 'desc' })
    expect(nextSort({ key: 'staff', dir: 'desc' }, 'headName')).toEqual({ key: 'headName', dir: 'asc' })
  })
  it('toCsv: BOM, «;», кавычки, CRLF', () => {
    const csv = toCsv([{ a: 'x;y', b: 'он сказал "да"' }, { a: 1, b: null }], [{ key: 'a', label: 'А' }, { key: 'b', label: 'Б' }])
    expect(csv.startsWith('﻿')).toBe(true)
    expect(csv).toBe('﻿А;Б\r\n"x;y";"он сказал ""да"""\r\n1;\r\n')
  })
})

describe('администрирование подразделений', () => {
  const DEPS = [
    { id: 1, name: 'Компания', code: 'CO', parent_id: null, level: 1, child_count: 2, path: 'Компания' },
    { id: 3, name: 'Продажи', code: null, parent_id: 1, level: 2, child_count: 1, path: 'Компания / Продажи' },
    { id: 4, name: 'Отдел Ёлок', code: 'ELK', parent_id: 3, level: 3, child_count: 0, path: 'Компания / Продажи / Отдел Ёлок' },
    { id: 2, name: 'Финансы', code: null, parent_id: 1, level: 2, child_count: 0, path: 'Компания / Финансы' },
  ]
  it('subtreeIds и subtreeHeight', () => {
    expect([...subtreeIds(DEPS, 3)].sort()).toEqual([3, 4])
    expect(subtreeHeight(DEPS, 1)).toBe(3)
    expect(subtreeHeight(DEPS, 4)).toBe(1)
  })
  it('parentOptions: без себя и вложенных, в пределах глубины', () => {
    expect(parentOptions(DEPS, 3, 15).map((o) => o.id)).toEqual([1, 2])
    expect(parentOptions(DEPS, 3, 3).map((o) => o.id)).toEqual([1])
    expect(parentOptions(DEPS, null, 3).map((o) => o.id)).toEqual([1, 3, 2])
    expect(parentOptions(DEPS, null, 2).map((o) => o.id)).toEqual([1])
  })
  it('canAddChild: на пределе вложенности — нельзя', () => {
    expect(canAddChild(DEPS[2], 3)).toBe(false)
    expect(canAddChild(DEPS[1], 3)).toBe(true)
  })
  it('departmentRows: свёрнутые ветки скрыты; поиск — совпадения с предками', () => {
    expect(departmentRows(DEPS).map((r) => [r.dep.id, r.depth])).toEqual([[1, 0], [3, 1], [4, 2], [2, 1]])
    expect(departmentRows(DEPS, new Set([3])).map((r) => r.dep.id)).toEqual([1, 3, 2])
    expect(departmentRows(DEPS, new Set([1])).map((r) => r.dep.id)).toEqual([1])
    const found = departmentRows(DEPS, new Set([1]), 'елок')
    expect(found.map((r) => [r.dep.id, r.match])).toEqual([[1, false], [3, false], [4, true]])
    expect(departmentRows(DEPS, new Set(), 'elk').map((r) => r.dep.id)).toEqual([1, 3, 4])
  })
  it('deleteMessage: кого затронет удаление', () => {
    const dep = { id: 2, heads: [{ user_id: 11, full_name: 'Белова Ирина' }, { user_id: 99, full_name: 'Кто-то Ещё' }] }
    const text = deleteMessage(dep, PEOPLE)
    expect(text).toContain('числятся 2 сотрудника: Белова Ирина, Ёлкин Пётр. Они останутся без подразделения.')
    expect(text).toContain('Руководитель Кто-то Ещё перестанет им руководить.')
    expect(deleteMessage({ id: 77, heads: [] }, PEOPLE)).toContain('никто не числится')
    const many = Array.from({ length: 7 }, (_, i) => person(100 + i, `Сотрудник ${i}`, { department_id: 5 }))
    expect(deleteMessage({ id: 5 }, many)).toContain('и ещё 2')
  })
  it('headcountText: своя численность и ветка', () => {
    expect(headcountText({ employee_count: 2, child_count: 1, branch_employee_count: 3 })).toBe('2 / 3 в ветке')
    expect(headcountText({ employee_count: 4, child_count: 0 })).toBe('4')
  })
})

describe('планы загрузки', () => {
  const users = [
    { line: 2, action: 'create', errors: [], warnings: [] },
    { line: 3, action: 'unchanged', errors: [], warnings: [] },
    { line: 4, action: 'error', errors: ['нет email'], warnings: [] },
    { line: 5, action: 'unchanged', errors: [], warnings: ['руководитель не найден'] },
  ]
  it('filterPlanUsers', () => {
    expect(filterPlanUsers(users, 'changes').map((u) => u.line)).toEqual([2, 4, 5])
    expect(filterPlanUsers(users, 'errors').map((u) => u.line)).toEqual([4])
    expect(filterPlanUsers(users, 'all')).toHaveLength(4)
  })
  it('filterStructureDepartments', () => {
    const deps = [{ action: 'create' }, { action: 'unchanged' }, { action: 'update' }]
    expect(filterStructureDepartments(deps, 'changes')).toHaveLength(2)
    expect(filterStructureDepartments(deps, 'errors')).toEqual([])
    expect(filterStructureDepartments(deps, 'all')).toHaveLength(3)
  })
  it('filterEmployeeRecords и needsAttention', () => {
    const records = [
      { key: 'a', action: 'unchanged', conflicts: [], errors: [], warnings: [] },
      { key: 'b', action: 'unchanged', conflicts: [{ field: 'position' }], errors: [], warnings: [] },
      { key: 'c', action: 'create', conflicts: [], errors: [], warnings: [], unresolved: true },
      { key: 'd', action: 'update', conflicts: [], errors: ['ошибка'], warnings: [] },
    ]
    expect(filterEmployeeRecords(records, 'changes').map((r) => r.key)).toEqual(['b', 'c', 'd'])
    expect(filterEmployeeRecords(records, 'errors').map((r) => r.key)).toEqual(['c', 'd'])
    expect(needsAttention(records[0])).toBe(false)
    expect(needsAttention(records[1])).toBe(true)
  })
  it('сводки: подписи, тона, необязательные чипы', () => {
    const s = structureChips({ departments: 13, create: 0, update: 1, unchanged: 12, settings: 0, add_heads: 0, existing_heads: 5, pending_heads: 2, missing_in_file: 0, errors: 0 })
    expect(s.map((c) => c.label)).toEqual(['В файле', 'Новых', 'Изменится', 'Без изменений', 'Руководителей нет в системе', 'Ошибок'])
    expect(s.find((c) => c.label === 'Изменится').tone).toBe('blue')
    expect(s.find((c) => c.label === 'Новых').tone).toBe('gray')
    const l = listChips({ rows: 3, create_departments: 1, create_users: 2, update_users: 0, unchanged: 1, deactivate_users: 0, errors: 1, warnings: 0 })
    expect(l.find((c) => c.label === 'Ошибок')).toEqual({ label: 'Ошибок', value: 1, tone: 'red' })
    expect(l.some((c) => c.label === 'Отключить')).toBe(false)
    const e = employeeChips({ records: 2, create: 1, update: 0, unchanged: 1, skip: 0, conflicts: 3, unresolved: 1, errors: 0, create_departments: 0 })
    expect(e.map((c) => c.label)).toContain('Нужно решение')
    expect(structureChips(null)).toEqual([])
  })
  it('displayValue', () => {
    expect(displayValue(['а', 'б'])).toBe('а; б')
    expect(displayValue([])).toBe('—')
    expect(displayValue('')).toBe('—')
    expect(displayValue(true)).toBe('да')
    expect(displayValue(0)).toBe('0')
  })
})

describe('решения по коллизиям сотрудников', () => {
  const record = { key: 'a@x.ru' }
  const conflict = { field: 'position', choice: 'current', choices: ['current', 'incoming', 'custom'], current: 'Инженер', incoming: 'Ведущий инженер', kind: 'text' }
  it('decisionFor: выбор администратора, иначе из плана', () => {
    expect(decisionFor({}, record, conflict)).toBe('current')
    const d = withFieldChoice({}, 'a@x.ru', 'position', 'incoming')
    expect(decisionFor(d, record, conflict)).toBe('incoming')
  })
  it('customValueFor: сохранённое, из файла, из системы; списки', () => {
    expect(customValueFor({}, record, conflict)).toBe('Ведущий инженер')
    expect(customValueFor({}, record, { ...conflict, incoming: '' })).toBe('Инженер')
    const d = withFieldChoice({}, 'a@x.ru', 'position', 'custom', 'Архитектор')
    expect(customValueFor(d, record, conflict)).toBe('Архитектор')
    expect(customValueFor({}, record, { field: 'heads', incoming: ['А / Б (основной)', 'В'] })).toBe('А / Б (основной) | В')
  })
  it('withIdentity и withBulkChoice не теряют остальное', () => {
    let d = withIdentity({}, 'a@x.ru', 'same')
    d = withFieldChoice(d, 'a@x.ru', 'phone', 'custom', '+7')
    expect(d['a@x.ru']).toEqual({ identity: 'same', fields: { phone: { choice: 'custom', value: '+7' } } })
    const plan = { records: [
      { key: 'a@x.ru', conflicts: [conflict, { field: 'login', choices: ['current', 'custom'] }] },
      { key: 'b@x.ru', conflicts: [{ field: 'heads', choices: ['current', 'incoming', 'merge', 'custom'] }] },
    ] }
    const bulk = withBulkChoice(d, plan, 'incoming')
    expect(bulk['a@x.ru'].identity).toBe('same')
    expect(bulk['a@x.ru'].fields.position).toEqual({ choice: 'incoming' })
    expect(bulk['a@x.ru'].fields.login).toBeUndefined()
    expect(bulk['b@x.ru'].fields.heads).toEqual({ choice: 'incoming' })
  })
  it('visibleChoices: для да/нет без «своего»', () => {
    expect(visibleChoices({ kind: 'bool', choices: ['current', 'incoming', 'custom'] })).toEqual(['current', 'incoming'])
    expect(visibleChoices(conflict)).toEqual(conflict.choices)
  })
})

describe('история', () => {
  it('historyChanges: только изменённые поля, с подписями', () => {
    const entry = {
      before: { department: 'Компания / Продажи', manager: null, reports_to_none: false, position: 'Менеджер', head_of: [] },
      after: { department: 'Компания / Финансы', manager: 'Громов Андрей', reports_to_none: false, position: 'Менеджер', head_of: ['Компания / Финансы (основной)'] },
    }
    expect(historyChanges(entry)).toEqual([
      { key: 'department', label: 'Подразделение', old: 'Компания / Продажи', new: 'Компания / Финансы' },
      { key: 'manager', label: 'Руководитель (явно)', old: '—', new: 'Громов Андрей' },
      { key: 'head_of', label: 'Руководит', old: '—', new: 'Компания / Финансы (основной)' },
    ])
    expect(historyChanges({ before: null, after: { reports_to_none: true } })).toEqual([
      { key: 'reports_to_none', label: 'Первое лицо', old: '—', new: 'да' },
    ])
    expect(historyChanges(null)).toEqual([])
  })
})
