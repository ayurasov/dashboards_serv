<script setup>
import { computed } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import SegmentedControl from '@/components/ui/SegmentedControl.vue'
import {
  DATA_CLASS_HINTS, DATA_CLASS_LABELS, DATA_CLASSES, depthOptions, MAX_DRILL_DEPTH, normalizeClasses, ORG_SCOPE_HINTS,
  ORG_SCOPE_SHORT, ORG_SCOPES, toggleClass,
} from '@/domain/access'

/**
 * Поле измерения доступа (ADR-0009): область структуры, классы данных, глубина детализации,
 * исходные записи, выгрузка. Одно и то же поле — в профиле доступа и в личной настройке пользователя.
 */
const props = defineProps({
  dimension: { type: String, required: true },
  modelValue: { type: [String, Number, Boolean, Array, null], default: null },
  disabled: { type: Boolean, default: false },
  maxDepth: { type: Number, default: MAX_DRILL_DEPTH },
  name: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue'])

const SCOPE_OPTIONS = ORG_SCOPES.map((k) => ({ value: k, label: ORG_SCOPE_SHORT[k], title: ORG_SCOPE_HINTS[k] }))
const BOOL_OPTIONS = {
  can_view_records: [{ value: true, label: 'Реестры и списки', title: 'Реестры, списки и дашборды' }, { value: false, label: 'Только дашборды', title: 'Только дашборды и сводки' }],
  can_export: [{ value: true, label: 'Разрешена', title: 'Excel, CSV и PDF' }, { value: false, label: 'Запрещена', title: 'Кнопки выгрузки скрыты' }],
}
const depths = computed(() => depthOptions(props.maxDepth))
const classes = computed(() => normalizeClasses(props.modelValue))

function set(value) {
  if (!props.disabled) emit('update:modelValue', value)
}
function onDepth(event) {
  set(event.target.value === '' ? null : Number(event.target.value))
}
</script>

<template>
  <fieldset class="dim" :disabled="disabled" :data-dimension="dimension">
    <SegmentedControl v-if="dimension === 'org_scope'" :model-value="modelValue" :options="SCOPE_OPTIONS" size="sm" @update:model-value="set" />

    <div v-else-if="dimension === 'data_classes'" class="classes" role="group" aria-label="Классы данных">
      <label v-for="c in DATA_CLASSES" :key="c" class="cls" :class="{ on: classes.includes(c), locked: c === 'operational' }" :title="DATA_CLASS_HINTS[c]">
        <input type="checkbox" :checked="classes.includes(c)" :disabled="disabled || c === 'operational'" @change="set(toggleClass(classes, c))" />
        <AppIcon v-if="c === 'operational'" name="lock" :size="12" />
        <AppIcon v-else-if="classes.includes(c)" name="check" :size="13" :stroke="2.4" />
        {{ DATA_CLASS_LABELS[c] }}
      </label>
    </div>

    <select v-else-if="dimension === 'drill_depth'" class="select select-sm depth" :value="modelValue === null || modelValue === undefined ? '' : modelValue"
            :aria-label="name || 'Глубина детализации'" @change="onDepth">
      <option v-for="o in depths" :key="String(o.value)" :value="o.value === null ? '' : o.value">{{ o.label }}</option>
    </select>

    <SegmentedControl v-else-if="BOOL_OPTIONS[dimension]" :model-value="!!modelValue" :options="BOOL_OPTIONS[dimension]" size="sm" @update:model-value="set" />
  </fieldset>
</template>

<style scoped>
.dim { margin: 0; padding: 0; border: 0; min-width: 0; }
.dim:disabled { opacity: .6; }
.classes { display: flex; flex-wrap: wrap; gap: 6px; }
.cls {
  position: relative; display: inline-flex; align-items: center; gap: 6px; height: 28px; padding: 0 11px; border-radius: var(--radius-pill);
  border: 1px solid var(--border-strong); background: var(--surface); color: var(--text-2); font-size: var(--fs-sm); font-weight: 540; cursor: pointer;
  transition: all var(--t-fast); user-select: none;
}
.cls input { position: absolute; opacity: 0; width: 1px; height: 1px; }
.cls:hover:not(.locked) { border-color: var(--faint); color: var(--text); }
.cls.on { background: var(--brand-soft); border-color: color-mix(in srgb, var(--brand) 38%, var(--border)); color: var(--brand); }
.cls.locked { cursor: default; background: var(--surface-3); border-color: var(--border); color: var(--text-2); }
.cls:has(input:focus-visible) { outline: 2px solid var(--focus); outline-offset: 2px; }
.depth { width: auto; min-width: 230px; max-width: 100%; }
</style>
