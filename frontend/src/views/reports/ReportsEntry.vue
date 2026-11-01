<script setup>
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import AppIcon from '@/components/ui/AppIcon.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import FilterBar from '@/components/ui/FilterBar.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import ImportValuesDialog from '@/components/reports/ImportValuesDialog.vue'
import { reportsApi } from '@/api/reports'
import { useAsync } from '@/composables/useAsync'
import { useQueryState } from '@/composables/useQueryState'
import { confirm } from '@/composables/useConfirm'
import { toastError, toastOk } from '@/composables/useToast'
import {
  DATA_CLASS_SHORT, canEnterCell, cellErrors, entryChanges, entryDraft, entryKey, entryOriginal, entryPeriods, entryRows,
  expectedEmpty, templateCsv,
} from '@/domain/reports'
import { formatDateTime, formatNumber, monthLabel, plural } from '@/utils/format'

/**
 * Ввод показателей (ADR-0010): подразделения × вводимые показатели за месяц — значение, цель и
 * комментарий. Строки — подразделения, где пользователь может вводить (служба-владелец, уровень
 * «ввод данных», своя область; «Сквозные отчёты» — везде). Сохраняются только изменённые ячейки;
 * ошибки сервера — у ячеек. Загрузка из Excel — план и применение.
 */
const { state: q } = useQueryState({ period: '', indicator: '' })
const periods = useAsync(() => reportsApi.periods())
const period = computed(() => q.period || periods.data.value?.latest || periods.data.value?.current || '')
const periodOptions = computed(() => {
  const info = periods.data.value
  if (!info) return []
  const set = new Set([...entryPeriods(info.current, 24), ...info.periods.map((p) => p.period)])
  if (period.value) set.add(period.value)
  const withData = new Set(info.periods.map((p) => p.period))
  return [...set].sort().reverse().map((p) => ({ value: p, label: `${monthLabel(p)}${withData.has(p) ? '' : ' · нет данных'}` }))
})

// Право ввода — заранее (сводка отчёта отдаёт me.can_enter): без права форма не запрашивается
const rights = useAsync(() => reportsApi.summary())
const canEnter = computed(() => !!rights.data.value?.me?.can_enter)
const ENTRY_DENIED = 'Вводить значения показателей могут сотрудники с уровнем «Ввод данных» к службе — владельцу показателя, в своей области структуры. Право выдаёт администратор.'

const { data, loading, error, reload } = useAsync(() => reportsApi.values({ period: period.value }), { immediate: false })
watch([period, canEnter], ([value, can]) => { if (value && can) reload() }, { immediate: true })

const indicators = computed(() => data.value?.indicators || [])
const columns = computed(() => indicators.value.filter((i) => !q.indicator || i.key === q.indicator))
const units = computed(() => entryRows(data.value?.units || []))
const original = computed(() => entryOriginal(data.value?.values || []))
const savedBy = computed(() => new Map((data.value?.values || []).map((v) => [entryKey(v.indicator_id, v.department_id), v])))

// ---------------------------------------------------------------- черновик
const drafts = reactive({})
const errors = ref({})
const saveError = ref('')
function resetDrafts() {
  for (const key of Object.keys(drafts)) delete drafts[key]
  for (const unit of units.value) {
    for (const ind of indicators.value) {
      if (canEnterCell(ind, unit)) drafts[entryKey(ind.id, unit.id)] = entryDraft(original.value, entryKey(ind.id, unit.id))
    }
  }
  errors.value = {}
  saveError.value = ''
}
watch(data, resetDrafts)
const changes = computed(() => entryChanges(original.value, new Map(Object.entries(drafts))))
const dirtyKeys = computed(() => new Set([...changes.value.keys, ...Object.keys(changes.value.invalid)]))
const dirty = computed(() => dirtyKeys.value.size)

