<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import EChart from '@/components/charts/EChart.vue'
import { donutOption, useChartTheme } from './TpDashCharts'

/**
 * Кольцевая диаграмма долей с итогом в центре. В широкой карточке легенда справа (имя и доля),
 * в узкой — под кольцом. items: [{ name, value, color }].
 */
const props = defineProps({
  items: { type: Array, required: true },
  unit: { type: String, default: '' },
  total: { type: String, default: null },
  totalLabel: { type: String, default: '' },
  /** Ширина, начиная с которой легенда помещается справа. */
  wideFrom: { type: Number, default: 440 },
})

const root = ref(null)
const width = ref(0)
let observer = null
onMounted(() => {
  observer = new ResizeObserver(([entry]) => { width.value = entry.contentRect.width })
  observer.observe(root.value)
  width.value = root.value.getBoundingClientRect().width
})
onBeforeUnmount(() => observer?.disconnect())

const theme = useChartTheme()
const option = computed(() => donutOption(props.items, {
  unit: props.unit, total: props.total, totalLabel: props.totalLabel, theme: theme.value,
  narrow: width.value > 0 && width.value < props.wideFrom,
}))
</script>

<template>
  <div ref="root" class="donut"><EChart :option="option" /></div>
</template>

<style scoped>
.donut { height: 100%; }
</style>
