import { readFileSync } from 'node:fs'
import { expect, test } from '@playwright/test'
import { collectErrors, login } from './helpers'

/** Структура компании (ADR-0007): оргсхема, виды, подразделения, импорт и экспорт, права. */

test('оргсхема: карточки подразделений, поиск раскрывает ветку до сотрудника', async ({ page }) => {
  const errors = collectErrors(page)
  await login(page, 'ceo')
  await page.goto('/org?view=chart')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Структура компании')
  const root = page.locator('[data-unit-id]').filter({ hasText: 'АЛМИ Партнер' })
  await expect(root).toBeVisible()
  await expect(root).toContainText('Громов Андрей Викторович')
  await expect(root.getByText('Вы здесь')).toBeVisible()
  // Группа поддержки — четвёртый уровень: по умолчанию видно три
  await expect(page.locator('[data-unit-id="12"]')).toHaveCount(0)

  await page.getByTestId('org-search').fill('петров')
  const option = page.getByRole('option', { name: /Петров Илья Сергеевич/ })
  await expect(option).toBeVisible()
  await expect(option).toContainText('Группа поддержки AlterOS')
  await page.keyboard.press('Enter')

  await expect(page).toHaveURL(/user=\d+/)
  await expect(page.locator('[data-unit-id="12"]')).toBeVisible()
  await expect(page.locator('[data-unit-id="12"]')).toHaveClass(/path/)
  const panel = page.getByTestId('org-panel')
  await expect(panel.getByRole('heading', { name: 'Петров Илья Сергеевич' })).toBeVisible()
  await expect(panel).toContainText('Руководитель техподдержки')
  await expect(panel).toContainText('по структуре')
  await expect(panel.getByText('Цепочка подчинения')).toBeVisible()

  // Переход по руководителю из панели
  await panel.getByRole('button', { name: /Руководитель техподдержки/ }).first().click()
  await expect(panel.getByRole('heading', { name: 'Руководитель техподдержки' })).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.getByTestId('org-panel')).toHaveCount(0)
  expect(errors).toEqual([])
})

test('виды переключаются, выбор сохраняется в адресе и у пользователя', async ({ page }) => {
  const errors = collectErrors(page)
  await login(page, 'tech_dir')
  await page.goto('/org')
  await expect(page.getByTestId('org-view-chart')).toHaveAttribute('aria-selected', 'true')

  await page.getByTestId('org-view-people').click()
  await expect(page).toHaveURL(/view=people/)
  await expect(page.locator('[data-person-id]').filter({ hasText: 'Соколова Мария Игоревна' })).toBeVisible()
  await page.reload()
  await expect(page.getByTestId('org-view-people')).toHaveAttribute('aria-selected', 'true')

  await page.getByTestId('org-view-tree').click()
  await expect(page).toHaveURL(/view=tree/)
  await expect(page.getByRole('tree')).toContainText('Техническая дирекция')

  await page.getByTestId('org-view-table').click()
  await expect(page.locator('table')).toContainText('Проектная служба')
  await page.locator('th').filter({ hasText: 'В ветке' }).getByRole('button').click()
  await expect(page.locator('tbody tr').first()).toContainText('АЛМИ Партнер')
  const download = page.waitForEvent('download')
  await page.getByTestId('org-export').click()
  const csv = readFileSync(await (await download).path(), 'utf-8')
  expect(csv.charCodeAt(0)).toBe(0xfeff)
  expect(csv).toContain('Путь;Подразделение;Код;Тип;Уровень;Руководитель')
  expect(csv).toContain('АЛМИ Партнер / Техническая дирекция;Техническая дирекция;TECHDIR;Дирекция;2;Соколова Мария Игоревна')

  // Без вида в адресе — последний выбранный
  await page.goto('/org')
  await expect(page.getByTestId('org-view-table')).toHaveAttribute('aria-selected', 'true')
  await page.getByTestId('org-where-am-i').click()
  await expect(page.locator('tr.selected, tr.flash').first()).toContainText('Техническая дирекция')
  expect(errors).toEqual([])
})

