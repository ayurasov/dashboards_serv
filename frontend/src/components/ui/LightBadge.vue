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
.dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; flex: 0 0 8px; background: var(--light-gray); }
.dot.green { background: var(--light-green); }
.dot.yellow { background: var(--light-yellow); }
.dot.red { background: var(--light-red); }
</style>
