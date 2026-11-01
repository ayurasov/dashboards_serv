<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import AppIcon from './AppIcon.vue'

/** Модальное окно: Esc и щелчок по фону закрывают, фокус переходит в окно. */
const props = defineProps({
  title: { type: String, required: true },
  subtitle: { type: String, default: '' },
  width: { type: [Number, String], default: 560 },
  closable: { type: Boolean, default: true },
})
const emit = defineEmits(['close'])
const dialog = ref(null)

function onKey(event) {
  if (event.key === 'Escape' && props.closable) emit('close')
}
onMounted(() => {
  document.addEventListener('keydown', onKey)
  document.body.style.overflow = 'hidden'
  dialog.value?.focus()
})
onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKey)
  document.body.style.overflow = ''
})
</script>

<template>
  <Teleport to="body">
    <div class="overlay" @mousedown.self="closable && emit('close')">
      <section ref="dialog" class="dialog" role="dialog" aria-modal="true" tabindex="-1"
               :style="{ width: typeof width === 'number' ? `${width}px` : width }">
        <header class="head">
          <div>
            <h2>{{ title }}</h2>
            <p v-if="subtitle" class="sub">{{ subtitle }}</p>
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
.overlay { position: fixed; inset: 0; z-index: 200; display: grid; place-items: center; padding: 24px; background: var(--overlay); backdrop-filter: blur(3px); animation: fade .15s ease; }
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
</style>
