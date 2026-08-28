<template>
  <div v-if="loading" class="tempty">Загрузка…</div>
  <template v-else>
    <!-- ── Toolbar ── -->
    <div class="filters">
      <input class="srch" placeholder="Поиск по периоду…" v-model="f.search">

      <select class="cfsel" v-model="f.year">
        <option value="">Все годы</option>
        <option v-for="y in yearOptions" :key="y" :value="y">{{ y }}</option>
      </select>

      <button class="btn btn-g" :disabled="!active.length" @click="reset">Сбросить</button>

      <button v-if="canEdit" class="btn btn-p" @click="openNew">+ Строка</button>

      <button class="btn btn-g" @click="doExport" title="Скачать CSV">↓ CSV</button>
    </div>

    <div class="tinfo">
      Показано {{ filtered.length }} из {{ rows.length }}
      <span v-if="active.length"> · фильтров: {{ active.length }}</span>
    </div>

    <!-- ── Table ── -->
    <div class="twrap">
      <div class="tscroll">
        <table>
          <thead>
            <tr>
              <th v-for="c in VISIBLE_COLS" :key="c.key" @click="setSort(c.key)">
                {{ c.label }}<span class="smark">{{ sortMark(c.key) }}</span>
              </th>
              <th v-if="canEdit"></th>
            </tr>
            <!-- per-column filter row -->
            <tr class="frow">
              <th v-for="c in VISIBLE_COLS" :key="c.key">
                <select v-if="c.key === 'year'" class="cfsel" v-model="f.year" @click.stop>
                  <option value="">Все</option>
                  <option v-for="y in yearOptions" :key="y" :value="y">{{ y }}</option>
                </select>
                <input v-else class="cfin" v-model="f[c.key]" :placeholder="'…'" @click.stop>
              </th>
              <th v-if="canEdit"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in filtered" :key="r.id">
              <td v-for="c in VISIBLE_COLS" :key="c.key" :class="tdClass(c, r)">
                <span v-if="c.key === 'period'" class="sb s-period">{{ r.period || '—' }}</span>
                <span v-else-if="c.traffic && trafficColor(c.key, r[c.key])" class="tl-dot" :class="'tl-' + trafficColor(c.key, r[c.key])"></span>
                <span v-if="c.key !== 'period'">{{ fmt(c, r[c.key]) }}</span>
              </td>
              <td v-if="canEdit">
                <button class="btn btn-g" style="font-size:.75rem;padding:2px 6px" @click="openEdit(r)">✎</button>
              </td>
            </tr>
            <tr v-if="!filtered.length"><td :colspan="VISIBLE_COLS.length + (canEdit?1:0)" class="tempty">Нет данных</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- ── Modal ── -->
    <div v-if="showModal" class="modal-overlay" @click.self="showModal=false">
      <div class="modal modal-wide">
        <div class="mh">
          <span class="mt">{{ editing?.id ? 'Редактировать строку' : 'Новая строка' }}</span>
          <button class="mc" @click="showModal=false">✕</button>
        </div>

        <!-- group fields -->
        <div v-for="grp in FIELD_GROUPS" :key="grp.label" class="modal-group">
          <div class="modal-group-title">{{ grp.label }}</div>
          <div class="fg flex-wrap">
            <div v-for="c in grp.cols" :key="c.key" class="fgi">
              <label class="fl">{{ c.label }}</label>
              <input class="fi" :type="c.key==='period'?'text':'number'" v-model="form[c.key]"
                     :step="c.key.includes('ratio')?'0.01':'1'" :placeholder="c.label">
            </div>
          </div>
        </div>

        <div class="fac" style="margin-top:16px">
          <button v-if="editing?.id" class="btn btn-d" @click="deleteRow">Удалить</button>
          <div class="right">
            <button class="btn btn-g" @click="showModal=false">Отмена</button>
            <button class="btn btn-p" @click="saveRow">Сохранить</button>
          </div>
        </div>
      </div>
    </div>
  </template>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { tpApi } from '../../api/tp.js'
import { useAuthStore } from '../../stores/auth.js'
import { useTableFilters, textMatch } from '../../composables/useTableFilters.js'

const auth = useAuthStore()
const canEdit = computed(() => auth.canEdit)
const loading = ref(true)
const rows    = ref([])
const traffic = ref({})
const showModal = ref(false)
const editing   = ref(null)
const form      = ref({})

