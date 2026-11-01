import { describe, expect, it } from 'vitest'
import {
  ACCESS_COLUMNS,
  accessSummary,
  actionLabel,
  auditDiff,
  avatarTone,
  buildAccessRows,
  entityLabel,
  formatAuditValue,
  formatMinutes,
  formFieldErrors,
  groupRules,
  initials,
  isValidUsername,
  normalizePalette,
  pageRange,
  paletteProblem,
  parseThreshold,
  profileForm,
  profilePatch,
  ruleBody,
  ruleDirty,
  ruleProblem,
  ruleZones,
  sameAccess,
  serializeAccess,
  setRowLevel,
  setRowScope,
  sortServices,
  USERNAME_PATTERN,
  userFormErrors,
} from './admin'

const SERVICES = [
  { key: 'hr', title: 'Служба персонала', short_title: 'Персонал', has_dashboard: true },
  { key: 'apparat_gd', title: 'Аппарат генерального директора', short_title: 'Аппарат ГД', has_dashboard: false },
  { key: 'tech', title: 'Техническая поддержка', short_title: 'Техподдержка', has_dashboard: true },
  { key: 'it', title: 'ИТ-служба', short_title: 'ИТ', has_dashboard: false },
]

describe('матрица доступа', () => {
  it('службы с дашбордом идут первыми, порядок внутри групп сохраняется', () => {
    expect(sortServices(SERVICES).map((s) => s.key)).toEqual(['hr', 'tech', 'apparat_gd', 'it'])
  })

  it('строки строятся из служб и текущего доступа', () => {
    const rows = buildAccessRows(SERVICES, [
      { service_key: 'hr', level: 'viewer', department_scope: true },
      { service_key: 'it', level: 'manager', department_scope: false },
    ])
    expect(rows.map((r) => [r.key, r.level, r.department_scope, r.scopeAvailable])).toEqual([
      ['hr', 'viewer', true, true],
      ['tech', '', false, false],
      ['apparat_gd', '', false, false],
      ['it', 'manager', false, false],
    ])
    expect(rows[2].has_dashboard).toBe(false)
  })

  it('ограничение подразделениями не переносится на другие службы и уровни', () => {
    const rows = buildAccessRows(SERVICES, [
      { service_key: 'tech', level: 'viewer', department_scope: true },
      { service_key: 'hr', level: 'editor', department_scope: true },
    ])
    expect(rows.find((r) => r.key === 'tech').department_scope).toBe(false)
    expect(rows.find((r) => r.key === 'hr').department_scope).toBe(false)
  })

  it('смена уровня снимает ограничение, если уровень не «Просмотр»', () => {
    let rows = buildAccessRows(SERVICES, [{ service_key: 'hr', level: 'viewer', department_scope: true }])
    rows = setRowLevel(rows, 'hr', 'editor')
    expect(rows[0]).toMatchObject({ level: 'editor', department_scope: false })
    rows = setRowScope(rows, 'hr', true)
    expect(rows[0].department_scope).toBe(false)
    rows = setRowScope(setRowLevel(rows, 'hr', 'viewer'), 'hr', true)
    expect(rows[0].department_scope).toBe(true)
    // Для служб без ограничения флажок не ставится
    expect(setRowScope(setRowLevel(rows, 'tech', 'viewer'), 'tech', true)[1].department_scope).toBe(false)
  })

  it('сериализуются только выданные службы', () => {
    let rows = buildAccessRows(SERVICES, [])
    rows = setRowScope(setRowLevel(rows, 'hr', 'viewer'), 'hr', true)
    rows = setRowLevel(rows, 'it', 'editor')
    expect(serializeAccess(rows)).toEqual([
      { service_key: 'hr', level: 'viewer', department_scope: true },
      { service_key: 'it', level: 'editor', department_scope: false },
    ])
    expect(serializeAccess(setRowLevel(rows, 'hr', ''))).toEqual([{ service_key: 'it', level: 'editor', department_scope: false }])
  })

  it('сравнение доступа не зависит от порядка и учитывает ограничение', () => {
    const a = [{ service_key: 'hr', level: 'viewer', department_scope: true }, { service_key: 'it', level: 'editor' }]
    const b = [{ service_key: 'it', level: 'editor', department_scope: false }, { service_key: 'hr', level: 'viewer', department_scope: true }]
    expect(sameAccess(a, b)).toBe(true)
    expect(sameAccess(a, [b[0], { ...b[1], department_scope: false }])).toBe(false)
    expect(sameAccess([], null)).toBe(true)
  })

  it('столбцы матрицы: «Нет» и три уровня', () => {
    expect(ACCESS_COLUMNS.map((c) => c.label)).toEqual(['Нет', 'Просмотр', 'Ввод данных', 'Управление'])
  })

  it('сводка доступа для таблицы в порядке служб; у администратора пусто', () => {
    const user = { role: 'user', access: [
      { service_key: 'it', level: 'viewer', department_scope: false },
      { service_key: 'hr', level: 'viewer', department_scope: true },
    ] }
    expect(accessSummary(user, SERVICES).map((c) => [c.short, c.label, c.scoped])).toEqual([
      ['Персонал', 'Просмотр', true],
      ['ИТ', 'Просмотр', false],
    ])
    expect(accessSummary({ role: 'admin', access: user.access }, SERVICES)).toEqual([])
  })
})

