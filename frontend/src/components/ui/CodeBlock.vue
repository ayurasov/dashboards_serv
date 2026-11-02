<script setup>
import { ref } from 'vue'
import AppIcon from './AppIcon.vue'
import { toastError } from '@/composables/useToast'
import { writeClipboard } from '@/utils/clipboard'

/** Пример кода или команды моноширинным шрифтом с кнопкой «Копировать». */
const props = defineProps({
  code: { type: String, required: true },
  label: { type: String, default: '' },
  testid: { type: String, default: '' },
})
const copied = ref(false)

async function copy() {
  if (await writeClipboard(props.code)) {
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
  } else {
    toastError('Не удалось скопировать — выделите текст и скопируйте вручную')
  }
}
</script>

<template>
  <figure class="code-block" :data-testid="testid || undefined">
    <figcaption v-if="label" class="cap">{{ label }}</figcaption>
    <pre class="scroll-thin" tabindex="0" :aria-label="label || 'Пример'"><code>{{ code }}</code></pre>
    <button class="copy btn btn-sm" type="button" :aria-label="copied ? 'Скопировано' : `Копировать${label ? `: ${label}` : ''}`" @click="copy">
      <AppIcon :name="copied ? 'check' : 'copy'" :size="13" />{{ copied ? 'Скопировано' : 'Копировать' }}
    </button>
  </figure>
</template>

<style scoped>
.code-block { position: relative; margin: 0; min-width: 0; }
.cap { margin-bottom: 6px; font-size: var(--fs-xs); font-weight: 620; color: var(--muted); text-transform: uppercase; letter-spacing: .05em; }
pre { margin: 0; padding: 12px 14px; padding-right: 120px; overflow-x: auto; border-radius: var(--radius); border: 1px solid var(--border); background: var(--surface-2); color: var(--text); font-family: var(--font-mono); font-size: 12px; line-height: 1.55; white-space: pre; }
pre:focus-visible { outline: 2px solid var(--focus); outline-offset: 1px; }
.copy { position: absolute; right: 8px; bottom: 8px; background: var(--surface); }
.cap + pre + .copy { bottom: 8px; }
@media (max-width: 560px) {
  pre { padding-right: 14px; padding-bottom: 44px; }
}
</style>
