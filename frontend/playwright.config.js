import { defineConfig, devices } from '@playwright/test'

/** E2E: сервер с демо-данными должен работать на E2E_BASE_URL (см. .github/workflows/e2e.yml). */
export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: process.env.E2E_BASE_URL || 'http://127.0.0.1:8000',
    locale: 'ru-RU',
    timezoneId: 'Europe/Moscow',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'chromium', testIgnore: /mobile\.spec\.js/, use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } } },
    // Мобильная вёрстка обширна (100+ @media) — охраняется отдельным набором: инвариант «нет
    // горизонтальной прокрутки» на ключевых маршрутах + шторка навигации (аудит 2026-11-20, D3)
    { name: 'mobile-chromium', use: { ...devices['Pixel 7'] }, testMatch: /mobile\.spec\.js/ },
  ],
})
