import { describe, expect, it } from 'vitest'
import {
  CLEARED_TEXT, cloneMatrix, detectRules, fileSize, filterPlanRows, folderState, folderTree, itemSummary, optionValues, optionsChanged, optionsPayload,
  planBlocked, planChips, planClears, planErrors, planHeads, planNewDepartments, planRows, rowAction, rulesChanges, rulesMatrix,
  scanText, sourceInfo, statusBadge, summaryText, workerState,
} from './inbox'

// Планы движков — в форме ответов /api/inbox/{id} (снято с работающего сервера 0.4.0)
const INDICATORS = {
  summary: { rows: 2, create: 0, update: 0, unchanged: 0, errors: 2 },
  rows: [
    { line: 2, department: 'NOPE', department_path: '', indicator: 'fin.revenue', indicator_name: 'Выручка', period: '2031-01', action: 'error', before: null, after: null, errors: ['Подразделение «NOPE» не найдено'] },
    { line: 3, department: 'COMM', department_path: 'АЛМИ Партнер / Коммерческая служба', indicator: 'nope', indicator_name: '', period: '2031-13', action: 'error', before: null, after: null, errors: ['Показатель не найден', 'Период — ГГГГ-ММ'] },
  ],
  can_apply: false,
}
const HR_MONTHS = {
  summary: { rows: 3, create: 3, update: 0, unchanged: 0, errors: 0, create_months: 2 },
  rows: [{ line: 2, month: '2031-01', month_label: 'Январь 2031', metric_key: 'total_employees', metric_label: 'Всего сотрудников', before: { value: 190, note: '' }, after: { value: 200, note: '' }, action: 'update', errors: [] }],
  can_apply: true,
}
const STRUCTURE = {
  summary: { departments: 14, create: 1, update: 0, unchanged: 13, settings: 0, add_heads: 0, existing_heads: 0, pending_heads: 7, missing_in_file: 0, errors: 0 },
  departments: [{ key: '8', path: 'АЛМИ Партнер', action: 'unchanged', changes: [] }, { key: 'new-1', path: 'АЛМИ Партнер / Отдел входящих', action: 'create', changes: [] }],
  heads: [{ path: 'АЛМИ Партнер', name: 'Громов', action: 'pending' }, { path: 'X', name: 'Y', action: 'exists' }],
  errors: [],
  can_apply: true,
}
const EMPLOYEES = {
  summary: { records: 1, create: 1, update: 0, unchanged: 0, skip: 0, conflicts: 0, unresolved: 0, errors: 0, create_departments: 1 },
  departments: [{ key: 'new:1', path: 'ИТ-служба', name: 'ИТ-служба', kind: 'department' }],
  records: [{ key: 'a@x.ru', line: 2, action: 'create', name: 'Входящий Сотрудник', email: 'a@x.ru', unresolved: false, changes: [{ field: 'position', label: 'Должность', old: '', new: 'Аналитик' }], conflicts: [], errors: [], warnings: [] }],
  can_apply: true,
}

// План значений показателей со строкой «очистить» (Пульс проекта: нет проектов в работе)
const CLEARING = {
  summary: { rows: 2, create: 0, update: 1, cleared: 1, unchanged: 0, errors: 0 },
  rows: [
    { line: 1, department: 'PROJ', department_path: 'АЛМИ Партнер / Проектная служба', indicator: 'puls.progress', indicator_name: 'Средний прогресс проектов', period: '2026-11', clear: true, action: 'clear', before: { value: 50, target: null, comment: 'из «Пульса проекта»' }, after: null, errors: [] },
    { line: 2, department: 'PROJ', department_path: 'АЛМИ Партнер / Проектная служба', indicator: 'puls.projects', indicator_name: 'Проекты в работе', period: '2026-11', clear: false, action: 'update', before: { value: 2, target: null, comment: '' }, after: { value: 0, target: null, comment: '' }, errors: [] },
  ],
  can_apply: true,
}

describe('строка «очистить» в плане значений', () => {
  it('действие «Очистить», «Станет» — значение удалится; видна среди изменений', () => {
    const rows = planRows(CLEARING)
    expect(rowAction(rows[0])).toEqual({ label: 'Очистить', tone: 'red' })
    expect(rows[0].before).toBe('50 · «из «Пульса проекта»»')
    expect(rows[0].after).toBe(CLEARED_TEXT)
    expect(rows[1].after).toBe('0')
    expect(filterPlanRows(rows, 'changes')).toHaveLength(2)
    expect(planClears(rows)).toBe(1)
  })
  it('сводка: «Очистится» чипом и строкой списка', () => {
    expect(planChips(CLEARING.summary).find((c) => c.label === 'Очистится')).toEqual({ label: 'Очистится', value: 1, tone: 'red' })
    expect(planChips({ ...CLEARING.summary, cleared: 0 }).some((c) => c.label === 'Очистится')).toBe(false)
    expect(summaryText(CLEARING.summary)).toBe('изменится 1 · очистится 1')
  })
})

