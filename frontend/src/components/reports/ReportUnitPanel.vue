<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import SideDrawer from '@/components/admin/SideDrawer.vue'
import MissingAlert from './MissingAlert.vue'
import ReasonList from './ReasonList.vue'
import StatusChip from './StatusChip.vue'
import TrendSpark from './TrendSpark.vue'
import { reportsApi } from '@/api/reports'
import { useAsync } from '@/composables/useAsync'
import { confirm } from '@/composables/useConfirm'
import { toastOk } from '@/composables/useToast'
import {
  DATA_CLASS_SHORT, INDICATOR_FORMS, UNIT_FORMS, count, noteByline, reasonText, ruleSummary, sortIndicators,
} from '@/domain/reports'
import { deltaTone, formatDelta, formatNumber, plural } from '@/utils/format'

/**
 * Панель подразделения (справа; на телефоне — лист снизу): путь, статус и объяснение (до 20 причин),
 * заметка «под контролем» (руководитель подразделения или «Сквозные отчёты» — правят её здесь),
 * все показатели со значением, целью, статусом, источником и трендом за 12 месяцев, вложенные
 * подразделения (переход), ссылки на дашборды и реестры служб.
 */
const props = defineProps({
  unitId: { type: Number, required: true },
  period: { type: String, default: '' },
  rootId: { type: Number, default: null },
  canOpen: { type: Function, default: () => true },
  hiddenNote: { type: String, default: '' },
  focusIndicator: { type: String, default: '' },
})
const emit = defineEmits(['close', 'select', 'root', 'changed'])

const { data, loading, error, reload } = useAsync(() => reportsApi.unit(props.unitId, { period: props.period || undefined }), { immediate: false })
const editing = ref(false)
watch(() => [props.unitId, props.period], () => {
  editing.value = false
  reload()
}, { immediate: true })

const unit = computed(() => (data.value?.unit?.id === props.unitId ? data.value.unit : null))
const me = computed(() => data.value?.me || {})
const indicators = computed(() => sortIndicators(data.value?.indicators || []))
const children = computed(() => data.value?.children || [])
const links = computed(() => data.value?.links || [])
const basis = computed(() => {
  const n = unit.value?.rated_count || 0
  const forms = props.hiddenNote ? ['доступному показателю', 'доступным показателям', 'доступным показателям'] : ['показателю', 'показателям', 'показателям']
  return n ? `Статус по ${n} ${plural(n, forms)}` : 'Нет оценённых показателей'
})
const missingItems = computed(() => (unit.value?.missing || []).map((m) => ({
  unit_id: unit.value.id, unit_name: unit.value.name, indicator: m.indicator, indicator_name: m.name,
})))
const childMissing = computed(() => children.value.reduce((sum, c) => sum + (c.missing_total || 0), 0))
const hiddenMissing = computed(() => {
  const rest = (unit.value?.missing_total || 0) - (unit.value?.missing?.length || 0) - childMissing.value
  return rest > 0 ? `${count(rest, ['пропуск', 'пропуска', 'пропусков'])} во вложенных подразделениях (детализация недоступна)` : ''
})

// ---------------------------------------------------------------- заметка «под контролем»
const draft = ref('')
const saving = ref(false)
const noteError = ref('')
function startNote() {
  draft.value = unit.value?.note?.comment || ''
  noteError.value = ''
  editing.value = true
  nextTick(() => document.querySelector('[data-testid="note-comment"]')?.focus())
}
async function saveNote() {
  if (!draft.value.trim()) {
    noteError.value = 'Напишите, что делается: заметка «под контролем» — с комментарием'
    return
  }
  saving.value = true
  noteError.value = ''
  try {
    await reportsApi.saveNote(props.unitId, { period: data.value.period, status: 'watch', comment: draft.value.trim() })
    toastOk('Отметка «Под контролем» сохранена')
    editing.value = false
    await reload()
    emit('changed')
  } catch (e) {
    noteError.value = e.fields?.comment || e.message
  } finally {
    saving.value = false
  }
}
async function removeNote() {
  const ok = await confirm({ title: 'Снять отметку «Под контролем»?', message: `Заметка о статусе «${unit.value.name}» за ${data.value.period_label.toLowerCase()} будет удалена. Расчётный статус не меняется.`, confirmText: 'Снять отметку', danger: true })
  if (!ok) return
  try {
    await reportsApi.saveNote(props.unitId, { period: data.value.period, status: null, comment: '' })
    toastOk('Отметка снята')
    await reload()
    emit('changed')
  } catch {}
}

