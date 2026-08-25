<template>
  <div class="tp-registry">
    <div class="page-header">
      <h1>Реестр данных ТП</h1>
      <div class="hd-actions" v-if="auth.canEdit">
        <label class="btn btn-g">
          <input type="file" accept=".csv" @change="importCsv" style="display:none">
          📥 Импорт CSV
        </label>
        <button class="btn btn-p" @click="openCreate">+ Добавить строку</button>
      </div>
    </div>

    <!-- Filters -->
    <div class="filter-bar">
      <select v-model="filterYear">
        <option value="">Все годы</option>
        <option v-for="y in years" :key="y" :value="y">{{ y }}</option>
      </select>
      <input v-model="search" placeholder="Поиск по периоду…" class="fi" style="width:200px">
    </div>

    <div class="table-wrap">
      <table class="data-table">
        <thead>
          <tr>
            <th>Год</th><th>Неделя</th><th>Период</th>
            <th>В работе</th><th>Доступность</th><th>Решено</th>
            <th>Коэф.</th><th>AltOS ср.вр.</th><th>AltOffice ср.вр.</th>
            <th v-if="auth.canEdit">Действия</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in filteredRows" :key="row.id">
            <td>{{ row.year }}</td>
            <td>{{ row.week }}</td>
            <td>{{ row.period || '—' }}</td>
            <td class="num">{{ fmt(row.total_in_work) }}</td>
            <td class="num">{{ fmt(row.avail_total) }}</td>
            <td class="num">{{ fmt(row.total_solved_week) }}</td>
            <td class="num">{{ fmtDec(row.ratio_solved_received, 2) }}</td>
            <td class="num">{{ fmt(row.altos_avg_time) }}</td>
            <td class="num">{{ fmt(row.altoffice_avg_time) }}</td>
            <td v-if="auth.canEdit" class="actions">
              <button class="btn btn-g" @click="openEdit(row)">✏</button>
              <button class="btn btn-g btn-danger" @click="confirmDelete(row)">🗑</button>
            </td>
          </tr>
          <tr v-if="!filteredRows.length">
            <td :colspan="auth.canEdit ? 10 : 9" style="text-align:center;color:var(--color-text-muted);padding:var(--space-8)">Нет данных</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Modal -->
    <div v-if="showModal" class="modal-overlay" @click.self="showModal=false">
      <div class="modal" style="max-width:760px;max-height:85vh;overflow-y:auto">
        <div class="mh">
          <span class="mt">{{ editRow?.id ? 'Редактировать' : 'Добавить' }} строку</span>
          <button class="mc" @click="showModal=false">✕</button>
        </div>
        <form @submit.prevent="saveRow">
          <div class="form-grid">
            <div class="fgi" v-for="col in formCols" :key="col.key">
              <label class="fl">{{ col.label }}</label>
              <input class="fi" :type="col.type || 'number'" v-model="form[col.key]" :step="col.step || 'any'" style="width:100%">
            </div>
          </div>
          <div class="fac"><span></span>
            <button type="button" class="btn btn-g" @click="showModal=false">Отмена</button>
            <button type="submit" class="btn btn-p">Сохранить</button>
          </div>
        </form>
      </div>
    </div>

    <!-- Delete confirm -->
    <div v-if="deleteTarget" class="modal-overlay" @click.self="deleteTarget=null">
      <div class="modal modal-sm">
        <div class="mh"><span class="mt">Удалить строку?</span><button class="mc" @click="deleteTarget=null">✕</button></div>
        <p style="padding:var(--space-4);color:var(--color-text-muted)">Неделя {{ deleteTarget.week }}, {{ deleteTarget.year }} г. Это действие нельзя отменить.</p>
        <div class="fac" style="padding:var(--space-4)">
          <span></span>
          <button class="btn btn-g" @click="deleteTarget=null">Отмена</button>
          <button class="btn btn-p btn-danger" @click="doDelete">Удалить</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { tpApi } from '../../api/tp.js'
import { useAuthStore } from '../../stores/auth.js'
import { toastOk } from '../../composables/useToast.js'

const auth = useAuthStore()
const rows = ref([])
const loading = ref(false)
const filterYear = ref('')
const search = ref('')
const showModal = ref(false)
const editRow = ref(null)
const deleteTarget = ref(null)
const form = ref({})

