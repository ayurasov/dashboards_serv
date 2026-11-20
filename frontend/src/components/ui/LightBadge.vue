<script setup>
import { LIGHT_LABELS } from '@/utils/lights'

/** Метка светофора: точка или точка с подписью. */
defineProps({
  light: { type: String, default: 'gray' },
  label: { type: String, default: '' },
  dot: { type: Boolean, default: false },
})
</script>

<template>
  <span v-if="dot" class="dot" :class="light || 'gray'" :title="label || LIGHT_LABELS[light || 'gray']" />
  <span v-else class="badge" :class="`badge-${light || 'gray'}`">
    <span class="dot" :class="light || 'gray'" />{{ label || LIGHT_LABELS[light || 'gray'] }}
  </span>
</template>

<style scoped>
/*
 * Статус различим и без цвета: норма — круг, внимание — треугольник, критично — ромб
 * (WCAG 1.4.1 «не передавать статус только цветом»; рядом всегда есть подпись или подсказка).
 */
.dot { display: inline-block; width: 8px; height: 8px; flex: 0 0 8px; background: var(--light-gray); }
.dot.green, .dot.gray { border-radius: 50%; }
.dot.green { background: var(--light-green); }
.dot.yellow { background: var(--light-yellow); clip-path: polygon(50% 0, 100% 92%, 0 92%); }
.dot.red { background: var(--light-red); border-radius: 1.5px; transform: rotate(45deg) scale(.82); }
</style>
