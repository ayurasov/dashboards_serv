import { utimesSync, writeFileSync, mkdirSync } from 'node:fs'
import { join } from 'node:path'
import { expect, test } from '@playwright/test'
import { api, apiGet, collectErrors, login, uniq } from './helpers'

/**
 * «Входящие данные» (ADR-0011): загрузка → план → применение, повтор файла, отклонение и выбор набора,
 * правила «применять сразу», папка «Входящие», доступ редактора службы, полномочия.
 * Папка: сервер e2e запускается с INBOX_DIR (см. .github/workflows/e2e.yml); если тесту известен этот
 * путь (E2E_INBOX_DIR), он кладёт файл в папку сам.
 */
test.describe.configure({ mode: 'serial' })

const HEADER = 'Подразделение;Показатель;Период;Значение;Цель;Комментарий'
const csv = (name, rows) => ({ name, mimeType: 'text/csv', buffer: Buffer.from(`\ufeff${HEADER}\r\n${rows.join('\r\n')}\r\n`) })
const drawer = (page) => page.getByRole('dialog').filter({ has: page.getByTestId('inbox-item-title') })

/** Значение «Выполнение плана работ» ИТ-службы за 2026-07 — как в сквозном отчёте (reports.spec). */
async function planCell(page) {
  const indicators = await apiGet(page, '/reports/indicators')
  const departments = await apiGet(page, '/departments')
  const indicator = indicators.find((i) => i.key === 'ops.plan').id
  const department = departments.find((d) => d.code === 'IT').id
  const restore = () => api(page, 'PUT', '/reports/values', { period: '2026-07', items: [{ indicator_id: indicator, department_id: department, value: 99, target: null, comment: '' }] })
  const read = async () => (await apiGet(page, '/reports/values?period=2026-07')).values
    .find((v) => v.indicator_id === indicator && v.department_id === department)
  return { indicator, department, restore, read }
}

async function upload(page, file, { dataset } = {}) {
  await page.getByTestId('inbox-upload').click()
  const dialog = page.getByRole('dialog', { name: 'Загрузить файл' })
  await dialog.getByTestId('inbox-file').setInputFiles(file)
  if (dataset) await dialog.getByTestId('inbox-dataset').selectOption(dataset)
  await dialog.getByTestId('inbox-upload-submit').click()
  await expect(dialog).toHaveCount(0)
  await expect(drawer(page).getByTestId('inbox-item-title')).toHaveText(file.name)
}

