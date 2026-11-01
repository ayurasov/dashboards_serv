<script setup>
import AppIcon from './AppIcon.vue'

/** Панель фильтров страницы: поля в ряд, справа — счётчик и «Сбросить». */
defineProps({
  summary: { type: String, default: '' },
  resettable: { type: Boolean, default: false },
})
const emit = defineEmits(['reset'])
</script>

<template>
  <div class="filter-bar card">
    <div class="fields"><slot /></div>
    <div class="side">
      <span v-if="summary" class="summary">{{ summary }}</span>
      <button v-if="resettable" class="btn btn-ghost btn-sm" type="button" @click="emit('reset')">
        <AppIcon name="refresh" :size="13" />Сбросить
      </button>
      <slot name="side" />
    </div>
  </div>
</template>

<style scoped>
.filter-bar { display: flex; align-items: center; gap: 12px 16px; flex-wrap: wrap; padding: 12px 16px; }
.fields { display: flex; flex-wrap: wrap; align-items: center; gap: 10px 12px; flex: 0 1 auto; min-width: 0; }
.fields :deep(.field) { flex-direction: row; align-items: center; gap: 8px; }
.fields :deep(.field > span) { font-size: var(--fs-xs); text-transform: uppercase; letter-spacing: .05em; color: var(--muted); font-weight: 620; white-space: nowrap; }
.fields :deep(.select), .fields :deep(.input) { height: 32px; width: auto; min-width: 150px; }
/* Длинное значение в списке (название подразделения, направления) не растягивает фильтр на всю строку */
.fields :deep(.select) { max-width: 320px; text-overflow: ellipsis; }
.side { display: flex; align-items: center; gap: 10px; margin-left: auto; }
.summary { font-size: var(--fs-sm); color: var(--muted); white-space: nowrap; }
</style>
