<script setup>
import AppIcon from './AppIcon.vue'

/**
 * Вкладки страницы (как в «Импорт и экспорт»): [{ key, label, short?, icon?, count? }]. Стрелки
 * влево и вправо переключают вкладки, на телефоне — короткие подписи.
 */
const props = defineProps({
  modelValue: { type: String, required: true },
  tabs: { type: Array, required: true },
  label: { type: String, default: 'Разделы страницы' },
})
const emit = defineEmits(['update:modelValue'])

function onKey(event, index) {
  if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft') return
  event.preventDefault()
  const next = (index + (event.key === 'ArrowRight' ? 1 : -1) + props.tabs.length) % props.tabs.length
  emit('update:modelValue', props.tabs[next].key)
  event.currentTarget.parentElement?.children[next]?.focus()
}
</script>

<template>
  <nav class="tabs" role="tablist" :aria-label="label">
    <button v-for="(t, i) in tabs" :key="t.key" type="button" role="tab" class="tab" :class="{ active: modelValue === t.key }"
            :aria-selected="modelValue === t.key" :tabindex="modelValue === t.key ? 0 : -1" :data-testid="`tab-${t.key}`"
            @click="emit('update:modelValue', t.key)" @keydown="onKey($event, i)">
      <AppIcon v-if="t.icon" :name="t.icon" :size="15" />
      <span class="full">{{ t.label }}</span><span class="short">{{ t.short || t.label }}</span>
      <span v-if="t.count" class="count num">{{ t.count }}</span>
    </button>
  </nav>
</template>

<style scoped>
.tabs { display: flex; gap: 2px; border-bottom: 1px solid var(--border); overflow-x: auto; scrollbar-width: none; }
.tab {
  position: relative; display: inline-flex; align-items: center; gap: 8px; height: 40px; padding: 0 14px; border: 0; background: transparent;
  color: var(--text-2); font-size: var(--fs-base); font-weight: 560; cursor: pointer; white-space: nowrap; transition: color var(--t-fast);
}
.tab:hover { color: var(--text); }
.tab.active { color: var(--text); font-weight: 640; }
.tab.active::after { content: ''; position: absolute; left: 10px; right: 10px; bottom: -1px; height: 2px; border-radius: 2px; background: var(--brand); }
.tab:focus-visible { outline: 2px solid var(--focus); outline-offset: -2px; border-radius: 8px; }
.count { min-width: 20px; height: 18px; padding: 0 6px; border-radius: 99px; background: var(--surface-3); color: var(--text-2); font-size: 10.5px; font-weight: 650; line-height: 18px; text-align: center; }
.short { display: none; }
@media (max-width: 640px) {
  .tab { padding: 0 10px; gap: 6px; }
  .tab .full { display: none; }
  .tab .short { display: inline; }
}
</style>