function cellClass(ind, unit) {
  const key = entryKey(ind.id, unit.id)
  return {
    changed: dirtyKeys.value.has(key),
    invalid: !!errors.value[key] || !!changes.value.invalid[key],
    expected: expectedEmpty(ind, unit, drafts[key]),
  }
}
const cellError = (key) => {
  const e = { ...(changes.value.invalid[key] || {}), ...(errors.value[key] || {}) }
  return e.cell || e.value || e.target || e.comment || ''
}
const expectedCount = computed(() => {
  let n = 0
  for (const unit of units.value) for (const ind of columns.value) if (canEnterCell(ind, unit) && expectedEmpty(ind, unit, drafts[entryKey(ind.id, unit.id)])) n += 1
  return n
})

function focusExpected() {
  const input = document.querySelector('[data-testid="entry-grid"] .cell.expected input[data-field=value]')
  input?.scrollIntoView({ block: 'center', inline: 'center', behavior: 'smooth' })
  input?.focus({ preventScroll: true })
}

// ---------------------------------------------------------------- сохранение
const saving = ref(false)
async function save() {
  const { items, keys, invalid } = changes.value
  if (Object.keys(invalid).length) {
    toastError('В некоторых ячейках не число — исправьте их')
    return
  }
  if (!items.length) return
  saving.value = true
  saveError.value = ''
  try {
    const result = await reportsApi.saveValues(period.value, items)
    const parts = [result.created && `новых ${result.created}`, result.updated && `изменено ${result.updated}`, result.deleted && `удалено ${result.deleted}`].filter(Boolean)
    toastOk(`Сохранено${parts.length ? `: ${parts.join(', ')}` : ''}`)
    await reload()
  } catch (e) {
    errors.value = cellErrors(e.fields, keys)
    saveError.value = Object.keys(errors.value).length
      ? `${e.message}. Ячейки с ошибками отмечены — ничего не сохранено.`
      : e.message
  } finally {
    saving.value = false
  }
}
function discard() { resetDrafts() }

async function confirmDiscard() {
  if (!dirty.value) return true
  return confirm({ title: 'Отменить несохранённые изменения?', message: `Изменено ячеек: ${dirty.value}. Они не сохранены и будут потеряны.`, confirmText: 'Отменить изменения', danger: true })
}
const periodModel = computed({
  get: () => period.value,
  set: async (value) => {
    if (value === period.value) return
    if (await confirmDiscard()) q.period = value
  },
})
onBeforeRouteLeave(async (to) => (to.path === '/reports/entry' ? true : confirmDiscard()))
function beforeUnload(event) {
  if (!dirty.value) return
  event.preventDefault()
  event.returnValue = ''
}
window.addEventListener('beforeunload', beforeUnload)
onBeforeUnmount(() => window.removeEventListener('beforeunload', beforeUnload))

// ---------------------------------------------------------------- комментарий ячейки
const note = ref(null) // { key, left, top, title }
async function openNote(event, ind, unit) {
  const rect = event.currentTarget.getBoundingClientRect()
  const width = 300
  note.value = {
    key: entryKey(ind.id, unit.id), title: `${ind.name} · ${unit.name}`,
    left: Math.min(window.innerWidth - width - 12, Math.max(12, rect.right - width)),
    top: Math.min(window.innerHeight - 200, rect.bottom + 6),
  }
  await nextTick()
  document.querySelector('[data-testid="entry-comment"]')?.focus()
}
function closeNote() { note.value = null }
function onNoteKey(event) { if (event.key === 'Escape') closeNote() }

// ---------------------------------------------------------------- загрузка и шаблон
const importing = ref(false)
function downloadTemplate() {
  const csv = templateCsv({ period: period.value, indicators: columns.value, units: units.value, values: data.value?.values || [] })
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `Показатели ${period.value}.csv`
  a.style.display = 'none'
  document.body.appendChild(a)
  a.click()
  setTimeout(() => { a.remove(); URL.revokeObjectURL(url) }, 1500)
}
async function openImport() {
  if (await confirmDiscard()) {
    resetDrafts()
    importing.value = true
  }
}

