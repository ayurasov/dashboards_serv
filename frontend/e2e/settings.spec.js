import { expect, test } from '@playwright/test'
import { api, apiGet, collectErrors, confirmDialog, kpi, login } from './helpers'

async function rule(page, service, key) {
  return (await apiGet(page, `/traffic-light/${service}`)).find((r) => r.metric_key === key)
}

function restoreBody(r) {
  return { direction: r.direction, green_threshold: r.green_threshold, yellow_threshold: r.yellow_threshold, enabled: r.enabled }
}

test.describe('настройка светофора', () => {
  test.describe.configure({ timeout: 90_000 })

  test('служба персонала: новый порог меняет цвет показателя на дашборде', async ({ page }) => {
    const errors = collectErrors(page)
    await login(page)
    const original = await rule(page, 'hr', 'turnover')
    try {
      await page.goto('/hr')
      await expect(kpi(page, 'Текучесть кадров')).toHaveClass(/l-green/)

      await page.goto('/settings/traffic-light/hr')
      const green = page.getByLabel('Текучесть кадров: граница зелёного')
      const yellow = page.getByLabel('Текучесть кадров: граница жёлтого')
      // Противоречивые границы: сообщение и отказ сервера
      await green.fill('3')
      await yellow.fill('1')
      await expect(page.getByRole('alert').filter({ hasText: 'граница зелёного должна быть не больше границы жёлтого' })).toBeVisible()
      await green.fill('1')
      await yellow.fill('1,5')
      await expect(page.getByRole('button', { name: 'Сохранить все (1)' })).toBeVisible()
      const row = page.getByRole('row').filter({ has: green })
      await row.getByRole('button', { name: 'Сохранить' }).click()
      await expect(page.getByRole('button', { name: /Сохранить все/ })).toHaveCount(0)
      const saved = await rule(page, 'hr', 'turnover')
      expect([saved.green_threshold, saved.yellow_threshold, saved.enabled]).toEqual([1, 1.5, true])

      await page.goto('/hr')
      // 2% > 1,5% при «меньше — лучше» — критично
      await expect(kpi(page, 'Текучесть кадров')).toHaveClass(/l-red/)
      await expect(page.locator('tr', { hasText: 'Текучесть кадров' }).first().locator('.badge, .light-badge').first()).toContainText('Критично')
    } finally {
      await api(page, 'PUT', '/traffic-light/hr/turnover', restoreBody(original)).catch(() => {})
    }
    await page.goto('/hr')
    await expect(kpi(page, 'Текучесть кадров')).toHaveClass(/l-green/)
    expect(errors).toEqual([])
  })

  test('техподдержка: порог недели умножается на число недель периода', async ({ page }) => {
    await login(page)
    const original = await rule(page, 'tech', 'total_solved_week')
    const rows = (await apiGet(page, '/tp/reports')).sort((a, b) => a.year - b.year || a.week - b.week)
    const last = rows.at(-1)
    try {
      // Норма — не меньше значения последней недели, внимание — на 1 меньше: неделя «в норме»
      await api(page, 'PUT', '/traffic-light/tech/total_solved_week',
        { direction: 'higher_is_better', green_threshold: last.total_solved_week, yellow_threshold: last.total_solved_week - 1, enabled: true })
      await page.goto('/tp?quick=1')
      await expect(kpi(page, 'Решено заявок')).toHaveClass(/l-green/)
      await page.goto('/settings/traffic-light/tech')
      await page.getByLabel('Решено за неделю: граница зелёного').fill(String(last.total_solved_week + 10))
      await page.getByLabel('Решено за неделю: граница жёлтого').fill(String(last.total_solved_week + 5))
      await page.getByRole('button', { name: 'Сохранить все (1)' }).click()
      await expect(page.getByRole('button', { name: /Сохранить все/ })).toHaveCount(0)
      await page.goto('/tp?quick=1')
      await expect(kpi(page, 'Решено заявок')).toHaveClass(/l-red/)
    } finally {
      await api(page, 'PUT', '/traffic-light/tech/total_solved_week', restoreBody(original)).catch(() => {})
    }
  })

  test('несохранённые пороги не теряются при переходе между службами', async ({ page }) => {
    await login(page)
    await page.goto('/settings/traffic-light/hr')
    await page.getByLabel('Текучесть кадров: граница зелёного').fill('0,5')
    await expect(page.getByRole('button', { name: 'Сохранить все (1)' })).toBeVisible()
    // Переход по меню к светофору техподдержки — тот же экран с другой службой
    await page.locator('a[href="/settings/traffic-light/tech"]').first().click()
    const ask = page.getByRole('dialog', { name: 'Уйти без сохранения?' })
    await expect(ask).toBeVisible()
    await ask.getByRole('button', { name: 'Отмена' }).click()
    await expect(page).toHaveURL(/traffic-light\/hr/)
    await expect(page.getByLabel('Текучесть кадров: граница зелёного')).toHaveValue('0,5')
    await page.locator('a[href="/settings/traffic-light/tech"]').first().click()
    await confirmDialog(page, 'Уйти')
    await expect(page).toHaveURL(/traffic-light\/tech/)
    await expect(page.getByRole('heading', { level: 1 })).toContainText('Техническая поддержка')
    expect((await rule(page, 'hr', 'turnover')).green_threshold).not.toBe(0.5)
  })

  test('партнёрства: цвет правила меняет светофор записей', async ({ page }) => {
    await login(page)
    const before = await apiGet(page, '/partnerships/light-rules')
    const ndaNo = before.find((r) => r.key === 'nda:no')
    expect(ndaNo.light).not.toBe('red')
    try {
      await page.goto('/settings/partnership-lights')
      await page.getByRole('radiogroup', { name: 'NDA не подписан' }).getByRole('radio', { name: 'Критично' }).click()
      await page.getByRole('button', { name: 'Сохранить (1)' }).click()
      await expect(page.getByRole('button', { name: 'Сохранить', exact: true })).toBeDisabled()
      const records = await apiGet(page, '/partnerships')
      const withoutNda = records.filter((r) => !r.nda)
      expect(withoutNda.length).toBeGreaterThan(0)
      expect(withoutNda.every((r) => r.light === 'red')).toBe(true)
      const red = records.filter((r) => r.light === 'red').length
      await page.goto('/product')
      await expect(page.locator('.legend-item', { hasText: 'Критично' }).locator('b')).toHaveText(String(red))
      await page.goto('/product/registry?light=red')
      await expect(page.locator('.strip-count')).toHaveText(`${red} из ${records.length}`)
    } finally {
      await api(page, 'PUT', '/partnerships/light-rules', [{ key: 'nda:no', light: ndaNo.light }]).catch(() => {})
    }
  })

  test('права: viewer не настраивает светофор, менеджер партнёрств — настраивает', async ({ page }) => {
    await login(page, 'viewer')
    await page.goto('/settings/partnership-lights')
    await expect(page.getByRole('radiogroup')).toHaveCount(0)
    await page.goto('/settings/traffic-light/tech')
    await expect(page.getByRole('heading', { name: 'Нет доступа' })).toBeVisible()
    await page.context().clearCookies()
    await login(page, 'product')
    await page.goto('/settings/partnership-lights')
    await expect(page.getByRole('radiogroup').first()).toBeVisible()
  })
})
