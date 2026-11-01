<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import AppIcon from '@/components/ui/AppIcon.vue'
import AppModal from '@/components/ui/AppModal.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import LightBadge from '@/components/ui/LightBadge.vue'
import MonthPicker from '@/components/hr/MonthPicker.vue'
import { commonApi, hrApi } from '@/api/services'
import { useAsync } from '@/composables/useAsync'
import { useQueryState } from '@/composables/useQueryState'
import { confirm } from '@/composables/useConfirm'
import { toastOk } from '@/composables/useToast'
import { useAuthStore } from '@/stores/auth'
import { useAppStore } from '@/stores/app'
import { MONTHS, deltaTone, formatDate, formatDateTime, formatDelta, formatNumber, plural } from '@/utils/format'
import { groupByCategory } from '@/domain/hr'
import {
  buildForm, changedRows, formErrors, isRowChanged, lightFor, liveDelta, mapRowErrors, monthKey, nextMonth, parseNumber, pickMonth,
} from '@/domain/hrDataEntry'

const auth = useAuthStore()
const app = useAppStore()
const canManage = computed(() => auth.can('hr', 'manager'))
const { state: q } = useQueryState({ month: '' })

const months = useAsync(() => hrApi.months())
const rules = useAsync(() => commonApi.lightRules('hr'))
const ruleMap = computed(() => Object.fromEntries((rules.data.value || []).map((r) => [r.metric_key, r])))

// ---------- выбранный месяц ----------
const current = ref('')
const month = useAsync(() => hrApi.month(current.value), { immediate: false })
const ready = computed(() => !!month.data.value && month.data.value.key === current.value)
const info = computed(() => (months.data.value || []).find((m) => m.key === current.value) || null)

watch(() => months.data.value, (list) => {
  if (!list) return
  const key = pickMonth(list, current.value || q.month)
  if (key !== current.value) current.value = key
})
watch(current, (key) => {
  q.month = key
  if (key) month.reload()
})

// ---------- форма метрик ----------
const form = ref({})
const comment = ref('')
const savedComment = ref('')
const notes = ref([])
const noteDraft = ref('')
const rowErrors = ref({})
const saving = ref(false)

watch(() => month.data.value, (m, old) => {
  // После сохранения метрик месяц перечитывается — несохранённый комментарий того же месяца остаётся
  const keepComment = !!m && m.key === old?.key && comment.value.trim() !== savedComment.value
  form.value = buildForm(m?.metrics)
  if (!keepComment) comment.value = m?.comment || ''
  savedComment.value = m?.comment || ''
  notes.value = m?.notes || []
  rowErrors.value = {}
})

const metrics = computed(() => (ready.value ? month.data.value.metrics : []))
const groups = computed(() => groupByCategory(metrics.value))
const pending = computed(() => changedRows(metrics.value, form.value))
const invalid = computed(() => formErrors(form.value))
const invalidCount = computed(() => Object.keys(invalid.value).length)
const dirtyMetrics = computed(() => pending.value.length > 0 || invalidCount.value > 0)
const commentDirty = computed(() => comment.value.trim() !== savedComment.value)
const dirty = computed(() => dirtyMetrics.value || commentDirty.value || !!noteDraft.value.trim())

/** Состояние строки: изменена ли, ошибка, светофор и изменение для введённого значения. */
const rows = computed(() => {
  const out = {}
  for (const m of metrics.value) {
    const f = form.value[m.key]
    if (!f) continue
    const parsed = parseNumber(f.value)
    const changed = isRowChanged(m, f)
    const value = parsed.error ? null : parsed.value
    out[m.key] = {
      changed,
      error: parsed.error || rowErrors.value[m.key] || '',
      light: changed && !parsed.error && rules.data.value ? lightFor(value, ruleMap.value[m.key]) : m.light,
      delta: parsed.error ? null : liveDelta(value, m.previous),
      filled: value !== null,
      // Включено правило светофора, а значения нет — критичное нарушение полноты данных
      missing: value === null && !parsed.error && !!ruleMap.value[m.key]?.enabled,
    }
  }
  return out
})
const filledCount = computed(() => Object.values(rows.value).filter((r) => r.filled).length)
const missingLabels = computed(() => metrics.value.filter((m) => rows.value[m.key]?.missing).map((m) => m.label))
const groupFilled = (g) => g.items.filter((m) => rows.value[m.key]?.filled).length
const targetText = (m) => (m.target === null || m.target === undefined ? ''
  : `цель ${m.direction === 'lower_is_better' ? '≤' : m.direction === 'higher_is_better' ? '≥' : ''} ${formatNumber(m.target, { unit: m.unit })}`)

