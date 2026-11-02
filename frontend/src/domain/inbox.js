/**
 * Входящие данные (ADR-0011): статусы и их тона, подписи источника, сводка и строки плана любого
 * набора (у движков служб разные поля — здесь они сводятся к одному виду), ошибки плана, параметры
 * набора, матрица правил «применять сразу», состояние папки и планировщика. Вход — ответы
 * /api/inbox/* (поля как в API). Чистые функции — покрыты тестами (inbox.test.js).
 */
import { formatDateTime, formatNumber, formatRelative, monthLabel, plural } from '@/utils/format'

// ---------------------------------------------------------------- статусы и источники

/** Порядок статусов в чипах — сначала то, что требует внимания. */
export const STATUS_ORDER = ['pending', 'error', 'received', 'recognized', 'applied', 'rejected', 'duplicate']
export const STATUS_LABELS = {
  received: 'Получен', recognized: 'Распознан', pending: 'Ожидает', applied: 'Применён',
  rejected: 'Отклонён', error: 'Ошибка', duplicate: 'Повтор',
}
export const STATUS_TONES = {
  received: 'yellow', recognized: 'blue', pending: 'yellow', applied: 'green', rejected: 'gray', error: 'red', duplicate: 'gray',
}
/** Подсказки к статусам — для чипов фильтра. */
export const STATUS_HINTS = {
  received: 'Набор не распознан — выберите набор и повторите',
  recognized: 'Набор распознан, план строится',
  pending: 'План готов и ждёт подтверждения',
  applied: 'Данные записаны в систему',
  rejected: 'Отклонён вручную — данные не записаны',
  error: 'Файл не прочитан или план не построен',
  duplicate: 'Этот файл уже получали — повторно не применяется',
}

export function statusBadge(item) {
  const status = item?.status
  return { label: item?.status_label || STATUS_LABELS[status] || status || '—', tone: STATUS_TONES[status] || 'gray' }
}

/** В плане ожидающего элемента ошибки — применить нельзя, нужно исправить файл или отклонить. */
export const planBlocked = (item) => item?.status === 'pending' && item.plan_can_apply === false

export const SOURCE_LABELS = {
  folder: 'Папка «Входящие»', upload: 'Загрузка в интерфейсе', api: 'Приём по API', integration: 'Подключение',
}
export const SOURCE_SHORT = { folder: 'Папка', upload: 'Загрузка', api: 'API', integration: 'Подключение' }
export const SOURCE_ICONS = { folder: 'folder', upload: 'upload', api: 'key', integration: 'plug' }

/**
 * Источник элемента для списка: название подключения или ключа, кто загрузил, путь в папке.
 * { icon, label, detail }.
 */
export function sourceInfo(item) {
  const source = item?.source
  const icon = SOURCE_ICONS[source] || 'file'
  if (source === 'integration') {
    return { icon, label: item.integration?.name || item.source_label || SOURCE_LABELS.integration, detail: 'Подключение' }
  }
  if (source === 'api') {
    return { icon, label: item.inbound_key?.name ? `Ключ «${item.inbound_key.name}»` : item.source_label || SOURCE_LABELS.api, detail: 'Приём по API' }
  }
  if (source === 'upload') return { icon, label: item.received_by || 'Загрузка', detail: 'Загрузка в интерфейсе' }
  if (source === 'folder') return { icon, label: SOURCE_LABELS.folder, detail: item.source_ref || '' }
  return { icon, label: item?.source_label || source || '—', detail: '' }
}

/** Размер файла: «512 Б», «12,4 КБ», «3,1 МБ». */
export function fileSize(bytes) {
  const n = Number(bytes) || 0
  if (n < 1024) return `${n} Б`
  if (n < 1024 * 1024) return `${(n / 1024).toLocaleString('ru-RU', { maximumFractionDigits: 1 })} КБ`
  return `${(n / 1024 / 1024).toLocaleString('ru-RU', { maximumFractionDigits: 1 })} МБ`
}

// ---------------------------------------------------------------- сводка плана

