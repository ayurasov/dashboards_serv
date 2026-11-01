<script setup>
import { computed } from 'vue'
import EChart from '@/components/charts/EChart.vue'
import { cssVar, lightColor } from '@/components/charts/echarts'
import { trendOption } from '@/domain/reports'
import { useAppStore } from '@/stores/app'
import { usePaletteStore } from '@/stores/palette'

/** Спарклайн показателя за 12 месяцев: точки — цветом статуса, пунктир — цель, красная вертикаль и кольцо — незаполненный месяц. */
const props = defineProps({
  trend: { type: Array, required: true },
  unit: { type: String, default: '' },
  height: { type: Number, default: 56 },
})
const app = useAppStore()
const palette = usePaletteStore()

const option = computed(() => {
  // Цвета из токенов темы и палитры: пересчёт при их смене
  void app.resolvedTheme
  void palette.colors
  return trendOption(props.trend, {
    unit: props.unit,
    colors: { light: lightColor, line: cssVar('--muted', '#7a8293'), target: cssVar('--faint', '#a6adba'), missing: lightColor('red'), surface: cssVar('--surface', '#fff') },
  })
})
const summary = computed(() => props.trend.map((t) => `${t.label}: ${t.missing ? 'не заполнено' : t.value ?? '—'}`).join('; '))
</script>

<template>
  <div class="spark" role="img" :aria-label="`Тренд за 12 месяцев. ${summary}`">
    <EChart class="spark-chart" :option="option" :height="height" />
  </div>
</template>

<style scoped>
.spark { min-width: 0; }
.spark-chart { min-height: 0 !important; }
</style>
