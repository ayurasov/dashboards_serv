<template>
  <div class="modal-overlay" @click.self="$emit('close')">
    <div class="modal">
      <div class="mh"><span class="mt">Настройки дашборда</span><button class="mc" @click="$emit('close')">✕</button></div>
      <div class="dset-hint">Перетащите строку за ⠿, чтобы изменить порядок. Размер — доля ширины экрана.</div>
      <div class="dset">
        <div
          v-for="w in widgets"
          :key="w.key"
          class="dset-row"
          :class="{ dragging: dragKey === w.key, 'drop-target': overKey === w.key }"
          @dragover="dragOver(w.key, $event)"
          @drop="drop(w.key, $event)"
        >
          <span class="whandle" draggable="true" @dragstart="dragStart(w.key, $event)" @dragend="dragEnd">⠿</span>
          <input type="checkbox" v-model="w.visible">
          <span class="dset-lbl">{{ title(w.key) }}</span>
          <select class="cfsel" style="max-width:120px" v-model="w.size">
            <option v-for="s in WIDGET_SIZES" :key="s.value" :value="s.value">{{ s.label }}</option>
          </select>
        </div>
      </div>
      <div class="fac" style="margin-top:16px">
        <button class="btn btn-d" @click="$emit('reset')">Сбросить</button>
        <div class="right">
          <button class="btn btn-g" @click="$emit('close')">Отмена</button>
          <button class="btn btn-p" @click="$emit('save')">Сохранить</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { useDragReorder, WIDGET_SIZES } from '../composables/useWidgetLayout.js'

// `widgets` are the live layout rows, so the checkbox and size select edit them in
// place and the parent only has to persist on save.
const props = defineProps({
  widgets: { type: Array, required: true },
  title: { type: Function, required: true },
})

const emit = defineEmits(['move', 'save', 'reset', 'close'])

const { dragKey, overKey, dragStart, dragOver, drop, dragEnd } =
  useDragReorder((from, to) => emit('move', from, to))
</script>
