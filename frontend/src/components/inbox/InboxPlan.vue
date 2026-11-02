<script setup>
import { computed, ref, watch } from 'vue'
import SegmentedControl from '@/components/ui/SegmentedControl.vue'
import PlanChips from '@/components/transfer/PlanChips.vue'
import TransferBanner from '@/components/transfer/TransferBanner.vue'
import {
  PLAN_FILTERS, filterPlanRows, planChips, planErrors, planHeads, planNewDepartments, planRows, rowAction,
} from '@/domain/inbox'
import { CHOICE_LABELS, decisionFor, displayValue, visibleChoices, withFieldChoice, withIdentity } from '@/domain/org'

/**
 * План элемента входящих — как в остальных загрузках: сводка чипами (новые, изменения, ошибки),
 * список ошибок, строки плана с действием. Подходит для плана любого набора: поля движков сводятся
 * к одному виду (domain/inbox.js). Различия у сотрудников (decisions) можно решить здесь же.
 */
const props = defineProps({
  plan: { type: Object, required: true },
  title: { type: String, default: 'Что изменится' },
  source: { type: String, default: '' },
  rejected: { type: String, default: '' },
  decisions: { type: Object, default: null },
})
const emit = defineEmits(['update:decisions'])

const chips = computed(() => planChips(props.plan.summary))
const errors = computed(() => planErrors(props.plan, 200))
const rows = computed(() => planRows(props.plan))
const hasValues = computed(() => rows.value.some((r) => r.before !== null || r.after !== null))
const heads = computed(() => planHeads(props.plan))
const newDepartments = computed(() => planNewDepartments(props.plan))
const notes = computed(() => (Array.isArray(props.plan.notes) ? props.plan.notes : []))

const filter = ref(props.plan.summary?.errors || props.plan.summary?.unresolved ? 'errors' : 'changes')
watch(() => props.plan, (plan) => { if (plan.summary?.errors || plan.summary?.unresolved) filter.value = 'errors' })
const shown = computed(() => filterPlanRows(rows.value, filter.value))
const PAGE = 100
const limit = ref(PAGE)
watch(filter, () => { limit.value = PAGE })
const visible = computed(() => shown.value.slice(0, limit.value))
const ERRORS_SHOWN = 12
const errorsOpen = ref(false)

const editable = computed(() => props.decisions !== null)
const choicesOf = (conflict) => visibleChoices(conflict).filter((c) => c !== 'custom')
function choose(row, conflict, choice) {
  emit('update:decisions', withFieldChoice(props.decisions || {}, row.raw.key, conflict.field, choice))
}
function setIdentity(row, identity) {
  emit('update:decisions', withIdentity(props.decisions || {}, row.raw.key, identity))
}
const emptyText = computed(() => {
  if (!rows.value.length) return 'В плане нет строк'
  if (filter.value === 'errors') return 'Ошибок нет'
  if (filter.value === 'changes') return 'Изменений нет — данные в файле совпадают с системой'
  return 'В плане нет строк'
})
</script>

