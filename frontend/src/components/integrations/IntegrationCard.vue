<script setup>
import { computed, ref, watch } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import ToggleSwitch from '@/components/admin/ToggleSwitch.vue'
import TransferBanner from '@/components/transfer/TransferBanner.vue'
import CheckResult from './CheckResult.vue'
import { integrationsApi } from '@/api/integrations'
import { confirm } from '@/composables/useConfirm'
import { toastOk } from '@/composables/useToast'
import { healthInfo, kindIcon, quoted, richPreview, runCounters, runStatus, shortError } from '@/domain/integrations'
import { formatDateTime, formatNumber, formatRelative } from '@/utils/format'

/**
 * Карточка подключения: состояние, последний запуск и ошибка, «Включено» (включить можно только после
 * успешной проверки — 409 check_required: объясняем и предлагаем «Проверить»), «Проверить», действия
 * со своей кнопкой «Запустить», расписание; «Настроить», «Журнал запусков», «Удалить».
 */
const props = defineProps({
  integration: { type: Object, required: true },
  kind: { type: Object, default: null },
})
const emit = defineEmits(['edit', 'journal', 'changed', 'removed'])

const it = computed(() => props.integration)
const k = computed(() => props.kind || it.value.connector || { kind: it.value.kind, title: it.value.kind, actions: [] })
const health = computed(() => healthInfo(it.value.health))
const actions = computed(() => k.value.actions || [])
const lastRun = computed(() => it.value.last_run)
const actionLabel = (key) => actions.value.find((a) => a.key === key)?.label || key
const scheduled = computed(() => (it.value.schedule?.mode && it.value.schedule.mode !== 'off' ? it.value.schedule.actions || [] : []))

// «Включено»: своё состояние, чтобы переключатель вернулся, если включить нельзя
const enabled = ref(it.value.enabled)
watch(() => it.value.enabled, (v) => { enabled.value = v })
const needCheck = ref('')
const busy = ref('')
const check = ref(null)
const runs = ref({})

async function refresh() {
  try { emit('changed', await integrationsApi.get(it.value.id)) } catch {}
}

async function setEnabled(value) {
  enabled.value = value
  busy.value = 'enable'
  try {
    const row = await integrationsApi.update(it.value.id, { enabled: value })
    needCheck.value = ''
    toastOk(value ? `Подключение ${quoted(row.name)} включено${row.schedule_label && row.schedule_label !== 'Вручную' ? `: ${row.schedule_label.toLowerCase()}` : ''}` : `Подключение ${quoted(row.name)} выключено: по расписанию не запускается`)
    emit('changed', row)
  } catch (e) {
    enabled.value = it.value.enabled
    if (e.code === 'check_required') needCheck.value = e.message
  } finally {
    busy.value = ''
  }
}

async function runCheck() {
  busy.value = 'check'
  try {
    check.value = await integrationsApi.check(it.value.id)
    await refresh()
  } catch (e) {
    check.value = { ok: false, message: e.message, details: { code: e.code } }
  } finally {
    busy.value = ''
  }
}

async function enableAfterCheck() {
  await setEnabled(true)
}

async function run(action) {
  busy.value = `run:${action.key}`
  try {
    const result = await integrationsApi.run(it.value.id, action.key)
    runs.value = { ...runs.value, [action.key]: result }
    const status = runStatus(result)
    toastOk(`${action.label}: ${status.label.toLowerCase()}${result.message ? ` — ${result.message}` : ''}`)
    await refresh()
  } catch {} finally {
    busy.value = ''
  }
}

async function remove() {
  const ok = await confirm({
    title: `Удалить подключение ${quoted(it.value.name)}?`,
    message: 'Подключение удалится вместе с журналом запусков и сохранёнными секретами. Элементы входящих, которые оно принесло, останутся. Если нужно только остановить запуски — выключите его.',
    confirmText: 'Удалить', danger: true,
  })
  if (!ok) return
  busy.value = 'delete'
  try {
    await integrationsApi.remove(it.value.id)
    toastOk(`Подключение ${quoted(it.value.name)} удалено`)
    emit('removed', it.value)
  } catch {} finally {
    busy.value = ''
  }
}
</script>