// Ключи сводок движков: основные показываются всегда, остальные — когда не ноль
const SUMMARY_KEYS = [
  { key: 'rows', label: 'Строк', base: true },
  { key: 'records', label: 'Записей', base: true },
  { key: 'departments', label: 'Подразделений в файле', base: true },
  { key: 'create', label: 'Новых', tone: 'green', base: true },
  { key: 'update', label: 'Изменится', tone: 'blue', base: true },
  { key: 'unchanged', label: 'Без изменений', base: true },
  { key: 'delete', label: 'Удалится', tone: 'red' },
  { key: 'cleared', label: 'Очистится', tone: 'red' },
  { key: 'create_months', label: 'Новых месяцев', tone: 'green' },
  { key: 'hired', label: 'Приёмов' },
  { key: 'fired', label: 'Увольнений' },
  { key: 'create_departments', label: 'Новых подразделений', tone: 'green' },
  { key: 'settings', label: 'Настроек изменится', tone: 'blue' },
  { key: 'add_heads', label: 'Назначить руководителей', tone: 'green' },
  { key: 'existing_heads', label: 'Руководители уже назначены' },
  { key: 'pending_heads', label: 'Руководителей нет в системе', tone: 'yellow' },
  { key: 'missing_in_file', label: 'Нет в файле' },
  { key: 'skip', label: 'Пропущено' },
  { key: 'skipped', label: 'Пропущено строк' },
  { key: 'conflicts', label: 'Различий', tone: 'yellow' },
  { key: 'unresolved', label: 'Нужно решение', tone: 'red' },
  { key: 'warnings', label: 'Предупреждений', tone: 'yellow' },
  { key: 'errors', label: 'Ошибок', tone: 'red', base: true },
]

/** Сводка плана чипами — как в «Импорт и экспорт»: новые — зелёным, изменения — синим, ошибки — красным. */
export function planChips(summary) {
  if (!summary || typeof summary !== 'object') return []
  const out = []
  for (const s of SUMMARY_KEYS) {
    const value = summary[s.key]
    if (typeof value !== 'number') continue
    if (!s.base && !value) continue
    out.push({ label: s.label, value, tone: value ? s.tone || 'gray' : 'gray' })
  }
  return out
}

/** Сводка одной строкой для списка: «новых 3 · изменится 1 · ошибок 2». */
export function summaryText(summary) {
  if (!summary || typeof summary !== 'object') return ''
  const parts = []
  const add = (key, label) => { if (summary[key]) parts.push(`${label} ${formatNumber(summary[key])}`) }
  add('create', 'новых')
  add('update', 'изменится')
  add('delete', 'удалится')
  add('cleared', 'очистится')
  add('unresolved', 'нужно решение')
  add('errors', 'ошибок')
  if (!parts.length) {
    const total = summary.rows ?? summary.records ?? summary.departments
    if (summary.unchanged) parts.push(`без изменений ${formatNumber(summary.unchanged)}`)
    else if (typeof total === 'number') parts.push(`${formatNumber(total)} ${plural(total, ['строка', 'строки', 'строк'])}, изменений нет`)
  }
  return parts.join(' · ')
}

/** Что показать в столбце «Сводка» списка: сводка плана, ошибка или сообщение. */
export function itemSummary(item) {
  if (!item) return ''
  if (item.status === 'error') return item.error || item.message || 'Ошибка обработки'
  if (item.status === 'duplicate') return item.duplicate_of ? `Повтор элемента №${item.duplicate_of}` : 'Повтор уже полученного файла'
  if (item.status === 'received') return item.message || 'Набор не распознан'
  return summaryText(item.summary) || item.message || ''
}

// ---------------------------------------------------------------- строки плана

export const ROW_ACTIONS = {
  create: { label: 'Новое', tone: 'green' },
  update: { label: 'Изменится', tone: 'blue' },
  unchanged: { label: 'Без изменений', tone: 'gray' },
  skip: { label: 'Пропущено', tone: 'gray' },
  delete: { label: 'Удалится', tone: 'red' },
  // Значения показателей: строка «очистить» удаляет сохранённое значение за месяц
  clear: { label: 'Очистить', tone: 'red' },
  error: { label: 'Ошибка', tone: 'red' },
  add: { label: 'Назначить', tone: 'green' },
  exists: { label: 'Уже назначен', tone: 'gray' },
  pending: { label: 'Нет в системе', tone: 'yellow' },
}

/** «Станет» у строки «очистить»: сохранённое значение удаляется. */
export const CLEARED_TEXT = 'значение удалится'

/** Строки «очистить» в плане (значения показателей). */
export const planClears = (rows = []) => rows.filter((r) => r.action === 'clear').length

export const PLAN_FILTERS = [
  { value: 'changes', label: 'Изменения и ошибки' },
  { value: 'errors', label: 'Ошибки' },
  { value: 'all', label: 'Все' },
]

