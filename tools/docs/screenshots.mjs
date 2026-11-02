// Снимки экрана для руководств (docs/manuals/images/{user,admin}).
// Нужен сервер с демо-данными (DEMO_DATA=true) на чистой базе и собранным интерфейсом:
//   cd frontend && SHOTS_BASE_URL=http://127.0.0.1:8000 node ../tools/docs/screenshots.mjs [часть-имени …]
// Затем: python3 tools/docs/optimize_png.py docs/manuals/images
//
// Скрипт меняет демо-данные через API только временно и возвращает их: пропуск показателя
// «Текучесть кадров» (снимки правила «Нет данных / Не заполнено»), тестовый пользователь для
// временного пароля. Для снимков импорта сотрудников у технического директора появляется e-mail,
// и проверяются (но не применяются) файлы загрузки. Сквозной отчёт (0.3.0) снимается на демо-значениях
// за июль 2026: ввод показателей — без сохранения, загрузка значений — только проверка.
// Запускайте на отдельной базе стенда.
// Для страниц «Вход по домену» сервер можно запустить с примером настроек AUTH_LDAP_* — адрес
// каталога может быть недоступен: пароль домена не проверяется, входят по паролю системы.
//
// Входящие данные и интеграции (0.4.0) снимаются последними и остаются в базе: ключи, правила, подключения,
// элементы входящих и значения показателей Jira за текущий и прошлый месяц. Нужны:
// - папка «Входящие» сервера: INBOX_DIR=<каталог> у сервера и SHOTS_INBOX_DIR=<тот же каталог> у скрипта;
// - планировщик (python -m app.cli worker) — отметка «Работает» на вкладке «Папка»;
// - поддельные «По Делу», Jira и Confluence: sudo python3 tools/docs/fake_systems.py (127.0.0.2:80) и строка
//   «127.0.0.2 podelu.almi-partner.local jira.almi-partner.local confluence.almi-partner.local» в /etc/hosts
//   (у сервера эти узлы не должны идти через прокси).
// Адрес в примерах запросов на снимках — адрес, по которому открыт стенд: удобно запустить сервер на
// 127.0.0.1:80 с именем «127.0.0.1 dashboards.almi-partner.local» в /etc/hosts и задать
// SHOTS_BASE_URL=http://dashboards.almi-partner.local. Время на снимках — московское (Europe/Moscow).
import { mkdirSync, utimesSync, writeFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createRequire } from 'node:module'

// Playwright — из frontend/node_modules: модули ESM ищутся рядом со скриптом, а не в рабочем каталоге
const { chromium } = createRequire(new URL('../../frontend/package.json', import.meta.url))('@playwright/test')

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const BASE = process.env.SHOTS_BASE_URL || 'http://127.0.0.1:8000'
const OUT = resolve(ROOT, 'docs/manuals/images')
const only = process.argv.slice(2)
const wanted = (...names) => !only.length || names.some((n) => only.some((o) => n.includes(o)))

const browser = await chromium.launch()
const NORMAL = { width: 1440, height: 900 }
// Боковая карточка пользователя и высокие окна целиком
const TALL = { width: 1440, height: 1300 }

async function session(username, password, { theme = 'light', viewport = NORMAL } = {}) {
  const context = await browser.newContext({ viewport, deviceScaleFactor: 1.5, colorScheme: theme, locale: 'ru-RU', timezoneId: 'Europe/Moscow' })
  const page = await context.newPage()
  page.on('pageerror', (e) => console.error('  ошибка страницы:', e.message))
  await page.goto(`${BASE}/login`)
  if (username) {
    await page.fill('input[name=username]', username)
    await page.fill('input[name=password]', password)
    await page.click('button[type=submit]')
    await page.waitForURL((url) => !url.pathname.startsWith('/login'))
  }
  return { context, page }
}

async function settle(page, ms = 900) {
  await page.waitForLoadState('networkidle').catch(() => {})
  // Скелетоны загрузки не должны попадать в снимки
  await page.locator('.skeleton').first().waitFor({ state: 'detached', timeout: 8000 }).catch(() => {})
  await page.waitForTimeout(ms)
}

async function shot(page, name, { clip, full = false, element } = {}) {
  if (!wanted(name)) return
  const path = `${OUT}/${name}.png`
  mkdirSync(dirname(path), { recursive: true })
  if (element) await element.screenshot({ path })
  else await page.screenshot({ path, fullPage: full, clip })
  console.log('  ', name)
}

async function open(page, path, ms) {
  await page.goto(`${BASE}${path}`)
  await settle(page, ms)
}

async function click(page, text) {
  await page.getByRole('button', { name: text }).first().click()
  await settle(page, 500)
}

async function dialogShot(page, name) {
  const dialog = page.getByRole('dialog').first()
  await dialog.waitFor()
  await page.waitForTimeout(400)
  await shot(page, name)
  await page.keyboard.press('Escape')
  await page.waitForTimeout(250)
}