test('подразделения: создать, переименовать, перенести, назначить руководителя, удалить', async ({ page }) => {
  const errors = collectErrors(page)
  await login(page)
  await page.goto('/admin/departments')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Подразделения')
  const name = `Отдел проверки ${Date.now() % 100000}`

  // Создать внутри «Коммерческая служба»
  await page.getByTestId('department-add').click()
  const dialog = page.getByRole('dialog')
  await dialog.getByTestId('department-name').fill(name)
  await dialog.getByTestId('department-parent').getByRole('button').first().click()
  await dialog.getByPlaceholder('Найти подразделение').fill('Коммерческая служба')
  await page.keyboard.press('Enter')
  await dialog.getByTestId('department-save').click()
  await expect(dialog).toHaveCount(0)
  const row = page.locator('tr', { hasText: name })
  await expect(row).toBeVisible()
  await expect(row).toContainText('Руководитель не назначен')
  const id = await row.getAttribute('data-department-id')

  // Переименовать
  const renamed = `${name} (продажи)`
  await row.getByRole('button', { name: /^Изменить/ }).click()
  await dialog.getByTestId('department-name').fill(renamed)
  await dialog.getByTestId('department-save').click()
  const renamedRow = page.locator(`tr[data-department-id="${id}"]`)
  await expect(renamedRow).toContainText(renamed)

  // Перенести в «Служба маркетинга»
  await renamedRow.getByRole('button', { name: /^Изменить/ }).click()
  await expect(dialog).toContainText('Коммерческая служба')
  await dialog.getByTestId('department-parent').getByRole('button').first().click()
  await dialog.getByPlaceholder('Найти подразделение').fill('маркетинг')
  await page.keyboard.press('Enter')
  await dialog.getByTestId('department-save').click()
  await expect(dialog).toHaveCount(0)
  const moved = await (await page.request.get(`/api/departments/${id}`)).json()
  expect(moved.path).toContain('Служба маркетинга')

  // Руководитель
  await renamedRow.getByRole('button', { name: /^Руководители/ }).click()
  await dialog.getByTestId('heads-search').fill('Петров')
  await dialog.getByRole('checkbox', { name: 'Петров Илья Сергеевич' }).check()
  await dialog.getByTestId('heads-save').click()
  await expect(renamedRow).toContainText('Петров Илья Сергеевич')
  await expect(renamedRow).not.toContainText('Руководитель не назначен')

  // Удаление: в подтверждении — кого затронет
  await renamedRow.getByRole('button', { name: /^Удалить/ }).click()
  const confirmDialog = page.getByRole('dialog')
  await expect(confirmDialog).toContainText('Петров Илья Сергеевич перестанет им руководить')
  await confirmDialog.getByRole('button', { name: 'Удалить' }).click()
  await expect(page.locator(`tr[data-department-id="${id}"]`)).toHaveCount(0)

  // Удалить подразделение с вложенными нельзя
  await expect(page.locator('tr', { hasText: 'Техническая дирекция' }).getByRole('button', { name: /^Удалить/ })).toBeDisabled()
  expect(errors).toEqual([])
})

test('перенос структуры: выгрузка и загрузка того же файла — без изменений', async ({ page }) => {
  const errors = collectErrors(page)
  await login(page)
  await page.goto('/admin/org-transfer')
  const download = page.waitForEvent('download')
  await page.getByTestId('structure-export').click()
  const file = await download
  expect(file.suggestedFilename()).toMatch(/^dashboards-structure-\d{4}-\d{2}-\d{2}\.json$/)
  const buffer = readFileSync(await file.path())
  const total = JSON.parse(buffer.toString('utf-8')).departments.length

  // Буфером, а не путём: путь к результатам теста — с кириллицей
  await page.getByTestId('structure-file').setInputFiles({ name: file.suggestedFilename(), mimeType: 'application/json', buffer })
  await page.getByTestId('structure-check').click()
  const plan = page.getByTestId('structure-plan')
  await expect(plan).toBeVisible()
  await expect(plan.locator('.plan-chip', { hasText: 'Без изменений' })).toContainText(String(total))
  await expect(plan.locator('.plan-chip', { hasText: 'Ошибок' })).toContainText('0')
  await expect(plan).toContainText('Изменений в подразделениях нет')
  await plan.getByRole('radio', { name: 'Все' }).click()
  await expect(plan.getByText('Без изменений', { exact: true }).first()).toBeVisible()
  await expect(plan.getByTestId('structure-apply')).toBeEnabled()
  expect(errors).toEqual([])
})

test('выгрузка сотрудников скачивает файл', async ({ page }) => {
  await login(page)
  await page.goto('/admin/org-transfer?tab=employees')
  await page.getByRole('radio', { name: 'CSV' }).click()
  const download = page.waitForEvent('download')
  await page.getByTestId('employees-export').click()
  const file = await download
  // Имя файла («Сотрудники 2026-…csv») задаёт сервер; безголовый Chromium кириллические имена не сообщает
  const text = readFileSync(await file.path(), 'utf-8')
  expect(text.charCodeAt(0)).toBe(0xfeff)
  expect(text).toContain('Email;Логин;ФИО')
  expect(text).toContain('Петров Илья Сергеевич')
})

test('сотрудник видит структуру, но не действия администрирования', async ({ page }) => {
  const errors = collectErrors(page)
  await login(page, 'engineer')
  await page.goto('/org?view=chart')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Структура компании')
  await expect(page.locator('[data-unit-id]').first()).toBeVisible()
  await expect(page.getByRole('link', { name: /Подразделения/ })).toHaveCount(0)
  await expect(page.getByRole('link', { name: /Импорт и экспорт/ })).toHaveCount(0)
  // «Где я» — своё подразделение
  await page.getByTestId('org-where-am-i').click()
  const mine = page.locator('[data-unit-id="12"]')
  await expect(mine).toBeVisible()
  await expect(mine.getByText('Вы здесь')).toBeVisible()
  await mine.click({ position: { x: 20, y: 20 } })
  const panel = page.getByTestId('org-panel')
  await expect(panel).toContainText('Группа поддержки AlterOS')
  await expect(panel.getByRole('link', { name: /Изменить подразделение/ })).toHaveCount(0)
  await panel.getByRole('button', { name: /Петров Илья Сергеевич/ }).click()
  await expect(panel.getByRole('heading', { name: 'Петров Илья Сергеевич' })).toBeVisible()
  await expect(panel.getByText('Это вы')).toBeVisible()
  await expect(page.getByTestId('org-person-editor')).toHaveCount(0)

  await page.goto('/admin/departments')
  await expect(page.getByRole('heading', { name: 'Нет доступа' })).toBeVisible()
  await page.goto('/admin/org-transfer')
  await expect(page.getByRole('heading', { name: 'Нет доступа' })).toBeVisible()
  expect(errors).toEqual([])
})
