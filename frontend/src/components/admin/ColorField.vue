<script setup>
import { ref, watch } from 'vue'
import { isHexColor } from '@/domain/admin'

/** Цвет: образец с системной палитрой и поле #rrggbb. */
const props = defineProps({
  modelValue: { type: String, required: true },
  label: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue'])
const text = ref(props.modelValue)
watch(() => props.modelValue, (v) => { if (v.toLowerCase() !== text.value.toLowerCase()) text.value = v })

function onText(value) {
  text.value = value
  const v = value.trim().startsWith('#') ? value.trim() : `#${value.trim()}`
  if (isHexColor(v)) emit('update:modelValue', v.toLowerCase())
}
</script>

<template>
  <label class="color-field">
    <span class="swatch" :style="{ background: modelValue }">
      <input type="color" :value="modelValue.length === 7 ? modelValue : '#000000'" :aria-label="label" @input="emit('update:modelValue', $event.target.value)" />
    </span>
    <span class="meta">
      <span class="label">{{ label }}</span>
      <input class="hex" :class="{ invalid: !isHexColor(text.startsWith('#') ? text : `#${text}`) }" :value="text" maxlength="7" spellcheck="false"
             :aria-label="`${label}, код цвета`" @input="onText($event.target.value)" @blur="text = modelValue" />
    </span>
  </label>
</template>

<style scoped>
.color-field { display: flex; align-items: center; gap: 9px; padding: 6px 8px 6px 6px; border: 1px solid var(--border); border-radius: 10px; background: var(--surface); min-width: 0; }
.color-field:focus-within { border-color: var(--accent); box-shadow: 0 0 0 3px var(--focus); }
.swatch { position: relative; width: 30px; height: 30px; flex: 0 0 30px; border-radius: 8px; box-shadow: inset 0 0 0 1px rgba(0, 0, 0, .12); overflow: hidden; cursor: pointer; }
.swatch input { position: absolute; inset: -6px; width: calc(100% + 12px); height: calc(100% + 12px); opacity: 0; cursor: pointer; }
.meta { display: flex; flex-direction: column; min-width: 0; line-height: 1.2; }
.label { font-size: var(--fs-xs); color: var(--muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.hex { width: 76px; padding: 0; border: 0; outline: 0; background: transparent; font-family: var(--font-mono); font-size: var(--fs-sm); color: var(--text); text-transform: lowercase; }
.hex.invalid { color: var(--light-red); }
</style>