describe('пользователь', () => {
  it('логин: латиница, цифры и . _ @ -', () => {
    expect(isValidUsername('i.ivanov@corp')).toBe(true)
    expect(isValidUsername('ivan_petrov-2')).toBe(true)
    expect(isValidUsername('иван')).toBe(false)
    expect(isValidUsername('a b')).toBe(false)
    expect(isValidUsername('a')).toBe(false)
    expect(new RegExp(`^(?:${USERNAME_PATTERN})$`).test('a.b-c@d_e')).toBe(true)
  })

  it('инициалы и оттенок аватара', () => {
    expect(initials('Иванов Пётр Сергеевич')).toBe('ИП')
    expect(initials('')).toBe('?')
    expect(initials('Пользователь (просмотр)')).toBe('ПП')
    const tone = avatarTone('admin')
    expect(tone).toBeGreaterThanOrEqual(1)
    expect(tone).toBeLessThanOrEqual(7)
    expect(avatarTone('admin')).toBe(tone)
  })

  it('PATCH содержит только изменённые поля', () => {
    const user = { full_name: 'Иванов', email: null, position: 'Аналитик', phone: null, role: 'user', is_active: true,
      departments: [{ id: 2 }, { id: 5 }] }
    const form = profileForm(user)
    expect(profilePatch(user, form)).toEqual({})
    expect(profilePatch(user, { ...form, department_ids: [5, 2] })).toEqual({})
    expect(profilePatch(user, { ...form, email: ' a@b.ru ', is_active: false, department_ids: [2] }))
      .toEqual({ email: 'a@b.ru', is_active: false, department_ids: [2] })
    expect(profilePatch(user, { ...form, position: '' })).toEqual({ position: '' })
  })

  it('проверка формы до отправки', () => {
    expect(userFormErrors({ username: 'ivanov', full_name: 'Иванов', email: '' }, { isNew: true })).toEqual({})
    expect(userFormErrors({ username: 'иван', full_name: ' ', email: 'not-an-email' }, { isNew: true }))
      .toEqual({ username: expect.any(String), full_name: 'Укажите ФИО', email: 'Некорректный e-mail' })
    expect(userFormErrors({ full_name: 'Иванов', email: 'a@b.ru' })).toEqual({})
  })

  it('ошибки полей сервера сопоставляются с формой', () => {
    expect(formFieldErrors({ new_password: 'Слишком короткий', 'access.0.level': 'Недопустимо', email: 'Занят' }))
      .toEqual({ password: 'Слишком короткий', access: 'Недопустимо', email: 'Занят' })
    expect(formFieldErrors(undefined)).toEqual({})
  })
})

