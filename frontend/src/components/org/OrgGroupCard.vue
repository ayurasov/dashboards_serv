<script setup>
import OrgIcon from './OrgIcon.vue'
import { PEOPLE_FORMS, countText } from '@/domain/org'

/** Группа на схеме «Люди»: сотрудники без руководителя и без подчинённых. */
defineProps({
  count: { type: Number, required: true },
  expanded: { type: Boolean, default: false },
})
const emit = defineEmits(['toggle'])
</script>

<template>
  <button type="button" class="group-card" :aria-expanded="expanded" @click="emit('toggle')">
    <span class="g-icon"><OrgIcon name="users" :size="16" /></span>
    <span class="text">
      <strong>Вне подчинения</strong>
      <small>{{ countText(count, PEOPLE_FORMS) }} без руководителя и подчинённых</small>
    </span>
    <OrgIcon :name="expanded ? 'chevron-up' : 'chevron-down'" :size="14" :stroke="2.2" class="chev" />
  </button>
</template>

<style scoped>
.group-card {
  width: 236px; display: flex; align-items: center; gap: 10px; padding: 12px 13px; text-align: left; cursor: pointer;
  border: 1.5px dashed var(--border-strong); border-radius: 14px; background: color-mix(in srgb, var(--surface) 70%, transparent);
  color: var(--text); transition: border-color var(--t-fast), background var(--t-fast);
}
.group-card:hover { border-color: var(--faint); background: var(--surface); }
.group-card:focus-visible { outline: none; box-shadow: 0 0 0 3px var(--focus); }
.g-icon { width: 32px; height: 32px; flex: 0 0 32px; display: grid; place-items: center; border-radius: 10px; background: var(--surface-3); color: var(--text-2); }
.text { display: flex; flex-direction: column; flex: 1; min-width: 0; line-height: 1.3; }
.text strong { font-size: var(--fs-sm); font-weight: 640; }
.text small { font-size: var(--fs-xs); color: var(--muted); }
.chev { color: var(--muted); }
</style>
