import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import SchemaForm from './SchemaForm.vue'
import IntegrationEditor from './IntegrationEditor.vue'
import OneTimeKey from './OneTimeKey.vue'
import ScheduleEditor from './ScheduleEditor.vue'
import IntegrationCard from './IntegrationCard.vue'
import KindPicker from './KindPicker.vue'
import CheckResult from './CheckResult.vue'
import RunsJournal from './RunsJournal.vue'
import CodeBlock from '@/components/ui/CodeBlock.vue'
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

describe('SchemaForm — «Тип подключения» не обрезается', () => {
  it('выбор с длинными подписями вариантов — на всю ширину формы; короткий — в половину', async () => {
    const kind = {
      kind: 'jira', fields: [
        { key: 'instance', label: 'Тип подключения', type: 'select', required: true, secret: false, default: 'server', options: [{ value: 'cloud', label: 'Cloud — email и API-токен' }, { value: 'server', label: 'Server / Data Center — персональный токен (PAT)' }] },
        { key: 'auth', label: 'Проверка подлинности', type: 'select', required: false, secret: false, default: 'ntlm', options: [{ value: 'ntlm', label: 'NTLM' }, { value: 'basic', label: 'Basic' }] },
      ],
    }
    const w = mount(SchemaForm, { props: { kind, values: { instance: 'server', auth: 'ntlm' }, secrets: {} } })
    // 2–4 длинных варианта — переключателями на всю ширину: подпись видна целиком и на телефоне
    const instance = w.find('[data-field=instance]')
    expect(instance.classes()).toContain('sf-choice')
    expect(instance.findAll('input[type=radio]')).toHaveLength(2)
    expect(instance.find('[data-testid=choice-instance-server]').element.checked).toBe(true)
    expect(instance.text()).toContain('Server / Data Center — персональный токен (PAT)')
    await instance.find('[data-testid=choice-instance-cloud]').setValue(true)
    expect(w.emitted('update:values').at(-1)[0].instance).toBe('cloud')
    expect(w.find('[data-field=auth] select').exists()).toBe(true)
    expect(w.find('[data-field=auth]').classes()).not.toContain('wide')
  })

  it('длинный список из многих вариантов — выпадающим списком на всю ширину', () => {
    const services = ['Служба персонала', 'Техническая поддержка', 'Проектный и продуктовый офис', 'Аппарат генерального директора', 'ИТ-служба']
    const kind = { kind: 'jira', fields: [{ key: 'owner', label: 'Служба', type: 'select', required: false, secret: false, default: 'it', options: services.map((label, n) => ({ value: String(n), label })) }] }
    const w = mount(SchemaForm, { props: { kind, values: { owner: '1' }, secrets: {} } })
    expect(w.find('[data-field=owner] select').exists()).toBe(true)
    expect(w.find('[data-field=owner]').classes()).toContain('wide')
  })
})

describe('SchemaForm — заполнитель по режиму (placeholder_if)', () => {
  it('«По Делу» по ключу: «пусто — все списки ключа»; служебная учётная запись — пример названия списка', async () => {
    const kind = { kind: 'podelu', fields: [
      { key: 'mode', label: 'Режим подключения', type: 'select', required: true, secret: false, default: 'key', options: [{ value: 'key', label: 'Ключ' }, { value: 'session', label: 'Учётная запись' }] },
      { key: 'data_list', label: 'Список задач с данными', type: 'string', required: false, secret: false, default: null, options: [], placeholder: 'Данные для дашбордов', placeholder_if: { mode: { key: 'пусто — все списки ключа' } } },
    ] }
    const w = mount(SchemaForm, { props: { kind, values: { mode: 'key', data_list: '' }, secrets: {} } })
    expect(w.find('[data-field=data_list] input').attributes('placeholder')).toBe('пусто — все списки ключа')
    await w.setProps({ values: { mode: 'session', data_list: '' } })
    expect(w.find('[data-field=data_list] input').attributes('placeholder')).toBe('Данные для дашбордов')
  })
})