<template>
  <section class="iplan" data-testid="inbox-plan">
    <header class="iplan-head">
      <div>
        <h3>{{ title }}</h3>
        <p v-if="source" class="muted small">{{ source }}</p>
      </div>
      <PlanChips :chips="chips" />
    </header>

    <TransferBanner v-if="rejected" tone="error" :title="rejected" text="Ничего не записано: план построен заново по текущим данным системы — исправьте ошибки и повторите." data-testid="plan-rejected" />

    <TransferBanner v-if="errors.length" tone="error" :title="`Ошибки в плане · ${errors.length}`" data-testid="plan-errors">
      <ul class="err-list">
        <li v-for="e in (errorsOpen ? errors : errors.slice(0, ERRORS_SHOWN))" :key="e">{{ e }}</li>
      </ul>
      <button v-if="errors.length > ERRORS_SHOWN" type="button" class="link-btn" @click="errorsOpen = !errorsOpen">
        {{ errorsOpen ? 'Свернуть' : `Показать все ${errors.length}` }}
      </button>
    </TransferBanner>

    <TransferBanner v-if="notes.length" tone="info" title="Обратите внимание">
      <ul class="err-list"><li v-for="n in notes" :key="n">{{ n }}</li></ul>
    </TransferBanner>

    <div v-if="newDepartments.length" class="block">
      <h4>Будут созданы подразделения · {{ newDepartments.length }}</h4>
      <ul class="list-inline"><li v-for="d in newDepartments" :key="d.key || d.path">{{ d.path || d.name }}</li></ul>
    </div>
    <div v-if="heads.length" class="block">
      <h4>Руководители · {{ heads.length }}</h4>
      <ul class="list-inline">
        <li v-for="h in heads" :key="`${h.path}-${h.name}`" :class="`h-${h.action}`">{{ h.name || h.email }} — {{ h.path }}<small> · {{ h.action === 'add' ? 'назначить' : 'нет в системе' }}</small></li>
      </ul>
    </div>

    <div v-if="rows.length" class="block">
      <div class="block-title">
        <h4>Строки плана</h4>
        <SegmentedControl v-model="filter" :options="PLAN_FILTERS" size="sm" />
      </div>
      <div v-if="visible.length" class="table-wrap bordered scroll-thin">
        <table class="table table-compact rows">
          <thead>
            <tr>
              <th class="num">Строка</th>
              <th>Запись</th>
              <template v-if="hasValues"><th>Было</th><th>Станет</th></template>
              <th>Действие</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in visible" :key="r.key" :class="{ err: r.errors.length || r.unresolved }">
              <td class="num muted line">{{ r.line ?? '—' }}</td>
              <td class="what">
                <b>{{ r.title }}</b>
                <small v-if="r.subtitle">{{ r.subtitle }}</small>
              </td>
              <template v-if="hasValues">
                <td class="muted val"><span class="lbl">Было: </span>{{ r.before ?? '—' }}</td>
                <td class="val"><span class="lbl">Станет: </span>{{ r.after ?? '—' }}</td>
              </template>
              <td class="act">
                <span class="badge" :class="`badge-${rowAction(r).tone}`">{{ rowAction(r).label }}</span>
                <ul v-if="r.changes.length" class="lines"><li v-for="c in r.changes" :key="c">{{ c }}</li></ul>
                <ul v-if="r.errors.length" class="lines errs"><li v-for="e in r.errors" :key="e">{{ e }}</li></ul>
                <ul v-if="r.warnings.length" class="lines warns"><li v-for="w in r.warnings" :key="w">{{ w }}</li></ul>

                <div v-if="r.identity" class="identity">
                  <p>Сотрудника с таким email нет, но логин занят: <b>{{ r.identity.name }}</b><template v-if="r.identity.email"> ({{ r.identity.email }})</template>. Это тот же человек?</p>
                  <SegmentedControl v-if="editable" :model-value="decisions?.[r.raw.key]?.identity || null" size="sm"
                                    :options="[{ value: 'same', label: 'Тот же — обновить' }, { value: 'new', label: 'Новый сотрудник' }]"
                                    @update:model-value="setIdentity(r, $event)" />
                </div>
                <table v-if="r.conflicts.length" class="conflicts">
                  <tbody>
                    <tr v-for="c in r.conflicts" :key="c.field">
                      <th scope="row">{{ c.label }}</th>
                      <td><span class="lbl">Система: </span>{{ displayValue(c.current) }}</td>
                      <td><span class="lbl">Файл: </span>{{ displayValue(c.incoming) }}</td>
                      <td>
                        <div v-if="editable" class="choices" role="radiogroup" :aria-label="`Решение: ${c.label}`">
                          <button v-for="choice in choicesOf(c)" :key="choice" type="button" role="radio" :aria-checked="decisionFor(decisions, r.raw, c) === choice"
                                  :class="{ active: decisionFor(decisions, r.raw, c) === choice }" @click="choose(r, c, choice)">{{ CHOICE_LABELS[choice] }}</button>
                        </div>
                        <span v-else class="muted">{{ CHOICE_LABELS[decisionFor({}, r.raw, c)] }}</span>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="empty">{{ emptyText }}</p>
      <button v-if="shown.length > visible.length" type="button" class="btn btn-ghost btn-sm more" @click="limit += PAGE">
        Показать ещё {{ Math.min(PAGE, shown.length - visible.length) }} из {{ shown.length - visible.length }}
      </button>
    </div>
    <p v-else-if="!errors.length" class="empty">В плане нет строк</p>
  </section>
</template>

