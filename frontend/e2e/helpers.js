import { expect } from '@playwright/test'

export const PASSWORDS = {
  admin: 'admin123', hr_head: 'hr123456', tp_lead: 'tp123456', product: 'pp123456', viewer: 'view1234', it_viewer: 'it123456',
  ceo: 'ceo12345', tech_dir: 'td123456', engineer: 'en123456',
}

export async function login(page, username = 'admin') {
  // Окно «Что нового» не перекрывает страницы в тестах
  await page.addInitScript(() => localStorage.setItem('ds_seen_version', '9.9.9'))
  await page.goto('/login')
  await page.fill('input[name=username]', username)
  await page.fill('input[name=password]', PASSWORDS[username])
  await page.click('button[type=submit]')
  await page.waitForURL((url) => !url.pathname.startsWith('/login'))
}

/** Ошибки страницы (исключения JS) — тест падает, если они есть. */
export function collectErrors(page) {
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  return errors
}

/** Уникальная метка для имён, которые создают тесты: повторный прогон на той же базе не конфликтует. */
export function uniq(prefix = 'e2e') {
  return `${prefix}-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 5)}`
}

/**
 * Запрос к API от имени вошедшего пользователя (cookie сессии общая со страницей).
 * Для изменяющих запросов подставляется CSRF-токен из cookie ds_csrf.
 */
export async function api(page, method, path, data) {
  const headers = {}
  if (method !== 'GET') {
    const cookies = await page.context().cookies()
    headers['X-CSRF-Token'] = cookies.find((c) => c.name === 'ds_csrf')?.value || ''
  }
  const response = await page.request.fetch(`/api${path}`, { method, headers, data })
  if (!response.ok()) throw new Error(`${method} ${path}: ${response.status()} ${await response.text()}`)
  const type = response.headers()['content-type'] || ''
  return type.includes('application/json') ? response.json() : response.body()
}

export const apiGet = (page, path) => api(page, 'GET', path)

/** Число из текста интерфейса: «9 757 ч» → 9757, «−1,87 п.п.» → -1.87, «—» → null. */
export function num(text) {
  const clean = String(text ?? '').replace(/[\s\u00a0\u202f]/g, '').replace('\u2212', '-').replace(',', '.')
  const match = clean.match(/-?\d+(\.\d+)?/)
  return match ? Number(match[0]) : null
}

/** Как formatNumber в интерфейсе: ru-RU, до digits знаков, без незначащих нулей. */
export function ru(value, digits = 2) {
  return Number(value).toLocaleString('ru-RU', { maximumFractionDigits: Number.isInteger(value) ? 0 : digits }).replace('-', '−')
}

/** Значение карточки показателя (KpiCard) по подписи. */
export function kpi(page, label) {
  return page.locator('.kpi.card').filter({ has: page.locator('.label', { hasText: label }) }).first()
}

export async function kpiValue(page, label) {
  return num(await kpi(page, label).locator('.value').innerText())
}

const MIME = {
  xlsx: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  pdf: 'application/pdf',
  csv: 'text/csv',
}

/**
 * Скачивание файла: щелчок по кнопке → ответ сервера (тип, непустое тело) и сохранённый файл с понятным
 * именем. Возвращает { name, body, response }.
 */
export async function expectDownload(page, trigger, { ext, name }) {
  // Имя, которое приложение передаёт браузеру (атрибут download). Имя из события download в Chromium
  // через CDP для кириллицы всегда «download» — поэтому проверяется атрибут ссылки.
  await page.evaluate(() => {
    if (window.__downloads) return
    window.__downloads = []
    const click = HTMLAnchorElement.prototype.click
    HTMLAnchorElement.prototype.click = function () {
      if (this.download) window.__downloads.push(this.download)
      return click.call(this)
    }
  })
  const before = await page.evaluate(() => window.__downloads.length)
  const responsePromise = page.waitForResponse((r) => /\/api\/(pdf\/|.*export)/.test(r.url()) && r.request().method() === 'GET')
  const downloadPromise = page.waitForEvent('download')
  await trigger()
  const [response, download] = await Promise.all([responsePromise, downloadPromise])
  expect(response.status(), response.url()).toBe(200)
  expect(response.headers()['content-type']).toContain(MIME[ext])
  expect(response.headers()['content-disposition']).toMatch(/^attachment; filename="[\x20-\x7e]+"; filename\*=UTF-8''/)
  const filename = await page.evaluate((i) => window.__downloads[i], before)
  expect(filename).toMatch(new RegExp(`\\d{4}-\\d{2}-\\d{2}\\.${ext}$`))
  if (name) expect(filename).toContain(name)
  const path = await download.path()
  const { readFileSync } = await import('node:fs')
  const body = readFileSync(path)
  expect(body.length).toBeGreaterThan(200)
  if (ext === 'pdf') expect(body.subarray(0, 4).toString()).toBe('%PDF')
  if (ext === 'xlsx') expect(body.subarray(0, 2).toString()).toBe('PK')
  if (ext === 'csv') expect(body.subarray(0, 3).toString('hex')).toBe('efbbbf')
  return { name: filename, body, path, response }
}

/** Есть ли на холсте графика пиксели заданного цвета (палитра применилась к графику). */
export async function canvasColorShare(locator, hex, tolerance = 6) {
  return locator.evaluate((root, [color, tol]) => {
    const canvas = root.querySelector('canvas')
    if (!canvas) return 0
    const target = [1, 3, 5].map((i) => parseInt(color.slice(i, i + 2), 16))
    const { data } = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height)
    let hits = 0
    for (let i = 0; i < data.length; i += 4) {
      if (data[i + 3] < 250) continue
      if (Math.abs(data[i] - target[0]) <= tol && Math.abs(data[i + 1] - target[1]) <= tol && Math.abs(data[i + 2] - target[2]) <= tol) hits++
    }
    return hits
  }, [hex.toLowerCase(), tolerance])
}

/** Подтвердить диалог подтверждения (ConfirmDialog). */
export async function confirmDialog(page, text) {
  const dialog = page.getByRole('dialog').last()
  await dialog.getByRole('button', { name: text, exact: true }).click()
}
