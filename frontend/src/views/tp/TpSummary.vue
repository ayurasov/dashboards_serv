<template>
  <div v-if="loading" class="tempty">Загрузка…</div>
  <div v-else>

    <div class="filters">
      <div class="tp-f-row">
        <span class="fl">Быстрый период</span>
        <div class="chip-row">
          <span v-for="q in QUICK" :key="q.v" class="chip" :class="{ active: quick === q.v }"
                @click="quick = q.v">{{ q.label }}</span>
        </div>
      </div>
      <div class="tp-f-bottom">
        <div class="tp-f-meta">{{ nowRows.length }} нед. в периоде · сравнение с предыдущим таким же периодом</div>
      </div>
    </div>

    <div class="twrap" style="margin-top:12px">
      <div class="tscroll">
        <table>
          <thead>
            <tr>
              <th>Показатель</th>
              <th>{{ nowLabel }}</th>
              <th>{{ prevLabel }}</th>
              <th>Изменение</th>
              <th>Статус</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="m in metrics" :key="m.key">
              <td class="td-p">{{ m.label }}</td>
              <td class="td-muted" style="font-variant-numeric:tabular-nums">{{ fmtVal(m.key, m.now) }}</td>
              <td class="td-muted" style="font-variant-numeric:tabular-nums">{{ fmtVal(m.key, m.prev) }}</td>
              <td :class="deltaClass(m.key, m.delta)" style="font-variant-numeric:tabular-nums">
                {{ fmtDelta(m.key, m.delta) }}
              </td>
              <td>
                <span v-if="m.status" class="sb" :class="'s-' + m.status">{{ TL_LABEL[m.status] }}</span>
                <span v-else class="td-muted">—</span>
              </td>
            </tr>
            <tr v-if="!metrics.length"><td colspan="5" class="tempty">Нет данных</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { tpApi } from '../../api/tp.js'

const QUICK = [
  { v: '1',  label: 'Последняя неделя' },
  { v: '2',  label: '2 недели' },
  { v: '4',  label: 'Месяц' },
  { v: '8',  label: '8 недель' },
  { v: '13', label: '13 недель' },
  { v: '26', label: 'Полгода' },
  { v: 'all', label: 'Всё время' },
]

const loading = ref(true)
const quick = ref('8')
const RAW = ref([])
const rules = ref({})
const meta = ref([])

const TL_LABEL = { green: 'Норма', yellow: 'Внимание', red: 'Критично' }

// Metrics aggregated as an average over the interval; the rest as a sum.
const AVG_KEYS = new Set(['total_in_work', 'ratio_solved_received', 'altos_avg_time', 'altoffice_avg_time'])
const RATIO_KEYS = ['ratio_solved_received']
const H1_KEYS = ['altos_avg_time', 'altoffice_avg_time']

// direction map (same as tp backend DEFAULT_TRAFFIC_RULES)
const DIR = { total_in_work: 'less', avail_total: 'less', new_received: 'less',
  total_solved_week: 'more', ratio_solved_received: 'more',
  altos_avg_time: 'less', altoffice_avg_time: 'less',
  altos_avail_total: 'more', altoffice_avail_total: 'more' }

// ── interval rows ──
const nowRows = computed(() => {
  if (quick.value === 'all') {
    const half = Math.max(1, Math.floor(RAW.value.length / 2))
    return RAW.value.slice(half)
  }
  return RAW.value.slice(-parseInt(quick.value))
})
const prevRows = computed(() => {
  if (quick.value === 'all') {
    const half = Math.max(1, Math.floor(RAW.value.length / 2))
    return RAW.value.slice(0, half)
  }
  const n = parseInt(quick.value)
  return RAW.value.length > n ? RAW.value.slice(-2 * n, -n) : []
})

const nowLabel = computed(() => quick.value === 'all'
  ? '2-я половина периода'
  : pluralLabel('Последние', 'Последняя'))
const prevLabel = computed(() => quick.value === 'all'
  ? '1-я половина периода'
  : pluralLabel('Предыдущие', 'Предыдущая'))

