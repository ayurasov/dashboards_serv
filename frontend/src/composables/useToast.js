import { ref } from 'vue'

const TOAST_MS = 4000
let seq = 0

export const toasts = ref([])

export function dismissToast(id) {
  toasts.value = toasts.value.filter(t => t.id !== id)
}

/** kind: 'info' | 'ok' | 'err' */
export function pushToast(message, kind = 'info') {
  if (!message) return
  // A single failing screen can fire the same request many times; one toast is enough.
  if (toasts.value.some(t => t.message === message)) return
  const id = ++seq
  toasts.value.push({ id, message, kind })
  setTimeout(() => dismissToast(id), TOAST_MS)
  return id
}

export function toastError(message) {
  pushToast(message, 'err')
}

export function toastOk(message) {
  pushToast(message, 'ok')
}
