import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import SchemaForm from './SchemaForm.vue'
import RichText from '@/components/ui/RichText.vue'

const KIND = {
  kind: 'jira',
  url_field: 'base_url',
  allowed_hosts_env: 'JIRA_ALLOWED_HOSTS',
  fields: [
    { key: 'base_url', label: 'Адрес', type: 'url', required: true, secret: false, default: null, options: [] },
    { key: 'instance', label: 'Тип', type: 'select', required: true, secret: false, default: 'cloud', options: [{ value: 'cloud', label: 'Cloud' }, { value: 'server', label: 'Server' }] },
    { key: 'login', label: 'Email', type: 'string', required: true, secret: false, default: null, options: [], show_if: { instance: ['cloud'] } },
    { key: 'token', label: 'Токен', type: 'password', required: true, secret: true, default: null, options: [] },
    { key: 'rules', label: 'Правила', type: 'json', required: true, secret: false, default: null, options: [], hint: 'Список JSON' },
  ],
}

function form(values, secrets = {}, extra = {}) {
  return mount(SchemaForm, { props: { kind: KIND, values, secrets, ...extra } })
}

describe('SchemaForm — форма по описанию полей', () => {
  it('show_if: поле видно только при нужном значении другого поля', async () => {
    const w = form({ base_url: '', instance: 'cloud', login: '', rules: '' })
    expect(w.find('[data-field=login]').exists()).toBe(true)
    await w.setProps({ values: { base_url: '', instance: 'server', login: '', rules: '' } })
    expect(w.find('[data-field=login]').exists()).toBe(false)
  })

  it('подсказка о разрешённых узлах под адресом', () => {
    expect(form({ instance: 'cloud' }).find('[data-field=base_url]').text()).toContain('JIRA_ALLOWED_HOSTS')
  })

  it('сохранённый секрет — «задан» с «Заменить»; заменить — поле ввода', async () => {
    const w = form({ instance: 'cloud' }, { token: { mode: 'keep', value: '' } }, { saved: ['token'] })
    expect(w.find('[data-testid=secret-set-token]').text()).toContain('задан')
    await w.find('[data-field=token] button').trigger('click')
    expect(w.emitted('update:secrets')[0][0]).toEqual({ token: { mode: 'replace', value: '' } })
    const rebind = form({ instance: 'cloud' }, { token: { mode: 'replace', value: '' } }, { saved: ['token'], rebind: true })
    expect(rebind.find('[data-field=token]').text()).toContain('Адрес изменён')
  })

  it('JSON — моноширинное поле 10–16 строк; ошибка разбора видна сразу', async () => {
    const pretty = JSON.stringify([{ indicator: 'jira.open' }], null, 2)
    const w = form({ instance: 'server', rules: pretty })
    const area = w.find('[data-field=rules] textarea')
    expect(area.classes()).toContain('mono')
    expect(Number(area.attributes('rows'))).toBeGreaterThanOrEqual(10)
    expect(w.find('[data-field=rules]').text()).toContain('JSON без ошибок')
    await w.setProps({ values: { instance: 'server', rules: '[{"a": 1,}]' } })
    expect(w.find('[data-field=rules] .error').text()).toMatch(/^Ошибка JSON: /)
    await area.setValue('[]')
    expect(w.emitted('update:values').at(-1)[0].rules).toBe('[]')
  })
})

describe('RichText — длинные описания', () => {
  const TEXT = 'Выгрузка из 1С по ключу.\n\nПример:\n```1c\nФункция Ф()\n    Возврат 1;\nКонецФункции\n```'

  it('свёрнуто — первый абзац и «Подробнее»; развёрнуто — код моноширинным блоком', async () => {
    const w = mount(RichText, { props: { text: TEXT } })
    expect(w.text()).toContain('Выгрузка из 1С по ключу.')
    expect(w.find('pre').exists()).toBe(false)
    const more = w.find('button.more')
    expect(more.attributes('aria-expanded')).toBe('false')
    await more.trigger('click')
    expect(w.find('pre code').text()).toContain('Возврат 1;')
    expect(w.find('button.more').text()).toBe('Свернуть')
  })

  it('короткий текст — без «Подробнее», переносы строк сохраняются', () => {
    const w = mount(RichText, { props: { text: 'Строка один\nстрока два' } })
    expect(w.find('button.more').exists()).toBe(false)
    expect(w.find('.txt').text()).toBe('Строка один\nстрока два')
  })
})