// ── Column definitions (matches DATA_COLUMNS in app.py) ──────────────────────
const ALL_COLS = [
  { key:'year',                label:'Год',                          group:'base' },
  { key:'week',                label:'Неделя',                       group:'base' },
  { key:'period',              label:'Период',                       group:'base' },
  { key:'total_in_work',       label:'В работе (всего)',             group:'load',   traffic:true },
  { key:'avail_total',         label:'Доступность (всего)',          group:'load',   traffic:true },
  { key:'new_received',        label:'Новых получено',               group:'load',   traffic:true },
  { key:'renewed',             label:'Возобновлено',                 group:'load' },
  { key:'ratio_solved_received',label:'Коэф. решения',              group:'load',   traffic:true },
  { key:'total_solved_week',   label:'Решено за неделю',            group:'load',   traffic:true },
  { key:'rushydro_hours',      label:'РусГидро (ч)',                group:'clients' },
  { key:'transneft_hours',     label:'Транснефть (ч)',              group:'clients' },
  { key:'roscosmos_hours',     label:'Роскосмос (ч)',               group:'clients' },
  { key:'bryansk_hours',       label:'Брянск (ч)',                  group:'clients' },
  { key:'mchs_hours',          label:'МЧС (ч)',                     group:'clients' },
  { key:'internal_sales_hours',label:'Internal Sales (ч)',          group:'clients' },
  { key:'altos_avg_time',      label:'AltOS ср.время (ч)',          group:'altos',  traffic:true },
  { key:'altos_total',         label:'AltOS всего',                 group:'altos' },
  { key:'altos_1_2line',       label:'AltOS 1-2 линия',            group:'altos' },
  { key:'altos_3line',         label:'AltOS 3 линия',              group:'altos' },
  { key:'altos_avail_total',   label:'AltOS дост. всего',          group:'altos',  traffic:true },
  { key:'altos_avail_1_3',     label:'AltOS дост. 1-3',            group:'altos' },
  { key:'altos_avail_4_7',     label:'AltOS дост. 4-7',            group:'altos' },
  { key:'altos_avail_8_10',    label:'AltOS дост. 8-10',           group:'altos' },
  { key:'altos_rusg_email',    label:'AltOS РусГ email',           group:'altos' },
  { key:'altos_rusg_tf',       label:'AltOS РусГ TF',              group:'altos' },
  { key:'altos_other_email',   label:'AltOS прочие email',         group:'altos' },
  { key:'altos_other_tf',      label:'AltOS прочие TF',            group:'altos' },
  { key:'altoffice_avg_time',  label:'AltOffice ср.время (ч)',     group:'altoffice', traffic:true },
  { key:'altoffice_total',     label:'AltOffice всего',            group:'altoffice' },
  { key:'altoffice_1_2line',   label:'AltOffice 1-2 линия',       group:'altoffice' },
  { key:'altoffice_3line',     label:'AltOffice 3 линия',         group:'altoffice' },
  { key:'altoffice_avail_total',label:'AltOffice дост. всего',    group:'altoffice', traffic:true },
  { key:'altoffice_avail_1_3', label:'AltOffice дост. 1-3',       group:'altoffice' },
  { key:'altoffice_avail_4_7', label:'AltOffice дост. 4-7',       group:'altoffice' },
  { key:'altoffice_avail_8_10',label:'AltOffice дост. 8-10',      group:'altoffice' },
  { key:'altoffice_rusg_email',label:'AltOffice РусГ email',      group:'altoffice' },
  { key:'altoffice_rusg_tf',   label:'AltOffice РусГ TF',         group:'altoffice' },
  { key:'altoffice_other_email',label:'AltOffice прочие email',   group:'altoffice' },
  { key:'altoffice_other_tf',  label:'AltOffice прочие TF',       group:'altoffice' },
  { key:'projserver_taken',    label:'ProjServer принято',        group:'projserver' },
  { key:'projserver_solved',   label:'ProjServer решено',         group:'projserver' },
  { key:'projserver_avail',    label:'ProjServer доступность',    group:'projserver' },
  { key:'extra',               label:'Доп. данные',               group:'extra' },
]

// Columns shown in the table (compact view — base + key metrics)
const VISIBLE_KEYS = ['year','week','period','total_in_work','avail_total','new_received',
  'ratio_solved_received','total_solved_week','altos_avg_time','altoffice_avg_time']
const VISIBLE_COLS = ALL_COLS.filter(c => VISIBLE_KEYS.includes(c.key))

// Modal field groups
const FIELD_GROUPS = [
  { label: 'Базовые', cols: ALL_COLS.filter(c => c.group === 'base') },
  { label: 'Нагрузка', cols: ALL_COLS.filter(c => c.group === 'load') },
  { label: 'Клиенты (часы)', cols: ALL_COLS.filter(c => c.group === 'clients') },
  { label: 'AltOS', cols: ALL_COLS.filter(c => c.group === 'altos') },
  { label: 'AltOffice', cols: ALL_COLS.filter(c => c.group === 'altoffice') },
  { label: 'ProjServer', cols: ALL_COLS.filter(c => c.group === 'projserver') },
  { label: 'Прочее', cols: ALL_COLS.filter(c => c.group === 'extra') },
]

