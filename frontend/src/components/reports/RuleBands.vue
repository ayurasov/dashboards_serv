<script setup>
import { computed } from 'vue'
import { ruleBands } from '@/domain/reports'
import { LIGHT_LABELS } from '@/utils/lights'

/** Полосы светофора правила показателя: зоны по возрастанию значения с границами; противоречие — предупреждением. */
const props = defineProps({
  rule: { type: Object, required: true },
  compact: { type: Boolean, default: false },
})
const result = computed(() => ruleBands(props.rule))
// В компактной шкале — только границы (значения в единицах — в подсказке)
const tick = (text) => (props.compact ? text.replace(/\s*\(.*\)$/u, '') : text)
</script>

<template>
  <div class="bands" :class="{ compact }" :title="result.bands.map((b) => `${LIGHT_LABELS[b.light]}: ${b.text}`).join('\n') || result.empty" data-testid="rule-bands">
    <template v-if="result.bands.length">
      <div class="bar"><span v-for="(b, i) in result.bands" :key="i" :class="b.light" /></div>
      <div class="ticks"><span v-for="(b, i) in result.bands" :key="i" class="num"><b v-if="!compact">{{ LIGHT_LABELS[b.light] }}</b>{{ tick(b.text) }}</span></div>
    </template>
    <template v-else>
      <div class="bar"><span class="none" /></div>
      <div class="ticks"><span class="empty">{{ result.empty }}</span></div>
    </template>
    <p v-if="result.warning && !compact" class="warn">{{ result.warning }}</p>
  </div>
</template>

<style scoped>
.bands { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.bar { display: flex; gap: 2px; height: 8px; }
.compact .bar { height: 5px; }
.bar span { flex: 1; border-radius: 3px; }
.bar .green { background: var(--light-green); }
.bar .yellow { background: var(--light-yellow); }
.bar .red { background: var(--light-red); }
.bar .none { background: repeating-linear-gradient(90deg, var(--border-strong) 0 6px, transparent 6px 10px); }
.ticks { display: flex; gap: 2px; font-size: var(--fs-xs); color: var(--text-2); }
.compact .ticks { font-size: 10px; color: var(--muted); }
.ticks span { flex: 1; min-width: 0; display: flex; flex-direction: column; text-align: center; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ticks b { font-weight: 620; color: var(--muted); font-size: 10.5px; }
.ticks .empty { text-align: left; color: var(--muted); white-space: normal; }
.warn { font-size: var(--fs-xs); color: color-mix(in srgb, var(--light-yellow) 75%, var(--text)); font-weight: 560; }
</style>
