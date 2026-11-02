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

  // «Подключить систему»: все виды сервера с названием и описанием — в порядке сервера, а не по ключу
  await page.getByTestId('integration-add').click()
  const picker = page.getByRole('dialog', { name: 'Подключить систему' })
  const kinds = await apiGet(page, '/integrations/kinds')
  for (const k of kinds) await expect(picker.getByTestId(`kind-${k.kind}`)).toContainText(k.title)
  expect(await picker.locator('button.kind').evaluateAll((items) => items.map((b) => b.dataset.kind))).toEqual(kinds.map((k) => k.kind))
  expect(kinds.map((k) => k.kind).slice(0, 4)).toEqual(['podelu', 'puls', 'jira', 'confluence'])
  await picker.getByTestId('kind-folder').click()

  const editor = page.getByRole('dialog').filter({ hasText: 'Новое подключение' })
  await expect(editor).toContainText('Папка «Входящие»')
  await expect(editor).toContainText('У этого вида подключения нет настроек')
  // Расписания нет — только вручную; «Добавить расписание»: через интервал, действие «Разобрать папку»
  await expect(editor.getByTestId('schedule-empty')).toBeVisible()
  await editor.getByTestId('schedule-add').click()
  await expect(editor.getByTestId('schedule-entry')).toHaveCount(1)
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
  await settings.getByTestId('schedule-entry').first().getByRole('radio', { name: 'В заданное время' }).click()
  await settings.getByTestId('schedule-time').fill('06:30')
  await settings.getByRole('button', { name: 'пн', exact: true }).click()
  await settings.getByRole('button', { name: 'пт', exact: true }).click()
  await expect(settings.getByTestId('schedule-preview')).toContainText('В 06:30 (пн, пт)')
  // Второе расписание того же подключения: каждые 30 минут — у каждого свой следующий запуск
  await settings.getByTestId('schedule-add').click()
  const second = settings.getByTestId('schedule-entry').nth(1)
  await second.getByTestId('schedule-minutes').fill('30')
  await expect(settings.getByTestId('schedule-preview')).toContainText('В 06:30 (пн, пт) — Разобрать папку; Каждые 30 мин — Разобрать папку')
  await settings.getByTestId('editor-save').click()
  await expect(settings).toHaveCount(0)
  const entries = c.getByTestId('integration-schedule-entry')
  await expect(entries).toHaveCount(2)
  await expect(entries.nth(0)).toContainText('В 06:30 (пн, пт)')
  await expect(entries.nth(1)).toContainText('Каждые 30 мин')
  const saved = (await apiGet(page, '/integrations')).find((i) => i.kind === 'folder')
  expect(saved.schedule.map((e) => e.label)).toEqual(['В 06:30 (пн, пт)', 'Каждые 30 мин'])
  // Одно из расписаний удаляется — остаётся одно
  await c.getByTestId('integration-edit').click()
  await settings.getByTestId('schedule-entry').nth(1).getByTestId('schedule-remove').click()
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
    else if (f.type === 'select') { if (!f.default) await ((await box.locator('select').count()) ? box.locator('select').selectOption(f.options[0].value) : box.locator('input[type=radio]').first().check()) }
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
  // Подписи областей — с сервера, одна и та же везде
  await expect(dialog).toContainText('Чтение статусов принятых файлов')
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
  // Частота вызовов — с сервера (INBOUND_RATE_LIMIT), а не числом в интерфейсе
  const keys = await apiGet(page, '/integrations/keys')
  await expect(shown).toContainText(`не больше ${keys[0].rate_limit} запросов в минуту на ключ`)
  await shown.getByTestId('key-done').click()

  const row = page.getByTestId('keys-table').locator(`tr[data-key="${name}"]`)
  await expect(row).toContainText(`${key.slice(0, 12)}…`)
  await expect(row).toContainText('Приём файлов')
  await expect(row).toContainText('Чтение статусов принятых файлов')
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

