import { describe, expect, it } from 'vitest'
import {
  accessProfileBody,
  accessProfileErrors,
  accessProfileForm,
  classesLabel,
  clearOverride,
  computeEffective,
  deniedServices,
  depthLabel,
  depthOptions,
  dimensionValueLabel,
  dimensionView,
  effectiveRows,
  grantViewAll,
  headedUnits,
  INDIVIDUAL_DEFAULTS,
  normalizeClasses,
  plainAccess,
  policyBody,
  policyDirty,
  policyDraft,
  profileComparison,
  profileFacts,
  scopeFor,
  scopeUnits,
  scopeWarning,
  serviceRowsBody,
  serviceView,
  setOverride,
  setServiceLevel,
  setServiceScope,
  sourceLabel,
  startOverride,
  suggestProfileKey,
  toggleClass,
  userAccess,
} from './access'

const SERVICES = [
  { key: 'hr', title: 'Служба персонала', short_title: 'Персонал', has_dashboard: true },
  { key: 'tech', title: 'Техническая поддержка', short_title: 'Техподдержка', has_dashboard: true },
  { key: 'project_product', title: 'Проектный и продуктовый офис', short_title: 'Партнёрства', has_dashboard: true },
  { key: 'it', title: 'ИТ-служба', short_title: 'ИТ', has_dashboard: false },
]

const HEAD = {
  id: 3, key: 'head', name: 'Руководитель подразделения', is_system: true, service_levels: {},
  org_scope: 'branch', data_classes: ['operational', 'personal'], drill_depth: null, can_view_records: true, can_export: true,
}
const EXECUTIVE = {
  id: 1, key: 'executive', name: 'Высшее руководство', is_system: true, service_levels: { hr: 'viewer', tech: 'viewer', project_product: 'viewer' },
  org_scope: 'company', data_classes: ['operational', 'personal', 'financial'], drill_depth: 1, can_view_records: false, can_export: true, users_count: 1,
}
const EMPLOYEE = {
  id: 5, key: 'employee', name: 'Сотрудник', is_system: true, service_levels: {},
  org_scope: 'unit', data_classes: ['operational'], drill_depth: 0, can_view_records: false, can_export: false, users_count: 4,
}

// Демонстрационная структура: компания → дирекция → служба → группы
const DEPARTMENTS = [
  { id: 8, parent_id: null, name: 'АЛМИ Партнер', path: 'АЛМИ Партнер', heads: [{ user_id: 7 }] },
  { id: 11, parent_id: 8, name: 'Техническая дирекция', path: 'АЛМИ Партнер / Техническая дирекция', heads: [{ user_id: 8 }] },
  { id: 3, parent_id: 11, name: 'Техническая служба', path: 'АЛМИ Партнер / Техническая дирекция / Техническая служба', heads: [{ user_id: 3 }] },
  { id: 12, parent_id: 3, name: 'Группа AlterOS', path: 'АЛМИ Партнер / Техническая дирекция / Техническая служба / Группа AlterOS', heads: [] },
  { id: 2, parent_id: 11, name: 'ИТ-служба', path: 'АЛМИ Партнер / Техническая дирекция / ИТ-служба', heads: [{ user_id: 6 }] },
  { id: 6, parent_id: 8, name: 'Проектная служба', path: 'АЛМИ Партнер / Проектная служба', heads: [] },
]