test('загрузка файла → план → применение; повтор того же файла — ссылка на исходный', async ({ page }) => {
  const errors = collectErrors(page)
  await login(page, 'admin')
  const cell = await planCell(page)
  await cell.restore()
  const mark = uniq('inbox')
  const file = csv(`${mark}.csv`, [`IT;Выполнение плана работ;2026-07;97;100;${mark}`])
  try {
    await page.getByTestId('nav-inbox').click()
    await expect(page).toHaveURL(/\/inbox$/)
    await expect(page.getByRole('heading', { name: 'Входящие данные', level: 1 })).toBeVisible()

    // Набор распознаётся сам; план — как у остальных загрузок: сводка, строки, действие
    await upload(page, file)
    const item = drawer(page)
    await expect(item.getByTestId('inbox-item-status')).toHaveText('Ожидает')
    await expect(item).toContainText('Значения показателей')
    const plan = item.getByTestId('inbox-plan')
    await expect(plan.locator('.plan-chip', { hasText: 'Изменится' })).toContainText('1')
    await expect(plan).toContainText('Выполнение плана работ')
    await expect(plan).toContainText('ИТ-служба · 2026-07')
    await expect(plan.locator('.badge', { hasText: 'Изменится' })).toBeVisible()

    await item.getByTestId('inbox-apply').click()
    await expect(item.getByTestId('inbox-item-status')).toHaveText('Применён')
    await expect(item.getByTestId('inbox-item-message')).toContainText('Применён')
    await expect(item.getByTestId('inbox-apply')).toHaveCount(0)
    expect(await cell.read()).toMatchObject({ value: 97, target: 100, comment: mark })
    const firstId = Number(new URL(page.url()).searchParams.get('item'))

    // Тот же файл ещё раз — повтор, не применяется; ссылка открывает исходный элемент
    await item.getByRole('button', { name: 'Закрыть' }).click()
    await upload(page, { ...file, name: `${mark}-again.csv` })
    await expect(item.getByTestId('inbox-item-status')).toHaveText('Повтор')
    await expect(item.getByTestId('inbox-item-message')).toContainText(`элемент №${firstId}`)
    await item.getByTestId('open-original').click()
    await expect(page).toHaveURL(new RegExp(`item=${firstId}`))
    await expect(item.getByTestId('inbox-item-title')).toHaveText(file.name)
    await expect(item.getByTestId('inbox-item-status')).toHaveText('Применён')
    await item.getByRole('button', { name: 'Закрыть' }).click()

    // Список: чипы статусов с числами, поиск, фильтр набора; строка открывает элемент
    await page.getByTestId('inbox-search').fill(mark)
    const rows = page.getByTestId('inbox-table').locator('tbody tr')
    await expect(rows).toHaveCount(2)
    await page.getByTestId('status-applied').click()
    await expect(page).toHaveURL(/status=applied/)
    await expect(rows).toHaveCount(1)
    await expect(rows.first()).toContainText('Значения показателей')
    await expect(rows.first()).toContainText('admin')
    await page.getByTestId('status-duplicate').click()
    await expect(rows.first()).toContainText(`Повтор элемента №${firstId}`)
    // Строка открывается и с клавиатуры; Esc закрывает карточку
    await rows.first().focus()
    await page.keyboard.press('Enter')
    await expect(drawer(page).getByTestId('inbox-item-status')).toHaveText('Повтор')
    await page.keyboard.press('Escape')
    await expect(drawer(page)).toHaveCount(0)
    await page.getByTestId('filter-dataset').selectOption('naumen')
    await expect(page.getByText('Ничего не найдено')).toBeVisible()
    await page.getByRole('button', { name: 'Сбросить', exact: true }).click()
    await expect(page.getByTestId('inbox-search')).toHaveValue('')
  } finally {
    await cell.restore()
  }
  expect(errors).toEqual([])
})

test('счётчик «ожидают» — из профиля; строка «Очистить» удаляет значение; текст ожидания загрузки', async ({ page }) => {
  const errors = collectErrors(page)
  await login(page, 'admin')
  const cell = await planCell(page)
  await cell.restore()
  const pending = (await apiGet(page, '/auth/me')).inbox.pending
  // Меню не делает отдельных запросов за доступом и счётчиком входящих
  const extra = []
  page.on('request', (r) => { if (/\/api\/inbox(\?|\/datasets)/.test(r.url())) extra.push(r.url()) })
  await page.goto('/')
  await expect(page.getByTestId('nav-inbox')).toBeVisible()
  expect(extra).toEqual([])
  const count = page.getByTestId('nav-inbox').locator('.count')
  if (pending) await expect(count).toHaveText(String(pending))
  else await expect(count).toHaveCount(0)

  const mark = uniq('clear')
  const file = { name: `${mark}.csv`, mimeType: 'text/csv',
    buffer: Buffer.from(`\ufeffПодразделение;Показатель;Период;Значение;Цель;Комментарий;Очистить;Метка\r\nIT;Выполнение плана работ;2026-07;;;;да;${mark}\r\n`) }
  await page.getByTestId('nav-inbox').click()
  await upload(page, file)
  const item = drawer(page)
  await expect(item.getByTestId('inbox-item-message')).toContainText('Загружено для проверки — посмотрите план и примените')
  const plan = item.getByTestId('inbox-plan')
  await expect(plan.getByTestId('plan-clears')).toContainText('Очистить значения · 1')
  await expect(plan.locator('.badge', { hasText: 'Очистить' })).toBeVisible()
  await expect(plan).toContainText('значение удалится')
  await expect(count).toHaveText(String(pending + 1))
  await item.getByTestId('inbox-apply').click()
  await expect(item.getByTestId('inbox-item-status')).toHaveText('Применён')
  expect(await cell.read()).toBeUndefined()
  if (pending) await expect(count).toHaveText(String(pending))
  else await expect(count).toHaveCount(0)
  await cell.restore()
  expect(errors).toEqual([])
})

