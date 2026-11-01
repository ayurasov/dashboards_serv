import { expect, test } from '@playwright/test'
import { api, apiGet, collectErrors, confirmDialog, expectDownload, login, num, uniq } from './helpers'

/** Сквозные отчёты (ADR-0010): отчёт по уровням сотрудников, ввод показателей, каталог, «Обзор». */

const matrix = (page) => page.getByTestId('report-matrix')
const row = (page, id) => matrix(page).locator(`tr.mx-row[data-unit="${id}"]`)
const cell = (page, unitId, key) => row(page, unitId).locator(`td[data-key="${key}"]`)
const FINANCIAL_WORDS = ['Выручка', 'Затраты', 'ФОТ', 'Исполнение бюджета', '₽']

/** Идентификаторы показателей по ключу и подразделений по коду — не зависят от порядка создания. */
async function entryIds(page) {
  const indicators = await apiGet(page, '/reports/indicators')
  const departments = await apiGet(page, '/departments')
  return {
    ind: Object.fromEntries(indicators.map((i) => [i.key, i.id])),
    dep: Object.fromEntries(departments.map((d) => [d.code, d.id])),
  }
}

test('первое лицо: компания и 4 направления с замком детализации, финансовые столбцы, PDF', async ({ page }) => {
  const errors = collectErrors(page)
  await login(page, 'ceo')
  await page.getByRole('link', { name: 'Сквозной отчёт', exact: true }).click()
  await expect(page).toHaveURL(/\/reports$/)
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Сквозной отчёт')

  // Сводка вершины: статус, подразделения по статусам, причины, пропуск за пределом детализации
  const hero = page.getByTestId('report-hero')
  await expect(hero.getByTestId('report-status')).toHaveText('Критично')
  await expect(hero).toContainText('АЛМИ Партнер')
  await expect(hero).toContainText('Подразделения по статусу')
  await expect(hero.getByTestId('report-reasons')).toContainText('Заявки в работе')
  await expect(page.getByTestId('report-missing')).toContainText('1 пропуск во вложенных подразделениях (детализация недоступна)')
  await expect(page.getByTestId('report-access')).toContainText('Ваш доступ: вся компания · детализация на 1 уровень')

  // Матрица: 5 подразделений, замок у трёх направлений с вложенными, финансовые показатели видны
  await expect(matrix(page).locator('tr.mx-row')).toHaveCount(5)
  await expect(row(page, 8)).toContainText('Критично')
  await expect(matrix(page).getByTestId('drill-lock')).toHaveCount(3)
  await expect(row(page, 6).getByTestId('drill-lock')).toHaveCount(0)
  for (const name of ['Выручка', 'Затраты', 'ФОТ']) await expect(matrix(page).locator('th.ind', { hasText: name })).toBeVisible()
  await expect(cell(page, 10, 'fin.revenue')).toContainText('53,5')

  // Панель направления: детализация недоступна, вложенных нет, тренды
  await row(page, 11).click()
  await expect(page).toHaveURL(/unit=11/)
  const panel = page.getByRole('dialog')
  await expect(panel.getByTestId('report-panel')).toContainText('Техническая дирекция')
  await expect(panel).toContainText('Детализация недоступна')
  await expect(panel.locator('[data-panel-indicator="tech.in_work"] canvas')).toHaveCount(1)
  await page.keyboard.press('Escape')
  await expect(page).not.toHaveURL(/unit=/)

  await expectDownload(page, () => page.getByRole('button', { name: 'PDF' }).click(), { ext: 'pdf' })
  expect(errors).toEqual([])
})

