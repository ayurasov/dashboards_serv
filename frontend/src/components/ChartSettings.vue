<template>
  <div class="cgear" ref="root">
    <button class="cgear-btn" type="button" title="Настройки графика" @click="open = !open">⚙</button>
    <div v-if="open" class="cpop">
      <div class="cpop-hd"><span>Настройки графика</span></div>

      <div v-if="switchable" class="cpop-row">
        <label>Тип</label>
        <select class="cfsel" v-model="draft.type" @change="emitChange">
          <option value="">По умолчанию</option>
          <option v-for="t in CHART_TYPES" :key="t.value" :value="t.value">{{ t.label }}</option>
        </select>
      </div>

      <div v-if="colorCount" class="cpop-row">
        <label>Цвета</label>
        <div class="cpop-colors">
          <input v-for="(c, i) in draft.colors" :key="i" type="color"
                 :value="c" @input="setColor(i, $event.target.value)">
        </div>
      </div>

      <div class="cpop-row">
        <label>Легенда</label>
        <input type="checkbox" v-model="draft.legend" @change="emitChange">
        <select class="cfsel" v-model="draft.legendPos" :disabled="!draft.legend" @change="emitChange">
          <option v-for="p in LEGEND_POSITIONS" :key="p.value" :value="p.value">{{ p.label }}</option>
        </select>
      </div>

      <div class="cpop-row">
        <label>Высота</label>
        <input type="range" :min="HEIGHT_MIN" :max="HEIGHT_MAX" step="10"
               v-model.number="draft.height" @change="emitChange">
        <span class="cpop-val">{{ draft.height }}</span>
      </div>

      <div class="cpop-ft">
        <button class="btn btn-g" type="button" @click="reset">Сбросить</button>
        <button class="btn btn-g" type="button" @click="open = false">Закрыть</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted, onUnmounted } from 'vue'
import {
  CHART_TYPES, LEGEND_POSITIONS, HEIGHT_MIN, HEIGHT_MAX,
  isSwitchable, seriesColorCount,
} from '../composables/useChartSettings.js'

const props = defineProps({
  settings: { type: Object, default: () => ({}) },
  option: { type: Object, default: null },
  defaultHeight: { type: Number, default: 240 },
  defaultColors: { type: Array, default: () => [] },
})

const emit = defineEmits(['update'])

const open = ref(false)
const root = ref(null)

const switchable = computed(() => isSwitchable(props.option))
const colorCount = computed(() => seriesColorCount(props.option))

const draft = reactive({ type: '', colors: [], legend: true, legendPos: 'bottom', height: props.defaultHeight })

function fillColors() {
  const saved = props.settings.colors || []
  const out = []
  for (let i = 0; i < colorCount.value; i++) {
    out.push(saved[i] || props.defaultColors[i % (props.defaultColors.length || 1)] || '#6b2fa0')
  }
  draft.colors = out
}

function syncFromProps() {
  draft.type = props.settings.type || ''
  draft.legend = props.settings.legend !== false
  draft.legendPos = props.settings.legendPos || 'bottom'
  draft.height = props.settings.height || props.defaultHeight
  fillColors()
}

syncFromProps()
watch(() => props.settings, syncFromProps, { deep: true })
watch(colorCount, fillColors)

function payload() {
  const out = { legend: draft.legend, legendPos: draft.legendPos, height: draft.height }
  if (draft.type) out.type = draft.type
  if (draft.colors.length) out.colors = [...draft.colors]
  return out
}

function emitChange() { emit('update', payload()) }

function setColor(i, value) {
  draft.colors[i] = value
  emitChange()
}

function reset() {
  emit('update', {})
  open.value = false
}

function onDocClick(ev) {
  if (open.value && root.value && !root.value.contains(ev.target)) open.value = false
}

onMounted(() => document.addEventListener('click', onDocClick))
onUnmounted(() => document.removeEventListener('click', onDocClick))
</script>