test('подвал карточки элемента: кнопки — одной строкой, подсказка над ними; на телефоне — как прежде', async ({ page }) => {
  const errors = collectErrors(page)
  await login(page, 'admin')
  const mark = uniq('footer')
  // Элемент «ожидает» с планом — загрузкой через API (файл — multipart)
  const csrf = (await page.context().cookies()).find((c) => c.name === 'ds_csrf')?.value || ''
  const response = await page.request.post('/api/inbox', {
    headers: { 'X-CSRF-Token': csrf },
    multipart: { file: csv(`${mark}.csv`, [`IT;Выполнение плана работ;2026-07;95;100;${mark}`]), dataset: 'indicators', apply: 'false' },
  })
  expect(response.status()).toBe(201)
  const { id } = await response.json()
  try {
    await page.goto(`/inbox?item=${id}`)
    const item = drawer(page)
    await expect(item.getByTestId('inbox-item-status')).toHaveText('Ожидает')
    const footer = item.getByTestId('inbox-footer')
    const hint = footer.getByTestId('inbox-footer-hint')
    const rows = async () => {
      const tops = await footer.locator('.foot-actions .btn').evaluateAll((els) => els.map((e) => Math.round(e.getBoundingClientRect().top)))
      return [...new Set(tops)]
    }
    for (const width of [1440, 1280, 1100, 768]) {
      await page.setViewportSize({ width, height: 900 })
      await expect(hint).toHaveText('Всё будет записано одной операцией; при ошибках ничего не записывается.')
      // «Отклонить», «Повторить», «Применить» и «Скачать» — одной строкой; подсказка целиком — над ними
      expect(await rows(), `${width} px`).toHaveLength(1)
      const [hintBox, apply, download] = await Promise.all([hint.boundingBox(), footer.getByTestId('inbox-apply').boundingBox(), footer.getByTestId('inbox-download').boundingBox()])
      expect(hintBox.y + hintBox.height, `${width} px`).toBeLessThanOrEqual(apply.y + 0.5)
      expect(Math.abs(download.y + download.height / 2 - (apply.y + apply.height / 2)), `${width} px`).toBeLessThan(2)
      expect(await hint.evaluate((el) => el.scrollWidth <= el.clientWidth + 1 && el.scrollHeight <= el.clientHeight + 1)).toBe(true)
    }
    // Телефон: подсказки нет, «Применить» — во всю ширину отдельной строкой (как было)
    await page.setViewportSize({ width: 360, height: 800 })
    await expect(hint).toBeHidden()
    expect(await rows()).toHaveLength(2)
    await expect(footer.getByTestId('inbox-apply')).toBeVisible()
  } finally {
    await page.setViewportSize({ width: 1440, height: 900 })
    await api(page, 'POST', `/inbox/${id}/reject`, { reason: 'проверка подвала' })
  }
  expect(errors).toEqual([])
})

test('нераспознанный файл: выбор набора, план с ошибками, отклонение с причиной', async ({ page }) => {
  const errors = collectErrors(page)
  await login(page, 'admin')
  await page.goto('/inbox')
  const mark = uniq('unknown')
  await upload(page, { name: `${mark}.csv`, mimeType: 'text/csv', buffer: Buffer.from(`Что-то;Другое\r\n${mark};1\r\n`) })
  const item = drawer(page)
  await expect(item.getByTestId('inbox-item-status')).toHaveText('Получен')
  await expect(item.getByTestId('inbox-item-message')).toContainText('Набор не распознан')
  await expect(item.getByTestId('inbox-apply')).toHaveCount(0)

  // Набор выбран вручную — план тем же движком: в файле нет нужных столбцов
  await item.getByTestId('pick-dataset').selectOption('indicators')
  await item.getByRole('button', { name: 'Построить план' }).click()
  await expect(item).toContainText('Значения показателей')
  await expect(item.getByTestId('inbox-item-status')).toHaveText(/Ошибка|Ожидает/)

  await item.getByTestId('inbox-reject').click()
  const reject = page.getByRole('dialog', { name: 'Отклонить элемент?' })
  await reject.getByTestId('reject-reason').fill('файл не из 1С')
  await reject.getByTestId('reject-confirm').click()
  await expect(item.getByTestId('inbox-item-status')).toHaveText('Отклонён')
  await expect(item.getByTestId('inbox-item-message')).toContainText('файл не из 1С')
  await expect(item.getByTestId('inbox-reject')).toHaveCount(0)
  // «Повторить» доступно и отклонённому: можно выбрать другой набор
  await item.getByTestId('inbox-retry').click()
  const retry = page.getByRole('dialog', { name: 'Повторить обработку' })
  await expect(retry.getByTestId('retry-dataset')).toHaveValue('indicators')
  await retry.getByRole('button', { name: 'Отмена' }).click()
  expect(errors).toEqual([])
})

