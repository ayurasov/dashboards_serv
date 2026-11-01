import { expect, test } from '@playwright/test'
import { collectErrors, login } from './helpers'

test('вход, обзор служб и выход', async ({ page }) => {
  const errors = collectErrors(page)
  await page.goto('/hr')
  await expect(page).toHaveURL(/\/login\?redirect=%2Fhr/)
  await page.fill('input[name=username]', 'admin')
  await page.fill('input[name=password]', 'неверный')
  await page.click('button[type=submit]')
  await expect(page.getByRole('alert')).toContainText('Неверный логин или пароль')
  await login(page)
  await expect(page.getByRole('heading', { level: 1 })).toContainText(/Добр/)
  for (const title of ['Служба персонала', 'Техническая поддержка', 'Проектный и продуктовый офис']) {
    await expect(page.getByRole('heading', { name: title })).toBeVisible()
  }
  await page.getByTitle('Выйти').click()
  await expect(page).toHaveURL(/\/login/)
  expect(errors).toEqual([])
})

const PAGES = [
  ['/hr', 'Служба персонала'], ['/hr/registry', 'Приёмы и увольнения'], ['/hr/data', 'Ввод данных'],
  ['/hr/summary', 'Сводка'], ['/hr/targets', 'Цели'], ['/hr/dashboards', 'дашборд'],
  ['/tp', 'поддержк'], ['/tp/registry', 'Недельный отчёт'], ['/tp/compare', 'Сравнение'], ['/tp/naumen', 'Naumen'],
  ['/tp/analytics', 'Naumen'], ['/product', 'артнёрств'], ['/product/registry', 'артнёрств'], ['/product/summary', 'Сводка'],
  ['/product/timeline', 'Хронология'], ['/settings/traffic-light/hr', 'Светофор'], ['/settings/traffic-light/tech', 'Светофор'],
  ['/settings/partnership-lights', 'Светофор'], ['/admin/users', 'Пользователи'], ['/admin/departments', 'Подразделения'],
  ['/admin/audit', 'Журнал'], ['/admin/palettes', 'Палитр'], ['/admin/system', 'систем'], ['/profile', 'Профиль'],
  ['/guide', 'Руководство пользователя'], ['/guide/admin', 'Руководство администратора'], ['/about', 'О программе'],
]

test('все страницы открываются без ошибок', async ({ page }) => {
  const errors = collectErrors(page)
  await login(page)
  for (const [path, title] of PAGES) {
    await page.goto(path)
    await expect(page.getByRole('heading', { level: 1 }).first(), path).toContainText(title, { ignoreCase: true })
  }
  expect(errors).toEqual([])
})

test('права: пользователь видит только свои службы', async ({ page }) => {
  await login(page, 'tp_lead')
  await expect(page.getByRole('heading', { name: 'Техническая поддержка' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Служба персонала' })).toHaveCount(0)
  await page.goto('/hr')
  await expect(page.getByRole('heading', { name: 'Нет доступа' })).toBeVisible()
  await page.goto('/admin/users')
  await expect(page.getByRole('heading', { name: 'Нет доступа' })).toBeVisible()
})

test('реестр: фильтр сохраняется в адресе', async ({ page }) => {
  await login(page)
  await page.goto('/hr/registry')
  await page.getByPlaceholder('ФИО или должность').fill('лапин')
  await expect(page).toHaveURL(/search=/)
  await expect(page.locator('tbody tr')).toHaveCount(1)
  await page.reload()
  await expect(page.getByPlaceholder('ФИО или должность')).toHaveValue('лапин')
})

test('тема переключается и запоминается', async ({ page }) => {
  await login(page)
  const html = page.locator('html')
  for (let i = 0; i < 3 && (await html.getAttribute('data-theme')) !== 'dark'; i++) {
    await page.locator('.topbar button[title*="тема"], .topbar button[title*="системе"]').last().click()
  }
  await expect(html).toHaveAttribute('data-theme', 'dark')
  await page.reload()
  await expect(html).toHaveAttribute('data-theme', 'dark')
})

test('история версий и руководство встроены в приложение', async ({ page }) => {
  await login(page)
  await page.getByRole('button', { name: 'Что нового' }).click()
  await expect(page.getByRole('dialog')).toContainText('Версия 0.1.0')
  await page.keyboard.press('Escape')
  await page.goto('/about')
  await expect(page.getByTestId('about-version')).toHaveText('0.1.0')
  await page.goto('/guide')
  await page.getByPlaceholder('Найти в руководстве').fill('светофор')
  await expect(page.locator('.toc li').first()).toBeVisible()
})