describe('статусы и источники', () => {
  it('статус — подпись сервера и тон', () => {
    expect(statusBadge({ status: 'pending', status_label: 'Ожидает' })).toEqual({ label: 'Ожидает', tone: 'yellow' })
    expect(statusBadge({ status: 'applied' })).toEqual({ label: 'Применён', tone: 'green' })
    expect(statusBadge({ status: 'error' }).tone).toBe('red')
    expect(statusBadge({ status: 'duplicate' }).tone).toBe('gray')
    expect(planBlocked({ status: 'pending', plan_can_apply: false })).toBe(true)
    expect(planBlocked({ status: 'pending', plan_can_apply: true })).toBe(false)
  })

  it('источник: подключение и ключ — по названию, загрузка — кто загрузил, папка — путь', () => {
    expect(sourceInfo({ source: 'integration', integration: { id: 1, name: 'По Делу' }, source_label: 'Подключение' })).toEqual({ icon: 'plug', label: 'По Делу', detail: 'Подключение' })
    expect(sourceInfo({ source: 'api', inbound_key: { id: 2, name: '1С: ЗУП' } })).toMatchObject({ icon: 'key', label: 'Ключ «1С: ЗУП»' })
    expect(sourceInfo({ source: 'api', source_label: 'Приём по API' }).label).toBe('Приём по API')
    expect(sourceInfo({ source: 'upload', received_by: 'admin' })).toMatchObject({ icon: 'upload', label: 'admin' })
    expect(sourceInfo({ source: 'folder', source_ref: 'tp-weekly/отчёт.xlsx' })).toEqual({ icon: 'folder', label: 'Папка «Входящие»', detail: 'tp-weekly/отчёт.xlsx' })
  })

  it('размер файла', () => {
    expect(fileSize(512)).toBe('512 Б')
    expect(fileSize(12700)).toBe('12,4 КБ')
    expect(fileSize(3.2 * 1024 * 1024)).toBe('3,2 МБ')
  })
})

describe('сводка плана', () => {
  it('чипы: основные всегда, дополнительные — когда не ноль; тон — только у ненулевых', () => {
    expect(planChips(HR_MONTHS.summary)).toEqual([
      { label: 'Строк', value: 3, tone: 'gray' }, { label: 'Новых', value: 3, tone: 'green' },
      { label: 'Изменится', value: 0, tone: 'gray' }, { label: 'Без изменений', value: 0, tone: 'gray' },
      { label: 'Новых месяцев', value: 2, tone: 'green' }, { label: 'Ошибок', value: 0, tone: 'gray' },
    ])
    expect(planChips(STRUCTURE.summary).map((c) => c.label)).toEqual(['Подразделений в файле', 'Новых', 'Изменится', 'Без изменений', 'Руководителей нет в системе', 'Ошибок'])
    expect(planChips(INDICATORS.summary).at(-1)).toEqual({ label: 'Ошибок', value: 2, tone: 'red' })
    expect(planChips(null)).toEqual([])
  })

  it('строкой для списка', () => {
    expect(summaryText({ rows: 5, create: 3, update: 1, errors: 2 })).toBe('новых 3 · изменится 1 · ошибок 2')
    expect(summaryText({ rows: 5, unchanged: 5 })).toBe('без изменений 5')
    expect(summaryText({ rows: 1 })).toBe('1 строка, изменений нет')
    expect(itemSummary({ status: 'error', error: 'Файл не является JSON' })).toBe('Файл не является JSON')
    expect(itemSummary({ status: 'duplicate', duplicate_of: 12 })).toBe('Повтор элемента №12')
    expect(itemSummary({ status: 'received', message: 'Набор не распознан — выберите набор' })).toBe('Набор не распознан — выберите набор')
    expect(itemSummary({ status: 'pending', summary: { create: 2 } })).toBe('новых 2')
  })
})

