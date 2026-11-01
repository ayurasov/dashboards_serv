import { describe, expect, it } from 'vitest'
import {
  actionLabel,
  auditDiff,
  avatarTone,
  createUserBody,
  departmentParts,
  entityLabel,
  formatAuditValue,
  formatMinutes,
  formFieldErrors,
  groupRules,
  initials,
  isValidUsername,
  managerLabel,
  needsAccess,
  newUserForm,
  normalizePalette,
  pageRange,
  paletteProblem,
  parseThreshold,
  personalServices,
  profileForm,
  profilePatch,
  resetAction,
  ruleBody,
  ruleDirty,
  ruleProblem,
  ruleZones,
  sortServices,
  summaryParts,
  USER_FILTERS,
  userBadges,
  userHistory,
  USERNAME_PATTERN,
  userFormErrors,
  usersParams,
} from './admin'

const SERVICES = [
  { key: 'hr', title: 'Служба персонала', short_title: 'Персонал', has_dashboard: true },
  { key: 'apparat_gd', title: 'Аппарат генерального директора', short_title: 'Аппарат ГД', has_dashboard: false },
  { key: 'tech', title: 'Техническая поддержка', short_title: 'Техподдержка', has_dashboard: true },
  { key: 'it', title: 'ИТ-служба', short_title: 'ИТ', has_dashboard: false },
]

describe('службы', () => {
  it('службы с дашбордом идут первыми, порядок внутри групп сохраняется', () => {
    expect(sortServices(SERVICES).map((s) => s.key)).toEqual(['hr', 'tech', 'apparat_gd', 'it'])
  })
})