test('«По Делу»: смена любого из адресов — предупреждение до сохранения, пароль вводится заново', async ({ page }) => {
  const errors = collectErrors(page)
  await login(page, 'admin')
  const kinds = await apiGet(page, '/integrations/kinds')
  expect(kinds.find((k) => k.kind === 'podelu').secret_url_fields).toEqual(['base_url', 'server_url'])
  const name = uniq('По Делу')
  const created = await api(page, 'POST', '/integrations', {
    kind: 'podelu', name, config: { base_url: 'https://podelu.company.ru', login: 'svc' }, secrets: { password: 'Пароль-42' },
  })
  try {
    await page.goto('/admin/integrations')
    await page.locator(`article[data-integration="${created.id}"]`).getByTestId('integration-edit').click()
    const editor = page.getByRole('dialog').filter({ has: page.getByTestId('editor-save') })
    await expect(editor.getByTestId('secret-set-password')).toBeVisible()
    await expect(editor.getByTestId('editor-rebind')).toHaveCount(0)
    await editor.locator('[data-field=server_url] input').fill('http://10.0.0.5:5000')
    await expect(editor.getByTestId('editor-rebind')).toContainText('Изменено: «Адрес для запросов сервера»')
    await expect(editor.locator('[data-field=password]')).toContainText('Адрес изменён')
    await editor.getByTestId('editor-save').click()
    await expect(editor.getByTestId('editor-error')).toContainText('Проверьте отмеченные поля')
    await expect(editor.locator('[data-field=password]')).toContainText('Обязательное поле')
    await editor.locator('[data-field=server_url] input').fill('')
    await expect(editor.getByTestId('editor-rebind')).toHaveCount(0)
  } finally {
    await api(page, 'DELETE', `/integrations/${created.id}`)
  }
  expect(errors).toEqual([])
})

test('несколько расписаний «По Делу»: структура раз в день, файлы задач каждые 30 минут — на карточке оба', async ({ page }) => {
  const errors = collectErrors(page)
  await login(page, 'admin')
  const name = uniq('По Делу')
  const created = await api(page, 'POST', '/integrations', {
    kind: 'podelu', name, config: { base_url: 'https://podelu.company.ru', login: 'svc' }, secrets: { password: 'Пароль-42' },
    schedule: [{ mode: 'daily', time: '06:00', actions: ['sync'] }, { mode: 'interval', minutes: 30, actions: ['pull'] }],
  })
  try {
    expect(created.schedule.map((e) => e.actions)).toEqual([['sync'], ['pull']])
    await page.goto('/admin/integrations')
    const c = page.locator(`article[data-integration="${created.id}"]`)
    const entries = c.getByTestId('integration-schedule-entry')
    await expect(entries).toHaveCount(2)
    await expect(entries.nth(0)).toContainText('В 06:00 ежедневно')
    await expect(entries.nth(0)).toContainText('Синхронизировать структуру')
    await expect(entries.nth(1)).toContainText('Каждые 30 мин')
    await expect(entries.nth(1)).toContainText('Забрать данные из задач')
    await expect(c.locator('[data-action=sync]')).toContainText('по расписанию')
    await expect(c.locator('[data-action=pull]')).toContainText('по расписанию')
    // Действие «По Делу» называет наборы так же, как «Входящие»
    await expect(c.locator('[data-action=sync] small').first()).toHaveAttribute('title', /наборы «Структура компании» и «Сотрудники»/)

    await c.getByTestId('integration-edit').click()
    const editor = page.getByRole('dialog').filter({ has: page.getByTestId('editor-save') })
    await expect(editor.getByTestId('schedule-entry')).toHaveCount(2)
    await expect(editor.getByTestId('schedule-entry').nth(1).locator('[data-action=pull] input')).toBeChecked()
    await expect(editor.getByTestId('schedule-entry').nth(1).locator('[data-action=sync] input')).not.toBeChecked()
    // «Тип подключения» и прочие длинные списки — на всю ширину, текст не обрезается (проверяется на Jira ниже)
    await editor.getByRole('button', { name: 'Отмена' }).click()
  } finally {
    await api(page, 'DELETE', `/integrations/${created.id}`)
  }
  expect(errors).toEqual([])
})

