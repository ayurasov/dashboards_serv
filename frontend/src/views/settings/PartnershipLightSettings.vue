<script setup>
import { computed, ref } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import AppIcon from '@/components/ui/AppIcon.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import LightBadge from '@/components/ui/LightBadge.vue'
import { partnershipsApi } from '@/api/services'
import { useAsync } from '@/composables/useAsync'
import { confirm } from '@/composables/useConfirm'
import { toastOk } from '@/composables/useToast'
import { useAuthStore } from '@/stores/auth'
import { formatNumber } from '@/utils/format'
import { LIGHT_LABELS, worst } from '@/utils/lights'
import {
  LIGHT_CHOICES, LIGHT_GROUP_ORDER, LIGHT_PARTS, certAgeRange, countWord, formatYearsGenitive, lightRuleChanges, shortRuleLabel,
  thresholdErrors,
} from '@/domain/partnerships'

const auth = useAuthStore()
const canManage = computed(() => auth.can('project_product', 'manager'))

const saved = ref([])
const draft = ref([])
const loading = ref(true)
const loadError = ref('')
const saving = ref(false)
const serverErrors = ref({})

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    const rules = await partnershipsApi.lightRules()
    saved.value = rules
    draft.value = rules.map((r) => ({ ...r }))
  } catch (e) {
    loadError.value = e.message
  } finally {
    loading.value = false
  }
}
load()
const stats = useAsync(() => partnershipsApi.analytics({}))
const statOf = (key) => stats.data.value?.lights?.find((r) => r.key === key) || null
const otherStatuses = computed(() => statOf('status:__other'))
const total = computed(() => stats.data.value?.total ?? null)

const HINTS = {
  status: 'Цвет задаётся для каждого статуса партнёрства.',
  nda: 'Подписано ли соглашение о неразглашении.',
  agreement: 'Подписано ли соглашение о технологическом партнёрстве.',
  cert_age: 'Сколько лет прошло с даты сертификата. Записи без даты по сроку не оцениваются.',
}
const ICONS = { status: 'activity', nda: 'lock', agreement: 'file', cert_age: 'calendar' }

const groups = computed(() => {
  const rank = (k) => (LIGHT_GROUP_ORDER.includes(k) ? LIGHT_GROUP_ORDER.indexOf(k) : 99)
  const out = []
  for (const r of [...draft.value].sort((a, b) => a.sort_order - b.sort_order)) {
    let g = out.find((x) => x.key === r.group_key)
    if (!g) {
      g = { key: r.group_key, label: r.group, rules: [] }
      out.push(g)
    }
    g.rules.push(r)
  }
  return out.sort((a, b) => rank(a.key) - rank(b.key))
})

const changes = computed(() => lightRuleChanges(draft.value, saved.value))
const changedKeys = computed(() => new Set(changes.value.map((c) => c.key)))
const errors = computed(() => ({ ...thresholdErrors(draft.value), ...serverErrors.value }))
const hasErrors = computed(() => Object.keys(thresholdErrors(draft.value)).length > 0)
const dirty = computed(() => changes.value.length > 0)

const thresholdOf = (key) => draft.value.find((r) => r.key === key)?.threshold
const thresholdPrefix = (key) => (key === 'cert_age:aging' ? `Старше ${formatYearsGenitive(thresholdOf('cert_age:fresh'))}, но не старше` : 'Не старше')
/** «2 → лет», «1 → года», «2,5 → года» — после «не старше». */
const yearsWord = (n) => formatYearsGenitive(n === '' || n === null ? 0 : n).split(' ').pop()

function setLight(rule, light) {
  if (!canManage.value) return
  rule.light = light
}
function onThreshold(rule, event) {
  const raw = event.target.value
  rule.threshold = raw === '' ? '' : Number(raw)
  delete serverErrors.value[rule.key]
}
function discard() {
  draft.value = saved.value.map((r) => ({ ...r }))
  serverErrors.value = {}
}

