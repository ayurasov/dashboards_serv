<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'

/**
 * Длинный список с отрисовкой только видимых строк (тысячи сотрудников в «Дереве»).
 * Высота строки задаётся функцией height(item); ключ строки — item.key.
 */
const props = defineProps({
  items: { type: Array, required: true },
  height: { type: Function, required: true },
  overscan: { type: Number, default: 8 },
  label: { type: String, default: '' },
  role: { type: String, default: 'list' },
})

const root = ref(null)
const scrollTop = ref(0)
const viewHeight = ref(600)

const offsets = computed(() => {
  const list = new Float64Array(props.items.length + 1)
  for (let i = 0; i < props.items.length; i += 1) list[i + 1] = list[i] + props.height(props.items[i])
  return list
})
const total = computed(() => offsets.value[props.items.length])

/** Индекс строки, на которую приходится смещение y. */
function indexAt(y) {
  const list = offsets.value
  let lo = 0
  let hi = props.items.length - 1
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1
    if (list[mid] <= y) lo = mid
    else hi = mid - 1
  }
  return Math.max(0, lo)
}

const visible = computed(() => {
  if (!props.items.length) return []
  const start = Math.max(0, indexAt(scrollTop.value) - props.overscan)
  const end = Math.min(props.items.length, indexAt(scrollTop.value + viewHeight.value) + props.overscan + 1)
  const rows = []
  for (let i = start; i < end; i += 1) rows.push({ item: props.items[i], index: i, top: offsets.value[i], height: props.height(props.items[i]) })
  return rows
})

let frame = 0
function onScroll() {
  if (frame) return
  frame = requestAnimationFrame(() => {
    frame = 0
    if (root.value) scrollTop.value = root.value.scrollTop
  })
}

let observer = null
watch(root, (el) => {
  observer?.disconnect()
  if (!el) return
  viewHeight.value = el.clientHeight || 600
  if (typeof ResizeObserver !== 'undefined') {
    observer = new ResizeObserver(() => { viewHeight.value = el.clientHeight || 600 })
    observer.observe(el)
  }
}, { flush: 'post' })
onBeforeUnmount(() => {
  observer?.disconnect()
  cancelAnimationFrame(frame)
})

/** Прокрутить к строке: по центру, если она не видна целиком. */
function scrollToIndex(index, { smooth = true, force = false } = {}) {
  const el = root.value
  if (!el || index < 0 || index >= props.items.length) return
  const top = offsets.value[index]
  const bottom = offsets.value[index + 1]
  if (!force && top >= el.scrollTop && bottom <= el.scrollTop + el.clientHeight) return
  el.scrollTo({ top: Math.max(0, top - (el.clientHeight - (bottom - top)) / 2), behavior: smooth ? 'smooth' : 'auto' })
}

defineExpose({ scrollToIndex, el: root })
</script>

<template>
  <div ref="root" class="vlist scroll-thin" :role="role" :aria-label="label || undefined" tabindex="-1" @scroll="onScroll">
    <div class="vlist-inner" :style="{ height: `${total}px` }">
      <div v-for="row in visible" :key="row.item.key" class="vlist-row" :style="{ transform: `translateY(${row.top}px)`, height: `${row.height}px` }">
        <slot :item="row.item" :index="row.index" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.vlist { position: relative; overflow-y: auto; overflow-x: hidden; outline: none; overscroll-behavior: contain; }
.vlist-inner { position: relative; width: 100%; }
.vlist-row { position: absolute; top: 0; left: 0; right: 0; }
</style>
