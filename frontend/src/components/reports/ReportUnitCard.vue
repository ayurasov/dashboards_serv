<script setup>
import { computed } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import StatusChip from './StatusChip.vue'
import { UNIT_FORMS, cellCounts, count } from '@/domain/reports'

/**
 * Карточка оргсхемы статусов: подразделение, окрашенное статусом; сколько своих показателей
 * критично и требует внимания, пропуски данных, «детализация недоступна», заметка «под контролем».
 */
const props = defineProps({
  unit: { type: Object, required: true },
  childCount: { type: Number, default: 0 },
  expanded: { type: Boolean, default: false },
  selected: { type: Boolean, default: false },
  onPath: { type: Boolean, default: false },
})
const emit = defineEmits(['select', 'toggle'])
const counts = computed(() => cellCounts(props.unit))
const rated = computed(() => counts.value.red + counts.value.yellow + counts.value.green)
</script>

<template>
  <article class="ruc" :class="[`s-${unit.status}`, { selected, path: onPath }]" tabindex="0" role="button" :aria-pressed="selected"
           :aria-label="`${unit.kind_label} «${unit.name}»: ${unit.status_label}`" :data-unit-id="unit.id"
           @click="emit('select', unit.id)" @keydown.enter.self.prevent="emit('select', unit.id)" @keydown.space.self.prevent="emit('select', unit.id)">
    <header class="r-head">
      <span class="r-kind">{{ unit.kind_label }}</span>
      <StatusChip :status="unit.status" :label="unit.status_label" size="sm" />
    </header>
    <h3 :title="unit.path">{{ unit.name }}</h3>

    <div class="r-counts">
      <span v-if="counts.red" class="cnt red" :title="`Критично: ${counts.red}`"><i />{{ counts.red }} крит.</span>
      <span v-if="counts.yellow" class="cnt yellow" :title="`Внимание: ${counts.yellow}`"><i />{{ counts.yellow }} вним.</span>
      <span v-if="counts.green" class="cnt green" :title="`Норма: ${counts.green}`"><i />{{ counts.green }} норма</span>
      <span v-if="!rated && !counts.missing" class="cnt none">Нет оценённых показателей</span>
    </div>

    <div v-if="unit.missing_total || unit.drill_locked || unit.note" class="r-flags">
      <span v-if="unit.missing_total" class="flag miss" :title="unit.missing.map((m) => m.name).join(', ') || 'Пропуски во вложенных подразделениях'">
        <AppIcon name="alert" :size="12" :stroke="2.3" />Не заполнено: {{ unit.missing_total }}
      </span>
      <span v-if="unit.drill_locked" class="flag lock" title="Вложенные подразделения входят в свёртку, но вам не видны"><AppIcon name="lock" :size="12" />детализация недоступна</span>
      <span v-if="unit.note" class="flag note" :title="unit.note.comment"><AppIcon name="eye" :size="12" />{{ unit.note.status_label }}</span>
    </div>

    <button v-if="childCount" type="button" class="r-toggle" :aria-expanded="expanded"
            :aria-label="`${expanded ? 'Свернуть' : 'Показать'} ${count(childCount, UNIT_FORMS)}`" @click.stop="emit('toggle', unit.id)">
      {{ count(childCount, UNIT_FORMS) }}<i class="chev" aria-hidden="true" />
    </button>
  </article>
</template>

<style scoped>
.ruc {
  --tone: var(--light-gray);
  position: relative; width: 236px; display: flex; flex-direction: column; text-align: left; cursor: pointer; overflow: hidden;
  background: color-mix(in srgb, var(--tone) 6%, var(--surface)); border: 1px solid color-mix(in srgb, var(--tone) 32%, var(--border));
  border-radius: 14px; box-shadow: var(--shadow-sm); transition: border-color var(--t-fast), box-shadow var(--t-fast);
}
.s-green { --tone: var(--light-green); }
.s-yellow { --tone: var(--light-yellow); }
.s-red { --tone: var(--light-red); }
.ruc::before { content: ''; position: absolute; left: 0; right: 0; top: 0; height: 4px; background: var(--tone); }
.ruc:hover { box-shadow: var(--shadow); border-color: color-mix(in srgb, var(--tone) 60%, var(--border)); }
.ruc:focus-visible { outline: none; box-shadow: 0 0 0 3px var(--focus); }
.ruc.selected { border-color: var(--accent); box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 22%, transparent), var(--shadow); }
.r-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 14px 12px 0 14px; }
.r-kind { font-size: var(--fs-xs); font-weight: 600; color: var(--muted); }
h3 { margin: 4px 14px 0; font-size: 14px; font-weight: 650; line-height: 1.3; display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; overflow-wrap: anywhere; }
.r-counts { display: flex; flex-wrap: wrap; gap: 4px 10px; padding: 10px 14px 0; font-size: var(--fs-xs); color: var(--text-2); }
.cnt { display: inline-flex; align-items: center; gap: 5px; font-weight: 620; font-variant-numeric: tabular-nums; }
.cnt i { width: 7px; height: 7px; border-radius: 50%; }
.cnt.red i { background: var(--light-red); }
.cnt.yellow i { background: var(--light-yellow); }
.cnt.green i { background: var(--light-green); }
.cnt.none { color: var(--muted); font-weight: 500; }
.r-flags { display: flex; flex-wrap: wrap; gap: 5px; padding: 10px 12px 0 14px; }
.flag { display: inline-flex; align-items: center; gap: 4px; height: 20px; padding: 0 7px; border-radius: var(--radius-pill); font-size: 10.5px; font-weight: 640; white-space: nowrap; }
.flag.miss { background: color-mix(in srgb, var(--light-red) 12%, transparent); color: var(--light-red); }
.flag.lock { background: var(--surface-3); color: var(--text-2); }
.flag.note { background: color-mix(in srgb, var(--accent) 12%, transparent); color: var(--accent); }
.ruc > :last-child:not(.r-toggle) { margin-bottom: 14px; }
.r-toggle {
  display: flex; align-items: center; justify-content: center; gap: 5px; margin-top: 12px; height: 30px; padding: 0 10px;
  border: 0; border-top: 1px solid color-mix(in srgb, var(--tone) 22%, var(--border)); background: color-mix(in srgb, var(--surface-2) 70%, transparent);
  color: var(--text-2); font-size: var(--fs-xs); font-weight: 600; cursor: pointer;
}
.r-toggle:hover { background: var(--surface-3); color: var(--text); }
.r-toggle[aria-expanded='true'] { color: var(--accent); }
.chev { width: 6px; height: 6px; margin: -3px 0 0 3px; border-right: 1.8px solid currentColor; border-bottom: 1.8px solid currentColor; transform: rotate(45deg); transition: transform var(--t-fast); }
.r-toggle[aria-expanded='true'] .chev { margin-top: 3px; transform: rotate(-135deg); }
</style>