function resetForm() {
  form.value = buildForm(metrics.value)
  rowErrors.value = {}
}

async function save() {
  const payload = pending.value
  if (!payload.length || invalidCount.value || saving.value) return
  saving.value = true
  rowErrors.value = {}
  try {
    const result = await hrApi.saveMetrics(current.value, payload)
    toastOk(result?.message || 'Значения сохранены')
    await Promise.all([month.reload(), months.reload()])
    app.loadServices()
  } catch (e) {
    rowErrors.value = mapRowErrors(e.fields, payload)
  } finally {
    saving.value = false
  }
}

async function saveComment() {
  const text = comment.value.trim()
  try { await hrApi.updateMonth(current.value, { comment: text }) } catch { return } // ошибку показал клиент API
  savedComment.value = text
  comment.value = text
  toastOk('Комментарий сохранён')
  months.reload()
}

// ---------- несохранённые изменения ----------
function confirmDiscard() {
  return confirm({
    title: 'Есть несохранённые изменения',
    message: 'Введённые значения, комментарий или текст заметки ещё не сохранены. Если продолжить, они будут потеряны.',
    confirmText: 'Не сохранять', danger: true,
  })
}
async function selectMonth(key) {
  if (!key || key === current.value) return
  if (dirty.value && !(await confirmDiscard())) return
  noteDraft.value = ''
  current.value = key
}
onBeforeRouteLeave(async () => (dirty.value ? confirmDiscard() : true))
function onBeforeUnload(event) {
  if (!dirty.value) return
  event.preventDefault()
  event.returnValue = ''
}
function onKey(event) {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
    event.preventDefault()
    save()
  }
}
onMounted(() => {
  window.addEventListener('beforeunload', onBeforeUnload)
  window.addEventListener('keydown', onKey)
})
onBeforeUnmount(() => {
  window.removeEventListener('beforeunload', onBeforeUnload)
  window.removeEventListener('keydown', onKey)
})

// ---------- добавление и удаление месяца ----------
const adding = ref(false)
const newMonth = reactive({ year: 2026, month: 1, comment: '' })
const addError = ref('')
const addFields = ref({})
const addSaving = ref(false)
const exists = computed(() => (months.data.value || []).some((m) => m.key === monthKey(newMonth.year, newMonth.month)))

function openAdd(preset = null) {
  Object.assign(newMonth, preset || nextMonth(months.data.value), { comment: '' })
  addError.value = ''
  addFields.value = {}
  adding.value = true
}
async function createMonth() {
  if (exists.value) return
  addSaving.value = true
  addError.value = ''
  addFields.value = {}
  try {
    const created = await hrApi.createMonth({ year: Number(newMonth.year), month: Number(newMonth.month), comment: newMonth.comment.trim() })
    adding.value = false
    toastOk(`Месяц «${created.label}» добавлен`)
    await months.reload()
    selectMonth(created.key)
  } catch (e) {
    addError.value = e.message
    addFields.value = e.fields || {}
  } finally {
    addSaving.value = false
  }
}