describe('подписи значений', () => {
  it('глубина детализации: без ограничения, вершина, уровни со склонением', () => {
    expect(depthLabel(null)).toBe('Без ограничения')
    expect(depthLabel(0)).toBe('Только вершина области')
    expect(depthLabel(1)).toBe('1 уровень вниз')
    expect(depthLabel(3)).toBe('3 уровня вниз')
    expect(depthLabel(5)).toBe('5 уровней вниз')
    const options = depthOptions(9)
    expect(options).toHaveLength(11)
    expect(options[0]).toEqual({ value: null, label: 'Без ограничения' })
    expect(options[1].label).toBe('0 — только вершина области')
  })

  it('классы данных: операционные всегда, порядок справочника', () => {
    expect(normalizeClasses(['financial'])).toEqual(['operational', 'financial'])
    expect(normalizeClasses(null)).toEqual(['operational'])
    expect(classesLabel(['operational'])).toBe('Только операционные')
    expect(classesLabel(['personal', 'operational'])).toBe('Операционные, персональные')
    expect(toggleClass(['operational', 'personal'], 'personal')).toEqual(['operational'])
    expect(toggleClass(['operational'], 'financial')).toEqual(['operational', 'financial'])
    expect(toggleClass(['personal'], 'operational')).toEqual(['operational', 'personal'])
  })

  it('значения измерений и источники', () => {
    expect(dimensionValueLabel('org_scope', 'branch')).toBe('Своя ветка структуры')
    expect(dimensionValueLabel('can_view_records', false)).toBe('Только дашборды и сводки')
    expect(dimensionValueLabel('can_export', true)).toBe('Разрешена')
    expect(sourceLabel('personal')).toBe('задано лично')
    expect(sourceLabel('profile', 'Сотрудник')).toBe('из профиля «Сотрудник»')
    expect(sourceLabel('default')).toBe('по умолчанию')
    expect(sourceLabel('admin')).toBe('роль администратора')
  })
})

describe('действующий доступ (как на сервере)', () => {
  it('без профиля — по умолчанию как в 0.1.0: вся компания, все классы, записи и выгрузка', () => {
    const eff = computeEffective({ services: [{ service_key: 'hr', level: 'viewer' }] })
    expect(eff).toMatchObject({ ...INDIVIDUAL_DEFAULTS, services: { hr: 'viewer' }, profile_name: null })
    expect(eff.sources).toMatchObject({ org_scope: 'default', can_export: 'default', 'service:hr': 'personal' })
  })

  it('профиль плюс личные значения: личное перекрывает профиль', () => {
    const eff = computeEffective({ profile: EMPLOYEE, overrides: { can_export: true, drill_depth: null }, services: { tech: { level: 'viewer', org_scope: '' } } })
    expect(eff.org_scope).toBe('unit')
    expect(eff.can_export).toBe(true)
    expect(eff.drill_depth).toBeNull()
    expect(eff.can_view_records).toBe(false)
    expect(eff.services).toEqual({ tech: 'viewer' })
    expect(eff.sources).toMatchObject({ org_scope: 'profile', can_export: 'personal', drill_depth: 'personal', 'service:tech': 'personal' })
    expect(eff.profile_name).toBe('Сотрудник')
  })

  it('«Нет доступа» лично запрещает службу из профиля; своя область службы', () => {
    const eff = computeEffective({
      profile: EXECUTIVE,
      services: [{ service_key: 'hr', level: 'none' }, { service_key: 'tech', level: 'editor', org_scope: 'branch' }],
    })
    expect(eff.services).toEqual({ tech: 'editor', project_product: 'viewer' })
    expect(eff.service_scopes).toEqual({ tech: 'branch' })
    expect(eff.sources['service:hr']).toBe('personal')
    expect(eff.sources['service:project_product']).toBe('profile')
    expect(deniedServices(eff, SERVICES)).toEqual([{ key: 'hr', title: 'Служба персонала' }])
    expect(scopeFor(eff, 'tech')).toBe('branch')
    expect(scopeFor(eff, 'hr')).toBe('company')
  })

  it('администратор — всё, источник «роль администратора»', () => {
    const eff = computeEffective({ isAdmin: true, serviceKeys: ['hr', 'tech'] })
    expect(eff.services).toEqual({ hr: 'manager', tech: 'manager' })
    expect(eff.sources.org_scope).toBe('admin')
  })

  it('доступ текущего пользователя: effective_access, иначе — из строк 0.1.0', () => {
    expect(userAccess(null)).toBeNull()
    expect(userAccess({ effective_access: { org_scope: 'unit' } }).org_scope).toBe('unit')
    const legacy = userAccess({ role: 'user', access: [{ service_key: 'hr', level: 'viewer' }] })
    expect(legacy.services).toEqual({ hr: 'viewer' })
    expect(legacy.can_export).toBe(true)
  })
})