<template>
  <article class="card icard" :class="`h-${it.health}`" :data-integration="it.id" :data-kind="it.kind">
    <header class="ic-head">
      <span class="k-icon"><AppIcon :name="kindIcon(it.kind)" :size="19" /></span>
      <div class="ic-title">
        <h3>{{ it.name }}</h3>
        <p v-if="k.title !== it.name">{{ k.title }}</p>
      </div>
      <div class="ic-state">
        <span class="badge" :class="`badge-${health.tone}`" data-testid="integration-health">{{ health.label }}</span>
        <ToggleSwitch :model-value="enabled" :disabled="busy === 'enable'" label="Включено" :title="enabled ? `Выключить ${quoted(it.name)}` : `Включить ${quoted(it.name)}`" data-testid="integration-enabled" @update:model-value="setEnabled" />
      </div>
    </header>

    <div class="ic-body">
      <TransferBanner v-if="it.secret_problem" tone="warn" title="Секрет нужно ввести заново" :text="it.secret_problem" data-testid="secret-problem">
        <template #actions><button type="button" class="btn btn-sm" @click="emit('edit', it)">Настроить</button></template>
      </TransferBanner>

      <TransferBanner v-if="needCheck" tone="info" title="Сначала проверьте подключение" data-testid="check-required"
                      text="Включить можно только после успешной проверки текущих настроек: так запуски по расписанию не будут падать из-за неверного адреса или токена.">
        <template #actions>
          <button type="button" class="btn btn-sm btn-primary" :disabled="!!busy" data-testid="check-required-run" @click="runCheck">{{ busy === 'check' ? 'Проверяю…' : 'Проверить' }}</button>
        </template>
      </TransferBanner>

      <div v-if="check" class="check-row">
        <CheckResult :result="check" :kind="k" data-testid="card-check-result" />
        <button v-if="check.ok && !it.enabled" type="button" class="btn btn-sm btn-primary" :disabled="!!busy" data-testid="enable-after-check" @click="enableAfterCheck">Включить</button>
      </div>

      <dl class="facts">
        <div>
          <dt>Последний запуск</dt>
          <dd v-if="lastRun">
            <span class="badge" :class="`badge-${runStatus(lastRun).tone}`">{{ runStatus(lastRun).label }}</span>
            <span>{{ actionLabel(lastRun.action) }} · {{ formatRelative(lastRun.started_at) }}</span>
            <small :title="formatDateTime(lastRun.started_at)">{{ lastRun.trigger_label }}<template v-if="runCounters(lastRun.summary).length"> · {{ runCounters(lastRun.summary).slice(0, 3).map((c) => `${c.label}: ${formatNumber(c.value)}`).join(', ') }}</template></small>
          </dd>
          <dd v-else class="muted">ещё не запускалось</dd>
        </div>
        <div>
          <dt>Расписание</dt>
          <dd><span data-testid="integration-schedule">{{ it.schedule_label || 'Вручную' }}</span>
            <small v-if="it.enabled && it.next_run_at">следующий запуск {{ formatDateTime(it.next_run_at) }}</small>
            <small v-else-if="!it.enabled && it.schedule_label && it.schedule_label !== 'Вручную'">выключено — по расписанию не запускается</small>
          </dd>
        </div>
        <div>
          <dt>Проверено</dt>
          <dd><template v-if="it.verified_at">{{ formatRelative(it.verified_at) }}</template><span v-else class="muted">не проверено с текущими настройками</span></dd>
        </div>
        <div v-if="it.last_error" class="err-fact">
          <dt>Последняя ошибка<template v-if="it.last_error_at"> · {{ formatRelative(it.last_error_at) }}</template></dt>
          <dd class="err" :title="it.last_error" data-testid="integration-error">{{ shortError(it.last_error) }}</dd>
        </div>
      </dl>

      <ul v-if="actions.length" class="acts" aria-label="Действия">
        <li v-for="a in actions" :key="a.key" :data-action="a.key">
          <div class="a-text">
            <b>{{ a.label }}<span v-if="!a.schedulable" class="tag">только вручную</span><span v-else-if="scheduled.includes(a.key)" class="tag on">по расписанию</span></b>
            <small v-if="a.description" :title="a.description">{{ richPreview(a.description, 140) }}</small>
            <small v-if="runs[a.key]" class="a-result" :class="`r-${runStatus(runs[a.key]).tone}`" data-testid="run-result">
              {{ runStatus(runs[a.key]).label }}<template v-if="runs[a.key].message">: {{ runs[a.key].message }}</template>
            </small>
          </div>
          <button type="button" class="btn btn-sm" :disabled="!!busy || it.running" :data-testid="`run-${a.key}`" @click="run(a)">
            <AppIcon name="play" :size="13" />{{ busy === `run:${a.key}` ? 'Выполняется…' : 'Запустить' }}
          </button>
        </li>
      </ul>
      <p v-if="it.running" class="muted running">Выполняется запуск<template v-if="it.running_since"> с {{ formatDateTime(it.running_since) }}</template> — дождитесь окончания.</p>
    </div>

    <footer class="ic-foot">
      <button type="button" class="btn btn-sm" :disabled="!!busy" data-testid="integration-check" @click="runCheck"><AppIcon name="activity" :size="14" />{{ busy === 'check' ? 'Проверяю…' : 'Проверить' }}</button>
      <button type="button" class="btn btn-sm" data-testid="integration-edit" @click="emit('edit', it)"><AppIcon name="settings" :size="14" />Настроить</button>
      <button type="button" class="btn btn-sm btn-ghost" data-testid="integration-journal" @click="emit('journal', it)"><AppIcon name="history" :size="14" />Журнал запусков</button>
      <span class="spacer" />
      <button type="button" class="btn btn-sm btn-ghost btn-icon btn-danger" :disabled="!!busy" :aria-label="`Удалить подключение ${quoted(it.name)}`" :title="`Удалить подключение ${quoted(it.name)}`" data-testid="integration-delete" @click="remove"><AppIcon name="trash" :size="14" /></button>
    </footer>
  </article>