test('сотрудник: только своё подразделение, без финансовых показателей и выгрузки', async ({ page }) => {
  const errors = collectErrors(page)
  await login(page, 'engineer')
  await page.goto('/reports')
  await expect(page.getByTestId('report-hero').getByTestId('report-status')).toHaveText('Внимание')
  await expect(page.getByTestId('report-hero')).toContainText('Статус по 2 доступным показателям')
  await expect(page.getByTestId('report-hidden')).toHaveText('Персональные и финансовые показатели скрыты')
  await expect(matrix(page).locator('tr.mx-row')).toHaveCount(1)
  await expect(row(page, 12)).toContainText('Группа поддержки AlterOS')
  await expect(cell(page, 12, 'ops.csat')).toContainText('4,3')
  await expect(page.getByRole('button', { name: 'PDF' })).toHaveCount(0)
  await expect(page.getByTestId('report-entry-link')).toHaveCount(0)

  // Панель подразделения и все виды — без денежных показателей
  await row(page, 12).click()
  await expect(page.getByRole('dialog')).toContainText('Удовлетворённость клиентов')
  let text = await page.locator('body').innerText()
  for (const word of FINANCIAL_WORDS) expect(text, `панель: ${word}`).not.toContain(word)
  await page.keyboard.press('Escape')
  for (const view of ['chart', 'list', 'matrix']) {
    await page.getByTestId(`report-view-${view}`).click()
    await expect(page.getByTestId(`report-view-${view}`)).toHaveAttribute('aria-selected', 'true')
    text = await page.locator('body').innerText()
    for (const word of FINANCIAL_WORDS) expect(text, `${view}: ${word}`).not.toContain(word)
  }
  const scorecard = await apiGet(page, '/reports/scorecard')
  expect(scorecard.indicators.every((i) => i.data_class === 'operational')).toBe(true)

  // Ввод показателей недоступен — с причиной
  await page.goto('/reports/entry')
  await expect(page.getByTestId('entry-forbidden')).toContainText('Ввод показателей недоступен')
  expect(errors).toEqual([])
})

test('руководитель направления вводит операционное значение — оно в отчёте', async ({ page }) => {
  const errors = collectErrors(page)
  await login(page, 'tech_dir')
  await page.goto('/reports')
  await expect(page.getByTestId('report-access')).toContainText('своя ветка структуры · детализация на 2 уровня')
  await page.getByTestId('report-entry-link').click()
  await expect(page).toHaveURL(/\/reports\/entry\?period=2026-07/)
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Ввод показателей')

  // Только операционные показатели службы «Аппарат ГД» и подразделения своей ветки
  const grid = page.getByTestId('entry-grid')
  const { ind, dep } = await entryIds(page)
  const planCell = `${ind['ops.plan']}:${dep['SUP-OFFICE']}`
  const csatCell = `${ind['ops.csat']}:${dep.IT}`
  await expect(grid.locator('th.ind')).toHaveCount(2)
  await expect(grid.locator('tbody tr')).toHaveCount(5)
  const value = Number((80 + (Date.now() % 97) / 10).toFixed(1))
  const input = grid.locator(`[data-cell="${planCell}"] input[data-field=value]`)
  await input.fill(String(value).replace('.', ','))
  await grid.locator(`[data-cell="${planCell}"] button[data-field=comment]`).click()
  await page.getByTestId('entry-comment').fill('Внедрение у заказчика завершено')
  await page.getByRole('button', { name: 'Готово' }).click()
  // Ошибка ввода видна у ячейки и не уходит на сервер
  await grid.locator(`[data-cell="${csatCell}"] input[data-field=value]`).fill('много')
  await page.getByTestId('entry-save').click()
  await expect(grid.locator(`[data-cell="${csatCell}"]`)).toContainText('Нужно число')
  await grid.locator(`[data-cell="${csatCell}"] input[data-field=value]`).fill('')
  await page.getByTestId('entry-save').click()
  await expect(page.getByText(/Сохранено: изменено 1/)).toBeVisible()
  await expect(page.getByTestId('entry-save')).toHaveCount(0)

  await page.goto('/reports?period=2026-07')
  await expect(cell(page, 13, 'ops.plan')).toContainText(String(value).replace('.', ','))
  await cell(page, 13, 'ops.plan').hover()
  await expect(page.getByRole('tooltip')).toContainText('Внедрение у заказчика завершено')
  await expect(page.getByRole('tooltip')).toContainText('Цель')
  expect(errors).toEqual([])
})