async function removeMonth() {
  const m = month.data.value
  const values = m.metrics.filter((x) => x.value !== null).length
  const ok = await confirm({
    title: `Удалить месяц «${m.label}»?`,
    message: `Вместе с месяцем удалятся значения метрик (${values}), записи реестра (${m.events.length}) и заметки (${notes.value.length}). Отменить удаление нельзя.`,
    confirmText: 'Удалить месяц', danger: true,
  })
  if (!ok) return
  try { await hrApi.deleteMonth(m.key) } catch { return } // ошибку показал клиент API
  toastOk(`Месяц «${m.label}» удалён`)
  noteDraft.value = ''
  form.value = {}
  current.value = ''
  await months.reload()
  app.loadServices()
}

// ---------- заметки и события ----------
const notesSorted = computed(() => [...notes.value].sort((a, b) => String(b.created_at).localeCompare(String(a.created_at))))
const noteSaving = ref(false)
async function addNote() {
  const text = noteDraft.value.trim()
  if (!text) return
  noteSaving.value = true
  try {
    const note = await hrApi.addNote(current.value, text)
    notes.value = [...notes.value, note]
    noteDraft.value = ''
    toastOk('Заметка добавлена')
  } catch {} finally {
    noteSaving.value = false
  }
}
async function removeNote(note) {
  const preview = note.content.length > 160 ? `${note.content.slice(0, 160)}…` : note.content
  if (!await confirm({ title: 'Удалить заметку?', message: preview, confirmText: 'Удалить', danger: true })) return
  try { await hrApi.deleteNote(note.id) } catch { return } // ошибку показал клиент API
  notes.value = notes.value.filter((n) => n.id !== note.id)
  toastOk('Заметка удалена')
}

const EVENTS_SHOWN = 6
const events = computed(() => [...(ready.value ? month.data.value.events : [])].sort((a, b) => String(b.event_date).localeCompare(String(a.event_date))))
const hiredCount = computed(() => events.value.filter((e) => e.event_type === 'hired').length)
// Записи реестра — с правом на исходные записи и персональные данные (сервер присылает events_hidden)
const eventsHidden = computed(() => ready.value && !!month.data.value.events_hidden)
const canRegistry = computed(() => !auth.denial({ service: 'hr', records: true, dataClass: 'personal' }))
const shortDate = (d) => formatDate(d).slice(0, 5)
</script>

