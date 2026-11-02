import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

/**
 * meta: title — заголовок вкладки и хлебных крошек; service — служба страницы; level — минимальный
 * уровень доступа; records — исходные записи (реестры и списки, ADR-0009); dataClass — класс данных
 * страницы (personal, financial); admin — только администратор; capability — полномочие
 * администрирования (org.manage, users.manage, reports.manage, data.manage, integrations.manage);
 * inbox — «Входящие данные»: полномочие data.manage или право применять хотя бы один набор (это
 * знает сервер, см. auth.loadInboxAccess); public — без входа; guide — раздел руководства (якорь заголовка),
 * guideKind: 'admin' — раздел руководства администратора (ссылка «?» видна администратору);
 * parent — раздел над страницей в «хлебных крошках» ({ label, to }).
 */
const routes = [
  { path: '/login', name: 'login', component: () => import('@/views/LoginView.vue'), meta: { public: true, title: 'Вход', bare: true } },
  { path: '/', name: 'home', component: () => import('@/views/HomeView.vue'), meta: { title: 'Обзор', guide: 'обзор' } },
  { path: '/org', name: 'org', component: () => import('@/views/org/OrgView.vue'), meta: { title: 'Структура компании', guide: 'структура-компании' } },

  // Сквозные отчёты (ADR-0010): отчёт — любому вошедшему; ввод — по признаку me.can_enter (проверяет страница)
  { path: '/reports', name: 'reports', component: () => import('@/views/reports/ReportsView.vue'), meta: { title: 'Сквозной отчёт', guide: 'сквозной-отчёт' } },
  { path: '/reports/entry', name: 'reports-entry', component: () => import('@/views/reports/ReportsEntry.vue'), meta: { title: 'Ввод показателей', guide: 'ввод-показателей', parent: { label: 'Сквозной отчёт', to: '/reports' } } },

  // Входящие данные (ADR-0011): папка, загрузка, приём по API, подключения — план и применение
  { path: '/inbox', name: 'inbox', component: () => import('@/views/InboxView.vue'), meta: { inbox: true, title: 'Входящие данные', guide: 'входящие-данные' } },

  // Служба персонала
  { path: '/hr', name: 'hr-dashboard', component: () => import('@/views/hr/HrDashboard.vue'), meta: { service: 'hr', title: 'Дашборд', guide: 'дашборд-службы-персонала' } },
  { path: '/hr/registry', name: 'hr-registry', component: () => import('@/views/hr/HrRegistry.vue'), meta: { service: 'hr', records: true, dataClass: 'personal', title: 'Приёмы и увольнения', guide: 'приёмы-и-увольнения' } },
  { path: '/hr/data', name: 'hr-data', component: () => import('@/views/hr/HrDataEntry.vue'), meta: { service: 'hr', level: 'editor', title: 'Ввод данных', guide: 'ввод-данных-месяца' } },
  { path: '/hr/summary', name: 'hr-summary', component: () => import('@/views/hr/HrSummary.vue'), meta: { service: 'hr', title: 'Сводка по периодам', guide: 'сводка-по-периодам' } },
  { path: '/hr/targets', name: 'hr-targets', component: () => import('@/views/hr/HrTargets.vue'), meta: { service: 'hr', title: 'Цели', guide: 'цели-и-бенчмарки' } },
  { path: '/hr/dashboards', name: 'hr-dashboards', component: () => import('@/views/hr/HrCustomDashboards.vue'), meta: { service: 'hr', title: 'Мои дашборды', guide: 'мои-дашборды' } },

  // Техническая поддержка
  { path: '/tp', name: 'tp-dashboard', component: () => import('@/views/tp/TpDashboard.vue'), meta: { service: 'tech', title: 'Дашборд', guide: 'дашборд-недельного-отчёта' } },
  { path: '/tp/registry', name: 'tp-registry', component: () => import('@/views/tp/TpRegistry.vue'), meta: { service: 'tech', title: 'Недельный отчёт', guide: 'недельный-отчёт' } },
  { path: '/tp/compare', name: 'tp-compare', component: () => import('@/views/tp/TpCompare.vue'), meta: { service: 'tech', title: 'Сравнение периодов', guide: 'сравнение-периодов' } },
  { path: '/tp/naumen', name: 'tp-naumen', component: () => import('@/views/tp/TpNaumen.vue'), meta: { service: 'tech', title: 'Заявки Naumen', guide: 'заявки-naumen' } },
  { path: '/tp/analytics', name: 'tp-analytics', component: () => import('@/views/tp/TpCrossAnalytics.vue'), meta: { service: 'tech', title: 'Отчёт и Naumen', guide: 'отчёт-и-naumen' } },

  // Проектный и продуктовый офис
  { path: '/product', name: 'product-dashboard', component: () => import('@/views/product/PartnershipsDashboard.vue'), meta: { service: 'project_product', title: 'Дашборд', guide: 'дашборд-партнёрств' } },
  { path: '/product/registry', name: 'product-registry', component: () => import('@/views/product/PartnershipsRegistry.vue'), meta: { service: 'project_product', records: true, title: 'Реестр партнёрств', guide: 'реестр-партнёрств' } },
  { path: '/product/summary', name: 'product-summary', component: () => import('@/views/product/PartnershipsSummary.vue'), meta: { service: 'project_product', title: 'Сводка по годам', guide: 'сводка-и-хронология' } },
  { path: '/product/timeline', name: 'product-timeline', component: () => import('@/views/product/PartnershipsTimeline.vue'), meta: { service: 'project_product', records: true, title: 'Хронология', guide: 'сводка-и-хронология' } },

  // Настройки служб
  { path: '/settings/traffic-light/:service(hr|tech)', name: 'traffic-light', component: () => import('@/views/settings/TrafficLightSettings.vue'), meta: { serviceParam: true, level: 'manager', title: 'Светофор', guide: 'настройка-светофора' } },
  { path: '/settings/partnership-lights', name: 'partnership-lights', component: () => import('@/views/settings/PartnershipLightSettings.vue'), meta: { service: 'project_product', title: 'Светофор партнёрств', guide: 'настройка-светофора' } },

  // Администрирование
  { path: '/admin/users', name: 'admin-users', component: () => import('@/views/admin/AdminUsers.vue'), meta: { capability: 'users.manage', title: 'Пользователи' } },
  { path: '/admin/access-profiles', name: 'admin-access-profiles', component: () => import('@/views/admin/AccessProfiles.vue'), meta: { capability: 'users.manage', title: 'Профили доступа' } },
  { path: '/admin/departments', name: 'admin-departments', component: () => import('@/views/admin/AdminDepartments.vue'), meta: { capability: 'org.manage', title: 'Подразделения' } },
  { path: '/admin/org-transfer', name: 'admin-org-transfer', component: () => import('@/views/admin/OrgTransfer.vue'), meta: { capability: 'org.manage', title: 'Импорт и экспорт' } },
  { path: '/admin/indicators', name: 'admin-indicators', component: () => import('@/views/admin/AdminIndicators.vue'), meta: { capability: 'reports.manage', title: 'Показатели' } },
  { path: '/admin/integrations', name: 'admin-integrations', component: () => import('@/views/admin/AdminIntegrations.vue'), meta: { capability: 'integrations.manage', title: 'Интеграции', guide: 'интеграции', guideKind: 'admin' } },
  { path: '/admin/directory', name: 'admin-directory', component: () => import('@/views/admin/AdminDirectory.vue'), meta: { admin: true, title: 'Вход по домену' } },
  { path: '/admin/audit', name: 'admin-audit', component: () => import('@/views/admin/AdminAudit.vue'), meta: { admin: true, title: 'Журнал изменений' } },
  { path: '/admin/palettes', name: 'admin-palettes', component: () => import('@/views/admin/AdminPalettes.vue'), meta: { admin: true, title: 'Палитры' } },
  { path: '/admin/system', name: 'admin-system', component: () => import('@/views/admin/AdminSystem.vue'), meta: { admin: true, title: 'О системе' } },

  // Личное и справка
  { path: '/profile', name: 'profile', component: () => import('@/views/ProfileView.vue'), meta: { title: 'Профиль', allowPasswordChange: true, guide: 'профиль-и-безопасность' } },
  { path: '/guide', name: 'guide', component: () => import('@/views/GuideView.vue'), meta: { title: 'Руководство пользователя', allowPasswordChange: true } },
  { path: '/guide/admin', name: 'guide-admin', component: () => import('@/views/GuideView.vue'), meta: { admin: true, title: 'Руководство администратора', guideKind: 'admin' } },
  { path: '/about', name: 'about', component: () => import('@/views/AboutView.vue'), meta: { title: 'О программе', allowPasswordChange: true } },
  { path: '/no-access', name: 'no-access', component: () => import('@/views/NoAccessView.vue'), meta: { title: 'Нет доступа' } },

  // Адреса прежних версий
  { path: '/registry', redirect: '/hr/registry' },
  { path: '/summary', redirect: '/hr/summary' },
  { path: '/hr/data-entry', redirect: '/hr/data' },
  { path: '/hr/benchmarks', redirect: '/hr/targets' },
  { path: '/custom-dashboards', redirect: '/hr/dashboards' },
  { path: '/traffic-light', redirect: '/settings/traffic-light/hr' },
  { path: '/tp/summary', redirect: '/tp/compare' },
  { path: '/tp/naumen/org', redirect: '/tp/analytics' },
  { path: '/tp/traffic-light', redirect: '/settings/traffic-light/tech' },
  { path: '/product/traffic-light', redirect: '/settings/partnership-lights' },
  { path: '/users', redirect: '/admin/users' },
  { path: '/structure', redirect: '/org' },
  { path: '/audit', redirect: '/admin/audit' },
  { path: '/palette', redirect: '/admin/palettes' },

  { path: '/:pathMatch(.*)*', name: 'not-found', component: () => import('@/views/NotFoundView.vue'), meta: { title: 'Страница не найдена' } },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior(to, from, saved) {
    if (saved) return saved
    if (to.hash) return { el: to.hash }
    if (to.path !== from.path) return { top: 0 }
    return undefined
  },
})