function pluralLabel(prefixMany, prefixOne) {
  const n = parseInt(quick.value)
  if (n === 1) return prefixOne + ' неделя'
  const w = (n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 12 || n % 100 > 14)) ? 'недели' : 'недель'
  return `${prefixMany} ${n} ${w}`
}

// ── metrics ──
const metrics = computed(() => {
  const cols = meta.value.filter(m => !['year', 'week', 'period'].includes(m.key))
  const last = nowRows.value[nowRows.value.length - 1]
  const agg = (rows, key) => {
    if (!rows.length) return null
    const vals = rows.map(r => r[key]).filter(v => v != null)
    if (!vals.length) return null
    if (AVG_KEYS.has(key)) return vals.reduce((a, b) => a + b, 0) / vals.length
    return vals.reduce((a, b) => a + b, 0)
  }
  return cols.map(m => {
    const key = m.key
    const now = agg(nowRows.value, key)
    const prev = agg(prevRows.value, key)
    return { key, label: m.label, now, prev, delta: (now != null && prev != null) ? now - prev : null,
      status: last ? trafficColor(key, last[key]) : null }
  })
})

function trafficColor(key, val) {
  const rule = rules.value[key]
  if (!rule || !rule.enabled || val == null) return null
  const v = Number(val)
  if (rule.direction === 'less') {
    if (v <= rule.green) return 'green'
    if (v <= rule.yellow) return 'yellow'
    return 'red'
  }
  if (v >= rule.green) return 'green'
  if (v >= rule.yellow) return 'yellow'
  return 'red'
}

function fmtVal(key, val) {
  if (val == null) return '—'
  if (RATIO_KEYS.includes(key)) return Number(val).toFixed(2)
  if (H1_KEYS.includes(key)) return Number(val).toFixed(1)
  return Math.round(val).toLocaleString('ru-RU')
}
function fmtDelta(key, delta) {
  if (delta == null) return '—'
  const sign = delta > 0 ? '+' : ''
  return sign + fmtVal(key, delta)
}
function deltaClass(key, delta) {
  if (delta == null) return 'td-muted'
  const dir = DIR[key]
  if (!dir || Math.abs(delta) < 1e-9) return 'td-muted'
  const good = dir === 'less' ? delta < 0 : delta > 0
  return good ? 'text-ok' : 'text-bad'
}

onMounted(async () => {
  try {
    const [rows, s, cols] = await Promise.all([
      tpApi.rows(), tpApi.getSetting('traffic_rules'), tpApi.columns(),
    ])
    RAW.value = rows
      .filter(r => r.year != null && r.week != null)
      .map(r => ({ ...r, year: Math.round(r.year), week: Math.round(r.week) }))
      .sort((a, b) => a.year - b.year || a.week - b.week)
    rules.value = s || {}
    meta.value = cols || []
  } finally { loading.value = false }
})
</script>

<style scoped>
.tp-f-row{display:flex;flex-direction:column;gap:6px;}
.chip-row{display:flex;flex-wrap:wrap;gap:6px;}
.chip{padding:4px 10px;border-radius:99px;border:1px solid var(--c-div);background:var(--c-surf2);font-size:.75rem;cursor:pointer;transition:all .15s;user-select:none;color:var(--c-muted);font-weight:500;}
.chip.active{background:var(--c-red);color:#fff;border-color:var(--c-red);}
.chip:hover:not(.active){background:var(--c-off);color:var(--c-txt);}
.tp-f-bottom{display:flex;align-items:center;gap:12px;}
.tp-f-meta{font-size:.75rem;color:var(--c-faint);}
.text-ok  { color: #16a34a; font-weight: 600; }
.text-bad { color: #dc2626; font-weight: 600; }
.s-green  { background:#dcfce7; color:#15803d; border-radius:4px; padding:1px 6px; font-size:.72rem; font-weight:600; }
.s-yellow { background:#fef9c3; color:#854d0e; border-radius:4px; padding:1px 6px; font-size:.72rem; font-weight:600; }
.s-red    { background:#fee2e2; color:#b91c1c; border-radius:4px; padding:1px 6px; font-size:.72rem; font-weight:600; }
</style>
