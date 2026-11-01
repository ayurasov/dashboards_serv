<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import StatusChip from './StatusChip.vue'
import { DATA_CLASS_SHORT, cellTooltip, cellView } from '@/domain/reports'

/**
 * Матрица «подразделения × показатели»: строки — дерево подразделений с отступом и раскрытием,
 * столбцы — видимые показатели. Ячейка — цвет статуса, значение и стрелка изменения к прошлому
 * месяцу; подсказка — значение, цель, отклонение, источник, комментарий. Шапка и первый столбец
 * закреплены, горизонтальная прокрутка — внутри карточки. Щелчок по строке открывает подразделение.
 */
const props = defineProps({
  rows: { type: Array, required: true },
  columns: { type: Array, required: true },
  selectedId: { type: Number, default: null },
  filtered: { type: Boolean, default: false },
})
const emit = defineEmits(['select', 'toggle'])

const views = computed(() => props.rows.map((row) => ({
  row,
  cells: props.columns.map((ind) => ({ ind, cell: row.unit.cells?.[ind.key], view: cellView(row.unit.cells?.[ind.key], ind) })),
})))

function onRowKey(event, row) {
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    emit('select', row.id)
  } else if (row.hasChildren && !row.forced && ((event.key === 'ArrowRight' && !row.open) || (event.key === 'ArrowLeft' && row.open))) {
    event.preventDefault()
    emit('toggle', row.id)
  }
}

// ---------------------------------------------------------------- подсказка ячейки
const tip = ref(null)
const TIP_W = 320
function showTip(event, row, item) {
  const rect = event.currentTarget.getBoundingClientRect()
  const above = rect.top > 260
  const half = TIP_W / 2 + 8
  const left = Math.min(window.innerWidth - half, Math.max(half, rect.left + rect.width / 2))
  tip.value = { left, top: above ? rect.top - 8 : rect.bottom + 8, above, data: cellTooltip(item.cell, item.ind, row.unit.name) }
}
function hideTip() { tip.value = null }
onBeforeUnmount(hideTip)
</script>

