<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import { isTopModal, popModal, pushModal, restoreFocus, trapFocus } from '@/components/ui/modalStack'

/**
 * Боковая панель карточки: Esc и щелчок по фону закрывают (если поверх не открыт другой диалог),
 * фокус переходит в панель. Ниже модальных окон по z-index — подтверждения открываются поверх.
 */
defineProps({
  title: { type: String, default: '' },
  width: { type: [Number, String], default: 640 },
})
const emit = defineEmits(['close'])
const panel = ref(null)
let token = null
let opener = null

function onKey(event) {
  // Поверх панели открыто подтверждение — клавиши принадлежат ему
  if (!isTopModal(token)) return
  if (event.key === 'Tab') return trapFocus(event, panel.value)
  if (event.key !== 'Escape') return
  const active = document.activeElement
  if (!active || active === document.body || panel.value?.contains(active)) emit('close')
}
onMounted(() => {
  opener = document.activeElement
  token = pushModal()
  document.addEventListener('keydown', onKey)
  panel.value?.focus()
})
onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKey)
  popModal(token)
  restoreFocus(opener)
})
</script>

<template>
  <Teleport to="body">
    <div class="drawer-overlay" @mousedown.self="emit('close')">
      <aside ref="panel" class="drawer" role="dialog" aria-modal="true" :aria-label="title || undefined" tabindex="-1"
             :style="{ width: typeof width === 'number' ? `${width}px` : width }">
        <header class="head">
          <div class="head-main"><slot name="header"><h2>{{ title }}</h2></slot></div>
          <button class="close" type="button" aria-label="Закрыть" @click="emit('close')"><AppIcon name="x" :size="18" /></button>
        </header>
        <slot name="tabs" />
        <div class="body scroll-thin"><slot /></div>
        <footer v-if="$slots.footer" class="foot"><slot name="footer" /></footer>
      </aside>
    </div>
  </Teleport>
</template>

<style scoped>
.drawer-overlay { position: fixed; inset: 0; z-index: 150; display: flex; justify-content: flex-end; background: var(--overlay); backdrop-filter: blur(2px); animation: fade .15s ease; }
.drawer { max-width: 100vw; height: 100%; display: flex; flex-direction: column; background: var(--bg-elevated); border-left: 1px solid var(--border); box-shadow: var(--shadow-lg); outline: none; animation: slide .22s var(--ease); }
.head { display: flex; align-items: flex-start; gap: 12px; padding: 20px 22px 14px; }
.head-main { flex: 1; min-width: 0; }
h2 { font-size: 17px; }
.close { width: 32px; height: 32px; display: grid; place-items: center; border: 0; border-radius: 8px; background: transparent; color: var(--muted); cursor: pointer; }
.close:hover { background: var(--surface-3); color: var(--text); }
.body { flex: 1; min-height: 0; overflow-y: auto; padding: 18px 22px 24px; }
.foot { display: flex; align-items: center; gap: 8px; padding: 14px 22px; border-top: 1px solid var(--border); background: var(--surface-2); }
@keyframes fade { from { opacity: 0; } }
@keyframes slide { from { transform: translateX(24px); opacity: .4; } }
</style>