describe('журнал изменений', () => {
  it('подписи действий и объектов', () => {
    expect(['create', 'update', 'delete', 'login', 'password', 'import'].map(actionLabel))
      .toEqual(['Создание', 'Изменение', 'Удаление', 'Вход', 'Пароль', 'Загрузка'])
    expect(entityLabel('user_access')).toBe('Доступ пользователя')
    expect(entityLabel('traffic_light_rule')).toBe('Правило светофора')
    expect(entityLabel('unknown_thing')).toBe('unknown_thing')
  })

  it('значения: пусто, логические, числа, списки, роли, уровни', () => {
    expect(formatAuditValue(null)).toBe('—')
    expect(formatAuditValue(true)).toBe('Да')
    expect(formatAuditValue(1234.5).replace(/\s/g, ' ')).toBe('1 234,5')
    expect(formatAuditValue(['ИТ-служба', 'АХО'])).toBe('ИТ-служба, АХО')
    expect(formatAuditValue('admin', 'role')).toBe('Администратор')
    expect(formatAuditValue('lower_is_better', 'direction')).toBe('Меньше — лучше')
    expect(formatAuditValue('viewer (свои подразделения)')).toBe('Просмотр (свои подразделения)')
    expect(formatAuditValue('2026-11-01T08:18:11.095298')).toBe('2026-11-01 08:18')
  })

  it('«было → стало» показывает только изменённые поля', () => {
    const diff = auditDiff({ full_name: 'Иванов', role: 'user', is_active: true }, { full_name: 'Иванов', role: 'admin', is_active: false })
    expect(diff.mode).toBe('diff')
    expect(diff.unchanged).toBe(1)
    expect(diff.rows.map((r) => [r.label, r.beforeText, r.afterText])).toEqual([
      ['Роль', 'Пользователь', 'Администратор'],
      ['Активен', 'Да', 'Нет'],
    ])
  })

  it('вложенные объекты раскладываются по путям, цвета распознаются', () => {
    const before = { name: 'Своя', colors: { traffic_light: { green: '#00aa00', red: '#ff0000' }, charts: ['#111111', '#222222'] } }
    const after = { name: 'Своя', colors: { traffic_light: { green: '#00bb00', red: '#ff0000' }, charts: ['#111111', '#333333'] } }
    const diff = auditDiff(before, after)
    expect(diff.rows.map((r) => r.label)).toEqual(['Цвета · Светофор · Норма', 'Цвета · Графики'])
    expect(diff.rows[0].beforeColors).toEqual(['#00aa00'])
    expect(diff.rows[1].afterColors).toEqual(['#111111', '#333333'])
    expect(diff.unchanged).toBe(2)
  })

  it('создание и удаление показывают все поля одного снимка; подписи служб для доступа', () => {
    const created = auditDiff(null, { username: 'ivanov', access: { hr: 'viewer' } }, { labels: { hr: 'Служба персонала' } })
    expect(created.mode).toBe('after')
    expect(created.rows.map((r) => [r.label, r.beforeText, r.afterText])).toEqual([
      ['Логин', '—', 'ivanov'],
      ['Доступ · Служба персонала', '—', 'Просмотр'],
    ])
    expect(auditDiff({ name: 'АХО' }, null).mode).toBe('before')
    expect(auditDiff(null, null)).toEqual({ rows: [], unchanged: 0, mode: 'none' })
  })

  it('страницы пагинации с пропусками', () => {
    expect(pageRange(1, 1)).toEqual([1])
    expect(pageRange(1, 4)).toEqual([1, 2, '…', 4])
    expect(pageRange(5, 10)).toEqual([1, '…', 4, 5, 6, '…', 10])
    expect(pageRange(10, 10)).toEqual([1, '…', 9, 10])
  })
})