test('«Тип подключения» Jira не обрезается; «Копировать» не закрывает код ключей', async ({ page }) => {
  const errors = collectErrors(page)
  await login(page, 'admin')
  await page.goto('/admin/integrations')
  await page.getByTestId('integration-add').click()
  await page.getByTestId('kind-jira').click()
  const editor = page.getByRole('dialog').filter({ hasText: 'Новое подключение' })
  // «Тип подключения» — переключателями: подпись варианта видна целиком, без обрезки
  const server = editor.locator('[data-field=instance] label.choice').filter({ hasText: 'Server / Data Center — персональный токен (PAT)' })
  await server.locator('input[type=radio]').check()
  await expect(server).toHaveClass(/on/)
  const clipped = await editor.locator('[data-field=instance] label.choice span').evaluateAll((spans) => spans.filter((el) => el.scrollWidth > el.clientWidth + 1).length)
  expect(clipped).toBe(0)
  await editor.getByRole('button', { name: 'Отмена' }).click()

  await page.goto('/admin/integrations?tab=keys')
  const block = page.getByTestId('keys-curl')
  const [button, pre] = [await block.locator('button.copy').boundingBox(), await block.locator('pre').boundingBox()]
  expect(button.y + button.height).toBeLessThanOrEqual(pre.y + 0.5)
  expect(errors).toEqual([])
})

test('полномочие «Интеграции» без роли администратора: Confluence — только для чтения, справка «?» открывается', async ({ page }) => {
  const errors = collectErrors(page)
  await login(page, 'admin')
  const viewer = (await apiGet(page, '/users?search=viewer')).items.find((u) => u.username === 'viewer')
  const name = uniq('Confluence')
  const created = await api(page, 'POST', '/integrations', {
    kind: 'confluence', name, config: { base_url: 'https://wiki.company.ru', instance: 'server', space: 'DASH' }, secrets: { token: 'pat-42' },
  })
  await api(page, 'PATCH', `/users/${viewer.id}`, { capabilities: ['integrations.manage'] })
  try {
    await page.context().clearCookies()
    await login(page, 'viewer')
    await page.goto('/admin/integrations')
    const c = page.locator(`article[data-integration="${created.id}"]`)
    await expect(c.getByTestId('integration-read-only')).toContainText('Только администратор: публикует полный сквозной отчёт')
    await expect(c.getByTestId('integration-edit')).toHaveCount(0)
    await expect(c.getByTestId('integration-check')).toHaveCount(0)
    await expect(c.getByTestId('integration-delete')).toHaveCount(0)
    await expect(c.getByTestId('run-publish')).toHaveCount(0)
    await expect(c.getByTestId('integration-journal')).toBeVisible()
    const denied = await page.request.post(`/api/integrations/${created.id}/run`, {
      data: { action: 'publish' }, headers: { 'X-CSRF-Token': (await page.context().cookies()).find((k) => k.name === 'ds_csrf')?.value || '' },
    })
    expect(denied.status()).toBe(403)
    await page.getByTestId('integration-add').click()
    const picker = page.getByRole('dialog', { name: 'Подключить систему' })
    await expect(picker.getByTestId('kind-confluence')).toBeDisabled()
    await expect(picker.getByTestId('kind-confluence')).toContainText('Только администратор')
    await picker.getByRole('button', { name: 'Закрыть' }).click()

    // «?» на странице администрирования ведёт в руководство администратора — оно открывается
    await page.getByTestId('page-help').click()
    await expect(page).toHaveURL(/\/guide\/admin#/)
    await expect(page.getByRole('heading', { name: 'Нет доступа' })).toHaveCount(0)
    await expect(page.locator('article h1, article h2').filter({ hasText: 'Интеграции' }).first()).toBeVisible()
  } finally {
    await page.context().clearCookies()
    await login(page, 'admin')
    await api(page, 'PATCH', `/users/${viewer.id}`, { capabilities: [] })
    await api(page, 'DELETE', `/integrations/${created.id}`)
  }
  // Без полномочий руководства администратора нет
  await page.context().clearCookies()
  await login(page, 'viewer')
  await page.goto('/guide/admin')
  await expect(page.getByRole('heading', { name: 'Нет доступа' })).toBeVisible()
  expect(errors).toEqual([])
})