describe('строки плана любого набора', () => {
  it('показатели: подразделение и период, ошибки', () => {
    const rows = planRows(INDICATORS)
    expect(rows[0]).toMatchObject({ line: 2, title: 'Выручка', subtitle: 'NOPE · 2031-01', action: 'error', errors: ['Подразделение «NOPE» не найдено'] })
    expect(rows[1]).toMatchObject({ title: 'nope', subtitle: 'Коммерческая служба · 2031-13' })
    expect(rowAction(rows[0])).toEqual({ label: 'Ошибка', tone: 'red' })
  })

  it('метрики месяца: было → стало', () => {
    expect(planRows(HR_MONTHS)[0]).toMatchObject({ title: 'Всего сотрудников', subtitle: 'Январь 2031', before: '190', after: '200', action: 'update' })
  })

  it('структура: строки — подразделения с действием; сотрудники: записи, изменения полями', () => {
    expect(planRows(STRUCTURE).map((r) => [r.title, r.action])).toEqual([['АЛМИ Партнер', 'unchanged'], ['Отдел входящих', 'create']])
    expect(planHeads(STRUCTURE)).toHaveLength(1)
    expect(planNewDepartments(STRUCTURE)).toEqual([])
    const [person] = planRows(EMPLOYEES)
    expect(person).toMatchObject({ title: 'Входящий Сотрудник', subtitle: 'a@x.ru', changes: ['Должность: Аналитик'] })
    expect(planNewDepartments(EMPLOYEES).map((d) => d.path)).toEqual(['ИТ-служба'])
  })

  it('недельный отчёт, Naumen, партнёрства, приёмы и увольнения', () => {
    expect(planRows({ rows: [{ period: '2031-W02', year: 2031, week: 2, action: 'update', changes: ['Заявок в работе'], errors: [] }] })[0])
      .toMatchObject({ title: '2031-W02', subtitle: 'Неделя 2, 2031', changes: ['Заявок в работе'] })
    expect(planRows({ rows: [{ number: 990001, registered_at: '2031-01-05T10:00:00', status: 'Закрыта', action: 'create', changes: [], errors: [] }] })[0])
      .toMatchObject({ title: '№ 990001', subtitle: 'Закрыта · 05.01.2031' })
    expect(planRows({ rows: [{ line: 2, partner: 'ООО Новый', product: 'Продукт X', action: 'create', changes: [], errors: [], warnings: [] }] })[0])
      .toMatchObject({ title: 'ООО Новый', subtitle: 'Продукт X' })
    expect(planRows({ rows: [{ line: 2, full_name: 'Тестов Тест', event_label: 'Приём', event_date: '2031-01-12', action: 'create', changes: [], errors: [] }] })[0])
      .toMatchObject({ title: 'Тестов Тест', subtitle: 'Приём · 12.01.2031' })
  })

  it('запись без решения — «Нужно решение»; фильтр: изменения и ошибки / ошибки / все', () => {
    const plan = { records: [
      { key: 'a', email: 'a@x', name: 'A', action: 'unchanged', changes: [], conflicts: [], errors: [], warnings: [] },
      { key: 'b', email: 'b@x', name: 'B', action: 'update', unresolved: true, changes: [], conflicts: [{ field: 'position' }], errors: [], warnings: [] },
      { key: 'c', email: 'c@x', name: 'C', action: 'create', changes: [], conflicts: [], errors: [], warnings: [] },
    ] }
    const rows = planRows(plan)
    expect(rowAction(rows[1])).toEqual({ label: 'Нужно решение', tone: 'red' })
    expect(filterPlanRows(rows, 'changes').map((r) => r.title)).toEqual(['B', 'C'])
    expect(filterPlanRows(rows, 'errors').map((r) => r.title)).toEqual(['B'])
    expect(filterPlanRows(rows, 'all')).toHaveLength(3)
  })

  it('ошибки плана списком — общие и по строкам, как на сервере', () => {
    expect(planErrors(INDICATORS)).toEqual(['строка 2: Подразделение «NOPE» не найдено', 'строка 3: Показатель не найден', 'строка 3: Период — ГГГГ-ММ'])
    expect(planErrors({ errors: ['Файл пустой'], records: [{ email: 'a@x', errors: ['Нет email'] }] })).toEqual(['Файл пустой', 'a@x: Нет email'])
    expect(planErrors(INDICATORS, 2)).toHaveLength(2)
    expect(planErrors(null)).toEqual([])
  })
})

describe('параметры набора', () => {
  const FIELDS = [{ key: 'mode', type: 'select', default: 'merge' }, { key: 'apply_settings', type: 'bool', default: false }]
  it('значения, изменения и тело запроса (служебные параметры сохраняются)', () => {
    expect(optionValues(FIELDS, { mode: 'replace' })).toEqual({ mode: 'replace', apply_settings: false })
    expect(optionsChanged(FIELDS, { mode: 'replace', apply_settings: false }, { mode: 'replace' })).toBe(false)
    expect(optionsChanged(FIELDS, { mode: 'merge', apply_settings: true }, { mode: 'merge' })).toBe(true)
    expect(optionsPayload([{ key: 'new_users', default: 'no_access' }], { new_users: 'inactive' }, { new_users: 'no_access', decisions: { a: 1 } }))
      .toEqual({ new_users: 'inactive', decisions: { a: 1 } })
  })
})

