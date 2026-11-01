/**
 * Открытые модальные окна и боковые панели — стопкой. Клавиатуру (Esc, Tab) обрабатывает только
 * верхнее окно: Esc в подтверждении поверх формы закрывает подтверждение, а не форму под ним.
 * Прокрутка страницы блокируется, пока открыто хотя бы одно окно.
 */
const stack = []

export function pushModal() {
  const token = Symbol('modal')
  stack.push(token)
  if (typeof document !== 'undefined') document.body.style.overflow = 'hidden'
  return token
}

export function popModal(token) {
  const index = stack.indexOf(token)
  if (index >= 0) stack.splice(index, 1)
  if (!stack.length && typeof document !== 'undefined') document.body.style.overflow = ''
}

export function isTopModal(token) {
  return stack.length > 0 && stack[stack.length - 1] === token
}

export function openModals() {
  return stack.length
}

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

/** Элементы окна, на которые можно перейти клавишей Tab (видимые и доступные). */
export function focusables(container) {
  if (!container) return []
  return [...container.querySelectorAll(FOCUSABLE)].filter((el) => !el.closest('[inert]') && el.getClientRects().length > 0)
}

/** Tab и Shift+Tab не выводят фокус из окна: после последнего элемента — первый, и наоборот. */
export function trapFocus(event, container) {
  if (event.key !== 'Tab' || !container) return
  const items = focusables(container)
  const active = document.activeElement
  if (!items.length) {
    event.preventDefault()
    container.focus()
    return
  }
  const first = items[0]
  const last = items[items.length - 1]
  const outside = !container.contains(active) || active === container
  if (event.shiftKey && (active === first || outside)) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && (active === last || outside)) {
    event.preventDefault()
    first.focus()
  }
}

/** Вернуть фокус элементу, который открыл окно (если он ещё на странице). */
export function restoreFocus(element) {
  if (element && typeof element.focus === 'function' && document.contains(element)) element.focus({ preventScroll: true })
}
