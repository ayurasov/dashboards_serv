<script setup>
import AppIcon from './AppIcon.vue'
import { dismissToast, toasts } from '@/composables/useToast'

const ICON = { ok: 'check', error: 'alert', info: 'info' }
</script>

<template>
  <div class="toasts" aria-live="polite">
    <TransitionGroup name="toast">
      <div v-for="t in toasts" :key="t.id" class="toast" :class="t.kind" role="status" @click="dismissToast(t.id)">
        <AppIcon :name="ICON[t.kind]" :size="16" :stroke="2.2" />
        <span>{{ t.message }}</span>
      </div>
    </TransitionGroup>
  </div>
</template>

<style scoped>
.toasts { position: fixed; right: 20px; bottom: 20px; z-index: 300; display: flex; flex-direction: column; gap: 8px; max-width: min(420px, calc(100vw - 40px)); }
.toast { display: flex; align-items: flex-start; gap: 10px; padding: 11px 14px; border-radius: 12px; background: var(--bg-elevated); border: 1px solid var(--border); box-shadow: var(--shadow-lg); font-size: var(--fs-sm); cursor: pointer; line-height: 1.4; }
.toast svg { margin-top: 1px; }
.ok svg { color: var(--light-green); }
.error svg { color: var(--light-red); }
.info svg { color: var(--accent); }
.toast-enter-active, .toast-leave-active { transition: all .22s var(--ease); }
.toast-enter-from, .toast-leave-to { opacity: 0; transform: translateY(8px); }
</style>
