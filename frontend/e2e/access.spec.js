import { expect, test } from '@playwright/test'
import { collectErrors, login } from './helpers'

/**
 * Модель доступа 2.0 (ADR-0009) и администрирование пользователей (ADR-0008): создание сотрудника
 * с профилем «Сотрудник» и временным паролем, его права в интерфейсе, личная настройка поверх профиля,
 * профили доступа, высшее руководство, индивидуальная настройка 0.1.0, вход по домену.
 * Тесты идут по порядку: следующие используют пользователя, созданного первым.
 */
test.describe.configure({ mode: 'serial' })

const stamp = Date.now().toString(36)
const USER = { username: `e2e_${stamp}`, full_name: `Тестов Сотрудник ${stamp}` }
const NEW_PASSWORD = `Svoy-parol-${stamp}`
const PROFILE = { key: `fin-${stamp}`, name: `Финконтроль ${stamp}` }
let temporaryPassword = ''

async function signIn(page, username, password) {
  await page.goto('/login')
  await page.fill('input[name=username]', username)
  await page.fill('input[name=password]', password)
  await page.click('button[type=submit]')
  await page.waitForURL((url) => !url.pathname.startsWith('/login'))
}

const sidebar = (page) => page.locator('aside.sidebar')
const userRow = (page) => page.locator(`[data-user="${USER.username}"]`)

async function openUserAccess(page) {
  await page.goto(`/admin/users?search=${USER.username}`)
  await userRow(page).getByRole('button', { name: `Доступ: ${USER.full_name}` }).click()
  await expect(page.getByTestId('effective-access')).toBeVisible()
}

test('администратор создаёт сотрудника с профилем «Сотрудник» и временным паролем', async ({ page }) => {
  const errors = collectErrors(page)
  await login(page, 'admin')
  await page.goto('/admin/users')
  await expect(page.getByTestId('users-summary')).toContainText(/\d+ всего\s*·\s*\d+ активн/)

  await page.getByTestId('user-add').click()
  const dialog = page.getByRole('dialog').filter({ hasText: 'Новый пользователь' })
  await dialog.locator('input[name=username]').fill(USER.username)
  await dialog.locator('input[name=full_name]').fill(USER.full_name)
  await dialog.locator('input[name=position]').fill('Инженер')
  await dialog.getByTestId('create-profile').selectOption({ label: 'Сотрудник' })
  // Профиль «Сотрудник» не даёт служб — выдаём просмотр двух служб лично
  await dialog.locator('select[data-service=tech]').selectOption('viewer')
  await dialog.locator('select[data-service=project_product]').selectOption('viewer')
  await expect(dialog.locator('[data-method=password]')).toHaveClass(/\bon\b/)
  await expect(dialog.locator('[data-method=ldap]')).toHaveClass(/\boff\b/)
  await dialog.getByTestId('create-submit').click()

  const secret = page.getByTestId('temporary-password')
  await expect(secret).toBeVisible()
  temporaryPassword = (await secret.textContent()).trim()
  expect(temporaryPassword.length).toBeGreaterThanOrEqual(8)
  await page.getByRole('button', { name: 'Готово' }).click()

  await page.getByPlaceholder('ФИО, логин, e-mail, должность').fill(USER.username)
  await expect(userRow(page)).toContainText('Сотрудник')
  await expect(userRow(page)).toContainText('временный пароль')
  await expect(userRow(page)).toContainText('лично: Техподдержка — просмотр')
  expect(errors).toEqual([])
})

