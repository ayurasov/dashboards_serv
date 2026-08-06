import { ref, onMounted, onUnmounted, nextTick } from 'vue'

/**
 * Gives every widget in the same grid row the height of the tallest one.
 *
 * Rows are discovered from the rendered layout rather than from the widget list,
 * because the grid reflows at narrow widths and a "row" is then a single cell.
 */
export function useRowEqualize() {
  const gridEl = ref(null)
  let observer = null
  let raf = 0
  let equalizing = false

  function equalize() {
    const grid = gridEl.value
    if (!grid) return
    const cells = [...grid.children].filter(el => el.classList?.contains('wcell'))
    if (!cells.length) return

    equalizing = true
    for (const el of cells) el.style.minHeight = ''

    const rows = new Map()
    for (const el of cells) {
      // Cells in one row share a top offset; round to absorb sub-pixel drift.
      const top = Math.round(el.offsetTop)
      if (!rows.has(top)) rows.set(top, [])
      rows.get(top).push(el)
    }
    for (const group of rows.values()) {
      if (group.length < 2) continue
      const tallest = Math.max(...group.map(el => el.offsetHeight))
      for (const el of group) el.style.minHeight = tallest + 'px'
    }
    // Release the guard only after the browser has settled the new heights,
    // otherwise our own writes retrigger the observer.
    requestAnimationFrame(() => { equalizing = false })
  }

  function schedule() {
    if (equalizing) return
    cancelAnimationFrame(raf)
    raf = requestAnimationFrame(equalize)
  }

  onMounted(() => {
    nextTick(equalize)
    observer = new ResizeObserver(schedule)
    if (gridEl.value) observer.observe(gridEl.value)
    window.addEventListener('resize', schedule)
  })

  onUnmounted(() => {
    cancelAnimationFrame(raf)
    observer?.disconnect()
    window.removeEventListener('resize', schedule)
  })

  return { gridEl, equalize: schedule }
}
