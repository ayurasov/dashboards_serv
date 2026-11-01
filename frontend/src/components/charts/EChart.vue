<script setup>
import { onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import { baseOption, echarts, mergeOption } from './echarts'
import { useAppStore } from '@/stores/app'
import { usePaletteStore } from '@/stores/palette'

/** Обёртка ECharts: тема из токенов, перерисовка при смене темы и палитры, подстройка под размер. */
const props = defineProps({
  option: { type: Object, required: true },
  height: { type: [Number, String], default: '100%' },
})
const emit = defineEmits(['click'])

const el = ref(null)
const chart = shallowRef(null)
const app = useAppStore()
const palette = usePaletteStore()
let observer = null

function render() {
  if (!chart.value) return
  const base = baseOption()
  const series = [].concat(props.option.series || [])
  if (series.length && series.every((s) => s.type === 'pie')) {
    // У круговых диаграмм нет осей и сетки
    delete base.xAxis
    delete base.yAxis
    delete base.grid
    base.tooltip = { ...base.tooltip, trigger: 'item' }
  }
  chart.value.setOption(mergeOption(base, props.option), { notMerge: true })
}

onMounted(() => {
  chart.value = echarts.init(el.value, null, { renderer: 'canvas' })
  chart.value.on('click', (params) => emit('click', params))
  render()
  observer = new ResizeObserver(() => chart.value?.resize())
  observer.observe(el.value)
})

onBeforeUnmount(() => {
  observer?.disconnect()
  chart.value?.dispose()
})

watch(() => props.option, render, { deep: true })
watch(() => [app.resolvedTheme, palette.colors], () => requestAnimationFrame(render), { deep: true })

defineExpose({ chart })
</script>

<template>
  <div ref="el" class="echart" :style="{ height: typeof height === 'number' ? `${height}px` : height }" />
</template>

<style scoped>
.echart { width: 100%; min-height: 120px; }
</style>
