import { expect, test } from '@playwright/test'
import { api, apiGet, canvasColorShare, collectErrors, expectDownload, login, uniq } from './helpers'

test.describe('администрирование', () => {
  test.describe.configure({ timeout: 90_000 })

  test('палитра: смена активной палитры перекрашивает графики и светофор', async ({ page }) => {
    const errors = collectErrors(page)
    await login(page)
    const palettes = await apiGet(page, '/palettes')
    const original = palettes.find((p) => p.is_active)
    const target = palettes.find((p) => !p.is_active && p.colors.charts[0] !== original.colors.charts[0] && p.colors.traffic_light.green !== original.colors.traffic_light.green)
    const turnoverCard = page.locator('.chart-card', { has: page.getByRole('heading', { name: 'Текучесть кадров' }) })
    try {
      await page.goto('/hr')
      await expect.poll(() => canvasColorShare(turnoverCard, original.colors.charts[0])).toBeGreaterThan(50)

      await page.goto('/admin/palettes')
      const card = page.locator('article.pal', { has: page.getByRole('heading', { name: target.name, exact: true }) })
      await card.getByRole('button', { name: 'Сделать активной' }).click()
      await expect(card.getByText('Активна')).toBeVisible()
      expect(await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue('--light-green').trim())).toBe(target.colors.traffic_light.green)

      await page.goto('/hr')
      await expect.poll(() => canvasColorShare(turnoverCard, target.colors.charts[0])).toBeGreaterThan(50)
      expect(await canvasColorShare(turnoverCard, original.colors.charts[0])).toBeLessThan(5)
      // Карточка показателя в норме окрашена зелёным цветом новой палитры
      const stripe = await page.locator('.kpi.card.l-green').first().evaluate((el) => getComputedStyle(el, '::before').backgroundColor)
      const [r, g, b] = [1, 3, 5].map((i) => parseInt(target.colors.traffic_light.green.slice(i, i + 2), 16))
      expect(stripe).toBe(`rgb(${r}, ${g}, ${b})`)
    } finally {
      await api(page, 'POST', `/palettes/${original.id}/activate`).catch(() => {})
    }
    expect(errors).toEqual([])
  })

  test('журнал: фильтры отбирают записи и хранятся в адресе, выгрузка CSV', async ({ page }) => {
    await login(page)
    const name = uniq('Журнал')
    const created = await api(page, 'POST', '/partnerships', { partner: name, status: 'В работе', type: 'ПО' })
    await api(page, 'DELETE', `/partnerships/${created.id}`)

    await page.goto('/admin/audit')
    await page.getByPlaceholder('Описание или ID объекта').fill(name)
    await expect(page).toHaveURL(/search=/)
    const rows = page.locator('table.audit tbody tr.main')
    await expect(rows).toHaveCount(2)
    await page.getByLabel('Действие').selectOption('delete')
    await expect(page).toHaveURL(/action=delete/)
    await expect(rows).toHaveCount(1)
    await expect(rows.first()).toContainText('admin')
    await page.reload()
    await expect(rows).toHaveCount(1)
    await expect(page.getByLabel('Действие')).toHaveValue('delete')

    const api1 = await apiGet(page, `/audit?search=${encodeURIComponent(name)}&action=delete`)
    expect(api1.total).toBe(1)
    const { body } = await expectDownload(page, () => page.getByRole('button', { name: 'Выгрузить CSV' }).click(), { ext: 'csv', name: 'Журнал изменений' })
    expect(body.toString('utf-8')).toContain(name)

    // Период без записей
    await page.getByLabel('С даты').fill('2001-01-01')
    await page.getByLabel('По дату').fill('2001-01-02')
    await expect(rows).toHaveCount(0)
    await page.getByRole('button', { name: 'Сбросить', exact: true }).click()
    await expect(page).not.toHaveURL(/search=|action=|date_from=/)
  })

  // Жизненный цикл пользователя (создание, временный пароль, отключение, удаление) — e2e/access.spec.js
  test('окно «Новый пользователь»: фокус внутри окна, Esc закрывает и возвращает фокус', async ({ page }) => {
    const errors = collectErrors(page)
    await login(page)
    await page.goto('/admin/users')
    const addButton = page.getByTestId('user-add')
    await expect(addButton).toBeEnabled()
    await addButton.click()
    const dialog = page.getByRole('dialog', { name: 'Новый пользователь' })
    await expect(dialog).toBeFocused()
    for (let i = 0; i < 40; i++) await page.keyboard.press('Tab')
    expect(await dialog.evaluate((el) => el.contains(document.activeElement))).toBe(true)
    await page.keyboard.press('Shift+Tab')
    expect(await dialog.evaluate((el) => el.contains(document.activeElement))).toBe(true)
    await page.keyboard.press('Escape')
    await expect(dialog).toBeHidden()
    await expect(addButton).toBeFocused()
    expect(errors).toEqual([])
  })
  test('права: администрирование недоступно не-администраторам', async ({ page }) => {
    for (const user of ['hr_head', 'viewer']) {
      await page.context().clearCookies()
      await login(page, user)
      for (const path of ['/admin/audit', '/admin/palettes', '/admin/system', '/admin/users']) {
        await page.goto(path)
        await expect(page.getByRole('heading', { name: 'Нет доступа' }), `${user} ${path}`).toBeVisible()
      }
      expect((await page.request.get('/api/audit')).status()).toBe(403)
    }
  })
})