describe('список пользователей', () => {
  it('фильтры страницы → параметры запроса', () => {
    expect(usersParams(USER_FILTERS)).toEqual({ search: '', role: '', status: '', department_id: '', profile_id: '', auth_source: '' })
    expect(usersParams({ ...USER_FILTERS, search: '  иван ', department: 'none', profile: '3', auth: 'ldap', status: 'no_access' }))
      .toEqual({ search: 'иван', role: '', status: 'no_access', department_id: 'none', profile_id: '3', auth_source: 'ldap' })
  })

  it('сводка в шапке: шесть частей со склонениями и фильтром по щелчку', () => {
    const parts = summaryParts({ total: 12, active: 11, disabled: 1, no_access: 2, ldap: 3, admins: 1 })
    expect(parts.map((p) => `${p.count} ${p.label}`)).toEqual([
      '12 всего', '11 активных', '1 отключено', '2 без доступа', '3 по домену', '1 администратор',
    ])
    expect(parts.find((p) => p.key === 'no_access').filter).toEqual({ status: 'no_access' })
    expect(parts.find((p) => p.key === 'ldap').filter).toEqual({ auth: 'ldap' })
    expect(summaryParts({ total: 2, active: 1, admins: 2 }).at(-1).label).toBe('администратора')
    expect(summaryParts(null)).toEqual([])
  })

  it('метки строки: «Вы», администратор, домен, без пароля, временный пароль', () => {
    const keys = (u, me) => userBadges(u, me).map((b) => b.key)
    expect(keys({ id: 1, role: 'admin', auth_source: 'local', has_password: true }, 1)).toEqual(['self', 'admin'])
    expect(keys({ id: 2, role: 'user', auth_source: 'ldap', has_password: false }, 1)).toEqual(['ldap'])
    expect(keys({ id: 3, role: 'user', auth_source: 'local', has_password: false }, 1)).toEqual(['no_password'])
    expect(keys({ id: 4, role: 'user', auth_source: 'local', has_password: true, must_change_password: true }, 1)).toEqual(['temporary'])
    expect(userBadges(null)).toEqual([])
  })

  it('«Выдать доступ» — только тем, кто не может войти', () => {
    expect(needsAccess({ status: 'no_access' })).toBe(true)
    expect(needsAccess({ status: 'active' })).toBe(false)
    expect(needsAccess({ status: 'disabled' })).toBe(false)
  })

  it('подразделение: название и путь до него; руководитель', () => {
    expect(departmentParts({ id: 3, name: 'Техническая служба', path: 'АЛМИ Партнер / Техническая дирекция / Техническая служба' }))
      .toEqual({ name: 'Техническая служба', parent: 'АЛМИ Партнер / Техническая дирекция', path: 'АЛМИ Партнер / Техническая дирекция / Техническая служба' })
    expect(departmentParts({ id: 8, name: 'АЛМИ Партнер', path: 'АЛМИ Партнер' }).parent).toBe('')
    expect(departmentParts(null)).toEqual({ name: '', parent: '', path: '' })
    expect(managerLabel({ full_name: 'Соколова Мария Игоревна', source: 'structure' })).toBe('Соколова Мария Игоревна')
    expect(managerLabel({ full_name: 'Громов Андрей', source: 'explicit' })).toBe('Громов Андрей · назначен явно')
    expect(managerLabel(null)).toBe('')
  })

  it('сброс пароля: у доменной учётной записи — перевод на пароль системы', () => {
    expect(resetAction({ full_name: 'Иванов', username: 'ivanov', auth_source: 'local' }).label).toBe('Сбросить пароль')
    const ldap = resetAction({ full_name: 'Иванов', username: 'ivanov', auth_source: 'ldap' })
    expect(ldap.label).toBe('Перевести на пароль системы')
    expect(ldap.message).toContain('учётной записи домена')
  })

  it('личные уровни служб из строк доступа; у администратора — пусто', () => {
    const user = { role: 'user', access: [{ service_key: 'tech', level: 'manager' }, { service_key: 'hr', level: 'none' }] }
    expect(personalServices(user, SERVICES).map((r) => `${r.title}: ${r.label}`)).toEqual(['Техподдержка: управление', 'Персонал: нет доступа'])
    expect(personalServices({ ...user, role: 'admin' }, SERVICES)).toEqual([])
  })

  it('тело создания: способ входа, профиль, личные службы; роль и полномочия — только администратор', () => {
    const form = { ...newUserForm(), username: ' i.ivanov ', full_name: ' Иванов Иван ', profile_id: 5, department_id: 12,
      capabilities: ['org.manage'], services: { tech: 'viewer', hr: '' }, password: 'secret12' }
    expect(createUserBody(form)).toEqual({
      username: 'i.ivanov', full_name: 'Иванов Иван', email: '', position: null, phone: null, role: 'user',
      access_method: 'password', password: 'secret12', department_id: 12, profile_id: 5, capabilities: ['org.manage'],
      access: [{ service_key: 'tech', level: 'viewer' }],
    })
    expect(createUserBody({ ...form, access_method: 'none' }).password).toBeNull()
    const manager = createUserBody({ ...form, role: 'admin' }, { isAdmin: false })
    expect(manager.role).toBe('user')
    expect(manager.capabilities).toEqual([])
    expect(createUserBody({ ...form, role: 'admin' }).access).toEqual([])
  })

  it('журнал пользователя: свои записи и входы, без повторов, новые сверху', () => {
    const lists = [
      [{ id: 1, entity_type: 'user', entity_id: '7', occurred_at: '2026-11-01T10:00:00' }, { id: 2, entity_type: 'user', entity_id: '17', occurred_at: '2026-11-01T11:00:00' }],
      [{ id: 3, entity_type: 'user_access', entity_id: '7', occurred_at: '2026-11-01T12:00:00' }, { id: 1, entity_type: 'user', entity_id: '7', occurred_at: '2026-11-01T10:00:00' }],
      [{ id: 4, entity_type: 'session', entity_id: null, occurred_at: '2026-11-01T09:00:00' }],
    ]
    expect(userHistory(lists, 7).map((e) => e.id)).toEqual([3, 1, 4])
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
      department: { id: 2, name: 'ИТ', path: 'АЛМИ / ИТ' }, capabilities: ['users.manage'] }
    const form = profileForm(user)
    expect(form.department_id).toBe(2)
    expect(profilePatch(user, form)).toEqual({})
    expect(profilePatch(user, { ...form, email: ' a@b.ru ', is_active: false, department_id: 5 }))
      .toEqual({ email: 'a@b.ru', is_active: false, department_id: 5 })
    expect(profilePatch(user, { ...form, department_id: null })).toEqual({ department_id: null })
    expect(profilePatch(user, { ...form, position: '' })).toEqual({ position: '' })
    expect(profilePatch(user, { ...form, capabilities: ['users.manage', 'org.manage'] })).toEqual({ capabilities: ['org.manage', 'users.manage'] })
  })

  it('проверка формы до отправки', () => {
    expect(userFormErrors({ username: 'ivanov', full_name: 'Иванов', email: '' }, { isNew: true })).toEqual({})
    expect(userFormErrors({ username: 'иван', full_name: ' ', email: 'not-an-email' }, { isNew: true }))
      .toEqual({ username: expect.any(String), full_name: 'Укажите ФИО', email: 'Некорректный e-mail' })
    expect(userFormErrors({ full_name: 'Иванов', email: 'a@b.ru' })).toEqual({})
    expect(userFormErrors({ username: 'ivanov', full_name: 'Иванов', email: '', access_method: 'ldap' }, { isNew: true }).email)
      .toContain('входа по домену')
  })

  it('ошибки полей сервера сопоставляются с формой', () => {
    expect(formFieldErrors({ new_password: 'Слишком короткий', 'access.0.level': 'Недопустимо', email: 'Занят' }))
      .toEqual({ password: 'Слишком короткий', access: 'Недопустимо', email: 'Занят' })
    expect(formFieldErrors(undefined)).toEqual({})
  })
})

describe('журнал изменений', () => {
  it('подписи действий и объектов', () => {
    expect(['create', 'update', 'delete', 'login', 'password', 'import', 'grant'].map(actionLabel))
      .toEqual(['Создание', 'Изменение', 'Удаление', 'Вход', 'Пароль', 'Загрузка', 'Выдача доступа'])
    expect(entityLabel('user_access')).toBe('Доступ пользователя')
    expect(entityLabel('access_profile')).toBe('Профиль доступа')
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
    expect(formatAuditValue('none')).toBe('Нет доступа')
    expect(formatAuditValue('branch', 'org_scope')).toBe('Своя ветка структуры')
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