test('правила «применять сразу»: источник × набор, сохранение и возврат', async ({ page }) => {
  const errors = collectErrors(page)
  await login(page, 'admin')
  await page.goto('/inbox')
  await page.getByTestId('tab-rules').click()
  await expect(page).toHaveURL(/tab=rules/)
  const rules = page.getByTestId('inbox-rules')
  const cell = rules.getByTestId('rule-api-tp-weekly')
  const input = cell.locator('input')
  const before = await input.isChecked()
  await expect(rules.getByTestId('rules-save')).toHaveCount(0)
  await cell.click()
  await expect(rules).toContainText('Изменено правил: 1')
  await rules.getByTestId('rules-save').click()
  await expect(rules.getByTestId('rules-save')).toHaveCount(0)
  const saved = await apiGet(page, '/inbox/rules')
  const list = Array.isArray(saved) ? saved : saved.rules
  expect(list.find((r) => r.source === 'api' && r.dataset === 'tp-weekly').auto_apply).toBe(!before)
  // Перезагрузка — правило сохранено; возврат
  await page.reload()
  await expect(input).toBeChecked({ checked: !before })
  await cell.click()
  await rules.getByTestId('rules-save').click()
  await expect(rules.getByTestId('rules-save')).toHaveCount(0)
  await expect(input).toBeChecked({ checked: before })
  expect(errors).toEqual([])
})

test('папка «Входящие»: состояние, подпапки, справка, «Проверить сейчас»', async ({ page }) => {
  const errors = collectErrors(page)
  await login(page, 'admin')
  const status = await apiGet(page, '/inbox/folder')
  await page.goto('/inbox?tab=folder')
  const folder = page.getByTestId('inbox-folder')
  await expect(folder).toContainText('Папка «Входящие»')
  await expect(page.getByText('tp-weekly/', { exact: true })).toBeVisible()
  await expect(page.getByTestId('inbox-help')).toContainText('POST /api/inbound/v1/files')
  await expect(page.getByTestId('inbox-curl')).toContainText('Authorization: Bearer dash_')
  await expect(page.getByTestId('worker-state')).toContainText('Планировщик')
  if (!status.enabled) {
    await expect(page.getByTestId('folder-state')).toHaveText('Не настроена')
    await expect(page.getByTestId('folder-scan')).toBeDisabled()
    expect(errors).toEqual([])
    return
  }
  await expect(page.getByTestId('folder-state')).toHaveText(status.exists && status.writable ? 'Работает' : /.+/)

  // Файл в подпапке набора — с отметкой времени в прошлом, чтобы не ждать INBOX_SETTLE_SECONDS
  const dir = process.env.E2E_INBOX_DIR || (status.path && status.path.startsWith('/') ? status.path : '')
  const mark = uniq('folder')
  let dropped = false
  if (dir) try {
    mkdirSync(join(dir, 'indicators'), { recursive: true })
    const path = join(dir, 'indicators', `${mark}.csv`)
    writeFileSync(path, `\ufeff${HEADER}\r\nIT;Выполнение плана работ;2026-07;95;;${mark}\r\n`)
    const past = new Date(Date.now() - 3600_000)
    utimesSync(path, past, past)
    dropped = true
  } catch {
    // Сервер на другой машине — папка недоступна тесту: проверяется только кнопка
  }
  await page.getByTestId('folder-scan').click()
  await expect(page.getByTestId('folder-scan-result')).toBeVisible()
  if (dropped) {
    await expect(page.getByTestId('folder-scan-result')).toContainText(/Взято файлов: [1-9]/)
    await page.getByRole('button', { name: 'Показать в списке' }).click()
    await expect(page).toHaveURL(/source=folder/)
    const row = page.getByTestId('inbox-table').locator('tbody tr', { hasText: `${mark}.csv` })
    await expect(row).toContainText('Папка «Входящие»')
    await expect(row).toContainText(`indicators/${mark}.csv`)
    await expect(row).toContainText('Ожидает')
    // Не применяем: правило «папка × показатели» выключено — элемент ждёт подтверждения; отклоняем
    await row.click()
    await drawer(page).getByTestId('inbox-reject').click()
    await page.getByRole('dialog', { name: 'Отклонить элемент?' }).getByTestId('reject-confirm').click()
    await expect(drawer(page).getByTestId('inbox-item-status')).toHaveText('Отклонён')
  }
  expect(errors).toEqual([])
})

