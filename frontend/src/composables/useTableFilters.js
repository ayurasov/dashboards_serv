import { reactive, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

/**
 * Per-column filter + sort state that lives in the URL query, so a registry
 * survives a reload and can be pre-filtered by a link from a chart.
 *
 * `defaults` maps a filter name to its "empty" value; anything equal to the
 * default is left out of the URL to keep links short.
 */
export function useTableFilters(defaults, { sortKey = '', sortDir = 'asc' } = {}) {
  const route = useRoute()
  const router = useRouter()

  const f = reactive({ ...defaults })
  const sort = reactive({ key: sortKey, dir: sortDir === 'desc' ? -1 : 1 })

  function applyQuery(q) {
    for (const key of Object.keys(defaults)) {
      const v = q[key]
      f[key] = v === undefined ? defaults[key] : String(v)
    }
    if (q.sort !== undefined) sort.key = String(q.sort)
    if (q.dir !== undefined) sort.dir = q.dir === 'desc' ? -1 : 1
  }

  applyQuery(route.query)

  function buildQuery() {
    const q = {}
    for (const key of Object.keys(defaults)) {
      if (f[key] !== defaults[key] && f[key] !== '') q[key] = f[key]
    }
    if (sort.key) {
      q.sort = sort.key
      q.dir = sort.dir === 1 ? 'asc' : 'desc'
    }
    return q
  }

  let selfWrite = false
  function syncUrl() {
    const q = buildQuery()
    const same = JSON.stringify(q) === JSON.stringify(
      Object.fromEntries(Object.entries(route.query).map(([k, v]) => [k, String(v)])))
    if (same) return
    selfWrite = true
    router.replace({ query: q }).catch(() => {})
  }

  watch([f, sort], syncUrl, { deep: true })
  watch(() => route.query, (q) => {
    if (selfWrite) { selfWrite = false; return }
    applyQuery(q)
  })

  function setSort(key) {
    if (sort.key === key) sort.dir *= -1
    else { sort.key = key; sort.dir = 1 }
  }

  function sortMark(key) {
    if (sort.key !== key) return ''
    return sort.dir === 1 ? '▲' : '▼'
  }

  function reset() {
    Object.assign(f, defaults)
  }

  const active = computed(() => Object.keys(defaults).filter(k => f[k] !== defaults[k] && f[k] !== ''))

  /** Compares two row values with the current direction; numbers and dates sort naturally. */
  function compare(a, b) {
    const va = a ?? '', vb = b ?? ''
    if (va === vb) return 0
    if (typeof va === 'number' && typeof vb === 'number') return (va - vb) * sort.dir
    if (typeof va === 'boolean' || typeof vb === 'boolean') return ((va ? 1 : 0) - (vb ? 1 : 0)) * sort.dir
    return String(va).localeCompare(String(vb), 'ru', { numeric: true }) * sort.dir
  }

  function sortRows(list, pick = (row, key) => row[key]) {
    if (!sort.key) return list
    return [...list].sort((a, b) => compare(pick(a, sort.key), pick(b, sort.key)))
  }

  return { f, sort, setSort, sortMark, reset, active, compare, sortRows }
}

/** Case-insensitive "contains" used by every text column filter. */
export function textMatch(value, needle) {
  if (!needle) return true
  return String(value ?? '').toLowerCase().includes(needle.trim().toLowerCase())
}
