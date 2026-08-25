import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from './stores/auth.js'

const routes = [
  { path: '/login', name: 'login', component: () => import('./views/Login.vue'), meta: { public: true } },
  { path: '/', name: 'dashboard', component: () => import('./views/Dashboard.vue'), meta: { service: 'hr' } },
  { path: '/registry', name: 'registry', component: () => import('./views/Registry.vue'), meta: { service: 'hr' } },
  { path: '/summary', name: 'summary', component: () => import('./views/Summary.vue'), meta: { service: 'hr' } },
  { path: '/hr/data-entry', name: 'data-entry', component: () => import('./views/DataEntry.vue'), meta: { service: 'hr' } },
  { path: '/hr/benchmarks', name: 'benchmarks', component: () => import('./views/Benchmarks.vue'), meta: { service: 'hr' } },
  { path: '/custom-dashboards', name: 'custom-dashboards', component: () => import('./views/CustomDashboard.vue'), meta: { service: 'hr' } },
  { path: '/audit', name: 'audit', component: () => import('./views/AuditLog.vue'), meta: { admin: true } },
  { path: '/users', name: 'users', component: () => import('./views/Users.vue'), meta: { admin: true } },
  { path: '/traffic-light', name: 'traffic-light', component: () => import('./views/TrafficLightConfig.vue'), meta: { admin: true, service: 'hr' } },
  { path: '/product', name: 'product-dashboard', component: () => import('./views/PartnershipsDashboard.vue'), meta: { service: 'project_product' } },
  { path: '/product/registry', name: 'product-registry', component: () => import('./views/PartnershipsRegistry.vue'), meta: { service: 'project_product' } },
  { path: '/product/summary', name: 'product-summary', component: () => import('./views/PartnershipsSummary.vue'), meta: { service: 'project_product' } },
  { path: '/product/timeline', name: 'product-timeline', component: () => import('./views/PartnershipsTimeline.vue'), meta: { service: 'project_product' } },
  { path: '/product/traffic-light', name: 'product-traffic-light', component: () => import('./views/PartnershipTrafficLight.vue'), meta: { service: 'project_product' } },
  // ---------- Technical Support ----------
  { path: '/tp', name: 'tp-dashboard', component: () => import('./views/tp/TpDashboard.vue'), meta: { service: 'tech' } },
  { path: '/tp/registry', name: 'tp-registry', component: () => import('./views/tp/TpRegistry.vue'), meta: { service: 'tech' } },
  { path: '/tp/summary', name: 'tp-summary', component: () => import('./views/tp/TpSummary.vue'), meta: { service: 'tech' } },
  { path: '/tp/naumen', name: 'tp-naumen', component: () => import('./views/tp/TpNaumenDashboard.vue'), meta: { service: 'tech' } },
  { path: '/tp/traffic-light', name: 'tp-traffic-light', component: () => import('./views/tp/TpTrafficLight.vue'), meta: { service: 'tech', admin: true } },
  // ---------- Other ----------
  { path: '/palette', name: 'palette', component: () => import('./views/PaletteSettings.vue'), meta: { admin: true } },
  { path: '/profile', name: 'profile', component: () => import('./views/Profile.vue') },
  { path: '/no-access', name: 'no-access', component: () => import('./views/NoAccess.vue') },
]

// Home page of each service that has dashboard content.
const SERVICE_HOME = { hr: '/', project_product: '/product', tech: '/tp' }

const router = createRouter({ history: createWebHistory(), routes })

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (to.meta.public) return true
  if (!auth.token) return { name: 'login' }
  if (to.meta.admin && auth.role !== 'admin') return { name: 'dashboard' }
  if (to.meta.edit && !auth.canEdit) return { name: 'dashboard' }
  if (!to.meta.service) return true

  try {
    await auth.loadAccess()
  } catch {
    return true
  }
  if (auth.canViewService(to.meta.service)) return true

  for (const [key, path] of Object.entries(SERVICE_HOME)) {
    if (auth.canViewService(key)) return path
  }
  return { name: 'no-access' }
})

export default router