<template>
  <div class="page">
    <PageHeader title="Ввод данных" description="Значения метрик, комментарии и заметки по месяцам" :updatedAt="ready ? month.data.value.updated_at : null">
      <router-link v-if="current && canRegistry" :to="{ path: '/hr/registry', query: { month: current } }" class="btn"><AppIcon name="list" :size="15" />Реестр месяца</router-link>
      <button class="btn" type="button" @click="openAdd()"><AppIcon name="plus" :size="15" />Добавить месяц</button>
    </PageHeader>

    <div v-if="!months.data.value && months.loading" class="skeleton" style="height: 86px" />

    <EmptyState v-else-if="months.data.value && !months.data.value.length" icon="calendar" title="Месяцев пока нет"
                text="Добавьте первый месяц — после этого можно вводить значения метрик, заметки и записи реестра.">
      <button class="btn btn-primary" type="button" @click="openAdd()"><AppIcon name="plus" :size="15" />Добавить месяц</button>
    </EmptyState>

    <template v-else-if="months.data.value">
      <MonthPicker :months="months.data.value" :modelValue="current" canAdd @select="selectMonth" @add="openAdd" />

      <div class="layout">
        <!-- метрики -->
        <div class="main-col">
          <template v-if="ready">
            <section v-for="g in groups" :key="g.key" class="card">
              <header class="card-head">
                <h3>{{ g.label }}</h3>
                <span class="spacer" />
                <span class="hint num">заполнено {{ groupFilled(g) }} из {{ g.items.length }}</span>
              </header>
              <div class="card-body table-wrap">
                <table class="table metrics">
                  <colgroup><col class="c-metric" /><col class="c-value" /><col class="c-prev" /><col /></colgroup>
                  <thead>
                    <tr><th>Метрика</th><th class="num">Значение</th><th class="num" title="Значение за прошлый месяц и изменение">Пред. месяц</th><th>Источник, комментарий</th></tr>
                  </thead>
                  <tbody>
                    <tr v-for="m in g.items" :key="m.key" :class="{ changed: rows[m.key]?.changed, missing: rows[m.key]?.missing }">
                      <td class="metric">
                        <div class="metric-name">
                          <LightBadge dot :light="rows[m.key]?.light" />
                          <label :for="`v-${m.key}`">{{ m.label }}</label>
                        </div>
                        <div v-if="m.description" class="desc">{{ m.description }}</div>
                      </td>
                      <td class="value">
                        <div class="value-field">
                          <input :id="`v-${m.key}`" v-model="form[m.key].value" class="input input-sm num" :class="{ invalid: rows[m.key]?.error }"
                                 inputmode="decimal" autocomplete="off"
                                 :aria-invalid="!!rows[m.key]?.error" />
                          <span class="unit">{{ m.unit }}</span>
                        </div>
                        <div v-if="rows[m.key]?.error" class="error">{{ rows[m.key].error }}</div>
                        <div v-else-if="rows[m.key]?.missing" class="error">Обязательно: показатель на светофоре</div>
                        <div v-else-if="targetText(m)" class="help">{{ targetText(m) }}</div>
                      </td>
                      <td class="num prev">
                        <div class="muted">{{ formatNumber(m.previous, { unit: m.unit }) }}</div>
                        <div v-if="rows[m.key]?.delta !== null" class="delta" :class="`delta-${deltaTone(rows[m.key]?.delta, m.direction)}`">
                          {{ formatDelta(rows[m.key]?.delta, m.unit) }}
                        </div>
                      </td>
                      <td class="note-cell">
                        <input v-model="form[m.key].source_note" class="input input-sm" maxlength="2000" placeholder="Источник данных" :aria-label="`Источник: ${m.label}`" />
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </section>

            <div class="savebar card" :class="{ active: dirtyMetrics }">
              <span v-if="invalidCount" class="state error-text"><AppIcon name="alert" :size="15" />Исправьте {{ invalidCount }} {{ plural(invalidCount, ['значение', 'значения', 'значений']) }}: нужно число</span>
              <span v-else-if="pending.length" class="state"><span class="pulse" />Изменено {{ pending.length }} {{ plural(pending.length, ['значение', 'значения', 'значений']) }}</span>
              <span v-else class="state muted"><AppIcon name="check" :size="15" />Изменений нет</span>
              <span class="spacer" />
              <span class="kbd-hint muted">Ctrl + S</span>
              <button class="btn btn-ghost" type="button" :disabled="!dirtyMetrics || saving" @click="resetForm">Отменить</button>
              <button class="btn btn-primary" type="button" :disabled="!pending.length || !!invalidCount || saving" @click="save">{{ saving ? 'Сохранение…' : 'Сохранить' }}</button>
            </div>
          </template>
          <template v-else>
            <div v-for="i in 3" :key="i" class="skeleton" style="height: 220px" />
          </template>
        </div>

        <!-- месяц, заметки, события -->
        <aside class="side-col">
          <section class="card">
            <header class="card-head">
              <h3>{{ info?.label || '…' }}</h3>
              <span class="spacer" />
              <button v-if="canManage && ready" class="btn btn-sm btn-ghost btn-danger" type="button" @click="removeMonth"><AppIcon name="trash" :size="13" />Удалить месяц</button>
            </header>
            <div v-if="ready" class="card-body stack">
              <div class="fill-block">
                <div class="row"><span class="muted">Заполнено метрик</span><span class="spacer" /><strong class="num">{{ filledCount }} из {{ metrics.length }}</strong></div>
                <div class="bar" role="progressbar" :aria-valuenow="filledCount" :aria-valuemax="metrics.length">
                  <span :style="{ width: metrics.length ? `${(filledCount / metrics.length) * 100}%` : '0' }" :class="{ full: filledCount === metrics.length }" />
                </div>
                <p v-if="missingLabels.length" class="missing-note" data-testid="hr-missing-entry">
                  <AppIcon name="alert" :size="14" />
                  <span><b>Не заполнено со светофором: {{ missingLabels.length }}</b> — критичное нарушение. На дашборде такие показатели — «Нет данных».</span>
                </p>
              </div>
              <dl class="facts">
                <div><dt>Принято</dt><dd class="num">{{ info?.hired ?? 0 }}</dd></div>
                <div><dt>Уволено</dt><dd class="num">{{ info?.fired ?? 0 }}</dd></div>
                <div><dt>Обновлено</dt><dd class="num" :title="formatDateTime(month.data.value.updated_at)">{{ formatDate(month.data.value.updated_at) }}</dd></div>
              </dl>
              <label class="field"><span>Комментарий к месяцу</span>
                <textarea v-model="comment" class="textarea" rows="3" maxlength="5000" placeholder="Особенности периода, источники данных" />
              </label>
              <div v-if="commentDirty" class="row">
                <span class="spacer" />
                <button class="btn btn-sm btn-ghost" type="button" @click="comment = savedComment">Отменить</button>
                <button class="btn btn-sm btn-primary" type="button" @click="saveComment">Сохранить комментарий</button>
              </div>
            </div>
            <div v-else class="card-body"><div class="skeleton" style="height: 160px" /></div>
          </section>

          <section class="card">
            <header class="card-head"><h3>Заметки</h3><span class="spacer" /><span v-if="notes.length" class="hint num">{{ notes.length }}</span></header>
            <div class="card-body stack">
              <form class="stack note-form" @submit.prevent="addNote">
                <textarea v-model="noteDraft" class="textarea" rows="2" maxlength="5000" placeholder="Новая заметка к месяцу" aria-label="Текст заметки" :disabled="!ready" />
                <div class="row"><span class="spacer" /><button class="btn btn-sm" type="submit" :disabled="!noteDraft.trim() || noteSaving || !ready"><AppIcon name="plus" :size="13" />Добавить заметку</button></div>
              </form>
              <ul v-if="notesSorted.length" class="notes">
                <li v-for="n in notesSorted" :key="n.id">
                  <p>{{ n.content }}</p>
                  <div class="meta">
                    <span>{{ n.author || 'Без автора' }} · {{ formatDateTime(n.created_at) }}</span>
                    <span class="spacer" />
                    <button class="btn btn-icon btn-sm btn-ghost" type="button" title="Удалить заметку" @click="removeNote(n)"><AppIcon name="trash" :size="13" /></button>
                  </div>
                </li>
              </ul>
              <p v-else-if="ready" class="muted small">Заметок пока нет.</p>
            </div>
          </section>

          <section class="card">
            <header class="card-head">
              <h3>Приёмы и увольнения</h3>
              <span class="spacer" />
              <span v-if="events.length" class="badge badge-green num">+{{ hiredCount }}</span>
              <span v-if="events.length" class="badge badge-red num">−{{ events.length - hiredCount }}</span>
            </header>
            <div class="card-body">
              <ul v-if="events.length" class="events">
                <li v-for="e in events.slice(0, EVENTS_SHOWN)" :key="e.id">
                  <span class="date num muted">{{ shortDate(e.event_date) }}</span>
                  <span class="kind" :class="e.event_type" :title="e.event_type === 'hired' ? 'Приём' : 'Увольнение'" />
                  <span class="who"><span class="ellipsis">{{ e.full_name }}</span><span class="dept ellipsis">{{ e.department || e.position || '—' }}</span></span>
                </li>
              </ul>
              <p v-else-if="eventsHidden" class="muted small hidden-note"><AppIcon name="lock" :size="13" />Записи реестра скрыты: для них нужны исходные записи и персональные данные.</p>
              <p v-else-if="ready" class="muted small">Записей за месяц нет.</p>
              <router-link v-if="current && canRegistry" :to="{ path: '/hr/registry', query: { month: current } }" class="link more">
                {{ events.length > EVENTS_SHOWN ? `Все записи месяца (${events.length})` : 'Открыть в реестре' }}<AppIcon name="chevron-right" :size="13" />
              </router-link>
            </div>
          </section>
        </aside>
      </div>
    </template>

    <AppModal v-if="adding" title="Новый месяц" subtitle="Метрики, заметки и записи реестра вводятся после добавления" :width="460" @close="adding = false">
      <form id="month-form" class="form-grid" @submit.prevent="createMonth">
        <label class="field"><span>Год</span>
          <input v-model.number="newMonth.year" class="input num" :class="{ invalid: addFields.year }" type="number" min="2000" max="2100" required />
          <span v-if="addFields.year" class="error">{{ addFields.year }}</span>
        </label>
        <label class="field"><span>Месяц</span>
          <select v-model.number="newMonth.month" class="select" :class="{ invalid: addFields.month || exists }">
            <option v-for="(name, i) in MONTHS" :key="i" :value="i + 1">{{ name }}</option>
          </select>
          <span v-if="addFields.month" class="error">{{ addFields.month }}</span>
        </label>
        <p v-if="exists" class="error full">Этот месяц уже добавлен — выберите его в списке месяцев.</p>
        <label class="field full"><span>Комментарий</span>
          <textarea v-model="newMonth.comment" class="textarea" :class="{ invalid: addFields.comment }" rows="3" maxlength="5000" placeholder="Необязательно" />
          <span v-if="addFields.comment" class="error">{{ addFields.comment }}</span>
        </label>
      </form>
      <p v-if="addError && !exists" class="error form-error">{{ addError }}</p>
      <template #footer>
        <button class="btn" type="button" @click="adding = false">Отмена</button>
        <button class="btn btn-primary" type="submit" form="month-form" :disabled="addSaving || exists">{{ addSaving ? 'Добавление…' : 'Добавить месяц' }}</button>
      </template>
    </AppModal>
  </div>
