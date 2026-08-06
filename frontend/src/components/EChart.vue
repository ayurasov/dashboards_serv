<template>
  <div ref="el" :style="{ width: '100%', height: height + 'px' }"></div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  option: { type: Object, required: true },
  height: { type: Number, default: 240 },
  colors: { type: Array, default: null },
})

const emit = defineEmits(['click'])

const el = ref(null)
let chart = null
let observer = null
let raf = 0

function resize() { chart?.resize() }

// The widget grid reflows without a window resize (size change, show/hide, drag),
// so the canvas has to follow its own box rather than the viewport.
function scheduleResize() {
  cancelAnimationFrame(raf)
  raf = requestAnimationFrame(resize)
}

function render() {
  if (!chart) return
  chart.setOption(props.option, true)
  if (props.colors?.length) chart.setOption({ color: props.colors })
}

onMounted(() => {
  chart = echarts.init(el.value)
  chart.on('click', (params) => emit('click', params))
  render()
  observer = new ResizeObserver(scheduleResize)
  observer.observe(el.value)
  window.addEventListener('resize', resize)
})

watch(() => props.option, render, { deep: true })
watch(() => props.colors, render, { deep: true })
// The wrapper's style height is reactive, but ECharts holds its own canvas size.
watch(() => props.height, () => nextTick(resize))

onUnmounted(() => {
  cancelAnimationFrame(raf)
  observer?.disconnect()
  window.removeEventListener('resize', resize)
  chart?.dispose()
})
</script>
