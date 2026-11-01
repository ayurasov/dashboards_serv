<script setup>
import { computed } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import LightBadge from '@/components/ui/LightBadge.vue'
import { DIRECTION_LABELS } from '@/utils/lights'
import { deltaTone, formatDelta, formatNumber } from '@/utils/format'
import { bulletScale, statusLabel } from '@/domain/hrTargets'

/** Карточка цели: факт, цель, справочное значение и полоса выполнения с зоной, где цель достигнута. */
const props = defineProps({
  row: { type: Object, required: true },
  editable: { type: Boolean, default: false },
})
const emit = defineEmits(['edit', 'remove'])

const hasTarget = computed(() => props.row.target_value !== null && props.row.target_value !== undefined)
const hasCurrent = computed(() => props.row.current_value !== null && props.row.current_value !== undefined)
const scale = computed(() => bulletScale(props.row))
const pct = (v) => `${(v * 100).toFixed(2)}%`
const fmt = (v) => formatNumber(v, { unit: props.row.unit })

/** Отклонение: от цели, а для справочной строки — от справочного значения. */
const diff = computed(() => {
  if (hasTarget.value) return props.row.diff
  const ref = props.row.reference_value
  if (!hasCurrent.value || ref === null || ref === undefined) return null
  return Math.round((props.row.current_value - ref) * 10000) / 10000
})
const tone = computed(() => deltaTone(diff.value, props.row.direction))
const diffText = computed(() => (diff.value === null ? '' : `${formatDelta(diff.value, props.row.unit)} ${hasTarget.value ? 'к цели' : 'к справочному значению'}`))
</script>

<template>
  <article class="target card" :class="`s-${row.status || 'gray'}`">
    <header class="head">
      <div class="titles">
        <h3 :title="row.metric_label">{{ row.metric_label }}</h3>
        <span class="sub">{{ row.label || row.year }}<template v-if="DIRECTION_LABELS[row.direction]"> · {{ DIRECTION_LABELS[row.direction].toLowerCase() }}</template></span>
      </div>
      <div v-if="editable" class="actions">
        <button class="btn btn-icon btn-sm btn-ghost" type="button" title="Изменить" @click="emit('edit', row)"><AppIcon name="edit" :size="14" /></button>
        <button class="btn btn-icon btn-sm btn-ghost" type="button" title="Удалить" @click="emit('remove', row)"><AppIcon name="trash" :size="14" /></button>
      </div>
    </header>

    <div class="figures">
      <div class="fig main">
        <span class="cap">Факт</span>
        <strong class="num">{{ fmt(row.current_value) }}</strong>
        <span class="muted small">{{ row.current_month || 'нет данных' }}</span>
      </div>
      <div v-if="hasTarget" class="fig">
        <span class="cap">Цель</span>
        <strong class="num">{{ fmt(row.target_value) }}</strong>
      </div>
      <div v-if="row.reference_value !== null && row.reference_value !== undefined" class="fig">
        <span class="cap">Справочно</span>
        <strong class="num ref">{{ fmt(row.reference_value) }}</strong>
      </div>
    </div>

    <div v-if="scale" class="bullet" aria-hidden="true">
      <div class="track">
        <span v-if="scale.zone" class="zone" :style="{ left: pct(scale.zone.from), width: pct(scale.zone.to - scale.zone.from) }" />
        <span v-if="scale.current !== null" class="fill" :style="{ width: pct(scale.current) }" />
        <span v-if="scale.reference !== null" class="tick ref" :style="{ left: pct(scale.reference) }" />
        <span v-if="scale.target !== null" class="tick goal" :style="{ left: pct(scale.target) }" />
      </div>
    </div>

    <div class="status">
      <LightBadge :light="row.status || 'gray'" :label="statusLabel(row)" />
      <span v-if="diffText" class="diff num" :class="`delta-${tone}`">{{ diffText }}</span>
    </div>

    <footer v-if="row.description || row.source" class="foot">
      <p v-if="row.description">{{ row.description }}</p>
      <p v-if="row.source" class="source"><AppIcon name="book" :size="12" />{{ row.source }}</p>
    </footer>
  </article>
</template>

<style scoped>
.target { position: relative; display: flex; flex-direction: column; gap: 14px; padding: 16px 18px; min-width: 0; overflow: hidden; }
.target::before { content: ''; position: absolute; left: 0; top: 16px; width: 3px; height: 28px; border-radius: 0 3px 3px 0; background: var(--light-gray); }
.s-green::before { background: var(--light-green); }
.s-yellow::before { background: var(--light-yellow); }
.s-red::before { background: var(--light-red); }
.head { display: flex; align-items: flex-start; gap: 8px; }
.titles { flex: 1; min-width: 0; }
h3 { font-size: var(--fs-md); font-weight: 620; line-height: 1.3; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.sub { font-size: var(--fs-xs); color: var(--muted); }
.actions { display: flex; gap: 2px; margin: -4px -6px 0 0; opacity: .7; transition: opacity var(--t-fast); }
.target:hover .actions, .actions:focus-within { opacity: 1; }

.figures { display: flex; flex-wrap: wrap; gap: 8px 24px; align-items: flex-start; }
.fig { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
.cap { font-size: var(--fs-xs); color: var(--muted); text-transform: uppercase; letter-spacing: .05em; font-weight: 600; }
.fig strong { font-size: var(--fs-lg); font-weight: 640; letter-spacing: -0.01em; color: var(--text-2); line-height: 1.15; padding-top: 7px; }
.fig.main strong { font-size: var(--fs-kpi); font-weight: 680; letter-spacing: -0.02em; color: var(--text); padding-top: 0; }
.fig strong.ref { color: var(--muted); }
.small { font-size: var(--fs-xs); }

.bullet { padding: 6px 0 2px; }
.track { position: relative; height: 8px; border-radius: var(--radius-pill); background: var(--surface-3); }
.zone { position: absolute; top: 0; bottom: 0; border-radius: var(--radius-pill); background: color-mix(in srgb, var(--light-green) 16%, transparent); }
.fill { position: absolute; left: 0; top: 0; bottom: 0; border-radius: var(--radius-pill); background: var(--light-gray); }
.s-green .fill { background: var(--light-green); }
.s-yellow .fill { background: var(--light-yellow); }
.s-red .fill { background: var(--light-red); }
.tick { position: absolute; top: -5px; bottom: -5px; width: 2px; margin-left: -1px; border-radius: 1px; }
.tick.goal { background: var(--text); }
.tick.ref { background: transparent; border-left: 2px dotted var(--muted); }

.status { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 10px; font-size: var(--fs-sm); }
.diff { font-weight: 600; font-size: var(--fs-sm); }
.foot { display: flex; flex-direction: column; gap: 4px; padding-top: 12px; border-top: 1px solid var(--border); font-size: var(--fs-sm); color: var(--text-2); }
.source { display: flex; align-items: center; gap: 6px; font-size: var(--fs-xs); color: var(--muted); }
</style>
