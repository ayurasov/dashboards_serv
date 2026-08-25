<template>
  <div class="tp-traffic">
    <div class="page-header">
      <h1>Настройка светофора ТП</h1>
      <div class="hd-actions">
        <button class="btn btn-g" @click="loadRules">↺ Сбросить</button>
        <button class="btn btn-p" @click="saveRules" :disabled="saving">{{ saving ? 'Сохранение…' : 'Сохранить' }}</button>
      </div>
    </div>

    <p class="hint">Настройте пороги для каждого показателя. Светофор отображается на главном дашборде ТП.</p>

    <div v-if="loading" class="loading-state">Загрузка…</div>

    <div v-else class="rules-grid">
      <div class="rule-card" v-for="(rule, key) in rules" :key="key">
        <div class="rule-header">
          <span class="rule-name">{{ LABELS[key] || key }}</span>
          <label class="toggle">
            <input type="checkbox" v-model="rule.enabled">
            <span class="toggle-track"></span>
          </label>
        </div>
        <div class="rule-body" v-if="rule.enabled">
          <div class="rule-direction">
            <label>
              <input type="radio" v-model="rule.direction" value="less"> Меньше — лучше
            </label>
            <label>
              <input type="radio" v-model="rule.direction" value="more"> Больше — лучше
            </label>
          </div>
          <div class="thresholds">
            <div class="threshold green">
              <span class="dot green-dot"></span>
              <label>Зелёный {{ rule.direction === 'less' ? '≤' : '≥' }}</label>
              <input type="number" class="fi" v-model.number="rule.green" step="any">
            </div>
            <div class="threshold yellow">
              <span class="dot yellow-dot"></span>
              <label>Жёлтый {{ rule.direction === 'less' ? '≤' : '≥' }}</label>
              <input type="number" class="fi" v-model.number="rule.yellow" step="any">
            </div>
            <div class="threshold red">
              <span class="dot red-dot"></span>
              <label>Красный — остальное</label>
            </div>
          </div>
        </div>
        <div class="rule-disabled" v-else>Показатель не отслеживается</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { tpApi } from '../../api/tp.js'
import { toastOk } from '../../composables/useToast.js'

const rules = ref({})
const loading = ref(false)
const saving = ref(false)

const LABELS = {
  total_in_work: 'В работе (обращений)',
  avail_total: 'Доступность (всего, ч.)',
  total_solved_week: 'Решено за неделю',
  ratio_solved_received: 'Коэффициент решения',
  altos_avg_time: 'AltOS — ср. время решения',
  altoffice_avg_time: 'AltOffice — ср. время решения',
  new_received: 'Новых получено',
  renewed: 'Возобновлено',
  projserver_avail: 'Проектный сервер — доступность',
}

async function loadRules() {
  loading.value = true
  try {
    rules.value = await tpApi.getSetting('traffic_rules')
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

async function saveRules() {
  saving.value = true
  try {
    await tpApi.putSetting('traffic_rules', rules.value)
    toastOk('Настройки светофора сохранены')
  } catch (e) {
    alert('Ошибка: ' + e.message)
  } finally {
    saving.value = false
  }
}

onMounted(loadRules)
</script>

<style scoped>
.tp-traffic { padding: var(--space-6); display: flex; flex-direction: column; gap: var(--space-5); }
.page-header { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: var(--space-3); }
.page-header h1 { font-size: var(--text-xl); font-weight: 700; }
.hd-actions { display: flex; gap: var(--space-2); }
.hint { color: var(--color-text-muted); font-size: var(--text-sm); margin-top: calc(var(--space-2) * -1); }

.rules-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: var(--space-4); }
.rule-card { background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-lg); overflow: hidden; }
.rule-header { display: flex; justify-content: space-between; align-items: center; padding: var(--space-3) var(--space-4); background: var(--color-surface-offset); border-bottom: 1px solid var(--color-border); }
.rule-name { font-weight: 600; font-size: var(--text-sm); }
.rule-body { padding: var(--space-4); display: flex; flex-direction: column; gap: var(--space-3); }
.rule-disabled { padding: var(--space-4); color: var(--color-text-faint); font-size: var(--text-sm); font-style: italic; }
.rule-direction { display: flex; gap: var(--space-4); font-size: var(--text-sm); }
.rule-direction label { display: flex; align-items: center; gap: var(--space-1); cursor: pointer; }

.thresholds { display: flex; flex-direction: column; gap: var(--space-2); }
.threshold { display: flex; align-items: center; gap: var(--space-2); font-size: var(--text-sm); }
.threshold label { min-width: 110px; color: var(--color-text-muted); }
.threshold .fi { width: 80px; padding: var(--space-1) var(--space-2); border: 1px solid var(--color-border); border-radius: var(--radius-md); background: var(--color-bg); color: var(--color-text); font-size: var(--text-sm); }
.threshold.red label { color: var(--color-text-muted); }
.dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
.green-dot { background: #27ae60; }
.yellow-dot { background: #f1c40f; }
.red-dot { background: #e74c3c; }

.toggle { position: relative; display: inline-flex; align-items: center; cursor: pointer; }
.toggle input { position: absolute; opacity: 0; width: 0; height: 0; }
.toggle-track { width: 36px; height: 20px; background: var(--color-border); border-radius: var(--radius-full); transition: background var(--transition-interactive); position: relative; }
.toggle-track::after { content: ''; position: absolute; top: 2px; left: 2px; width: 16px; height: 16px; background: #fff; border-radius: 50%; transition: transform var(--transition-interactive); }
.toggle input:checked + .toggle-track { background: var(--color-primary); }
.toggle input:checked + .toggle-track::after { transform: translateX(16px); }

.loading-state { padding: var(--space-8); text-align: center; color: var(--color-text-muted); }
</style>
