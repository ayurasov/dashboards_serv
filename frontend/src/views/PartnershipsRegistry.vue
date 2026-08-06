<template>
  <div v-if="loading" class="tempty">Загрузка…</div>
  <div v-else-if="error" class="tempty">Ошибка: {{ error }}</div>
  <template v-else>
    <div class="filters">
      <input class="srch" placeholder="Поиск по партнёру, продукту, направлению…" v-model="f.search">
      <button class="btn btn-g" :disabled="!active.length" @click="reset">Сбросить фильтры</button>
      <button class="btn btn-g" @click="exportCsv">↓ CSV</button>
      <button v-if="canEdit" class="btn btn-p" @click="openNew">+ Партнёрство</button>
    </div>

    <div class="tinfo">
      Показано {{ filtered.length }} из {{ rows.length }}
      <span v-if="active.length"> · фильтров: {{ active.length }}</span>
    </div>

    <div class="twrap">
      <div class="tscroll">
        <table>
          <thead>
            <tr>
              <th v-for="c in COLUMNS" :key="c.key" @click="setSort(c.key)">
                {{ c.label }}<span class="smark">{{ sortMark(c.key) }}</span>
              </th>
            </tr>
            <tr class="frow">
              <th v-for="c in COLUMNS" :key="c.key">
                <select v-if="c.options" class="cfsel" v-model="f[c.key]" @click.stop>
                  <option value="">Все</option>
                  <option v-for="o in c.options()" :key="o.value ?? o" :value="o.value ?? o">
                    {{ o.label ?? o }}
                  </option>
                </select>
                <input v-else class="cfin" v-model="f[c.key]" :placeholder="c.ph || '…'" @click.stop>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in filtered" :key="r.id" class="row-click" @click="openEdit(r)">
              <td class="td-p">{{ r.partner }}</td>
              <td>{{ r.product || '—' }}</td>
              <td class="td-muted">{{ r.direction || '—' }}</td>
              <td class="td-muted">{{ r.almi_product || '—' }}</td>
              <td class="td-muted">{{ r.almi_version || '—' }}</td>
              <td><span class="sb" :class="statusClass(r.status)">{{ r.status }}</span></td>
              <td class="td-mono">{{ formatDate(r.cert_date) }}</td>
              <td :class="r.nda ? 'bool-y' : 'bool-n'">{{ r.nda ? '✓' : '—' }}</td>
              <td :class="r.agreement ? 'bool-y' : 'bool-n'">{{ r.agreement ? '✓' : '—' }}</td>
              <td class="td-muted">{{ r.type }}</td>
              <td class="td-muted td-clip" :title="r.comment || ''">{{ r.comment || '—' }}</td>
            </tr>
            <tr v-if="!filtered.length"><td colspan="11" class="tempty">Ничего не найдено</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <partnership-modal
      v-if="editing"
      :model-value="editing"
      :directions="directions"
      :almi-products="almiProducts"
      @close="editing=null"
      @saved="onSaved"
    />
  </template>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import PartnershipModal from '../components/PartnershipModal.vue'
import { api } from '../api/client.js'
import { useAuthStore } from '../stores/auth.js'
import { statusClass, formatDate, PARTNERSHIP_STATUSES } from '../api/partnerships.js'
import { useTableFilters, textMatch } from '../composables/useTableFilters.js'
import { setPdfParams } from '../composables/usePdfExport.js'

const auth = useAuthStore()
const canEdit = computed(() => auth.canEdit)

const loading = ref(true)
const error = ref('')
const rows = ref([])
const editing = ref(null)

const BOOL_OPTIONS = [{ value: 'yes', label: 'Да' }, { value: 'no', label: 'Нет' }]

const uniq = (key) => [...new Set(rows.value.map(r => r[key]).filter(Boolean))]
  .sort((a, b) => a.localeCompare(b, 'ru'))