test('ввод: загрузка CSV — план с ошибками, затем применение', async ({ page }) => {
  const errors = collectErrors(page)
  await login(page, 'tech_dir')
  // Исходное значение — независимо от остатков прерванных прогонов
  const { ind, dep } = await entryIds(page)
  await api(page, 'PUT', '/reports/values', { period: '2026-07', items: [{ indicator_id: ind['ops.plan'], department_id: dep.IT, value: 99, target: 100, comment: '' }] })
  await page.goto('/reports/entry?period=2026-07')
  await page.getByTestId('entry-import').click()
  const dialog = page.getByRole('dialog')
  const csv = (rows) => ({ name: 'values.csv', mimeType: 'text/csv', buffer: Buffer.from(`\ufeffПодразделение;Показатель;Период;Значение;Цель;Комментарий\r\n${rows.join('\r\n')}\r\n`) })
  await dialog.getByTestId('values-file').setInputFiles(csv(['IT;Выполнение плана работ;2026-07;98,5;100;', 'MKT;Выполнение плана работ;2026-07;90;;']))
  await dialog.getByTestId('import-check').click()
  const plan = dialog.getByTestId('import-plan')
  await expect(plan).toContainText('вне вашей области')
  await expect(dialog.getByTestId('import-apply')).toHaveCount(0)

  await dialog.getByRole('button', { name: 'Убрать' }).click()
  await dialog.getByTestId('values-file').setInputFiles(csv(['IT;Выполнение плана работ;2026-07;98,5;100;импорт']))
  await dialog.getByTestId('import-check').click()
  await expect(plan).toContainText('Изменится')
  await dialog.getByTestId('import-apply').click()
  await expect(dialog.getByTestId('import-applied')).toContainText('изменено: 1')
  await dialog.getByRole('button', { name: 'Готово' }).click()
  await expect(page.getByTestId('entry-grid').locator(`[data-cell="${ind['ops.plan']}:${dep.IT}"] input[data-field=value]`)).toHaveValue('98,5')
  // Возврат значения
  await api(page, 'PUT', '/reports/values', { period: '2026-07', items: [{ indicator_id: ind['ops.plan'], department_id: dep.IT, value: 99, target: null, comment: '' }] })
  expect(errors).toEqual([])
})

test('руководитель службы отмечает статус «под контролем»', async ({ page }) => {
  const errors = collectErrors(page)
  await login(page, 'tp_lead')
  await page.goto('/reports')
  await expect(page.getByTestId('report-hidden')).toHaveText('Финансовые показатели скрыты')
  await expect(page.getByTestId('report-hero').getByTestId('report-note')).toBeVisible()
  await row(page, 3).click()
  const panel = page.getByRole('dialog')
  const comment = `Разбираем очередь: ${uniq('note')}`
  await panel.getByTestId('note-edit').click()
  await panel.getByTestId('note-comment').fill('')
  await panel.getByTestId('note-save').click()
  await expect(panel).toContainText('с комментарием')
  await panel.getByTestId('note-comment').fill(comment)
  await panel.getByTestId('note-save').click()
  await expect(page.getByText('Отметка «Под контролем» сохранена')).toBeVisible()
  await expect(panel.getByTestId('panel-note')).toContainText(comment)
  await expect(panel.getByTestId('panel-note')).toContainText('Руководитель техподдержки')
  await page.keyboard.press('Escape')
  await expect(page.getByTestId('report-hero').getByTestId('report-note')).toContainText(comment)
  await expect(row(page, 3).getByTestId('note-mark')).toBeVisible()

  // У вложенной группы tp_lead не руководитель — отметки нет
  await row(page, 12).click()
  await expect(panel.getByTestId('note-add')).toHaveCount(0)
  await expect(panel.getByTestId('note-edit')).toHaveCount(0)
  expect(errors).toEqual([])
})

