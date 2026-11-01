<script setup>
import { ref } from 'vue'
import AppModal from './AppModal.vue'
import AppIcon from './AppIcon.vue'

/** Настройка дашборда: видимость и порядок блоков. */
const props = defineProps({ items: { type: Array, required: true } })
const emit = defineEmits(['close', 'save', 'reset'])
const draft = ref(props.items.map((b) => ({ ...b })))

function move(index, step) {
  const next = [...draft.value]
  const [item] = next.splice(index, 1)
  next.splice(index + step, 0, item)
  draft.value = next
}
</script>

<template>
  <AppModal title="Настроить дашборд" subtitle="Какие блоки показывать и в каком порядке. Настройка сохраняется для вашей учётной записи." :width="480" @close="emit('close')">
    <ul class="blocks">
      <li v-for="(b, i) in draft" :key="b.key" :class="{ hidden: !b.visible }">
        <label class="check"><input v-model="b.visible" type="checkbox" />{{ b.label }}</label>
        <span class="spacer" />
        <button class="btn btn-icon btn-sm btn-ghost" type="button" :disabled="i === 0" title="Выше" @click="move(i, -1)"><AppIcon name="chevron-up" :size="14" /></button>
        <button class="btn btn-icon btn-sm btn-ghost" type="button" :disabled="i === draft.length - 1" title="Ниже" @click="move(i, 1)"><AppIcon name="chevron-down" :size="14" /></button>
      </li>
    </ul>
    <template #footer>
      <button class="btn btn-ghost" type="button" @click="emit('reset'); emit('close')">По умолчанию</button>
      <span class="spacer" />
      <button class="btn" type="button" @click="emit('close')">Отмена</button>
      <button class="btn btn-primary" type="button" @click="emit('save', draft); emit('close')">Сохранить</button>
    </template>
  </AppModal>
</template>

<style scoped>
.blocks { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 4px; }
.blocks li { display: flex; align-items: center; gap: 6px; padding: 6px 8px 6px 12px; border: 1px solid var(--border); border-radius: 10px; }
.blocks li.hidden { opacity: .6; }
</style>
