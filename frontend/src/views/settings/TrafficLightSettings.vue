<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRoute } from 'vue-router'
import AppIcon from '@/components/ui/AppIcon.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import SegmentedControl from '@/components/ui/SegmentedControl.vue'
import ToggleSwitch from '@/components/admin/ToggleSwitch.vue'
import ThresholdScale from '@/components/admin/ThresholdScale.vue'
import { commonApi } from '@/api/services'
import { useAsync } from '@/composables/useAsync'
import { confirm } from '@/composables/useConfirm'
import { toastOk } from '@/composables/useToast'
import { useAppStore } from '@/stores/app'
import { groupRules, ruleBody, ruleDirty, ruleProblem } from '@/domain/admin'
import { DIRECTION_LABELS } from '@/utils/lights'
import { formatDateTime, formatRelative, plural } from '@/utils/format'

/** Пороги светофора метрик службы (персонал — по месяцам, техподдержка — по неделям). */
const route = useRoute()
const app = useAppStore()
const service = computed(() => String(route.params.service || 'hr'))
const isTech = computed(() => service.value === 'tech')
const serviceTitle = computed(() => app.service(service.value)?.title || (isTech.value ? 'Техническая поддержка' : 'Служба персонала'))

const DIRECTION_OPTIONS = [
  { value: 'lower_is_better', label: DIRECTION_LABELS.lower_is_better },
  { value: 'higher_is_better', label: DIRECTION_LABELS.higher_is_better },
]
const STATUS_OPTIONS = [{ value: 'all', label: 'Все' }, { value: 'on', label: 'Включённые' }, { value: 'off', label: 'Выключенные' }]

const asText = (v) => (v === null || v === undefined ? '' : String(v).replace('.', ','))
function toDraft(rule) {
  return { ...rule, green_threshold: asText(rule.green_threshold), yellow_threshold: asText(rule.yellow_threshold), _saved: rule, _saving: false, _error: '' }
}

const rules = ref([])
const { loading, error, reload } = useAsync(async () => {
  const list = await commonApi.lightRules(service.value)
  rules.value = list.map(toDraft)
  return list
}, { immediate: false })
watch(service, () => reload(), { immediate: true })

const search = ref('')
const status = ref('all')
const filtered = computed(() => {
  const q = search.value.trim().toLowerCase()
  return rules.value.filter((r) => (!q || r.label.toLowerCase().includes(q) || r.metric_key.includes(q))
    && (status.value === 'all' || (status.value === 'on') === !!r._saved.enabled))
})
const groups = computed(() => groupRules(filtered.value))
const enabledCount = computed(() => rules.value.filter((r) => r._saved.enabled).length)
const dirtyRules = computed(() => rules.value.filter(isDirty))

function isDirty(r) {
  return ruleDirty(r, r._saved)
}
function message(r) {
  return r._error || ruleProblem(r)
}
function touch(r) {
  r._error = ''
}
/** Знак сравнения для границ: зона «не хуже границы». */
const op = (r) => (r.direction === 'lower_is_better' ? '≤' : '≥')

async function save(r, { quiet = false } = {}) {
  r._saving = true
  r._error = ''
  try {
    const out = await commonApi.saveLightRule(service.value, r.metric_key, ruleBody(r))
    Object.assign(r, toDraft(out))
    if (!quiet) toastOk(`«${r.label}»: правило сохранено`)
    return true
  } catch (e) {
    r._error = e.message
    return false
  } finally {
    r._saving = false
  }
}
async function saveAll() {
  let ok = 0
  let failed = 0
  for (const r of [...dirtyRules.value]) (await save(r, { quiet: true })) ? ok++ : failed++
  if (ok) toastOk(`Сохранено ${ok} ${plural(ok, ['правило', 'правила', 'правил'])}${failed ? `, с ошибками: ${failed}` : ''}`)
}
function discard() {
  rules.value = rules.value.map((r) => toDraft(r._saved))
}