describe('область структуры', () => {
  it('вся компания — null; своё подразделение — вершины; своя ветка — с вложенными', () => {
    expect(scopeUnits(DEPARTMENTS, { scope: 'company', homeId: 3 })).toBeNull()
    expect(scopeUnits(DEPARTMENTS, { scope: 'unit', homeId: 3 }).map((u) => u.id)).toEqual([3])
    expect(scopeUnits(DEPARTMENTS, { scope: 'branch', homeId: 3 }).map((u) => u.id)).toEqual([3, 12])
    // Руководимые подразделения и дополнительные — тоже вершины
    expect(scopeUnits(DEPARTMENTS, { scope: 'branch', userId: 8 }).map((u) => u.name))
      .toEqual(['Техническая дирекция', 'ИТ-служба', 'Техническая служба', 'Группа AlterOS'])
    expect(scopeUnits(DEPARTMENTS, { scope: 'unit', homeId: 12, extraIds: [6, 999] }).map((u) => u.id)).toEqual([6, 12])
    expect(scopeUnits(DEPARTMENTS, { scope: 'unit' })).toEqual([])
    expect(headedUnits(DEPARTMENTS, 3).map((d) => d.id)).toEqual([3])
  })

  it('предупреждение: область уже компании без вершин', () => {
    expect(scopeWarning({ scopes: ['unit'] })).toContain('нет ни основного')
    expect(scopeWarning({ scopes: ['company', 'branch'] })).not.toBe('')
    expect(scopeWarning({ scopes: ['unit'], homeId: 3 })).toBe('')
    expect(scopeWarning({ scopes: ['branch'], extraIds: [6] })).toBe('')
    expect(scopeWarning({ scopes: ['unit'], headedCount: 1 })).toBe('')
    expect(scopeWarning({ scopes: ['company'] })).toBe('')
  })
})