test('сотрудник меняет пароль, не видит реестров и выгрузки, видит только операционные данные', async ({ page }) => {
  const errors = collectErrors(page)
  await signIn(page, USER.username, temporaryPassword)
  await expect(page).toHaveURL(/\/profile\?password=required/)
  await page.locator('input[autocomplete=current-password]').fill(temporaryPassword)
  await page.locator('input[autocomplete=new-password]').nth(0).fill(NEW_PASSWORD)
  await page.locator('input[autocomplete=new-password]').nth(1).fill(NEW_PASSWORD)
  await page.getByRole('button', { name: 'Сменить пароль' }).click()
  await expect(page).toHaveURL(/\/$/)

  // Меню: службы есть, реестров нет; под именем — профиль доступа
  await expect(sidebar(page).getByTestId('sidebar-profile')).toHaveText('Сотрудник')
  await expect(sidebar(page).getByRole('link', { name: 'Сводка по годам' })).toBeVisible()
  await expect(sidebar(page).getByRole('link', { name: 'Заявки Naumen' })).toBeVisible()
  for (const label of ['Реестр партнёрств', 'Хронология', 'Приёмы и увольнения']) {
    await expect(sidebar(page).getByRole('link', { name: label })).toHaveCount(0)
  }

  // Кнопок выгрузки нет
  await page.goto('/tp')
  await expect(page.getByRole('heading', { level: 1 })).toContainText('поддержк')
  await expect(page.getByRole('button', { name: 'PDF' })).toHaveCount(0)
  await page.goto('/tp/registry')
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Недельный отчёт')
  await expect(page.getByRole('button', { name: 'Excel' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'CSV' })).toHaveCount(0)
  await page.goto('/product')
  await expect(page.getByRole('heading', { level: 1 })).toContainText('артнёрств')
  await expect(page.getByRole('link', { name: 'Реестр', exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'PDF' })).toHaveCount(0)

  // Прямой адрес реестра — «Нет доступа» с причиной
  await page.goto('/product/registry')
  await expect(page.getByRole('heading', { name: 'Нет доступа' })).toBeVisible()
  await expect(page.getByText('исходные записи службы')).toBeVisible()

  // Только операционные данные: ответственные Naumen скрыты
  await page.goto('/tp/naumen')
  await expect(page.getByText('Ответственные скрыты: нет доступа к персональным данным')).toBeVisible()

  // «Мой доступ» простыми словами
  await page.goto('/profile')
  const mine = page.getByTestId('my-access')
  await expect(mine).toContainText('Профиль доступа: Сотрудник')
  await expect(mine).toContainText('Только операционные')
  await expect(mine).toContainText('Персональные данные (ФИО, должности, причины увольнения) скрыты')
  await expect(mine).toContainText('Выгрузка: Недоступна')
  await expect(mine).toContainText('Техническая поддержка')
  expect(errors).toEqual([])
})

test('личная настройка поверх профиля: выгрузка и записи — сотрудник видит Excel', async ({ page }) => {
  const errors = collectErrors(page)
  await login(page, 'admin')
  await openUserAccess(page)
  const exportRow = page.locator('li.dim-row[data-dimension=can_export]')
  await expect(exportRow).toContainText('Как в профиле: Запрещена')
  await exportRow.getByRole('button', { name: 'Задать лично' }).click()
  await exportRow.getByRole('radio', { name: 'Разрешена' }).click()
  const recordsRow = page.locator('li.dim-row[data-dimension=can_view_records]')
  await recordsRow.getByRole('button', { name: 'Задать лично' }).click()
  await recordsRow.getByRole('radio', { name: 'Реестры и списки' }).click()

  // Живая сводка называет источник каждого значения
  const summary = page.getByTestId('effective-access')
  await expect(summary.locator('[data-dimension=can_export]')).toContainText('Разрешена')
  await expect(summary.locator('[data-dimension=can_export]')).toContainText('задано лично')
  await expect(summary.locator('[data-dimension=org_scope]')).toContainText('из профиля «Сотрудник»')
  // Своё подразделение без подразделения — предупреждение
  await expect(summary).toContainText('нет ни основного, ни дополнительных подразделений')
  await page.getByTestId('user-save').click()
  await expect(page.getByText('Изменения сохранены')).toBeVisible()

  // Сотрудник видит реестр и выгрузку
  await page.context().clearCookies()
  await signIn(page, USER.username, NEW_PASSWORD)
  await expect(sidebar(page).getByRole('link', { name: 'Реестр партнёрств' })).toBeVisible()
  await page.goto('/product/registry')
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Реестр партнёрств')
  await expect(page.getByRole('button', { name: 'Excel' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'PDF' })).toBeVisible()
  // Персональных данных по-прежнему нет: реестр приёмов и увольнений закрыт
  await expect(sidebar(page).getByRole('link', { name: 'Приёмы и увольнения' })).toHaveCount(0)
  expect(errors).toEqual([])
})

