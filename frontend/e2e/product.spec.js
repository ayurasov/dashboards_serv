import { expect, test } from '@playwright/test'
import { api, apiGet, collectErrors, confirmDialog, expectDownload, kpi, kpiValue, login, ru, uniq } from './helpers'

async function dropByPartner(page, prefix) {
  for (const p of await apiGet(page, `/partnerships?search=${encodeURIComponent(prefix)}`)) {
    if (p.partner.startsWith(prefix)) await api(page, 'DELETE', `/partnerships/${p.id}`)
  }
}

function isoToday() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

test.describe('партнёрства', () => {
  test.describe.configure({ timeout: 90_000 })

  test('дашборд: показатели совпадают с API, фильтры меняют их и хранятся в адресе', async ({ page }) => {
    const errors = collectErrors(page)
    await login(page)
    await page.goto('/product')
    const all = await apiGet(page, '/partnerships/analytics')
    await expect.poll(() => kpiValue(page, 'Всего партнёрств')).toBe(all.total)
    expect(await kpiValue(page, 'Завершено')).toBe(all.by_status['Завершено'] || 0)
    await expect(kpi(page, 'NDA подписан').locator('.value')).toHaveText(`${ru(Math.round((all.nda_count / all.total) * 1000) / 10, 1)}%`)
    const records = await apiGet(page, '/partnerships')
    const green = records.filter((r) => r.light === 'green').length
    await expect(page.getByRole('img', { name: new RegExp(`^Норма: ${green},`) })).toBeVisible()
    await expect(page.locator('.legend-item', { hasText: 'Норма' }).locator('b')).toHaveText(String(green))

    await page.getByLabel('Год сертификации').selectOption('2024')
    await expect(page).toHaveURL(/year=2024/)
    const y = await apiGet(page, '/partnerships/analytics?year=2024')
    await expect.poll(() => kpiValue(page, 'Всего партнёрств')).toBe(y.total)
    expect(y.total).toBeLessThan(all.total)
    await page.reload()
    await expect(page.getByLabel('Год сертификации')).toHaveValue('2024')
    await expect.poll(() => kpiValue(page, 'Всего партнёрств')).toBe(y.total)
    await expectDownload(page, () => page.getByRole('button', { name: 'PDF' }).click(), { ext: 'pdf', name: 'Партнёрства — сводка' })
    expect(errors).toEqual([])
  })

  test('реестр: добавление с проверкой, изменение меняет светофор, удаление', async ({ page }) => {
    const errors = collectErrors(page)
    await login(page)
    const prefix = 'E2E Партнёр'
    await dropByPartner(page, prefix)
    const name = `${prefix} ${uniq('')}`
    try {
      await page.goto('/product/registry')
      await page.locator('.page-header').getByRole('button', { name: 'Добавить' }).click()
      const form = page.getByRole('dialog', { name: 'Новое партнёрство' })
      await form.getByRole('button', { name: 'Добавить' }).click()
      await expect(form.getByText('Укажите партнёра')).toBeVisible()
      await form.getByPlaceholder('ООО «Название»').fill(name)
      await form.getByLabel('Продукт партнёра').fill('Тестовый продукт')
      await form.getByLabel('Продукт АЛМИ', { exact: true }).fill('АльтерОС')
      await form.getByLabel('Статус').selectOption('Завершено')
      await form.getByLabel('Дата сертификата').fill(isoToday())
      await form.getByLabel('NDA подписан').check()
      await form.getByLabel('Соглашение подписано').check()
      await form.getByRole('button', { name: 'Добавить' }).click()
      await expect(form).toBeHidden()

      await page.getByLabel('Поиск').fill(name)
      const row = page.locator('tbody tr', { hasText: name })
      await expect(row).toHaveCount(1)
      await expect(row.getByLabel('Светофор: Норма')).toBeVisible()
      await expect(row).toContainText('Завершено')

      // Без NDA запись требует внимания
      await row.getByTitle('Изменить').click()
      const edit = page.getByRole('dialog', { name: 'Изменить партнёрство' })
      await edit.getByLabel('NDA подписан').uncheck()
      await edit.getByRole('button', { name: 'Сохранить' }).click()
      await expect(edit).toBeHidden()
      await expect(row.getByLabel('Светофор: Внимание')).toBeVisible()
      const saved = (await apiGet(page, `/partnerships?search=${encodeURIComponent(name)}`))[0]
      expect(saved.light).toBe('yellow')
      expect(saved.light_parts.nda).toBe('yellow')

      // Фильтр светофора и выгрузка с фильтрами
      await page.locator('label.field', { hasText: 'Светофор' }).locator('select').selectOption('yellow')
      await expect(page).toHaveURL(/light=yellow/)
      await expect(row).toHaveCount(1)
      const { response } = await expectDownload(page, () => page.getByRole('button', { name: 'Excel' }).click(), { ext: 'xlsx', name: 'Реестр технологических партнёрств' })
      expect(response.url()).toContain('light=yellow')
      await expectDownload(page, () => page.getByRole('button', { name: 'PDF' }).click(), { ext: 'pdf', name: 'Партнёрства — реестр' })

      // Удаление из формы: Esc закрывает только подтверждение
      await row.getByTitle('Изменить').click()
      await edit.getByRole('button', { name: 'Удалить' }).click()
      await expect(page.getByRole('dialog', { name: 'Удалить партнёрство?' })).toBeVisible()
      await page.keyboard.press('Escape')
      await expect(page.getByRole('dialog', { name: 'Удалить партнёрство?' })).toBeHidden()
      await expect(edit).toBeVisible()
      await edit.getByRole('button', { name: 'Удалить' }).click()
      await confirmDialog(page, 'Удалить')
      await expect(edit).toBeHidden()
      await expect(page.locator('tbody tr', { hasText: name })).toHaveCount(0)
      expect(await apiGet(page, `/partnerships?search=${encodeURIComponent(name)}`)).toEqual([])
    } finally {
      await dropByPartner(page, prefix).catch(() => {})
    }
    expect(errors).toEqual([])
  })

  test('сводка по годам и хронология совпадают с API', async ({ page }) => {
    const errors = collectErrors(page)
    await login(page)
    const summary = await apiGet(page, '/partnerships/summary')
    await page.goto('/product/summary')
    const years = Array.isArray(summary) ? summary : summary.years
    const last = years.at(-1)
    await expect(page.getByText(String(last.year)).first()).toBeVisible()
    await expect(page.locator('table').first()).toContainText(String(last.total))
    await expectDownload(page, () => page.getByRole('button', { name: 'PDF' }).click(), { ext: 'pdf', name: 'Партнёрства — сводка' })
    await page.goto('/product/timeline')
    await expect(page.getByRole('heading', { level: 1 })).toContainText('Хронология')
    expect(errors).toEqual([])
  })

  test('права: viewer видит реестр без изменения, tp_lead — без доступа', async ({ page }) => {
    await login(page, 'viewer')
    await page.goto('/product/registry')
    await expect(page.locator('tbody tr').first()).toBeVisible()
    await expect(page.locator('.page-header').getByRole('button', { name: 'Добавить' })).toHaveCount(0)
    await expect(page.locator('tbody tr').first().getByTitle('Изменить')).toHaveCount(0)
    await page.context().clearCookies()
    await login(page, 'tp_lead')
    await page.goto('/product')
    await expect(page.getByRole('heading', { name: 'Нет доступа' })).toBeVisible()
  })
})
