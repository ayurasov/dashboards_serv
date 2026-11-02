import { afterEach, describe, expect, it, vi } from 'vitest'

const toastError = vi.fn()
vi.mock('@/composables/useToast', () => ({ toastError: (...args) => toastError(...args) }))

const { inboxApi, ruleList } = await import('./inbox')
const { integrationsApi } = await import('./integrations')

/** Ответ сервера по очереди; запросы — в calls. */
function replies(...list) {
  const calls = []
  globalThis.fetch = vi.fn(async (url, init) => {
    calls.push({ url, init })
    const [status, body] = list.shift()
    return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
  })
  return calls
}

const ITEM = { id: 7, status: 'pending', plan: { summary: { errors: 1 }, can_apply: false } }

describe('входящие: применение', () => {
  afterEach(() => toastError.mockReset())

  it('успех — элемент; параметры передаются в теле', async () => {
    const calls = replies([200, { ...ITEM, status: 'applied' }])
    const result = await inboxApi.apply(7, { mode: 'replace' })
    expect(result).toEqual({ item: { ...ITEM, status: 'applied' }, rejected: false, detail: '' })
    expect(calls[0].url).toBe('/api/inbox/7/apply')
    expect(JSON.parse(calls[0].init.body)).toEqual({ options: { mode: 'replace' } })
  })

  it('409 import_has_errors — не ошибка: свежий план элемента, без всплывающего сообщения', async () => {
    replies([409, { detail: 'В плане ошибки: 1', code: 'import_has_errors', item: ITEM }])
    const result = await inboxApi.apply(7)
    expect(result).toEqual({ item: ITEM, rejected: true, detail: 'В плане ошибки: 1' })
    expect(toastError).not.toHaveBeenCalled()
  })

  it('прочие ошибки — исключение и сообщение', async () => {
    replies([409, { detail: 'Элемент в статусе «Применён» — применять нечего', code: 'wrong_status' }])
    await expect(inboxApi.apply(7)).rejects.toMatchObject({ status: 409, code: 'wrong_status' })
    expect(toastError).toHaveBeenCalledWith('Элемент в статусе «Применён» — применять нечего')
  })
})

describe('входящие: загрузка, повтор, правила, список', () => {
  afterEach(() => toastError.mockReset())

  it('загрузка — multipart с набором, признаком применения и параметрами JSON; ошибки файла — без сообщения', async () => {
    const calls = replies([201, ITEM], [403, { detail: 'Файл распознан как «Сотрудники» — этот набор вам недоступен', code: 'dataset_forbidden' }])
    const file = new File(['a;b'], 'x.csv', { type: 'text/csv' })
    await inboxApi.upload({ file, dataset: 'tp-weekly', apply: true, options: { mode: 'replace' } })
    const form = calls[0].init.body
    expect(form.get('file').name).toBe('x.csv')
    expect(form.get('dataset')).toBe('tp-weekly')
    expect(form.get('apply')).toBe('true')
    expect(JSON.parse(form.get('options'))).toEqual({ mode: 'replace' })
    expect(calls[0].init.headers['Content-Type']).toBeUndefined()
    await expect(inboxApi.upload({ file })).rejects.toMatchObject({ status: 403, code: 'dataset_forbidden' })
    expect(calls[1].init.body.get('dataset')).toBe('')
    expect(calls[1].init.body.get('options')).toBeNull()
    expect(toastError).not.toHaveBeenCalled()
  })

  it('повтор с другим набором и отклонение с причиной', async () => {
    const calls = replies([200, ITEM], [200, ITEM])
    await inboxApi.retry(7, { dataset: 'naumen' })
    expect(JSON.parse(calls[0].init.body)).toEqual({ dataset: 'naumen', options: null, apply: false })
    await inboxApi.reject(7, 'не тот месяц')
    expect(calls[1].url).toBe('/api/inbox/7/reject')
    expect(JSON.parse(calls[1].init.body)).toEqual({ reason: 'не тот месяц' })
  })

  it('правила — списком (и в обёртке { rules }); сохраняются только переданные', async () => {
    const rule = { source: 'folder', dataset: 'tp-weekly', auto_apply: true }
    const calls = replies([200, [rule]], [200, { rules: [rule] }])
    expect(await inboxApi.rules()).toEqual([rule])
    expect(await inboxApi.saveRules([rule])).toEqual([rule])
    expect(calls[1].init.method).toBe('PUT')
    expect(JSON.parse(calls[1].init.body)).toEqual({ rules: [rule] })
    expect(ruleList(null)).toEqual([])
  })

  it('список: несколько статусов через запятую, пустые фильтры не передаются', async () => {
    const calls = replies([200, { items: [], total: 0, counts: {} }])
    await inboxApi.list({ status: ['pending', 'error'], dataset: '', source: 'api', q: '', page: 2, page_size: 50 })
    expect(calls[0].url).toBe('/api/inbox?status=pending%2Cerror&source=api&page=2&page_size=50')
  })
})

describe('интеграции: ошибки, которые экран показывает сам', () => {
  afterEach(() => toastError.mockReset())

  it('check_required и secret_rebind_required — без всплывающего сообщения, с кодом и телом', async () => {
    replies([409, { detail: 'Сначала проверьте подключение', code: 'check_required' }],
      [422, { detail: 'Адрес изменён — введите токен заново', code: 'secret_rebind_required', fields: { secrets: 'Введите заново' } }])
    await expect(integrationsApi.update(3, { enabled: true })).rejects.toMatchObject({ status: 409, code: 'check_required', body: { code: 'check_required' } })
    await expect(integrationsApi.update(3, { config: {} })).rejects.toMatchObject({ code: 'secret_rebind_required', fields: { secrets: 'Введите заново' } })
    expect(toastError).not.toHaveBeenCalled()
  })

  it('запуск действия и журнал; ключи', async () => {
    const calls = replies([200, { id: 1, status: 'ok' }], [200, []], [201, { id: 4, key: 'dash_x' }], [200, { id: 4 }])
    await integrationsApi.run(3, 'scan')
    expect(JSON.parse(calls[0].init.body)).toEqual({ action: 'scan' })
    await integrationsApi.runs(3, 20)
    expect(calls[1].url).toBe('/api/integrations/3/runs?limit=20')
    expect((await integrationsApi.issueKey({ name: '1С', scopes: ['files'] })).key).toBe('dash_x')
    await integrationsApi.revokeKey(4)
    expect(calls[3].url).toBe('/api/integrations/keys/4/revoke')
    expect(calls[3].init.headers['X-CSRF-Token']).toBeDefined()
  })
})
