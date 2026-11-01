<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'
import OrgChart from '@/components/org/OrgChart.vue'
import OrgIcon from '@/components/org/OrgIcon.vue'
import ReportUnitCard from './ReportUnitCard.vue'
import { ZOOM } from '@/domain/org'
import { treeDepth } from '@/domain/reports'

/**
 * Оргсхема статусов: видимые подразделения отчёта карточками структуры, окрашенными статусом.
 * Холст и линии — общие с «Структурой компании» (OrgChart); масштаб и «Вписать».
 */
const props = defineProps({
  forest: { type: Array, required: true },
  expanded: { type: Object, required: true },
  selectedId: { type: Number, default: null },
  path: { type: Object, default: () => new Set() },
  // Фильтр отчёта: неподходящие карточки приглушены (схема не перестраивается)
  dimmed: { type: Object, default: () => new Set() },
})
const emit = defineEmits(['select', 'toggle', 'expand-all', 'collapse'])
const zoom = ref(1)
const canvas = ref(null)
const percent = computed(() => `${Math.round(zoom.value * 100)} %`)
// Неглубокое дерево (вершина и уровень под ней) — в ряд; глубже — нижние уровни столбиком, чтобы схема не росла вширь
const stack = computed(() => treeDepth(props.forest) > 2)
// Сначала — вся видимая схема, если она читается (не мельче 80 %); иначе 80 % и вершина по центру
const MIN_FIT = 0.8
onMounted(async () => {
  await nextTick()
  requestAnimationFrame(async () => {
    await canvas.value?.fit()
    if (zoom.value >= MIN_FIT) return
    zoom.value = MIN_FIT
    await nextTick()
    const top = props.forest[0]?.id
    if (top !== undefined) canvas.value?.focus(top, { smooth: false })
  })
})
defineExpose({ focus: (id) => canvas.value?.focus(id, { flash: true, ifHidden: true }) })
</script>

<template>
  <section class="card chart-card" data-testid="report-chart">
    <div class="c-tools" role="toolbar" aria-label="Схема">
      <button type="button" class="btn btn-ghost btn-sm" @click="emit('expand-all')"><OrgIcon name="expand-all" :size="14" /><span class="lbl">Развернуть всё</span></button>
      <button type="button" class="btn btn-ghost btn-sm" @click="emit('collapse')"><OrgIcon name="collapse-all" :size="14" /><span class="lbl">Свернуть</span></button>
      <span class="spacer" />
      <button type="button" class="icon-tool" aria-label="Уменьшить" :disabled="zoom <= ZOOM.min" @click="canvas?.zoomBy(-ZOOM.step)"><OrgIcon name="zoom-out" :size="17" /></button>
      <button type="button" class="zoom-value num" title="Масштаб 100 %" @click="canvas?.zoomTo(1)">{{ percent }}</button>
      <button type="button" class="icon-tool" aria-label="Увеличить" :disabled="zoom >= ZOOM.max" @click="canvas?.zoomBy(ZOOM.step)"><OrgIcon name="zoom-in" :size="17" /></button>
      <button type="button" class="btn btn-ghost btn-sm" @click="canvas?.fit()"><OrgIcon name="fit" :size="14" /><span class="lbl">Вписать</span></button>
    </div>
    <OrgChart ref="canvas" v-model:zoom="zoom" class="r-canvas" label="Оргсхема статусов" :forest="forest" :expanded="expanded" :path="path" orientation="vertical" :stack-leaves="stack">
      <template #default="{ node, expanded: open, onPath }">
        <ReportUnitCard :unit="node.item" :child-count="node.children.length" :expanded="open" :on-path="onPath" :selected="node.id === selectedId" :class="{ dim: dimmed.has(node.id) }"
                        @select="(id) => emit('select', id)" @toggle="(id) => emit('toggle', id)" />
      </template>
    </OrgChart>
  </section>
</template>

<style scoped>
.chart-card { display: flex; flex-direction: column; height: max(520px, calc(100dvh - var(--topbar-h) - 120px)); padding: 10px; gap: 8px; }
.c-tools { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; }
.c-tools .btn-ghost { color: var(--text-2); gap: 6px; padding: 0 9px; }
.icon-tool { width: 32px; height: 32px; display: grid; place-items: center; border: 0; border-radius: 8px; background: transparent; color: var(--text-2); cursor: pointer; }
.icon-tool:hover:not(:disabled) { background: var(--surface-3); color: var(--text); }
.icon-tool:disabled { opacity: .4; cursor: not-allowed; }
.zoom-value { min-width: 50px; height: 30px; border: 0; border-radius: 8px; background: transparent; color: var(--text-2); font-size: var(--fs-sm); cursor: pointer; }
.zoom-value:hover { background: var(--surface-3); }
.r-canvas { flex: 1; min-height: 0; }
.dim { opacity: .38; filter: saturate(.4); }
.dim:hover, .dim:focus-visible { opacity: 1; filter: none; }
.r-canvas :deep(.oc-viewport) { border-radius: 10px; }
@media (max-width: 640px) {
  .chart-card { height: 72dvh; padding: 8px; }
  .lbl { display: none; }
}
</style>