</template>

<style scoped>
.icard { display: flex; flex-direction: column; min-width: 0; }
.ic-head { display: flex; align-items: center; flex-wrap: wrap; gap: 10px 12px; padding: 16px 18px 12px; }
.k-icon { width: 40px; height: 40px; flex: 0 0 40px; display: grid; place-items: center; border-radius: 12px; background: var(--surface-3); color: var(--text-2); }
.h-ok .k-icon { background: color-mix(in srgb, var(--light-green) 13%, transparent); color: var(--light-green); }
.h-error .k-icon { background: color-mix(in srgb, var(--light-red) 12%, transparent); color: var(--light-red); }
.ic-title { flex: 1 1 140px; min-width: 0; }
.ic-state { display: flex; align-items: center; gap: 12px; margin-left: auto; }
.ic-title h3 { font-size: var(--fs-md); font-weight: 650; overflow-wrap: anywhere; }
.ic-title p { font-size: var(--fs-xs); color: var(--muted); }
.ic-body { display: flex; flex-direction: column; gap: 12px; padding: 0 18px 14px; flex: 1; }
.check-row { display: flex; align-items: flex-start; gap: 10px; }
.check-row > :first-child { flex: 1; min-width: 0; }
.facts { margin: 0; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px 20px; }
.facts div { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.facts dt { font-size: var(--fs-xs); color: var(--muted); }
.facts dd { margin: 0; display: flex; flex-wrap: wrap; align-items: center; gap: 2px 6px; font-size: var(--fs-sm); }
.facts small { flex-basis: 100%; font-size: var(--fs-xs); color: var(--muted); }
.err-fact { grid-column: 1 / -1; }
.err { color: color-mix(in srgb, var(--light-red) 82%, var(--text)); overflow-wrap: anywhere; display: -webkit-box !important; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.muted { color: var(--muted); }
.acts { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; border: 1px solid var(--border); border-radius: 12px; overflow: hidden; }
.acts li { display: flex; align-items: center; gap: 12px; padding: 9px 12px; }
.acts li + li { border-top: 1px solid var(--border); }
.a-text { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.a-text b { display: flex; flex-wrap: wrap; align-items: center; gap: 2px 8px; font-size: var(--fs-sm); font-weight: 600; }
.tag { height: 18px; padding: 0 7px; border-radius: 99px; background: var(--surface-3); color: var(--muted); font-size: 10.5px; font-weight: 600; line-height: 18px; }
.tag.on { background: color-mix(in srgb, var(--accent) 12%, transparent); color: color-mix(in srgb, var(--accent) 72%, var(--text)); }
.a-text small { font-size: var(--fs-xs); color: var(--muted); }
.a-result { margin-top: 2px; font-weight: 560; }
.a-result.r-green { color: color-mix(in srgb, var(--light-green) 70%, var(--text)); }
.a-result.r-yellow { color: color-mix(in srgb, var(--light-yellow) 75%, var(--text)); }
.a-result.r-red { color: var(--light-red); }
.running { font-size: var(--fs-sm); }
.ic-foot { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; padding: 10px 14px; border-top: 1px solid var(--border); background: var(--surface-2); border-radius: 0 0 var(--radius-lg) var(--radius-lg); }
.badge-blue { background: color-mix(in srgb, var(--accent) 13%, transparent); color: var(--on-blue); }
@media (max-width: 560px) {
  .facts { grid-template-columns: minmax(0, 1fr); }
  .ic-head { padding: 14px 14px 10px; }
  .ic-body { padding: 0 14px 12px; }
}
</style>
