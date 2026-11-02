import { expect, test } from '@playwright/test'
import { api, apiGet, collectErrors, confirmDialog, login, uniq } from './helpers'

/**
 * «Интеграции» (ADR-0011): подключение из вида (форма по описанию полей), проверка, включение только
 * после проверки, расписание, запуск действия, журнал запусков, удаление; проверка с ошибкой;
 * ключи для входящих вызовов: выпуск (показ один раз), приём файла по ключу, отзыв.
 */
test.describe.configure({ mode: 'serial' })

const card = (page, kind) => page.locator(`article[data-kind="${kind}"]`)

test('папка «Входящие» как подключение: создание, «сначала проверьте», включение, расписание, запуск, журнал, удаление', async ({ page }) => {
  const errors = collectErrors(page)
  await login(page, 'admin')
  // Подключение папки — одно на систему: остаток прерванного прогона убирается
  for (const i of await apiGet(page, '/integrations')) if (i.kind === 'folder') await api(page, 'DELETE', `/integrations/${i.id}`)
  const folder = await apiGet(page, '/inbox/folder')

  await page.getByRole('link', { name: 'Интеграции', exact: true }).click()
  await expect(page).toHaveURL(/\/admin\/integrations$/)
  await expect(page.getByRole('heading', { name: 'Интеграции', level: 1 })).toBeVisible()

  // «Подключить систему»: все виды сервера с названием и описанием
  await page.getByTestId('integration-add').click()
  const picker = page.getByRole('dialog', { name: 'Подключить систему' })
  const kinds = await apiGet(page, '/integrations/kinds')
  for (const k of kinds) await expect(picker.getByTestId(`kind-${k.kind}`)).toContainText(k.title)
  await picker.getByTestId('kind-folder').click()

  const editor = page.getByRole('dialog').filter({ hasText: 'Новое подключение' })
  await expect(editor).toContainText('Папка «Входящие»')
  await expect(editor).toContainText('У этого вида подключения нет настроек')
  // Расписание: через интервал, 60 минут, действие «Разобрать папку»
  await editor.locator('.schedule').getByRole('radio', { name: 'Через интервал' }).click()
  await editor.getByTestId('schedule-minutes').fill('3')
  await editor.getByTestId('editor-save').click()
  await expect(editor.getByTestId('editor-error')).toBeVisible()
  await expect(editor).toContainText('Целое число минут от 5')
  await editor.getByTestId('schedule-minutes').fill('60')
  await expect(editor.getByTestId('schedule-preview')).toContainText('Каждые 60 мин')
  await editor.getByTestId('editor-save').click()
  await expect(editor).toHaveCount(0)

  const c = card(page, 'folder')
  await expect(c).toBeVisible()
  await expect(c.getByTestId('integration-health')).toHaveText('Выключено')
  await expect(c.getByTestId('integration-schedule')).toHaveText('Каждые 60 мин')
  await expect(c.locator('[data-action=scan]')).toContainText('по расписанию')

  // Включить без проверки нельзя: объяснение и «Проверить»
  await c.getByTestId('integration-enabled').click()
  await expect(c.getByTestId('check-required')).toContainText('Сначала проверьте подключение')
  await expect(c.getByTestId('integration-enabled').locator('input')).not.toBeChecked()
  await c.getByTestId('check-required-run').click()
  const result = c.getByTestId('card-check-result')
  if (!folder.enabled || !folder.exists || !folder.writable) {
    // Сервер без INBOX_DIR — проверка с ошибкой и понятным текстом
    await expect(result).toHaveClass(/bad/)
    await expect(result).toContainText(/Папка не настроена|не найдена|Нет прав/)
  } else {
    await expect(result).toHaveClass(/ok/)
    await expect(result).toContainText('доступна')
    await c.getByTestId('enable-after-check').click()
    await expect(c.getByTestId('integration-enabled').locator('input')).toBeChecked()
    await expect(c.getByTestId('integration-health')).toHaveText('Работает')
    await expect(c).toContainText('следующий запуск')
  }

  // Действие — своя кнопка «Запустить»; итог в карточке и в журнале запусков
  await c.getByTestId('run-scan').click()
  await expect(c.getByTestId('run-result')).toContainText(folder.enabled ? 'Успешно' : 'Ошибка')
  await c.getByTestId('integration-journal').click()
  const journal = page.getByRole('dialog').filter({ hasText: 'Журнал запусков' })
  const run = journal.getByTestId('runs-table').locator('tbody tr').first()
  await expect(run).toContainText('Разобрать папку')
  await expect(run).toContainText('Вручную')
  await expect(run).toContainText('admin')
  await journal.getByRole('button', { name: 'Закрыть' }).click()

  // Расписание меняется в настройках: в 06:30 по понедельникам и пятницам
  await c.getByTestId('integration-edit').click()
  const settings = page.getByRole('dialog').filter({ hasText: 'Расписание' })
  await settings.locator('.schedule').getByRole('radio', { name: 'В заданное время' }).click()
  await settings.getByTestId('schedule-time').fill('06:30')
  await settings.getByRole('button', { name: 'пн', exact: true }).click()
  await settings.getByRole('button', { name: 'пт', exact: true }).click()
  await expect(settings.getByTestId('schedule-preview')).toContainText('В 06:30 (пн, пт)')
  await settings.getByTestId('editor-save').click()
  await expect(c.getByTestId('integration-schedule')).toHaveText('В 06:30 (пн, пт)')

  await c.getByTestId('integration-delete').click()
  await confirmDialog(page, 'Удалить')
  await expect(c).toHaveCount(0)
  expect(errors).toEqual([])
})

