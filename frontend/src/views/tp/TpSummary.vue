<template>
  <div v-if="loading" class="tempty">Загрузка…</div>
  <div v-else>
    <div class="filters">
      <select class="cfsel" v-model="weeks" @change="load">
        <option :value="4">4 недели</option>
        <option :value="8">8 недель</option>
        <option :value="12">12 недель</option>
        <option :value="26">26 недель</option>
      </select>
    </div>

    <div class="twrap" style="margin-top:12px">
      <div class="tscroll">
        <table>
          <thead>
            <tr>
              <th>Показатель</th>
              <th>Последняя неделя</th>
              <th>Предыдущая</th>
              <th>Изменение</th>
              <th>Статус</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="m in meta" :key="m.key">
              <td class="td-p">{{ m.label }}</td>
              <td class="td-muted" style="font-variant-numeric:tabular-nums">{{ fmtVal(m.key, data.last_week?.[m.key]) }}</td>
              <td class="td-muted" style="font-variant-numeric:tabular-nums">{{ fmtVal(m.key, data.prev_week?.[m.key]) }}</td>
              <td :class="deltaClass(m.key, data.trend?.[m.key])" style="font-variant-numeric:tabular-nums">
                {{ fmtDelta(m.key, data.trend?.[m.key]) }}
              </td>
              <td>
                <span v-if="data.traffic?.[m.key]" class="sb" :class="'s-' + data.traffic[m.key]">
                  {{ TL_LABEL[data.traffic[m.key]] }}
                </span>
                <span v-else class="td-muted">—</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { tpApi } from '../../api/tp.js'

const loading = ref(true)
const weeks   = ref(8)
const data    = ref({})

const TL_LABEL = { green: 'Норма', yellow: 'Внимание', red: 'Критично' }

const TRAFFIC_KEYS = ['total_in_work','avail_total','new_received','total_solved_week',
  'ratio_solved_received','altos_avg_time','altoffice_avg_time','altos_avail_total','altoffice_avail_total']

const RATIO_KEYS = ['ratio_solved_received']
const H1_KEYS   = ['altos_avg_time','altoffice_avg_time']

const meta = computed(() => (data.value?.meta || []))

function fmtVal(key, val) {
  if (val == null) return '—'
  if (RATIO_KEYS.includes(key)) return Number(val).toFixed(2)
  if (H1_KEYS.includes(key))   return Number(val).toFixed(1)
  return Math.round(val)
}
function fmtDelta(key, delta) {
  if (delta == null) return ''
  const sign = delta > 0 ? '+' : ''
  return sign + fmtVal(key, delta)
}

// direction map (same as tp/app.py DEFAULT_TRAFFIC_RULES)
const DIR = { total_in_work:'less', avail_total:'less', new_received:'less',
  total_solved_week:'more', ratio_solved_received:'more',
  altos_avg_time:'less', altoffice_avg_time:'less',
  altos_avail_total:'more', altoffice_avail_total:'more' }

function deltaClass(key, delta) {
  if (delta == null) return 'td-muted'
  const dir = DIR[key]
  if (!dir || delta === 0) return 'td-muted'
  const good = dir === 'less' ? delta < 0 : delta > 0
  return good ? 'text-ok' : 'text-bad'
}

async function load() {
  loading.value = true
  try { data.value = await tpApi.summary(weeks.value) }
  finally { loading.value = false }
}

onMounted(load)
</script>

<style scoped>
.text-ok  { color: #16a34a; font-weight: 600; }
.text-bad { color: #dc2626; font-weight: 600; }
.s-green  { background:#dcfce7; color:#15803d; border-radius:4px; padding:1px 6px; font-size:.72rem; font-weight:600; }
.s-yellow { background:#fef9c3; color:#854d0e; border-radius:4px; padding:1px 6px; font-size:.72rem; font-weight:600; }
.s-red    { background:#fee2e2; color:#b91c1c; border-radius:4px; padding:1px 6px; font-size:.72rem; font-weight:600; }
</style>
