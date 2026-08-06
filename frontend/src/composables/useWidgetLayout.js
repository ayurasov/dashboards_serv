import { ref, computed } from 'vue'
import { api } from '../api/client.js'
import { toastOk } from './useToast.js'

export const WIDGET_SIZES = [
  { value: 'small', label: '1/3' },
  { value: 'medium', label: '1/2' },
  { value: 'wide', label: '2/3' },
  { value: 'large', label: 'Вся ширина' },
]

// Auto-layout size per widget kind. A catalog entry declares its `kind`; anything
// undeclared keeps the size it already has.
const AUTO_SIZES = { kpi: 'small', chart: 'medium', wide_chart: 'wide', table: 'large' }

// Column spans of `.wcell` in the 6-column `.wgrid`, mirrored from style.css.
const GRID_COLUMNS = 6
const SIZE_SPANS = { small: 2, medium: 3, wide: 4, large: 6 }
const CHART_KINDS = new Set(['chart', 'wide_chart'])

/**
 * Widget order / size / visibility for one service dashboard, persisted per user
 * through /api/dashboard/preferences. `catalog` is the list of widgets the page
 * knows how to render: [{ key, title, size, visible }].
 */
export function useWidgetLayout(serviceKey, catalog) {
  const byKey = new Map(catalog.map(c => [c.key, c]))
  const defaults = () => catalog.map((c, i) => ({
    key: c.key,
    visible: c.visible !== false,
    size: c.size || 'medium',
    sort_order: i,
    settings: {},
  }))

  const layout = ref(defaults())

  const ordered = computed(() => [...layout.value].sort((a, b) => a.sort_order - b.sort_order))
  const visibleWidgets = computed(() => ordered.value.filter(w => w.visible))

  function title(key) { return byKey.get(key)?.title || key }
  function sizeOf(key) { return layout.value.find(w => w.key === key)?.size || 'medium' }
  function settingsOf(key) { return layout.value.find(w => w.key === key)?.settings || {} }

  /** Per-chart overrides are saved immediately so the gear popover needs no Save step. */
  async function setSettings(key, settings) {
    const row = layout.value.find(w => w.key === key)
    if (!row) return
    row.settings = { ...settings }
    await persist()
  }

  async function load() {
    let saved = []
    try {
      saved = (await api.get(`/dashboard/preferences/${serviceKey}`))?.widgets || []
    } catch {
      return // the API layer already surfaced the reason; defaults stay
    }
    // Widgets added to the catalog after the layout was saved land at the end.
    const known = saved.filter(w => byKey.has(w.key))
    if (!known.length) return
    const seen = new Set(known.map(w => w.key))
    const merged = known.map((w, i) => ({
      key: w.key,
      visible: w.visible !== false,
      size: WIDGET_SIZES.some(s => s.value === w.size) ? w.size : 'medium',
      sort_order: i,
      settings: w.settings && typeof w.settings === 'object' ? w.settings : {},
    }))
    for (const c of catalog) {
      if (!seen.has(c.key)) {
        merged.push({ key: c.key, visible: c.visible !== false, size: c.size || 'medium',
                      sort_order: merged.length, settings: {} })
      }
    }
    layout.value = merged
  }

  function normalized() {
    return ordered.value.map((w, i) => ({
      key: w.key, visible: w.visible, size: w.size, sort_order: i, settings: w.settings || {},
    }))
  }

  async function persist() {
    const widgets = normalized()
    try {
      await api.put(`/dashboard/preferences/${serviceKey}`, { widgets })
      layout.value = widgets
      return true
    } catch {
      return false
    }
  }

  async function save() {
    if (!await persist()) return false
    toastOk('Настройки дашборда сохранены')
    return true
  }

  /** Sizes every widget by its declared kind, then persists the result. */
  async function autoLayout() {
    layout.value = ordered.value.map((w, i) => ({
      ...w,
      size: AUTO_SIZES[byKey.get(w.key)?.kind] || w.size,
      sort_order: i,
    }))
    if (await persist()) toastOk('Виджеты расставлены автоматически')
  }

  async function resetLayout() {
    try { await api.del(`/dashboard/preferences/${serviceKey}`) } catch { return }
    layout.value = defaults()
    toastOk('Настройки дашборда сброшены')
  }

  function move(fromKey, toKey) {
    if (!fromKey || !toKey || fromKey === toKey) return
    const list = normalized()
    const from = list.findIndex(w => w.key === fromKey)
    const to = list.findIndex(w => w.key === toKey)
    if (from < 0 || to < 0) return
    const [moved] = list.splice(from, 1)
    list.splice(to, 0, moved)
    layout.value = list.map((w, i) => ({ ...w, sort_order: i }))
  }

  return { layout, ordered, visibleWidgets, title, sizeOf, settingsOf, setSettings,
           load, save, resetLayout, autoLayout, move }
}

/** HTML5 drag-and-drop plumbing shared by the dashboard grid and the settings list. */
export function useDragReorder(onMove) {
  const dragKey = ref('')
  const overKey = ref('')

  function dragStart(key, ev) {
    dragKey.value = key
    if (ev.dataTransfer) {
      ev.dataTransfer.effectAllowed = 'move'
      ev.dataTransfer.setData('text/plain', key)
    }
  }

  function dragOver(key, ev) {
    ev.preventDefault()
    if (ev.dataTransfer) ev.dataTransfer.dropEffect = 'move'
    overKey.value = key === dragKey.value ? '' : key
  }

  function drop(key, ev) {
    ev.preventDefault()
    const from = dragKey.value || ev.dataTransfer?.getData('text/plain')
    onMove(from, key)
    dragEnd()
  }

  function dragEnd() {
    dragKey.value = ''
    overKey.value = ''
  }

  return { dragKey, overKey, dragStart, dragOver, drop, dragEnd }
}