<template>
  <div class="mx-scroll scroll-thin" data-testid="report-matrix" @scroll.passive="hideTip">
    <table class="mx" :style="{ '--cols': columns.length }">
      <thead>
        <tr>
          <th class="corner" scope="col">
            <span>Подразделение</span>
            <small>{{ rows.length }} в таблице</small>
          </th>
          <th class="corner-status" scope="col"><span>Статус</span></th>
          <th v-for="ind in columns" :key="ind.key" scope="col" class="ind" :title="[ind.name, ind.description].filter(Boolean).join(' — ')" :data-indicator="ind.key">
            <span class="i-name">{{ ind.name }}</span>
            <span class="i-meta">
              <span class="cls" :class="`c-${ind.data_class}`" :title="ind.data_class_label">{{ DATA_CLASS_SHORT[ind.data_class] || ind.data_class_label }}</span>
              <span v-if="ind.unit" class="i-unit">{{ ind.unit }}</span>
            </span>
          </th>
          <th class="filler" aria-hidden="true" />
        </tr>
      </thead>
      <tbody>
        <tr v-for="{ row, cells } in views" :key="row.id" class="mx-row" :class="{ selected: row.id === selectedId, context: !row.match, top: row.depth === 0 }"
            tabindex="0" :aria-label="`${row.unit.name}: ${row.unit.status_label}`" :data-unit="row.id" :aria-expanded="row.hasChildren ? row.open : undefined"
            @click="emit('select', row.id)" @keydown="onRowKey($event, row)">
          <th scope="row" class="unit-cell" :style="{ '--indent': row.depth }">
            <div class="u-inner">
              <button v-if="row.hasChildren && !row.forced" type="button" class="tw" :class="{ open: row.open }" tabindex="-1"
                      :aria-label="row.open ? 'Свернуть' : 'Развернуть'" @click.stop="emit('toggle', row.id)">
                <AppIcon name="chevron-right" :size="14" :stroke="2.2" />
              </button>
              <span v-else class="tw-space" :class="{ leaf: !row.hasChildren }" aria-hidden="true" />
              <span class="u-text">
                <span class="u-name" :title="row.unit.path">{{ row.unit.name }}</span>
                <span class="u-meta">
                  <span>{{ row.unit.kind_label }}</span>
                  <span v-if="row.unit.drill_locked" class="u-lock" title="Вложенные подразделения входят в свёртку, но вам не видны" data-testid="drill-lock">
                    <AppIcon name="lock" :size="11" :stroke="2.2" />детализация недоступна
                  </span>
                </span>
              </span>
              <span v-if="row.unit.note" class="u-note" :title="`${row.unit.note.status_label}: ${row.unit.note.comment}`" data-testid="note-mark">
                <AppIcon name="eye" :size="14" />
              </span>
            </div>
          </th>
          <td class="status-cell">
            <div class="s-inner">
              <StatusChip :status="row.unit.status" :label="row.unit.status_label" size="sm" />
              <span v-if="row.unit.missing_total" class="u-miss" :title="`Не заполнено показателей в ветке: ${row.unit.missing_total} — критичное нарушение полноты`">
                <AppIcon name="alert" :size="10" :stroke="2.4" />не заполнено: {{ row.unit.missing_total }}
              </span>
            </div>
          </td>
          <td v-for="item in cells" :key="item.ind.key" class="mx-cell" :data-key="item.ind.key"
              :aria-label="`${item.ind.name}: ${item.view.label}`"
              @mouseenter="showTip($event, row, item)" @mouseleave="hideTip">
            <div class="c" :class="`t-${item.view.tone}`">
              <template v-if="item.view.tone === 'missing'">
                <AppIcon name="alert" :size="12" :stroke="2.3" /><span class="c-miss">Нет данных</span>
              </template>
              <template v-else>
                <i v-if="item.view.tone !== 'none' && item.view.tone !== 'gray'" class="c-dot" aria-hidden="true" />
                <span class="c-val num">{{ item.view.text }}</span>
                <span v-if="item.view.arrow" class="c-arrow" :class="`delta-${item.view.trend}`" aria-hidden="true">
                  <AppIcon :name="item.view.arrow === 'up' ? 'arrow-up' : 'arrow-down'" :size="11" :stroke="2.6" />
                </span>
              </template>
              <AppIcon v-if="item.cell?.comment" class="c-comment" name="note" :size="10" :stroke="2.2" />
            </div>
          </td>
          <td class="filler" aria-hidden="true" />
        </tr>
      </tbody>
    </table>
  </div>

  <Teleport to="body">
    <div v-if="tip" class="mx-tip" :class="[{ above: tip.above }, `t-${tip.data.tone}`]" :style="{ left: `${tip.left}px`, top: `${tip.top}px`, width: `${TIP_W}px` }" role="tooltip">
      <header>
        <strong>{{ tip.data.title }}</strong>
        <span class="t-unit">{{ tip.data.subtitle }}</span>
      </header>
      <p class="t-status"><i />{{ tip.data.status }}</p>
      <dl v-if="tip.data.rows.length">
        <div v-for="r in tip.data.rows" :key="r.label"><dt>{{ r.label }}</dt><dd :class="r.trend ? `delta-${r.trend}` : ''">{{ r.value }}</dd></div>
      </dl>
      <p v-if="tip.data.note" class="t-note">{{ tip.data.note }}</p>
      <p v-if="tip.data.comment" class="t-comment"><AppIcon name="note" :size="12" />{{ tip.data.comment }}</p>
    </div>
  </Teleport>
</template>

<style scoped>
.mx-scroll {
  --first: 292px; --status: 120px; --col: 116px;
  position: relative; overflow: auto; max-height: max(420px, calc(100dvh - var(--topbar-h) - 150px));
  border-radius: 0 0 var(--radius-lg) var(--radius-lg); overscroll-behavior-x: contain;
}
.mx { border-collapse: separate; border-spacing: 0; width: 100%; table-layout: fixed; font-size: var(--fs-sm); }
.filler { width: auto; min-width: 0; }
.mx tbody th, .mx tbody td { padding: 0; }

