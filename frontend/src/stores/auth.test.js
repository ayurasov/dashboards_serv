import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAuthStore } from './auth'
import { navItemAllowed, SERVICE_NAV } from '@/router/navigation'

const EMPLOYEE = {
  id: 9, username: 'engineer', role: 'user', capabilities: [], auth_source: 'local',
  access: [{ service_key: 'tech', level: 'viewer', org_scope: null }],
  effective_access: {
    is_admin: false, profile_key: 'employee', profile_name: 'Сотрудник', services: { tech: 'viewer' }, service_scopes: {},
    org_scope: 'unit', data_classes: ['operational'], drill_depth: 0, can_view_records: false, can_export: false,
    sources: { org_scope: 'profile', 'service:tech': 'personal' },
  },
}
const IT_HEAD = {
  id: 6, username: 'it_viewer', role: 'user', capabilities: ['users.manage'], auth_source: 'ldap',
  effective_access: {
    is_admin: false, profile_key: 'head', profile_name: 'Руководитель подразделения', services: { hr: 'viewer', it: 'viewer' },
    service_scopes: { hr: 'branch' }, org_scope: 'company', data_classes: ['operational', 'personal'], drill_depth: null,
    can_view_records: true, can_export: true, sources: {},
  },
}

describe('права текущего пользователя', () => {
  let auth
  beforeEach(() => {
    setActivePinia(createPinia())
    auth = useAuthStore()
  })

  it('без входа — ничего', () => {
    expect(auth.can('hr')).toBe(false)
    expect(auth.canRecords).toBe(false)
    expect(auth.canExport).toBe(false)
    expect(auth.profileName).toBe('')
  })

  it('сотрудник: уровни служб, без записей и выгрузки, только операционные данные', () => {
    auth.setUser(EMPLOYEE)
    expect(auth.level('tech')).toBe('viewer')
    expect(auth.can('tech')).toBe(true)
    expect(auth.can('tech', 'editor')).toBe(false)
    expect(auth.can('hr')).toBe(false)
    expect(auth.canRecords).toBe(false)
    expect(auth.canExport).toBe(false)
    expect(auth.allows('operational')).toBe(true)
    expect(auth.allows('personal')).toBe(false)
    expect(auth.scope).toBe('unit')
    expect(auth.drillDepth).toBe(0)
    expect(auth.departmentScoped('tech')).toBe(true)
    expect(auth.profileName).toBe('Сотрудник')
    expect(auth.denial({ service: 'tech', records: true })).toBe('records')
    expect(auth.denial({ service: 'hr' })).toBe('service')
    expect(auth.denial({ service: 'tech' })).toBe('')
  })

  it('своя область службы; полномочия; вход по домену', () => {
    auth.setUser(IT_HEAD)
    expect(auth.scope).toBe('company')
    expect(auth.scopeFor('hr')).toBe('branch')
    expect(auth.departmentScoped('hr')).toBe(true)
    expect(auth.departmentScoped('it')).toBe(false)
    expect(auth.hasCapability('users.manage')).toBe(true)
    expect(auth.hasCapability('org.manage')).toBe(false)
    expect(auth.isDomainUser).toBe(true)
    expect(auth.allows('financial')).toBe(false)
    expect(auth.denial({ service: 'hr', records: true, dataClass: 'personal' })).toBe('')
    expect(auth.drillDepth).toBeNull()
  })

  it('администратор — всё', () => {
    auth.setUser({ id: 1, role: 'admin', capabilities: [], effective_access: { is_admin: true, services: {} } })
    expect(auth.can('legal', 'manager')).toBe(true)
    expect(auth.canRecords && auth.canExport).toBe(true)
    expect(auth.allows('financial')).toBe(true)
    expect(auth.hasCapability('org.manage')).toBe(true)
    expect(auth.departmentScoped()).toBe(false)
    expect(auth.profileName).toBe('Администратор')
  })

  it('сервер 0.1.0 без effective_access: права из строк доступа', () => {
    auth.setUser({ id: 2, role: 'user', access: [{ service_key: 'hr', level: 'editor', department_scope: false }] })
    expect(auth.can('hr', 'editor')).toBe(true)
    expect(auth.canRecords).toBe(true)
    expect(auth.canExport).toBe(true)
  })

  it('меню: реестры скрыты без исходных записей, приёмы и увольнения — без персональных данных', () => {
    auth.setUser(EMPLOYEE)
    const visible = (service) => SERVICE_NAV[service].filter((i) => navItemAllowed(auth, service, i)).map((i) => i.to)
    expect(visible('tech')).toContain('/tp/registry')
    expect(visible('tech')).not.toContain('/settings/traffic-light/tech')
    auth.setUser({ ...EMPLOYEE, effective_access: { ...EMPLOYEE.effective_access, services: { hr: 'viewer', project_product: 'viewer' } } })
    expect(visible('hr')).not.toContain('/hr/registry')
    expect(visible('project_product')).not.toContain('/product/registry')
    expect(visible('project_product')).not.toContain('/product/timeline')
    auth.setUser({ ...EMPLOYEE, effective_access: { ...EMPLOYEE.effective_access, services: { hr: 'viewer' }, can_view_records: true } })
    expect(visible('hr')).not.toContain('/hr/registry')
    auth.setUser({ ...EMPLOYEE, effective_access: { ...EMPLOYEE.effective_access, services: { hr: 'viewer' }, can_view_records: true, data_classes: ['operational', 'personal'] } })
    expect(visible('hr')).toContain('/hr/registry')
  })

  it('входящие данные: доступ и счётчик — из профиля /api/auth/me, без отдельных запросов', async () => {
    const calls = []
    globalThis.fetch = vi.fn(async (url) => {
      calls.push(url)
      return new Response(JSON.stringify({ ...EMPLOYEE, inbox: { available: true, pending: 1 } }), { status: 200, headers: { 'content-type': 'application/json' } })
    })
    auth.setUser({ id: 1, role: 'user', capabilities: ['data.manage'], effective_access: { services: {} }, inbox: { available: true, pending: 3 } })
    expect(await auth.loadInboxAccess()).toBe(true)
    expect(auth.inboxPending).toBe(3)
    auth.setUser({ ...EMPLOYEE, inbox: { available: true, pending: 4 } })
    expect(auth.inbox).toBe(true)
    expect(await auth.loadInboxAccess()).toBe(true)
    expect(auth.inboxPending).toBe(4)
    expect(calls).toEqual([]), 'меню не делает запросов /api/inbox/datasets и /api/inbox'
    // после применения, отклонения или загрузки — счётчик тем же /api/auth/me; одновременные вызовы — один запрос
    await Promise.all([auth.refreshInbox(), auth.refreshInbox()])
    expect(calls).toEqual(['/api/auth/me'])
    expect(auth.inboxPending).toBe(1)
    expect(auth.user.username).toBe('engineer')
    auth.setUser({ ...EMPLOYEE, id: 10, inbox: { available: false, pending: 0 } })
    expect(await auth.loadInboxAccess()).toBe(false)
    expect(auth.inbox).toBe(false)
    expect(auth.inboxPending).toBe(0)
    auth.setUser({ ...EMPLOYEE, id: 11 })
    expect(auth.inbox).toBe(false)
  })
})

describe('руководство администратора', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('администратору и любому полномочию администрирования; остальным — нет', () => {
    const auth = useAuthStore()
    expect(auth.canReadAdminGuide).toBe(false)
    auth.setUser(EMPLOYEE)
    expect(auth.canReadAdminGuide).toBe(false)
    for (const capability of ['org.manage', 'users.manage', 'reports.manage', 'data.manage', 'integrations.manage']) {
      auth.setUser({ ...EMPLOYEE, capabilities: [capability] })
      expect(auth.canReadAdminGuide).toBe(true)
    }
    auth.setUser({ ...EMPLOYEE, role: 'admin' })
    expect(auth.canReadAdminGuide).toBe(true)
  })
})