// ---------------------------------------------------------------- показатели
function deltaText(ind) {
  const cell = ind.cell
  if (!cell || cell.delta === null || cell.delta === undefined || cell.missing) return ''
  return `${formatDelta(cell.delta, ind.unit) || '±0'} к прошлому месяцу`
}
const tone = (ind) => (ind.cell?.missing ? 'missing' : ind.cell?.status || 'gray')

// Переход к показателю, по ячейке которого открыли панель
watch([data, () => props.focusIndicator], async () => {
  if (!props.focusIndicator || !unit.value) return
  await nextTick()
  const el = document.querySelector(`[data-panel-indicator="${CSS.escape(props.focusIndicator)}"]`)
  if (!el) return
  el.scrollIntoView({ block: 'center', behavior: 'smooth' })
  el.classList.remove('flash')
  void el.offsetWidth
  el.classList.add('flash')
}, { flush: 'post' })
</script>

<template>
  <SideDrawer :title="unit?.name || 'Подразделение'" :width="640" sheet @close="emit('close')">
    <template #header>
      <div class="ph" data-testid="report-panel">
        <nav v-if="data?.breadcrumbs?.length && unit" class="crumbs" aria-label="Путь в структуре">
          <template v-for="(c, i) in data.breadcrumbs" :key="c.id">
            <span v-if="i" class="sep">›</span>
            <button type="button" @click="emit('select', c.id)">{{ c.name }}</button>
          </template>
        </nav>
        <h2 class="ph-title">{{ unit?.name || (loading ? 'Загрузка…' : 'Подразделение') }}</h2>
        <div v-if="unit" class="ph-tags">
          <StatusChip :status="unit.status" :label="unit.status_label" size="lg" />
          <span class="ph-kind">{{ unit.kind_label }}</span>
          <span v-if="unit.code" class="ph-code">{{ unit.code }}</span>
          <span class="ph-basis">{{ basis }}</span>
        </div>
      </div>
    </template>

    <div v-if="loading && !unit" class="stack">
      <div class="skeleton" style="height: 90px" />
      <div class="skeleton" style="height: 220px" />
    </div>
    <EmptyState v-else-if="error && !unit" compact :icon="error.status === 403 ? 'lock' : 'alert'"
                :title="error.status === 403 ? 'Подразделение вне вашей области' : error.status === 404 ? 'Подразделение не найдено' : 'Не удалось загрузить подразделение'"
                :text="error.message">
      <button class="btn btn-sm" type="button" @click="reload()">Повторить</button>
    </EmptyState>

    <div v-else-if="unit" class="pb" :class="{ busy: loading }">
      <div v-if="(children.length && unit.id !== rootId) || (rootId && unit.id === rootId) || links.length" class="ph-actions">
        <button v-if="children.length && unit.id !== rootId" type="button" class="btn btn-sm" title="Показать в отчёте только эту ветку" data-testid="panel-root" @click="emit('root', unit.id)">
          <AppIcon name="layers" :size="14" />Открыть ветку
        </button>
        <button v-if="rootId && unit.id === rootId" type="button" class="btn btn-sm" @click="emit('root', null)"><AppIcon name="layers" :size="14" />Вся область</button>
        <div v-if="links.length" class="ph-links" data-testid="panel-links">
          <span class="pl-label">Данные служб</span>
          <template v-for="l in links" :key="l.service">
            <router-link :to="l.dashboard_url" class="pl" :title="`Дашборд службы «${l.title}»`"><AppIcon name="grid" :size="13" />{{ l.title }}</router-link>
            <router-link v-if="l.records_url" :to="l.records_url" class="pl" :title="`Исходные записи службы «${l.title}»`"><AppIcon name="list" :size="13" />Реестр</router-link>
          </template>
        </div>
      </div>

      <MissingAlert v-if="missingItems.length || hiddenMissing" compact :items="missingItems" :hidden="hiddenMissing" :period="data.period_label" @select="(id) => id !== unit.id && emit('select', id)" />
      <p v-if="childMissing > 0" class="p-hint miss"><AppIcon name="alert" :size="13" />Во вложенных подразделениях не заполнено показателей: {{ childMissing }} — откройте подразделение ниже.</p>
      <p v-if="unit.drill_locked" class="p-hint"><AppIcon name="lock" :size="13" />Детализация недоступна: вложенные подразделения входят в свёртку значений, но вам не видны.</p>

      <section class="ps">
        <h3>Почему такой статус</h3>
        <ReasonList v-if="unit.explanation.items.length" :items="unit.explanation.items" :can-open="(id) => id !== unit.id && canOpen(id)" dense @select="(id) => emit('select', id)" />
        <p v-else class="p-ok"><AppIcon name="check" :size="14" :stroke="2.4" />{{ reasonText(unit.explanation.text) || 'Оценённых показателей нет' }}</p>
        <p v-if="unit.explanation.more" class="p-more">и ещё {{ unit.explanation.more }}</p>
      </section>

      <section class="ps">
        <h3>Отметка руководителя</h3>
        <div v-if="unit.note && !editing" class="note" data-testid="panel-note">
          <span class="n-icon"><AppIcon name="eye" :size="15" /></span>
          <div class="n-text">
            <strong>{{ unit.note.status_label }}</strong>
            <p>{{ unit.note.comment }}</p>
            <small>{{ noteByline(unit.note) }}</small>
          </div>
          <div v-if="me.can_note" class="n-actions">
            <button type="button" class="btn btn-sm btn-ghost" data-testid="note-edit" @click="startNote"><AppIcon name="edit" :size="13" />Изменить</button>
            <button type="button" class="btn btn-sm btn-ghost btn-danger" @click="removeNote">Снять</button>
          </div>
        </div>
        <form v-else-if="editing" class="note-form" @submit.prevent="saveNote">
          <label class="field">
            <span>Что делается — комментарий к отметке «Под контролем»</span>
            <textarea v-model="draft" class="textarea" :class="{ invalid: noteError }" rows="3" maxlength="2000" data-testid="note-comment"
                      placeholder="Например: очередь разбираем, подключены инженеры смежной группы, срок — конец месяца" />
            <span v-if="noteError" class="error">{{ noteError }}</span>
            <span v-else class="help">Расчётный статус не меняется — заметка показывается рядом с ним за {{ data.period_label.toLowerCase() }}.</span>
          </label>
          <div class="row">
            <button type="submit" class="btn btn-primary btn-sm" :disabled="saving" data-testid="note-save">{{ saving ? 'Сохраняю…' : 'Сохранить' }}</button>
            <button type="button" class="btn btn-sm" @click="editing = false">Отмена</button>
          </div>
        </form>
        <div v-else class="note-empty">
          <span class="p-muted">Отметки нет. Руководитель подразделения может отметить статус «под контролем» с комментарием.</span>
          <button v-if="me.can_note" type="button" class="btn btn-sm" data-testid="note-add" @click="startNote"><AppIcon name="eye" :size="14" />Под контролем</button>
        </div>
      </section>

      <section class="ps">
        <h3>Показатели <span class="count">{{ indicators.length }}</span><span class="h-sub">за {{ data.period_label.toLowerCase() }} · тренд за 12 месяцев</span></h3>
        <p v-if="!indicators.length" class="p-muted">За последние 12 месяцев у подразделения нет значений доступных вам показателей.</p>
        <ul class="inds">
          <li v-for="ind in indicators" :key="ind.key" class="ind" :class="`t-${tone(ind)}`" :data-panel-indicator="ind.key">
            <div class="i-head">
              <span class="i-name" :title="ind.description">{{ ind.name }}</span>
              <span class="cls" :class="`c-${ind.data_class}`" :title="ind.data_class_label">{{ DATA_CLASS_SHORT[ind.data_class] }}</span>
              <span class="spacer" />
              <StatusChip :status="ind.cell?.status || 'gray'" :label="ind.cell?.status_label || 'Нет значения'" :missing="!!ind.cell?.missing" size="sm" />
            </div>
            <div class="i-body">
              <div class="i-figs">
                <div class="i-value">
                  <template v-if="ind.cell?.missing"><span class="i-miss">Не заполнено</span></template>
                  <template v-else>{{ formatNumber(ind.cell?.value) }}<small v-if="ind.unit && ind.cell && ind.cell.value !== null">{{ ind.unit === '%' ? '%' : ` ${ind.unit}` }}</small></template>
                </div>
                <div class="i-sub">
                  <span v-if="ind.cell?.target !== null && ind.cell?.target !== undefined">цель {{ formatNumber(ind.cell.target, { unit: ind.unit }) }}</span>
                  <span v-if="ind.cell?.deviation">отклонение {{ formatNumber(ind.cell.deviation, { unit: '%' }) }}</span>
                </div>
                <div v-if="deltaText(ind)" class="i-delta" :class="`delta-${deltaTone(ind.cell.delta, ind.direction)}`">
                  <AppIcon v-if="ind.cell.delta" :name="ind.cell.delta > 0 ? 'arrow-up' : 'arrow-down'" :size="12" :stroke="2.4" />{{ deltaText(ind) }}
                </div>
              </div>
              <TrendSpark class="i-spark" :trend="ind.trend" :unit="ind.unit" />
            </div>
            <div class="i-foot">
              <span v-if="ind.cell?.source_label" class="src"><AppIcon :name="ind.source_type === 'computed' ? 'refresh' : 'edit'" :size="11" />{{ ind.cell.source_label }}</span>
              <span class="rule">{{ ruleSummary(ind) }}</span>
              <router-link v-if="ind.dashboard_url" :to="ind.dashboard_url" class="src-link">{{ ind.origin }}</router-link>
              <span v-else class="origin">{{ ind.origin }}</span>
            </div>
            <p v-if="ind.cell?.comment" class="i-comment"><AppIcon name="note" :size="12" />{{ ind.cell.comment }}</p>
          </li>
        </ul>
      </section>

      <section v-if="children.length || unit.drill_locked" class="ps">
        <h3>Вложенные подразделения <span class="count">{{ children.length }}</span></h3>
        <p v-if="!children.length" class="p-muted">Вложенные подразделения за пределом вашей детализации.</p>
        <div class="kids">
          <button v-for="c in children" :key="c.id" type="button" class="kid" :class="`s-${c.status}`" :data-child="c.id" @click="emit('select', c.id)">
            <i class="k-dot" aria-hidden="true" />
            <span class="k-text">
              <span class="k-name">{{ c.name }}</span>
              <small>{{ c.kind_label }}<template v-if="c.indicator_count"> · {{ count(c.indicator_count, INDICATOR_FORMS) }}</template><template v-if="c.has_children && !c.drill_locked"> · есть вложенные</template></small>
            </span>
            <AppIcon v-if="c.note" class="k-note" name="eye" :size="14" :title="c.note.comment" />
            <span v-if="c.missing_total" class="k-miss" title="Не заполнено — критичное нарушение"><AppIcon name="alert" :size="11" :stroke="2.4" />{{ c.missing_total }}</span>
            <AppIcon v-if="c.drill_locked" name="lock" :size="13" class="k-lock" title="Детализация недоступна" />
            <StatusChip :status="c.status" :label="c.status_label" size="sm" />
            <AppIcon name="chevron-right" :size="14" class="k-go" />
          </button>
        </div>
      </section>

      <p v-if="!links.length" class="p-foot">Переходы к дашбордам служб появляются при доступе к службе — показатели из её данных.</p>
      <p class="p-foot">{{ count(indicators.length, INDICATOR_FORMS) }}<template v-if="children.length"> · {{ count(children.length, UNIT_FORMS) }}</template> · {{ data.access.text }}</p>
    </div>
  </SideDrawer>
