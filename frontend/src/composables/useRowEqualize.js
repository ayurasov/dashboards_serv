import { ref, onMounted, onUnmounted, nextTick } from 'vue'

/**
 * Gives every widget in the same grid row the height of the tallest one.
 *
 * Rows are discovered from the rendered layout rather than from the widget list,
 * because the grid reflows at narrow widths and a "row" is then a single cell.
 *
 * Each scheduled run performs several passes on consecutive animation frames:
 * clear pins → measure → pin, repeat. That makes it converge even when a chart's
 * own minHeight (or a table) settles one frame after the mutation that scheduled
 * the run — a single pass could measure mid-update and pin a stale height.
 * The passes stop early once nothing changes; identical writes produce no resize
 * events, so the ResizeObserver doesn't keep it alive forever.
 */
export function useRowEqualize() {
  const gridEl = ref(null)
  let observer = null
  let passLeft = 0
  let queued = false

  function pass() {
    const grid = gridEl.value
    if (!grid) return
    const cells = [...grid.children].filter(el => el.classList?.contains('wcell'))
    if (!cells.length) return

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
  }

  function run() {
    queued = false
    if (passLeft-- <= 0) return
    pass()
    if (passLeft > 0) requestAnimationFrame(run)
  }

  function schedule() {
    passLeft = 4
    if (queued) return
    queued = true
    requestAnimationFrame(run)
  }

  onMounted(() => {
    nextTick(schedule)
    observer = new ResizeObserver(schedule)
    if (gridEl.value) observer.observe(gridEl.value)
    window.addEventListener('resize', schedule)
  })

  onUnmounted(() => {
    observer?.disconnect()
    window.removeEventListener('resize', schedule)
  })

  return { gridEl, equalize: schedule }
}