/** Запрос к API от имени вошедшего пользователя (cookie сессии и CSRF-токен). */
async function api(page, method, path, body) {
  const csrf = (await page.context().cookies()).find((c) => c.name === 'ds_csrf')?.value
  const response = await page.request.fetch(`${BASE}/api${path}`, {
    method, headers: csrf ? { 'X-CSRF-Token': csrf } : {}, ...(body === undefined ? {} : { data: body }),
  })
  if (!response.ok()) throw new Error(`${method} ${path}: ${response.status()} ${await response.text()}`)
  return response.json()
}

/** Файл для поля выбора файла — из памяти, без временных файлов на диске. */
function memoryFile(name, mimeType, content) {
  return { name, mimeType, buffer: Buffer.from(content, 'utf8') }
}

// ---------------------------------------------------------------- пользователь
{
  // Страница входа; при настроенном входе по домену под полями — подсказка
  const { context, page } = await session(null)
  await settle(page)
  await shot(page, 'user/01-login')
  await context.close()
}
{
  const { context, page } = await session('admin', 'admin123')
  const p = page
  await open(p, '/'); await shot(p, 'user/02-overview')
  await open(p, '/hr?quick=6', 1400); await shot(p, 'user/03-hr-dashboard')
  await click(p, 'Настроить'); await dialogShot(p, 'user/04-hr-layout')
  await open(p, '/hr/registry?month=2026-06'); await shot(p, 'user/05-hr-registry')
  await click(p, 'Добавить'); await dialogShot(p, 'user/06-hr-event-form')
  await open(p, '/hr/data?month=2026-07'); await shot(p, 'user/07-hr-data-entry')
  await open(p, '/hr/summary', 1400); await shot(p, 'user/08-hr-summary')
  await open(p, '/hr/targets'); await shot(p, 'user/09-hr-targets')
  await open(p, '/hr/dashboards'); await shot(p, 'user/10-hr-custom')
  await open(p, '/tp', 1600); await shot(p, 'user/11-tp-dashboard')
  await open(p, '/tp/registry'); await shot(p, 'user/12-tp-registry')
  await click(p, 'Загрузить файл'); await dialogShot(p, 'user/13-tp-import')
  await open(p, '/tp/compare', 1400); await shot(p, 'user/14-tp-compare')
  await open(p, '/tp/naumen', 1600); await shot(p, 'user/15-tp-naumen')
  await open(p, '/tp/analytics', 1600); await shot(p, 'user/16-tp-analytics')
  await open(p, '/product', 1400); await shot(p, 'user/17-pp-dashboard')
  await open(p, '/product/registry'); await shot(p, 'user/18-pp-registry')
  await p.locator('tbody tr').first().click(); await settle(p, 400); await dialogShot(p, 'user/19-pp-form')
  await open(p, '/product/summary', 1400); await shot(p, 'user/20-pp-summary')
  await open(p, '/product/timeline'); await shot(p, 'user/21-pp-timeline')
  await open(p, '/settings/traffic-light/hr'); await shot(p, 'user/22-traffic-light')
  await open(p, '/profile'); await shot(p, 'user/23-profile')
  await open(p, '/guide#дашборд-службы-персонала', 1200); await shot(p, 'user/24-guide')

  // Правило «Нет данных / Не заполнено»: «Текучесть кадров» за последний месяц временно очищается
  if (wanted('user/32-hr-missing', 'user/33-hr-missing-entry')) {
    const months = await api(p, 'GET', '/hr/months')
    const key = months.map((m) => m.key).sort().at(-1)
    const month = await api(p, 'GET', `/hr/months/${key}`)
    const turnover = month.metrics.find((m) => m.key === 'turnover')
    await api(p, 'PUT', `/hr/months/${key}/metrics`, [{ metric_key: 'turnover', value: null, source_note: turnover.source_note || '' }])
    try {
      await open(p, '/hr?quick=6', 1400); await shot(p, 'user/32-hr-missing')
      await open(p, `/hr/data?month=${key}`)
      await p.locator('tr.missing').first().scrollIntoViewIfNeeded()
      await p.mouse.wheel(0, 260); await p.waitForTimeout(500)
      await shot(p, 'user/33-hr-missing-entry')
    } finally {
      await api(p, 'PUT', `/hr/months/${key}/metrics`, [{ metric_key: 'turnover', value: turnover.value, source_note: turnover.source_note || '' }])
    }
  }

  // администратор
  await open(p, '/admin/users'); await shot(p, 'admin/01-users')
  await open(p, '/admin/departments'); await shot(p, 'admin/05-departments')
  const techRow = p.locator('tr', { has: p.locator('.dep-name', { hasText: /^Техническая служба$/ }) })
  await techRow.getByRole('button', { name: /Руководители/ }).click(); await settle(p, 300)
  await dialogShot(p, 'admin/11-department-heads')
  await techRow.getByRole('button', { name: 'Изменить «Техническая служба»' }).click(); await settle(p, 300)
  await dialogShot(p, 'admin/12-department-edit')
  await open(p, '/admin/access-profiles', 1200); await shot(p, 'admin/18-access-profiles')
  await shot(p, 'admin/19-profile-comparison', { element: p.locator('section.card', { has: p.locator('h3', { hasText: 'Сравнение профилей' }) }) })
  await open(p, '/admin/directory'); await shot(p, 'admin/21-domain-login')
  await open(p, '/admin/audit'); await shot(p, 'admin/06-audit')
  await open(p, '/admin/palettes'); await shot(p, 'admin/07-palettes')
  await open(p, '/admin/system'); await shot(p, 'admin/08-system')
  await open(p, '/settings/traffic-light/hr'); await shot(p, 'admin/09-traffic-light-hr')
  await open(p, '/settings/partnership-lights'); await shot(p, 'admin/10-partnership-lights')
  await context.close()
}
{
  // Высокие окна: карточка пользователя (вкладка «Доступ» с личными настройками), создание, настройки структуры
  const { context, page: p } = await session('admin', 'admin123', { viewport: TALL })
  await open(p, '/admin/users')
  await p.locator('.urow[data-user="ceo"]').click(); await settle(p, 400)
  await p.getByRole('tab', { name: 'Доступ' }).click()
  await p.locator('[data-testid=effective-access]').waitFor()
  // Первому лицу — глубина детализации шире профиля и исходные записи (без сохранения)
  const depth = p.locator('li.dim-row[data-dimension=drill_depth]')
  await depth.locator('[data-action=override]').click()
  await depth.locator('select').selectOption('3')
  const records = p.locator('li.dim-row[data-dimension=can_view_records]')
  await records.locator('[data-action=override]').click()
  await records.getByRole('radio', { name: 'Реестры и списки' }).click()
  await settle(p, 400)
  await shot(p, 'admin/02-user-access')
  await p.getByRole('tab', { name: 'Полномочия' }).click(); await settle(p, 300)
  // Вкладка короткая — снимаем верх карточки (пять полномочий)
  const drawer = await p.locator('aside.drawer').boundingBox()
  await shot(p, 'admin/20-user-capabilities', { clip: { x: drawer.x, y: 0, width: drawer.width, height: 760 } })
  await p.keyboard.press('Escape'); await p.waitForTimeout(300)
  // Несохранённые изменения: система спрашивает, закрыть ли карточку
  const discard = p.getByRole('button', { name: /Закрыть без сохранения|Не сохранять|Закрыть/ })
  if (await p.getByRole('alertdialog').count() || await p.getByRole('dialog').count() > 1) await discard.last().click().catch(() => {})
  await open(p, '/admin/users')
  await click(p, 'Добавить пользователя'); await dialogShot(p, 'admin/03-user-create')
  await open(p, '/admin/departments')
  await click(p, 'Типы уровней и вложенность'); await dialogShot(p, 'admin/13-org-settings')
  await context.close()
}
{
  // Временный пароль — на тестовом пользователе, который сразу удаляется
  const { context, page: p } = await session('admin', 'admin123')
  await open(p, '/admin/users')
  await click(p, 'Добавить пользователя')
  const dialog = p.getByRole('dialog').first()
  await dialog.locator('input[name=username]').fill('demo.user')
  await dialog.locator('input[name=full_name]').fill('Петрова Анна Сергеевна')
  await dialog.getByRole('button', { name: /Создать/ }).click()
  await settle(p, 600)
  await shot(p, 'admin/04-temp-password')
  const users = await api(p, 'GET', '/users?search=demo.user')
  for (const u of users.items || users) await api(p, 'DELETE', `/users/${u.id}`)
  await context.close()
}
{
  // Структура компании глазами технического директора: «Вы здесь», руководитель по структуре
  // Меню свёрнуто, схема вписана в окно — структура видна целиком
  const { context, page: p } = await session('tech_dir', 'td123456')
  await open(p, '/org?view=chart', 600)
  await p.getByRole('button', { name: 'Свернуть меню' }).click()
  const fit = async () => { await p.getByRole('button', { name: 'Вписать схему в окно' }).click(); await p.waitForTimeout(1200) }
  await open(p, '/org?view=chart', 1500); await fit(); await shot(p, 'user/26-org-chart')
  await open(p, '/org?view=people&user=9', 1500); await fit(); await shot(p, 'user/27-org-people')
  await open(p, '/org?view=tree', 1200)
  // «Где я» прокручивает дерево к своему подразделению — для снимка показываем начало списка
  await p.evaluate(() => document.querySelectorAll('.org-body *').forEach((el) => { if (el.scrollTop) el.scrollTop = 0 }))
  await p.waitForTimeout(500)
  await shot(p, 'user/28-org-tree')
  await open(p, '/org?view=table&unit=3', 1200); await shot(p, 'user/29-org-table')
  await context.close()
}
{
  // «Мой доступ» первого лица: профиль «Высшее руководство», без исходных записей
  const { context, page: p } = await session('ceo', 'ceo12345')
  await open(p, '/profile#my-access', 1000)
  await shot(p, 'user/30-my-access', { element: p.locator('[data-testid=my-access]') })
  // «Нет доступа» с причиной: реестр — исходные записи, профилю они не положены.
  // (У сотрудника без служб, engineer, на /hr сейчас выводится текст «только администратору»:
  // NoAccessView не находит название недоступной службы — снимок с engineer после исправления.)
  await open(p, '/hr/registry', 800); await shot(p, 'user/31-no-access')
  await context.close()
}
{
  // Импорт и экспорт: проверка файлов (план), без применения
  const { context, page: p } = await session('admin', 'admin123')
  if (wanted('admin/14-transfer-structure', 'admin/15-transfer-employees')) {
    // У технического директора есть e-mail — по нему сопоставляются руководители (структура) и сотрудник (импорт)
    await api(p, 'PATCH', '/users/8', { email: 'm.sokolova@almi-partner.ru' })
  }
  if (wanted('admin/14-transfer-structure')) {
    const bundle = await api(p, 'GET', '/org/export')
    // Руководители демо-стенда без e-mail не сопоставляются — в файле оставляем только с e-mail
    for (const d of bundle.departments) d.heads = (d.heads || []).filter((h) => h.email)
    const tech = bundle.departments.find((d) => d.code === 'TECH')
    bundle.departments = bundle.departments.filter((d) => d.code !== 'AHO')
    bundle.departments.find((d) => d.code === 'COMMDIR').kind = 'direction'
    bundle.departments.push({
      key: 'impl', name: 'Группа внедрения', parent: tech.key, path: `${tech.path} / Группа внедрения`, kind: 'group',
      sort_order: 30, code: 'SUP-IMPL', external_id: null,
      heads: [{ email: 'o.kuznetsova@almi-partner.ru', name: 'Кузнецова Ольга Павловна', primary: true }],
    })
    bundle.settings.org_max_depth = 12
    await open(p, '/admin/org-transfer?tab=structure')
    await p.locator('[data-testid=structure-file]').setInputFiles(memoryFile('dashboards-structure-2026-11-01.json', 'application/json', JSON.stringify(bundle, null, 2)))
    await p.locator('[data-testid=structure-check]').click(); await settle(p, 600)
    await p.locator('[data-testid=structure-plan]').scrollIntoViewIfNeeded()
    await p.evaluate(() => document.querySelector('[data-testid=structure-plan]')?.scrollIntoView({ block: 'start' }))
    await p.mouse.wheel(0, -90); await p.waitForTimeout(400)
    await shot(p, 'admin/14-transfer-structure')
  }
  if (wanted('admin/15-transfer-employees')) {
    // Технический директор сопоставляется по e-mail; инженер без e-mail — вопрос «тот же человек?»
    const csv = [
      'Email;Логин;ФИО;Должность;Телефон;Подразделение',
      'm.sokolova@almi-partner.ru;tech_dir;Соколова Мария Игоревна;Директор по технологиям;+7 495 120-45-10;АЛМИ Партнер / Техническая дирекция',
      'i.petrov@almi-partner.ru;engineer;Петров Илья Сергеевич;Инженер технической поддержки;;АЛМИ Партнер / Техническая дирекция / Техническая служба / Группа поддержки AlterOS',
      'o.kuznetsova@almi-partner.ru;o.kuznetsova;Кузнецова Ольга Павловна;Инженер технической поддержки;;АЛМИ Партнер / Техническая дирекция / Техническая служба / Группа поддержки AlterOffice',
    ].join('\r\n')
    await open(p, '/admin/org-transfer?tab=employees')
    await p.locator('[data-testid=employees-file]').setInputFiles(memoryFile('employees.csv', 'text/csv', `\ufeff${csv}\r\n`))
    await p.locator('[data-testid=employees-check]').click(); await settle(p, 600)
    await p.evaluate(() => document.querySelector('[data-testid=employees-plan]')?.scrollIntoView({ block: 'start' }))
    await p.mouse.wheel(0, -90); await p.waitForTimeout(400)
    await shot(p, 'admin/15-transfer-employees')
  }
  if (wanted('admin/16-transfer-list')) {
    const list = [
      'email;ФИО;Подразделение;Должность;Руководитель;Руководит',
      'o.kuznetsova@almi-partner.ru;Кузнецова Ольга Павловна;АЛМИ Партнер / Техническая дирекция / Техническая служба / Группа поддержки AlterOffice;Ведущий инженер;;да',
      'a.belov@almi-partner.ru;Белов Артём Николаевич;АЛМИ Партнер / Техническая дирекция / Техническая служба / Группа поддержки AlterOffice;Инженер технической поддержки;;',
      'n.orlova@almi-partner.ru;Орлова Наталья Викторовна;АЛМИ Партнер / Коммерческая дирекция / Отдел продаж;Менеджер по продажам;;',
    ].join('\n')
    await open(p, '/admin/org-transfer?tab=list')
    await p.locator('[data-testid=list-text]').fill(list)
    await p.locator('[data-testid=list-create]').check()
    await p.locator('[data-testid=list-check]').click(); await settle(p, 600)
    await p.evaluate(() => document.querySelector('[data-testid=import-plan]')?.scrollIntoView({ block: 'start' }))
    await p.mouse.wheel(0, -90); await p.waitForTimeout(400)
    await shot(p, 'admin/16-transfer-list')
  }
  await open(p, '/admin/org-transfer?tab=ad'); await shot(p, 'admin/17-transfer-ad')
  await context.close()
}
// ---------------------------------------------------------------- сквозной отчёт (0.3.0)
// Демо-данные: последний месяц — июль 2026; пропуск «Выполнение плана работ» у Службы маркетинга,
// заметка «под контролем» у Технической службы. Ввод и загрузка — только проверка, без сохранения.
const REPORT = { width: 1440, height: 1140 }
{
  // Первое лицо: статус компании, «почему такой статус», матрица с замком детализации; карточка «Обзора»
  const { context, page: p } = await session('ceo', 'ceo12345', { viewport: REPORT })
  await open(p, '/reports?period=2026-07', 1200)
  await shot(p, 'user/34-report-ceo')
  await open(p, '/', 1200)
  await shot(p, 'user/41-overview-report', { element: p.locator('[data-testid=report-summary]') })
  await context.close()
}
{
  // Вся компания: оргсхема статусов — все уровни раскрыты, схема вписана в окно (пропуски, «под контролем»)
  const { context, page: p } = await session('admin', 'admin123')
  await open(p, '/reports?period=2026-07&view=chart', 600)
  await p.getByRole('button', { name: 'Свернуть меню' }).click()
  await open(p, '/reports?period=2026-07&view=chart', 1500)
  const chart = p.locator('[data-testid=report-chart]')
  await chart.getByRole('button', { name: /Развернуть всё/ }).click(); await p.waitForTimeout(600)
  await chart.scrollIntoViewIfNeeded()
  await chart.getByRole('button', { name: /Вписать/ }).click(); await p.waitForTimeout(1200)
  // Без пустого холста под схемой: до нижней карточки
  const box = await chart.boundingBox()
  const bottom = await chart.locator('article.ruc').evaluateAll((els) => Math.max(...els.map((e) => e.getBoundingClientRect().bottom)))
  await shot(p, 'user/35-report-chart', { clip: { x: box.x, y: box.y, width: box.width, height: Math.min(box.height, bottom - box.y + 36) } })
  await context.close()
}
{
  // Руководитель направления: панель подразделения с трендами, подсказка ячейки, ввод и загрузка
  const { context, page: p } = await session('tech_dir', 'td123456', { viewport: TALL })
  await open(p, '/reports?period=2026-07&unit=3', 1600)
  await shot(p, 'user/36-report-panel')
  await context.close()
}
{
  const { context, page: p } = await session('tech_dir', 'td123456', { viewport: REPORT })
  if (wanted('user/37-report-tooltip')) {
    await open(p, '/reports?period=2026-07', 1200)
    const target = p.locator('tr.mx-row[data-unit="3"] td[data-key="fin.costs"]')
    await target.hover(); await p.waitForTimeout(500)
    const tip = await p.locator('.mx-tip').boundingBox()
    const cell = await target.boundingBox()
    const table = await p.getByTestId('report-matrix').boundingBox()
    const x = Math.max(0, table.x - 2)
    const y = Math.max(0, Math.min(tip.y, cell.y) - 60)
    const right = Math.min(REPORT.width, Math.max(tip.x + tip.width, cell.x + cell.width) + 120)
    const bottom = Math.min(REPORT.height, Math.max(tip.y + tip.height, cell.y + cell.height) + 70)
    await shot(p, 'user/37-report-tooltip', { clip: { x, y, width: right - x, height: bottom - y } })
  }
  await context.close()
}
{
  // Ввод показателей: одно изменённое значение (без сохранения) — выделение ячейки и панель «Сохранить»
  const { context, page: p } = await session('tech_dir', 'td123456')
  await open(p, '/reports/entry?period=2026-07', 1000)
  if (wanted('user/39-report-entry')) {
    await p.locator('[data-testid=entry-grid] input[data-field=value]').first().fill('97')
    await p.mouse.move(5, 5); await p.waitForTimeout(500)
    await shot(p, 'user/39-report-entry')
    await p.getByRole('button', { name: 'Отменить', exact: true }).click(); await p.waitForTimeout(300)
  }
  if (wanted('user/40-report-import')) {
    // План загрузки: новое значение, изменения и строка вне области ввода (Служба маркетинга)
    const rows = [
      'Подразделение;Показатель;Период;Значение;Цель;Комментарий',
      'MKT;Выполнение плана работ;2026-07;90;;',
      'АЛМИ Партнер / Техническая дирекция / ИТ-служба;Выполнение плана работ;2026-07;98,5;100;',
      'SUP-OS;ops.plan;2026-07;95;100;',
      'TECH;Удовлетворённость клиентов;2026-07;4,6;;',
    ]
    await p.getByTestId('entry-import').click()
    const dialog = p.getByRole('dialog').first()
    await dialog.getByTestId('values-file').setInputFiles(memoryFile('Показатели 2026-07.csv', 'text/csv', `\ufeff${rows.join('\r\n')}\r\n`))
    await dialog.getByTestId('import-check').click(); await settle(p, 600)
    await dialog.getByRole('radio', { name: 'Все' }).click(); await p.waitForTimeout(400)
    await shot(p, 'user/40-report-import')
    await p.keyboard.press('Escape'); await p.waitForTimeout(250)
  }
  await context.close()
}
{
  // Сотрудник: своё подразделение, операционные показатели, без выгрузки
  const { context, page: p } = await session('engineer', 'en123456', { viewport: REPORT })
  await open(p, '/reports?period=2026-07', 1200)
  const card = await p.locator('section.matrix-card').boundingBox()
  await shot(p, 'user/38-report-engineer', { clip: { x: 0, y: 0, width: REPORT.width, height: Math.min(REPORT.height, card.y + card.height + 28) } })
  await context.close()
}
{
  // Каталог показателей, редактор с предпросмотром светофора, подразделения служб
  const { context, page: p } = await session('admin', 'admin123', { viewport: TALL })
  await open(p, '/admin/indicators', 1000)
  await shot(p, 'admin/22-indicators')
  await shot(p, 'admin/24-service-units', { element: p.locator('[data-testid=service-units]') })
  if (wanted('admin/23-indicator-editor')) {
    await p.getByRole('button', { name: 'Изменить «Затраты»' }).click(); await settle(p, 400)
    const dialog = p.getByRole('dialog').first()
    await dialog.getByLabel('Значение для проверки').fill('12,4')
    await dialog.getByLabel('Цель для проверки').fill('11,3')
    await p.waitForTimeout(300)
    await dialogShot(p, 'admin/23-indicator-editor')
  }
  await context.close()
}
{
  const { context, page: p } = await session('admin', 'admin123', { theme: 'dark' })
  await open(p, '/tp', 1600); await shot(p, 'user/25-dark-theme')
  await context.close()
}
// ---------------------------------------------------------------- входящие данные и интеграции (0.4.0)
// Данные создаются через API: ключ «1С: Бухгалтерия» и приём файла значений по нему (применяется по правилу)
// и его повтор; файлы в папке «Входящие» (недельный отчёт ТП — по правилу, нераспознанный файл, испорченная
// выгрузка Naumen); подключения «По Делу», Jira (поддельные), Confluence (неверный токен — неудачная проверка)
// и 1С (не проверено); загрузка метрик месяца руководителем службы персонала — через окно загрузки.
const INBOX_DIR = process.env.SHOTS_INBOX_DIR || ''
const FAKE = { podelu: 'http://podelu.almi-partner.local', jira: 'http://jira.almi-partner.local', confluence: 'http://confluence.almi-partner.local' }
const JIRA_RULES = [
  {
    indicator: 'jira.resolved', name: 'Решено задач в Jira', unit: 'шт.', direction: 'higher_is_better', measure: 'count',
    jql: 'project = SUP AND component = "{unit_code}" AND resolved >= "{month_start}" AND resolved < "{next_month_start}"',
    units: { 'SUP-OS': 'AlterOS', 'SUP-OFFICE': 'AlterOffice' },
  },
  {
    indicator: 'jira.spent_hours', name: 'Затрачено в Jira', measure: 'sum', field: 'timespent',
    unit_jql: { IT: 'project = IT AND worklogDate >= "{month_start}" AND worklogDate < "{next_month_start}"' },
  },
  {
    indicator: 'jira.backlog', name: 'Открытые задачи поддержки', unit: 'шт.', direction: 'lower_is_better', green: 40, yellow: 60,
    jql: 'project = SUP AND statusCategory != Done', units: ['TECH'],
  },
]
const ONEC_QUERIES = [
  {
    name: 'ФОТ', entity: 'Document_НачислениеЗарплаты',
    filter: "Date ge datetime'{month_start}' and Date le datetime'{month_end}' and Posted eq true",
    select: 'Подразделение_Key,ВсегоНачислено', value_field: 'ВсегоНачислено', aggregate: 'sum',
    department_field: 'Подразделение_Key', scale: 0.000001, indicator: 'fin.payroll',
  },
]
const csv = (rows) => `﻿${rows.join('\r\n')}\r\n`