</template>

<style scoped>
.ph { min-width: 0; }
.crumbs { display: flex; flex-wrap: wrap; align-items: center; gap: 2px 4px; margin-bottom: 6px; font-size: var(--fs-xs); color: var(--muted); }
.crumbs button { padding: 1px 3px; border: 0; border-radius: 4px; background: transparent; color: var(--text-2); font: inherit; cursor: pointer; }
.crumbs button:hover { color: var(--accent); text-decoration: underline; }
.crumbs .sep { color: var(--faint); }
.ph-title { font-size: var(--fs-xl); font-weight: 690; letter-spacing: -0.015em; line-height: 1.2; overflow-wrap: anywhere; }
.ph-tags { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 10px; margin-top: 10px; }
.ph-kind { font-size: var(--fs-sm); color: var(--text-2); font-weight: 560; }
.ph-code { display: inline-flex; align-items: center; height: 21px; padding: 0 7px; border-radius: 6px; background: var(--surface-3); font-family: var(--font-mono); font-size: var(--fs-xs); font-weight: 600; color: var(--text-2); }
.ph-basis { font-size: var(--fs-xs); color: var(--muted); }

.pb { display: flex; flex-direction: column; gap: 16px; transition: opacity var(--t); }
.pb.busy { opacity: .6; }
.ph-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px; }
.ph-links { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 6px; min-width: 0; }
.pl-label { font-size: var(--fs-xs); color: var(--muted); margin-right: 2px; }
.pl { display: inline-flex; align-items: center; gap: 5px; height: 26px; padding: 0 9px; border-radius: var(--radius-pill); background: color-mix(in srgb, var(--accent) 9%, transparent); color: var(--accent); font-size: var(--fs-xs); font-weight: 600; }
.pl:hover { background: color-mix(in srgb, var(--accent) 16%, transparent); }
.p-hint { display: flex; align-items: flex-start; gap: 7px; padding: 9px 12px; border-radius: 10px; background: var(--surface-2); font-size: var(--fs-sm); color: var(--text-2); line-height: 1.45; }
.p-hint :deep(svg) { margin-top: 3px; flex: 0 0 auto; color: var(--muted); }
.p-hint.miss { color: var(--light-red); background: color-mix(in srgb, var(--light-red) 7%, transparent); }
.p-hint.miss :deep(svg) { color: var(--light-red); }

