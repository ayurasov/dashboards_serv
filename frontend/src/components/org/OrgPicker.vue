<script setup>
import { computed, nextTick, ref } from 'vue'
import OrgAvatar from './OrgAvatar.vue'
import OrgIcon from './OrgIcon.vue'
import { normalize } from '@/domain/org'

/**
 * Выбор из длинного списка с поиском (подразделение, сотрудник). Список раскрывается под полем,
 * в потоке страницы — поэтому работает и в прокручиваемой панели, и в модальном окне.
 * items: [{ id, label, sub, depth, color, person }].
 */
const props = defineProps({
  modelValue: { type: [Number, String], default: null },
  items: { type: Array, required: true },
  placeholder: { type: String, default: 'Не выбрано' },
  nullLabel: { type: String, default: '' },
  searchPlaceholder: { type: String, default: 'Поиск' },
  limit: { type: Number, default: 60 },
  disabled: { type: Boolean, default: false },
  invalid: { type: Boolean, default: false },
  label: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue'])

const open = ref(false)
const query = ref('')
const active = ref(0)
const search = ref(null)
const listId = `org-picker-${Math.random().toString(36).slice(2, 8)}`

const selected = computed(() => props.items.find((i) => i.id === props.modelValue) || null)
const matches = computed(() => {
  const needle = normalize(query.value)
  const list = needle ? props.items.filter((i) => normalize(`${i.label} ${i.sub || ''}`).includes(needle)) : props.items
  return list
})
const shown = computed(() => {
  const head = props.nullLabel && !query.value ? [{ id: null, label: props.nullLabel, isNull: true }] : []
  return [...head, ...matches.value.slice(0, props.limit)]
})

async function toggle() {
  if (props.disabled) return
  open.value = !open.value
  query.value = ''
  active.value = Math.max(0, shown.value.findIndex((i) => i.id === props.modelValue))
  if (open.value) {
    await nextTick()
    search.value?.focus()
  }
}
function choose(item) {
  emit('update:modelValue', item.id)
  open.value = false
}
function onKey(event) {
  if (event.key === 'ArrowDown') active.value = Math.min(shown.value.length - 1, active.value + 1)
  else if (event.key === 'ArrowUp') active.value = Math.max(0, active.value - 1)
  else if (event.key === 'Enter') { if (shown.value[active.value]) choose(shown.value[active.value]) }
  else if (event.key === 'Escape') open.value = false
  else return
  event.preventDefault()
  event.stopPropagation()
}
</script>

<template>
  <div class="org-picker" :class="{ open, invalid, disabled }">
    <button type="button" class="picker-field" :disabled="disabled" :aria-expanded="open" :aria-controls="listId" :aria-label="label || undefined" @click="toggle">
      <template v-if="selected">
        <OrgAvatar v-if="selected.person" :person="selected.person" :size="22" />
        <span v-else-if="selected.color" class="dot" :style="{ background: selected.color }" />
        <span class="value">{{ selected.label }}</span>
        <small v-if="selected.sub" class="sub">{{ selected.sub }}</small>
      </template>
      <span v-else class="placeholder">{{ modelValue === null && nullLabel ? nullLabel : placeholder }}</span>
      <OrgIcon :name="open ? 'chevron-up' : 'chevron-down'" :size="14" class="chev" />
    </button>
    <div v-if="open" class="drop">
      <label class="search">
        <OrgIcon name="search" :size="14" />
        <input ref="search" v-model="query" type="search" :placeholder="searchPlaceholder" :aria-controls="listId" @keydown="onKey" @input="active = 0" />
      </label>
      <ul :id="listId" class="options scroll-thin" role="listbox">
        <li v-for="(item, i) in shown" :key="item.id ?? 'null'" role="option" :aria-selected="item.id === modelValue"
            class="option" :class="{ active: i === active, current: item.id === modelValue, muted: item.isNull }"
            :style="{ paddingLeft: `${10 + (query ? 0 : (item.depth || 0)) * 14}px` }"
            @mousedown.prevent="choose(item)" @mousemove="active = i">
          <OrgAvatar v-if="item.person" :person="item.person" :size="24" />
          <span v-else-if="item.color" class="dot" :style="{ background: item.color }" />
          <span class="text">
            <span class="value">{{ item.label }}</span>
            <small v-if="item.sub && (query || item.person)">{{ item.sub }}</small>
          </span>
          <OrgIcon v-if="item.id === modelValue" name="check" :size="14" :stroke="2.4" class="tick" />
        </li>
        <li v-if="!shown.length" class="empty">Ничего не найдено</li>
        <li v-else-if="matches.length > limit" class="empty">Показаны первые {{ limit }} из {{ matches.length }} — уточните поиск</li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.org-picker { position: relative; min-width: 0; }
.picker-field {
  display: flex; align-items: center; gap: 8px; width: 100%; height: 34px; padding: 0 10px; border: 1px solid var(--border-strong);
  border-radius: var(--radius); background: var(--surface); color: var(--text); font-size: var(--fs-sm); text-align: left; cursor: pointer;
  transition: border-color var(--t-fast), box-shadow var(--t-fast);
}
.picker-field:hover:not(:disabled) { border-color: var(--faint); }
.picker-field:focus-visible, .open .picker-field { outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px var(--focus); }
.picker-field:disabled { background: var(--surface-2); color: var(--muted); cursor: not-allowed; }
.invalid .picker-field { border-color: var(--light-red); }
.value { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; }
.picker-field .value { flex: 0 1 auto; }
.sub { flex: 1 1 auto; min-width: 0; color: var(--muted); font-size: var(--fs-xs); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.placeholder { flex: 1; color: var(--muted); }
.chev { margin-left: auto; color: var(--muted); }
.dot { width: 8px; height: 8px; flex: 0 0 8px; border-radius: 3px; }
.drop { margin-top: 6px; border: 1px solid var(--border); border-radius: 12px; background: var(--bg-elevated); box-shadow: var(--shadow); overflow: hidden; animation: drop .14s var(--ease); }
.search { display: flex; align-items: center; gap: 8px; padding: 0 10px; height: 36px; border-bottom: 1px solid var(--border); color: var(--muted); }
.search input { flex: 1; min-width: 0; border: 0; outline: 0; background: transparent; color: var(--text); font-size: var(--fs-sm); }
.options { list-style: none; margin: 0; padding: 4px; max-height: 260px; overflow-y: auto; }
.option { display: flex; align-items: center; gap: 9px; min-height: 34px; padding: 5px 10px; border-radius: 8px; cursor: pointer; font-size: var(--fs-sm); }
.option.active { background: var(--surface-3); }
.option.current { font-weight: 600; }
.option.muted .value { color: var(--text-2); font-style: italic; }
.text { display: flex; flex-direction: column; min-width: 0; flex: 1; line-height: 1.3; }
.text small { font-size: var(--fs-xs); color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 400; }
.tick { color: var(--accent); }
.empty { padding: 10px; font-size: var(--fs-xs); color: var(--muted); text-align: center; }
@keyframes drop { from { opacity: 0; transform: translateY(-4px); } }
</style>