const placeholder = (ind) => (ind.default_target !== null && ind.default_target !== undefined ? formatNumber(ind.default_target) : 'цель')
const savedTitle = (key) => {
  const v = savedBy.value.get(key)
  return v ? `${v.source_label}${v.updated_by ? ` · ${v.updated_by.full_name}` : ''}${v.updated_at ? ` · ${formatDateTime(v.updated_at)}` : ''}` : 'Значения нет'
}
const summary = computed(() => (data.value
  ? `${units.value.length} ${plural(units.value.length, ['подразделение', 'подразделения', 'подразделений'])} · ${columns.value.length} ${plural(columns.value.length, ['показатель', 'показателя', 'показателей'])}`
  : ''))
</script>

<template>
  <div class="page entry">
    <PageHeader title="Ввод показателей" :description="data ? `Значения, цели и комментарии за ${data.period_label.toLowerCase()} — по подразделениям, где вы вводите данные` : 'Значения, цели и комментарии по подразделениям за месяц'">
      <router-link :to="{ path: '/reports', query: period ? { period } : {} }" class="btn btn-ghost"><AppIcon name="traffic" :size="15" />Сквозной отчёт</router-link>
      <button v-if="data" class="btn" type="button" data-testid="entry-template" @click="downloadTemplate"><AppIcon name="download" :size="15" />Шаблон CSV</button>
      <button v-if="data" class="btn" type="button" data-testid="entry-import" @click="openImport"><AppIcon name="upload" :size="15" />Загрузить из Excel</button>
    </PageHeader>

    <FilterBar :summary="summary">
      <label class="field"><span>Период</span>
        <select v-model="periodModel" class="select" data-testid="entry-period" :disabled="!periodOptions.length">
          <option v-for="p in periodOptions" :key="p.value" :value="p.value">{{ p.label }}</option>
        </select>
      </label>
      <label class="field"><span>Показатель</span>
        <select v-model="q.indicator" class="select" data-testid="entry-indicator" :disabled="!indicators.length">
          <option value="">Все показатели</option>
          <option v-for="i in indicators" :key="i.key" :value="i.key">{{ i.name }}</option>
        </select>
      </label>
    </FilterBar>

    <div v-if="(loading && !data) || (!rights.data.value && !rights.error.value)" class="skeleton" style="height: 420px; border-radius: var(--radius-lg)" />
    <EmptyState v-else-if="rights.data.value && !canEnter" class="card" icon="lock" title="Ввод показателей недоступен" :text="ENTRY_DENIED" data-testid="entry-forbidden">
      <router-link to="/reports" class="btn btn-primary btn-sm">К сквозному отчёту</router-link>
      <router-link to="/profile#my-access" class="btn btn-sm">Мой доступ</router-link>
    </EmptyState>
    <EmptyState v-else-if="error && !data && error.status === 403" class="card" icon="lock" title="Ввод показателей недоступен" :text="error.message" data-testid="entry-forbidden">
      <router-link to="/reports" class="btn btn-primary btn-sm">К сквозному отчёту</router-link>
      <router-link to="/profile#my-access" class="btn btn-sm">Мой доступ</router-link>
    </EmptyState>
    <EmptyState v-else-if="error && !data" class="card" icon="alert" title="Не удалось загрузить форму" :text="error.message">
      <button class="btn btn-sm" type="button" @click="reload()">Повторить</button>
    </EmptyState>
    <EmptyState v-else-if="data && (!units.length || !indicators.length)" class="card" icon="edit" title="Нечего вводить"
                text="В вашей области нет подразделений для вводимых показателей. Вычисляемые показатели берутся из данных служб сами." />

    <template v-else-if="data">
      <p v-if="expectedCount" class="expect-note" data-testid="entry-expected">
        <AppIcon name="alert" :size="14" /><span>Не заполнено обязательных значений: <b>{{ expectedCount }}</b> — такие ячейки выделены; в отчёте это критичное нарушение полноты.</span>
        <button type="button" class="btn btn-sm" @click="focusExpected">Перейти</button>
      </p>
      <p v-if="saveError" class="save-error" role="alert"><AppIcon name="alert" :size="14" />{{ saveError }}</p>

      <section class="card grid-card" :class="{ busy: loading }">
        <div class="grid-scroll scroll-thin">
          <table class="eg" data-testid="entry-grid">
            <thead>
              <tr>
                <th class="corner" scope="col">Подразделение</th>
                <th v-for="ind in columns" :key="ind.id" scope="col" class="ind" :data-indicator="ind.key">
                  <span class="i-name" :title="ind.name">{{ ind.name }}</span>
                  <span class="i-meta">
                    <span class="cls" :class="`c-${ind.data_class}`" :title="ind.data_class_label">{{ DATA_CLASS_SHORT[ind.data_class] }}</span>
                    <span v-if="ind.unit">{{ ind.unit }}</span>
                    <span class="own" :title="`Служба-владелец: ${ind.owner_service_title || '—'}`">{{ ind.owner_service_title }}</span>
                  </span>
                  <span class="i-cols"><span>значение</span><span>цель</span></span>
                </th>
                <th class="filler" aria-hidden="true" />
              </tr>
            </thead>
            <tbody>
              <tr v-for="unit in units" :key="unit.id" :data-unit="unit.id">
                <th scope="row" class="unit" :style="{ '--indent': unit.indent }">
                  <span class="u-name" :title="unit.path">{{ unit.name }}</span>
                  <span class="u-meta">{{ unit.kind_label }}<template v-if="unit.code"> · {{ unit.code }}</template></span>
                </th>
                <td v-for="ind in columns" :key="ind.id" class="cell" :class="cellClass(ind, unit)" :data-cell="entryKey(ind.id, unit.id)">
                  <template v-if="canEnterCell(ind, unit) && drafts[entryKey(ind.id, unit.id)]">
                    <div class="inputs" :title="cellError(entryKey(ind.id, unit.id)) || savedTitle(entryKey(ind.id, unit.id))">
                      <input v-model="drafts[entryKey(ind.id, unit.id)].value" class="in v" inputmode="decimal" autocomplete="off"
                             :placeholder="cellClass(ind, unit).expected ? 'нужно' : '—'" :aria-label="`${ind.name}, ${unit.name}: значение`" data-field="value" />
                      <input v-model="drafts[entryKey(ind.id, unit.id)].target" class="in t" inputmode="decimal" autocomplete="off"
                             :placeholder="placeholder(ind)" :aria-label="`${ind.name}, ${unit.name}: цель`" data-field="target" />
                      <button type="button" class="cm" :class="{ has: drafts[entryKey(ind.id, unit.id)].comment }" :aria-label="`Комментарий: ${ind.name}, ${unit.name}`"
                              :title="drafts[entryKey(ind.id, unit.id)].comment || 'Добавить комментарий'" data-field="comment" @click="openNote($event, ind, unit)">
                        <AppIcon name="note" :size="14" />
                      </button>
                    </div>
                    <span v-if="cellError(entryKey(ind.id, unit.id))" class="c-err">{{ cellError(entryKey(ind.id, unit.id)) }}</span>
                  </template>
                  <span v-else class="na" title="Вводить этот показатель здесь нельзя: подразделение вне вашей области для службы-владельца">—</span>
                </td>
                <td class="filler" aria-hidden="true" />
              </tr>
            </tbody>
          </table>
        </div>
        <footer class="legend">
          <span><i class="sw changed" />изменено</span>
          <span><i class="sw expected" />значение ожидается, но не заполнено</span>
          <span><i class="sw invalid" />ошибка</span>
          <span class="muted">Пустые значение, цель и комментарий удаляют сохранённое значение. Цель пустая — берётся цель показателя по умолчанию.</span>
        </footer>
      </section>
    </template>

    <Transition name="fade">
      <div v-if="dirty" class="savebar" role="region" aria-label="Несохранённые изменения">
        <span><b class="num">{{ dirty }}</b> {{ plural(dirty, ['ячейка изменена', 'ячейки изменены', 'ячеек изменено']) }}</span>
        <span class="spacer" />
        <button class="btn" type="button" :disabled="saving" @click="discard">Отменить</button>
        <button class="btn btn-primary" type="button" :disabled="saving" data-testid="entry-save" @click="save">
          <AppIcon name="check" :size="15" />{{ saving ? 'Сохраняю…' : 'Сохранить' }}
        </button>
      </div>
    </Transition>

    <Teleport to="body">
      <div v-if="note" class="note-scrim" @mousedown.self="closeNote" />
      <div v-if="note && drafts[note.key]" class="note-pop" :style="{ left: `${note.left}px`, top: `${note.top}px` }" role="dialog" aria-label="Комментарий к значению" @keydown="onNoteKey">
        <strong>{{ note.title }}</strong>
        <textarea v-model="drafts[note.key].comment" class="textarea" rows="4" maxlength="2000" placeholder="Почему так: причина отклонения, что делается" data-testid="entry-comment" />
        <div class="row"><span class="spacer" /><button type="button" class="btn btn-sm btn-primary" @click="closeNote">Готово</button></div>
      </div>
    </Teleport>

    <ImportValuesDialog v-if="importing" :period="period" @close="importing = false" @applied="reload()" @template="downloadTemplate" />
  </div>