/* ---- шапка ---- */
.mx thead th {
  position: sticky; top: 0; z-index: 2; height: 62px; padding: 8px 8px 7px 10px; vertical-align: bottom; text-align: left;
  background: var(--surface-2); border-bottom: 1px solid var(--border); font-weight: 600;
}
.mx thead .corner { left: 0; z-index: 4; width: var(--first); min-width: var(--first); padding-left: 16px; }
.mx thead .corner-status { left: var(--first); z-index: 4; padding-left: 6px; width: var(--status); min-width: var(--status); border-right: 1px solid var(--border-strong); }
.corner span, .corner-status span { display: block; font-size: var(--fs-xs); font-weight: 650; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); }
.corner small { font-size: var(--fs-xs); color: var(--faint); font-weight: 500; }
.ind { width: var(--col); min-width: var(--col); max-width: var(--col); }
.i-name { display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; font-size: var(--fs-xs); font-weight: 620; line-height: 1.3; color: var(--text); hyphens: auto; overflow-wrap: break-word; }
.i-meta { display: flex; align-items: center; gap: 5px; margin-top: 4px; min-width: 0; }
.i-unit { font-size: 10.5px; color: var(--muted); font-weight: 520; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cls { --c: var(--chart-1); flex: 0 0 auto; height: 16px; padding: 0 5px; display: inline-flex; align-items: center; border-radius: 4px; font-size: 9.5px; font-weight: 700; letter-spacing: .02em;
  background: color-mix(in srgb, var(--c) 13%, transparent); color: color-mix(in srgb, var(--c) 78%, var(--text)); }
.c-financial { --c: var(--chart-3); }
.c-personal { --c: var(--chart-2); }

/* ---- строки ---- */
.mx-row { cursor: pointer; outline: none; }
.mx-row > * { border-bottom: 1px solid var(--border); background: var(--surface); transition: background var(--t-fast); }
.mx-row:last-child > * { border-bottom: 0; }
.mx-row:hover > * { background: var(--row-hover); }
.mx-row:focus-visible .unit-cell { box-shadow: inset 3px 0 0 var(--accent), inset 0 2px 0 var(--focus), inset 0 -2px 0 var(--focus); }
.mx-row.selected > * { background: color-mix(in srgb, var(--accent) 6%, var(--surface)); }
.mx-row.selected .unit-cell { box-shadow: inset 3px 0 0 var(--accent); }
.mx-row.context .unit-cell .u-inner, .mx-row.context .s-inner, .mx-row.context .mx-cell .c { opacity: .5; }

.unit-cell { position: sticky; left: 0; z-index: 1; width: var(--first); min-width: var(--first); max-width: var(--first); text-align: left; font-weight: 400; }
.status-cell { position: sticky; left: var(--first); z-index: 1; width: var(--status); min-width: var(--status); max-width: var(--status); border-right: 1px solid var(--border-strong); }
.s-inner { display: flex; flex-direction: column; align-items: flex-start; justify-content: center; gap: 3px; height: 52px; padding: 0 10px 0 4px; }
.u-inner { display: flex; align-items: center; gap: 6px; height: 52px; padding: 0 10px 0 calc(8px + var(--indent) * 16px); }
.tw, .tw-space { width: 22px; height: 22px; flex: 0 0 22px; }
.tw { display: grid; place-items: center; padding: 0; border: 0; border-radius: 6px; background: transparent; color: var(--muted); cursor: pointer; transition: transform var(--t-fast), background var(--t-fast); }
.tw:hover { background: var(--surface-3); color: var(--text); }
.tw.open :deep(svg) { transform: rotate(90deg); }
.tw :deep(svg) { transition: transform var(--t-fast); }
.tw-space.leaf { position: relative; }
.tw-space.leaf::after { content: ''; position: absolute; left: 10px; top: 10px; width: 3px; height: 3px; border-radius: 50%; background: var(--border-strong); }
.u-text { flex: 1; min-width: 0; display: flex; flex-direction: column; line-height: 1.25; }
.u-name { font-size: var(--fs-sm); font-weight: 600; color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.top .u-name { font-size: var(--fs-base); font-weight: 680; }
.u-meta { display: flex; align-items: center; gap: 6px; min-width: 0; margin-top: 2px; font-size: 10.5px; color: var(--muted); white-space: nowrap; overflow: hidden; }
.u-lock { display: inline-flex; align-items: center; gap: 3px; color: var(--text-2); font-weight: 600; }
.u-note { width: 24px; height: 24px; flex: 0 0 24px; display: grid; place-items: center; border-radius: 50%; background: color-mix(in srgb, var(--accent) 12%, transparent); color: var(--accent); }
.u-miss { display: inline-flex; align-items: center; gap: 3px; padding-left: 2px; color: var(--light-red); font-size: 10px; font-weight: 680; white-space: nowrap; }

/* ---- ячейки ---- */
.mx-cell { width: var(--col); min-width: var(--col); max-width: var(--col); padding: 3px 2px !important; }
.c {
  --tone: transparent; position: relative; display: flex; align-items: center; justify-content: center; gap: 4px; height: 44px; padding: 0 6px;
  border-radius: 8px; background: color-mix(in srgb, var(--tone) 13%, var(--surface)); color: var(--text); white-space: nowrap; transition: opacity var(--t-fast);
}
.c.t-green { --tone: var(--light-green); }
.c.t-yellow { --tone: var(--light-yellow); background: color-mix(in srgb, var(--tone) 17%, var(--surface)); }
.c.t-red { --tone: var(--light-red); background: color-mix(in srgb, var(--tone) 15%, var(--surface)); }
.c.t-red .c-val { font-weight: 720; }
.c.t-gray { background: var(--surface-2); color: var(--text-2); }
.c.t-none { background: transparent; color: var(--faint); }
.c.t-missing {
  gap: 4px; color: var(--light-red); font-size: 10.5px; font-weight: 700;
  background: repeating-linear-gradient(135deg, color-mix(in srgb, var(--light-red) 12%, var(--surface)) 0 5px, var(--surface) 5px 10px);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--light-red) 50%, transparent);
}
.c-dot { width: 6px; height: 6px; flex: 0 0 6px; border-radius: 50%; background: var(--tone); }
.c-val { font-size: var(--fs-sm); font-weight: 600; letter-spacing: -0.01em; }
.c-arrow { display: inline-flex; }
.c-comment { position: absolute; top: 4px; right: 4px; color: var(--muted); opacity: .8; }
.mx-row:hover .c:not(.t-none) { box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--tone) 40%, transparent); }

