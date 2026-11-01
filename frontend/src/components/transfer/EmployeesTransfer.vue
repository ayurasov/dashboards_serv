<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import SegmentedControl from '@/components/ui/SegmentedControl.vue'
import PlanChips from './PlanChips.vue'
import TransferBanner from './TransferBanner.vue'
import TransferFile from './TransferFile.vue'
import { orgApi } from '@/api/org'
import { useAuthStore } from '@/stores/auth'
import {
  CHOICE_LABELS, NEW_USER_MODES, PLAN_ACTIONS, PLAN_FILTERS, customValueFor, decisionFor, displayValue, employeeChips,
  filterEmployeeRecords, visibleChoices, withBulkChoice, withFieldChoice, withIdentity,
} from '@/domain/org'

/**
 * Сотрудники: выгрузка (Excel, CSV, JSON) и загрузка с разбором различий. Сервер строит план;
 * администратор решает каждое различие — значение системы, из файла, объединение или своё — и
 * отвечает, тот же ли это человек, если email новый, а логин занят. Пустое в файле не стирает.
 */
const emit = defineEmits(['applied'])
const auth = useAuthStore()
const canUsers = computed(() => auth.hasCapability('users.manage'))

// ---------------------------------------------------------------- выгрузка
const FORMATS = [{ value: 'xlsx', label: 'Excel' }, { value: 'csv', label: 'CSV' }, { value: 'json', label: 'JSON' }]
const format = ref('xlsx')
const inactive = ref(true)
const exporting = ref(false)
async function download() {
  exporting.value = true
  try { await orgApi.exportEmployees({ format: format.value, inactive: inactive.value }) } catch {} finally { exporting.value = false }
}

// ---------------------------------------------------------------- загрузка
const file = ref(null)
const newUsers = ref('no_access')
const decisions = ref({})
const plan = ref(null)
const result = ref(null)
const busy = ref('')
const error = ref('')
const filter = ref('changes')
const PAGE = 50
const limit = ref(PAGE)

watch(file, () => {
  plan.value = null
  result.value = null
  decisions.value = {}
  error.value = ''
})
watch(newUsers, () => { if (plan.value && !result.value) check() })

let seq = 0
async function run(apply) {
  if (!file.value) return null
  const id = ++seq
  busy.value = apply ? 'apply' : 'check'
  error.value = ''
  try {
    const response = await orgApi.importEmployees({ file: file.value, apply, newUsers: newUsers.value, decisions: decisions.value })
    return id === seq ? response : null
  } catch (e) {
    if (id === seq) error.value = e.message
    return null
  } finally {
    if (id === seq) busy.value = ''
  }
}
async function check() {
  clearTimeout(timer)
  result.value = null
  const next = await run(false)
  if (next) plan.value = next
}
let timer = null
function recheck(delay = 0) {
  clearTimeout(timer)
  timer = setTimeout(check, delay)
}
onBeforeUnmount(() => clearTimeout(timer))

async function apply() {
  clearTimeout(timer)
  const applied = await run(true)
  if (!applied) return
  if (applied.rejected) {
    plan.value = applied
    filter.value = 'errors'
    return
  }
  result.value = { create: applied.summary.create, update: applied.summary.update }
  emit('applied')
  const fresh = await run(false)
  if (fresh) plan.value = fresh
}

function choose(record, conflict, choice) {
  const value = choice === 'custom' ? customValueFor(decisions.value, record, conflict) : undefined
  decisions.value = withFieldChoice(decisions.value, record.key, conflict.field, choice, value)
  recheck()
}
function setCustom(record, conflict, value) {
  decisions.value = withFieldChoice(decisions.value, record.key, conflict.field, 'custom', value)
  recheck(450)
}
function setIdentity(record, identity) {
  decisions.value = withIdentity(decisions.value, record.key, identity)
  recheck()
}
function bulk(choice) {
  decisions.value = withBulkChoice(decisions.value, plan.value, choice)
  recheck()
}

const chips = computed(() => employeeChips(plan.value?.summary))
const records = computed(() => filterEmployeeRecords(plan.value?.records || [], filter.value))
const shown = computed(() => records.value.slice(0, limit.value))
watch(filter, () => { limit.value = PAGE })
const status = (r) => (r.unresolved ? { label: 'Нужно решение', tone: 'red' } : r.errors.length ? { label: 'Ошибка', tone: 'red' } : PLAN_ACTIONS[r.action] || PLAN_ACTIONS.unchanged)
const modes = computed(() => NEW_USER_MODES.map((m) => (m.value === 'active' ? { ...m, label: 'Активные (вход по домену)' } : m)))
</script>

