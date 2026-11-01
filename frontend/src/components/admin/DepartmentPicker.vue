<script setup>
import AppIcon from '@/components/ui/AppIcon.vue'

/** Выбор нескольких подразделений: чипы-переключатели. */
const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  departments: { type: Array, default: () => [] },
  disabled: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue'])

function toggle(id) {
  const set = new Set(props.modelValue)
  set.has(id) ? set.delete(id) : set.add(id)
  emit('update:modelValue', props.departments.map((d) => d.id).filter((x) => set.has(x)))
}
</script>

<template>
  <div class="picker" role="group">
    <button v-for="d in departments" :key="d.id" type="button" class="chip" :class="{ on: modelValue.includes(d.id) }"
            :aria-pressed="modelValue.includes(d.id)" :disabled="disabled" :title="d.code" @click="toggle(d.id)">
      <AppIcon v-if="modelValue.includes(d.id)" name="check" :size="13" :stroke="2.4" />{{ d.name }}
    </button>
    <span v-if="!departments.length" class="muted empty">Подразделения не заведены — добавьте их в разделе «Подразделения»</span>
  </div>
</template>

<style scoped>
.picker { display: flex; flex-wrap: wrap; gap: 6px; }
.chip { height: 28px; padding: 0 11px; gap: 5px; }
.chip.on { background: var(--brand-soft); border-color: color-mix(in srgb, var(--brand) 40%, var(--border)); color: var(--brand); }
.chip:disabled { opacity: .55; cursor: not-allowed; }
.empty { font-size: var(--fs-sm); }
</style>