</template>

<style scoped>
.layout { display: grid; grid-template-columns: minmax(0, 1fr) 312px; gap: var(--sp-4); align-items: start; }
.main-col, .side-col { display: flex; flex-direction: column; gap: var(--sp-4); min-width: 0; }
@media (max-width: 1180px) { .layout { grid-template-columns: minmax(0, 1fr); } }

.metrics { table-layout: fixed; min-width: 620px; }
.metrics .c-metric { width: 36%; }
.metrics .c-value { width: 160px; }
.metrics .c-prev { width: 116px; }
.metrics td { vertical-align: top; }
.metrics tr.changed td:first-child { box-shadow: inset 3px 0 0 var(--accent); }
.metrics tr.changed { background: color-mix(in srgb, var(--accent) 4%, transparent); }
.metric-name { display: flex; align-items: baseline; gap: 8px; font-weight: 540; }
.metric-name .dot { transform: translateY(-1px); }
.metric-name label { cursor: pointer; }
.desc { margin: 2px 0 0 16px; font-size: var(--fs-xs); color: var(--muted); line-height: 1.4; }
.value-field { display: flex; align-items: center; gap: 6px; justify-content: flex-end; }
.value .input { width: 96px; text-align: right; }
.value .unit { width: 28px; font-size: var(--fs-xs); color: var(--muted); }
.value .help, .value .error { margin-top: 3px; padding-right: 34px; text-align: right; font-size: var(--fs-xs); white-space: nowrap; }
.value .help { color: var(--muted); }
.value .error { color: var(--light-red); }
.prev { white-space: nowrap; padding-top: 14px !important; }
.prev .delta { margin-top: 2px; font-size: var(--fs-xs); font-weight: 600; }