test('проверка до сохранения: подробная ошибка и подсказка о разрешённых узлах', async ({ page }) => {
  const errors = collectErrors(page)
  await login(page, 'admin')
  const kinds = await apiGet(page, '/integrations/kinds')
  // Вид с адресом (Jira, «По Делу», «Пульс»…) — любой, который есть на сервере
  const kind = kinds.find((k) => k.url_field && k.fields.some((f) => f.key === k.url_field))
  test.skip(!kind, 'На сервере нет видов подключений с адресом')
  await page.goto('/admin/integrations')
  await page.getByTestId('integration-add').click()
  await page.getByTestId(`kind-${kind.kind}`).click()
  const editor = page.getByRole('dialog').filter({ hasText: 'Новое подключение' })
  await expect(editor).toContainText(kind.allowed_hosts_env)

  // Пустую форму не проверить: обязательные поля отмечаются
  await editor.getByTestId('editor-check').click()
  await expect(editor.getByTestId('editor-error')).toContainText('Заполните отмеченные поля')

  // Обязательные видимые поля — по описанию вида
  const values = {}
  for (const f of kind.fields) values[f.key] = f.default
  const visible = (f) => !f.show_if || Object.entries(f.show_if).every(([k, allowed]) => allowed.map(String).includes(String(values[k] ?? '')))
  for (const f of kind.fields) {
    if (!f.required || !visible(f) || f.type === 'bool') continue
    const box = editor.locator(`[data-field="${f.key}"]`)
    if (f.key === kind.url_field) await box.locator('input').fill('http://127.0.0.1:9')
    else if (f.secret) await box.locator('input').fill('e2e-secret')
    else if (f.type === 'select') { if (!f.default) await box.locator('select').selectOption(f.options[0].value) }
    else if (f.type === 'multiselect') await box.locator('input[type=checkbox]').first().check()
    else if (f.type === 'int') await box.locator('input').fill(String(f.min ?? 1))
    else if (f.type === 'time') await box.locator('input').fill('06:00')
    else if (f.type === 'text' || f.type === 'list') await box.locator('textarea').fill('e2e')
    else await box.locator('input').fill(f.type === 'url' ? 'http://127.0.0.1:9' : 'e2e@example.com')
  }
  await editor.getByTestId('editor-check').click()
  const result = editor.getByTestId('editor-check-result')
  await expect(result).toHaveClass(/bad/, { timeout: 20_000 })
  await expect(result.locator('.msg')).not.toBeEmpty()
  await expect(result).toContainText('Проверены несохранённые значения')
  await editor.getByRole('button', { name: 'Отмена' }).click()
  await expect(editor).toHaveCount(0)
  expect(errors).toEqual([])
})

test('ключи для входящих вызовов: выпуск, показ один раз, приём файла по ключу, отзыв', async ({ page }) => {
  const errors = collectErrors(page)
  await login(page, 'admin')
  await page.goto('/admin/integrations')
  await page.getByTestId('tab-keys').click()
  await expect(page).toHaveURL(/tab=keys/)
  await expect(page.getByTestId('keys-curl')).toContainText('/api/inbound/v1/files')

  const name = uniq('1С ЗУП')
  await page.getByTestId('key-create').click()
  const dialog = page.getByRole('dialog', { name: 'Выпустить ключ' })
  await dialog.getByTestId('key-issue').click()
  await expect(dialog).toContainText('Укажите название ключа')
  await dialog.getByTestId('key-name').fill(name)
  await dialog.getByTestId('key-scope-status').check()
  await dialog.getByTestId('key-issue').click()

  const shown = page.getByRole('dialog', { name: 'Ключ выпущен' })
  const key = (await shown.getByTestId('one-time-key').innerText()).trim()
  expect(key).toMatch(/^dash_[\w-]{20,}$/)
  await expect(shown).toContainText('показывается один раз')
  await expect(shown).toContainText(`Bearer ${key}`)
  await shown.getByTestId('key-done').click()

  const row = page.getByTestId('keys-table').locator(`tr[data-key="${name}"]`)
  await expect(row).toContainText(`${key.slice(0, 12)}…`)
  await expect(row).toContainText('Приём файлов')
  await expect(row).toContainText('Чтение статусов')
  await expect(row).toContainText('Действует')
  await expect(page.locator('body')).not.toContainText(key)

  // Внешняя система кладёт файл по ключу — во «Входящих» источник подписан названием ключа
  const auth = { Authorization: `Bearer ${key}` }
  const ping = await page.request.get('/api/inbound/v1/ping', { headers: auth })
  expect(ping.status()).toBe(200)
  const mark = uniq('api')
  const sent = await page.request.post('/api/inbound/v1/files', {
    headers: auth,
    multipart: {
      file: { name: `${mark}.csv`, mimeType: 'text/csv', buffer: Buffer.from(`\ufeffПодразделение;Показатель;Период;Значение;Цель;Комментарий\r\nIT;Выполнение плана работ;2026-07;96;;${mark}\r\n`) },
      dataset: 'indicators', apply: 'false',
    },
  })
  expect(sent.status()).toBe(201)
  await page.goto(`/inbox?source=api&q=${mark}`)
  const item = page.getByTestId('inbox-table').locator('tbody tr').first()
  await expect(item).toContainText(`Ключ «${name}»`)
  await expect(item).toContainText('Значения показателей')

  // Отзыв — с подтверждением; ключ перестаёт работать сразу
  await page.goto('/admin/integrations?tab=keys')
  await row.getByRole('button', { name: 'Отозвать' }).click()
  await confirmDialog(page, 'Отозвать')
  await expect(row).toContainText('Отозван')
  await expect(row.getByRole('button', { name: 'Отозвать' })).toHaveCount(0)
  expect((await page.request.get('/api/inbound/v1/ping', { headers: auth })).status()).toBe(401)
  expect(errors).toEqual([])
})
