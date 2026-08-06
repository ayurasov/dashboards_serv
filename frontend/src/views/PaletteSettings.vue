<template>
  <div v-if="loading" class="tempty">Загрузка…</div>
  <div v-else-if="error" class="tempty">Ошибка: {{ error }}</div>
  <template v-else>
    <div class="filters">
      <button class="btn btn-p" @click="openNew">+ Новая палитра</button>
      <button class="btn btn-g" @click="load">Обновить</button>
    </div>

    <div class="fl" style="margin-bottom:8px">Готовые палитры</div>
    <div class="pal-list" style="margin-bottom:24px">
      <div v-for="preset in PRESETS" :key="preset.name" class="pal-card">
        <div class="pal-name">{{ preset.name }}</div>
        <div class="sw-row">
          <span class="sw" :style="{ background: preset.colors.traffic_light.green }" title="Норма"></span>
          <span class="sw" :style="{ background: preset.colors.traffic_light.yellow }" title="Внимание"></span>
          <span class="sw" :style="{ background: preset.colors.traffic_light.red }" title="Критично"></span>
          <span class="sw" :style="{ background: preset.colors.traffic_light.neutral }" title="Нейтральный"></span>
        </div>
        <div class="sw-row">
          <span v-for="(c, i) in preset.colors.charts" :key="i" class="sw" :style="{ background: c }"></span>
        </div>
        <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:auto">
          <button class="btn btn-p" style="font-size:.75rem;padding:3px 8px" @click="applyPreset(preset)">Использовать</button>
        </div>
      </div>
    </div>

    <div class="fl" style="margin-bottom:8px">Сохранённые палитры</div>
    <div class="pal-list">
      <div v-for="p in palettes" :key="p.id" class="pal-card" :class="{ 'is-active': p.is_active }">
        <div class="pal-name">
          {{ p.name }}
          <span v-if="p.is_active" class="sb s-done">активна</span>
        </div>
        <div class="sw-row">
          <span class="sw" :style="{ background: tl(p).green }" title="Норма"></span>
          <span class="sw" :style="{ background: tl(p).yellow }" title="Внимание"></span>
          <span class="sw" :style="{ background: tl(p).red }" title="Критично"></span>
          <span class="sw" :style="{ background: tl(p).neutral }" title="Нейтральный"></span>
        </div>
        <div class="sw-row">
          <span v-for="(c, i) in (p.colors.charts || [])" :key="i" class="sw" :style="{ background: c }"></span>
        </div>
        <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:auto">
          <button class="btn btn-g" style="font-size:.75rem;padding:3px 8px" @click="openEdit(p)">✎ Изменить</button>
          <button v-if="!p.is_active" class="btn btn-g" style="font-size:.75rem;padding:3px 8px" @click="activate(p)">Активировать</button>
          <button v-if="!p.is_active" class="btn btn-d" style="font-size:.75rem;padding:3px 8px" @click="remove(p)">Удалить</button>
        </div>
      </div>
    </div>

    <!-- Editor -->
    <div v-if="form" class="ccard" style="margin-bottom:24px">
      <div class="ctitle">{{ form.id ? 'Редактирование: ' + form.name : 'Новая палитра' }}</div>

      <div class="fgi" style="max-width:320px;margin-bottom:16px">
        <label class="fl">Название</label>
        <input class="fi" v-model="form.name">
      </div>

      <div class="fl" style="margin-bottom:8px">Цвета светофора</div>
      <div class="cpick-grid" style="margin-bottom:20px">
        <div v-for="k in TL_KEYS" :key="k.key" class="cpick">
          <input type="color" v-model="form.colors.traffic_light[k.key]">
          <input class="fi" type="text" v-model="form.colors.traffic_light[k.key]">
          <span style="font-size:.75rem;color:var(--c-muted)">{{ k.label }}</span>
        </div>
      </div>

      <div class="fl" style="margin-bottom:8px">Цвета графиков</div>
      <div class="cpick-grid" style="margin-bottom:12px">
        <div v-for="(c, i) in form.colors.charts" :key="i" class="cpick">
          <input type="color" v-model="form.colors.charts[i]">
          <input class="fi" type="text" v-model="form.colors.charts[i]">
          <button class="btn btn-g" style="padding:2px 7px" title="Удалить" @click="form.colors.charts.splice(i, 1)">✕</button>
        </div>
      </div>
      <button class="btn btn-g" style="font-size:.75rem" @click="form.colors.charts.push('#8899aa')">+ Цвет графика</button>

      <div class="fl" style="margin:20px 0 8px">Предпросмотр</div>
      <div class="kpi-grid" style="margin-bottom:16px">
        <div v-for="pv in PREVIEW" :key="pv.label" class="kpi" :style="{ borderLeft: '3px solid ' + form.colors.traffic_light[pv.key] }">
          <div class="kpi-lbl">{{ pv.label }}</div>
          <div class="kpi-val" :style="{ color: form.colors.traffic_light[pv.key] }">{{ pv.value }}</div>
          <div class="kpi-sub">
            <span class="light-dot" :style="{ background: form.colors.traffic_light[pv.key] }"></span>
            {{ pv.hint }}
          </div>
        </div>
      </div>
      <div class="sw-row" style="margin-bottom:16px">
        <span v-for="(c, i) in form.colors.charts" :key="i" class="sw" :style="{ background: c, width: '38px', height: '18px' }"></span>
      </div>

      <div class="err-msg">{{ formErr }}</div>
      <div class="fac">
        <span></span>
        <div class="right">
          <button class="btn btn-g" @click="form = null">Отмена</button>
          <button class="btn btn-p" :disabled="saving" @click="save">{{ saving ? '…' : 'Сохранить' }}</button>
        </div>
      </div>
    </div>
  </template>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api/client.js'