@media (max-width: 640px) {
  .metrics { min-width: 0; table-layout: auto; }
  .metrics colgroup, .metrics thead { display: none; }
  .metrics tbody tr { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 8px 12px; padding: 12px 0; border-bottom: 1px solid var(--border); }
  .metrics tbody tr:last-child { border-bottom: 0; }
  .metrics td { display: block; padding: 0 !important; border: 0 !important; }
  .metrics td.metric, .metrics td.note-cell { grid-column: 1 / -1; }
  .metrics tr.changed td:first-child { box-shadow: none; }
  .value-field { justify-content: flex-start; }
  .value .help, .value .error { text-align: left; padding-right: 0; }
  .prev { padding-top: 6px !important; }
}

.savebar { position: sticky; bottom: var(--sp-4); z-index: 5; display: flex; align-items: center; gap: var(--sp-2); padding: 10px 12px 10px 16px; }
.savebar.active { border-color: color-mix(in srgb, var(--accent) 45%, var(--border)); box-shadow: var(--shadow-lg); }
.state { display: inline-flex; align-items: center; gap: 8px; min-width: 0; font-size: var(--fs-sm); font-weight: 540; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.error-text { color: var(--light-red); }
tr.missing td.metric { box-shadow: inset 3px 0 0 var(--light-red); }
tr.missing .input { border-color: color-mix(in srgb, var(--light-red) 55%, var(--border-strong)); }
.missing-note { display: flex; gap: 8px; align-items: flex-start; margin: 10px 0 0; font-size: var(--fs-sm); color: var(--text-2); line-height: 1.4; }
.missing-note svg { color: var(--light-red); flex: 0 0 auto; margin-top: 2px; }
.missing-note b { color: var(--light-red); }
.pulse { flex: 0 0 8px; width: 8px; height: 8px; border-radius: 50%; background: var(--accent); box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 22%, transparent); }
.kbd-hint { font-size: var(--fs-xs); margin-right: 4px; }
@media (max-width: 640px) {
  .kbd-hint { display: none; }
  .savebar { flex-wrap: wrap; }
  .savebar .state { flex: 1 1 100%; }
}

