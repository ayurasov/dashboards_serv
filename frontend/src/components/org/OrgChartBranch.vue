<script setup>
import { computed, onMounted, onUpdated, ref } from 'vue'
import { isStackable } from '@/domain/org'

/**
 * Ветка оргсхемы (рекурсивно): карточка узла через слот и, если ветка раскрыта, дочерние узлы.
 * Линии подчинения рисует CSS (OrgChart.vue). Участок пути к выбранному узлу на общей линии
 * соседей дорисовывается отдельным отрезком: его концы измеряются после раскладки.
 */
defineOptions({ name: 'OrgChartBranch' })
const props = defineProps({
  node: { type: Object, required: true },
  expanded: { type: Object, required: true },
  path: { type: Object, required: true },
  stack: { type: Boolean, default: false },
  orientation: { type: String, default: 'vertical' },
})

const open = computed(() => props.node.children.length > 0 && props.expanded.has(props.node.id))
const stacked = computed(() => props.stack && props.orientation === 'vertical' && isStackable(props.node))
const onPath = computed(() => props.path.has(props.node.id))
const pathChild = computed(() => (onPath.value && open.value ? props.node.children.findIndex((c) => props.path.has(c.id)) : -1))

const level = ref(null)
const bar = ref(null)
let last = ''

function measure() {
  const ul = level.value
  const li = pathChild.value >= 0 && ul ? ul.querySelectorAll(':scope > li')[pathChild.value] : null
  const slot = li?.firstElementChild
  let style = null
  if (slot) {
    if (props.orientation === 'horizontal') {
      const mid = ul.offsetHeight / 2
      const y = li.offsetTop + slot.offsetTop + slot.offsetHeight / 2
      style = { top: `${Math.min(mid, y)}px`, height: `${Math.abs(y - mid)}px` }
    } else if (stacked.value) {
      style = { top: '0px', height: `${li.offsetTop + slot.offsetTop + slot.offsetHeight / 2}px` }
    } else {
      const mid = ul.offsetWidth / 2
      const x = li.offsetLeft + slot.offsetLeft + slot.offsetWidth / 2
      style = { left: `${Math.min(mid, x)}px`, width: `${Math.abs(x - mid)}px` }
    }
  }
  const key = JSON.stringify(style)
  if (key !== last) {
    last = key
    bar.value = style
  }
}
onMounted(measure)
onUpdated(measure)
</script>

<template>
  <li class="oc-node" :class="{ 'oc-node--path': onPath }">
    <div class="oc-slot" :data-node-id="node.id">
      <slot :node="node" :expanded="open" :on-path="onPath" />
    </div>
    <ul v-if="open" ref="level" class="oc-level" :class="{ 'oc-level--path': pathChild >= 0, 'oc-level--stack': stacked }">
      <OrgChartBranch v-for="child in node.children" :key="child.id" :node="child" :expanded="expanded" :path="path"
                      :stack="stack" :orientation="orientation">
        <template #default="slotProps"><slot v-bind="slotProps" /></template>
      </OrgChartBranch>
      <i v-if="bar" class="oc-bar" :style="bar" aria-hidden="true" />
    </ul>
  </li>
</template>
