<script setup>
/** Переключатель «вкл/выкл» (checkbox с ролью switch). */
defineProps({
  modelValue: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  label: { type: String, default: '' },
  title: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue'])
</script>

<template>
  <label class="switch" :class="{ disabled }" :title="title || undefined">
    <input type="checkbox" role="switch" :checked="modelValue" :disabled="disabled" :aria-label="label || title || undefined"
           @change="emit('update:modelValue', $event.target.checked)" />
    <span class="track" aria-hidden="true"><span class="thumb" /></span>
    <span v-if="label || $slots.default" class="text"><slot>{{ label }}</slot></span>
  </label>
</template>

<style scoped>
.switch { position: relative; display: inline-flex; align-items: center; gap: 9px; cursor: pointer; user-select: none; }
.switch.disabled { cursor: not-allowed; opacity: .55; }
input { position: absolute; opacity: 0; width: 1px; height: 1px; }
.track { position: relative; width: 32px; height: 18px; flex: 0 0 32px; border-radius: 99px; background: var(--border-strong); transition: background var(--t-fast); }
.thumb { position: absolute; top: 2px; left: 2px; width: 14px; height: 14px; border-radius: 50%; background: #fff; box-shadow: 0 1px 2px rgba(0, 0, 0, .2); transition: transform var(--t-fast); }
input:checked + .track { background: var(--light-green); }
input:checked + .track .thumb { transform: translateX(14px); }
input:focus-visible + .track { outline: 2px solid var(--focus); outline-offset: 2px; }
.text { font-size: var(--fs-base); color: var(--text); }
</style>
