<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import OrgAvatar from './OrgAvatar.vue'
import OrgIcon from './OrgIcon.vue'

/**
 * Поиск по структуре: подразделения и люди в выпадающем списке. Стрелки — выбор, Enter — перейти,
 * Esc — закрыть; «/» в любом месте страницы — к поиску.
 */
const props = defineProps({
  modelValue: { type: String, default: '' },
  results: { type: Array, default: () => [] },
  kindOf: { type: Function, default: () => ({ color: 'var(--muted)', label: '' }) },
  placeholder: { type: String, default: 'Поиск по структуре' },
})
const emit = defineEmits(['update:modelValue', 'pick'])

const input = ref(null)
const open = ref(false)
const active = ref(0)
const listId = `org-search-${Math.random().toString(36).slice(2, 8)}`
watch(() => props.results, () => { active.value = 0 })
const showList = computed(() => open.value && props.modelValue.trim().length > 0)

function pick(result) {
  if (!result) return
  open.value = false
  emit('pick', result)
}
function onKey(event) {
  if (event.key === 'ArrowDown') {
    open.value = true
    active.value = Math.min(props.results.length - 1, active.value + 1)
  } else if (event.key === 'ArrowUp') {
    active.value = Math.max(0, active.value - 1)
  } else if (event.key === 'Enter') {
    pick(props.results[active.value])
  } else if (event.key === 'Escape') {
    if (open.value && props.modelValue) open.value = false
    else emit('update:modelValue', '')
  } else return
  event.preventDefault()
}
let blurTimer = null
function onBlur() {
  blurTimer = setTimeout(() => { open.value = false }, 120)
}

/** Подсветка совпадения в названии. */
function parts(title) {
  const q = props.modelValue.trim().toLocaleLowerCase('ru')
  const at = q ? title.toLocaleLowerCase('ru').indexOf(q) : -1
  if (at < 0) return [{ text: title, hit: false }]
  return [
    { text: title.slice(0, at), hit: false },
    { text: title.slice(at, at + q.length), hit: true },
    { text: title.slice(at + q.length), hit: false },
  ].filter((p) => p.text)
}

function onGlobalKey(event) {
  if (event.key !== '/' || event.ctrlKey || event.metaKey || event.altKey) return
  const target = event.target
  if (target && (target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName))) return
  event.preventDefault()
  input.value?.focus()
}
onMounted(() => document.addEventListener('keydown', onGlobalKey))
onBeforeUnmount(() => {
  document.removeEventListener('keydown', onGlobalKey)
  clearTimeout(blurTimer)
})
defineExpose({ focus: () => input.value?.focus() })
</script>

<template>
  <div class="org-search" :class="{ open: showList }">
    <label class="box">
      <OrgIcon name="search" :size="15" />
      <input ref="input" :value="modelValue" type="search" :placeholder="placeholder" aria-label="Поиск по структуре"
             role="combobox" :aria-expanded="showList" :aria-controls="listId" aria-autocomplete="list"
             :aria-activedescendant="showList && results.length ? `${listId}-${active}` : undefined" autocomplete="off"
             data-testid="org-search"
             @input="emit('update:modelValue', $event.target.value); open = true" @focus="open = true" @blur="onBlur" @keydown="onKey" />
      <kbd v-if="!modelValue" class="kbd hint" aria-hidden="true">/</kbd>
    </label>
    <div v-if="showList" :id="listId" class="results scroll-thin" role="listbox" aria-label="Результаты поиска">
      <button v-for="(r, i) in results" :id="`${listId}-${i}`" :key="`${r.type}-${r.id}`" type="button" role="option"
              class="result" :class="{ active: i === active }" :aria-selected="i === active"
              @mousedown.prevent="pick(r)" @mousemove="active = i">
        <OrgAvatar v-if="r.type === 'person'" :person="r.person" :size="28" />
        <span v-else class="unit-icon" :style="{ '--kind': kindOf(r.kind).color }"><OrgIcon name="folder" :size="15" /></span>
        <span class="text">
          <span class="title"><template v-for="(p, j) in parts(r.title)" :key="j"><mark v-if="p.hit">{{ p.text }}</mark><template v-else>{{ p.text }}</template></template></span>
          <small>
            <template v-if="r.type === 'unit'">{{ kindOf(r.kind).label }}<template v-if="r.subtitle"> · {{ r.subtitle }}</template></template>
            <template v-else>{{ r.subtitle || 'Сотрудник' }}</template>
          </small>
        </span>
        <span v-if="r.inactive" class="badge badge-gray">Отключён</span>
      </button>
      <p v-if="!results.length" class="empty">Ничего не найдено</p>
    </div>
  </div>
</template>

<style scoped>
.org-search { position: relative; flex: 1 1 220px; min-width: 200px; max-width: 360px; }
.box {
  display: flex; align-items: center; gap: 8px; height: 34px; padding: 0 10px; border: 1px solid var(--border-strong);
  border-radius: var(--radius); background: var(--surface); color: var(--muted); cursor: text;
  transition: border-color var(--t-fast), box-shadow var(--t-fast);
}
.box:hover { border-color: var(--faint); }
.box:focus-within { border-color: var(--accent); box-shadow: 0 0 0 3px var(--focus); }
input { flex: 1; min-width: 0; border: 0; outline: 0; background: transparent; color: var(--text); font-size: var(--fs-sm); }
input::-webkit-search-cancel-button { cursor: pointer; }
.hint { color: var(--muted); }
.results {
  position: absolute; top: calc(100% + 6px); left: 0; z-index: 40; width: max(100%, 380px); max-width: calc(100vw - 32px);
  max-height: 380px; overflow-y: auto; padding: 6px; border: 1px solid var(--border); border-radius: 12px;
  background: var(--bg-elevated); box-shadow: var(--shadow-lg); animation: drop .14s var(--ease);
}
.result {
  display: flex; align-items: center; gap: 10px; width: 100%; padding: 7px 8px; border: 0; border-radius: 8px;
  background: transparent; color: var(--text); text-align: left; cursor: pointer;
}
.result.active { background: var(--surface-3); }
.unit-icon { width: 28px; height: 28px; flex: 0 0 28px; display: grid; place-items: center; border-radius: 8px; background: color-mix(in srgb, var(--kind) 14%, var(--surface)); color: color-mix(in srgb, var(--kind) 85%, var(--text)); }
.text { display: flex; flex-direction: column; min-width: 0; flex: 1; line-height: 1.3; }
.title { font-size: var(--fs-sm); font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
mark { background: color-mix(in srgb, var(--light-yellow) 30%, transparent); color: inherit; border-radius: 3px; padding: 0 1px; }
small { font-size: var(--fs-xs); color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.empty { padding: 14px 10px; text-align: center; font-size: var(--fs-sm); color: var(--muted); }
@keyframes drop { from { opacity: 0; transform: translateY(-4px); } }
@media (max-width: 640px) {
  .org-search { max-width: none; flex-basis: 100%; }
  .results { width: 100%; }
  .hint { display: none; }
}
</style>