export function routeService(route) {
  return route.meta.serviceParam ? route.params.service : route.meta.service
}

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (!auth.loaded) await auth.load()
  if (to.meta.public) {
    return auth.isLoggedIn && to.name === 'login' ? { path: String(to.query.redirect || '/') } : true
  }
  if (!auth.isLoggedIn) return { name: 'login', query: to.fullPath !== '/' ? { redirect: to.fullPath } : {} }
  if (auth.mustChangePassword && !to.meta.allowPasswordChange) return { name: 'profile', query: { password: 'required' } }
  if (to.meta.admin && !auth.isAdmin) return { name: 'no-access', query: { reason: 'admin' } }
  if (to.meta.capability && !auth.hasCapability(to.meta.capability)) return { name: 'no-access', query: { reason: 'capability', capability: to.meta.capability } }
  if (to.meta.inbox && !(await auth.loadInboxAccess())) return { name: 'no-access', query: { reason: 'inbox', page: to.meta.title } }
  const service = routeService(to)
  const reason = auth.denial({ service, level: to.meta.level || 'viewer', records: !!to.meta.records, dataClass: to.meta.dataClass })
  if (reason) return { name: 'no-access', query: { reason, ...(service ? { service } : {}), page: to.meta.title } }
  return true
})

router.afterEach((to) => {
  document.title = to.meta.title ? `${to.meta.title} — Дашборды компании` : 'Дашборды компании'
})

export default router
