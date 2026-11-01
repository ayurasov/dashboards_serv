import { expect, test } from '@playwright/test'
import { api, apiGet, collectErrors, confirmDialog, expectDownload, kpi, kpiValue, login, ru } from './helpers'

/** Неделя, которой нет в демо-данных: тест добавляет и удаляет её сам. */
const TEST_WEEK = { year: 2030, week: 1, period: '2030-W01' }

const sum = (rows, key) => rows.reduce((s, r) => s + (r[key] ?? 0), 0)
const avg = (rows, key) => {
  const vals = rows.map((r) => r[key]).filter((v) => v !== null && v !== undefined)
  return vals.reduce((s, v) => s + v, 0) / vals.length
}

async function sortedReports(page) {
  const rows = await apiGet(page, '/tp/reports')
  return rows.sort((a, b) => a.year - b.year || a.week - b.week)
}

async function dropWeek(page, { year, week }) {
  for (const r of await apiGet(page, `/tp/reports?year=${year}`)) if (r.week === week) await api(page, 'DELETE', `/tp/reports/${r.id}`)
}

test.describe('техническая поддержка', () => {
  test.describe.configure({ timeout: 90_000 })

  test('дашборд: светофор совпадает с данными отчёта, период меняет его и хранится в адресе', async ({ page }) => {
    const errors = collectErrors(page)
    await login(page)
    const rows = await sortedReports(page)
    await page.goto('/tp')
    const last26 = rows.slice(-26)
    await expect(page.locator('.page-header')).toContainText(`${last26[0].period} — ${last26.at(-1).period} · 26 недель`)
    await expect.poll(() => kpiValue(page, 'Решено заявок')).toBe(sum(last26, 'total_solved_week'))
    await expect(kpi(page, 'В работе, в среднем').locator('.value')).toHaveText(`${ru(avg(last26, 'total_in_work'), 1)}шт.`)
    expect(await kpiValue(page, 'Трудозатраты')).toBe(sum(last26, 'avail_total'))

    await page.getByRole('button', { name: '8 недель' }).click()
    await expect(page).toHaveURL(/quick=8/)
    const last8 = rows.slice(-8)
    await expect.poll(() => kpiValue(page, 'Решено заявок')).toBe(sum(last8, 'total_solved_week'))
    await expect(page.locator('.page-header')).toContainText('8 недель')
    // Изменение — к 8 неделям перед ними
    const prev8 = rows.slice(-16, -8)
    const pct = ((sum(last8, 'total_solved_week') - sum(prev8, 'total_solved_week')) / sum(prev8, 'total_solved_week')) * 100
    await expect(kpi(page, 'Решено заявок').locator('.delta')).toContainText(`${Math.abs(pct).toLocaleString('ru-RU', { maximumFractionDigits: 1 })}%`)
    await expect(kpi(page, 'Решено заявок')).toContainText('к пред. 8 нед.')

    await page.reload()
    await expect.poll(() => kpiValue(page, 'Решено заявок')).toBe(sum(last8, 'total_solved_week'))

    // Один год и диапазон недель
    await page.getByRole('button', { name: 'Всё время' }).click()
    await page.locator('.chip', { hasText: /^2026$/ }).click()
    await page.locator('.chip', { hasText: /^2024$/ }).click()
    await expect(page).toHaveURL(/years=2025/)
    await page.getByLabel('Неделя с').selectOption('10')
    await page.getByLabel('Неделя по').selectOption('19')
    await expect(page).toHaveURL(/from=10/)
    await expect(page).toHaveURL(/to=19/)
    const span = rows.filter((r) => r.year === 2025 && r.week >= 10 && r.week <= 19)
    await expect.poll(() => kpiValue(page, 'Решено заявок')).toBe(sum(span, 'total_solved_week'))
    await expect(page.locator('.page-header')).toContainText(`${span.length} недель`)
    // Нечётное число недель: половины периода равной длины (средняя неделя не сравнивается)
    await page.getByLabel('Неделя по').selectOption('12')
    const three = rows.filter((r) => r.year === 2025 && r.week >= 10 && r.week <= 12)
    expect(three).toHaveLength(3)
    const pct3 = ((three[2].total_solved_week - three[0].total_solved_week) / three[0].total_solved_week) * 100
    await expect(kpi(page, 'Решено заявок').locator('.delta')).toContainText(`${Math.abs(pct3).toLocaleString('ru-RU', { maximumFractionDigits: 1 })}%`)
    await expect(kpi(page, 'Решено заявок')).toContainText('к 1-й половине периода')
    expect(errors).toEqual([])
  })

  test('дашборд: раскладка блоков сохраняется после перезагрузки', async ({ page }) => {
    await login(page)
    await api(page, 'DELETE', '/layouts/tech')
    await page.goto('/tp')
    await expect(page.getByRole('heading', { name: 'Каналы обращений' })).toBeVisible()
    await page.getByRole('button', { name: 'Настроить' }).click()
    const dialog = page.getByRole('dialog', { name: 'Настроить дашборд' })
    await dialog.getByLabel('Каналы обращений').uncheck()
    await dialog.getByRole('button', { name: 'Сохранить' }).click()
    await page.reload()
    await expect(page.getByRole('heading', { name: 'Поток заявок' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Каналы обращений' })).toHaveCount(0)
    await api(page, 'DELETE', '/layouts/tech')
    await page.reload()
    await expect(page.getByRole('heading', { name: 'Каналы обращений' })).toBeVisible()
  })

  test('недельный отчёт: неделя уникальна, добавление и удаление с подтверждением', async ({ page }) => {
    const errors = collectErrors(page)
    await login(page)
    await dropWeek(page, TEST_WEEK)
    const rows = await sortedReports(page)
    const existing = rows.at(-1)
    try {
      await page.goto('/tp/registry')
      await page.getByRole('button', { name: 'Добавить неделю' }).first().click()
      const dialog = page.getByRole('dialog', { name: 'Новая неделя отчёта' })
      await dialog.getByLabel('Год').fill(String(existing.year))
      await dialog.getByLabel('Номер недели').fill(String(existing.week))
      await dialog.getByLabel('Итого в работе заявок').fill('10')
      await dialog.getByRole('button', { name: 'Сохранить' }).click()
      await expect(dialog.getByText('Неделя уже заполнена')).toBeVisible()
      await expect(dialog).toBeVisible()
      // Ошибка показана у поля — без второго всплывающего сообщения
      await expect(page.locator('.toast', { hasText: 'уже есть в отчёте' })).toHaveCount(0)
      // Номер недели больше, чем недель в году
      await dialog.getByLabel('Год').fill(String(TEST_WEEK.year))
      await dialog.getByLabel('Номер недели').fill('54')
      await dialog.getByRole('button', { name: 'Сохранить' }).click()
      await expect(dialog.getByText(/В 2030 году 52 недели/)).toBeVisible()
      await dialog.getByLabel('Номер недели').fill(String(TEST_WEEK.week))
      await dialog.getByLabel('Итого в работе заявок').fill('12,5')
      await dialog.getByRole('button', { name: 'Сохранить' }).click()
      await expect(dialog).toBeHidden()
      const created = (await apiGet(page, `/tp/reports?year=${TEST_WEEK.year}`)).find((r) => r.week === TEST_WEEK.week)
      expect(created.total_in_work).toBe(12.5)

      await page.getByLabel('Поиск по периоду').fill(TEST_WEEK.period)
      const row = page.locator('tbody tr', { hasText: TEST_WEEK.period })
      await expect(row).toHaveCount(1)
      await row.click()
      const edit = page.getByRole('dialog', { name: `Неделя ${TEST_WEEK.period}` })
      await edit.getByRole('button', { name: 'Удалить неделю' }).click()
      const confirmBox = page.getByRole('dialog', { name: `Удалить неделю ${TEST_WEEK.period}?` })
      await expect(confirmBox).toBeVisible()
      // Esc закрывает только подтверждение — форма недели остаётся открытой
      await page.keyboard.press('Escape')
      await expect(confirmBox).toBeHidden()
      await expect(edit).toBeVisible()
      await edit.getByRole('button', { name: 'Удалить неделю' }).click()
      await confirmDialog(page, 'Удалить')
      await expect(edit).toBeHidden()
      await expect(page.locator('tbody tr', { hasText: TEST_WEEK.period })).toHaveCount(0)
    } finally {
      await dropWeek(page, TEST_WEEK).catch(() => {})
    }
    expect(errors).toEqual([])
  })

  test('недельный отчёт: выгрузка Excel и повторная загрузка в режиме «Дополнить» не создаёт недель', async ({ page }) => {
    await login(page)
    const before = await sortedReports(page)
    await page.goto('/tp/registry')
    const { body } = await expectDownload(page, () => page.getByRole('button', { name: 'Excel' }).click(), { ext: 'xlsx', name: 'Итоговый отчёт ТП по неделям' })
    await expectDownload(page, () => page.getByRole('button', { name: 'CSV' }).click(), { ext: 'csv', name: 'Отчёт ТП по неделям' })
    await expectDownload(page, () => page.getByRole('button', { name: 'PDF' }).click(), { ext: 'pdf', name: 'Техподдержка — отчёт' })

    await page.getByRole('button', { name: 'Загрузить файл' }).click()
    const dialog = page.getByRole('dialog', { name: 'Загрузка недельного отчёта' })
    await dialog.locator('input[type=file]').setInputFiles({ name: 'roundtrip.xlsx', mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', buffer: body })
    await expect(dialog.getByText('roundtrip.xlsx')).toBeVisible()
    await expect(dialog.getByRole('radio', { name: 'Дополнить' }).or(dialog.getByRole('button', { name: 'Дополнить' })).first()).toHaveAttribute('aria-checked', 'true')
    await dialog.getByRole('button', { name: 'Загрузить' }).click()
    await expect(dialog.getByText('Загрузка завершена')).toBeVisible()
    await expect(dialog.locator('li', { hasText: 'Добавлено' })).toHaveText('Добавлено: 0')
    await expect(dialog.locator('li', { hasText: 'Обновлено' })).toHaveText(`Обновлено: ${before.length}`)
    await dialog.getByRole('button', { name: 'Готово' }).click()

    const after = await sortedReports(page)
    expect(after.length).toBe(before.length)
    const strip = (r) => Object.fromEntries(Object.entries(r).filter(([k]) => !['id', 'updated_at'].includes(k)))
    expect(after.map(strip)).toEqual(before.map(strip))
  })

  test('сравнение периодов: интервалы одинаковой длины, суммы совпадают с отчётом', async ({ page }) => {
    await login(page)
    const rows = await sortedReports(page)
    await page.goto('/tp/compare')
    await page.getByRole('button', { name: 'Месяц' }).click()
    await expect(page).toHaveURL(/quick=4/)
    const now = rows.slice(-4)
    const prev = rows.slice(-8, -4)
    await expect(page.getByText('Последние 4 недели', { exact: true }).first()).toBeVisible()
    await expect(page.getByText(`${now[0].period} — ${now.at(-1).period}`)).toBeVisible()
    await expect(page.getByText(`${prev[0].period} — ${prev.at(-1).period}`)).toBeVisible()
    const row = page.locator('tbody tr', { has: page.locator('td', { hasText: /^Решено за неделю$/ }) })
    await expect(row.locator('td').nth(1)).toContainText(ru(sum(now, 'total_solved_week')))
    await expect(row.locator('td').nth(2)).toContainText(ru(sum(prev, 'total_solved_week')))
    const delta = sum(now, 'total_solved_week') - sum(prev, 'total_solved_week')
    await expect(row.locator('td').nth(3)).toContainText(`${delta > 0 ? '+' : delta < 0 ? '−' : '±'}${ru(Math.abs(delta))}`)
    await page.reload()
    await expect(page.getByText('Последние 4 недели', { exact: true }).first()).toBeVisible()
  })

  test('заявки Naumen: год и организация фильтруют показатели и хранятся в адресе', async ({ page }) => {
    const errors = collectErrors(page)
    await login(page)
    await page.goto('/tp/naumen')
    const def = await apiGet(page, '/tp/naumen/summary?months=12')
    await expect.poll(() => kpiValue(page, 'Всего заявок')).toBe(def.total)
    expect(await kpiValue(page, 'Закрыто')).toBe(def.closed)

    await page.locator('.chip', { hasText: /^2025$/ }).click()
    await expect(page).toHaveURL(/year=2025/)
    const y2025 = await apiGet(page, '/tp/naumen/summary?year=2025')
    await expect.poll(() => kpiValue(page, 'Всего заявок')).toBe(y2025.total)
    // Помесячные графики года — только месяцы 2025 года (решённые позже заявки не растягивают ось)
    expect(y2025.months.every((m) => m.month.startsWith('2025'))).toBe(true)
    await expect(kpi(page, 'Всего заявок')).toContainText(`зарегистрировано за ${y2025.months.length} `)
    expect(await kpiValue(page, 'Просрочено')).toBe(y2025.overdue)
    await expect(kpi(page, 'Просрочено')).toContainText(`${ru(y2025.overdue_pct, 1)}% от всех заявок`)

    const org = y2025.orgs[0].org
    await page.getByLabel('Организация').selectOption(org)
    await expect(page).toHaveURL(/org=/)
    const byOrg = await apiGet(page, `/tp/naumen/summary?year=2025&org=${encodeURIComponent(org)}`)
    await expect.poll(() => kpiValue(page, 'Всего заявок')).toBe(byOrg.total)
    await page.reload()
    await expect.poll(() => kpiValue(page, 'Всего заявок')).toBe(byOrg.total)
    await expect(page.getByLabel('Организация')).toHaveValue(org)

    const { response } = await expectDownload(page, () => page.getByRole('button', { name: 'PDF' }).click(), { ext: 'pdf', name: 'Техподдержка — заявки Naumen' })
    expect(response.url()).toContain('year=2025')

    await page.getByRole('button', { name: 'Сбросить' }).first().click()
    await expect(page).not.toHaveURL(/year=|org=/)
    await expect.poll(() => kpiValue(page, 'Всего заявок')).toBe(def.total)
    expect(errors).toEqual([])
  })

  test('отчёт и Naumen: показатели совпадают с сопоставлением API', async ({ page }) => {
    await login(page)
    const match = await apiGet(page, '/tp/naumen/match')
    await page.goto('/tp/analytics')
    const weeks = match.weeks.slice(-26)
    await expect.poll(() => kpiValue(page, 'Принято по отчёту')).toBe(sum(weeks, 'tp_new_received'))
    expect(await kpiValue(page, 'Зарегистрировано в Naumen')).toBe(sum(weeks, 'naumen_registered'))
    expect(await kpiValue(page, 'Просрочено в Naumen')).toBe(sum(weeks, 'naumen_overdue'))

    await page.getByRole('button', { name: 'Месяцы' }).or(page.getByRole('radio', { name: 'Месяцы' })).first().click()
    await expect(page).toHaveURL(/by=months/)
    const months = match.months.filter((m) => m.tp_new_received !== null).slice(-12)
    await expect.poll(() => kpiValue(page, 'Принято по отчёту')).toBe(sum(months, 'tp_new_received'))
    await page.locator('.chip', { hasText: /^2025$/ }).click()
    await expect(page).toHaveURL(/year=2025/)
    const y = match.months.filter((m) => m.tp_new_received !== null && m.year === 2025)
    await expect.poll(() => kpiValue(page, 'Зарегистрировано в Naumen')).toBe(sum(y, 'naumen_registered'))
  })

  test('права: tp_lead правит отчёт, но не видит службу персонала; viewer только смотрит', async ({ page }) => {
    await login(page, 'tp_lead')
    await page.goto('/tp/registry')
    await expect(page.getByRole('button', { name: 'Добавить неделю' }).first()).toBeVisible()
    await expect(page.getByRole('button', { name: 'Загрузить файл' })).toBeVisible()
    await page.goto('/settings/traffic-light/tech')
    await expect(page.getByRole('heading', { level: 1 })).toContainText('Светофор')
    await page.goto('/settings/traffic-light/hr')
    await expect(page.getByRole('heading', { name: 'Нет доступа' })).toBeVisible()
    const denied = await page.request.get('/api/hr/analytics/dashboard')
    expect(denied.status()).toBe(403)

    await page.context().clearCookies()
    await login(page, 'viewer')
    await page.goto('/tp/registry')
    await expect(page.getByRole('heading', { level: 1 })).toContainText('Недельный отчёт')
    await expect(page.getByRole('button', { name: 'Добавить неделю' })).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'Загрузить файл' })).toHaveCount(0)
    await page.goto('/tp/naumen')
    await expect(page.getByRole('button', { name: 'Загрузить выгрузку' })).toHaveCount(0)
  })
})