async function save() {
  if (!dirty.value || hasErrors.value) return
  saving.value = true
  serverErrors.value = {}
  const body = changes.value
  try {
    const rules = await partnershipsApi.saveLightRules(body)
    saved.value = rules
    draft.value = rules.map((r) => ({ ...r }))
    toastOk('Правила светофора сохранены')
    stats.reload()
  } catch (e) {
    // Ошибки полей приходят как «0.threshold» — номер изменения в запросе
    const mapped = {}
    for (const [field, message] of Object.entries(e.fields || {})) {
      const key = body[Number(field.split('.')[0])]?.key
      if (key) mapped[key] = message
    }
    serverErrors.value = mapped
  } finally {
    saving.value = false
  }
}

onBeforeRouteLeave(async () => {
  if (!dirty.value) return true
  return confirm({ title: 'Уйти без сохранения?', message: 'Изменённые правила светофора не сохранены.', confirmText: 'Уйти', danger: true })
})

// ---------- пример расчёта по текущим (несохранённым) правилам ----------
const lightOf = (key) => draft.value.find((r) => r.key === key)?.light || 'gray'
const example = computed(() => {
  const parts = [
    { key: 'status', label: 'Статус «Завершено»', light: lightOf('status:Завершено') },
    { key: 'nda', label: 'NDA подписан', light: lightOf('nda:yes') },
    { key: 'agreement', label: 'Соглашение не подписано', light: lightOf('agreement:no') },
    { key: 'cert_age', label: 'Сертификат устаревает', light: lightOf('cert_age:aging') },
  ]
  return { parts, result: worst(parts.map((p) => p.light)) }
})
</script>

