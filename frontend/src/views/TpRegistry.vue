<template>
  <div class="tp-registry">
    <div class="page-header">
      <div class="page-header__left">
        <h1 class="page-title">Реестр недель — ТП</h1>
        <p class="page-subtitle">Все записи еженедельного отчёта</p>
      </div>
      <div class="page-header__right" v-if="canEdit">
        <button class="btn btn-primary" @click="openCreate">+ Добавить неделю</button>
      </div>
    </div>

    <div v-if="loading" class="loading-state">Загрузка...</div>
    <div v-else-if="error" class="error-state">{{ error }}</div>

    <template v-else>
      <!-- Search / filter -->
      <div class="toolbar">
        <input v-model="search" class="input-sm" placeholder="Поиск по периоду..." />
        <select v-model="filterYear" class="select-sm">
          <option value="">Все годы</option>
          <option v-for="y in years" :key="y" :value="y">{{ y }}</option>
        </select>
      </div>

      <!-- Table -->
      <div class="table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>Период</th><th>Год</th><th>Нед.</th>
              <th>В работе</th><th>Доступность</th>
              <th>Новых</th><th>Решено</th><th>Коэф.</th>
              <th>SLA AltOS</th><th>SLA AltOffice</th>
              <th v-if="canEdit">Действия</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in filtered" :key="row.id" @click="openEdit(row)" class="clickable-row">
              <td>{{ row.period || '—' }}</td>
              <td>{{ row.year }}</td>
              <td>{{ row.week }}</td>
              <td class="num">{{ fmt(row.total_in_work) }}</td>
              <td class="num">{{ fmt(row.avail_total) }}</td>
              <td class="num">{{ fmt(row.new_received) }}</td>
              <td class="num">{{ fmt(row.total_solved_week) }}</td>
              <td class="num">{{ fmt(row.ratio_solved_received, 2) }}</td>
              <td class="num">{{ fmt(row.altos_avg_time, 1) }}</td>
              <td class="num">{{ fmt(row.altoffice_avg_time, 1) }}</td>
              <td v-if="canEdit" @click.stop>
                <button class="btn-icon" title="Редактировать" @click="openEdit(row)">✏️</button>
                <button class="btn-icon btn-icon--danger" title="Удалить" @click="deleteRow(row.id)">🗑️</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>

    <!-- Modal -->
    <div v-if="modal.open" class="modal-overlay" @click.self="modal.open = false">
      <div class="modal">
        <h2 class="modal-title">{{ modal.isNew ? 'Новая неделя' : 'Редактировать' }}</h2>
        <div class="modal-body">
          <div class="form-row">
            <label>Год</label>
            <input v-model.number="modal.row.year" type="number" class="input-sm" />
          </div>
          <div class="form-row">
            <label>Неделя</label>
            <input v-model.number="modal.row.week" type="number" class="input-sm" />
          </div>
          <div class="form-row">
            <label>Период</label>
            <input v-model="modal.row.period" class="input-sm" placeholder="2026-W01" />
          </div>
          <div class="form-row">
            <label>В работе</label>
            <input v-model.number="modal.row.total_in_work" type="number" class="input-sm" />
          </div>
          <div class="form-row">
            <label>Доступность</label>
            <input v-model.number="modal.row.avail_total" type="number" class="input-sm" />
          </div>
          <div class="form-row">
            <label>Новых заявок</label>
            <input v-model.number="modal.row.new_received" type="number" class="input-sm" />
          </div>
          <div class="form-row">
            <label>Решено за нед.</label>
            <input v-model.number="modal.row.total_solved_week" type="number" class="input-sm" />
          </div>
          <div class="form-row">
            <label>Коэф. решения</label>
            <input v-model.number="modal.row.ratio_solved_received" type="number" step="0.01" class="input-sm" />
          </div>
          <div class="form-row">
            <label>SLA AltOS (ч.)</label>
            <input v-model.number="modal.row.altos_avg_time" type="number" step="0.1" class="input-sm" />
          </div>
          <div class="form-row">
            <label>SLA AltOffice (ч.)</label>
            <input v-model.number="modal.row.altoffice_avg_time" type="number" step="0.1" class="input-sm" />
          </div>
          <div class="form-row">
            <label>Примечание</label>
            <textarea v-model="modal.row.extra" class="input-sm" rows="3"></textarea>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-ghost" @click="modal.open = false">Отмена</button>
          <button class="btn btn-primary" @click="saveRow">Сохранить</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, reactive } from 'vue'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const apiBase = import.meta.env.VITE_API_URL || ''
const h = () => ({ Authorization: `Bearer ${auth.token}` })

const rows = ref([])
const loading = ref(true)
const error = ref(null)
const search = ref('')
const filterYear = ref('')

const canEdit = computed(() => {
  const level = auth.serviceAccessLevel('tech')
  return auth.role === 'admin' || level === 'edit' || level === 'edit_metrics' || level === 'admin'
})

const modal = reactive({ open: false, isNew: true, row: {} })

