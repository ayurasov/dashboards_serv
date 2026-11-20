/**
 * Мобильная вёрстка (390×844, тач): инвариант «вьюпорт без горизонтальной прокрутки» на ключевых
 * маршрутах и шторка навигации — бургер с aria-expanded, закрытие по Esc и щелчку по фону.
 * Аудит 2026-11-20 (D3): обходчик показал 0px переполнения — тест закрепляет это как контракт.
 */
import { expect, test } from '@playwright/test'
import { collectErrors, login } from './helpers'

const ROUTES = [
  ['/', 'Обзор'],
  ['/reports', 'Сквозной отчёт'],
  ['/hr', 'Служба персонала'],
  ['/tp', 'Техническая поддержка'],
  ['/product', 'Партнёрства'],
  ['/inbox', 'Входящие данные'],
  ['/org', 'Структура'],
  ['/profile', 'Профиль'],
]

test.describe('мобильная вёрстка', () => {
  for (const [route] of ROUTES) {
    test(`без горизонтальной прокрутки: ${route}`, async ({ page }) => {
      const errors = collectErrors(page)
      await login(page)
      await page.goto(route)
      await page.waitForTimeout(1200)
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
      expect(overflow, 'scrollWidth не должен превышать ширину вьюпорта').toBeLessThanOrEqual(1)
      expect(errors).toEqual([])
    })
  }

  test('шторка навигации: бургер с aria-expanded, закрывается Esc и щелчком по фону', async ({ page }) => {
    await login(page)
    await page.goto('/')
    const burger = page.locator('.tb-btn.mobile-only')
    await expect(burger).toBeVisible()
    await expect(burger).toHaveAttribute('aria-expanded', 'false')

    await burger.click()
    const sidebar = page.locator('#app-sidebar')
    await expect(sidebar).toBeVisible()
    await expect(burger).toHaveAttribute('aria-expanded', 'true')

    // Закрытая шторка уезжает transform'ом за экран — Playwright считает её «видимой»,
    // поэтому проверяем класс open и aria-expanded бургера
    const closed = () => Promise.all([
      expect(sidebar).not.toHaveClass(/open/),
      expect(burger).toHaveAttribute('aria-expanded', 'false'),
    ])
    await page.keyboard.press('Escape')
    await closed()

    await burger.click()
    await expect(sidebar).toHaveClass(/open/)
    await page.locator('.scrim').click({ position: { x: 360, y: 100 } })
    await closed()

    // Ссылка из шторки ведёт в раздел и закрывает её
    await burger.click()
    await sidebar.getByRole('link', { name: 'Сквозной отчёт' }).click()
    await expect(page).toHaveURL(/\/reports$/)
    await closed()
  })
})