.mx-row:hover .c.t-missing { box-shadow: inset 0 0 0 1.5px var(--light-red); }

@media (max-width: 640px) {
  .mx-scroll { --first: 168px; --status: 30px; --col: 96px; max-height: 70dvh; }
  .u-inner { padding-left: calc(4px + var(--indent) * 8px); gap: 4px; }
  .u-meta, .u-note { display: none; }
  .unit-cell .u-name { white-space: normal; display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; }
  .corner-status span { display: none; }
  .s-inner { padding: 0; align-items: center; }
  .s-inner :deep(.status-chip) { width: 18px; padding: 0; justify-content: center; font-size: 0; gap: 0; }
  .u-miss { display: none; }
}
</style>

<style>
/* Подсказка ячейки — в body (вне прокрутки матрицы) */
.mx-tip {
  --tone: var(--light-gray);
  position: fixed; z-index: 120; transform: translate(-50%, 0); pointer-events: none; padding: 12px 14px 12px;
  border-radius: 12px; border: 1px solid var(--border); background: var(--bg-elevated); color: var(--text); box-shadow: var(--shadow-lg);
  font-size: var(--fs-sm); line-height: 1.4; animation: mx-tip-in .1s ease;
}
.mx-tip.above { transform: translate(-50%, -100%); }
.mx-tip.t-green { --tone: var(--light-green); }
.mx-tip.t-yellow { --tone: var(--light-yellow); }
.mx-tip.t-red, .mx-tip.t-missing { --tone: var(--light-red); }
.mx-tip header { display: flex; flex-direction: column; }
.mx-tip header strong { font-size: var(--fs-base); font-weight: 650; }
.mx-tip .t-unit { font-size: var(--fs-xs); color: var(--muted); }
.mx-tip .t-status { display: inline-flex; align-items: center; gap: 6px; margin-top: 8px; font-size: var(--fs-xs); font-weight: 680; color: color-mix(in srgb, var(--tone) 75%, var(--text)); }
.mx-tip .t-status i { width: 8px; height: 8px; border-radius: 50%; background: var(--tone); }
.mx-tip.t-missing .t-status i { background: transparent; box-shadow: inset 0 0 0 1.6px var(--light-red); }
.mx-tip dl { margin: 8px 0 0; display: flex; flex-direction: column; gap: 3px; }
.mx-tip dl div { display: grid; grid-template-columns: 128px minmax(0, 1fr); gap: 8px; }
.mx-tip dt { color: var(--muted); font-size: var(--fs-xs); padding-top: 1px; }
.mx-tip dd { margin: 0; font-weight: 560; font-variant-numeric: tabular-nums; }
.mx-tip .t-note { margin-top: 8px; font-size: var(--fs-xs); color: var(--light-red); font-weight: 560; }
.mx-tip .t-comment { display: flex; gap: 6px; margin-top: 8px; padding-top: 8px; border-top: 1px dashed var(--border); font-size: var(--fs-xs); color: var(--text-2); }
.mx-tip .t-comment svg { margin-top: 2px; flex: 0 0 auto; color: var(--muted); }
@keyframes mx-tip-in { from { opacity: 0; } }
</style>