const years = computed(() => [...new Set(rows.value.map(r => r.year))].sort((a, b) => a - b))
const filteredRows = computed(() => {
  let r = [...rows.value].sort((a, b) => a.year - b.year || a.week - b.week)
  if (filterYear.value !== '') r = r.filter(x => x.year === Number(filterYear.value))
  if (search.value) r = r.filter(x => String(x.period || '').toLowerCase().includes(search.value.toLowerCase()))
  return r
})

const formCols = [
  { key: 'year', label: 'Год', step: '1' }, { key: 'week', label: 'Неделя', step: '1' },
  { key: 'period', label: 'Период', type: 'text' },
  { key: 'total_in_work', label: 'В работе' }, { key: 'avail_total', label: 'Доступность (всего)' },
  { key: 'rushydro_hours', label: 'РусГидро, ч.' }, { key: 'transneft_hours', label: 'Транснефть, ч.' },
  { key: 'roscosmos_hours', label: 'Роскосмос, ч.' }, { key: 'bryansk_hours', label: 'Брянск, ч.' },
  { key: 'mchs_hours', label: 'МЧС, ч.' }, { key: 'internal_sales_hours', label: 'Внутр. продажи, ч.' },
  { key: 'new_received', label: 'Новых получено' }, { key: 'renewed', label: 'Возобновлено' },
  { key: 'ratio_solved_received', label: 'Коэф. решения' },
  { key: 'altos_rusg_email', label: 'AltOS РусГ Email' }, { key: 'altos_rusg_tf', label: 'AltOS РусГ TF' },
  { key: 'altos_other_email', label: 'AltOS Other Email' }, { key: 'altos_other_tf', label: 'AltOS Other TF' },
  { key: 'altoffice_rusg_email', label: 'AltOffice РусГ Email' }, { key: 'altoffice_rusg_tf', label: 'AltOffice РусГ TF' },
  { key: 'altoffice_other_email', label: 'AltOffice Other Email' }, { key: 'altoffice_other_tf', label: 'AltOffice Other TF' },
  { key: 'projserver_taken', label: 'ПС Принято' }, { key: 'projserver_solved', label: 'ПС Решено' }, { key: 'projserver_avail', label: 'ПС Доступность' },
  { key: 'total_solved_week', label: 'Решено за неделю' },
  { key: 'altos_avg_time', label: 'AltOS ср. время' }, { key: 'altos_total', label: 'AltOS Всего' },
  { key: 'altos_1_2line', label: 'AltOS 1-2 лин.' }, { key: 'altos_3line', label: 'AltOS 3 лин.' },
  { key: 'altoffice_avg_time', label: 'AltOffice ср. время' }, { key: 'altoffice_total', label: 'AltOffice Всего' },
  { key: 'altoffice_1_2line', label: 'AltOffice 1-2 лин.' }, { key: 'altoffice_3line', label: 'AltOffice 3 лин.' },
  { key: 'altos_avail_total', label: 'AltOS Дост. всего' }, { key: 'altos_avail_1_3', label: 'AltOS 1-3 дн.' },
  { key: 'altos_avail_4_7', label: 'AltOS 4-7 дн.' }, { key: 'altos_avail_8_10', label: 'AltOS 8-10 дн.' },
  { key: 'altoffice_avail_total', label: 'AltOffice Дост. всего' }, { key: 'altoffice_avail_1_3', label: 'AltOffice 1-3 дн.' },
  { key: 'altoffice_avail_4_7', label: 'AltOffice 4-7 дн.' }, { key: 'altoffice_avail_8_10', label: 'AltOffice 8-10 дн.' },
  { key: 'extra', label: 'Доп. данные', type: 'text' },
]

function fmt(v) { return v != null ? Number(v).toLocaleString('ru-RU') : '—' }
function fmtDec(v, d) { return v != null ? Number(v).toFixed(d) : '—' }

function openCreate() {
  editRow.value = null
  form.value = {}
  showModal.value = true
}
function openEdit(row) {
  editRow.value = row
  form.value = { ...row }
  showModal.value = true
}
function confirmDelete(row) { deleteTarget.value = row }

