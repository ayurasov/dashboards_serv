/**
 * Копирование в буфер обмена. В небезопасном контексте (http не на localhost) navigator.clipboard
 * недоступен — тогда через скрытое поле и execCommand. true — скопировано.
 */
export async function writeClipboard(text) {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    const area = document.createElement('textarea')
    area.value = text
    area.setAttribute('readonly', '')
    area.style.position = 'fixed'
    area.style.opacity = '0'
    document.body.appendChild(area)
    area.select()
    let ok = false
    try { ok = document.execCommand('copy') } catch {}
    area.remove()
    return ok
  }
}