<template>
  <div class="page">
    <PageHeader title="Светофор партнёрств" description="Как оценивается каждая запись реестра технологических партнёрств">
      <router-link to="/product" class="btn btn-ghost"><AppIcon name="grid" :size="15" />Дашборд</router-link>
      <template v-if="canManage">
        <button v-if="dirty" class="btn" type="button" :disabled="saving" @click="discard">Отменить</button>
        <button class="btn btn-primary" type="button" :disabled="!dirty || hasErrors || saving" @click="save">
          <AppIcon name="check" :size="15" />{{ saving ? 'Сохранение…' : dirty ? `Сохранить (${changes.length})` : 'Сохранить' }}
        </button>
      </template>
    </PageHeader>

    <p v-if="!canManage" class="readonly card"><AppIcon name="lock" :size="15" />Изменять правила могут пользователи с уровнем доступа «Управление». Вы видите действующие настройки.</p>

    <section class="card explain">
      <div class="explain-text">
        <h3>Как считается оценка записи</h3>
        <p>Каждое партнёрство получает четыре частные оценки: по статусу, NDA, соглашению и сроку сертификата. Итоговый цвет записи — <b>худший</b> из них: «Критично» важнее «Внимания», «Внимание» важнее «Нормы».</p>
        <p class="muted">Части с цветом «Нет оценки» не учитываются. Срок сертификата не оценивается, если дата не указана. Если не оценена ни одна часть, у записи нет оценки.</p>
      </div>
      <div class="example" aria-label="Пример расчёта по текущим правилам">
        <span class="example-title">Пример по текущим правилам</span>
        <ul>
          <li v-for="p in example.parts" :key="p.key"><LightBadge :light="p.light" dot /><span>{{ p.label }}</span><span class="example-light">{{ LIGHT_LABELS[p.light] }}</span></li>
        </ul>
        <div class="example-result"><span>Итог — худшая оценка</span><LightBadge :light="example.result" /></div>
      </div>
    </section>

    <div v-if="loading" class="groups">
      <div v-for="i in 4" :key="i" class="skeleton" style="height: 180px" />
    </div>
    <EmptyState v-else-if="loadError" icon="alert" title="Не удалось загрузить правила" :text="loadError">
      <button class="btn" type="button" @click="load">Повторить</button>
    </EmptyState>

    <div v-else class="groups">
      <section v-for="g in groups" :key="g.key" class="card group">
        <header class="group-head">
          <span class="group-icon"><AppIcon :name="ICONS[g.key] || 'traffic'" :size="16" /></span>
          <div>
            <h3>{{ g.label }}</h3>
            <p class="hint">{{ HINTS[g.key] }}</p>
          </div>
          <span class="spacer" />
          <span class="part-no muted">Часть {{ LIGHT_PARTS.findIndex((p) => p.key === g.key) + 1 }} из 4</span>
        </header>
        <ul class="rules">
          <li v-for="r in g.rules" :key="r.key" class="rule" :class="{ changed: changedKeys.has(r.key) }">
            <div class="rule-info">
              <div class="rule-label">
                <span>{{ g.key === 'cert_age' ? shortRuleLabel(r.label, g.label) : r.label }}</span>
                <span v-if="changedKeys.has(r.key)" class="changed-mark" title="Изменено, не сохранено">изменено</span>
              </div>
              <div class="rule-sub">
                <span v-if="statOf(r.key)" class="num">{{ formatNumber(statOf(r.key).count) }} {{ countWord(statOf(r.key).count) }} · {{ formatNumber(statOf(r.key).share) }}%</span>
              </div>
              <span v-if="errors[r.key]" class="error">{{ errors[r.key] }}</span>
            </div>
            <div class="rule-threshold">
              <label v-if="r.key === 'cert_age:fresh' || r.key === 'cert_age:aging'" class="threshold">
                <span>{{ thresholdPrefix(r.key) }}</span>
                <input class="input input-sm num" :class="{ invalid: errors[r.key] }" type="number" min="0.5" max="50" step="0.5" :value="r.threshold" :disabled="!canManage" :aria-label="`${r.label}: порог в годах`" @input="onThreshold(r, $event)" />
                <span>{{ yearsWord(r.threshold) }}</span>
              </label>
              <span v-else-if="r.key === 'cert_age:stale'" class="threshold">{{ certAgeRange(r.key, draft) }}</span>
            </div>
            <div v-if="canManage" class="picker" role="radiogroup" :aria-label="r.label">
              <button v-for="c in LIGHT_CHOICES" :key="c.value" type="button" role="radio" :aria-checked="r.light === c.value" :class="[c.value, { active: r.light === c.value }]" :title="c.label" @click="setLight(r, c.value)">
                <span class="pdot" />{{ c.label }}
              </button>
            </div>
            <LightBadge v-else :light="r.light" />
          </li>
        </ul>
        <p v-if="g.key === 'status' && otherStatuses?.count" class="group-note"><AppIcon name="info" :size="13" />Статусы без правила не оцениваются: {{ formatNumber(otherStatuses.count) }} {{ countWord(otherStatuses.count) }}</p>
        <p v-if="g.key === 'cert_age' && total !== null" class="group-note muted"><AppIcon name="info" :size="13" />Число записей — по сохранённым порогам; новые пороги применятся после сохранения</p>
      </section>
    </div>
  </div>
</template>

<style scoped>
.readonly { display: flex; align-items: center; gap: 10px; padding: 12px 16px; font-size: var(--fs-sm); color: var(--text-2); background: var(--surface-2); }
.readonly :deep(svg) { color: var(--muted); }

.explain { display: grid; grid-template-columns: minmax(0, 1.25fr) minmax(280px, 1fr); gap: var(--sp-6); padding: var(--sp-5); }
.explain-text { display: flex; flex-direction: column; gap: 8px; }
.explain-text h3 { font-size: var(--fs-md); font-weight: 620; }
.explain-text p { font-size: var(--fs-sm); color: var(--text-2); max-width: 640px; line-height: 1.55; }
.explain-text p.muted { color: var(--muted); }
.example { padding: 14px 16px; border: 1px solid var(--border); border-radius: var(--radius); background: var(--surface-2); }
.example-title { display: block; font-size: var(--fs-xs); text-transform: uppercase; letter-spacing: .05em; color: var(--muted); font-weight: 620; margin-bottom: 10px; }
.example ul { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 7px; }
.example li { display: grid; grid-template-columns: 8px 1fr auto; align-items: center; gap: 10px; font-size: var(--fs-sm); color: var(--text-2); }
.example-light { font-size: var(--fs-xs); color: var(--muted); }
.example-result { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-top: 10px; padding-top: 10px; border-top: 1px solid var(--border); font-size: var(--fs-sm); font-weight: 600; }
@media (max-width: 960px) { .explain { grid-template-columns: minmax(0, 1fr); } }

