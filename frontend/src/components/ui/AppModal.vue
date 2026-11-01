<script setup>
import { onBeforeUnmount, onMounted, ref, useId } from 'vue'
import AppIcon from './AppIcon.vue'
import { isTopModal, popModal, pushModal, restoreFocus, trapFocus } from './modalStack'

/**
 * Модальное окно: Esc и щелчок по фону закрывают, фокус переходит в окно и не уходит из него по Tab,
 * после закрытия возвращается к элементу, который открыл окно. Название окна — его заголовок.
 */
const props = defineProps({
  title: { type: String, required: true },
  subtitle: { type: String, default: '' },
  width: { type: [Number, String], default: 560 },
  closable: { type: Boolean, default: true },
})
const emit = defineEmits(['close'])
const dialog = ref(null)
const titleId = useId()
const subtitleId = useId()
let token = null
let opener = null

function onKey(event) {
  // Клавиши обрабатывает только верхнее окно: подтверждение поверх формы закрывается само по себе
  if (!isTopModal(token)) return
  if (event.key === 'Escape' && props.closable) emit('close')
  else trapFocus(event, dialog.value)
}
onMounted(() => {
  opener = document.activeElement
  token = pushModal()
  document.addEventListener('keydown', onKey)
  dialog.value?.focus()
})
onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKey)
  popModal(token)
  restoreFocus(opener)
})
</script>

<template>
  <Teleport to="body">
    <div class="overlay" @mousedown.self="closable && emit('close')">
      <section ref="dialog" class="dialog" role="dialog" aria-modal="true" tabindex="-1" :aria-labelledby="titleId" :aria-describedby="subtitle ? subtitleId : undefined"
               :style="{ width: typeof width === 'number' ? `${width}px` : width }">
        <header class="head">
          <div>
            <h2 :id="titleId">{{ title }}</h2>
            <p v-if="subtitle" :id="subtitleId" class="sub">{{ subtitle }}</p>
          </div>
          <button v-if="closable" class="close" type="button" aria-label="Закрыть" @click="emit('close')">
            <AppIcon name="x" :size="18" />
          </button>
        </header>
        <div class="body scroll-thin"><slot /></div>
        <footer v-if="$slots.footer" class="foot"><slot name="footer" /></footer>
      </section>
    </div>
  </Teleport>
</template>

<style scoped>
.overlay { position: fixed; inset: 0; z-index: 200; display: grid; grid-template-columns: minmax(0, 1fr); place-items: center; padding: 24px; background: var(--overlay); backdrop-filter: blur(3px); animation: fade .15s ease; }
.dialog { max-width: 100%; max-height: calc(100vh - 48px); display: flex; flex-direction: column; background: var(--bg-elevated); border: 1px solid var(--border); border-radius: 16px; box-shadow: var(--shadow-lg); outline: none; animation: rise .18s var(--ease); }
.head { display: flex; align-items: flex-start; gap: 12px; padding: 20px 22px 6px; }
.head > div { flex: 1; min-width: 0; }
h2 { font-size: 17px; }
.sub { margin-top: 3px; font-size: var(--fs-sm); color: var(--muted); }
.close { width: 32px; height: 32px; display: grid; place-items: center; border: 0; border-radius: 8px; background: transparent; color: var(--muted); cursor: pointer; }
.close:hover { background: var(--surface-3); color: var(--text); }
.body { padding: 14px 22px 20px; overflow-y: auto; }
.foot { display: flex; justify-content: flex-end; gap: 8px; padding: 14px 22px; border-top: 1px solid var(--border); background: var(--surface-2); border-radius: 0 0 16px 16px; }
@keyframes fade { from { opacity: 0; } }
@keyframes rise { from { opacity: 0; transform: translateY(8px) scale(.99); } }
/* Телефон: окно во всю ширину с небольшим полем; колонка minmax(0, 1fr) не даёт окну шире экрана */
@media (max-width: 560px) { .overlay { padding: 12px; } }
</style>