.ps h3 { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; font-size: var(--fs-xs); font-weight: 650; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); }
.ps h3 .count { padding: 0 6px; border-radius: var(--radius-pill); background: var(--surface-3); color: var(--text-2); letter-spacing: 0; font-weight: 620; }
.ps h3 .h-sub { text-transform: none; letter-spacing: 0; font-weight: 500; color: var(--faint); }
.p-ok { display: flex; align-items: center; gap: 7px; font-size: var(--fs-sm); color: var(--text-2); }
.p-ok :deep(svg) { color: var(--light-green); }
.p-more { margin: 4px 8px 0; font-size: var(--fs-xs); color: var(--muted); }
.p-muted { font-size: var(--fs-sm); color: var(--muted); }
.p-foot { font-size: var(--fs-xs); color: var(--faint); }

.note { display: flex; align-items: flex-start; gap: 12px; padding: 12px 14px; border-radius: var(--radius); border: 1px solid color-mix(in srgb, var(--accent) 28%, var(--border)); background: color-mix(in srgb, var(--accent) 6%, var(--surface)); }
.n-icon { width: 28px; height: 28px; flex: 0 0 28px; display: grid; place-items: center; border-radius: 50%; background: color-mix(in srgb, var(--accent) 14%, transparent); color: var(--accent); }
.n-text { flex: 1; min-width: 0; font-size: var(--fs-sm); line-height: 1.45; }
.n-text strong { color: var(--accent); }
.n-text small { color: var(--muted); font-size: var(--fs-xs); }
.n-actions { display: flex; flex-direction: column; gap: 2px; }
.note-form { display: flex; flex-direction: column; gap: 10px; padding: 12px 14px; border-radius: var(--radius); border: 1px solid var(--border); background: var(--surface-2); }
.note-empty { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; justify-content: space-between; padding: 10px 12px; border-radius: var(--radius); border: 1px dashed var(--border-strong); }
.note-empty .p-muted { flex: 1 1 260px; font-size: var(--fs-xs); }