describe('черновик доступа пользователя', () => {
  const POLICY = {
    profile: { id: 5, key: 'employee', name: 'Сотрудник' },
    overrides: { can_export: true },
    services: [{ service_key: 'tech', level: 'viewer', org_scope: null }],
    extra_units: [{ id: 6, name: 'Проектная служба', path: 'АЛМИ Партнер / Проектная служба' }],
  }

  it('из ответа API и без изменений — пустое тело', () => {
    const draft = policyDraft(POLICY)
    expect(draft).toEqual({ profileId: 5, overrides: { can_export: true }, services: { tech: { level: 'viewer', org_scope: '' } }, extraUnitIds: [6] })
    expect(policyBody(draft, policyDraft(POLICY))).toEqual({})
    expect(policyDirty(draft, policyDraft(POLICY))).toBe(false)
  })

  it('в теле только изменённые части', () => {
    const saved = policyDraft(POLICY)
    const draft = policyDraft(POLICY)
    draft.profileId = null
    expect(policyBody(draft, saved)).toEqual({ profile_id: null })
    draft.overrides = clearOverride(draft.overrides, 'can_export')
    draft.extraUnitIds = [6, 2]
    expect(policyBody(draft, saved)).toEqual({ profile_id: null, overrides: {}, extra_unit_ids: [2, 6] })
    draft.services = setServiceLevel(draft.services, 'hr', 'none')
    expect(policyBody(draft, saved).services).toEqual([
      { service_key: 'hr', level: 'none', org_scope: null },
      { service_key: 'tech', level: 'viewer', org_scope: null },
    ])
  })

  it('«Задать лично» начинается со значения профиля и не меняет доступ; «Вернуть как в профиле»', () => {
    let overrides = startOverride({}, 'org_scope', HEAD)
    expect(overrides).toEqual({ org_scope: 'branch' })
    expect(dimensionView('org_scope', overrides, HEAD)).toMatchObject({ personal: true, differs: false, value: 'branch', inheritedText: 'Своя ветка структуры' })
    overrides = setOverride(overrides, 'org_scope', 'company')
    expect(dimensionView('org_scope', overrides, HEAD)).toMatchObject({ personal: true, differs: true, source: 'personal', valueText: 'Вся компания' })
    overrides = clearOverride(overrides, 'org_scope')
    expect(dimensionView('org_scope', overrides, HEAD)).toMatchObject({ personal: false, source: 'profile', value: 'branch' })
    // Без профиля — значение по умолчанию
    expect(dimensionView('drill_depth', {}, null)).toMatchObject({ source: 'default', inheritedSource: 'default', valueText: 'Без ограничения' })
    // «Без ограничения» лично поверх профиля — ключ есть, значение null
    expect(dimensionView('drill_depth', { drill_depth: null }, EXECUTIVE)).toMatchObject({ personal: true, differs: true, value: null })
    expect(setOverride({}, 'data_classes', ['financial'])).toEqual({ data_classes: ['operational', 'financial'] })
  })

  it('строки служб: как в профиле, лично, запрет; своя область фиксирует уровень лично', () => {
    const draft = { services: {} }
    expect(serviceView(SERVICES[0], draft, EXECUTIVE)).toMatchObject({ profileLevel: 'viewer', personalLevel: '', level: 'viewer', source: 'profile' })
    expect(serviceView(SERVICES[0], draft, HEAD)).toMatchObject({ profileLevel: null, level: null, source: 'none' })
    let services = setServiceLevel({}, 'hr', 'none')
    expect(serviceView(SERVICES[0], { services }, EXECUTIVE)).toMatchObject({ personalLevel: 'none', level: null, source: 'personal' })
    services = setServiceScope({}, 'hr', 'unit', EXECUTIVE)
    expect(services).toEqual({ hr: { level: 'viewer', org_scope: 'unit' } })
    expect(setServiceScope({}, 'hr', 'unit', HEAD)).toEqual({})
    expect(setServiceLevel(services, 'hr', '')).toEqual({})
    expect(setServiceLevel(services, 'hr', 'none')).toEqual({ hr: { level: 'none', org_scope: '' } })
    expect(serviceRowsBody({ tech: { level: 'editor', org_scope: 'branch' }, hr: { level: '', org_scope: '' } }))
      .toEqual([{ service_key: 'tech', level: 'editor', org_scope: 'branch' }])
  })

  it('«Просмотр всех дашбордов» не понижает выданные уровни', () => {
    const next = grantViewAll({ tech: { level: 'manager', org_scope: '' } }, SERVICES, HEAD)
    expect(next).toEqual({ tech: { level: 'manager', org_scope: '' }, hr: { level: 'viewer', org_scope: '' }, project_product: { level: 'viewer', org_scope: '' } })
    expect(grantViewAll({}, SERVICES, EXECUTIVE)).toEqual({})
  })
})

describe('сводка действующего доступа', () => {
  it('строки служб и измерений с источниками', () => {
    const eff = computeEffective({ profile: EMPLOYEE, overrides: { can_export: true }, services: { tech: { level: 'viewer' } } })
    const { services, dimensions } = effectiveRows(eff, SERVICES)
    expect(services).toEqual([expect.objectContaining({ key: 'tech', short_title: 'Техподдержка', levelText: 'Просмотр', sourceText: 'задано лично' })])
    expect(dimensions.map((d) => [d.key, d.valueText, d.sourceText])).toEqual([
      ['org_scope', 'Своё подразделение', 'из профиля «Сотрудник»'],
      ['data_classes', 'Только операционные', 'из профиля «Сотрудник»'],
      ['drill_depth', 'Только вершина области', 'из профиля «Сотрудник»'],
      ['can_view_records', 'Только дашборды и сводки', 'из профиля «Сотрудник»'],
      ['can_export', 'Разрешена', 'задано лично'],
    ])
  })

  it('«Мой доступ» простыми словами', () => {
    const plain = plainAccess(computeEffective({ profile: EMPLOYEE, services: { tech: { level: 'viewer' } } }), SERVICES)
    expect(plain.profile).toBe('Сотрудник')
    expect(plain.services.map((s) => `${s.title}: ${s.levelText}`)).toEqual(['Техническая поддержка: Просмотр'])
    const lines = Object.fromEntries(plain.lines.map((l) => [l.key, l]))
    expect(lines.org_scope.text).toContain('только своих подразделений')
    expect(lines.data_classes.text).toContain('Персональные данные (ФИО, должности, причины увольнения) скрыты')
    expect(lines.can_view_records.ok).toBe(false)
    expect(lines.can_export.text).toContain('скрыты')
    expect(lines.drill_depth.text).toContain('без раскрытия')
    expect(plainAccess(computeEffective({ profile: HEAD }), SERVICES).lines.find((l) => l.key === 'drill_depth').text).toContain('любую глубину')
  })
})

