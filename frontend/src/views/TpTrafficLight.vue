<template>
  <div class="tp-tl">
    <div class="page-header">
      <div>
        <h1 class="page-title">Светофор — Техподдержка</h1>
        <p class="page-subtitle">Статус ключевых показателей за последнюю неделю</p>
      </div>
    </div>

    <div v-if="loading" class="loading-state">Загрузка...</div>
    <div v-else-if="error" class="error-state">{{ error }}</div>

    <div v-else class="tl-grid">
      <div v-for="item in lights" :key="item.key" class="tl-card" :class="`tl-card--${item.light}`">
        <div class="tl-light" :class="`tl-light--${item.light}`">
          <span class="tl-dot"></span>
        </div>
        <div class="tl-content">
          <div class="tl-label">{{ item.label }}</div>
          <div class="tl-value">{{ item.valueStr }}</div>
          <div class="tl-rule">{{ item.ruleStr }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const apiBase = import.meta.env.VITE_API_URL || ''
const h = () => ({ Authorization: `Bearer ${auth.token}` })

const rows = ref([])
const rules = ref({})
const loading = ref(true)
const error = ref(null)

const LABELS = {
  total_in_work: 'В работе',
  avail_total: 'Доступность (всего)',
  new_received: 'Новых заявок',
  total_solved_week: 'Решено за неделю',
  ratio_solved_received: 'Коэф. решения',
  altos_avg_time: 'SLA AltOS (ч.)',
  altoffice_avg_time: 'SLA AltOffice (ч.)',
  altos_avail_total: 'Доступность AltOS',
  altoffice_avail_total: 'Доступность AltOffice',
}

async function load() {
  loading.value = true
  try {
    const [rr, rl] = await Promise.all([
      fetch(`${apiBase}/api/tp/rows`, { headers: h() }),
      fetch(`${apiBase}/api/tp/settings/traffic_rules`, { headers: h() }),
    ])
    rows.value = rr.ok ? await rr.json() : []
    rules.value = rl.ok ? await rl.json() : {}
  } catch (e) { error.value = e.message }
  finally { loading.value = false }
}

const lastRow = computed(() => rows.value[rows.value.length - 1] || null)

function getLight(key, value) {
  const rule = rules.value[key]
  if (!rule || !rule.enabled || value == null) return 'gray'
  const { direction, green, yellow } = rule
  if (direction === 'less') {
    if (value <= green) return 'green'
    if (value <= yellow) return 'yellow'
    return 'red'
  } else {
    if (value >= green) return 'green'
    if (value >= yellow) return 'yellow'
    return 'red'
  }
}

function ruleStr(key) {
  const rule = rules.value[key]
  if (!rule) return ''
  const dir = rule.direction === 'less' ? '≤' : '≥'
  return `Зелёный ${dir} ${rule.green} | Жёлтый ${dir} ${rule.yellow}`
}

const lights = computed(() => {
  const row = lastRow.value
  return Object.entries(LABELS)
    .filter(([key]) => rules.value[key])
    .map(([key, label]) => {
      const value = row ? row[key] : null
      const light = getLight(key, value)
      const valueStr = value == null ? '—' : Number(value).toLocaleString('ru-RU', { maximumFractionDigits: 2 })
      return { key, label, value, light, valueStr, ruleStr: ruleStr(key) }
    })
})

onMounted(load)
</script>

<style scoped>
.tp-tl { padding: var(--space-6); }
.page-header { margin-bottom: var(--space-6); }
.page-title { font-size: var(--text-xl); font-weight: 700; margin: 0; }
.page-subtitle { font-size: var(--text-sm); color: var(--color-text-muted); margin: 0; }
.loading-state, .error-state { padding: var(--space-12); text-align: center; color: var(--color-text-muted); }
.tl-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: var(--space-4); }
.tl-card { display: flex; gap: var(--space-4); align-items: flex-start; background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-lg); padding: var(--space-4); box-shadow: var(--shadow-sm); }
.tl-card--green { border-left: 4px solid var(--color-success); }
.tl-card--yellow { border-left: 4px solid var(--color-gold); }
.tl-card--red { border-left: 4px solid var(--color-error); }
.tl-card--gray { border-left: 4px solid var(--color-text-faint); }
.tl-light { width: 36px; height: 36px; border-radius: 50%; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.tl-light--green { background: color-mix(in oklch, var(--color-success) 20%, transparent); }
.tl-light--yellow { background: color-mix(in oklch, var(--color-gold) 20%, transparent); }
.tl-light--red { background: color-mix(in oklch, var(--color-error) 20%, transparent); }
.tl-light--gray { background: var(--color-surface-offset); }
.tl-dot { width: 16px; height: 16px; border-radius: 50%; display: block; }
.tl-light--green .tl-dot { background: var(--color-success); }
.tl-light--yellow .tl-dot { background: var(--color-gold); }
.tl-light--red .tl-dot { background: var(--color-error); }
.tl-light--gray .tl-dot { background: var(--color-text-faint); }
.tl-label { font-size: var(--text-sm); font-weight: 600; color: var(--color-text); }
.tl-value { font-size: var(--text-xl); font-weight: 700; color: var(--color-text); font-variant-numeric: tabular-nums; }
.tl-rule { font-size: var(--text-xs); color: var(--color-text-faint); margin-top: var(--space-1); }
</style>
