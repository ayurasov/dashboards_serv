<script setup>
import { computed, ref } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import AppModal from '@/components/ui/AppModal.vue'
import CodeBlock from '@/components/ui/CodeBlock.vue'
import { toastError } from '@/composables/useToast'
import { curlExample, pingExample } from '@/domain/integrations'
import { writeClipboard } from '@/utils/clipboard'

/** Ключ для входящих вызовов: значение показывается один раз — с копированием и примером вызова. */
const props = defineProps({
  item: { type: Object, required: true },
  reissued: { type: Boolean, default: false },
})
const emit = defineEmits(['close'])
const copied = ref(false)
const origin = typeof window !== 'undefined' ? window.location.origin : ''
const example = computed(() => curlExample({ origin, key: props.item.key }))
const ping = computed(() => pingExample({ origin, key: props.item.key }))

async function copy() {
  if (await writeClipboard(props.item.key)) {
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
  } else {
    toastError('Не удалось скопировать — выделите ключ и скопируйте вручную')
  }
}
</script>

<template>
  <AppModal :title="reissued ? 'Ключ выпущен заново' : 'Ключ выпущен'" :subtitle="item.name" :width="'min(640px, calc(100vw - 24px))'" @close="emit('close')">
    <div class="secret">
      <code class="value" data-testid="one-time-key">{{ item.key }}</code>
      <button class="btn btn-sm" type="button" data-testid="copy-key" @click="copy">
        <AppIcon :name="copied ? 'check' : 'copy'" :size="14" />{{ copied ? 'Скопировано' : 'Копировать' }}
      </button>
    </div>
    <ul class="notes">
      <li><AppIcon name="eye-off" :size="15" />Ключ показывается один раз — после закрытия окна посмотреть его снова нельзя: сохраните его в настройках системы, которая будет отправлять файлы.</li>
      <li v-if="reissued"><AppIcon name="alert" :size="15" />Прежнее значение ключа больше не работает.</li>
      <li><AppIcon name="shield" :size="15" />Области: {{ (item.scope_labels || item.scopes || []).join(', ') }}. Частота вызовов ограничена (по умолчанию — 120 в минуту на ключ).</li>
    </ul>
    <div class="stack ex">
      <CodeBlock :code="example" label="Отправить файл" />
      <CodeBlock :code="ping" label="Проверить ключ" />
    </div>
    <template #footer>
      <button class="btn btn-primary" type="button" data-testid="key-done" @click="emit('close')">Готово, ключ сохранён</button>
    </template>
  </AppModal>
</template>

<style scoped>
.secret { display: flex; align-items: center; gap: 10px; padding: 12px 12px 12px 16px; border-radius: 12px; background: var(--surface-2); border: 1px dashed var(--border-strong); }
.value { flex: 1; min-width: 0; font-family: var(--font-mono); font-size: 14px; font-weight: 600; color: var(--text); user-select: all; word-break: break-all; }
.notes { list-style: none; margin: 14px 0 0; padding: 0; display: flex; flex-direction: column; gap: 8px; font-size: var(--fs-sm); color: var(--text-2); }
.notes li { display: flex; gap: 8px; align-items: flex-start; }
.notes :deep(svg) { flex: 0 0 auto; margin-top: 2px; color: var(--muted); }
.ex { margin-top: 16px; }
</style>