describe('профили доступа', () => {
  it('ключ из названия и проверка формы', () => {
    expect(suggestProfileKey('Финансовый контролёр')).toBe('finansovyy-kontroler')
    expect(suggestProfileKey('42')).toBe('')
    expect(accessProfileErrors({ key: 'Fin', name: '' }, { isNew: true })).toEqual({ key: expect.any(String), name: 'Укажите название' })
    expect(accessProfileErrors({ key: 'fin_ctl', name: 'Финансы' }, { isNew: true })).toEqual({})
    expect(accessProfileErrors({ key: '', name: 'Финансы' })).toEqual({})
  })

  it('создание — все поля; изменение — только изменённые', () => {
    const form = accessProfileForm(null)
    expect(form).toMatchObject({ org_scope: 'unit', data_classes: ['operational'], drill_depth: null, can_view_records: true, can_export: true })
    Object.assign(form, { key: 'fin', name: '  Финансовый  контролёр ', org_scope: 'company', data_classes: ['financial'], service_levels: { hr: 'viewer', tech: '' } })
    expect(accessProfileBody(form)).toEqual({
      key: 'fin', name: 'Финансовый контролёр', description: '', sort_order: 100, org_scope: 'company',
      data_classes: ['operational', 'financial'], drill_depth: null, can_view_records: true, can_export: true, service_levels: { hr: 'viewer' },
    })
    const edit = accessProfileForm(EXECUTIVE)
    expect(accessProfileBody(edit, EXECUTIVE)).toEqual({})
    edit.drill_depth = 3
    edit.service_levels = { ...edit.service_levels, hr: 'manager' }
    expect(accessProfileBody(edit, EXECUTIVE)).toEqual({ drill_depth: 3, service_levels: { hr: 'manager', tech: 'viewer', project_product: 'viewer' } })
  })

  it('сравнение профилей: столбцы и строки «кто что видит»', () => {
    const { columns, rows } = profileComparison([EXECUTIVE, EMPLOYEE], SERVICES)
    expect(columns.map((c) => c.name)).toEqual(['Высшее руководство', 'Сотрудник', 'Индивидуальная настройка'])
    const byKey = Object.fromEntries(rows.map((r) => [r.key, r.cells.map((c) => c.text)]))
    expect(byKey.org_scope).toEqual(['Вся компания', 'Своё подразделение', 'Вся компания'])
    expect(byKey['class:financial']).toEqual(['Да', 'Нет', 'Да'])
    expect(byKey.drill_depth).toEqual(['1', '0', 'Без ограничения'])
    expect(byKey.can_view_records).toEqual(['Нет', 'Нет', 'Да'])
    expect(byKey['service:hr']).toEqual(['Просмотр', '—', 'Лично'])
    expect(rows.some((r) => r.key === 'service:it')).toBe(false)
  })

  it('факты профиля для карточки', () => {
    const facts = Object.fromEntries(profileFacts(EXECUTIVE, SERVICES).map((f) => [f.key, f.text]))
    expect(facts.services).toBe('Просмотр всех дашбордов')
    expect(facts.can_view_records).toBe('Только дашборды')
    expect(Object.fromEntries(profileFacts(HEAD, SERVICES).map((f) => [f.key, f.text])).services).toBe('Выдаются лично')
    const mixed = profileFacts({ ...HEAD, service_levels: { tech: 'manager' } }, SERVICES).find((f) => f.key === 'services')
    expect(mixed.text).toBe('Техподдержка — управление')
  })
})