describe('CheckResult — замечания и подписанные подробности', () => {
  const kind = {
    kind: 'puls', fields: [{ key: 'mode', type: 'select', options: [{ value: 'key', label: 'Ключ интеграции (Пульс 0.6.0 и новее)' }] }],
    detail_labels: { mode: 'Режим подключения', version: 'Версия', key: 'Ключ', scopes: 'Права', stats: 'Право «Показатели проектов»', directions: 'Направления', projects: 'Проектов', department: 'Подразделение' },
    technical_details: ['code', 'schema'],
  }
  const result = {
    ok: true, message: 'Подключено к «Пульс проекта» 0.6.0: проектов 9',
    warnings: ['у ключа нет права «Показатели проектов» (projects.stats)', 'сопоставление, строка 3 («7»): укажите «Разработка»'],
    details: { mode: 'key', version: '0.6.0', key: { name: 'Дашборды', scopes: ['projects.read'] }, stats: false, schema: '0021',
      directions: [{ id: 3, name: 'Внедрение', projects: 3, department: 'АЛМИ Партнер / Проектная служба' }] },
  }

  it('ok с замечаниями — жёлтый «Подключено с замечаниями», сообщение и замечания списком', () => {
    const w = mount(CheckResult, { props: { result, kind } })
    expect(w.classes()).toContain('warn')
    expect(w.find('.msg').text()).toBe('Подключено с замечаниями')
    expect(w.find('[data-testid=check-message]').text()).toBe(result.message)
    expect(w.findAll('[data-testid=check-warnings] li').map((li) => li.text())).toEqual([
      'У ключа нет права «Показатели проектов» (projects.stats)', 'Сопоставление, строка 3 («7»): укажите «Разработка»',
    ])
  })

  it('подробности — русскими подписями, служебные — в свёрнутых «Технических подробностях»', () => {
    const w = mount(CheckResult, { props: { result, kind } })
    const details = w.find('[data-testid=check-details]')
    expect(details.find('summary').text()).toBe('Подробности · 5')
    expect(details.text()).toContain('Режим подключенияКлюч интеграции (Пульс 0.6.0 и новее)')
    expect(details.text()).toContain('Дашборды · права: projects.read')
    expect(details.text()).toContain('Внедрение (3) · проектов: 3 · подразделение: АЛМИ Партнер / Проектная служба')
    expect(details.text()).not.toMatch(/\b(mode|stats|directions|schema)\b/)
    const technical = w.find('[data-testid=check-technical]')
    expect(technical.find('summary').text()).toBe('Технические подробности · 1')
    expect(technical.text()).toContain('schema')
  })

  it('без замечаний — зелёный с сообщением; ошибка — красная, код ошибки не показывается', () => {
    const ok = mount(CheckResult, { props: { result: { ok: true, message: 'Подключено', warnings: [], details: { version: '1.4.5' } }, kind } })
    expect(ok.classes()).toContain('ok')
    expect(ok.find('.msg').text()).toBe('Подключено')
    expect(ok.find('[data-testid=check-warnings]').exists()).toBe(false)
    expect(ok.find('[data-testid=check-details]').text()).toBe('Версия1.4.5')
    const bad = mount(CheckResult, { props: { result: { ok: false, message: 'Ключ отозван', details: { code: 'key_revoked' } }, kind } })
    expect(bad.classes()).toContain('bad')
    expect(bad.text()).not.toContain('key_revoked')
    expect(bad.find('[data-testid=check-technical]').exists()).toBe(false)
  })
})

