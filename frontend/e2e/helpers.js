export const PASSWORDS = { admin: 'admin123', hr_head: 'hr123456', tp_lead: 'tp123456', product: 'pp123456', viewer: 'view1234', it_viewer: 'it123456' }

export async function login(page, username = 'admin') {
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
