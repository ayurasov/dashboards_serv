import { onUnmounted } from 'vue'

// The single PDF button lives in the topbar, so the page that is open publishes
// its filters here and the button picks them up.
let paramsSource = null

/** Called by a page whose PDF should honour its on-screen filters. */
export function setPdfParams(fn) {
  paramsSource = fn
  onUnmounted(() => { if (paramsSource === fn) paramsSource = null })
}

export function currentPdfParams() {
  try {
    return paramsSource?.() || {}
  } catch {
    return {}
  }
}
