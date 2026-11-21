/**
 * Визуальная регрессия: эталонные снимки ключевых экранов (обе темы, ширины 1440/768/390).
 * Охраняет вёрстку при рефакторинге — в частности лестницу адаптива 640/960/1100/1280 (B2, 0.4.3).
 *
 * Детерминированность: время зафиксировано page.clock (приветствие и «N дней назад» не зависят
 * от момента прогона), демо-данные фиксированы, анимации отключаются на снимке. Эталоны сгенерированы
 * в том же окружении, что и CI (образ метки ubuntu-latest — node:20-bookworm): обновление —
 * `npx playwright test visual --update-snapshots` и внимательный просмотр дифа в ревью.
 */
import { expect, test } from '@playwright/test'
import { login } from './helpers'

const FIXED_TIME = new Date('2026-11-21T12:00:00+03:00')
const SHOT = { animations: 'disabled', caret: 'hide', maxDiffPixelRatio: 0.01 }

const DESKTOP = ['/', '/reports', '/hr', '/tp', '/product', '/org', '/inbox', '/profile']
const DARK = ['/', '/reports', '/hr']
const NARROW = [
  [768, ['/reports', '/hr', '/inbox']],
  [390, ['/', '/reports', '/hr']],
]

async function open(page, route, { width, height } = {}) {
  if (width) await page.setViewportSize({ width, height })
  await page.clock.install({ time: FIXED_TIME })
  await login(page)
  await page.goto(route)
  await page.waitForLoadState('networkidle').catch(() => {})
  await page.locator('.skeleton').first().waitFor({ state: 'detached', timeout: 8000 }).catch(() => {})
  await page.waitForTimeout(1200)  // анимации графиков
}

test.describe('визуальная регрессия', () => {
  test.beforeEach(async ({ page }) => {
    await page.clock.install({ time: FIXED_TIME })
  })

  for (const route of DESKTOP) {
    test(`светлая тема 1440: ${route}`, async ({ page }) => {
      await open(page, route)
      await expect(page).toHaveScreenshot(`light-1440${route.replace(/\//g, '-') || '-root'}.png`, SHOT)
    })
  }

  for (const route of DARK) {
    test(`тёмная тема 1440: ${route}`, async ({ page }) => {
      await page.addInitScript(() => localStorage.setItem('ds_theme', 'dark'))
      await open(page, route)
      await expect(page).toHaveScreenshot(`dark-1440${route.replace(/\//g, '-') || '-root'}.png`, SHOT)
    })
  }

  for (const [width, routes] of NARROW) {
    for (const route of routes) {
      test(`светлая тема ${width}: ${route}`, async ({ page }) => {
        await open(page, route, { width, height: width === 390 ? 844 : 900 })
        await expect(page).toHaveScreenshot(`light-${width}${route.replace(/\//g, '-') || '-root'}.png`, SHOT)
      })
    }
  }

  test('страница входа', async ({ page }) => {
    await page.clock.install({ time: FIXED_TIME })
    await page.goto('/login')
    await page.waitForTimeout(800)
    await expect(page).toHaveScreenshot('login-1440.png', SHOT)
  })
})