</template>

<style scoped>
.entry { gap: var(--sp-4); padding-bottom: 72px; }
.expect-note, .save-error { display: flex; align-items: center; gap: 8px; padding: 10px 14px; border-radius: var(--radius); font-size: var(--fs-sm);
  border: 1px solid color-mix(in srgb, var(--light-red) 35%, var(--border)); background: color-mix(in srgb, var(--light-red) 7%, var(--surface)); color: var(--text); }
.expect-note :deep(svg), .save-error :deep(svg) { color: var(--light-red); flex: 0 0 auto; }
.expect-note > span { flex: 1; }
.save-error { color: var(--light-red); font-weight: 560; }

.grid-card { overflow: hidden; transition: opacity var(--t); }
.grid-card.busy { opacity: .6; }
.grid-scroll { overflow: auto; max-height: max(420px, calc(100dvh - var(--topbar-h) - 250px)); }
.eg { --first: 260px; --col: 200px; border-collapse: separate; border-spacing: 0; width: 100%; table-layout: fixed; }
.eg thead th { position: sticky; top: 0; z-index: 2; padding: 10px 10px 8px; text-align: left; vertical-align: bottom; background: var(--surface-2); border-bottom: 1px solid var(--border); }
.eg thead .corner { left: 0; z-index: 3; width: var(--first); padding-left: 16px; font-size: var(--fs-xs); font-weight: 650; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); border-right: 1px solid var(--border-strong); }
.ind { width: var(--col); }
.filler { width: auto; }
.i-name { display: block; font-size: var(--fs-sm); font-weight: 620; line-height: 1.3; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.i-meta { display: flex; align-items: center; gap: 6px; margin-top: 3px; font-size: 10.5px; color: var(--muted); font-weight: 520; min-width: 0; white-space: nowrap; }
.own { overflow: hidden; text-overflow: ellipsis; }
.cls { --c: var(--chart-1); flex: 0 0 auto; height: 16px; padding: 0 5px; display: inline-flex; align-items: center; border-radius: 4px; font-size: 9.5px; font-weight: 700; background: color-mix(in srgb, var(--c) 13%, transparent); color: color-mix(in srgb, var(--c) 78%, var(--text)); }
.c-financial { --c: var(--chart-3); }
.c-personal { --c: var(--chart-2); }
.i-cols { display: grid; grid-template-columns: 1fr 74px 30px; gap: 4px; margin-top: 6px; font-size: 10px; text-transform: uppercase; letter-spacing: .05em; color: var(--faint); font-weight: 650; }

.eg tbody th, .eg tbody td { border-bottom: 1px solid var(--border); background: var(--surface); }
.eg tbody tr:last-child > * { border-bottom: 0; }
.eg tbody tr:hover > * { background: var(--row-hover); }
.unit { position: sticky; left: 0; z-index: 1; width: var(--first); padding: 8px 12px 8px calc(16px + var(--indent) * 14px); text-align: left; font-weight: 400; border-right: 1px solid var(--border-strong); }
.u-name { display: block; font-size: var(--fs-sm); font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.u-meta { display: block; font-size: 10.5px; color: var(--muted); }
.cell { padding: 6px 8px; vertical-align: middle; }
.inputs { display: grid; grid-template-columns: 1fr 74px 30px; gap: 4px; align-items: center; }
.in { width: 100%; min-width: 0; height: 32px; padding: 0 8px; border: 1px solid var(--border-strong); border-radius: 8px; background: var(--surface); color: var(--text); font-variant-numeric: tabular-nums; text-align: right; transition: border-color var(--t-fast), box-shadow var(--t-fast), background var(--t-fast); }
.in.v { font-weight: 600; }
.in.t { font-size: var(--fs-sm); color: var(--text-2); }
.in::placeholder { color: var(--faint); font-weight: 400; }
.in:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px var(--focus); }
.cm { width: 30px; height: 32px; display: grid; place-items: center; padding: 0; border: 1px solid transparent; border-radius: 8px; background: transparent; color: var(--faint); cursor: pointer; }
.cm:hover { background: var(--surface-3); color: var(--text); }
.cm.has { color: var(--accent); background: color-mix(in srgb, var(--accent) 10%, transparent); }
.cell.changed .in { border-color: color-mix(in srgb, var(--accent) 60%, var(--border-strong)); background: color-mix(in srgb, var(--accent) 6%, var(--surface)); }
.cell.expected .in.v { border: 1.5px dashed var(--light-red); background: color-mix(in srgb, var(--light-red) 6%, var(--surface)); }
.cell.expected .in.v::placeholder { color: var(--light-red); font-weight: 600; }
.cell.invalid .in { border-color: var(--light-red); box-shadow: 0 0 0 2px color-mix(in srgb, var(--light-red) 18%, transparent); }
.c-err { display: block; margin-top: 3px; font-size: 10.5px; color: var(--light-red); line-height: 1.3; }
.na { display: block; text-align: center; color: var(--faint); }

.legend { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 16px; padding: 10px 16px; border-top: 1px solid var(--border); background: var(--surface-2); font-size: var(--fs-xs); color: var(--text-2); }
.legend span { display: inline-flex; align-items: center; gap: 6px; }
.sw { width: 16px; height: 11px; border-radius: 3px; border: 1px solid var(--border-strong); }
.sw.changed { border-color: var(--accent); background: color-mix(in srgb, var(--accent) 10%, var(--surface)); }
.sw.expected { border: 1.5px dashed var(--light-red); }
.sw.invalid { border-color: var(--light-red); box-shadow: 0 0 0 2px color-mix(in srgb, var(--light-red) 18%, transparent); }

.savebar {
  position: fixed; left: calc(var(--sb, 256px) + var(--sp-8)); right: var(--sp-8); bottom: 18px; z-index: 60; display: flex; align-items: center; gap: 10px;
  padding: 10px 12px 10px 18px; border-radius: 14px; border: 1px solid var(--border-strong); background: color-mix(in srgb, var(--bg-elevated) 94%, transparent);
  backdrop-filter: blur(8px); box-shadow: var(--shadow-lg); font-size: var(--fs-sm); max-width: var(--content-max);
}
.note-scrim { position: fixed; inset: 0; z-index: 90; }
.note-pop { position: fixed; z-index: 91; width: 300px; display: flex; flex-direction: column; gap: 8px; padding: 12px; border-radius: 12px; border: 1px solid var(--border); background: var(--bg-elevated); box-shadow: var(--shadow-lg); }
.note-pop strong { font-size: var(--fs-sm); }
@media (max-width: 960px) {
  .savebar { left: var(--sp-4); right: var(--sp-4); }
}
@media (max-width: 640px) {
  .eg { --first: 150px; --col: 184px; }
  .entry :deep(.page-actions) { width: 100%; }
}
</style>
