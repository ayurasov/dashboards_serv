import { computed, ref } from 'vue'
import { commonApi } from '@/api/services'
import { toastOk } from '@/composables/useToast'

/**
 * Личная настройка дашборда службы: какие блоки показывать и в каком порядке.
 * blocks: [{ key, label }] — блоки страницы по умолчанию (все видимы, в этом порядке).
 * Хранится на сервере (/api/layouts/{service}), поэтому одинакова на всех устройствах.
 */
export function useDashboardLayout(serviceKey, blocks) {
  const saved = ref([])
  const loaded = ref(false)

  const ordered = computed(() => {
    const byKey = Object.fromEntries(saved.value.map((w) => [w.key, w]))
    return blocks
      .map((b, i) => ({ ...b, visible: byKey[b.key]?.visible ?? true, order: byKey[b.key]?.order ?? 100 + i }))
      .sort((a, b) => a.order - b.order)
  })

  function visible(key) {
    return ordered.value.find((b) => b.key === key)?.visible ?? true
  }

  function orderOf(key) {
    return ordered.value.findIndex((b) => b.key === key)
  }

  async function load() {
    try {
      saved.value = (await commonApi.layout(serviceKey)).widgets || []
    } catch {
      saved.value = []
    }
    loaded.value = true
  }

  async function save(items) {
    const widgets = items.map((b, i) => ({ key: b.key, visible: b.visible, order: i, size: 'medium' }))
    saved.value = (await commonApi.saveLayout(serviceKey, widgets)).widgets
    toastOk('Настройка дашборда сохранена')
  }

  async function reset() {
    await commonApi.resetLayout(serviceKey)
    saved.value = []
    toastOk('Восстановлен вид по умолчанию')
  }

  load()
  return { ordered, visible, orderOf, save, reset, loaded }
}
