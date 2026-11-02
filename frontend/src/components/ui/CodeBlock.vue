<script setup>
import { ref } from 'vue'
import AppIcon from './AppIcon.vue'
import { toastError } from '@/composables/useToast'
import { writeClipboard } from '@/utils/clipboard'

/**
 * Пример кода или команды моноширинным шрифтом с кнопкой «Копировать». Кнопка — в своей строке над кодом
 * (с подписью слева): длинная строка прокручивается под ней, а не прячется под кнопкой.
 */
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
    <div class="bar">
      <figcaption v-if="label" class="cap">{{ label }}</figcaption>
      <button class="copy btn btn-sm btn-ghost" type="button" :aria-label="copied ? 'Скопировано' : `Копировать${label ? `: ${label}` : ''}`" @click="copy">
        <AppIcon :name="copied ? 'check' : 'copy'" :size="13" />{{ copied ? 'Скопировано' : 'Копировать' }}
      </button>
    </div>
    <pre class="scroll-thin" tabindex="0" :aria-label="label || 'Пример'"><code>{{ code }}</code></pre>
  </figure>
</template>

<style scoped>
.code-block { margin: 0; min-width: 0; display: flex; flex-direction: column; gap: 4px; }
.bar { display: flex; align-items: center; gap: 8px; min-height: 28px; }
.cap { flex: 1; min-width: 0; font-size: var(--fs-xs); font-weight: 620; color: var(--muted); text-transform: uppercase; letter-spacing: .05em; overflow-wrap: anywhere; }
.copy { margin-left: auto; flex: 0 0 auto; white-space: nowrap; }
pre { margin: 0; padding: 12px 14px; overflow-x: auto; border-radius: var(--radius); border: 1px solid var(--border); background: var(--surface-2); color: var(--text); font-family: var(--font-mono); font-size: 12px; line-height: 1.55; white-space: pre; }
pre:focus-visible { outline: 2px solid var(--focus); outline-offset: 1px; }
</style>
