<script setup>
import { computed } from 'vue'
import { MONTHS, MONTHS_SHORT } from '@/utils/format'
import { fillState, groupMonthsByYear } from '@/domain/hrDataEntry'

/**
 * Выбор месяца: строка на год, двенадцать ячеек. Точка в ячейке — заполненность метрик.
 * Пустая ячейка (месяца ещё нет) при canAdd предлагает добавить этот месяц.
 */
const props = defineProps({
  months: { type: Array, default: () => [] },
  modelValue: { type: String, default: '' },
  canAdd: { type: Boolean, default: false },
})
const emit = defineEmits(['select', 'add'])

const years = computed(() => groupMonthsByYear(props.months).map((y) => {
  const byMonth = Object.fromEntries(y.months.map((m) => [m.month, m]))
  return { year: y.year, cells: MONTHS_SHORT.map((short, i) => ({ index: i + 1, short, month: byMonth[i + 1] || null })) }
}))

const FILL_LABELS = { full: 'заполнены все метрики', partial: 'заполнены не все метрики', empty: 'метрики не заполнены' }
function title(m) {
  return `${m.label}: ${m.filled_metrics} из ${m.total_metrics} метрик (${FILL_LABELS[fillState(m)]}), принято ${m.hired}, уволено ${m.fired}`
}
</script>

<template>
  <div class="picker card">
    <div v-for="y in years" :key="y.year" class="year">
      <span class="year-label num">{{ y.year }}</span>
      <div class="cells">
        <template v-for="c in y.cells" :key="c.index">
          <button v-if="c.month" type="button" class="cell" :class="{ active: c.month.key === modelValue }" :title="title(c.month)"
                  :aria-pressed="c.month.key === modelValue" @click="emit('select', c.month.key)">
            <span class="fill" :class="fillState(c.month)" />{{ c.short }}
          </button>
          <button v-else-if="canAdd" type="button" class="cell ghost" :title="`Добавить месяц «${MONTHS[c.index - 1]} ${y.year}»`"
                  @click="emit('add', { year: y.year, month: c.index })">{{ c.short }}</button>
          <span v-else class="cell ghost" aria-hidden="true">{{ c.short }}</span>
        </template>
      </div>
    </div>
    <div class="legend">
      <span><i class="fill full" />все метрики</span>
      <span><i class="fill partial" />частично</span>
      <span><i class="fill empty" />не заполнены</span>
    </div>
  </div>
</template>

<style scoped>
.picker { padding: 12px 16px; display: flex; flex-direction: column; gap: 8px; }
.year { display: flex; align-items: center; gap: 14px; }
.year-label { width: 40px; flex: 0 0 auto; font-size: var(--fs-sm); font-weight: 620; color: var(--text-2); }
.cells { flex: 1; display: grid; grid-template-columns: repeat(12, minmax(52px, 1fr)); gap: 6px; }
.cell { display: inline-flex; align-items: center; justify-content: center; gap: 6px; height: 30px; padding: 0 8px; border-radius: var(--radius-sm); border: 1px solid var(--border); background: var(--surface); color: var(--text-2); font-size: var(--fs-sm); font-weight: 540; cursor: pointer; white-space: nowrap; transition: all var(--t-fast); }
.cell:hover { border-color: var(--border-strong); color: var(--text); }
.cell.active { background: var(--text); border-color: var(--text); color: var(--bg-elevated); }
.cell.ghost { border-style: dashed; background: transparent; color: var(--faint); font-weight: 450; }
span.cell.ghost { cursor: default; }
button.cell.ghost:hover { color: var(--text-2); border-color: var(--border-strong); background: var(--surface-2); }
.fill { display: inline-block; width: 7px; height: 7px; border-radius: 50%; flex: 0 0 7px; }
.fill.full { background: var(--light-green); }
.fill.partial { background: var(--light-yellow); }
.fill.empty { background: transparent; box-shadow: inset 0 0 0 1.5px var(--faint); }
.cell.active .fill.empty { box-shadow: inset 0 0 0 1.5px var(--bg-elevated); }
.legend { display: flex; flex-wrap: wrap; gap: 4px 16px; padding-left: 54px; font-size: var(--fs-xs); color: var(--muted); }
.legend span { display: inline-flex; align-items: center; gap: 6px; }
@media (max-width: 960px) {
  .year { align-items: flex-start; }
  .year-label { padding-top: 6px; }
  .cells { grid-template-columns: repeat(6, minmax(0, 1fr)); }
  .legend { padding-left: 0; }
}
</style>
