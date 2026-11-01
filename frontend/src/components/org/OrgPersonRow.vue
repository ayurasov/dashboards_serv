<script setup>
import OrgAvatar from './OrgAvatar.vue'

/** Строка сотрудника в панели: аватар, имя, пояснение; щелчок — открыть сотрудника. */
defineProps({
  person: { type: Object, required: true },
  sub: { type: String, default: '' },
  size: { type: Number, default: 32 },
  active: { type: Boolean, default: false },
})
const emit = defineEmits(['select'])
</script>

<template>
  <button type="button" class="person-row" :class="{ active }" @click="emit('select', person.id)">
    <OrgAvatar :person="person" :size="size" />
    <span class="text">
      <span class="name">{{ person.full_name }}<slot name="badge" /></span>
      <small v-if="sub || $slots.sub"><slot name="sub">{{ sub }}</slot></small>
    </span>
    <slot name="aside" />
  </button>
</template>

<style scoped>
.person-row { display: flex; align-items: center; gap: 10px; width: 100%; min-height: 44px; padding: 6px 8px; border: 0; border-radius: 10px; background: transparent; color: var(--text); text-align: left; cursor: pointer; transition: background var(--t-fast); }
.person-row:hover { background: var(--surface-3); }
.person-row.active { background: color-mix(in srgb, var(--accent) 10%, transparent); }
.person-row:focus-visible { outline: 2px solid var(--focus); outline-offset: -2px; }
.text { display: flex; flex-direction: column; min-width: 0; flex: 1; line-height: 1.3; }
.name { display: flex; align-items: center; gap: 6px; font-size: var(--fs-sm); font-weight: 600; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
small { font-size: var(--fs-xs); color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