test('редактор службы видит свои наборы; без права ввода — «Нет доступа»', async ({ page }) => {
  const errors = collectErrors(page)
  await login(page, 'hr_head')
  await expect(page.getByTestId('nav-inbox')).toBeVisible()
  await page.getByTestId('nav-inbox').click()
  await expect(page.getByRole('heading', { name: 'Входящие данные', level: 1 })).toBeVisible()
  // Правила и папка — только ведущему входящие
  await expect(page.getByTestId('tab-rules')).toHaveCount(0)
  await page.getByTestId('inbox-upload').click()
  const dialog = page.getByRole('dialog', { name: 'Загрузить файл' })
  const options = await dialog.getByTestId('inbox-dataset').locator('option').allTextContents()
  expect(options).toContain('Метрики месяцев службы персонала')
  expect(options).not.toContain('Недельный отчёт техподдержки')
  await dialog.getByRole('button', { name: 'Отмена' }).click()
  expect(errors).toEqual([])

  await page.context().clearCookies()
  await login(page, 'viewer')
  await expect(page.getByTestId('nav-inbox')).toHaveCount(0)
  await page.goto('/inbox')
  await expect(page.getByRole('heading', { name: 'Нет доступа' })).toBeVisible()
  await expect(page.getByText('редакторам служб')).toBeVisible()
})

test('полномочия «Входящие данные» и «Интеграции»: в карточке пользователя и в меню', async ({ page }) => {
  const errors = collectErrors(page)
  await login(page, 'admin')
  await page.goto('/admin/users?search=viewer')
  await page.locator('.urow[data-user="viewer"]').click()
  await page.getByRole('tab', { name: 'Полномочия' }).click()
  const card = page.getByRole('dialog')
  await expect(card.getByText('Входящие данные', { exact: true })).toBeVisible()
  await expect(card.getByText('Интеграции', { exact: true })).toBeVisible()
  await expect(card.getByText('data.manage')).toBeVisible()
  await expect(card.getByText('integrations.manage')).toBeVisible()
  const viewer = (await apiGet(page, '/users?search=viewer')).items.find((u) => u.username === 'viewer')
  await api(page, 'PATCH', `/users/${viewer.id}`, { capabilities: ['data.manage', 'integrations.manage'] })
  try {
    await page.context().clearCookies()
    await login(page, 'viewer')
    await expect(page.getByTestId('nav-inbox')).toBeVisible()
    await page.getByRole('link', { name: 'Интеграции', exact: true }).click()
    await expect(page).toHaveURL(/\/admin\/integrations$/)
    await expect(page.getByRole('heading', { name: 'Интеграции', level: 1 })).toBeVisible()
    await page.goto('/inbox')
    await expect(page.getByTestId('tab-rules')).toBeVisible()
    await expect(page.getByTestId('tab-folder')).toBeVisible()
    // Вход по домену — по-прежнему только администратору
    await page.goto('/admin/directory')
    await expect(page.getByRole('heading', { name: 'Нет доступа' })).toBeVisible()
  } finally {
    await page.context().clearCookies()
    await login(page, 'admin')
    await api(page, 'PATCH', `/users/${viewer.id}`, { capabilities: [] })
  }
  expect(errors).toEqual([])
})