describe('правила «применять сразу»', () => {
  const RULES = [
    { source: 'folder', source_label: 'Папка «Входящие»', dataset: 'tp-weekly', dataset_label: 'Недельный отчёт', auto_apply: true },
    { source: 'api', source_label: 'Приём по API', dataset: 'tp-weekly', dataset_label: 'Недельный отчёт', auto_apply: false },
    { source: 'folder', source_label: 'Папка «Входящие»', dataset: 'naumen', dataset_label: 'Naumen', auto_apply: false },
    { source: 'api', source_label: 'Приём по API', dataset: 'naumen', dataset_label: 'Naumen', auto_apply: false },
  ]
  it('матрица: наборы × источники с правилами', () => {
    const m = rulesMatrix(RULES, { sources: [{ key: 'folder', label: 'Папка', has_rules: true }, { key: 'upload', label: 'Загрузка', has_rules: false }, { key: 'api', label: 'API', has_rules: true }] })
    expect(m.sources).toEqual([{ key: 'folder', label: 'Папка' }, { key: 'api', label: 'API' }])
    expect(m.rows).toEqual([
      { key: 'tp-weekly', label: 'Недельный отчёт', cells: { folder: true, api: false } },
      { key: 'naumen', label: 'Naumen', cells: { folder: false, api: false } },
    ])
    expect(rulesMatrix(RULES).sources.map((s) => s.label)).toEqual(['Папка «Входящие»', 'Приём по API'])
  })

  it('изменения для сохранения — только отличающиеся клетки', () => {
    const original = rulesMatrix(RULES)
    const draft = cloneMatrix(original)
    draft.rows[0].cells.folder = false
    draft.rows[1].cells.api = true
    expect(original.rows[0].cells.folder).toBe(true)
    expect(rulesChanges(original, draft)).toEqual([
      { source: 'folder', dataset: 'tp-weekly', auto_apply: false }, { source: 'api', dataset: 'naumen', auto_apply: true },
    ])
    expect(rulesChanges(original, cloneMatrix(original))).toEqual([])
  })
})

describe('папка и планировщик', () => {
  it('состояние папки', () => {
    expect(folderState({ enabled: false }).label).toBe('Не настроена')
    expect(folderState({ enabled: true, exists: false, path: '/data/inbox' })).toMatchObject({ tone: 'red', label: 'Не найдена' })
    expect(folderState({ enabled: true, exists: true, writable: false, path: '/x' }).tone).toBe('yellow')
    expect(folderState({ enabled: true, exists: true, writable: true, waiting_files: 3 })).toEqual({ tone: 'green', label: 'Работает', text: 'Ждут разбора: 3 файла' })
    expect(folderState({ enabled: true, exists: true, writable: true, waiting_files: 0 }).text).toBe('Новых файлов нет')
  })

  it('планировщик: нет отметки, свежая, давняя', () => {
    const now = new Date('2026-11-01T12:00:00Z')
    expect(workerState(null, now)).toMatchObject({ tone: 'yellow', label: 'Не запущен' })
    expect(workerState({ last_tick_at: '2026-11-01T11:59:40', tick_seconds: 30, host: 'worker-1', version: '0.4.0' }, now))
      .toMatchObject({ tone: 'green', label: 'Работает', text: 'Такт 30 с, последняя отметка только что — worker-1 · версия 0.4.0' })
    expect(workerState({ last_tick_at: '2026-11-01T11:50:00', tick_seconds: 30 }, now)).toMatchObject({ tone: 'red', label: 'Не отвечает' })
  })

  it('итог разбора и устройство папки', () => {
    expect(scanText({ taken: 2, applied: 1, pending: 1, waiting: 1 })).toBe('Взято файлов: 2, применено: 1, ожидают: 1, дописываются: 1')
    expect(scanText({ taken: 0 })).toBe('Взято файлов: 0')
    const tree = folderTree({ path: '/data/inbox', folders: [{ folder: 'tp-weekly', label: 'Недельный отчёт' }] })
    expect(tree.split('\n')[0]).toBe('/data/inbox/')
    expect(tree).toContain('tp-weekly/')
    expect(tree).toContain('Недельный отчёт')
    expect(tree.split('\n').at(-1)).toMatch(/^└── rejected\//)
  })
})

describe('распознавание в корне папки «Входящие»', () => {
  it('по содержимому; имя по шаблону только добавляет очки — числа с сервера', () => {
    const rules = detectRules({ threshold: 50, name_bonus: 20 })
    expect(rules.column).toBe('Шаблоны имени: +20 к оценке в корне')
    expect(rules.hint).toContain('распознаётся по содержимому')
    expect(rules.hint).toContain('имя по шаблону добавляет 20, нужно не меньше 50 — по одному имени файл не распознаётся')
    expect(rules.hint).not.toMatch(/по имени и содержимому/)
    expect(detectRules(null)).toMatchObject({ threshold: 50, bonus: 20 })
    expect(detectRules({ threshold: 60, name_bonus: 15 }).column).toContain('+15')
  })
})
