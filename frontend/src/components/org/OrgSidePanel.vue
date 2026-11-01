<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import OrgIcon from './OrgIcon.vue'

/**
 * Боковая панель структуры: справа от схемы, на узком экране — лист снизу. Esc закрывает
 * (если не открыт диалог и фокус не в поле ввода).
 */
defineProps({ label: { type: String, default: 'Подробности' } })
const emit = defineEmits(['close'])
const body = ref(null)
const peek = ref(false)

function onKey(event) {
  if (event.key !== 'Escape' || event.defaultPrevented) return
  const target = event.target
  if (target && ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName) && target.value) return
  if (document.querySelector('[role="dialog"][aria-modal="true"]')) return
  emit('close')
}
onMounted(() => document.addEventListener('keydown', onKey))
onBeforeUnmount(() => document.removeEventListener('keydown', onKey))
defineExpose({ scrollTop: () => body.value?.scrollTo({ top: 0 }) })
</script>

<template>
  <aside class="org-panel card" :class="{ peek }" :aria-label="label" data-testid="org-panel">
    <button type="button" class="grabber" :aria-label="peek ? 'Развернуть панель' : 'Свернуть панель'" @click="peek = !peek" />
    <button type="button" class="close" aria-label="Закрыть панель" title="Закрыть (Esc)" @click="emit('close')">
      <OrgIcon name="x" :size="17" />
    </button>
    <div ref="body" class="panel-body scroll-thin">
      <slot />
    </div>
  </aside>
</template>

<style scoped>
.org-panel { position: relative; display: flex; flex-direction: column; min-height: 0; height: 100%; overflow: hidden; animation: panel-in .2s var(--ease); }
.panel-body { flex: 1; min-height: 0; overflow-y: auto; padding: 20px 20px 24px; }
.close { position: absolute; top: 12px; right: 12px; z-index: 2; width: 32px; height: 32px; display: grid; place-items: center; border: 0; border-radius: 9px; background: transparent; color: var(--muted); cursor: pointer; }
.close:hover { background: var(--surface-3); color: var(--text); }
.close:focus-visible { outline: 2px solid var(--focus); }
.grabber { display: none; }
@keyframes panel-in { from { opacity: 0; transform: translateX(10px); } }
@media (max-width: 900px) {
  .org-panel {
    position: fixed; left: 0; right: 0; bottom: 0; z-index: 70; height: auto; max-height: min(76dvh, 680px);
    border-radius: 18px 18px 0 0; border-bottom: 0; box-shadow: 0 -10px 40px rgba(0, 0, 0, .18); animation: sheet-in .24s var(--ease);
  }
  .org-panel.peek { max-height: 34dvh; }
  .grabber { display: block; width: 64px; height: 20px; margin: 0 auto; padding: 0; border: 0; background: transparent; cursor: pointer; flex: 0 0 auto; position: relative; }
  .grabber::before { content: ''; position: absolute; left: 12px; right: 12px; top: 8px; height: 4px; border-radius: 4px; background: var(--border-strong); }
  .grabber:focus-visible { outline: 2px solid var(--focus); border-radius: 6px; }
  .panel-body { padding: 4px 18px calc(22px + env(safe-area-inset-bottom)); }
  .close { top: 10px; }
  @keyframes sheet-in { from { transform: translateY(40px); opacity: .3; } }
}
</style>
