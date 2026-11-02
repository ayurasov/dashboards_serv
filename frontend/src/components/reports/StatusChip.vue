<script setup>
import { computed } from 'vue'
import { LIGHT_LABELS, MISSING_HINT, MISSING_LABEL } from '@/utils/lights'

/**
 * Статус светофора меткой: цветная точка и подпись (цвет никогда не единственный признак).
 * missing — «Нет данных»: обязательное значение не заполнено. size: sm · md · lg.
 */
const props = defineProps({
  status: { type: String, default: 'gray' },
  label: { type: String, default: '' },
  missing: { type: Boolean, default: false },
  size: { type: String, default: 'md' },
})
const tone = computed(() => (props.missing ? 'missing' : props.status || 'gray'))
const text = computed(() => (props.missing ? MISSING_LABEL : props.label || LIGHT_LABELS[props.status || 'gray']))
</script>

<template>
  <span class="status-chip" :class="[`t-${tone}`, size]" :title="missing ? MISSING_HINT : undefined" data-testid="status-chip">
    <i aria-hidden="true" />{{ text }}
  </span>
</template>

<style scoped>
.status-chip {
  --tone: var(--light-gray);
  display: inline-flex; align-items: center; gap: 6px; flex: 0 0 auto; height: 22px; padding: 0 9px 0 8px;
  border-radius: var(--radius-pill); font-size: var(--fs-xs); font-weight: 640; white-space: nowrap; letter-spacing: .01em;
  /* Текст — токен --on-* темы: не ниже 4.5:1 на подложке (src/styles/tokens.css) */
  background: color-mix(in srgb, var(--tone) 14%, transparent); color: var(--on, var(--muted));
}
.status-chip i { width: 7px; height: 7px; flex: 0 0 7px; border-radius: 50%; background: var(--tone); }
.t-green { --tone: var(--light-green); --on: var(--on-green); }
.t-yellow { --tone: var(--light-yellow); --on: var(--on-yellow); }
.t-red { --tone: var(--light-red); --on: var(--on-red); }
.t-gray { background: var(--surface-3); color: var(--muted); }
.t-missing { --tone: var(--light-red); background: transparent; box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--light-red) 55%, transparent); color: var(--on-red); }
.t-missing i { background: transparent; box-shadow: inset 0 0 0 1.6px var(--light-red); }
.sm { height: 19px; padding: 0 7px 0 6px; gap: 5px; font-size: 10.5px; }
.sm i { width: 6px; height: 6px; flex-basis: 6px; }
.lg { height: 28px; padding: 0 12px 0 10px; gap: 8px; font-size: var(--fs-sm); }
.lg i { width: 9px; height: 9px; flex-basis: 9px; }
</style>