async function saveRow() {
  try {
    if (editRow.value?.id) {
      await tpApi.updateRow(editRow.value.id, form.value)
      toastOk('Строка обновлена')
    } else {
      await tpApi.createRow(form.value)
      toastOk('Строка добавлена')
    }
    showModal.value = false
    rows.value = await tpApi.getRows()
  } catch (e) { alert('Ошибка: ' + e.message) }
}

async function doDelete() {
  try {
    await tpApi.deleteRow(deleteTarget.value.id)
    toastOk('Строка удалена')
    deleteTarget.value = null
    rows.value = await tpApi.getRows()
  } catch (e) { alert('Ошибка: ' + e.message) }
}

async function importCsv(e) {
  const file = e.target.files[0]
  if (!file) return
  const text = await file.text()
  const lines = text.trim().split('\n')
  const headers = lines[0].split(';').map(h => h.trim().replace(/^"|"+$/g, ''))
  const rowsData = lines.slice(1).map(line => {
    const vals = line.split(';').map(v => v.trim().replace(/^"|"+$/g, ''))
    const obj = {}
    headers.forEach((h, i) => { obj[h] = vals[i] === '' ? null : isNaN(vals[i]) ? vals[i] : Number(vals[i]) })
    return obj
  })
  try {
    const res = await tpApi.bulkImport(rowsData)
    toastOk(`Импортировано: ${res.imported}, пропущено: ${res.skipped}`)
    rows.value = await tpApi.getRows()
  } catch (e) { alert('Ошибка импорта: ' + e.message) }
  e.target.value = ''
}

onMounted(async () => { rows.value = await tpApi.getRows() })
</script>

<style scoped>
.tp-registry { padding: var(--space-6); display: flex; flex-direction: column; gap: var(--space-5); }
.page-header { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: var(--space-3); }
.page-header h1 { font-size: var(--text-xl); font-weight: 700; }
.hd-actions { display: flex; gap: var(--space-2); }
.filter-bar { display: flex; gap: var(--space-3); align-items: center; flex-wrap: wrap; }
.filter-bar select, .filter-bar .fi { padding: var(--space-2) var(--space-3); border: 1px solid var(--color-border); border-radius: var(--radius-md); background: var(--color-surface); color: var(--color-text); font-size: var(--text-sm); }
.table-wrap { overflow-x: auto; border: 1px solid var(--color-border); border-radius: var(--radius-lg); }
.data-table { width: 100%; font-size: var(--text-sm); }
.data-table th { background: var(--color-surface-offset); padding: var(--space-3) var(--space-3); text-align: left; font-weight: 600; white-space: nowrap; border-bottom: 1px solid var(--color-border); }
.data-table td { padding: var(--space-2) var(--space-3); border-bottom: 1px solid var(--color-divider); }
.data-table tr:last-child td { border-bottom: none; }
.data-table tr:hover td { background: var(--color-surface-offset); }
.num { text-align: right; font-variant-numeric: tabular-nums; }
.actions { display: flex; gap: var(--space-1); white-space: nowrap; }
.btn-danger { color: var(--color-error) !important; }
.form-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: var(--space-3); padding: var(--space-4); }
.modal-overlay { position: fixed; inset: 0; background: oklch(0 0 0 / .4); display: flex; align-items: center; justify-content: center; z-index: 1000; padding: var(--space-4); }
.modal { background: var(--color-surface); border-radius: var(--radius-xl); box-shadow: var(--shadow-lg); width: 100%; }
.modal-sm { max-width: 420px; }
.mh { display: flex; justify-content: space-between; align-items: center; padding: var(--space-4) var(--space-5); border-bottom: 1px solid var(--color-border); }
.mt { font-weight: 600; font-size: var(--text-lg); }
.mc { background: none; border: none; cursor: pointer; font-size: 1.1rem; color: var(--color-text-muted); padding: var(--space-1); }
.fgi { display: flex; flex-direction: column; gap: var(--space-1); }
.fl { font-size: var(--text-xs); font-weight: 500; color: var(--color-text-muted); }
.fi { padding: var(--space-2) var(--space-3); border: 1px solid var(--color-border); border-radius: var(--radius-md); background: var(--color-bg); color: var(--color-text); font-size: var(--text-sm); }
.fac { display: flex; justify-content: flex-end; gap: var(--space-2); padding: var(--space-4); border-top: 1px solid var(--color-border); }
</style>