/** Запрос к приёму по API с ключом (без сессии). */
async function inbound(page, key, filename, content, fields = {}) {
  const response = await page.request.post(`${BASE}/api/inbound/v1/files`, {
    headers: { Authorization: `Bearer ${key}` },
    multipart: { file: { name: filename, mimeType: 'text/csv', buffer: Buffer.from(content, 'utf8') }, ...fields },
  })
  if (!response.ok()) throw new Error(`inbound ${filename}: ${response.status()} ${await response.text()}`)
  return response.json()
}

/** Файл в папку «Входящие», «старше» INBOX_SETTLE_SECONDS — планировщик возьмёт его сразу. */
function dropFile(folder, name, buffer) {
  const dir = folder ? `${INBOX_DIR}/${folder}` : INBOX_DIR
  mkdirSync(dir, { recursive: true })
  const path = `${dir}/${name}`
  writeFileSync(path, buffer)
  const past = new Date(Date.now() - 5 * 60 * 1000)
  utimesSync(path, past, past)
}

async function upload(page, filename, content, fields = {}) {
  const csrf = (await page.context().cookies()).find((c) => c.name === 'ds_csrf')?.value
  const response = await page.request.post(`${BASE}/api/inbox`, {
    headers: { 'X-CSRF-Token': csrf },
    multipart: { file: { name: filename, mimeType: 'text/csv', buffer: Buffer.from(content, 'utf8') }, ...fields },
  })
  if (!response.ok()) throw new Error(`upload ${filename}: ${response.status()} ${await response.text()}`)
  return response.json()
}

