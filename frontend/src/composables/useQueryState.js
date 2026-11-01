import { reactive, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

/**
 * Фильтры страницы, сохранённые в адресной строке: ссылкой можно поделиться,
 * «Назад» возвращает прежние фильтры. defaults задаёт поля и их типы (строка, число, массив).
 */
export function useQueryState(defaults) {
  const route = useRoute()
  const router = useRouter()

  function parse(key, raw) {
    const base = defaults[key]
    if (raw === undefined || raw === null || raw === '') return Array.isArray(base) ? [...base] : base
    if (Array.isArray(base)) return String(raw).split(',').filter(Boolean)
    if (typeof base === 'number') return Number(raw)
    if (typeof base === 'boolean') return raw === '1' || raw === 'true'
    return String(raw)
  }

  const state = reactive(Object.fromEntries(Object.keys(defaults).map((k) => [k, parse(k, route.query[k])])))

  function serialize() {
    const query = { ...route.query }
    for (const [key, base] of Object.entries(defaults)) {
      const value = state[key]
      const isDefault = Array.isArray(base) ? value.join(',') === base.join(',') : value === base
      if (isDefault || value === '' || value === null) delete query[key]
      else query[key] = Array.isArray(value) ? value.join(',') : typeof value === 'boolean' ? (value ? '1' : '0') : String(value)
    }
    return query
  }

  const path = route.path
  watch(state, () => {
    if (route.path === path) router.replace({ query: serialize(), hash: route.hash })
  }, { deep: true })

  // «Назад» / «Вперёд» и переход по ссылке на ту же страницу с другими параметрами
  watch(() => route.query, (query) => {
    if (route.path !== path) return // уход со страницы — не трогаем
    for (const key of Object.keys(defaults)) {
      const next = parse(key, query[key])
      if (JSON.stringify(next) !== JSON.stringify(state[key])) state[key] = next
    }
  })

  function reset() {
    for (const [key, base] of Object.entries(defaults)) state[key] = Array.isArray(base) ? [...base] : base
  }

  function isDefault() {
    return Object.entries(defaults).every(([k, base]) => (Array.isArray(base) ? state[k].join(',') === base.join(',') : state[k] === base))
  }

  return { state, reset, isDefault }
}