describe('светофор служб', () => {
  it('границы: пусто, запятая, нечисло', () => {
    expect(parseThreshold('')).toBe(null)
    expect(parseThreshold(null)).toBe(null)
    expect(parseThreshold('1,5')).toBe(1.5)
    expect(parseThreshold(12)).toBe(12)
    expect(parseThreshold('abc')).toBeNaN()
  })

  it('проверка порядка границ по направлению — как на сервере', () => {
    expect(ruleProblem({ direction: 'lower_is_better', green_threshold: 10, yellow_threshold: 20, enabled: true })).toBe('')
    expect(ruleProblem({ direction: 'lower_is_better', green_threshold: 30, yellow_threshold: 20, enabled: true })).toMatch(/не больше/)
    expect(ruleProblem({ direction: 'higher_is_better', green_threshold: 10, yellow_threshold: 20, enabled: true })).toMatch(/не меньше/)
    expect(ruleProblem({ direction: 'higher_is_better', green_threshold: '', yellow_threshold: 20, enabled: true })).toMatch(/обе границы/)
    expect(ruleProblem({ direction: 'higher_is_better', green_threshold: '', yellow_threshold: '', enabled: false })).toBe('')
    expect(ruleProblem({ direction: 'higher_is_better', green_threshold: 'x', yellow_threshold: 1, enabled: false })).toMatch(/числами/)
  })

  it('тело запроса и признак изменений', () => {
    const saved = { direction: 'lower_is_better', green_threshold: 180, yellow_threshold: 220, enabled: true }
    expect(ruleBody({ ...saved, green_threshold: '175,5' })).toEqual({ ...saved, green_threshold: 175.5 })
    expect(ruleDirty({ ...saved, green_threshold: '180' }, saved)).toBe(false)
    expect(ruleDirty({ ...saved, enabled: false }, saved)).toBe(true)
  })

  it('зоны шкалы по возрастанию значения', () => {
    expect(ruleZones({ direction: 'lower_is_better', green_threshold: 180, yellow_threshold: 220 }, 'шт.').map((z) => [z.light, z.text.replace(/\s/g, ' ')]))
      .toEqual([['green', '≤ 180 шт.'], ['yellow', '≤ 220 шт.'], ['red', '> 220 шт.']])
    expect(ruleZones({ direction: 'higher_is_better', green_threshold: 85, yellow_threshold: 65 }, '%').map((z) => [z.light, z.text]))
      .toEqual([['red', '< 65%'], ['yellow', '≥ 65%'], ['green', '≥ 85%']])
    expect(ruleZones({ direction: 'higher_is_better', green_threshold: null, yellow_threshold: 65 })).toEqual([])
  })

  it('группы правил в исходном порядке', () => {
    const groups = groupRules([{ metric_key: 'a', group: 'Нагрузка' }, { metric_key: 'b', group: 'Поток' }, { metric_key: 'c', group: 'Нагрузка' }, { metric_key: 'd' }])
    expect(groups.map((g) => [g.name, g.items.map((i) => i.metric_key)])).toEqual([
      ['Нагрузка', ['a', 'c']], ['Поток', ['b']], ['Прочее', ['d']],
    ])
  })
})

describe('палитры и система', () => {
  it('палитра дополняется до 7 цветов графиков и приводится к #rrggbb', () => {
    const p = normalizePalette({ traffic_light: { green: '#0A0' }, charts: ['#123456'], brand: { primary: '#ABCDEF' } })
    expect(p.traffic_light.green).toBe('#00aa00')
    expect(p.traffic_light.red).toMatch(/^#[0-9a-f]{6}$/)
    expect(p.charts).toHaveLength(7)
    expect(p.charts[0]).toBe('#123456')
    expect(p.brand.primary).toBe('#abcdef')
    expect(paletteProblem(p)).toBe('')
    expect(paletteProblem({ ...p, charts: ['#12'] })).toBe('Некорректный цвет: #12')
  })

  it('длительность в минутах', () => {
    expect(formatMinutes(240)).toBe('4 часа')
    expect(formatMinutes(90)).toBe('1 ч 30 мин')
    expect(formatMinutes(45)).toBe('45 мин')
    expect(formatMinutes(null)).toBe('—')
  })
})