const isNil = (v) => v === null || v === undefined || v === ''
const lastSegment = (path) => String(path || '').split(' / ').at(-1)
const shortDate = (text) => {
  const m = String(text || '').match(/^(\d{4})-(\d{2})-(\d{2})/)
  return m ? `${m[3]}.${m[2]}.${m[1]}` : String(text || '')
}

function valueText(state) {
  if (state === null || state === undefined) return '—'
  if (typeof state !== 'object') return String(state)
  const parts = []
  parts.push(isNil(state.value) ? '—' : formatNumber(state.value))
  if (!isNil(state.target)) parts.push(`цель ${formatNumber(state.target)}`)
  if (state.comment) parts.push(`«${state.comment}»`)
  if (state.note) parts.push(`«${state.note}»`)
  return parts.join(' · ')
}

function changeText(change) {
  if (typeof change === 'string') return change
  if (!change || typeof change !== 'object') return ''
  const label = change.label || change.field || ''
  const show = (v) => (Array.isArray(v) ? (v.length ? v.join('; ') : '—') : isNil(v) ? '—' : String(v))
  if ('new' in change || 'old' in change) {
    return `${label}: ${show(change.new)}${isNil(change.old) || (Array.isArray(change.old) && !change.old.length) ? '' : ` (было ${show(change.old)})`}`
  }
  return label
}

/** Подпись строки плана по полям движка: что это за запись и где она в файле. */
function rowTitle(row) {
  if (row.metric_label) return { title: row.metric_label, subtitle: row.month_label || monthLabel(row.month) }
  if (row.indicator_name || row.indicator) {
    const unit = lastSegment(row.department_path) || row.department || ''
    return { title: row.indicator_name || row.indicator, subtitle: [unit, row.period].filter(Boolean).join(' · ') }
  }
  if (row.full_name) return { title: row.full_name, subtitle: [row.event_label, shortDate(row.event_date)].filter(Boolean).join(' · ') }
  if (row.partner) return { title: row.partner, subtitle: row.product || '' }
  if (row.number !== undefined && row.registered_at) return { title: `№ ${row.number}`, subtitle: [row.status, shortDate(row.registered_at)].filter(Boolean).join(' · ') }
  if (row.year && row.week) return { title: row.period || `${row.year}-W${String(row.week).padStart(2, '0')}`, subtitle: `Неделя ${row.week}, ${row.year}` }
  if (row.email !== undefined && (row.name !== undefined || row.key !== undefined)) return { title: row.name || row.email || 'Без имени', subtitle: row.email || '' }
  if (row.path) return { title: lastSegment(row.path), subtitle: row.path }
  const title = row.title || row.name || row.period || row.key || ''
  return { title: String(title || '—'), subtitle: '' }
}

/** Массив строк плана — у движков он называется по-разному. */
export function planRowsSource(plan) {
  if (!plan || typeof plan !== 'object') return []
  for (const key of ['rows', 'records', 'users']) if (Array.isArray(plan[key])) return plan[key]
  // План структуры: подразделения с действием (у плана сотрудников departments — только новые, без действия)
  if (Array.isArray(plan.departments) && plan.departments.some((d) => d && 'action' in d)) return plan.departments
  return []
}

/**
 * Строки плана в одном виде: { key, line, title, subtitle, action, before, after, changes, errors,
 * warnings, conflicts, unresolved, identity }. before/after — значения ячеек (метрики, показатели).
 */
export function planRows(plan) {
  return planRowsSource(plan).map((row, index) => {
    const { title, subtitle } = rowTitle(row)
    const before = row.before !== undefined ? valueText(row.before) : null
    let after = row.after !== undefined ? (row.action === 'error' ? '—' : valueText(row.after)) : null
    if (row.action === 'clear') after = CLEARED_TEXT
    return {
      key: `${row.key ?? row.id ?? row.number ?? row.period ?? ''}-${row.line ?? index}-${index}`,
      line: row.line ?? null,
      title,
      subtitle,
      action: row.unresolved ? 'error' : row.action || 'unchanged',
      unresolved: !!row.unresolved,
      before,
      after,
      changes: (row.changes || []).map(changeText).filter(Boolean),
      errors: (row.errors || []).map(String),
      warnings: (row.warnings || []).map(String),
      conflicts: row.conflicts || [],
      identity: row.identity || null,
      raw: row,
    }
  })
}

export const rowHasErrors = (row) => row.action === 'error' || row.errors.length > 0 || row.unresolved