<style scoped>
.iplan { display: flex; flex-direction: column; gap: 14px; min-width: 0; }
.iplan-head { display: flex; flex-wrap: wrap; align-items: flex-start; justify-content: space-between; gap: 10px 20px; }
.iplan-head h3 { font-size: var(--fs-md); font-weight: 650; }
.small { font-size: var(--fs-xs); margin-top: 2px; overflow-wrap: anywhere; }
.err-list { margin: 4px 0 0; padding-left: 18px; display: flex; flex-direction: column; gap: 2px; overflow-wrap: anywhere; }
.link-btn { margin-top: 6px; padding: 0; border: 0; background: transparent; color: var(--accent); font-size: var(--fs-sm); cursor: pointer; }
.link-btn:hover { text-decoration: underline; }
.block h4 { margin: 0 0 8px; font-size: var(--fs-xs); font-weight: 650; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); }
.block-title { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px 16px; margin-bottom: 8px; }
.block-title h4 { margin: 0; }
.list-inline { display: flex; flex-wrap: wrap; gap: 6px; margin: 0; padding: 0; list-style: none; }
.list-inline li { padding: 3px 10px; border-radius: var(--radius-pill); background: var(--surface-3); font-size: var(--fs-sm); color: var(--text-2); overflow-wrap: anywhere; }
.list-inline li small { color: var(--muted); }
.list-inline li.h-pending small { color: color-mix(in srgb, var(--light-yellow) 80%, var(--text)); }
.bordered { border: 1px solid var(--border); border-radius: 12px; max-height: 420px; }
.rows td { vertical-align: top; font-size: var(--fs-sm); }
.line { width: 64px; }
.what b { display: block; font-weight: 600; overflow-wrap: anywhere; }
.what small { display: block; color: var(--muted); font-size: var(--fs-xs); overflow-wrap: anywhere; }
.val { white-space: nowrap; }
.lbl { display: none; color: var(--muted); }
.act { min-width: 180px; }
.badge-blue { background: color-mix(in srgb, var(--accent) 13%, transparent); color: var(--accent); }
tr.err td { background: color-mix(in srgb, var(--light-red) 5%, transparent); }
.lines { margin: 4px 0 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 1px; font-size: var(--fs-xs); color: var(--text-2); overflow-wrap: anywhere; }
.errs { color: var(--light-red); }
.warns { color: color-mix(in srgb, var(--light-yellow) 80%, var(--text)); }
.identity { margin-top: 8px; display: flex; flex-direction: column; gap: 6px; padding: 8px 10px; border-radius: 10px; background: color-mix(in srgb, var(--light-yellow) 10%, transparent); font-size: var(--fs-xs); }
.conflicts { margin-top: 8px; border-collapse: collapse; font-size: var(--fs-xs); width: 100%; }
.conflicts th, .conflicts td { padding: 4px 6px; border-top: 1px solid var(--border); text-align: left; vertical-align: top; font-weight: 500; overflow-wrap: anywhere; }
.conflicts th { color: var(--text-2); font-weight: 600; }
.conflicts .lbl { display: inline; }
.choices { display: inline-flex; flex-wrap: wrap; gap: 2px; padding: 2px; border-radius: 9px; background: var(--surface-3); border: 1px solid var(--border); }
.choices button { height: 22px; padding: 0 8px; border: 0; border-radius: 7px; background: transparent; color: var(--text-2); font-size: var(--fs-xs); font-weight: 560; cursor: pointer; }
.choices button.active { background: var(--bg-elevated); color: var(--text); box-shadow: var(--shadow-sm); font-weight: 650; }
.empty { display: flex; align-items: center; justify-content: center; gap: 6px; padding: 14px; border: 1px dashed var(--border-strong); border-radius: 12px; text-align: center; font-size: var(--fs-sm); color: var(--muted); }
.more { margin-top: 8px; }
.muted { color: var(--muted); }
@media (max-width: 720px) {
  .rows thead { display: none; }
  .rows tr { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 2px 10px; padding: 8px 10px; border-bottom: 1px solid var(--border); }
  .rows td { padding: 0; border: 0; background: transparent !important; }
  .rows td.line { grid-row: span 3; width: auto; }
  .rows td.val { white-space: normal; }
  .rows .lbl { display: inline; }
  .rows tr:last-child { border-bottom: 0; }
  .conflicts tr { display: grid; grid-template-columns: 1fr; }
}
</style>
