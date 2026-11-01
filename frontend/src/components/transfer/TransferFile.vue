<script setup>
import { ref } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'

/** Выбор файла: щелчок или перетаскивание; выбранный файл — с размером и «Убрать». */
const props = defineProps({
  modelValue: { type: Object, default: null },
  accept: { type: String, required: true },
  hint: { type: String, default: '' },
  testid: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue'])
const dragging = ref(false)
const input = ref(null)

function set(file) {
  emit('update:modelValue', file || null)
  if (input.value) input.value.value = ''
}
function onDrop(event) {
  dragging.value = false
  set(event.dataTransfer.files?.[0])
}
function size(bytes) {
  if (bytes < 1024) return `${bytes} Б`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toLocaleString('ru-RU', { maximumFractionDigits: 1 })} КБ`
  return `${(bytes / 1024 / 1024).toLocaleString('ru-RU', { maximumFractionDigits: 1 })} МБ`
}
const formats = props.accept.split(',').map((x) => x.trim().replace('.', '').toUpperCase()).join(', ')
</script>

<template>
  <div v-if="modelValue" class="picked">
    <span class="file-icon"><AppIcon name="file" :size="18" /></span>
    <span class="meta"><strong>{{ modelValue.name }}</strong><small>{{ size(modelValue.size) }}</small></span>
    <button type="button" class="btn btn-ghost btn-sm" @click="set(null)"><AppIcon name="x" :size="14" />Убрать</button>
  </div>
  <label v-else class="drop" :class="{ dragging }" @dragover.prevent="dragging = true" @dragleave="dragging = false" @drop.prevent="onDrop">
    <input ref="input" type="file" :accept="accept" class="sr-only" :data-testid="testid || undefined" @change="set($event.target.files?.[0])" />
    <span class="drop-icon"><AppIcon name="upload" :size="18" /></span>
    <span class="meta">
      <strong>Выберите файл или перетащите его сюда</strong>
      <small>{{ hint || formats }}</small>
    </span>
  </label>
</template>

<style scoped>
.drop { display: flex; align-items: center; gap: 14px; padding: 16px 18px; border: 1.5px dashed var(--border-strong); border-radius: 12px; cursor: pointer; color: var(--text-2); transition: border-color var(--t-fast), background var(--t-fast); }
.drop:hover, .drop.dragging { border-color: var(--accent); background: color-mix(in srgb, var(--accent) 5%, transparent); }
.drop:focus-within { border-color: var(--accent); box-shadow: 0 0 0 3px var(--focus); }
.drop-icon, .file-icon { width: 38px; height: 38px; flex: 0 0 38px; display: grid; place-items: center; border-radius: 10px; background: var(--surface-3); color: var(--text-2); }
.file-icon { background: color-mix(in srgb, var(--accent) 12%, transparent); color: var(--accent); }
.meta { display: flex; flex-direction: column; min-width: 0; flex: 1; line-height: 1.35; }
.meta strong { font-size: var(--fs-base); color: var(--text); font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.meta small { font-size: var(--fs-xs); color: var(--muted); }
.picked { display: flex; align-items: center; gap: 14px; padding: 12px 12px 12px 18px; border: 1px solid var(--border); border-radius: 12px; background: var(--surface-2); }
</style>
