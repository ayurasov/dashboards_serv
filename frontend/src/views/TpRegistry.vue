<template>
  <div class="tp-registry page-content">
    <div class="page-header">
      <h1 class="page-title">🎧 Реестр обращений ТП</h1>
      <div class="header-controls">
        <input v-model="search" class="search-input" placeholder="Поиск по периоду/году…" />
        <select v-model="selectedYear" class="filter-select">
          <option :value="null">Все годы</option>
          <option v-for="y in years" :key="y" :value="y">{{ y }}</option>
        </select>
        <button v-if="canEdit" class="btn btn-primary btn-sm" @click="openNew">+ Добавить</button>
        <button v-if="canEdit" class="btn btn-secondary btn-sm" @click="triggerImport">📥 Импорт JSON</button>
        <input ref="fileInput" type="file" accept=".json" style="display:none" @change="importJson" />
        <router-link to="/tp" class="btn btn-secondary btn-sm">← Дашборд</router-link>
      </div>
    </div>

    <div v-if="loading" class="loading-state">Загрузка…</div>
    <div v-else-if="error" class="error-banner">{{ error }}</div>

    <div v-else class="table-wrapper">
      <table class="data-table">
        <thead>
          <tr>
            <th>Год</th><th>Неделя</th><th>Период</th>
            <th>В работе</th><th>Новых</th><th>Решено</th>
            <th>Коэф.</th><th>AltOS ч</th><th>AltOff ч</th>
            <th v-if="canEdit">Действия</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in filtered" :key="row.id">
            <td>{{ row.year }}</td>
            <td>{{ row.week }}</td>
            <td>{{ row.period || '—' }}</td>
            <td :class="light('total_in_work', row.total_in_work)">{{ row.total_in_work ?? '—' }}</td>
            <td>{{ row.new_received ?? '—' }}</td>
            <td>{{ row.total_solved_week ?? '—' }}</td>
            <td :class="light('ratio_solved_received', row.ratio_solved_received)">
              {{ row.ratio_solved_received !== null ? Number(row.ratio_solved_received).toFixed(2) : '—' }}
            </td>
            <td :class="light('altos_avg_time', row.altos_avg_time)">{{ row.altos_avg_time ?? '—' }}</td>
            <td :class="light('altoffice_avg_time', row.altoffice_avg_time)">{{ row.altoffice_avg_time ?? '—' }}</td>
            <td v-if="canEdit" class="actions-cell">
              <button class="btn-icon" title="Редактировать" @click="openEdit(row)">✏️</button>
              <button class="btn-icon btn-danger" title="Удалить" @click="remove(row.id)">🗑</button>
            </td>
          </tr>
          <tr v-if="!filtered.length">
            <td :colspan="canEdit ? 10 : 9" class="empty-row">Нет записей</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Modal -->
    <div v-if="modal.open" class="modal-backdrop" @click.self="modal.open = false">
      <div class="modal-card">
        <h2 class="modal-title">{{ modal.id ? 'Редактировать запись' : 'Новая запись' }}</h2>
        <div class="form-grid">
          <label>Год<input v-model.number="modal.data.year" type="number" /></label>
          <label>Неделя<input v-model.number="modal.data.week" type="number" /></label>
          <label>Период<input v-model="modal.data.period" /></label>
          <label>В работе<input v-model.number="modal.data.total_in_work" type="number" /></label>
          <label>Всего (доступность)<input v-model.number="modal.data.avail_total" type="number" /></label>
          <label>Новых обращений<input v-model.number="modal.data.new_received" type="number" /></label>
          <label>Обновлений<input v-model.number="modal.data.renewed" type="number" /></label>
          <label>Решено за неделю<input v-model.number="modal.data.total_solved_week" type="number" /></label>
          <label>Коэф. закрытия<input v-model.number="modal.data.ratio_solved_received" type="number" step="0.01" /></label>
          <label>AltOS ср. время (ч)<input v-model.number="modal.data.altos_avg_time" type="number" /></label>
          <label>AltOffice ср. время (ч)<input v-model.number="modal.data.altoffice_avg_time" type="number" /></label>
          <label>Примечание<input v-model="modal.data.extra" /></label>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="modal.open = false">Отмена</button>
          <button class="btn btn-primary" :disabled="saving" @click="save">
            {{ saving ? 'Сохранение…' : 'Сохранить' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useAuthStore } from '../stores/auth.js'
import { tpApi } from '../api/tp.js'

const rows    = ref([])
const rules   = ref({})
const loading = ref(false)
const saving  = ref(false)
const error   = ref(null)
const search  = ref('')
const selectedYear = ref(null)
const fileInput = ref(null)
const auth    = useAuthStore()

const canEdit = computed(() => auth.role === 'admin' || auth.canEditService?.('tech'))

const modal = ref({ open: false, id: null, data: {} })

const years = computed(() => {
  const s = new Set(rows.value.map(r => r.year).filter(Boolean))
  return [...s].sort((a, b) => b - a)
})

const filtered = computed(() => {
  let list = rows.value
  if (selectedYear.value) list = list.filter(r => r.year === selectedYear.value)
  if (search.value) {
    const q = search.value.toLowerCase()
    list = list.filter(r =>
      String(r.year).includes(q) ||
      String(r.week).includes(q) ||
      (r.period || '').toLowerCase().includes(q)
    )
  }
  return list
})

function light(key, val) {
  const rule = rules.value[key]
  if (!rule || !rule.enabled || val === null || val === undefined) return ''
  const { direction, green, yellow } = rule
  if (direction === 'less') {
    if (val <= green)  return 'cell-green'
    if (val <= yellow) return 'cell-yellow'
    return 'cell-red'
  } else {
    if (val >= green)  return 'cell-green'
    if (val >= yellow) return 'cell-yellow'
    return 'cell-red'
  }
}

function openNew() {
  modal.value = { open: true, id: null, data: { year: new Date().getFullYear(), week: 1 } }
}
function openEdit(row) {
  modal.value = { open: true, id: row.id, data: { ...row } }
}

async function save() {
  saving.value = true
  try {
    if (modal.value.id) {
      await tpApi.updateRow(modal.value.id, modal.value.data)
    } else {
      await tpApi.createRow(modal.value.data)
    }
    modal.value.open = false
    await loadData()
  } catch (e) {
    alert(e.message)
  } finally {
    saving.value = false
  }
}

async function remove(id) {
  if (!confirm('Удалить эту запись?')) return
  await tpApi.deleteRow(id)
  rows.value = rows.value.filter(r => r.id !== id)
}

function triggerImport() { fileInput.value?.click() }
async function importJson(e) {
  const file = e.target.files?.[0]
  if (!file) return
  const text = await file.text()
  const data = JSON.parse(text)
  const list = Array.isArray(data) ? data : data.rows
  if (!list) return alert('Неверный формат файла')
  if (!confirm(`Импортировать ${list.length} строк? Текущие данные будут заменены.`)) return
  await tpApi.bulkImport(list)
  await loadData()
  e.target.value = ''
}

async function loadData() {
  loading.value = true
  error.value = null
  try {
    [rows.value, rules.value] = await Promise.all([tpApi.getRows(), tpApi.getTrafficRules()])
  } catch (e) { error.value = e.message }
  finally { loading.value = false }
}

onMounted(loadData)
</script>

<style scoped>
.tp-registry  { padding: var(--space-6); }
.page-header  { display: flex; align-items: center; justify-content: space-between; margin-bottom: var(--space-5); flex-wrap: wrap; gap: var(--space-3); }
.page-title   { font-size: var(--text-xl); font-weight: 700; }
.header-controls { display: flex; gap: var(--space-2); align-items: center; flex-wrap: wrap; }
.search-input  { padding: var(--space-2) var(--space-3); border: 1px solid var(--color-border); border-radius: var(--radius-md); background: var(--color-surface); color: var(--color-text); font-size: var(--text-sm); width: 200px; }
.filter-select { padding: var(--space-2) var(--space-3); border: 1px solid var(--color-border); border-radius: var(--radius-md); background: var(--color-surface); color: var(--color-text); font-size: var(--text-sm); }

.table-wrapper { overflow-x: auto; border: 1px solid var(--color-border); border-radius: var(--radius-lg); }
.data-table    { width: 100%; border-collapse: collapse; font-size: var(--text-sm); }
.data-table th { background: var(--color-surface-offset); padding: var(--space-3); text-align: left; font-weight: 600; color: var(--color-text-muted); white-space: nowrap; border-bottom: 1px solid var(--color-border); }
.data-table td { padding: var(--space-2) var(--space-3); border-bottom: 1px solid var(--color-divider); font-variant-numeric: tabular-nums; }
.data-table tr:last-child td { border-bottom: none; }
.data-table tr:hover td { background: var(--color-surface-offset); }
.empty-row     { text-align: center; color: var(--color-text-faint); padding: var(--space-10) !important; }

.cell-green  { color: var(--color-success); font-weight: 600; }
.cell-yellow { color: var(--color-gold); font-weight: 600; }
.cell-red    { color: var(--color-notification); font-weight: 600; }

.actions-cell { display: flex; gap: var(--space-1); white-space: nowrap; }
.btn-icon     { background: none; border: none; cursor: pointer; font-size: 1rem; padding: var(--space-1); border-radius: var(--radius-sm); }
.btn-icon:hover { background: var(--color-surface-offset); }

.loading-state { text-align: center; padding: var(--space-16); color: var(--color-text-muted); }
.error-banner  { background: var(--color-error-highlight); color: var(--color-error); padding: var(--space-4); border-radius: var(--radius-md); }

/* Modal */
.modal-backdrop { position: fixed; inset: 0; background: rgba(0,0,0,.4); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.modal-card     { background: var(--color-surface); border-radius: var(--radius-xl); padding: var(--space-8); width: min(640px, 96vw); max-height: 90vh; overflow-y: auto; box-shadow: var(--shadow-lg); }
.modal-title    { font-size: var(--text-lg); font-weight: 700; margin-bottom: var(--space-5); }
.form-grid      { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-4); }
.form-grid label{ display: flex; flex-direction: column; gap: var(--space-1); font-size: var(--text-sm); color: var(--color-text-muted); }
.form-grid input { padding: var(--space-2) var(--space-3); border: 1px solid var(--color-border); border-radius: var(--radius-md); background: var(--color-bg); color: var(--color-text); font-size: var(--text-sm); }
.modal-footer   { display: flex; justify-content: flex-end; gap: var(--space-3); margin-top: var(--space-6); }
</style>