.groups { display: flex; flex-direction: column; gap: var(--sp-4); }
.group { padding: var(--sp-5) var(--sp-5) var(--sp-4); display: flex; flex-direction: column; gap: var(--sp-3); }
.group-head { display: flex; align-items: flex-start; gap: 12px; }
.group-icon { width: 32px; height: 32px; flex: 0 0 32px; display: grid; place-items: center; border-radius: 9px; background: var(--surface-3); color: var(--text-2); }
.group-head h3 { font-size: var(--fs-md); font-weight: 620; }
.group-head .hint { font-size: var(--fs-xs); color: var(--muted); margin-top: 2px; }
.part-no { font-size: var(--fs-xs); white-space: nowrap; }

.rules { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; }
.rule { display: grid; grid-template-columns: minmax(200px, 1fr) minmax(0, auto) auto; align-items: center; gap: 10px 24px; padding: 11px 12px; margin: 0 -12px; border-top: 1px solid var(--border); transition: background var(--t-fast); }
.rule:hover { background: var(--row-hover); }
.rule:first-child { border-top: 0; }
.rule.changed { background: color-mix(in srgb, var(--accent) 6%, transparent); border-radius: var(--radius-sm); }
.rule-info { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.rule-threshold { justify-self: end; }
@media (max-width: 900px) { .rule { grid-template-columns: minmax(0, 1fr); } .rule-threshold { justify-self: start; } }
.rule-label { display: flex; align-items: center; gap: 8px; font-weight: 560; }
.changed-mark { font-size: 10.5px; font-weight: 620; text-transform: uppercase; letter-spacing: .05em; color: var(--accent); }
.rule-sub { display: flex; flex-wrap: wrap; gap: 2px 12px; font-size: var(--fs-xs); color: var(--muted); }
.threshold { display: inline-flex; align-items: center; gap: 8px; font-size: var(--fs-sm); color: var(--text-2); white-space: nowrap; }
.threshold .input { width: 76px; text-align: right; }
.error { font-size: var(--fs-xs); color: var(--light-red); }

.picker { display: inline-flex; padding: 3px; gap: 2px; border-radius: 10px; background: var(--surface-3); border: 1px solid var(--border); flex-wrap: wrap; }
.picker button { display: inline-flex; align-items: center; gap: 6px; height: 28px; padding: 0 10px; border: 0; border-radius: 7px; background: transparent; color: var(--text-2); font-size: var(--fs-sm); font-weight: 540; cursor: pointer; white-space: nowrap; transition: all var(--t-fast); }
.picker button:hover { color: var(--text); }
.picker button.active { background: var(--bg-elevated); color: var(--text); box-shadow: var(--shadow-sm); font-weight: 620; }
.pdot { width: 8px; height: 8px; border-radius: 50%; background: var(--light-gray); opacity: .55; transition: opacity var(--t-fast); }
.picker button.active .pdot, .picker button:hover .pdot { opacity: 1; }
.green .pdot { background: var(--light-green); }
.yellow .pdot { background: var(--light-yellow); }
.red .pdot { background: var(--light-red); }
.gray .pdot { background: var(--light-gray); }
.picker button.active.green { box-shadow: var(--shadow-sm), inset 0 0 0 1px color-mix(in srgb, var(--light-green) 45%, transparent); }
.picker button.active.yellow { box-shadow: var(--shadow-sm), inset 0 0 0 1px color-mix(in srgb, var(--light-yellow) 50%, transparent); }
.picker button.active.red { box-shadow: var(--shadow-sm), inset 0 0 0 1px color-mix(in srgb, var(--light-red) 45%, transparent); }
.group-note { display: flex; align-items: center; gap: 6px; font-size: var(--fs-xs); color: var(--text-2); }
.group-note.muted { color: var(--muted); }
</style>