// Несохранённые изменения не теряются молча
onBeforeRouteLeave(async () => {
  if (!dirtyRules.value.length) return true
  return confirm({ title: 'Уйти без сохранения?', message: `Не сохранено правил: ${dirtyRules.value.length}. Изменения будут потеряны.`, confirmText: 'Уйти' })
})
function beforeUnload(event) {
  if (dirtyRules.value.length) event.preventDefault()
}
onMounted(() => window.addEventListener('beforeunload', beforeUnload))
onBeforeUnmount(() => window.removeEventListener('beforeunload', beforeUnload))
</script>

<template>
  <div class="page">
    <PageHeader :title="`Светофор — ${serviceTitle}`"
                :description="isTech ? 'Пороги показателей недельного отчёта: зелёный — норма, жёлтый — внимание, красный — критично' : 'Пороги метрик по месяцам: зелёный — норма, жёлтый — внимание, красный — критично'">
      <template v-if="dirtyRules.length">
        <button class="btn btn-ghost" type="button" @click="discard">Отменить изменения</button>
        <button class="btn btn-primary" type="button" @click="saveAll"><AppIcon name="check" :size="15" />Сохранить все ({{ dirtyRules.length }})</button>
      </template>
    </PageHeader>

    <div class="notes">
      <div class="note">
        <AppIcon name="traffic" :size="16" />
        <p><b>Как читается правило.</b> «Меньше — лучше»: зелёный, если значение не больше границы зелёного; жёлтый — не больше границы жёлтого; иначе красный. «Больше — лучше» — наоборот. Выключенное правило не оценивает метрику.</p>
      </div>
      <div v-if="isTech" class="note accent">
        <AppIcon name="calendar" :size="16" />
        <p><b>Пороги — за одну неделю.</b> Если на дашборде выбран период из N недель, сумма за период сравнивается с порогом × N.</p>
      </div>
    </div>

    <div class="card toolbar">
      <label class="search"><AppIcon name="search" :size="14" /><input v-model="search" type="search" placeholder="Название метрики" aria-label="Поиск метрики" /></label>
      <SegmentedControl v-model="status" :options="STATUS_OPTIONS" />
      <span class="spacer" />
      <span v-if="rules.length" class="muted summary">Включено {{ enabledCount }} из {{ rules.length }}</span>
    </div>

    <div v-if="loading && !rules.length" class="stack">
      <div v-for="i in 3" :key="i" class="card skeleton" style="height: 180px" />
    </div>
    <EmptyState v-else-if="error && !rules.length" icon="alert" title="Не удалось загрузить правила" :text="error.message">
      <button class="btn btn-sm" type="button" @click="reload">Повторить</button>
    </EmptyState>
    <EmptyState v-else-if="!groups.length" compact icon="search" title="Метрики не найдены" text="Измените поиск или фильтр." />

    <section v-for="g in groups" :key="g.name" class="card group">
      <header class="card-head">
        <h3>{{ g.name }}</h3>
        <span class="hint">включено {{ g.items.filter((r) => r._saved.enabled).length }} из {{ g.items.length }}</span>
      </header>
      <div class="rules" role="table" :aria-label="g.name">
        <div class="rule head" role="row">
          <span class="c-metric" role="columnheader">Метрика</span>
          <span class="c-on" role="columnheader">Вкл.</span>
          <span class="c-dir" role="columnheader">Направление</span>
          <span class="c-green" role="columnheader" title="Граница зелёной зоны"><i class="dot green" />Зелёный</span>
          <span class="c-yellow" role="columnheader" title="Граница жёлтой зоны"><i class="dot yellow" />Жёлтый</span>
          <span class="c-scale" role="columnheader">Шкала{{ isTech ? ' за неделю' : '' }}</span>
        </div>
        <div v-for="r in g.items" :key="r.metric_key" class="rule" role="row" :class="{ off: !r.enabled, dirty: isDirty(r) }">
          <div class="c-metric metric" role="cell">
            <span class="m-label">{{ r.label }}</span>
            <span class="m-meta">
              <template v-if="r.unit">{{ r.unit }}</template>
              <template v-if="r.unit && r._saved.updated_at"> · </template>
              <span v-if="r._saved.updated_at" :title="formatDateTime(r._saved.updated_at)">изменено {{ formatRelative(r._saved.updated_at) }}</span>
            </span>
          </div>
          <div class="c-on" role="cell">
            <ToggleSwitch v-model="r.enabled" :title="r.enabled ? 'Правило включено' : 'Правило выключено'" @update:modelValue="touch(r)" />
          </div>
          <div class="c-dir" role="cell">
            <SegmentedControl v-model="r.direction" size="sm" :options="DIRECTION_OPTIONS" @update:modelValue="touch(r)" />
          </div>
          <div class="c-green" role="cell">
            <label class="thr" :class="{ invalid: r._error || (ruleProblem(r) && isDirty(r)) }" :title="`Зелёный: значение ${op(r)} границы`">
              <span class="op green">{{ op(r) }}</span>
              <input v-model="r.green_threshold" inputmode="decimal" :aria-label="`${r.label}: граница зелёного`" placeholder="—" @input="touch(r)" />
              <span v-if="r.unit" class="u">{{ r.unit }}</span>
            </label>
          </div>
          <div class="c-yellow" role="cell">
            <label class="thr" :class="{ invalid: r._error || (ruleProblem(r) && isDirty(r)) }" :title="`Жёлтый: значение ${op(r)} границы`">
              <span class="op yellow">{{ op(r) }}</span>
              <input v-model="r.yellow_threshold" inputmode="decimal" :aria-label="`${r.label}: граница жёлтого`" placeholder="—" @input="touch(r)" />
              <span v-if="r.unit" class="u">{{ r.unit }}</span>
            </label>
          </div>
          <div class="c-scale" role="cell"><ThresholdScale :rule="r" :unit="r.unit" /></div>
          <div class="c-save" role="cell">
            <button v-if="isDirty(r)" class="btn btn-sm btn-primary" type="button" :disabled="r._saving" @click="save(r)">
              {{ r._saving ? 'Сохранение…' : 'Сохранить' }}
            </button>
          </div>
          <p v-if="message(r) && (isDirty(r) || r._error)" class="msg" :class="{ server: r._error }" role="alert">
            <AppIcon name="alert" :size="13" />{{ message(r) }}
          </p>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.notes { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 12px; }