import { usePaletteStore } from '../stores/palette.js'

const TL_KEYS = [
  { key: 'green', label: 'Норма' },
  { key: 'yellow', label: 'Внимание' },
  { key: 'red', label: 'Критично' },
  { key: 'neutral', label: 'Нейтральный' },
]

const PREVIEW = [
  { key: 'green', label: 'Принятые офферы', value: '100%', hint: 'Норма' },
  { key: 'yellow', label: 'Время закрытия', value: '48 дн.', hint: 'Внимание' },
  { key: 'red', label: 'Текучесть', value: '9,1%', hint: 'Критично' },
  { key: 'neutral', label: 'На адаптации', value: '14', hint: 'Без порога' },
]

const DEFAULT_TL = { green: '#7FAE8A', yellow: '#D8B56D', red: '#D98282', neutral: '#B8BEC7' }
const DEFAULT_CHARTS = ['#6F8FBF', '#8BBE9F', '#D8B56D', '#C99ACD', '#D98282', '#A9B2C3']

// Preset palettes offered to the admin. The hex values here must stay in sync with
// PALETTE_PRESETS in backend/app/seed.py (which seeds each of these as a selectable
// palette row on first run).
const PRESETS = [
  {
    name: 'Мягкая',
    colors: {
      traffic_light: { green: '#5a9e68', yellow: '#c9974a', red: '#c97171', neutral: '#b8bec7' },
      charts: ['#5a9e68', '#6F8FBF', '#c9974a', '#8BBE9F', '#c97171', '#A9B2C3'],
      brand: { primary: '#c0392b', muted: '#6b6a65' },
    },
  },
  {
    name: 'Классическая',
    colors: {
      traffic_light: { green: '#4caf50', yellow: '#ffc107', red: '#f44336', neutral: '#9E9E9E' },
      charts: ['#4caf50', '#1F77B4', '#ffc107', '#8E44AD', '#f44336', '#7F8C8D'],
      brand: { primary: '#f44336', muted: '#6B6A65' },
    },
  },
  {
    name: 'Холодная',
    colors: {
      traffic_light: { green: '#26a69a', yellow: '#42a5f5', red: '#ff7043', neutral: '#8FA3B0' },
      charts: ['#26a69a', '#42a5f5', '#6FB1E0', '#8E7CC3', '#ff7043', '#8FA3B0'],
      brand: { primary: '#26a69a', muted: '#5A6B78' },
    },
  },
  {
    name: 'Контрастная',
    colors: {
      traffic_light: { green: '#2e7d32', yellow: '#ef6c00', red: '#c62828', neutral: '#6E7378' },
      charts: ['#2e7d32', '#0B5FA5', '#ef6c00', '#7B2FA0', '#c62828', '#5A6570'],
      brand: { primary: '#c62828', muted: '#5A6570' },
    },
  },
]

const store = usePaletteStore()
const loading = ref(true)
const saving = ref(false)
const error = ref('')
const formErr = ref('')
const palettes = ref([])
const form = ref(null)

function tl(p) {
  return { ...DEFAULT_TL, ...(p.colors?.traffic_light || {}) }
}

function openNew() {
  formErr.value = ''
  form.value = {
    id: null,
    name: 'Новая палитра',
    scope: 'global',
    module_key: null,
    is_active: false,
    colors: {
      traffic_light: { ...DEFAULT_TL },
      charts: [...DEFAULT_CHARTS],
      brand: { primary: '#C0392B', muted: '#6B6A65' },
    },
  }
}

/** Loads a preset's colours into the editor, as a new (unsaved) palette named
 *  after the preset — the admin can tweak and save it, or activate it as-is. */
function applyPreset(preset) {
  formErr.value = ''
  form.value = {
    id: null,
    name: preset.name,
    scope: 'global',
    module_key: null,
    is_active: false,
    colors: {
      traffic_light: { ...preset.colors.traffic_light },
      charts: [...preset.colors.charts],
      brand: { ...preset.colors.brand },
    },
  }
}

function openEdit(p) {
  formErr.value = ''
  form.value = {
    id: p.id,
    name: p.name,
    scope: p.scope,
    module_key: p.module_key,
    is_active: p.is_active,
    colors: {
      traffic_light: tl(p),
      charts: [...(p.colors?.charts || DEFAULT_CHARTS)],
      brand: { primary: '#C0392B', muted: '#6B6A65', ...(p.colors?.brand || {}) },
    },
  }
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    palettes.value = await api.get('/palette/all')
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function save() {
  if (!form.value.name?.trim()) { formErr.value = 'Укажите название'; return }
  saving.value = true
  formErr.value = ''
  const body = {
    name: form.value.name.trim(),
    scope: form.value.scope || 'global',
    module_key: form.value.module_key,
    colors: form.value.colors,
    is_active: form.value.is_active,
  }
  try {
    if (form.value.id) await store.save(form.value.id, body)
    else await store.create(body)
    form.value = null
    await load()
  } catch (e) {
    formErr.value = e.message
  } finally {
    saving.value = false
  }
}

async function activate(p) {
  try {
    await store.activate(p.id)
    await load()
  } catch (e) {
    error.value = e.message
  }
}

async function remove(p) {
  if (!confirm(`Удалить палитру «${p.name}»?`)) return
  try {
    await api.del(`/palette/${p.id}`)
    if (form.value?.id === p.id) form.value = null
    await load()
  } catch (e) {
    error.value = e.message
  }
}

onMounted(load)
</script>