<template>
  <div class="transfer">
    <section class="card block">
      <div class="block-head">
        <span class="b-icon"><AppIcon name="download" :size="18" /></span>
        <div class="b-text">
          <h2>Выгрузить сотрудников</h2>
          <p>Email, логин, ФИО, должность, телефон, подразделение, явный руководитель, «первое лицо», «Руководит», роль, профиль доступа, активность, способ входа, внешний ID. Пароли не выгружаются.</p>
        </div>
      </div>
      <div class="block-body export-row">
        <SegmentedControl v-model="format" :options="FORMATS" aria-label="Формат файла" />
        <label class="check"><input v-model="inactive" type="checkbox" data-testid="employees-inactive" />Включая отключённых</label>
        <span class="spacer" />
        <button type="button" class="btn" :disabled="exporting" data-testid="employees-export" @click="download">
          <AppIcon name="download" :size="15" />{{ exporting ? 'Готовлю файл…' : 'Скачать' }}
        </button>
      </div>
    </section>

    <section class="card block">
      <div class="block-head">
        <span class="b-icon"><AppIcon name="upload" :size="18" /></span>
        <div class="b-text">
          <h2>Загрузить сотрудников</h2>
          <p>Excel, CSV или JSON со столбцами выгрузки (обязателен email). Сотрудники сопоставляются по email. Если значения в файле и в системе различаются, вы решаете, что оставить; пустое в файле ничего не стирает. Профиль доступа указывается названием.</p>
        </div>
      </div>
      <div class="block-body">
        <TransferFile v-model="file" accept=".xlsx,.csv,.json" testid="employees-file" />
        <fieldset class="modes">
          <legend>Новые сотрудники</legend>
          <label v-for="m in modes" :key="m.value" class="mode" :class="{ on: newUsers === m.value }">
            <input v-model="newUsers" type="radio" name="new-users" :value="m.value" :data-testid="`new-users-${m.value}`" />
            <span><strong>{{ m.label }}</strong><small>{{ m.hint }}</small></span>
          </label>
        </fieldset>
        <p v-if="newUsers === 'active' && !canUsers" class="note-warn"><AppIcon name="info" :size="14" />Вход по домену разрешает ведущий пользователей — без этого полномочия новые сотрудники будут без доступа.</p>
        <p v-if="error" class="form-error" role="alert"><AppIcon name="alert" :size="14" />{{ error }}</p>
        <div class="actions">
          <button type="button" class="btn btn-primary" :disabled="!file || !!busy" data-testid="employees-check" @click="check">
            <AppIcon name="search" :size="15" />{{ busy === 'check' && !plan ? 'Проверяю…' : 'Проверить' }}
          </button>
          <span class="muted">Проверка ничего не записывает.</span>
        </div>
      </div>
    </section>

    <TransferBanner v-if="result" title="Сотрудники загружены" :text="`Новых: ${result.create} · обновлено: ${result.update}`" data-testid="employees-applied" />

    <section v-if="plan" class="card plan" data-testid="employees-plan">
      <header class="plan-head">
        <div>
          <h2>{{ result ? 'Сотрудники после загрузки' : 'Что изменится' }}<span v-if="busy === 'check'" class="recalc">пересчёт…</span></h2>
          <p class="muted">{{ file?.name }}</p>
        </div>
        <PlanChips :chips="chips" />
      </header>

      <TransferBanner v-if="plan.rejected" tone="error" :title="plan.detail || 'Ничего не записано'" text="Ответьте на вопросы и исправьте ошибки в отмеченных записях, затем примените снова." class="inset" />
      <TransferBanner v-if="plan.notes.length" tone="info" title="Обратите внимание" class="inset">
        <ul class="notes"><li v-for="n in plan.notes" :key="n">{{ n }}</li></ul>
      </TransferBanner>

      <div v-if="plan.departments.length" class="plan-block">
        <h3>Будут созданы подразделения</h3>
        <ul class="list-inline"><li v-for="d in plan.departments" :key="d.key">{{ d.path }}</li></ul>
      </div>

      <div class="plan-block">
        <div class="block-title">
          <SegmentedControl v-model="filter" :options="PLAN_FILTERS" size="sm" />
          <div v-if="plan.summary.conflicts" class="bulk">
            <span class="muted">Во всех различиях:</span>
            <button type="button" class="btn btn-sm" data-testid="bulk-current" @click="bulk('current')">оставить значения системы</button>
            <button type="button" class="btn btn-sm" data-testid="bulk-incoming" @click="bulk('incoming')">взять из файла</button>
          </div>
        </div>

        <div v-if="shown.length" class="records">
          <article v-for="r in shown" :key="`${r.key}-${r.line}`" class="record" :class="{ attention: r.unresolved || r.errors.length }" :data-record="r.email">
            <header class="record-head">
              <div class="who">
                <strong>{{ r.name || r.email || 'Без имени' }}</strong>
                <small>{{ r.email || 'email не указан' }} · строка {{ r.line }}</small>
              </div>
              <span class="badge" :class="`badge-${status(r).tone}`">{{ status(r).label }}</span>
            </header>

            <div v-if="r.identity" class="identity" data-testid="identity-question">
              <p>Сотрудника с таким email нет, но логин занят: <b>{{ r.identity.name }}</b><template v-if="r.identity.email"> ({{ r.identity.email }})</template>, логин <code>{{ r.identity.login }}</code>. Это тот же человек?</p>
              <SegmentedControl :model-value="decisions[r.key]?.identity || null" size="sm"
                                :options="[{ value: 'same', label: 'Тот же человек — обновить' }, { value: 'new', label: 'Новый сотрудник' }]"
                                @update:model-value="setIdentity(r, $event)" />
            </div>

            <div v-if="r.conflicts.length" class="table-wrap conflicts-wrap">
              <table class="table table-compact conflicts">
                <thead><tr><th>Поле</th><th>В системе</th><th>В файле</th><th>Решение</th></tr></thead>
                <tbody>
                  <tr v-for="c in r.conflicts" :key="c.field" :data-field="c.field">
                    <td class="field-label">{{ c.label }}<small v-if="c.note">{{ c.note }}</small></td>
                    <td :class="{ chosen: decisionFor(decisions, r, c) === 'current' }">{{ displayValue(c.current) }}</td>
                    <td :class="{ chosen: decisionFor(decisions, r, c) === 'incoming' }">{{ displayValue(c.incoming) }}</td>
                    <td class="decision"><div class="decision-inner">
                      <div class="choices" role="radiogroup" :aria-label="`Решение: ${c.label}`">
                        <button v-for="choice in visibleChoices(c)" :key="choice" type="button" role="radio" :aria-checked="decisionFor(decisions, r, c) === choice"
                                :class="{ active: decisionFor(decisions, r, c) === choice }" :data-choice="choice" @click="choose(r, c, choice)">
                          {{ CHOICE_LABELS[choice] }}
                        </button>
                      </div>
                      <small v-if="decisionFor(decisions, r, c) === 'merge'" class="muted">{{ displayValue(c.merged) }}</small>
                      <template v-if="decisionFor(decisions, r, c) === 'custom'">
                        <input class="input input-sm" :value="customValueFor(decisions, r, c)" :aria-label="`Своё значение: ${c.label}`" data-testid="custom-value"
                               @input="setCustom(r, c, $event.target.value)" />
                        <small v-if="c.kind === 'list'" class="muted">Пути через «|», основное — с пометкой «(основной)»</small>
                        <small v-else-if="c.kind === 'path'" class="muted">Путь от верхнего уровня через «/»</small>
                        <small v-else-if="c.kind === 'email'" class="muted">Email руководителя</small>
                      </template>
                    </div></td>
                  </tr>
                </tbody>
              </table>
            </div>

            <ul v-if="r.changes.length" class="lines">
              <li v-for="c in r.changes" :key="c.field"><span class="lbl">{{ c.label }}:</span> {{ displayValue(c.new) }}<span v-if="r.action !== 'create' && displayValue(c.old) === '—'" class="muted"> (в системе пусто)</span><template v-else-if="displayValue(c.old) !== '—'"> <span class="muted">вместо {{ displayValue(c.old) }}</span></template></li>
            </ul>
            <ul v-if="r.errors.length" class="lines errors"><li v-for="e in r.errors" :key="e">{{ e }}</li></ul>
            <ul v-if="r.warnings.length" class="lines warnings"><li v-for="w in r.warnings" :key="w">{{ w }}</li></ul>
          </article>
          <button v-if="records.length > shown.length" type="button" class="btn btn-ghost more" @click="limit += PAGE">
            Показать ещё {{ Math.min(PAGE, records.length - shown.length) }} из {{ records.length - shown.length }}
          </button>
        </div>
        <p v-else class="empty">{{ filter === 'errors' ? 'Ошибок нет' : filter === 'changes' ? 'Изменений нет — данные в файле совпадают с системой' : 'В файле нет записей' }}</p>
      </div>

      <footer class="plan-foot">
        <button type="button" class="btn btn-primary" :disabled="!plan.can_apply || !!busy || !!result" data-testid="employees-apply" @click="apply">
          <AppIcon name="check" :size="15" />{{ busy === 'apply' ? 'Применяю…' : 'Применить' }}
        </button>
        <span class="muted">
          <template v-if="result">Изменения применены.</template>
          <template v-else-if="!plan.can_apply">Ответьте на вопросы («Нужно решение») и исправьте ошибки.</template>
          <template v-else>Записи без изменений не затрагиваются; всё записывается одной операцией.</template>
        </span>
      </footer>
    </section>
  </div>