async function load() {
  loading.value = true
  error.value = null
  try {
    const res = await fetch(`${apiBase}/api/tp/rows`, { headers: h() })
    if (!res.ok) throw new Error(res.status)
    rows.value = await res.json()
  } catch (e) { error.value = e.message }
  finally { loading.value = false }
}

const years = computed(() => [...new Set(rows.value.map(r => r.year).filter(Boolean))].sort())

const filtered = computed(() => {
  let data = rows.value
  if (filterYear.value) data = data.filter(r => r.year == filterYear.value)
  if (search.value) {
    const q = search.value.toLowerCase()
    data = data.filter(r => String(r.period || '').toLowerCase().includes(q))
  }
  return data
})

function fmt(v, dec = 0) {
  if (v == null) return '—'
  return Number(v).toLocaleString('ru-RU', { maximumFractionDigits: dec })
}

function openCreate() {
  modal.row = {}
  modal.isNew = true
  modal.open = true
}
function openEdit(row) {
  modal.row = { ...row }
  modal.isNew = false
  modal.open = true
}

async function saveRow() {
  try {
    const url = modal.isNew ? `${apiBase}/api/tp/rows` : `${apiBase}/api/tp/rows/${modal.row.id}`
    const method = modal.isNew ? 'POST' : 'PUT'
    const res = await fetch(url, {
      method,
      headers: { ...h(), 'Content-Type': 'application/json' },
      body: JSON.stringify(modal.row),
    })
    if (!res.ok) throw new Error(await res.text())
    modal.open = false
    await load()
  } catch (e) { alert('Ошибка: ' + e.message) }
}

async function deleteRow(id) {
  if (!confirm('Удалить запись?')) return
  await fetch(`${apiBase}/api/tp/rows/${id}`, { method: 'DELETE', headers: h() })
  await load()
}

onMounted(load)
</script>

<style scoped>
.tp-registry { padding: var(--space-6); }
.page-header { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: var(--space-4); margin-bottom: var(--space-5); }
.page-title { font-size: var(--text-xl); font-weight: 700; margin: 0; }
.page-subtitle { font-size: var(--text-sm); color: var(--color-text-muted); margin: 0; }
.loading-state, .error-state { padding: var(--space-12); text-align: center; color: var(--color-text-muted); }
.error-state { color: var(--color-error); }
.toolbar { display: flex; gap: var(--space-3); flex-wrap: wrap; margin-bottom: var(--space-4); }
.input-sm, .select-sm { padding: var(--space-1) var(--space-3); border: 1px solid var(--color-border); border-radius: var(--radius-sm); background: var(--color-surface); color: var(--color-text); font-size: var(--text-sm); }
.table-wrap { overflow-x: auto; }
.data-table { width: 100%; border-collapse: collapse; font-size: var(--text-sm); }
.data-table th { background: var(--color-surface-offset); color: var(--color-text-muted); padding: var(--space-2) var(--space-3); text-align: left; border-bottom: 1px solid var(--color-border); white-space: nowrap; }
.data-table td { padding: var(--space-2) var(--space-3); border-bottom: 1px solid var(--color-divider); }
.clickable-row { cursor: pointer; transition: background var(--transition-interactive); }
.clickable-row:hover { background: var(--color-surface-offset); }
.num { text-align: right; font-variant-numeric: tabular-nums; }
.btn-icon { background: none; border: none; cursor: pointer; padding: var(--space-1); font-size: 1rem; opacity: 0.7; transition: opacity 0.15s; }
.btn-icon:hover { opacity: 1; }
.btn-icon--danger:hover { color: var(--color-error); }
.btn { padding: var(--space-2) var(--space-4); border-radius: var(--radius-md); font-size: var(--text-sm); font-weight: 600; cursor: pointer; border: none; transition: background var(--transition-interactive); }
.btn-primary { background: var(--color-primary); color: #fff; }
.btn-primary:hover { background: var(--color-primary-hover); }
.btn-ghost { background: transparent; color: var(--color-text-muted); border: 1px solid var(--color-border); }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,.4); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.modal { background: var(--color-surface-2); border-radius: var(--radius-xl); padding: var(--space-6); width: min(90vw, 480px); max-height: 90vh; overflow-y: auto; box-shadow: var(--shadow-lg); }
.modal-title { font-size: var(--text-lg); font-weight: 700; margin: 0 0 var(--space-4) 0; }
.modal-body { display: flex; flex-direction: column; gap: var(--space-3); }
.form-row { display: flex; flex-direction: column; gap: var(--space-1); }
.form-row label { font-size: var(--text-sm); color: var(--color-text-muted); }
.form-row input, .form-row textarea { padding: var(--space-2) var(--space-3); border: 1px solid var(--color-border); border-radius: var(--radius-sm); background: var(--color-surface); color: var(--color-text); font-size: var(--text-sm); }
.modal-footer { display: flex; justify-content: flex-end; gap: var(--space-3); margin-top: var(--space-5); }
</style>