async function integration(page, body) {
  const existing = (await api(page, 'GET', '/integrations')).find((i) => i.name === body.name)
  return existing || api(page, 'POST', '/integrations', body)
}

if (wanted('user/42', 'user/43', 'user/44', 'admin/25', 'admin/26', 'admin/27', 'admin/28', 'admin/29', 'admin/30', 'admin/31', 'admin/32', 'admin/33')) {
  const { context, page: p } = await session('admin', 'admin123', { viewport: TALL })
  // Ключи: рабочий ключ 1С и отозванный прежний
  const keys = await api(p, 'GET', '/integrations/keys')
  let key = null
  if (!keys.some((k) => k.name === '1С: Бухгалтерия')) {
    key = (await api(p, 'POST', '/integrations/keys', { name: '1С: Бухгалтерия', scopes: ['files', 'status'] })).key
    const old = await api(p, 'POST', '/integrations/keys', { name: '1С: Бухгалтерия (прежний)', scopes: ['files'] })
    await api(p, 'POST', `/integrations/keys/${old.id}/revoke`)
  }
  await api(p, 'PUT', '/inbox/rules', { rules: [
    { source: 'api', dataset: 'indicators', auto_apply: true },
    { source: 'folder', dataset: 'tp-weekly', auto_apply: true },
    { source: 'integration', dataset: 'structure', auto_apply: false },
  ] })
  if (key) {
    // Финансовые показатели из 1С за октябрь: применяется сразу по правилу, второй раз — повтор
    const values = csv([
      'Подразделение;Показатель;Период;Значение;Цель;Комментарий',
      'TECH;fin.costs;2026-10;11,6;11,3;', 'IT;fin.costs;2026-10;4,1;4,5;', 'COMM;fin.revenue;2026-10;33,8;32;',
      'COMMDIR;fin.budget;2026-10;97;100;', 'MKT;fin.payroll;2026-10;2,1;2;',
    ])
    await inbound(p, key, 'Показатели из 1С 2026-10.csv', values, { dataset: 'indicators' })
    await inbound(p, key, 'Показатели из 1С 2026-10.csv', values, { dataset: 'indicators' })
  }
  if (INBOX_DIR) {
    const tp = await p.request.get(`${BASE}/api/tp/reports/export.xlsx`)
    dropFile('tp-weekly', 'Итоговый отчёт ТП по неделям.xlsx', await tp.body())
    dropFile('naumen', 'Заявки Naumen октябрь.xlsx', Buffer.from('Номер;Дата регистрации\n', 'utf8'))
    dropFile('', 'выгрузка.csv', Buffer.from(csv(['Столбец 1;Столбец 2', 'а;б']), 'utf8'))
    await api(p, 'POST', '/inbox/folder/scan')
  }
  // Реестр партнёрств, загруженный не тем файлом, — отклонён с причиной
  const partners = await upload(p, 'Реестр партнёрств.csv', csv(['№;Партнёр;Продукт партнёра;Продукт АЛМИ;Статус', '1;Базальт СПО;Альт Сервер 11;AlterOS 2.7;Сертифицировано']), { dataset: 'partnerships' })
  if (partners.actions?.reject) await api(p, 'POST', `/inbox/${partners.id}/reject`, { reason: 'Выгрузка за прошлый год — нужна текущая' })

  // Подключения
  const podelu = await integration(p, {
    kind: 'podelu', name: 'По Делу',
    config: { base_url: FAKE.podelu, login: 'dashboards-sync', data_list: 'Данные для дашбордов', data_tags: [] },
    secrets: { password: 'demo-password' },
    schedule: { mode: 'interval', minutes: 30, actions: ['pull'] },
  })
  if (!podelu.enabled) {
    await api(p, 'POST', `/integrations/${podelu.id}/check`)
    await api(p, 'PATCH', `/integrations/${podelu.id}`, { enabled: true })
    await api(p, 'POST', `/integrations/${podelu.id}/run`, { action: 'sync' })
    await api(p, 'POST', `/integrations/${podelu.id}/run`, { action: 'pull' })
  }
  const jira = await integration(p, {
    kind: 'jira', name: 'Jira — поддержка',
    config: { base_url: FAKE.jira, instance: 'server', rules: JIRA_RULES, months: 2, owner_service: 'tech' },
    secrets: { token: 'demo-expired-token' },
    schedule: { mode: 'daily', time: '06:30', weekdays: [], actions: ['refresh'] },
  })
  if (!jira.enabled) {
    // Первый запуск — с устаревшим токеном (ошибка в журнале), затем токен заменён
    await api(p, 'POST', `/integrations/${jira.id}/run`, { action: 'refresh' })
    await api(p, 'PATCH', `/integrations/${jira.id}`, { secrets: { token: 'demo-jira-token' } })
    await api(p, 'POST', `/integrations/${jira.id}/check`)
    await api(p, 'PATCH', `/integrations/${jira.id}`, { enabled: true })
    await api(p, 'POST', `/integrations/${jira.id}/run`, { action: 'preview' })
    await api(p, 'POST', `/integrations/${jira.id}/run`, { action: 'refresh' })
    await api(p, 'POST', `/integrations/${jira.id}/run`, { action: 'refresh' })
  }
  const confluence = await integration(p, {
    kind: 'confluence', name: 'Confluence — сквозной отчёт',
    config: { base_url: FAKE.confluence, instance: 'server', space: 'REPORTS' },
    secrets: { token: 'demo-old-token' },
    schedule: { mode: 'daily', time: '09:00', weekdays: [1], actions: ['publish'] },
  })
  if (!confluence.last_error) await api(p, 'POST', `/integrations/${confluence.id}/check`)
  await integration(p, {
    kind: 'onec', name: '1С: ЗУП',
    config: { base_url: 'https://1c.almi-partner.ru/zup/odata/standard.odata', login: 'dashboards', queries: ONEC_QUERIES },
    secrets: { password: 'demo-password' },
  })
  await context.close()

  {
    // Руководитель службы персонала загружает метрики месяца: окно загрузки и карточка с планом
    const { context: c, page: hr } = await session('hr_head', 'hr123456', { viewport: TALL })
    await open(hr, '/inbox', 800)
    await hr.getByTestId('inbox-upload').click()
    const dialog = hr.getByRole('dialog').first()
    await dialog.waitFor()
    await dialog.getByTestId('inbox-file').setInputFiles(memoryFile('Метрики персонала 2026-08.csv', 'text/csv', csv([
      'Метрика;2026-07;2026-08', 'Всего сотрудников;189;192', 'Среднее время закрытия позиции;34;31', 'Текучесть кадров;;0,9',
      'Принятые офферы;;86', 'Прохождение испытательного срока (общее);;94',
    ])))
    await dialog.getByTestId('inbox-dataset').selectOption('hr-months')
    await hr.setViewportSize(NORMAL); await hr.waitForTimeout(500)
    await shot(hr, 'user/43-inbox-upload')
    await hr.setViewportSize(TALL)
    await dialog.getByTestId('inbox-upload-submit').click()
    await hr.getByTestId('inbox-plan').waitFor()
    await settle(hr, 3800)   // всплывающее «Файл получен…» успевает закрыться
    await shot(hr, 'user/44-inbox-item')
    await c.close()
  }

  const { context: c2, page: a } = await session('admin', 'admin123', { viewport: TALL })
  await open(a, '/inbox', 1000); await shot(a, 'user/42-inbox', { clip: { x: 0, y: 0, width: TALL.width, height: 1000 } })
  await open(a, '/inbox?tab=rules', 800); await shot(a, 'admin/25-inbox-rules', { element: a.getByTestId('inbox-rules') })
  await open(a, '/inbox?tab=folder', 1000); await shot(a, 'admin/26-inbox-folder')
  await open(a, '/admin/integrations', 1200); await shot(a, 'admin/27-integrations')
  if (wanted('admin/28')) {
    await a.getByTestId('integration-add').click()
    await dialogShot(a, 'admin/28-integration-kinds')
  }
  if (wanted('admin/29')) {
    await a.locator('[data-kind=jira]').getByTestId('integration-edit').click(); await settle(a, 500)
    const editor = a.getByRole('dialog').first()
    await editor.locator('[data-field=rules]').scrollIntoViewIfNeeded()
    await editor.getByRole('heading', { name: 'Подключение' }).scrollIntoViewIfNeeded()
    await a.waitForTimeout(400)
    await shot(a, 'admin/29-integration-jira')
    await a.keyboard.press('Escape'); await a.waitForTimeout(300)
  }
  if (wanted('admin/30')) {
    await a.locator('[data-kind=podelu]').getByTestId('integration-edit').click(); await settle(a, 500)
    const editor = a.getByRole('dialog').first()
    const schedule = editor.locator('section.sec', { has: a.getByTestId('schedule-editor') })
    await schedule.scrollIntoViewIfNeeded(); await a.waitForTimeout(400)
    const box = await schedule.boundingBox()
    await shot(a, 'admin/30-integration-schedule', { clip: { x: box.x - 24, y: box.y - 20, width: box.width + 48, height: box.height + 40 } })
    await a.keyboard.press('Escape'); await a.waitForTimeout(300)
  }
  if (wanted('admin/31')) {
    await a.locator('[data-kind=jira]').getByTestId('integration-journal').click(); await settle(a, 600)
    await shot(a, 'admin/31-integration-runs')
    await a.keyboard.press('Escape'); await a.waitForTimeout(300)
  }
  await open(a, '/admin/integrations?tab=keys', 800)
  if (wanted('admin/33')) {
    // Новый ключ через окно: значение показывается один раз
    await a.setViewportSize(NORMAL)
    await a.getByTestId('key-create').click()
    const dialog = a.getByRole('dialog').first()
    await dialog.getByTestId('key-name').fill('Скрипт выгрузки Naumen')
    await dialog.getByTestId('key-issue').click()
    await a.getByTestId('one-time-key').waitFor(); await a.waitForTimeout(400)
    await shot(a, 'admin/33-inbound-key-once')
    await a.getByTestId('key-done').click(); await settle(a, 600)
    await a.setViewportSize(TALL)
  }
  await open(a, '/admin/integrations?tab=keys', 800); await shot(a, 'admin/32-inbound-keys')
  await c2.close()
}
await browser.close()