.inds { display: flex; flex-direction: column; gap: 8px; margin: 0; padding: 0; list-style: none; }
.ind {
  --tone: var(--light-gray);
  position: relative; display: flex; flex-direction: column; gap: 6px; padding: 12px 14px 10px 16px; border-radius: 12px;
  border: 1px solid var(--border); background: var(--surface); overflow: hidden;
}
.ind::before { content: ''; position: absolute; left: 0; top: 12px; bottom: 12px; width: 3px; border-radius: 0 3px 3px 0; background: var(--tone); }
.ind.t-green { --tone: var(--light-green); }
.ind.t-yellow { --tone: var(--light-yellow); }
.ind.t-red { --tone: var(--light-red); }
.ind.t-gray::before { background: transparent; }
.ind.t-missing { --tone: var(--light-red); border-color: color-mix(in srgb, var(--light-red) 40%, var(--border)); }
.ind.t-missing::before { background: repeating-linear-gradient(180deg, var(--light-red) 0 6px, transparent 6px 10px); }
.ind.flash { animation: ind-flash 1.6s var(--ease); }
@keyframes ind-flash { 0%, 100% { box-shadow: 0 0 0 0 transparent; } 20%, 60% { box-shadow: 0 0 0 4px color-mix(in srgb, var(--accent) 30%, transparent); } }
.i-head { display: flex; align-items: center; gap: 7px; min-width: 0; }
.i-name { font-size: var(--fs-base); font-weight: 630; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cls { --c: var(--chart-1); flex: 0 0 auto; height: 16px; padding: 0 5px; display: inline-flex; align-items: center; border-radius: 4px; font-size: 9.5px; font-weight: 700; background: color-mix(in srgb, var(--c) 13%, transparent); color: color-mix(in srgb, var(--c) 78%, var(--text)); }
.c-financial { --c: var(--chart-3); }
.c-personal { --c: var(--chart-2); }
.i-body { display: grid; grid-template-columns: minmax(0, 5fr) minmax(0, 6fr); gap: 14px; align-items: center; }
.i-value { font-size: 24px; font-weight: 700; letter-spacing: -0.02em; line-height: 1.15; }
.i-value small { font-size: var(--fs-sm); font-weight: 560; color: var(--muted); letter-spacing: 0; }
.i-miss { font-size: var(--fs-md); color: var(--light-red); font-weight: 680; }
.i-sub { display: flex; flex-wrap: wrap; gap: 2px 10px; margin-top: 3px; font-size: var(--fs-xs); color: var(--text-2); font-variant-numeric: tabular-nums; }
.i-delta { display: inline-flex; align-items: center; gap: 3px; margin-top: 3px; font-size: var(--fs-xs); font-weight: 620; }
.i-spark { height: 56px; }
.i-foot { display: flex; flex-wrap: wrap; align-items: center; gap: 3px 12px; font-size: 10.5px; color: var(--muted); }
.src { display: inline-flex; align-items: center; gap: 4px; color: var(--text-2); font-weight: 560; }
.src-link { color: var(--accent); }
.src-link:hover { text-decoration: underline; }
.i-comment { display: flex; gap: 6px; padding-top: 6px; border-top: 1px dashed var(--border); font-size: var(--fs-xs); color: var(--text-2); }
.i-comment :deep(svg) { margin-top: 2px; flex: 0 0 auto; color: var(--muted); }

.kids { display: flex; flex-direction: column; gap: 1px; margin: 0 -8px; }
.kid { --tone: var(--light-gray); display: flex; align-items: center; gap: 10px; width: 100%; min-height: 44px; padding: 6px 8px; border: 0; border-radius: 10px; background: transparent; color: var(--text); text-align: left; cursor: pointer; transition: background var(--t-fast); }
.kid:hover { background: var(--surface-3); }
.kid:focus-visible { outline: 2px solid var(--focus); outline-offset: -2px; }
.kid.s-green { --tone: var(--light-green); }
.kid.s-yellow { --tone: var(--light-yellow); }
.kid.s-red { --tone: var(--light-red); }
.k-dot { width: 9px; height: 9px; flex: 0 0 9px; border-radius: 50%; background: var(--tone); }
.k-text { flex: 1; min-width: 0; display: flex; flex-direction: column; line-height: 1.3; }
.k-name { font-size: var(--fs-sm); font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.k-text small { font-size: var(--fs-xs); color: var(--muted); }
.k-note { color: var(--accent); }
.k-lock, .k-go { color: var(--faint); }
.k-miss { display: inline-flex; align-items: center; gap: 2px; height: 19px; padding: 0 6px; border-radius: var(--radius-pill); background: color-mix(in srgb, var(--light-red) 12%, transparent); color: var(--light-red); font-size: 10.5px; font-weight: 700; }

@media (max-width: 560px) {
  .i-body { grid-template-columns: minmax(0, 1fr); gap: 6px; }
  .i-spark { height: 48px; }
  .ph-title { font-size: var(--fs-lg); }
}
</style>
