<script setup>
import { computed } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'

/** Иконки структуры компании, которых нет в общем наборе; остальные имена — из AppIcon. */
const EXTRA = {
  'zoom-in': '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5M11 8v6M8 11h6"/>',
  'zoom-out': '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5M8 11h6"/>',
  fit: '<path d="M4 9V5.5A1.5 1.5 0 0 1 5.5 4H9M15 4h3.5A1.5 1.5 0 0 1 20 5.5V9M20 15v3.5a1.5 1.5 0 0 1-1.5 1.5H15M9 20H5.5A1.5 1.5 0 0 1 4 18.5V15"/>',
  star: '<path d="m12 3.6 2.55 5.2 5.7.83-4.13 4.02.98 5.68L12 16.65l-5.1 2.68.98-5.68L3.75 9.63l5.7-.83Z"/>',
  'orient-v': '<rect x="9" y="3" width="6" height="5" rx="1.2"/><rect x="3.5" y="16" width="6" height="5" rx="1.2"/><rect x="14.5" y="16" width="6" height="5" rx="1.2"/><path d="M12 8v4M6.5 16v-4h11v4"/>',
  'orient-h': '<rect x="3" y="9" width="5" height="6" rx="1.2"/><rect x="16" y="3.5" width="5" height="6" rx="1.2"/><rect x="16" y="14.5" width="5" height="6" rx="1.2"/><path d="M8 12h4M16 6.5h-4v11h4"/>',
  stack: '<rect x="3.5" y="3" width="8" height="5" rx="1.2"/><path d="M7.5 8v10.5"/><rect x="12" y="10" width="8.5" height="4" rx="1.2"/><rect x="12" y="16.5" width="8.5" height="4" rx="1.2"/><path d="M7.5 12H12M7.5 18.5H12"/>',
  compact: '<rect x="4" y="4" width="16" height="4.2" rx="1.2"/><rect x="4" y="9.9" width="16" height="4.2" rx="1.2"/><rect x="4" y="15.8" width="16" height="4.2" rx="1.2"/>',
  locate: '<circle cx="12" cy="12" r="7"/><circle cx="12" cy="12" r="2.4"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3"/>',
  'expand-all': '<path d="m7 15 5 5 5-5M7 9l5-5 5 5"/>',
  'collapse-all': '<path d="m7 20 5-5 5 5M7 4l5 5 5-5"/>',
  folder: '<path d="M3.5 7.5a2 2 0 0 1 2-2h3.8l2 2.3h7.2a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2Z"/>',
  link: '<path d="M10 14a4 4 0 0 0 5.66 0l3-3a4 4 0 0 0-5.66-5.66l-1 1"/><path d="M14 10a4 4 0 0 0-5.66 0l-3 3a4 4 0 0 0 5.66 5.66l1-1"/>',
  terminal: '<rect x="3" y="4.5" width="18" height="15" rx="2"/><path d="m7 10 3 2.5L7 15M12.5 15H17"/>',
  'arrow-right': '<path d="M5 12h14M13 6l6 6-6 6"/>',
  clipboard: '<rect x="5.5" y="4.5" width="13" height="16.5" rx="2"/><path d="M9 4.5V3.8A.8.8 0 0 1 9.8 3h4.4a.8.8 0 0 1 .8.8v.7M9 11h6M9 15h4"/>',
  hand: '<path d="M8 13V5.5a1.5 1.5 0 0 1 3 0V12M11 11V4a1.5 1.5 0 0 1 3 0v7M14 11V5.5a1.5 1.5 0 0 1 3 0V13"/><path d="M17 9.5a1.5 1.5 0 0 1 3 0V14a7 7 0 0 1-7 7h-1.2a6 6 0 0 1-4.6-2.1L4.4 15.6a1.5 1.5 0 0 1 2.2-2L8 15"/>',
}

const props = defineProps({
  name: { type: String, required: true },
  size: { type: [Number, String], default: 16 },
  stroke: { type: [Number, String], default: 1.8 },
})
const extra = computed(() => EXTRA[props.name])
</script>

<template>
  <svg v-if="extra" class="icon" :width="size" :height="size" viewBox="0 0 24 24" fill="none" stroke="currentColor"
       :stroke-width="stroke" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" v-html="extra" />
  <AppIcon v-else :name="name" :size="size" :stroke="stroke" />
</template>

<style scoped>
.icon { flex: 0 0 auto; }
</style>
