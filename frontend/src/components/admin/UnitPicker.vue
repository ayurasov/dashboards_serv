<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'

/**
 * Выбор подразделения структуры с поиском: одно (modelValue — id или null) или несколько
 * (multiple, modelValue — массив id). Подразделения — плоский список /api/departments в порядке
 * дерева (родители раньше вложенных) с путями; в списке — отступ по уровню и путь до подразделения.
 */
const props = defineProps({
  modelValue: { type: [Number, Array, null], default: null },
  departments: { type: Array, default: () => [] },
  multiple: { type: Boolean, default: false },
  /** Вариант «Без подразделения» в одиночном выборе. */
  noneLabel: { type: String, default: 'Без подразделения' },
  placeholder: { type: String, default: 'Выберите подразделение' },
  exclude: { type: Array, default: () => [] },
  disabled: { type: Boolean, default: false },
  invalid: { type: Boolean, default: false },
  label: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue'])

const open = ref(false)
const query = ref('')
const root = ref(null)
const search = ref(null)
const active = ref(-1)

const byId = computed(() => new Map(props.departments.map((d) => [d.id, d])))
const selectedIds = computed(() => (props.multiple ? props.modelValue || [] : props.modelValue ? [props.modelValue] : []))
const selected = computed(() => selectedIds.value.map((id) => byId.value.get(id)).filter(Boolean))
const single = computed(() => (props.multiple ? null : selected.value[0] || null))

const parentPath = (d) => String(d.path || d.name).split(' / ').slice(0, -1).join(' / ')
const options = computed(() => {
  const needle = query.value.trim().toLocaleLowerCase('ru')
  return props.departments
    .filter((d) => !props.exclude.includes(d.id))
    .filter((d) => !needle || String(d.path || d.name).toLocaleLowerCase('ru').includes(needle) || String(d.code || '').toLocaleLowerCase('ru').includes(needle))
    .map((d) => ({ ...d, parent: parentPath(d), depth: Math.max(0, (d.level || 1) - 1) }))
})
const showNone = computed(() => !props.multiple && !query.value.trim())

function toggleOpen() {
  if (props.disabled) return
  open.value ? close() : openMenu()
}
function openMenu() {
  open.value = true
  query.value = ''
  active.value = -1
  nextTick(() => search.value?.focus())
}
function close() {
  open.value = false
}
function pick(id) {
  if (props.multiple) {
    const set = new Set(selectedIds.value)
    set.has(id) ? set.delete(id) : set.add(id)
    // Порядок — как в дереве
    emit('update:modelValue', props.departments.map((d) => d.id).filter((x) => set.has(x)))
  } else {
    emit('update:modelValue', id)
    close()
  }
}
function remove(id) {
  emit('update:modelValue', selectedIds.value.filter((x) => x !== id))
}
function onKey(event) {
  const count = options.value.length
  if (event.key === 'ArrowDown') { event.preventDefault(); active.value = Math.min(count - 1, active.value + 1) }
  else if (event.key === 'ArrowUp') { event.preventDefault(); active.value = Math.max(-1, active.value - 1) }
  else if (event.key === 'Enter') {
    event.preventDefault()
    if (active.value >= 0 && options.value[active.value]) pick(options.value[active.value].id)
    else if (count === 1) pick(options.value[0].id)
  }
}
function onDocument(event) {
  if (root.value && !root.value.contains(event.target)) close()
}
watch(open, (value) => {
  if (value) document.addEventListener('mousedown', onDocument)
  else document.removeEventListener('mousedown', onDocument)
})
watch(query, () => { active.value = -1 })
onBeforeUnmount(() => document.removeEventListener('mousedown', onDocument))
</script>

<template>
  <div ref="root" class="unit-picker" :class="{ open, disabled, invalid, multiple }" @keydown.esc.stop="close">
    <div v-if="multiple && selected.length" class="tags">
      <span v-for="d in selected" :key="d.id" class="tag" :title="d.path">
        <AppIcon name="building" :size="12" />
        <span class="tag-text"><b>{{ d.name }}</b><small v-if="parentPath(d)">{{ parentPath(d) }}</small></span>
        <button v-if="!disabled" type="button" class="tag-x" :aria-label="`Убрать: ${d.name}`" @click="remove(d.id)"><AppIcon name="x" :size="12" /></button>
      </span>
    </div>
    <button type="button" class="control" :disabled="disabled" :aria-expanded="open" aria-haspopup="listbox" :aria-label="label || placeholder" @click="toggleOpen">
      <template v-if="multiple">
        <AppIcon name="plus" :size="14" class="lead" />
        <span class="ph">{{ selected.length ? 'Добавить подразделение' : placeholder }}</span>
      </template>
      <template v-else-if="single">
        <AppIcon name="building" :size="14" class="lead" />
        <span class="value"><b>{{ single.name }}</b><small v-if="parentPath(single)">{{ parentPath(single) }}</small></span>
      </template>
      <template v-else>
        <AppIcon name="building" :size="14" class="lead" />
        <span class="ph">{{ modelValue === null && noneLabel ? noneLabel : placeholder }}</span>
      </template>
      <AppIcon name="chevron-down" :size="14" class="chev" />
    </button>

    <div v-if="open" class="menu" role="listbox" :aria-multiselectable="multiple || undefined">
      <label class="find">
        <AppIcon name="search" :size="14" />
        <input ref="search" v-model="query" type="search" placeholder="Найти по названию или пути" aria-label="Найти подразделение" @keydown="onKey" />
      </label>
      <div class="options scroll-thin">
        <button v-if="showNone && noneLabel" type="button" role="option" class="option none" :aria-selected="modelValue === null" @click="pick(null)">
          <span class="check"><AppIcon v-if="modelValue === null" name="check" :size="13" :stroke="2.4" /></span>
          <span class="o-text"><b>{{ noneLabel }}</b></span>
        </button>
        <button v-for="(d, i) in options" :key="d.id" type="button" role="option" class="option" :class="{ active: i === active }"
                :aria-selected="selectedIds.includes(d.id)" :style="{ '--depth': query ? 0 : d.depth }" @click="pick(d.id)" @mouseenter="active = i">
          <span class="check"><AppIcon v-if="selectedIds.includes(d.id)" name="check" :size="13" :stroke="2.4" /></span>
          <span class="o-text"><b>{{ d.name }}</b><small v-if="query && d.parent">{{ d.parent }}</small></span>
          <span v-if="d.employee_count" class="count num" :title="`Сотрудников: ${d.employee_count}`">{{ d.employee_count }}</span>
        </button>
        <p v-if="!options.length" class="empty">{{ departments.length ? 'Ничего не найдено' : 'Подразделения ещё не заведены — добавьте их в разделе «Подразделения»' }}</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.unit-picker { position: relative; display: flex; flex-direction: column; gap: 6px; min-width: 0; font-weight: 400; color: var(--text); font-size: var(--fs-base); }
.control {
  display: flex; align-items: center; gap: 8px; width: 100%; min-height: 34px; padding: 4px 10px; text-align: left;
  border: 1px solid var(--border-strong); border-radius: var(--radius); background: var(--surface); color: var(--text); cursor: pointer;
  transition: border-color var(--t-fast), box-shadow var(--t-fast);
}
.control:hover:not(:disabled) { border-color: var(--faint); }
.open .control, .control:focus-visible { outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px var(--focus); }
.invalid .control { border-color: var(--light-red); }
.control:disabled { background: var(--surface-2); color: var(--muted); cursor: not-allowed; border-color: var(--border); }
.multiple .control { border-style: dashed; color: var(--text-2); min-height: 32px; }
.lead { flex: 0 0 auto; color: var(--muted); }
.chev { flex: 0 0 auto; margin-left: auto; color: var(--muted); transition: transform var(--t-fast); }
.open .chev { transform: rotate(180deg); }
.value { display: flex; flex-direction: column; min-width: 0; line-height: 1.25; }
.value b, .tag-text b, .o-text b { font-weight: 560; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.value small, .tag-text small, .o-text small { font-size: var(--fs-xs); color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ph { color: var(--muted); }
.tags { display: flex; flex-direction: column; gap: 4px; }
.tag { display: flex; align-items: center; gap: 8px; padding: 5px 6px 5px 10px; border-radius: var(--radius-sm); background: var(--surface-2); border: 1px solid var(--border); min-width: 0; }
.tag > :deep(svg) { flex: 0 0 auto; color: var(--muted); }
.tag-text { display: flex; flex-direction: column; flex: 1; min-width: 0; line-height: 1.25; }
.tag-x { flex: 0 0 auto; width: 24px; height: 24px; display: grid; place-items: center; border: 0; border-radius: 6px; background: transparent; color: var(--muted); cursor: pointer; }
.tag-x:hover { background: var(--surface-3); color: var(--light-red); }
.menu {
  position: absolute; z-index: 30; left: 0; right: 0; top: calc(100% + 4px); display: flex; flex-direction: column;
  background: var(--bg-elevated); border: 1px solid var(--border); border-radius: var(--radius-lg); box-shadow: var(--shadow-lg); overflow: hidden;
  animation: drop .14s var(--ease);
}
.find { display: flex; align-items: center; gap: 8px; padding: 8px 12px; border-bottom: 1px solid var(--border); color: var(--muted); }
.find input { flex: 1; min-width: 0; border: 0; outline: 0; background: transparent; color: var(--text); font-size: var(--fs-sm); }
.options { max-height: 264px; overflow-y: auto; padding: 4px; display: flex; flex-direction: column; }
.option {
  display: flex; align-items: center; gap: 8px; width: 100%; padding: 6px 10px 6px calc(10px + var(--depth, 0) * 14px);
  border: 0; border-radius: 8px; background: transparent; color: var(--text); text-align: left; cursor: pointer; font-size: var(--fs-sm);
}
.option.active, .option:hover { background: var(--surface-3); }
.option[aria-selected='true'] b { color: var(--brand); }
.option.none { border-bottom: 1px dashed var(--border); border-radius: 8px 8px 0 0; margin-bottom: 2px; }
.check { width: 16px; flex: 0 0 16px; display: grid; place-items: center; color: var(--brand); }
.o-text { display: flex; flex-direction: column; flex: 1; min-width: 0; line-height: 1.3; }
.count { flex: 0 0 auto; font-size: var(--fs-xs); color: var(--faint); }
.empty { padding: 14px 12px; font-size: var(--fs-sm); color: var(--muted); }
@keyframes drop { from { opacity: 0; transform: translateY(-4px); } }
</style>
