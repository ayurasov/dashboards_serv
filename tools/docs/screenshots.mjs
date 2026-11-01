// Снимки экрана для руководств (docs/manuals/images/{user,admin}).
// Нужен сервер с демо-данными (DEMO_DATA=true) и собранным интерфейсом:
//   cd frontend && SHOTS_BASE_URL=http://127.0.0.1:8000 node ../tools/docs/screenshots.mjs
// Затем: python3 tools/docs/optimize_png.py docs/manuals/images
import { chromium } from '@playwright/test'
import { mkdirSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const BASE = process.env.SHOTS_BASE_URL || 'http://127.0.0.1:8000'
const OUT = resolve(ROOT, 'docs/manuals/images')
const only = process.argv.slice(2)

const browser = await chromium.launch()

async function session(username, password, { theme = 'light' } = {}) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1.5, colorScheme: theme, locale: 'ru-RU' })
  const page = await context.newPage()
  page.on('pageerror', (e) => console.error('  ошибка страницы:', e.message))
  await page.goto(`${BASE}/login`)
  if (username) {
    await page.fill('input[name=username]', username)
    await page.fill('input[name=password]', password)
    await page.click('button[type=submit]')
    await page.waitForURL((url) => !url.pathname.startsWith('/login'))
  }
  return { context, page }
}

async function settle(page, ms = 900) {
  await page.waitForLoadState('networkidle').catch(() => {})
  await page.waitForTimeout(ms)
}

async function shot(page, name, { clip, full = false } = {}) {
  if (only.length && !only.some((o) => name.includes(o))) return
  const path = `${OUT}/${name}.png`
  mkdirSync(dirname(path), { recursive: true })
  await page.screenshot({ path, fullPage: full, clip })
  console.log('  ', name)
}

async function open(page, path, ms) {
  await page.goto(`${BASE}${path}`)
  await settle(page, ms)
}

async function click(page, text) {
  await page.getByRole('button', { name: text }).first().click()
  await settle(page, 500)
}

async function dialogShot(page, name) {
  const dialog = page.getByRole('dialog').first()
  await dialog.waitFor()
  await page.waitForTimeout(300)
  await shot(page, name)
  await page.keyboard.press('Escape')
  await page.waitForTimeout(200)
}

// ---------------------------------------------------------------- пользователь
{
  const { context, page } = await session(null)
  await settle(page)
  await shot(page, 'user/01-login')
  await context.close()
}
{
  const { context, page } = await session('admin', 'admin123')
  const p = page
  await open(p, '/'); await shot(p, 'user/02-overview')
  await open(p, '/hr?quick=6', 1400); await shot(p, 'user/03-hr-dashboard')
  await click(p, 'Настроить'); await dialogShot(p, 'user/04-hr-layout')
  await open(p, '/hr/registry?month=2026-06'); await shot(p, 'user/05-hr-registry')
  await click(p, 'Добавить'); await dialogShot(p, 'user/06-hr-event-form')
  await open(p, '/hr/data?month=2026-07'); await shot(p, 'user/07-hr-data-entry')
  await open(p, '/hr/summary', 1400); await shot(p, 'user/08-hr-summary')
  await open(p, '/hr/targets'); await shot(p, 'user/09-hr-targets')
  await open(p, '/hr/dashboards'); await shot(p, 'user/10-hr-custom')
  await open(p, '/tp', 1600); await shot(p, 'user/11-tp-dashboard')
  await open(p, '/tp/registry'); await shot(p, 'user/12-tp-registry')
  await click(p, 'Загрузить файл'); await dialogShot(p, 'user/13-tp-import')
  await open(p, '/tp/compare', 1400); await shot(p, 'user/14-tp-compare')
  await open(p, '/tp/naumen', 1600); await shot(p, 'user/15-tp-naumen')
  await open(p, '/tp/analytics', 1600); await shot(p, 'user/16-tp-analytics')
  await open(p, '/product', 1400); await shot(p, 'user/17-pp-dashboard')
  await open(p, '/product/registry'); await shot(p, 'user/18-pp-registry')
  await p.locator('tbody tr').first().click(); await settle(p, 400); await dialogShot(p, 'user/19-pp-form')
  await open(p, '/product/summary', 1400); await shot(p, 'user/20-pp-summary')
  await open(p, '/product/timeline'); await shot(p, 'user/21-pp-timeline')
  await open(p, '/settings/traffic-light/hr'); await shot(p, 'user/22-traffic-light')
  await open(p, '/profile'); await shot(p, 'user/23-profile')
  await open(p, '/guide#дашборд-службы-персонала', 1200); await shot(p, 'user/24-guide')

  // администратор
  await open(p, '/admin/users'); await shot(p, 'admin/01-users')
  await p.locator('tbody tr', { hasText: 'hr_head' }).first().click(); await settle(p, 400)
  const accessTab = p.getByRole('tab', { name: 'Доступ' }).or(p.getByRole('button', { name: 'Доступ' }))
  if (await accessTab.count()) { await accessTab.first().click(); await settle(p, 300) }
  await shot(p, 'admin/02-user-access'); await p.keyboard.press('Escape'); await p.waitForTimeout(200)
  await click(p, 'Добавить пользователя'); await dialogShot(p, 'admin/03-user-create')
  await open(p, '/admin/departments'); await shot(p, 'admin/05-departments')
  await open(p, '/admin/audit'); await shot(p, 'admin/06-audit')
  await open(p, '/admin/palettes'); await shot(p, 'admin/07-palettes')
  await open(p, '/admin/system'); await shot(p, 'admin/08-system')
  await open(p, '/settings/traffic-light/hr'); await shot(p, 'admin/09-traffic-light-hr')
  await open(p, '/settings/partnership-lights'); await shot(p, 'admin/10-partnership-lights')
  await context.close()
}
{
  // Временный пароль — на тестовом пользователе, который сразу удаляется
  const { context, page: p } = await session('admin', 'admin123')
  await open(p, '/admin/users')
  await click(p, 'Добавить пользователя')
  const dialog = p.getByRole('dialog').first()
  await dialog.locator('input').nth(0).fill('demo.user')
  await dialog.locator('input').nth(1).fill('Петрова Анна Сергеевна')
  await dialog.getByRole('button', { name: /Создать|Сохранить/ }).click()
  await settle(p, 600)
  await shot(p, 'admin/04-temp-password')
  const csrf = (await context.cookies()).find((c) => c.name === 'ds_csrf')?.value
  const users = await (await p.request.get(`${BASE}/api/users?search=demo.user`)).json()
  for (const u of users) await p.request.delete(`${BASE}/api/users/${u.id}`, { headers: { 'X-CSRF-Token': csrf } })
  await context.close()
}
{
  const { context, page: p } = await session('admin', 'admin123', { theme: 'dark' })
  await open(p, '/tp', 1600); await shot(p, 'user/25-dark-theme')
  await context.close()
}
await browser.close()
