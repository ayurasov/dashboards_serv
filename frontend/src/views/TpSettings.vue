<template>
  <div class="tp-settings">
    <div class="page-header">
      <h1 class="page-title">Настройки светофора — ТП</h1>
      <p class="page-subtitle">Пороговые значения для индикаторов технической поддержки</p>
    </div>

    <div v-if="loading" class="loading-state">Загрузка...</div>
    <div v-else-if="error" class="error-state">{{ error }}</div>

    <template v-else>
      <div class="rules-grid">
        <div v-for="(rule, key) in rules" :key="key" class="rule-card">
          <div class="rule-key">{{ LABELS[key] || key }}</div>
          <div class="rule-fields">
            <label class="field-label">Направление</label>
            <select v-model="rules[key].direction" class="select-sm" :disabled="!canEdit">
              <option value="less">меньше — лучше</option>
              <option value="more">больше — лучше</option>
            </select>
            <label class="field-label">🟢 Зелёный (≤/≥)</label>
            <input v-model.number="rules[key].green" type="number" step="any" class="input-sm" :disabled="!canEdit" />
            <label class="field-label">🟡 Жёлтый (≤/≥)</label>
            <input v-model.number="rules[key].yellow" type="number" step="any" class="input-sm" :disabled="!canEdit" />
            <label class="field-label toggle-label">
              <input type="checkbox" v-model="rules[key].enabled" :disabled="!canEdit" />
              Активно
            </label>
          </div>
        </div>
      </div>
      <div class="save-row" v-if="canEdit">
        <button class="btn btn-primary" @click="save" :disabled="saving">
          {{ saving ? 'Сохранение...' : 'Сохранить настройки' }}
        </button>
        <span v-if="saved" class="save-ok">✅ Сохранено</span>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const apiBase = import.meta.env.VITE_API_URL || ''
const h = (extra = {}) => ({ Authorization: `Bearer ${auth.token}`, ...extra })

const rules = ref({})
const loading = ref(true)
const error = ref(null)
const saving = ref(false)
const saved = ref(false)

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

const canEdit = computed(() => {
  const level = auth.serviceAccessLevel?.('tech')
  return auth.role === 'admin' || level === 'edit' || level === 'edit_metrics' || level === 'admin'
})

async function load() {
  loading.value = true
  try {
    const res = await fetch(`${apiBase}/api/tp/settings/traffic_rules`, { headers: h() })
    if (!res.ok) throw new Error(res.status)
    rules.value = await res.json()
  } catch (e) { error.value = e.message }
  finally { loading.value = false }
}

async function save() {
  saving.value = true
  saved.value = false
  try {
    const res = await fetch(`${apiBase}/api/tp/settings/traffic_rules`, {
      method: 'PUT',
      headers: h({ 'Content-Type': 'application/json' }),
      body: JSON.stringify(rules.value),
    })
    if (!res.ok) throw new Error(await res.text())
    saved.value = true
    setTimeout(() => { saved.value = false }, 3000)
  } catch (e) { alert('Ошибка: ' + e.message) }
  finally { saving.value = false }
}

onMounted(load)
</script>

<style scoped>
.tp-settings { padding: var(--space-6); }
.page-header { margin-bottom: var(--space-6); }
.page-title { font-size: var(--text-xl); font-weight: 700; margin: 0; }
.page-subtitle { font-size: var(--text-sm); color: var(--color-text-muted); margin: 0; }
.loading-state, .error-state { padding: var(--space-12); text-align: center; color: var(--color-text-muted); }
.rules-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: var(--space-4); margin-bottom: var(--space-6); }
.rule-card { background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-lg); padding: var(--space-4); box-shadow: var(--shadow-sm); }
.rule-key { font-size: var(--text-base); font-weight: 600; color: var(--color-text); margin-bottom: var(--space-3); }
.rule-fields { display: flex; flex-direction: column; gap: var(--space-2); }
.field-label { font-size: var(--text-xs); color: var(--color-text-muted); }
.input-sm, .select-sm { padding: var(--space-1) var(--space-3); border: 1px solid var(--color-border); border-radius: var(--radius-sm); background: var(--color-surface); color: var(--color-text); font-size: var(--text-sm); }
.toggle-label { display: flex; align-items: center; gap: var(--space-2); font-size: var(--text-sm); color: var(--color-text-muted); }
.save-row { display: flex; align-items: center; gap: var(--space-4); }
.btn { padding: var(--space-2) var(--space-5); border-radius: var(--radius-md); font-size: var(--text-sm); font-weight: 600; cursor: pointer; border: none; }
.btn-primary { background: var(--color-primary); color: #fff; }
.btn-primary:hover:not(:disabled) { background: var(--color-primary-hover); }
.btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }
.save-ok { color: var(--color-success); font-size: var(--text-sm); }
</style>