/** Изменения и ошибки / только ошибки / все. */
export function filterPlanRows(rows = [], filter = 'changes') {
  if (filter === 'errors') return rows.filter(rowHasErrors)
  if (filter === 'changes') {
    return rows.filter((r) => !['unchanged', 'skip', 'exists'].includes(r.action) || rowHasErrors(r) || r.warnings.length || r.conflicts.length)
  }
  return rows
}

/** Подпись действия строки; у записи без решения — «Нужно решение». */
export function rowAction(row) {
  if (row.unresolved) return { label: 'Нужно решение', tone: 'red' }
  if (row.errors.length && row.action !== 'error') return { label: 'Ошибка', tone: 'red' }
  return ROW_ACTIONS[row.action] || { label: row.action, tone: 'gray' }
}

/**
 * Ошибки плана списком — как на сервере (plan_errors): общие и по строкам с указанием, где.
 * limit — не больше стольких.
 */
export function planErrors(plan, limit = 50) {
  if (!plan || typeof plan !== 'object') return []
  const out = []
  for (const e of Array.isArray(plan.errors) ? plan.errors : []) if (typeof e === 'string') out.push(e)
  for (const key of ['rows', 'records', 'users', 'departments']) {
    for (const row of Array.isArray(plan[key]) ? plan[key] : []) {
      if (!row || typeof row !== 'object' || !row.errors?.length) continue
      const where = row.line ? `строка ${row.line}` : row.email || row.path || ''
      for (const e of row.errors) {
        out.push(where ? `${where}: ${e}` : String(e))
        if (out.length >= limit) return out
      }
    }
  }
  return out.slice(0, limit)
}

/** Руководители в плане структуры, которых нужно назначить или нет в системе. */
export function planHeads(plan) {
  return (Array.isArray(plan?.heads) ? plan.heads : []).filter((h) => h.action === 'add' || h.action === 'pending')
}

/** Новые подразделения в плане сотрудников (у плана структуры они — сами строки). */
export function planNewDepartments(plan) {
  if (!Array.isArray(plan?.departments) || plan.departments.some((d) => d && 'action' in d)) return []
  return plan.departments
}

// ---------------------------------------------------------------- параметры набора

/** Значения параметров для формы: сохранённые у элемента, иначе по умолчанию. */
export function optionValues(fields = [], options = {}) {
  return Object.fromEntries(fields.map((f) => [f.key, options && f.key in options ? options[f.key] : f.default]))
}

/** Параметры изменены относительно сохранённых у элемента. */
export function optionsChanged(fields = [], values = {}, options = {}) {
  return fields.some((f) => JSON.stringify(values[f.key]) !== JSON.stringify(options?.[f.key] ?? f.default))
}

/**
 * Параметры для запроса: значения полей плюс служебные (решения по сотрудникам — decisions),
 * которых нет среди полей, но которые набор хранит.
 */
export function optionsPayload(fields = [], values = {}, options = {}) {
  const out = { ...(options || {}) }
  for (const f of fields) out[f.key] = values[f.key]
  return out
}

// ---------------------------------------------------------------- правила «применять сразу»

/**
 * Матрица правил: строки — наборы, столбцы — источники с правилами. rules — [{ source, dataset,
 * auto_apply, source_label, dataset_label }]. → { sources: [{ key, label }], rows: [{ key, label, cells }] }.
 */
export function rulesMatrix(rules = [], { datasets = [], sources = [] } = {}) {
  const sourceKeys = sources.length ? sources.filter((s) => s.has_rules !== false).map((s) => s.key) : [...new Set(rules.map((r) => r.source))]
  const labelOf = (key) => sources.find((s) => s.key === key)?.label || rules.find((r) => r.source === key)?.source_label || SOURCE_LABELS[key] || key
  const datasetKeys = datasets.length ? datasets.map((d) => d.key) : [...new Set(rules.map((r) => r.dataset))]
  const datasetLabel = (key) => datasets.find((d) => d.key === key)?.label || rules.find((r) => r.dataset === key)?.dataset_label || key
  const value = (source, dataset) => !!rules.find((r) => r.source === source && r.dataset === dataset)?.auto_apply
  return {
    sources: sourceKeys.map((key) => ({ key, label: labelOf(key) })),
    rows: datasetKeys.map((key) => ({ key, label: datasetLabel(key), cells: Object.fromEntries(sourceKeys.map((s) => [s, value(s, key)])) })),
  }
}

/** Изменённые правила для PUT: [{ source, dataset, auto_apply }]. */
export function rulesChanges(original, draft) {
  const out = []
  for (const row of draft?.rows || []) {
    const before = original?.rows?.find((r) => r.key === row.key)?.cells || {}
    for (const [source, value] of Object.entries(row.cells)) {
      if (!!before[source] !== !!value) out.push({ source, dataset: row.key, auto_apply: !!value })
    }
  }
  return out
}