.fill-block { display: flex; flex-direction: column; gap: 6px; font-size: var(--fs-sm); }
.bar { height: 6px; border-radius: var(--radius-pill); background: var(--surface-3); overflow: hidden; }
.bar span { display: block; height: 100%; border-radius: inherit; background: var(--light-yellow); transition: width var(--t); }
.bar span.full { background: var(--light-green); }
.facts { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) minmax(0, 1.45fr); gap: 8px; margin: 0; }
.facts div { padding: 8px 10px; border-radius: var(--radius); background: var(--surface-2); border: 1px solid var(--border); min-width: 0; }
.facts dt { font-size: var(--fs-xs); color: var(--muted); }
.facts dd { margin: 2px 0 0; font-weight: 620; font-size: var(--fs-sm); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

.note-form .textarea { min-height: 60px; }
.notes { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; }
.notes li { padding: 10px 0; border-top: 1px solid var(--border); }
.notes p { white-space: pre-line; font-size: var(--fs-sm); color: var(--text); }
.notes .meta { display: flex; align-items: center; gap: 6px; margin-top: 4px; font-size: var(--fs-xs); color: var(--muted); }
.small { font-size: var(--fs-sm); }

.hidden-note { display: flex; align-items: flex-start; gap: 6px; }
.hidden-note :deep(svg) { flex: 0 0 auto; margin-top: 2px; }
.events { list-style: none; margin: 0 0 10px; padding: 0; display: flex; flex-direction: column; }
.events li { display: grid; grid-template-columns: 42px 8px minmax(0, 1fr); align-items: center; gap: 10px; padding: 7px 0; border-bottom: 1px solid var(--border); font-size: var(--fs-sm); }
.events li:last-child { border-bottom: 0; }
.kind { width: 8px; height: 8px; border-radius: 50%; }
.kind.hired { background: var(--light-green); }
.kind.fired { background: var(--light-red); }
.who { display: flex; flex-direction: column; min-width: 0; }
.dept { font-size: var(--fs-xs); color: var(--muted); }
.date { font-size: var(--fs-xs); }
.more { display: inline-flex; align-items: center; gap: 4px; font-size: var(--fs-sm); font-weight: 540; }
.error { color: var(--light-red); font-size: var(--fs-sm); }
.form-error { margin-top: 10px; }
</style>