const statuses = computed(() => {
  const present = new Set(rows.value.map(r => r.status).filter(Boolean))
  return [...PARTNERSHIP_STATUSES.filter(s => present.has(s)),
          ...[...present].filter(s => !PARTNERSHIP_STATUSES.includes(s))]
})
const almiProducts = computed(() => uniq('almi_product'))
const types = computed(() => uniq('type'))
const directions = computed(() => uniq('direction'))

const COLUMNS = [
  { key: 'partner', label: 'Партнёр', ph: 'название' },
  { key: 'product', label: 'Продукт', ph: 'продукт' },
  { key: 'direction', label: 'Направление', options: () => directions.value },
  { key: 'almi_product', label: 'Продукт АЛМИ', options: () => almiProducts.value },
  { key: 'almi_version', label: 'Версия', ph: 'версия' },
  { key: 'status', label: 'Статус', options: () => statuses.value },
  { key: 'cert_date', label: 'Дата серт.', ph: 'год' },
  { key: 'nda', label: 'NDA', options: () => BOOL_OPTIONS },
  { key: 'agreement', label: 'Соглаш.', options: () => BOOL_OPTIONS },
  { key: 'type', label: 'Тип', options: () => types.value },
  { key: 'comment', label: 'Комментарий', ph: 'текст' },
]

const DEFAULTS = { search: '' }
for (const c of COLUMNS) DEFAULTS[c.key] = ''

const { f, setSort, sortMark, reset, active, sortRows } =
  useTableFilters(DEFAULTS, { sortKey: 'partner' })

function boolMatch(value, choice) {
  if (!choice) return true
  return choice === 'yes' ? !!value : !value
}

const filtered = computed(() => {
  const q = f.search.trim().toLowerCase()
  const list = rows.value.filter(r => {
    if (f.status && r.status !== f.status) return false
    if (f.almi_product && r.almi_product !== f.almi_product) return false
    if (f.type && r.type !== f.type) return false
    if (f.direction && r.direction !== f.direction) return false
    if (!boolMatch(r.nda, f.nda) || !boolMatch(r.agreement, f.agreement)) return false
    if (!textMatch(r.partner, f.partner)) return false
    if (!textMatch(r.product, f.product)) return false
    if (!textMatch(r.almi_version, f.almi_version)) return false
    if (!textMatch(formatDate(r.cert_date), f.cert_date) && !textMatch(r.cert_date, f.cert_date)) return false
    if (!textMatch(r.comment, f.comment)) return false
    if (!q) return true
    return [r.partner, r.product, r.direction, r.comment].some(v => v?.toLowerCase().includes(q))
  })
  return sortRows(list)
})

// The topbar PDF button reads these, so its export honours the page filters.
setPdfParams(() => ({
  status: f.status, almi_product: f.almi_product,
  direction: f.direction, type: f.type, search: f.search,
}))

function openNew() { editing.value = {} }
function openEdit(r) { editing.value = { ...r } }

async function load() {
  loading.value = true
  error.value = ''
  try {
    rows.value = await api.get('/partnerships')
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function onSaved() {
  editing.value = null
  load()
}

const CSV_COLS = [
  ['partner', 'Партнёр'], ['product', 'Продукт'], ['direction', 'Направление'],
  ['almi_product', 'Продукт АЛМИ'], ['almi_version', 'Версия'], ['status', 'Статус'],
  ['cert_date', 'Дата сертификата'], ['nda', 'NDA'], ['agreement', 'Соглашение'],
  ['type', 'Тип'], ['bitrix', 'Bitrix'], ['website', 'Сайт'], ['comment', 'Комментарий'],
]

function csvCell(v) {
  if (v === true) return 'да'
  if (v === false) return 'нет'
  return `"${String(v ?? '').replace(/"/g, '""')}"`
}

function exportCsv() {
  const head = CSV_COLS.map(c => c[1]).join(';')
  const body = filtered.value.map(r => CSV_COLS.map(c => csvCell(r[c[0]])).join(';'))
  // BOM so Excel detects UTF-8 for the Cyrillic headers.
  const blob = new Blob(['﻿' + [head, ...body].join('\n')], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `partnerships_${new Date().toISOString().slice(0, 10)}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

onMounted(load)
</script>
