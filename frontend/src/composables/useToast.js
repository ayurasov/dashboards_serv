import { reactive } from 'vue'

/** Всплывающие сообщения. Ошибки держатся дольше успехов; одинаковые подряд не дублируются. */
export const toasts = reactive([])
let seq = 0

function push(kind, message, timeout) {
  const last = toasts[toasts.length - 1]
  if (last && last.message === message && last.kind === kind) return
  const id = ++seq
  toasts.push({ id, kind, message })
  if (toasts.length > 4) toasts.shift()
  setTimeout(() => dismissToast(id), timeout)
}

export function dismissToast(id) {
  const index = toasts.findIndex((t) => t.id === id)
  if (index >= 0) toasts.splice(index, 1)
}

export const toastOk = (message) => push('ok', message, 3200)
export const toastError = (message) => push('error', message, 6000)
export const toastInfo = (message) => push('info', message, 4000)
