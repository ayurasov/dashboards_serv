<script setup>
import AppIcon from '@/components/ui/AppIcon.vue'
import StatusChip from './StatusChip.vue'
import { reasonParts, reasonText } from '@/domain/reports'

/**
 * «Список» (для телефона): подразделения карточками в порядке структуры — статус и главные
 * проблемы (до трёх причин), пропуски, «детализация недоступна», заметка. Щелчок открывает панель.
 */
defineProps({
  rows: { type: Array, required: true },
  selectedId: { type: Number, default: null },
})
const emit = defineEmits(['select'])
</script>

<template>
  <ul class="r-list" data-testid="report-list">
    <li v-for="row in rows" :key="row.id" :style="{ '--indent': Math.min(row.depth, 3) }" :class="{ context: !row.match }">
      <article class="rl" :class="[`s-${row.unit.status}`, { selected: row.id === selectedId }]" tabindex="0" role="button" :data-unit="row.id"
               :aria-label="`${row.unit.name}: ${row.unit.status_label}`"
               @click="emit('select', row.id)" @keydown.enter.self.prevent="emit('select', row.id)" @keydown.space.self.prevent="emit('select', row.id)">
        <header class="rl-head">
          <div class="rl-titles">
            <h3>{{ row.unit.name }}</h3>
            <p>{{ row.unit.kind_label }}<template v-if="row.depth"> · {{ row.unit.path.split(' / ').slice(-2, -1)[0] }}</template></p>
          </div>
          <StatusChip :status="row.unit.status" :label="row.unit.status_label" />
        </header>
        <ul v-if="row.unit.explanation?.items?.length" class="rl-problems">
          <li v-for="(item, i) in row.unit.explanation.items" :key="i" :class="`t-${item.status}`">
            <i aria-hidden="true" /><span><b v-if="reasonParts(item).lead">{{ reasonParts(item).lead }}</b>{{ reasonParts(item).rest }}</span>
          </li>
        </ul>
        <p v-else class="rl-ok">{{ reasonText(row.unit.explanation?.text) || 'Нет оценённых показателей' }}</p>
        <footer v-if="row.unit.missing_total || row.unit.drill_locked || row.unit.note" class="rl-flags">
          <span v-if="row.unit.missing_total" class="flag miss"><AppIcon name="alert" :size="12" :stroke="2.3" />Не заполнено: {{ row.unit.missing_total }}</span>
          <span v-if="row.unit.drill_locked" class="flag lock"><AppIcon name="lock" :size="12" />детализация недоступна</span>
          <span v-if="row.unit.note" class="flag note" :title="row.unit.note.comment"><AppIcon name="eye" :size="12" />{{ row.unit.note.status_label }}</span>
        </footer>
      </article>
    </li>
  </ul>
</template>

<style scoped>
.r-list { display: flex; flex-direction: column; gap: 10px; margin: 0; padding: 0; list-style: none; }
.r-list > li { padding-left: calc(var(--indent) * 14px); }
.r-list > li.context { opacity: .55; }
.rl {
  --tone: var(--light-gray);
  position: relative; display: flex; flex-direction: column; gap: 10px; padding: 14px 14px 14px 18px; cursor: pointer; overflow: hidden;
  background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); box-shadow: var(--shadow-sm);
  transition: border-color var(--t-fast), box-shadow var(--t-fast);
}
.rl::before { content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 4px; background: var(--tone); }
.s-green { --tone: var(--light-green); }
.s-yellow { --tone: var(--light-yellow); }
.s-red { --tone: var(--light-red); }
.rl:hover { border-color: var(--border-strong); box-shadow: var(--shadow); }
.rl:focus-visible { outline: none; box-shadow: 0 0 0 3px var(--focus); }
.rl.selected { border-color: var(--accent); }
.rl-head { display: flex; align-items: flex-start; gap: 10px; }
.rl-titles { flex: 1; min-width: 0; }
.rl-titles h3 { font-size: var(--fs-md); font-weight: 650; line-height: 1.3; overflow-wrap: anywhere; }
.rl-titles p { margin-top: 2px; font-size: var(--fs-xs); color: var(--muted); }
.rl-problems { display: flex; flex-direction: column; gap: 6px; margin: 0; padding: 0; list-style: none; }
.rl-problems li { --t: var(--light-gray); display: flex; gap: 8px; font-size: var(--fs-sm); line-height: 1.4; color: var(--text-2); }
.rl-problems li.t-red { --t: var(--light-red); }
.rl-problems li.t-yellow { --t: var(--light-yellow); }
.rl-problems i { width: 7px; height: 7px; flex: 0 0 7px; margin-top: 6px; border-radius: 50%; background: var(--t); }
.rl-problems b { color: var(--text); font-weight: 630; }
.rl-ok { font-size: var(--fs-sm); color: var(--muted); }
.rl-flags { display: flex; flex-wrap: wrap; gap: 6px; }
.flag { display: inline-flex; align-items: center; gap: 4px; height: 22px; padding: 0 8px; border-radius: var(--radius-pill); font-size: var(--fs-xs); font-weight: 620; }
.flag.miss { background: color-mix(in srgb, var(--light-red) 12%, transparent); color: var(--light-red); }
.flag.lock { background: var(--surface-3); color: var(--text-2); }
.flag.note { background: color-mix(in srgb, var(--accent) 12%, transparent); color: var(--accent); }
</style>