describe('RunsJournal — сводка без повторов', () => {
  const RUNS = [
    { id: 2, action: 'indicators', trigger_label: 'Вручную', status: 'ok', status_label: 'Успешно', username: 'admin', started_at: '2026-11-02T05:55:00', finished_at: '2026-11-02T05:55:01',
      message: 'Показатели проектов за ноябрь 2026: значений новых 0, без изменений 20', error: '', summary: { values_unchanged: 20, projects: 9, structure_item: 4 } },
    { id: 1, action: 'indicators', trigger_label: 'Вручную', status: 'ok', status_label: 'Успешно', username: 'admin', started_at: '2026-11-02T05:54:00', finished_at: '2026-11-02T05:54:01',
      message: '', error: '', summary: { projects: 9 } },
  ]
  const kind = { kind: 'puls', actions: [{ key: 'indicators', label: 'Обновить показатели проектов' }], counter_labels: { values_unchanged: 'значений без изменений', projects: 'проектов' } }

  it('сообщение — в строке, счётчики — под «Подробности»; запуск без сообщения — счётчики сразу', async () => {
    const { integrationsApi } = await import('@/api/integrations')
    const runs = integrationsApi.runs
    integrationsApi.runs = async () => RUNS
    try {
      const w = mount(RunsJournal, {
        props: { integration: { id: 5, name: 'Пульс проекта' }, kind },
        global: { stubs: { SideDrawer: { template: '<div><slot name="header" /><slot /></div>' } } },
      })
      await new Promise((r) => setTimeout(r))
      await w.vm.$nextTick()
      const rows = w.findAll('[data-testid=runs-table] tbody tr')
      expect(rows).toHaveLength(2)
      expect(rows[0].find('[data-testid=run-message]').text()).toBe(RUNS[0].message)
      const more = rows[0].find('[data-testid=run-more]')
      expect(more.element.tagName).toBe('DETAILS')
      expect(more.find('summary').text()).toBe('Подробности · 2')
      expect(more.find('[data-testid=run-counters]').text()).toContain('значений без изменений: 20')
      expect(rows[0].find('td.sum > [data-testid=run-counters]').exists()).toBe(false)
      expect(rows[1].find('[data-testid=run-more]').exists()).toBe(false)
      expect(rows[1].find('[data-testid=run-counters]').text()).toBe('проектов: 9')
    } finally {
      integrationsApi.runs = runs
    }
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

describe('IntegrationEditor — секреты привязаны к адресам (secret_url_fields)', () => {
  const PODELU = {
    kind: 'podelu', title: 'По Делу', url_field: 'base_url', secret_url_fields: ['base_url', 'server_url'], actions: [],
    fields: [
      { key: 'base_url', label: 'Адрес «По Делу»', type: 'url', required: true, secret: false, default: null, options: [] },
      { key: 'server_url', label: 'Адрес для запросов сервера', type: 'url', required: false, secret: false, default: null, options: [] },
      { key: 'login', label: 'Служебная учётная запись', type: 'string', required: true, secret: false, default: null, options: [] },
      { key: 'password', label: 'Пароль', type: 'password', required: true, secret: true, default: null, options: [] },
    ],
  }
  const INTEGRATION = {
    id: 3, name: 'По Делу', kind: 'podelu', has_secret: true, secret_fields: ['password'], secret_bound_url: 'https://podelu.ru',
    secret_problem: null, config: { base_url: 'https://podelu.ru', server_url: null, login: 'svc' }, schedule: {},
  }
  const mountEditor = () => mount(IntegrationEditor, {
    props: { kind: PODELU, integration: INTEGRATION },
    global: { stubs: { SideDrawer: { template: '<div><slot name="header" /><slot /><slot name="footer" /></div>' }, ScheduleEditor: true } },
  })

  it('изменён адрес для запросов сервера — предупреждение до сохранения, пароль вводится заново', async () => {
    const w = mountEditor()
    expect(w.find('[data-testid=editor-rebind]').exists()).toBe(false)
    expect(w.find('[data-testid=secret-set-password]').exists()).toBe(true)
    await w.find('[data-field=login] input').setValue('другой')
    expect(w.find('[data-testid=editor-rebind]').exists()).toBe(false)
    await w.find('[data-field=server_url] input').setValue('http://10.0.0.5:5000')
    const banner = w.find('[data-testid=editor-rebind]')
    expect(banner.text()).toContain('Изменено: «Адрес для запросов сервера»')
    expect(banner.text()).toContain('«Пароль»')
    expect(w.find('[data-field=password]').text()).toContain('Адрес изменён')
    await w.find('[data-field=server_url] input').setValue('')
    expect(w.find('[data-testid=editor-rebind]').exists()).toBe(false)
  })
})

describe('OneTimeKey — частота вызовов с сервера', () => {
  it('rate_limit ключа вместо числа в коде', () => {
    const w = mount(OneTimeKey, {
      props: { item: { name: '1С', key: 'dash_x', scope_labels: ['Приём файлов'], rate_limit: 300 } },
      global: { stubs: { AppModal: { template: '<div><slot /><slot name="footer" /></div>' } } },
    })
    expect(w.text()).toContain('не больше 300 запросов в минуту на ключ')
    expect(w.text()).not.toContain('120')
  })
})

const SCHED_KIND = {
  kind: 'podelu', title: 'По Делу',
  actions: [
    { key: 'sync', label: 'Синхронизировать структуру', schedulable: true },
    { key: 'pull', label: 'Забрать данные из задач', schedulable: true },
    { key: 'check', label: 'Только вручную', schedulable: false },
  ],
  counter_labels: { tasks: 'задач в списке', values: 'значений' },
}

describe('ScheduleEditor — несколько расписаний', () => {
  const mountEditor = (modelValue, errors = {}) => mount(ScheduleEditor, { props: { modelValue, kind: SCHED_KIND, errors } })

  it('нет записей — только вручную; «Добавить расписание» добавляет запись со свободным действием', async () => {
    const w = mountEditor([])
    expect(w.find('[data-testid=schedule-empty]').exists()).toBe(true)
    expect(w.find('[data-testid=schedule-preview]').text()).toContain('Вручную')
    await w.find('[data-testid=schedule-add]').trigger('click')
    const [first] = w.emitted('update:modelValue')[0][0]
    expect(first).toMatchObject({ mode: 'interval', minutes: '60', actions: ['sync'] })
    await w.setProps({ modelValue: [first] })
    await w.find('[data-testid=schedule-add]').trigger('click')
    expect(w.emitted('update:modelValue')[1][0][1].actions).toEqual(['pull'])
  })

  it('две записи — у каждой свои поля и действия; подпись — все записи; удалить — одну', async () => {
    const entries = [
      { mode: 'daily', minutes: '60', time: '06:00', weekdays: [], actions: ['sync'] },
      { mode: 'interval', minutes: '30', time: '06:00', weekdays: [], actions: ['pull'] },
    ]
    const w = mountEditor(entries, { 'schedule.1.minutes': 'Целое число минут' })
    const blocks = w.findAll('[data-testid=schedule-entry]')
    expect(blocks).toHaveLength(2)
    expect(blocks[0].find('[data-testid=schedule-time]').exists()).toBe(true)
    expect(blocks[1].find('[data-testid=schedule-minutes]').element.value).toBe('30')
    expect(blocks[1].text()).toContain('Целое число минут')
    expect(blocks[0].text()).not.toContain('Целое число минут')
    expect(w.find('[data-testid=schedule-preview]').text()).toContain('В 06:00 ежедневно — Синхронизировать структуру; Каждые 30 мин — Забрать данные из задач')
    expect(blocks[0].find('[data-action=check]').exists()).toBe(false)
    await blocks[1].find('[data-action=sync] input').trigger('change')
    expect(w.emitted('update:modelValue')[0][0][1].actions).toEqual(['pull', 'sync'])
    await blocks[0].find('[data-testid=schedule-remove]').trigger('click')
    expect(w.emitted('update:modelValue')[1][0]).toEqual([entries[1]])
  })

  it('не больше 5 записей', () => {
    const entry = { mode: 'interval', minutes: '60', time: '06:00', weekdays: [], actions: ['sync'] }
    const w = mountEditor(Array.from({ length: 5 }, () => entry))
    expect(w.find('[data-testid=schedule-add]').attributes('disabled')).toBeDefined()
    expect(w.text()).toContain('Не больше 5 расписаний у подключения')
  })
})

describe('IntegrationCard — расписания, ошибка, только для чтения', () => {
  const BASE = {
    id: 7, kind: 'podelu', name: 'По Делу', enabled: true, health: 'ok', can_manage: true, running: false, verified_at: '2026-11-01T09:00:00',
    schedule: [
      { mode: 'daily', time: '06:00', weekdays: [], actions: ['sync'], label: 'В 06:00 ежедневно', next_run_at: '2026-11-03T03:00:00' },
      { mode: 'interval', minutes: 30, actions: ['pull'], label: 'Каждые 30 мин', next_run_at: '2026-11-02T10:30:00' },
    ],
    schedule_label: 'В 06:00 ежедневно — Синхронизировать структуру; Каждые 30 мин — Забрать данные из задач', next_run_at: '2026-11-02T10:30:00',
    last_error: 'Старая ошибка', last_error_at: '2026-11-01T08:00:00', last_ok_at: '2026-11-01T09:00:00', current_error: '',
    last_run: { id: 1, action: 'pull', status: 'ok', status_label: 'Успешно', started_at: '2026-11-01T09:00:00', trigger_label: 'По расписанию', summary: { tasks: 4, structure_item: 12 } },
  }
  const card = (patch = {}, kind = SCHED_KIND) => mount(IntegrationCard, {
    props: { integration: { ...BASE, ...patch }, kind },
    global: { stubs: { TransferBanner: { props: ['title', 'text'], template: '<div class="banner">{{ title }} {{ text }}<slot /><slot name="actions" /></div>' } } },
  })

  it('все записи расписания со своим следующим запуском и действиями', () => {
    const w = card()
    const items = w.findAll('[data-testid=integration-schedule-entry]')
    expect(items).toHaveLength(2)
    expect(items[0].text()).toContain('В 06:00 ежедневно')
    expect(items[0].text()).toContain('Синхронизировать структуру')
    expect(items[1].text()).toContain('Забрать данные из задач')
    expect(items[1].text()).toContain('следующий')
    expect(w.find('[data-action=sync]').text()).toContain('по расписанию')
    expect(w.find('[data-action=pull]').text()).toContain('по расписанию')
  })

  it('старая ошибка при «Работает» не показывается; новая — показывается', () => {
    expect(card().find('[data-testid=integration-error]').exists()).toBe(false)
    expect(card({ current_error: 'Нет связи', health: 'error' }).find('[data-testid=integration-error]').text()).toBe('Нет связи')
  })

  it('счётчики последнего запуска — подписями вида, служебные числа не показываются', () => {
    const text = card().text()
    expect(text).toContain('задач в списке: 4')
    expect(text).not.toContain('structure')
  })

  it('прерванный запуск: «Запуск прерван», запустить снова можно', () => {
    const w = card({ last_run: { ...BASE.last_run, status: 'interrupted', status_label: 'Запуск прерван' } })
    expect(w.text()).toContain('Запуск прерван')
    expect(w.find('[data-testid=run-interrupted]').exists()).toBe(true)
    expect(w.find('[data-testid=run-pull]').attributes('disabled')).toBeUndefined()
  })

  it('вид «только администратор»: карточка только для чтения с пояснением', () => {
    const kind = { ...SCHED_KIND, kind: 'confluence', admin_only: true, admin_only_note: 'Только администратор: публикует полный сквозной отчёт' }
    const w = card({ kind: 'confluence', can_manage: false }, kind)
    expect(w.find('[data-testid=integration-read-only]').text()).toContain('Только администратор: публикует полный сквозной отчёт')
    for (const id of ['integration-check', 'integration-edit', 'integration-delete', 'run-pull', 'run-sync']) expect(w.find(`[data-testid=${id}]`).exists()).toBe(false)
    expect(w.find('[data-testid=integration-journal]').exists()).toBe(true)
    expect(w.find('[data-testid=integration-enabled] input').attributes('disabled')).toBeDefined()
  })
})

describe('KindPicker — порядок и «только администратор»', () => {
  const KINDS = [
    { kind: 'podelu', title: 'По Делу', description: '', actions: [] },
    { kind: 'confluence', title: 'Confluence', description: '', actions: [], admin_only: true, admin_only_note: 'Только администратор: публикует полный сквозной отчёт' },
  ]
  const picker = (isAdmin) => mount(KindPicker, {
    props: { kinds: KINDS, integrations: [], isAdmin },
    global: { stubs: { AppModal: { template: '<div><slot /></div>' } } },
  })

  it('виды — в порядке сервера; Confluence не администратору недоступен, с пояснением', () => {
    const w = picker(false)
    expect(w.findAll('button.kind').map((b) => b.attributes('data-kind'))).toEqual(['podelu', 'confluence'])
    const confluence = w.find('[data-testid=kind-confluence]')
    expect(confluence.attributes('disabled')).toBeDefined()
    expect(confluence.text()).toContain('Только администратор: публикует полный сквозной отчёт')
    expect(picker(true).find('[data-testid=kind-confluence]').attributes('disabled')).toBeUndefined()
  })
})

describe('CodeBlock — «Копировать» не закрывает код', () => {
  it('кнопка — в своей строке над кодом, не внутри блока кода', () => {
    const w = mount(CodeBlock, { props: { code: 'curl -X POST "https://dashboards.company.ru/api/inbound/v1/files" -H "Authorization: Bearer dash_…"', label: 'curl' } })
    const bar = w.find('.bar')
    expect(bar.find('button.copy').text()).toContain('Копировать')
    expect(bar.find('figcaption').text()).toBe('curl')
    expect(w.find('pre').find('button').exists()).toBe(false)
    expect(w.find('pre').element.previousElementSibling).toBe(bar.element)
  })
})
