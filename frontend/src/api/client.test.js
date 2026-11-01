import { afterEach, describe, expect, it, vi } from 'vitest'

const toastError = vi.fn()
vi.mock('@/composables/useToast', () => ({ toastError: (...args) => toastError(...args) }))

const { request } = await import('./client')

function reply(status, body) {
  globalThis.fetch = vi.fn(async () => new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } }))
}

describe('ошибки запросов', () => {
  afterEach(() => toastError.mockReset())

  it('ошибки полей формы (422 и 409 с fields) не дублируются всплывающим сообщением', async () => {
    reply(409, { detail: 'Неделя 2026-W31 уже есть в отчёте', code: 'conflict', fields: { week: 'Неделя уже заполнена' } })
    await expect(request('POST', '/tp/reports', { body: {} })).rejects.toMatchObject({ status: 409, fields: { week: 'Неделя уже заполнена' } })
    reply(422, { detail: 'Проверьте поля', fields: { name: 'Обязательно' } })
    await expect(request('PUT', '/x', { body: {} })).rejects.toMatchObject({ status: 422 })
    expect(toastError).not.toHaveBeenCalled()
  })

  it('прочие ошибки показываются всплывающим сообщением', async () => {
    reply(409, { detail: 'Месяц уже есть' })
    await expect(request('POST', '/hr/months', { body: {} })).rejects.toMatchObject({ status: 409 })
    reply(500, {})
    await expect(request('GET', '/hr/analytics/dashboard')).rejects.toMatchObject({ message: 'Ошибка сервера. Попробуйте позже' })
    expect(toastError).toHaveBeenCalledTimes(2)
    expect(toastError).toHaveBeenCalledWith('Месяц уже есть')
  })
})