test('администратор: пропуск данных «Выполнение плана работ» в «Службе маркетинга», фильтры и виды', async ({ page }) => {
  const errors = collectErrors(page)
  await login(page)
  await page.goto('/reports')
  const periods = await apiGet(page, '/reports/periods')
  await expect(page.getByTestId('report-period')).toHaveValue(periods.latest)
  const alert = page.getByTestId('report-missing').first()
  await expect(alert).toContainText('Не заполнены показатели')
  await expect(alert).toContainText('критичное нарушение полноты')
  await expect(alert).toContainText('Выполнение плана работ — Служба маркетинга')
  await expect(cell(page, 4, 'ops.plan')).toContainText('Нет данных')

  await page.getByTestId('report-violations').click()
  await expect(page).toHaveURL(/violations=1/)
  await expect(matrix(page).locator('tr.mx-row:not(.context)')).toHaveCount(1)
  await expect(matrix(page).locator('tr.mx-row:not(.context)')).toContainText('Служба маркетинга')

  // Переход из плашки: панель с пропуском и трендом
  await alert.getByRole('button', { name: /Служба маркетинга/ }).click()
  await expect(page).toHaveURL(/unit=4/)
  const panel = page.getByRole('dialog')
  await expect(panel.getByTestId('report-missing')).toContainText('Выполнение плана работ')
  await expect(panel.locator('[data-panel-indicator="ops.plan"]')).toContainText('Не заполнено')
  await page.keyboard.press('Escape')

  // Вид и период — в адресе
  await page.getByTestId('report-view-chart').click()
  await expect(page).toHaveURL(/view=chart/)
  await expect(page.getByTestId('report-chart').locator('[data-unit-id="4"]')).toContainText('Не заполнено: 1')
  await page.getByTestId('report-period').selectOption('2026-06')
  await expect(page).toHaveURL(/period=2026-06/)
  await page.reload()
  await expect(page.getByTestId('report-view-chart')).toHaveAttribute('aria-selected', 'true')
  await expect(page.getByTestId('report-period')).toHaveValue('2026-06')
  expect(errors).toEqual([])
})

test('администратор добавляет и удаляет показатель (со значениями — после подтверждения)', async ({ page }) => {
  const errors = collectErrors(page)
  await login(page)
  await page.getByRole('link', { name: 'Показатели', exact: true }).click()
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Показатели')
  await expect(page.locator('tr[data-indicator="ops.plan"]')).toContainText('Выполнение плана работ')
  await expect(page.getByTestId('service-units')).toContainText('По коду TECH')

  const key = uniq('ops.e2e').replace(/-/g, '_')
  const name = `Показатель ${key}`
  await page.getByTestId('indicator-add').click()
  const dialog = page.getByRole('dialog')
  await dialog.getByTestId('ind-save').click()
  await expect(dialog).toContainText('Выберите службу, которая вводит значения')
  await dialog.getByTestId('ind-name').fill(name)
  await dialog.getByTestId('ind-key').fill(key)
  await dialog.getByTestId('ind-owner').selectOption('apparat_gd')
  await dialog.getByTestId('ind-unit').fill('%')
  await dialog.getByTestId('ind-green').fill('95')
  await dialog.getByTestId('ind-yellow').fill('85')
  await expect(dialog.getByTestId('rule-bands')).toContainText('≥ 95%')
  await dialog.getByTestId('ind-save').click()
  await expect(page.getByText(`Показатель «${name}» добавлен`)).toBeVisible()
  const created = page.locator(`tr[data-indicator="${key}"]`)
  await expect(created).toContainText(name)
  await expect(created).toContainText('Аппарат генерального директора')

  // Значение у показателя — удаление просит второе подтверждение
  const indicator = (await apiGet(page, '/reports/indicators')).find((i) => i.key === key)
  await api(page, 'PUT', '/reports/values', { period: '2026-07', items: [{ indicator_id: indicator.id, department_id: 3, value: 90, target: null, comment: '' }] })
  await page.reload()
  await expect(created.locator('td.num')).toHaveText('1')
  await created.getByRole('button', { name: `Удалить «${name}»` }).click()
  await confirmDialog(page, 'Удалить')
  await expect(page.getByRole('dialog')).toContainText('1 сохранённых значений')
  await confirmDialog(page, 'Удалить вместе со значениями')
  await expect(page.getByText(`Показатель «${name}» удалён вместе с 1 значениями`)).toBeVisible()
  await expect(created).toHaveCount(0)
  expect(errors).toEqual([])
})

test('«Обзор»: карточка статуса области со ссылкой на отчёт', async ({ page }) => {
  const errors = collectErrors(page)
  await login(page)
  const card = page.getByTestId('report-summary')
  await expect(card.getByRole('heading', { name: 'Статус: АЛМИ Партнер' })).toBeVisible()
  await expect(card).toContainText('Критично')
  await expect(card).toContainText('Главные причины')
  await expect(card).toContainText('Не заполнено показателей: 1')
  const summary = await apiGet(page, '/reports/summary')
  expect(num(await card.locator('.legend span').first().innerText())).toBe(summary.counts.red)
  await card.getByTestId('report-summary-open').click()
  await expect(page).toHaveURL(/\/reports$/)
  await expect(page.getByTestId('report-hero')).toBeVisible()
  expect(errors).toEqual([])
})
