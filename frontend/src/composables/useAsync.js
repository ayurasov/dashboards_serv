import { ref, shallowRef } from 'vue'

/**
 * Загрузка данных страницы: data, loading, error и reload().
 * Устаревшие ответы (если запрос перезапущен раньше, чем пришёл прошлый) отбрасываются.
 */
export function useAsync(loader, { immediate = true, initial = null } = {}) {
  const data = shallowRef(initial)
  const loading = ref(false)
  const error = ref(null)
  let seq = 0

  async function reload(...args) {
    const id = ++seq
    loading.value = true
    error.value = null
    try {
      const result = await loader(...args)
      if (id === seq) data.value = result
      return result
    } catch (e) {
      if (id === seq) error.value = e
      return undefined
    } finally {
      if (id === seq) loading.value = false
    }
  }

  if (immediate) reload()
  return { data, loading, error, reload }
}
