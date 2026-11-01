<script setup>
/** Сводка плана загрузки: числа чипами (новые — зелёным, изменения — синим, ошибки — красным). */
defineProps({ chips: { type: Array, required: true } })
</script>

<template>
  <ul class="plan-chips" aria-label="Сводка">
    <li v-for="c in chips" :key="c.label" class="plan-chip" :class="`tone-${c.tone}`"><b class="num">{{ c.value.toLocaleString('ru-RU') }}</b>{{ c.label }}</li>
  </ul>
</template>

<style scoped>
.plan-chips { display: flex; flex-wrap: wrap; gap: 6px; margin: 0; padding: 0; list-style: none; }
.plan-chip { display: inline-flex; align-items: center; gap: 6px; height: 28px; padding: 0 11px; border-radius: var(--radius-pill); background: var(--surface-3); color: var(--text-2); font-size: var(--fs-sm); }
.plan-chip b { color: var(--text); font-weight: 700; }
.tone-green { background: color-mix(in srgb, var(--light-green) 13%, transparent); color: color-mix(in srgb, var(--light-green) 80%, var(--text)); }
.tone-green b { color: var(--light-green); }
.tone-blue { background: color-mix(in srgb, var(--accent) 12%, transparent); color: color-mix(in srgb, var(--accent) 80%, var(--text)); }
.tone-blue b { color: var(--accent); }
.tone-yellow { background: color-mix(in srgb, var(--light-yellow) 15%, transparent); color: color-mix(in srgb, var(--light-yellow) 75%, var(--text)); }
.tone-yellow b { color: color-mix(in srgb, var(--light-yellow) 85%, var(--text)); }
.tone-red { background: color-mix(in srgb, var(--light-red) 12%, transparent); color: var(--light-red); }
.tone-red b { color: var(--light-red); }
</style>
