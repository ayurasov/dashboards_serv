/**
 * Навигация служб: разделы бокового меню. `level` — минимальный уровень доступа к службе,
 * при котором пункт виден (сервер всё равно проверяет права сам).
 */
export const SERVICE_NAV = {
  hr: [
    { to: '/hr', label: 'Дашборд', icon: 'grid', exact: true },
    { to: '/hr/registry', label: 'Приёмы и увольнения', icon: 'list' },
    { to: '/hr/data', label: 'Ввод данных', icon: 'edit', level: 'editor' },
    { to: '/hr/summary', label: 'Сводка по периодам', icon: 'table' },
    { to: '/hr/targets', label: 'Цели', icon: 'target' },
    { to: '/hr/dashboards', label: 'Мои дашборды', icon: 'layout' },
    { to: '/settings/traffic-light/hr', label: 'Светофор', icon: 'traffic', level: 'manager' },
  ],
  tech: [
    { to: '/tp', label: 'Дашборд', icon: 'grid', exact: true },
    { to: '/tp/registry', label: 'Недельный отчёт', icon: 'table' },
    { to: '/tp/compare', label: 'Сравнение периодов', icon: 'compare' },
    { to: '/tp/naumen', label: 'Заявки Naumen', icon: 'ticket' },
    { to: '/tp/analytics', label: 'Отчёт и Naumen', icon: 'layers' },
    { to: '/settings/traffic-light/tech', label: 'Светофор', icon: 'traffic', level: 'manager' },
  ],
  project_product: [
    { to: '/product', label: 'Дашборд', icon: 'grid', exact: true },
    { to: '/product/registry', label: 'Реестр партнёрств', icon: 'list' },
    { to: '/product/summary', label: 'Сводка по годам', icon: 'table' },
    { to: '/product/timeline', label: 'Хронология', icon: 'clock' },
    { to: '/settings/partnership-lights', label: 'Светофор', icon: 'traffic' },
  ],
}

export const ADMIN_NAV = [
  { to: '/admin/users', label: 'Пользователи', icon: 'users' },
  { to: '/admin/departments', label: 'Подразделения', icon: 'building' },
  { to: '/admin/audit', label: 'Журнал изменений', icon: 'history' },
  { to: '/admin/palettes', label: 'Палитры', icon: 'palette' },
  { to: '/admin/system', label: 'О системе', icon: 'server' },
]

export const HELP_NAV = [
  { to: '/guide', label: 'Руководство', icon: 'book' },
  { to: '/guide/admin', label: 'Руководство администратора', icon: 'shield', admin: true },
  { to: '/about', label: 'О программе', icon: 'info' },
]