</template>

<style scoped src="./transfer.css"></style>
<style scoped>
.export-row { flex-direction: row; flex-wrap: wrap; align-items: center; gap: 12px 18px; }
.modes { border: 0; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
.modes legend { margin-bottom: 8px; font-size: var(--fs-sm); font-weight: 600; color: var(--text-2); }
.mode { display: flex; gap: 10px; align-items: flex-start; padding: 11px 12px; border: 1px solid var(--border); border-radius: 12px; cursor: pointer; transition: border-color var(--t-fast), background var(--t-fast); }
.mode:hover { border-color: var(--border-strong); }
.mode.on { border-color: var(--accent); background: color-mix(in srgb, var(--accent) 6%, transparent); box-shadow: 0 0 0 1px var(--accent); }
.mode input { margin-top: 3px; accent-color: var(--accent); }
.mode span { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.mode strong { font-size: var(--fs-sm); font-weight: 620; }
.mode small { font-size: var(--fs-xs); color: var(--muted); line-height: 1.4; }
.note-warn { display: flex; align-items: center; gap: 6px; font-size: var(--fs-sm); color: color-mix(in srgb, var(--light-yellow) 75%, var(--text)); }
.recalc { margin-left: 10px; font-size: var(--fs-xs); font-weight: 500; color: var(--muted); }
.notes { margin: 4px 0 0; padding-left: 18px; }
.bulk { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
.records { display: flex; flex-direction: column; gap: 10px; }
.record { display: flex; flex-direction: column; gap: 10px; padding: 12px 14px; border: 1px solid var(--border); border-radius: 12px; background: var(--surface); }
.record.attention { border-color: color-mix(in srgb, var(--light-red) 40%, var(--border)); background: color-mix(in srgb, var(--light-red) 3%, var(--surface)); }
.record-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.who { display: flex; flex-direction: column; min-width: 0; line-height: 1.35; }
.who strong { font-weight: 640; }
.who small { font-size: var(--fs-xs); color: var(--muted); }
.identity { display: flex; flex-direction: column; gap: 8px; padding: 10px 12px; border-radius: 10px; background: color-mix(in srgb, var(--light-yellow) 10%, transparent); font-size: var(--fs-sm); }
.identity code { font-family: var(--font-mono); font-size: var(--fs-xs); }
.conflicts-wrap { border: 1px solid var(--border); border-radius: 10px; }
.conflicts td { vertical-align: top; font-size: var(--fs-sm); overflow-wrap: anywhere; }
.conflicts td.chosen { background: color-mix(in srgb, var(--accent) 8%, transparent); font-weight: 600; }
.field-label { min-width: 120px; font-weight: 560; }
.field-label small { display: block; font-weight: 400; font-size: var(--fs-xs); color: color-mix(in srgb, var(--light-yellow) 80%, var(--text)); }
.decision { min-width: 250px; }
.decision-inner { display: flex; flex-direction: column; gap: 6px; }
.choices { display: inline-flex; flex-wrap: wrap; gap: 2px; padding: 2px; border-radius: 9px; background: var(--surface-3); border: 1px solid var(--border); align-self: flex-start; }
.choices button { height: 24px; padding: 0 9px; border: 0; border-radius: 7px; background: transparent; color: var(--text-2); font-size: var(--fs-xs); font-weight: 560; cursor: pointer; }
.choices button:hover { color: var(--text); }
.choices button.active { background: var(--bg-elevated); color: var(--text); box-shadow: var(--shadow-sm); font-weight: 650; }
.lines { margin: 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 2px; font-size: var(--fs-sm); }
.lines .lbl { color: var(--muted); }
.errors { color: var(--light-red); }
.warnings { color: color-mix(in srgb, var(--light-yellow) 80%, var(--text)); }
.more { align-self: center; }
@media (max-width: 900px) {
  .modes { grid-template-columns: 1fr; }
}
@media (max-width: 720px) {
  .conflicts thead { display: none; }
  .conflicts tr { display: grid; grid-template-columns: 1fr 1fr; }
  .conflicts td { border: 0; }
  .conflicts td.field-label, .conflicts td.decision { grid-column: 1 / -1; }
}
</style>