.note { display: flex; gap: 10px; padding: 12px 14px; border-radius: 12px; background: var(--surface-2); border: 1px solid var(--border); color: var(--muted); font-size: var(--fs-sm); line-height: 1.45; }
.note :deep(svg) { margin-top: 2px; }
.note p { color: var(--text-2); }
.note b { color: var(--text); font-weight: 620; }
.note.accent { background: color-mix(in srgb, var(--accent) 7%, var(--surface)); border-color: color-mix(in srgb, var(--accent) 25%, var(--border)); color: var(--accent); }
.toolbar { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; padding: 12px 16px; }
.search { display: flex; align-items: center; gap: 8px; height: 32px; padding: 0 10px; border: 1px solid var(--border-strong); border-radius: var(--radius); color: var(--muted); min-width: 240px; background: var(--surface); }
.search input { border: 0; outline: 0; background: transparent; width: 100%; color: var(--text); font-size: var(--fs-sm); }
.search:focus-within { border-color: var(--accent); box-shadow: 0 0 0 3px var(--focus); }
.summary { font-size: var(--fs-sm); }
.group .card-head { padding-bottom: 6px; }
.rules { display: flex; flex-direction: column; padding: 0 0 6px; container-type: inline-size; }
.rule {
  display: grid; align-items: center; column-gap: 12px; row-gap: 6px; padding: 10px 20px; border-top: 1px solid var(--border);
  grid-template-columns: minmax(180px, 1.2fr) 36px 248px 112px 112px minmax(150px, 1fr) 92px;
  grid-template-areas: "metric on dir green yellow scale save";
}
.c-metric { grid-area: metric; } .c-on { grid-area: on; } .c-dir { grid-area: dir; } .c-green { grid-area: green; }
.c-yellow { grid-area: yellow; } .c-scale { grid-area: scale; min-width: 0; } .c-save { grid-area: save; }
.rule :deep(.seg) { flex-wrap: nowrap; }
/* Раскладка строки — по ширине списка правил (container query), а не окна */
@container (max-width: 1060px) {
  .rule {
    grid-template-columns: minmax(170px, 1fr) 36px 248px 112px 112px 92px;
    grid-template-areas: "metric on dir green yellow save" "metric on . scale scale save";
  }
  .rule.head { grid-template-areas: "metric on dir green yellow save"; }
  .rule.head .c-scale { display: none; }
  .rule:not(.head) .c-scale { padding-top: 2px; }
}
@container (max-width: 880px) {
  /* Узко (телефон, планшет): показатель сверху, переключатели и пороги — строками под ним */
  .rule {
    grid-template-columns: 36px minmax(0, 1fr) 36px minmax(0, 1fr);
    grid-template-areas: "on metric metric metric" "dir dir dir dir" "green green yellow yellow" "scale scale scale scale" "save save save save";
    padding: 12px 14px;
  }
  .rule.head { display: none; }
  .rule:not(.head) .c-scale { padding-top: 0; }
  .rule :deep(.seg) { width: 100%; }
  .rule :deep(.seg button) { flex: 1; }
  .c-save { justify-self: end; }
}
.rule.head { border-top: 0; padding-top: 4px; padding-bottom: 6px; font-size: var(--fs-xs); font-weight: 620; color: var(--muted); text-transform: uppercase; letter-spacing: .04em; }
.rule.head span { display: inline-flex; align-items: center; gap: 6px; white-space: nowrap; }
.rule.dirty { background: color-mix(in srgb, var(--light-yellow) 6%, transparent); }
.dot { width: 7px; height: 7px; border-radius: 50%; }
.dot.green { background: var(--light-green); }
.dot.yellow { background: var(--light-yellow); }
.metric { display: flex; flex-direction: column; min-width: 0; line-height: 1.3; }
.m-label { font-weight: 560; color: var(--text); }
.off .m-label { color: var(--text-2); font-weight: 520; }
.m-meta { font-size: var(--fs-xs); color: var(--muted); }
.thr { display: flex; align-items: center; height: 32px; padding: 0 8px; gap: 6px; border: 1px solid var(--border-strong); border-radius: var(--radius); background: var(--surface); transition: border-color var(--t-fast), box-shadow var(--t-fast); }
.thr:focus-within { border-color: var(--accent); box-shadow: 0 0 0 3px var(--focus); }
.thr.invalid { border-color: var(--light-red); }
.thr input { flex: 1; min-width: 0; width: 100%; border: 0; outline: 0; background: transparent; color: var(--text); font-size: var(--fs-sm); font-variant-numeric: tabular-nums; text-align: right; }
.op { font-size: var(--fs-sm); font-weight: 650; }
.op.green { color: var(--light-green); }
.op.yellow { color: color-mix(in srgb, var(--light-yellow) 85%, var(--text)); }
.u { font-size: var(--fs-xs); color: var(--muted); white-space: nowrap; }
.off .thr { background: var(--surface-2); }
.c-save .btn { width: 100%; }
.msg { grid-column: 1 / -1; display: flex; align-items: center; gap: 6px; margin: 0; font-size: var(--fs-xs); color: color-mix(in srgb, var(--light-yellow) 80%, var(--text)); }
.msg.server { color: var(--light-red); }
</style>
