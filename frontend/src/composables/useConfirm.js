import { reactive } from 'vue'

/**
 * Диалог подтверждения. Использование:
 *   if (await confirm({ title: 'Удалить месяц?', message: '…', confirmText: 'Удалить', danger: true })) …
 */
export const confirmState = reactive({ open: false, title: '', message: '', confirmText: 'Подтвердить', danger: false })
let resolver = null

export function confirm(options) {
  Object.assign(confirmState, { confirmText: 'Подтвердить', danger: false, message: '' }, options, { open: true })
  return new Promise((resolve) => { resolver = resolve })
}

export function resolveConfirm(result) {
  confirmState.open = false
  if (resolver) resolver(result)
  resolver = null
}
