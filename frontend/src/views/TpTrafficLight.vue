<template>
  <div class="tp-traffic page-content">
    <div class="page-header">
      <h1 class="page-title">🚦 Светофор — Техподдержка</h1>
      <div class="header-controls">
        <router-link to="/tp" class="btn btn-secondary btn-sm">← Дашборд</router-link>
      </div>
    </div>

    <p class="page-desc">Настройте пороговые значения показателей. Зелёный — норма, жёлтый — внимание, красный — превышение.</p>

    <div v-if="loading" class="loading-state">Загрузка…</div>
    <div v-else-if="error" class="error-banner">{{ error }}</div>

    <div v-else class="rules-grid">
      <div class="rule-card" v-for="(rule, key) in localRules" :key="key">
        <div class="rule-header">
          <span class="rule-key">{{ LABELS[key] || key }}</span>
          <label class="toggle">
            <input type="checkbox" v-model="rule.enabled" :disabled="!canEdit" />
            <span class="toggle-slider"></span>
          </label>
        </div>
        <div class="rule-body" :class="{ disabled: !rule.enabled }">
          <div class="threshold-row">
            <span class="threshold-dir" :class="rule.direction">
              {{ rule.direction === 'more' ? '↑ больше лучше' : '↓ меньше лучше' }}
            </span>
          </div>
          <div class="threshold-inputs">
            <label>
              🟢 Зелёный {{ rule.direction === 'more' ? '≥' : '≤' }}
              <input v-model.number="rule.green" type="number" step="any" :disabled="!canEdit" />
            </label>
            <label>
              🟡 Жёлтый {{ rule.direction === 'more' ? '≥' : '≤' }}
              <input v-model.number="rule.yellow" type="number" step="any" :disabled="!canEdit" />
            </label>
          </div>
        </div>
        <!-- Current value indicator -->
        <div class="rule-current" v-if="lastRow">
          <span class="current-label">Последнее:</span>
          <span class="current-val" :class="calcLight(key, lastRow[key], rule)">
            {{ lastRow[key] ?? '—' }}
          </span>
        </div>
      </div>
    </div>

    <div v-if="canEdit && !loading" class="save-bar">
      <button class="btn btn-primary" :disabled="saving" @click="saveRules">
        {{ saving ? 'Сохранение…' : 'Сохранить настройки' }}
      </button>
      <span v-if="saved" class="saved-msg">✅ Сохранено</span>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useAuthStore } from '../stores/auth.js'
import { tpApi } from '../api/tp.js'

const loading = ref(false)
const saving  = ref(false)
const saved   = ref(false)
const error   = ref(null)
const rules   = ref({})
const rows    = ref([])
const localRules = ref({})
const auth    = useAuthStore()

const canEdit = computed(() => auth.role === 'admin' || auth.canEditService?.('tech'))
const lastRow = computed(() => rows.value.at(-1) || null)

const LABELS = {
  total_in_work:          'В работе (обращений)',
  avail_total:            'Доступность — итого',
  new_received:           'Новых за неделю',
  total_solved_week:      'Решено за неделю',
  ratio_solved_received:  'Коэф. закрытия',
  altos_avg_time:         'AltOS — ср. время (ч)',
  altoffice_avg_time:     'AltOffice — ср. время (ч)',
  altos_avail_total:      'AltOS — доступность',
  altoffice_avail_total:  'AltOffice — доступность',
}

function calcLight(key, val, rule) {
  if (!rule.enabled || val === null || val === undefined) return ''
  const { direction, green, yellow } = rule
  if (direction === 'less') {
    if (val <= green)  return 'green'
    if (val <= yellow) return 'yellow'
    return 'red'
  } else {
    if (val >= green)  return 'green'
    if (val >= yellow) return 'yellow'
    return 'red'
  }
}

async function load() {
  loading.value = true
  error.value = null
  try {
    [rules.value, rows.value] = await Promise.all([tpApi.getTrafficRules(), tpApi.getRows()])
    localRules.value = JSON.parse(JSON.stringify(rules.value))
  } catch (e) { error.value = e.message }
  finally { loading.value = false }
}

async function saveRules() {
  saving.value = true
  saved.value = false
  try {
    await tpApi.putTrafficRules(localRules.value)
    rules.value = JSON.parse(JSON.stringify(localRules.value))
    saved.value = true
    setTimeout(() => { saved.value = false }, 3000)
  } catch (e) { alert(e.message) }
  finally { saving.value = false }
}

onMounted(load)
</script>

<style scoped>
.tp-traffic  { padding: var(--space-6); }
.page-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: var(--space-4); flex-wrap: wrap; gap: var(--space-3); }
.page-title  { font-size: var(--text-xl); font-weight: 700; }
.header-controls { display: flex; gap: var(--space-2); }
.page-desc   { color: var(--color-text-muted); font-size: var(--text-sm); margin-bottom: var(--space-6); max-width: 65ch; }

.rules-grid  { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: var(--space-4); margin-bottom: var(--space-6); }
.rule-card   { background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-lg); padding: var(--space-4); display: flex; flex-direction: column; gap: var(--space-3); }
.rule-header { display: flex; align-items: center; justify-content: space-between; }
.rule-key    { font-weight: 600; font-size: var(--text-sm); }

.toggle      { position: relative; display: inline-block; width: 36px; height: 20px; }
.toggle input{ opacity: 0; width: 0; height: 0; }
.toggle-slider { position: absolute; cursor: pointer; inset: 0; background: var(--color-border); border-radius: var(--radius-full); transition: .2s; }
.toggle-slider::before { content: ''; position: absolute; width: 14px; height: 14px; left: 3px; bottom: 3px; background: white; border-radius: 50%; transition: .2s; }
.toggle input:checked + .toggle-slider { background: var(--color-primary); }
.toggle input:checked + .toggle-slider::before { transform: translateX(16px); }

.rule-body.disabled { opacity: .45; pointer-events: none; }
.threshold-dir { font-size: var(--text-xs); font-weight: 600; text-transform: uppercase; letter-spacing: .05em; }
.threshold-dir.more { color: var(--color-success); }
.threshold-dir.less { color: var(--color-notification); }

.threshold-inputs { display: flex; flex-direction: column; gap: var(--space-2); }
.threshold-inputs label { display: flex; align-items: center; justify-content: space-between; font-size: var(--text-sm); gap: var(--space-2); }
.threshold-inputs input { width: 90px; padding: var(--space-1) var(--space-2); border: 1px solid var(--color-border); border-radius: var(--radius-sm); background: var(--color-bg); color: var(--color-text); font-size: var(--text-sm); }

.rule-current { display: flex; align-items: center; gap: var(--space-2); font-size: var(--text-xs); border-top: 1px solid var(--color-divider); padding-top: var(--space-2); }
.current-label { color: var(--color-text-faint); }
.current-val.green  { color: var(--color-success); font-weight: 700; }
.current-val.yellow { color: var(--color-gold); font-weight: 700; }
.current-val.red    { color: var(--color-notification); font-weight: 700; }

.save-bar  { display: flex; align-items: center; gap: var(--space-4); padding-top: var(--space-4); border-top: 1px solid var(--color-border); }
.saved-msg { color: var(--color-success); font-size: var(--text-sm); }

.loading-state { text-align: center; padding: var(--space-16); color: var(--color-text-muted); }
.error-banner  { background: var(--color-error-highlight); color: var(--color-error); padding: var(--space-4); border-radius: var(--radius-md); }
</style>
