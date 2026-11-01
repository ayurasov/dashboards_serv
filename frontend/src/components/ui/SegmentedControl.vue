<script setup>
/** Переключатель вариантов: [{ value, label }]. */
defineProps({
  modelValue: { type: [String, Number, Boolean], default: null },
  options: { type: Array, required: true },
  size: { type: String, default: 'md' },
})
const emit = defineEmits(['update:modelValue'])
</script>

<template>
  <div class="seg" :class="size" role="radiogroup">
    <button v-for="o in options" :key="String(o.value)" type="button" role="radio" :aria-checked="modelValue === o.value"
            :class="{ active: modelValue === o.value }" :title="o.title || o.label" @click="emit('update:modelValue', o.value)">
      {{ o.label }}
    </button>
  </div>
</template>

<style scoped>
.seg { display: inline-flex; padding: 3px; gap: 2px; border-radius: 10px; background: var(--surface-3); border: 1px solid var(--border); flex-wrap: wrap; }
button { height: 28px; padding: 0 12px; border: 0; border-radius: 7px; background: transparent; color: var(--text-2); font-size: var(--fs-sm); font-weight: 540; cursor: pointer; white-space: nowrap; transition: all var(--t-fast); }
button:hover { color: var(--text); }
button.active { background: var(--bg-elevated); color: var(--text); box-shadow: var(--shadow-sm); font-weight: 600; }
.sm button { height: 24px; padding: 0 9px; font-size: var(--fs-xs); }
</style>