test('профили доступа: создание, изменение, сравнение, защита от удаления, удаление', async ({ page }) => {
  const errors = collectErrors(page)
  await login(page, 'admin')
  await page.goto('/admin/access-profiles')
  await expect(page.getByText('Доступ пользователя = профиль + личные настройки.')).toBeVisible()
  await expect(page.locator('[data-profile=employee]').getByRole('button', { name: 'Удалить профиль «Сотрудник»' })).toBeDisabled()

  await page.getByTestId('profile-add').click()
  let dialog = page.getByRole('dialog').filter({ hasText: 'Новый профиль доступа' })
  await dialog.locator('input[name=name]').fill(PROFILE.name)
  await expect(dialog.locator('input[name=key]')).toHaveValue(/^finkontrol-/)
  await dialog.locator('input[name=key]').fill(PROFILE.key)
  await dialog.locator('li[data-dimension=org_scope]').getByRole('radio', { name: 'Вся компания' }).click()
  await dialog.locator('li[data-dimension=data_classes]').getByText('Финансовые', { exact: true }).click()
  await dialog.locator('li[data-dimension=can_export]').getByRole('radio', { name: 'Запрещена' }).click()
  await dialog.locator('[data-service=hr] select').selectOption('viewer')
  await dialog.getByTestId('profile-save').click()

  const card = page.locator(`[data-profile="${PROFILE.key}"]`)
  await expect(card).toContainText('Вся компания')
  await expect(card).toContainText('Операционные, финансовые')
  await expect(card).toContainText('Персонал — просмотр')
  await expect(page.getByTestId('profile-comparison')).toContainText(PROFILE.name)

  await card.getByRole('button', { name: 'Изменить' }).click()
  dialog = page.getByRole('dialog').filter({ hasText: `Профиль «${PROFILE.name}»` })
  await dialog.locator('li[data-dimension=drill_depth] select').selectOption('2')
  await dialog.getByTestId('profile-save').click()
  await expect(card).toContainText('2 уровня вниз')

  // Назначен пользователю — сервер не даёт удалить
  await openUserAccess(page)
  await page.getByTestId('access-profile').selectOption({ label: PROFILE.name })
  await page.getByTestId('user-save').click()
  await expect(page.getByText('Изменения сохранены')).toBeVisible()
  await page.goto('/admin/access-profiles')
  await expect(card).toContainText('1 пользователь')
  await card.getByRole('button', { name: `Удалить профиль «${PROFILE.name}»` }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Удалить' }).click()
  await expect(page.getByText(/назначен 1 пользователю/)).toBeVisible()

  // Вернуть пользователю «Сотрудник» и удалить профиль
  await openUserAccess(page)
  await page.getByTestId('access-profile').selectOption({ label: 'Сотрудник' })
  await page.getByTestId('user-save').click()
  await expect(page.getByText('Изменения сохранены')).toBeVisible()
  await page.goto('/admin/access-profiles')
  await card.getByRole('button', { name: `Удалить профиль «${PROFILE.name}»` }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Удалить' }).click()
  await expect(card).toHaveCount(0)
  expect(errors).toEqual([])
})

test('высшее руководство: без пунктов реестров, со сводками и выгрузкой', async ({ page }) => {
  const errors = collectErrors(page)
  await login(page, 'ceo')
  await expect(sidebar(page).getByTestId('sidebar-profile')).toHaveText('Высшее руководство')
  for (const label of ['Приёмы и увольнения', 'Реестр партнёрств', 'Хронология']) {
    await expect(sidebar(page).getByRole('link', { name: label })).toHaveCount(0)
  }
  await expect(sidebar(page).getByRole('link', { name: 'Сводка по периодам' })).toBeVisible()
  await page.goto('/hr/registry')
  await expect(page.getByRole('heading', { name: 'Нет доступа' })).toBeVisible()
  await expect(page.getByText('Раздел «Приёмы и увольнения» — исходные записи службы')).toBeVisible()
  await page.goto('/hr')
  await expect(page.getByRole('button', { name: 'PDF' })).toBeVisible()
  await page.goto('/profile')
  await expect(page.getByTestId('my-access')).toContainText('Исходные записи: Недоступны')
  expect(errors).toEqual([])
})

test('индивидуальная настройка (viewer) работает как в 0.1.0', async ({ page }) => {
  const errors = collectErrors(page)
  await login(page, 'viewer')
  for (const label of ['Приёмы и увольнения', 'Реестр партнёрств', 'Хронология', 'Недельный отчёт']) {
    await expect(sidebar(page).getByRole('link', { name: label })).toBeVisible()
  }
  await page.goto('/hr/registry')
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Приёмы и увольнения')
  await expect(page.getByRole('button', { name: 'Excel' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'PDF' })).toBeVisible()
  await page.goto('/tp/registry')
  await expect(page.getByRole('button', { name: 'CSV' })).toBeVisible()
  await page.goto('/tp/naumen')
  await expect(page.getByRole('heading', { name: 'Ответственные' })).toBeVisible()
  await expect(page.getByText('Ответственные скрыты')).toHaveCount(0)
  await page.goto('/profile')
  await expect(page.getByTestId('my-access')).toContainText('Профиль доступа: Индивидуальная настройка')
  await page.goto('/admin/users')
  await expect(page.getByRole('heading', { name: 'Нет доступа' })).toBeVisible()
  expect(errors).toEqual([])
})

test('вход по домену не настроен: состояние, проверка, переменные окружения', async ({ page }) => {
  const errors = collectErrors(page)
  await login(page, 'admin')
  await page.goto('/admin/integrations')
  await expect(page.getByTestId('ldap-status')).toContainText('Не настроен')
  await expect(page.getByTestId('ldap-status')).toContainText('Вход по домену не настроен')
  await page.getByRole('button', { name: 'Проверить подключение' }).click()
  await expect(page.getByTestId('ldap-result')).toContainText('Вход по домену не настроен')
  await expect(page.getByText('AUTH_LDAP_URL', { exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Импорт и экспорт структуры' })).toHaveAttribute('href', '/admin/org-transfer')
  // На странице входа подсказки о домене нет
  await page.context().clearCookies()
  await page.goto('/login')
  await expect(page.getByTestId('login-domain-hint')).toHaveCount(0)
  expect(errors).toEqual([])
})

test('статус и удаление: отключение с подтверждением, удаление с предложением отключить', async ({ page }) => {
  const errors = collectErrors(page)
  await login(page, 'admin')
  await page.goto(`/admin/users?search=${USER.username}`)
  await userRow(page).getByTestId('status-toggle').click()
  await page.getByRole('dialog').getByRole('button', { name: 'Отключить' }).click()
  await expect(userRow(page).getByTestId('status-toggle')).toHaveText('Отключён')
  await page.getByRole('button', { name: /отключено/ }).click()
  await expect(page).toHaveURL(/status=disabled/)
  await expect(userRow(page)).toBeVisible()

  await userRow(page).getByRole('button', { name: `Удалить: ${USER.full_name}` }).click()
  const dialog = page.getByRole('dialog').filter({ hasText: 'Удалить пользователя?' })
  await expect(dialog.getByRole('button', { name: 'Отключить' })).toHaveCount(0)
  await dialog.getByTestId('delete-confirm').click()
  await expect(userRow(page)).toHaveCount(0)
  expect(errors).toEqual([])
})

test('«Нет доступа» называет недоступную службу (сотрудник открывает дашборд персонала)', async ({ page }) => {
  await login(page, 'engineer')
  await page.goto('/hr')
  await expect(page.getByRole('heading', { name: 'Нет доступа' })).toBeVisible()
  await expect(page.getByText('«Служба персонала»')).toBeVisible()
  await expect(page.getByText('доступна только администратору')).toHaveCount(0)
})
