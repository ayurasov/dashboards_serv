export const PARTNERSHIP_STATUSES = ['Завершено', 'В работе', 'Отложено', 'Не подписывают']

const STATUS_CLASS = {
  'Завершено': 's-done',
  'В работе': 's-prog',
  'Отложено': 's-hold',
  'Не подписывают': 's-none',
}

export function statusClass(status) {
  return STATUS_CLASS[status] || 's-neutral'
}

/** Traffic-light key for a status, used to pick a dot colour from the palette. */
export function statusTone(status) {
  if (status === 'Завершено') return 'green'
  if (status === 'В работе') return 'yellow'
  if (status === 'Не подписывают') return 'red'
  return 'neutral'
}

export function formatDate(d) {
  return d ? new Date(d).toLocaleDateString('ru-RU') : '—'
}