const DEFAULTS = { search: '', year: '' }
for (const c of VISIBLE_COLS) DEFAULTS[c.key] = ''

const { f, setSort, sortMark, reset, active, sortRows } =
  useTableFilters(DEFAULTS, { sortKey: 'year', sortDir: 'desc' })

const yearOptions = computed(() =>
  [...new Set(rows.value.map(r => r.year).filter(Boolean))].sort((a, b) => b - a))

const filtered = computed(() => {
  const list = rows.value.filter(r => {
    if (f.year && String(r.year) !== String(f.year)) return false
    if (f.search && !textMatch(String(r.period || ''), f.search)) return false
    for (const c of VISIBLE_COLS) {
      if (c.key === 'year' || c.key === 'period') continue
      if (f[c.key] && !textMatch(String(r[c.key] ?? ''), f[c.key])) return false
    }
    return true
  })
  return sortRows(list)
})

function fmt(col, val) {
  if (val == null || val === '') return '—'
  if (col.key === 'ratio_solved_received') return Number(val).toFixed(2)
  if (col.key === 'year' || col.key === 'week') return String(Math.round(val))
  if (typeof val === 'number') return Number.isInteger(val) ? val : val.toFixed(1)
  return val
}

function tdClass(col, row) {
  const classes = ['td-muted']
  if (col.key === 'year' || col.key === 'week') classes.push('td-num')
  return classes
}

function trafficColor(key, val) {
  const rule = traffic.value[key]
  if (!rule || !rule.enabled || val == null) return null
  const v = Number(val)
  if (rule.direction === 'less') {
    if (v <= rule.green) return 'green'
    if (v <= rule.yellow) return 'yellow'
    return 'red'
  } else {
    if (v >= rule.green) return 'green'
    if (v >= rule.yellow) return 'yellow'
    return 'red'
  }
}

async function load() {
  loading.value = true
  try {
    const [r, s] = await Promise.all([tpApi.rows(), tpApi.getSetting('traffic_rules')])
    rows.value = r
    traffic.value = s || {}
  } finally { loading.value = false }
}

function openNew() {
  editing.value = {}
  form.value = {}
  ALL_COLS.forEach(c => { form.value[c.key] = '' })
  showModal.value = true
}

function openEdit(r) {
  editing.value = { ...r }
  form.value = { ...r }
  showModal.value = true
}

function payload() {
  const p = {}
  ALL_COLS.forEach(c => {
    const v = form.value[c.key]
    p[c.key] = (c.key === 'period') ? (v || null) : (v === '' || v == null ? null : Number(v))
  })
  return p
}

async function saveRow() {
  try {
    if (editing.value?.id) {
      await tpApi.updateRow(editing.value.id, payload())
    } else {
      await tpApi.createRow(payload())
    }
    await load()
    showModal.value = false
  } catch { /* toast handled by client */ }
}

async function deleteRow() {
  if (!confirm('Удалить строку?')) return
  try {
    await tpApi.deleteRow(editing.value.id)
    await load()
    showModal.value = false
  } catch { /* toast handled by client */ }
}

async function doExport() {
  const url = `/api/tp/export`
  const a = document.createElement('a')
  a.href = url
  a.download = 'tp_report.csv'
  a.click()
}

onMounted(load)
</script>

<style scoped>
.modal-wide { max-width: 860px; }
.modal-group { margin-top: 14px; }
.modal-group-title {
  font-size: var(--text-xs, .75rem);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: .05em;
  color: var(--color-muted, #888);
  margin-bottom: 6px;
  padding-bottom: 4px;
  border-bottom: 1px solid var(--color-border, #e5e7eb);
}
.flex-wrap { flex-wrap: wrap; gap: 8px; }
.fgi { min-width: 180px; flex: 1 1 180px; }
.tl-dot {
  display: inline-block;
  width: 8px; height: 8px;
  border-radius: 50%;
  margin-right: 4px;
  vertical-align: middle;
}
.tl-green  { background: #22c55e; }
.tl-yellow { background: #eab308; }
.tl-red    { background: #ef4444; }
.s-period {
  background: var(--color-primary-highlight, #e0f2fe);
  color: var(--color-primary, #0369a1);
  border-radius: 4px;
  padding: 1px 6px;
  font-size: .75rem;
  font-weight: 600;
}
.td-num { font-variant-numeric: tabular-nums; }
</style>
