<script setup>
import AppIcon from '@/components/ui/AppIcon.vue'

/** Итог операции: успех (зелёный), ошибки плана (красный), предупреждение (жёлтый). */
defineProps({
  tone: { type: String, default: 'ok' },
  title: { type: String, required: true },
  text: { type: String, default: '' },
})
const ICONS = { ok: 'check', error: 'alert', warn: 'alert', info: 'info' }
</script>

<template>
  <div class="banner" :class="tone" :role="tone === 'error' ? 'alert' : 'status'">
    <span class="b-icon"><AppIcon :name="ICONS[tone]" :size="16" :stroke="2.2" /></span>
    <div class="b-text">
      <strong>{{ title }}</strong>
      <p v-if="text || $slots.default"><slot>{{ text }}</slot></p>
    </div>
    <slot name="actions" />
  </div>
</template>

<style scoped>
.banner { --tone: var(--light-green); display: flex; align-items: flex-start; gap: 12px; padding: 12px 14px; border-radius: 12px;
  border: 1px solid color-mix(in srgb, var(--tone) 35%, var(--border)); background: color-mix(in srgb, var(--tone) 8%, var(--surface)); }
.banner.error { --tone: var(--light-red); }
.banner.warn { --tone: var(--light-yellow); }
.banner.info { --tone: var(--accent); }
.b-icon { width: 28px; height: 28px; flex: 0 0 28px; display: grid; place-items: center; border-radius: 50%; background: color-mix(in srgb, var(--tone) 16%, transparent); color: color-mix(in srgb, var(--tone) 85%, var(--text)); }
.b-text { flex: 1; min-width: 0; padding-top: 3px; }
.b-text strong { font-size: var(--fs-base); font-weight: 650; }
.b-text p { margin-top: 2px; font-size: var(--fs-sm); color: var(--text-2); line-height: 1.45; }
</style>