export const cloneMatrix = (m) => ({ sources: [...(m?.sources || [])], rows: (m?.rows || []).map((r) => ({ ...r, cells: { ...r.cells } })) })

// ---------------------------------------------------------------- папка и планировщик

/** Состояние папки «Входящие»: { tone, label, text }. */
export function folderState(folder) {
  if (!folder) return { tone: 'gray', label: '—', text: '' }
  if (!folder.enabled) return { tone: 'gray', label: 'Не настроена', text: 'Задайте переменную INBOX_DIR на сервере (в Docker — том /data/inbox) и перезапустите приложение и планировщик' }
  if (!folder.exists) return { tone: 'red', label: 'Не найдена', text: `Папки ${folder.path} нет на сервере — создайте её или исправьте INBOX_DIR` }
  if (!folder.writable) return { tone: 'yellow', label: 'Только чтение', text: `Нет прав на запись в ${folder.path}: обработанные файлы не перенести в processed/ и rejected/` }
  const waiting = folder.waiting_files || 0
  return {
    tone: 'green',
    label: 'Работает',
    text: waiting ? `Ждут разбора: ${waiting} ${plural(waiting, ['файл', 'файла', 'файлов'])}` : 'Новых файлов нет',
  }
}

const toDate = (value) => {
  if (!value) return null
  const text = String(value)
  return new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(text) ? text : `${text}Z`)
}

/**
 * Планировщик (python -m app.cli worker) по отметке о работе: { tone, label, text }. Отметка старше
 * трёх тактов (не меньше 2 минут) — «не отвечает».
 */
export function workerState(worker, now = new Date()) {
  if (!worker?.last_tick_at) {
    return { tone: 'yellow', label: 'Не запущен', text: 'Планировщик ещё не отмечался: папку разбирает только кнопка «Проверить сейчас», расписания не выполняются. Запустите сервис worker (python -m app.cli worker)' }
  }
  const last = toDate(worker.last_tick_at)
  const tick = Number(worker.tick_seconds) || 30
  const late = now - last > Math.max(120, tick * 3) * 1000
  const where = [worker.host, worker.version ? `версия ${worker.version}` : ''].filter(Boolean).join(' · ')
  if (late) return { tone: 'red', label: 'Не отвечает', text: `Последняя отметка ${formatRelative(last, now)} (${formatDateTime(last)})${where ? ` — ${where}` : ''}` }
  return { tone: 'green', label: 'Работает', text: `Такт ${tick} с, последняя отметка ${formatRelative(last, now)}${where ? ` — ${where}` : ''}` }
}

/** Итог разбора папки одной строкой. */
export function scanText(result) {
  if (!result) return ''
  const parts = [`взято файлов: ${result.taken || 0}`]
  if (result.applied) parts.push(`применено: ${result.applied}`)
  if (result.pending) parts.push(`ожидают: ${result.pending}`)
  if (result.duplicates) parts.push(`повторов: ${result.duplicates}`)
  if (result.errors) parts.push(`ошибок: ${result.errors}`)
  if (result.waiting) parts.push(`дописываются: ${result.waiting}`)
  if (result.skipped) parts.push(`пропущено: ${result.skipped}`)
  const text = parts.join(', ')
  return text[0].toUpperCase() + text.slice(1)
}

/** Устройство папки «Входящие» деревом — для справки. */
export function folderTree(folder, datasets = []) {
  const root = folder?.path || 'INBOX_DIR'
  const names = (folder?.folders?.length ? folder.folders.map((f) => f.folder) : datasets.map((d) => d.folder || d.key))
  const width = Math.max(14, ...names.map((n) => n.length + 2))
  const lines = [`${root}/`, `├── ${'файл.xlsx'.padEnd(width)}набор распознаётся по имени и содержимому`]
  for (const name of names) {
    const label = folder?.folders?.find((f) => f.folder === name)?.label || datasets.find((d) => d.key === name)?.label || ''
    lines.push(`├── ${`${name}/`.padEnd(width)}${label}`)
  }
  lines.push(`├── ${'processed/'.padEnd(width)}принятые, по месяцам ГГГГ-ММ/ с отчётом *.result.json`)
  lines.push(`└── ${'rejected/'.padEnd(width)}не принятые: ошибка, повтор, слишком большой`)
  return lines.join('\n')
}
