import { expect, test } from '@playwright/test'
import { api, apiGet, canvasColorShare, collectErrors, confirmDialog, expectDownload, kpi, kpiValue, login, num, ru, uniq } from './helpers'

/** Месяц, которого нет в демо-данных: тест ввода данных создаёт и удаляет его сам. */
const TEST_MONTH = { year: 2099, month: 12, key: '2099-12', label: 'Декабрь 2099' }

async function dropMonth(page, key) {
  const months = await apiGet(page, '/hr/months')
  if (months.some((m) => m.key === key)) await api(page, 'DELETE', `/hr/months/${key}`)
}

test.describe('служба персонала', () => {
  test.describe.configure({ timeout: 90_000 })

  test('дашборд: показатели совпадают с API, период меняет их и хранится в адресе', async ({ page }) => {
    const errors = collectErrors(page)
    await login(page)
    await page.goto('/hr')
    const months = await apiGet(page, '/hr/months')
    const keys = months.map((m) => m.key)
    const six = keys.slice(-6)
    const dash = await apiGet(page, `/hr/analytics/dashboard?months=${six.join(',')}`)

    await expect(page.locator('.page-header').getByText(`${dash.series[0].label} — ${dash.series.at(-1).label}`)).toBeVisible()
    await expect.poll(() => kpiValue(page, 'Принято за период')).toBe(dash.totals.hired)
    expect(await kpiValue(page, 'Уволено за период')).toBe(dash.totals.fired)
    expect(await kpiValue(page, 'Чистый прирост')).toBe(dash.totals.net)
    const turnover = dash.latest.metrics.find((m) => m.key === 'turnover')
    await expect(kpi(page, 'Текучесть кадров').locator('.value')).toHaveText(`${ru(turnover.value)}%`)
    await expect(kpi(page, 'Текучесть кадров')).toHaveClass(new RegExp(`l-${turnover.light}`))
    await expect(page.getByRole('heading', { name: `Все метрики за ${dash.latest.label}` })).toBeVisible()

    // Быстрый период «3 месяца»: суммы — за три последних месяца, выбор — в адресе
    await page.getByRole('button', { name: '3 месяца' }).click()
    await expect(page).toHaveURL(/quick=3/)
    const last3 = months.slice(-3)
    await expect.poll(() => kpiValue(page, 'Принято за период')).toBe(last3.reduce((s, m) => s + m.hired, 0))
    expect(await kpiValue(page, 'Уволено за период')).toBe(last3.reduce((s, m) => s + m.fired, 0))

    // Отдельный месяц снимается с выбора — суммы пересчитываются, выбор переживает перезагрузку
    await page.locator('.chip.month', { hasText: /^\s*июл 26\s*$/i }).click()
    await expect(page).toHaveURL(/months=2026-05%2C2026-06|months=2026-05,2026-06/)
    const expected = last3.slice(0, 2).reduce((s, m) => s + m.hired, 0)
    await expect.poll(() => kpiValue(page, 'Принято за период')).toBe(expected)
    await page.reload()
    await expect.poll(() => kpiValue(page, 'Принято за период')).toBe(expected)
    await expect(page.locator('.chip.month.active')).toHaveCount(2)
    await page.getByRole('button', { name: 'Сбросить' }).click()
    await expect(page).not.toHaveURL(/months=/)
    expect(errors).toEqual([])
  })

  test('дашборд: цель текучести видна на графике, даже если она выше всех значений', async ({ page }) => {
    await login(page)
    await page.goto('/hr')
    const card = page.locator('.chart-card', { has: page.getByRole('heading', { name: 'Текучесть кадров' }) })
    await expect(card.locator('canvas')).toBeVisible()
    const target = (await apiGet(page, '/hr/targets')).find((t) => t.metric_key === 'turnover' && t.year === 2026)
    const dash = await apiGet(page, '/hr/analytics/dashboard')
    const max = Math.max(...dash.series.map((s) => s.metrics.find((m) => m.key === 'turnover').value ?? 0))
    expect(target.target_value).toBeGreaterThan(max)
    // Линия цели рисуется красным пунктиром — других красных элементов на графике нет
    const red = await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue('--light-red').trim())
    await expect.poll(() => canvasColorShare(card, red, 10)).toBeGreaterThan(30)
  })

  test('дашборд: ошибка загрузки — понятное сообщение и повтор, а не «нет данных»', async ({ page }) => {
    await login(page)
    let fail = true
    await page.route('**/api/hr/analytics/dashboard*', (route) => (fail
      ? route.fulfill({ status: 500, contentType: 'application/json', body: '{"detail":"Сервис временно недоступен"}' })
      : route.continue()))
    await page.goto('/hr')
    await expect(page.getByText('Не удалось загрузить дашборд')).toBeVisible()
    await expect(page.locator('.page').getByText('Сервис временно недоступен').first()).toBeVisible()
    await expect(page.getByText('Нет данных за выбранный период')).toHaveCount(0)
    fail = false
    await page.getByRole('button', { name: 'Повторить' }).click()
    await expect(page.getByText('Не удалось загрузить дашборд')).toHaveCount(0)
    await expect.poll(() => kpiValue(page, 'Принято за период')).not.toBeNull()
  })

  test('дашборд: раскладка блоков сохраняется после перезагрузки', async ({ page }) => {
    await login(page)
    await api(page, 'DELETE', '/layouts/hr')
    await page.goto('/hr')
    await expect(page.getByRole('heading', { name: 'Воронка найма' })).toBeVisible()
    await page.getByRole('button', { name: 'Настроить' }).click()
    const dialog = page.getByRole('dialog', { name: 'Настроить дашборд' })
    await dialog.getByLabel('Воронка найма').uncheck()
    // «Все метрики месяца» — наверх
    const row = dialog.locator('li', { hasText: 'Все метрики месяца' })
    for (let i = 0; i < 6; i++) await row.getByTitle('Выше').click()
    await dialog.getByRole('button', { name: 'Сохранить' }).click()
    await expect(dialog).toBeHidden()
    await expect(page.getByRole('heading', { name: 'Воронка найма' })).toHaveCount(0)

    await page.reload()
    await expect(page.getByRole('heading', { name: /^Все метрики за/ })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Воронка найма' })).toHaveCount(0)
    const tableTop = (await page.getByRole('heading', { name: /^Все метрики за/ }).boundingBox()).y
    const kpiTop = (await page.getByRole('heading', { name: 'Ключевые показатели' }).boundingBox()).y
    expect(tableTop).toBeLessThan(kpiTop)

    await page.getByRole('button', { name: 'Настроить' }).click()
    await page.getByRole('dialog').getByRole('button', { name: 'По умолчанию' }).click()
    await expect(page.getByRole('heading', { name: 'Воронка найма' })).toBeVisible()
    const layout = await apiGet(page, '/layouts/hr')
    expect(layout.widgets).toEqual([])
  })

  test('мои дашборды: создание, изменение и удаление', async ({ page }) => {
    const errors = collectErrors(page)
    await login(page)
    for (const d of await apiGet(page, '/dashboards')) if (d.name.startsWith('Дашборд-')) await api(page, 'DELETE', `/dashboards/${d.id}`)
    const name = uniq('Дашборд')
    const renamed = `${name} — изменён`
    const dash = await apiGet(page, '/hr/analytics/dashboard')
    const turnover = dash.latest.metrics.find((m) => m.key === 'turnover')

    await page.goto('/hr/dashboards')
    await page.locator('.page-header').getByRole('button', { name: 'Создать дашборд' }).first().click()
    const editor = page.getByRole('dialog', { name: 'Новый дашборд' })
    await editor.getByRole('button', { name: 'Сохранить' }).click()
    await expect(editor.getByText('Введите название')).toBeVisible()
    await editor.getByPlaceholder('Например, «Найм и адаптация»').fill(name)
    await editor.getByRole('button', { name: 'Карточка метрики' }).click()
    await editor.getByRole('button', { name: 'Сохранить' }).click()
    await expect(editor.getByText('Проверьте настройки виджетов')).toBeVisible()
    await editor.getByLabel('Метрика', { exact: true }).selectOption('turnover')
    await editor.getByRole('button', { name: 'Заметка' }).click()
    await editor.getByLabel('Текст заметки').fill('Проверка e2e')
    await editor.getByRole('button', { name: 'Сохранить' }).click()
    await expect(editor).toBeHidden()

    await expect(page.getByRole('heading', { level: 2, name })).toBeVisible()
    await expect(page).toHaveURL(/id=\d+/)
    await expect(kpi(page, 'Текучесть кадров').locator('.value')).toHaveText(`${ru(turnover.value)}%`)
    await expect(page.getByText('Проверка e2e')).toBeVisible()

    await page.getByRole('button', { name: 'Изменить' }).click()
    const edit = page.getByRole('dialog', { name: 'Изменить дашборд' })
    await edit.getByPlaceholder('Например, «Найм и адаптация»').fill(renamed)
    await edit.getByRole('button', { name: 'Сохранить' }).click()
    await expect(page.getByRole('heading', { level: 2, name: renamed })).toBeVisible()
    await page.reload()
    await expect(page.getByRole('heading', { level: 2, name: renamed })).toBeVisible()

    await page.getByTitle('Удалить дашборд').click()
    await confirmDialog(page, 'Удалить')
    await expect(page.getByRole('heading', { level: 2, name: renamed })).toHaveCount(0)
    const list = await apiGet(page, '/dashboards')
    expect(list.some((d) => d.name.startsWith(name))).toBe(false)
    expect(errors).toEqual([])
  })

  test('ввод данных: сохранённое значение месяца появляется на дашборде', async ({ page }) => {
    const errors = collectErrors(page)
    await login(page)
    await dropMonth(page, TEST_MONTH.key)
    try {
      await page.goto('/hr/data')
      await page.locator('.page-header').getByRole('button', { name: 'Добавить месяц' }).click()
      const dialog = page.getByRole('dialog', { name: 'Новый месяц' })
      await dialog.getByLabel('Год').fill(String(TEST_MONTH.year))
      await dialog.getByLabel('Месяц').selectOption(String(TEST_MONTH.month))
      await dialog.getByRole('button', { name: 'Добавить месяц' }).click()
      await expect(dialog).toBeHidden()
      await expect(page).toHaveURL(new RegExp(`month=${TEST_MONTH.key}`))
      await expect(page.getByRole('heading', { name: TEST_MONTH.label })).toBeVisible()

      const input = page.locator('#v-total_employees')
      await input.fill('1 234,5')
      await page.locator('#v-turnover').fill('abc')
      await expect(page.getByText('Исправьте 1 значение: нужно число')).toBeVisible()
      await expect(page.getByRole('button', { name: 'Сохранить', exact: true })).toBeDisabled()
      await page.locator('#v-turnover').fill('7,5')
      await expect(page.getByText('Изменено 2 значения')).toBeVisible()
      await page.getByRole('button', { name: 'Сохранить', exact: true }).click()
      await expect(page.getByText('Изменений нет')).toBeVisible()
      await expect(page.getByText('заполнено 1 из 1')).toBeVisible()

      const month = await apiGet(page, `/hr/months/${TEST_MONTH.key}`)
      expect(month.metrics.find((m) => m.key === 'total_employees').value).toBe(1234.5)

      await page.goto(`/hr?months=${TEST_MONTH.key}`)
      await expect(page.getByRole('heading', { name: `Все метрики за ${TEST_MONTH.label}` })).toBeVisible()
      const row = page.locator('tr', { hasText: 'Всего сотрудников' })
      await expect(row.locator('td').nth(1)).toHaveText('1 234,5 чел.')
      await expect(kpi(page, 'Текучесть кадров').locator('.value')).toHaveText('7,5%')
      // Один месяц: изменения к прошлому месяцу в карточке нет, график строится по одной точке
      await expect(page.locator('.chart-card', { hasText: 'Приём и увольнение' }).locator('canvas')).toBeVisible()

      await page.goto(`/hr/data?month=${TEST_MONTH.key}`)
      await page.getByRole('button', { name: 'Удалить месяц' }).click()
      await confirmDialog(page, 'Удалить месяц')
      await expect(page.getByRole('heading', { name: TEST_MONTH.label })).toHaveCount(0)
      expect((await apiGet(page, '/hr/months')).some((m) => m.key === TEST_MONTH.key)).toBe(false)
    } finally {
      await dropMonth(page, TEST_MONTH.key).catch(() => {})
    }
    expect(errors).toEqual([])
  })

  test('реестр: добавление, проверка полей, изменение и удаление записи', async ({ page }) => {
    const errors = collectErrors(page)
    await login(page)
    const months = await apiGet(page, '/hr/months')
    const last = months.at(-1)
    const name = uniq('Тестов Тест')
    await page.goto('/hr/registry')
    const total = (await apiGet(page, '/hr/events')).length
    await expect(page.locator('.filter-bar').getByText(new RegExp(`^${total} `))).toBeVisible()

    await page.getByRole('button', { name: 'Добавить' }).click()
    const dialog = page.getByRole('dialog', { name: 'Новая запись' })
    await expect(dialog.getByLabel('Месяц')).toHaveValue(last.key)
    await expect(dialog.getByLabel('Дата')).toHaveValue(`${last.key}-01`)
    // ФИО обязательно: без него форма не отправляется
    await dialog.getByRole('button', { name: 'Сохранить' }).click()
    await expect(dialog).toBeVisible()
    expect(await dialog.getByLabel('ФИО').evaluate((el) => el.validity.valueMissing)).toBe(true)

    await dialog.getByLabel('ФИО').fill(name)
    await dialog.getByLabel('Событие').selectOption('fired')
    await dialog.getByLabel('Дата').fill('2001-01-15')
    await dialog.getByLabel('Должность', { exact: true }).fill('Тестировщик')
    await dialog.getByLabel('Подразделение').fill('ИТ-служба')
    await dialog.getByRole('button', { name: 'Сохранить' }).click()
    await expect(dialog.getByText('Дата вне месяца')).toBeVisible()
    await dialog.getByLabel('Дата').fill(`${last.key}-15`)
    await dialog.getByLabel('Причина увольнения').fill('Тест')
    await dialog.getByRole('button', { name: 'Сохранить' }).click()
    await expect(dialog).toBeHidden()

    await page.getByPlaceholder('ФИО или должность').fill(name)
    const rows = page.locator('tbody tr')
    await expect(rows).toHaveCount(1)
    await expect(rows.first()).toContainText('Увольнение')
    await expect(rows.first()).toContainText(`15.${last.key.slice(5)}.${last.key.slice(0, 4)}`)
    await expect(await kpiValue(page, 'Увольнений')).toBe(1)

    // Строка открывается и с клавиатуры
    await rows.first().focus()
    await page.keyboard.press('Enter')
    const edit = page.getByRole('dialog', { name: 'Запись реестра' })
    await expect(edit.getByLabel('Месяц')).toBeDisabled()
    await edit.getByLabel('Должность', { exact: true }).fill('Ведущий тестировщик')
    await edit.getByRole('button', { name: 'Сохранить' }).click()
    await expect(edit).toBeHidden()
    await expect(rows.first()).toContainText('Ведущий тестировщик')

    await rows.first().getByTitle('Удалить').click()
    await confirmDialog(page, 'Удалить')
    await expect(page.getByText('Ничего не найдено')).toBeVisible()
    const after = await apiGet(page, `/hr/events?search=${encodeURIComponent(name)}`)
    expect(after).toEqual([])
    // Счётчики месяца на других страницах обновились
    expect((await apiGet(page, '/hr/months')).at(-1).fired).toBe(last.fired)
    expect(errors).toEqual([])
  })

  test('реестр: фильтры меняют показатели и сохраняются в адресе', async ({ page }) => {
    await login(page)
    await page.goto('/hr/registry')
    await page.getByLabel('Событие').selectOption('hired')
    await page.getByLabel('Подразделение').selectOption('ИТ-служба')
    await expect(page).toHaveURL(/event_type=hired/)
    await expect(page).toHaveURL(/department=/)
    const events = await apiGet(page, `/hr/events?event_type=hired&department=${encodeURIComponent('ИТ-служба')}`)
    await expect(page.locator('tbody tr')).toHaveCount(events.length)
    expect(await kpiValue(page, 'Приёмов')).toBe(events.length)
    expect(await kpiValue(page, 'Увольнений')).toBe(0)
    await page.reload()
    await expect(page.getByLabel('Событие')).toHaveValue('hired')
    await expect(page.locator('tbody tr')).toHaveCount(events.length)
  })

  test('сводка по периодам: тип периода в адресе, итоги совпадают с API', async ({ page }) => {
    await login(page)
    await page.goto('/hr/summary')
    await page.getByRole('radio', { name: 'Месяц' }).or(page.getByRole('button', { name: 'Месяц', exact: true })).first().click()
    await expect(page).toHaveURL(/period=month/)
    const periods = await apiGet(page, '/hr/analytics/summary?period_type=month')
    const lastPeriod = periods.at(-1)
    await expect(page.getByRole('heading', { name: `Итоги: ${lastPeriod.label}` })).toBeVisible()
    expect(await kpiValue(page, 'Принято')).toBe(lastPeriod.hired)
    expect(await kpiValue(page, 'Уволено')).toBe(lastPeriod.fired)
    await expect(page.locator('table.summary thead th.period')).toHaveCount(periods.length)
    // Щелчок по столбцу периода — итоги за него
    await page.locator('table.summary thead th.period').first().click()
    await expect(page.getByRole('heading', { name: `Итоги: ${periods[0].label}` })).toBeVisible()
    await expect(page).toHaveURL(new RegExp(`focus=${periods[0].key}`))
    expect(await kpiValue(page, 'Принято')).toBe(periods[0].hired)
  })

  test('цели: добавление, изменение и удаление; цель года без данных не оценивается', async ({ page }) => {
    const errors = collectErrors(page)
    await login(page)
    for (const t of await apiGet(page, '/hr/targets')) if (t.year === 2099) await api(page, 'DELETE', `/hr/targets/${t.id}`)
    await page.goto('/hr/targets')
    await page.getByRole('button', { name: 'Добавить цель' }).click()
    const dialog = page.getByRole('dialog', { name: 'Новая цель' })
    await dialog.getByLabel('Год').fill('2099')
    await dialog.getByLabel('Метрика').selectOption('turnover')
    await dialog.getByRole('button', { name: 'Сохранить' }).click()
    await expect(dialog.getByText('Укажите цель или справочное значение')).toBeVisible()
    await dialog.getByLabel(/^Целевое значение/).fill('4,5')
    await dialog.getByRole('button', { name: 'Сохранить' }).click()
    await expect(dialog).toBeHidden()

    const section = page.locator('section', { has: page.getByRole('heading', { name: '2099 год' }) })
    const card = section.locator('.target').first()
    await expect(card).toContainText('Текучесть кадров')
    await expect(card).toContainText('4,5%')
    // Данных за 2099 год нет — факт другого года не подставляется
    await expect(card).toContainText('Нет данных')

    await card.getByTitle('Изменить').click()
    const edit = page.getByRole('dialog', { name: 'Изменить цель' })
    await edit.getByLabel(/^Целевое значение/).fill('4')
    await edit.getByRole('button', { name: 'Сохранить' }).click()
    await expect(card).toContainText('4%')

    await card.getByTitle('Удалить').click()
    await confirmDialog(page, 'Удалить')
    await expect(page.getByRole('heading', { name: '2099 год' })).toHaveCount(0)
    expect(errors).toEqual([])
  })

  test('выгрузки Excel и PDF: имя файла, тип и содержимое', async ({ page }) => {
    await login(page)
    await page.goto('/hr/registry')
    await expectDownload(page, () => page.getByRole('button', { name: 'Excel' }).click(), { ext: 'xlsx', name: 'Реестр приёмов и увольнений' })
    await expectDownload(page, () => page.getByRole('button', { name: 'PDF' }).click(), { ext: 'pdf', name: 'Персонал — реестр' })
    await page.goto('/hr')
    const { response } = await expectDownload(page, () => page.getByRole('button', { name: 'PDF' }).click(), { ext: 'pdf', name: 'Персонал — дашборд' })
    expect(response.url()).toMatch(/months=/)
    await page.goto('/hr/summary')
    await expectDownload(page, () => page.getByRole('button', { name: 'PDF' }).click(), { ext: 'pdf', name: 'Персонал — сводка' })
    await page.goto('/hr/targets')
    await expectDownload(page, () => page.getByRole('button', { name: 'PDF' }).click(), { ext: 'pdf', name: 'Персонал — цели' })
  })

  test('права: it_viewer видит только записи ИТ-службы и не может править', async ({ page }) => {
    await login(page, 'it_viewer')
    await page.goto('/hr/registry')
    await expect(page.getByText(/Показаны только записи подразделений/)).toBeVisible()
    const events = await apiGet(page, '/hr/events')
    expect(events.length).toBeGreaterThan(0)
    expect(new Set(events.map((e) => e.department))).toEqual(new Set(['ИТ-служба']))
    await expect(page.locator('tbody tr')).toHaveCount(events.length)
    const departments = await page.locator('tbody tr td:nth-child(5)').allInnerTexts()
    expect(new Set(departments)).toEqual(new Set(['ИТ-служба']))
    await expect(page.getByRole('button', { name: 'Добавить' })).toHaveCount(0)
    await expect(page.locator('tbody tr').first().getByTitle('Удалить')).toHaveCount(0)

    await page.goto('/hr')
    const dash = await apiGet(page, '/hr/analytics/dashboard')
    expect(dash.departments.map((d) => d.department)).toEqual(['ИТ-служба'])
    await expect(page.getByRole('link', { name: 'Ввод данных' })).toHaveCount(0)
    await page.goto('/hr/data')
    await expect(page.getByRole('heading', { name: 'Нет доступа' })).toBeVisible()
  })

  test('права: viewer видит службы без кнопок изменения', async ({ page }) => {
    await login(page, 'viewer')
    await page.goto('/hr/registry')
    await expect(page.getByRole('heading', { level: 1 })).toContainText('Приёмы и увольнения')
    await expect(page.getByRole('button', { name: 'Добавить' })).toHaveCount(0)
    await page.goto('/hr/targets')
    await expect(page.getByRole('button', { name: 'Добавить цель' })).toHaveCount(0)
    await page.goto('/settings/traffic-light/hr')
    await expect(page.getByRole('heading', { name: 'Нет доступа' })).toBeVisible()
  })
})

test('числа в ru-RU: helper разбирает типографские пробелы и минус', () => {
  expect(num('9 757 ч')).toBe(9757)
  expect(num('−1,87 п.п.')).toBe(-1.87)
  expect(num('—')).toBe(null)
})

test('PDF сводки и дашбордов — по фильтрам страницы', async ({ page }) => {
  await login(page)
  const summary = await apiGet(page, '/hr/analytics/summary?period_type=quarter')
  const [first, second] = summary.map((p) => p.key)
  await page.goto(`/hr/summary?period=quarter&from=${first}&to=${second}`)
  const hrPdf = page.waitForRequest((r) => r.url().includes('/api/pdf/hr/summary'))
  await page.getByRole('button', { name: 'PDF' }).click()
  const hrUrl = new URL((await hrPdf).url())
  expect(hrUrl.searchParams.get('from_key')).toBe(first)
  expect(hrUrl.searchParams.get('to_key')).toBe(second)

  await page.goto('/product?status=Завершено')
  const ppPdf = page.waitForRequest((r) => r.url().includes('/api/pdf/partnerships/summary'))
  await page.getByRole('button', { name: 'PDF' }).click()
  expect(new URL((await ppPdf).url()).searchParams.get('status')).toBe('Завершено')
})
