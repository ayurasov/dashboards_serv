<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import OrgChartBranch from './OrgChartBranch.vue'
import { clampZoom } from '@/domain/org'

/**
 * Холст оргсхемы: лес узлов карточками с линиями подчинения (сверху вниз или слева направо),
 * масштаб 30–160 % (кнопки, Ctrl + колесо — вокруг указателя), перетаскивание холста мышью,
 * «Вписать», прокрутка к узлу с подсветкой. Карточку рисует родитель через слот.
 */
const props = defineProps({
  forest: { type: Array, required: true },
  expanded: { type: Object, required: true },
  path: { type: Object, default: () => new Set() },
  orientation: { type: String, default: 'vertical' },
  stackLeaves: { type: Boolean, default: true },
  zoom: { type: Number, default: 1 },
  label: { type: String, default: 'Схема' },
})
const emit = defineEmits(['update:zoom'])

const viewport = ref(null)
const sizer = ref(null)
const canvas = ref(null)
const size = ref({ width: 0, height: 0 })
const dragging = ref(false)
const PAD = 32

const sizerStyle = computed(() => ({
  width: `${Math.ceil(size.value.width * props.zoom)}px`,
  height: `${Math.ceil(size.value.height * props.zoom)}px`,
}))

let observer = null
function measure() {
  if (canvas.value) size.value = { width: canvas.value.offsetWidth, height: canvas.value.offsetHeight }
}
watch(canvas, (el) => {
  observer?.disconnect()
  if (el && typeof ResizeObserver !== 'undefined') {
    observer = new ResizeObserver(measure)
    observer.observe(el)
  }
  measure()
}, { flush: 'post' })
onBeforeUnmount(() => {
  observer?.disconnect()
  clearTimeout(flashTimer)
})

// ---------------------------------------------------------------- масштаб

/** Новый масштаб; точка под anchor (координаты окна) остаётся на месте. */
async function zoomTo(value, anchor = null) {
  const vp = viewport.value
  const next = clampZoom(value)
  const prev = props.zoom
  if (!vp || !sizer.value || next === prev) return
  const box = vp.getBoundingClientRect()
  const ax = anchor ? anchor.x : box.left + box.width / 2
  const ay = anchor ? anchor.y : box.top + box.height / 2
  const before = sizer.value.getBoundingClientRect()
  const cx = (ax - before.left) / prev
  const cy = (ay - before.top) / prev
  emit('update:zoom', next)
  await nextTick()
  const after = sizer.value.getBoundingClientRect()
  vp.scrollLeft += after.left + cx * next - ax
  vp.scrollTop += after.top + cy * next - ay
}

function zoomBy(step) {
  return zoomTo(Math.round((props.zoom + step) * 10) / 10)
}

function onWheel(event) {
  if (!event.ctrlKey && !event.metaKey) return
  event.preventDefault()
  const delta = Math.max(-100, Math.min(100, event.deltaY))
  zoomTo(props.zoom * Math.exp(-delta * 0.0022), { x: event.clientX, y: event.clientY })
}

/** Вписать схему в окно (не крупнее 100 %) и показать верх по центру. */
async function fit() {
  const vp = viewport.value
  if (!vp || !size.value.width) return
  const scale = Math.min(1, (vp.clientWidth - PAD * 2) / size.value.width, (vp.clientHeight - PAD * 2) / size.value.height)
  emit('update:zoom', clampZoom(scale))
  await nextTick()
  vp.scrollTo({ left: (vp.scrollWidth - vp.clientWidth) / 2, top: 0, behavior: 'smooth' })
}

// ---------------------------------------------------------------- переход к узлу

let flashTimer = null

/** Прокрутить к узлу (по центру по горизонтали, в верхней трети) и, если нужно, подсветить. */
async function focus(id, { flash = false, smooth = true, ifHidden = false } = {}) {
  await nextTick()
  const vp = viewport.value
  const el = vp?.querySelector(`[data-node-id="${CSS.escape(String(id))}"]`)
  if (!el) return
  const box = el.getBoundingClientRect()
  const view = vp.getBoundingClientRect()
  const inside = box.left >= view.left && box.right <= view.right && box.top >= view.top && box.bottom <= view.bottom
  if (!(ifHidden && inside)) vp.scrollTo({
    left: vp.scrollLeft + box.left - view.left - (view.width - box.width) / 2,
    top: vp.scrollTop + box.top - view.top - Math.max(PAD, Math.min(view.height / 3, (view.height - box.height) / 2)),
    behavior: smooth ? 'smooth' : 'auto',
  })
  if (flash) {
    vp.querySelectorAll('.oc-flash').forEach((node) => node.classList.remove('oc-flash'))
    void el.offsetWidth
    el.classList.add('oc-flash')
    clearTimeout(flashTimer)
    flashTimer = setTimeout(() => el.classList.remove('oc-flash'), 1800)
  }
}

/** Показать верх схемы (корни) по центру. */
async function home() {
  await nextTick()
  const vp = viewport.value
  if (vp) vp.scrollTo({ left: (vp.scrollWidth - vp.clientWidth) / 2, top: 0 })
}

// ---------------------------------------------------------------- перетаскивание мышью

let drag = null
let suppressClick = false
function onPointerDown(event) {
  if (event.button !== 0 || event.pointerType === 'touch' || event.target.closest('input, select, textarea')) return
  drag = { x: event.clientX, y: event.clientY, left: viewport.value.scrollLeft, top: viewport.value.scrollTop, id: event.pointerId, moved: false }
}
function onPointerMove(event) {
  if (!drag) return
  const dx = event.clientX - drag.x
  const dy = event.clientY - drag.y
  if (!drag.moved) {
    if (Math.hypot(dx, dy) < 5) return
    drag.moved = true
    dragging.value = true
    viewport.value.setPointerCapture?.(drag.id)
  }
  viewport.value.scrollLeft = drag.left - dx
  viewport.value.scrollTop = drag.top - dy
}
function onPointerUp() {
  if (drag?.moved) {
    suppressClick = true
    setTimeout(() => { suppressClick = false }, 0)
  }
  drag = null
  dragging.value = false
}
function onClickCapture(event) {
  if (!suppressClick) return
  event.stopPropagation()
  event.preventDefault()
}

function onKey(event) {
  if (event.target !== viewport.value || event.ctrlKey || event.metaKey || event.altKey) return
  if (event.key === '+' || event.key === '=') zoomBy(0.1)
  else if (event.key === '-') zoomBy(-0.1)
  else if (event.key === '0') zoomTo(1)
  else return
  event.preventDefault()
}

defineExpose({ fit, focus, home, zoomTo, zoomBy })
</script>

<template>
  <div class="oc-wrap">
    <div ref="viewport" class="oc-viewport scroll-thin" :class="{ 'oc-dragging': dragging }" tabindex="0" role="region"
         :aria-label="`${label}: перетаскивайте мышью, Ctrl + колесо — масштаб, + и − — масштаб с клавиатуры`"
         @pointerdown="onPointerDown" @pointermove="onPointerMove" @pointerup="onPointerUp" @pointercancel="onPointerUp"
         @click.capture="onClickCapture" @wheel="onWheel" @keydown="onKey">
      <div class="oc-stage" :class="`oc-stage--${orientation}`">
        <div ref="sizer" class="oc-sizer" :style="sizerStyle">
          <div ref="canvas" class="oc-canvas" :class="`oc--${orientation}`" :style="{ transform: `scale(${zoom})` }">
            <ul class="oc-level oc-root">
              <OrgChartBranch v-for="node in forest" :key="node.id" :node="node" :expanded="expanded" :path="path"
                              :stack="stackLeaves" :orientation="orientation">
                <template #default="slotProps"><slot v-bind="slotProps" /></template>
              </OrgChartBranch>
            </ul>
          </div>
        </div>
      </div>
    </div>
    <slot name="overlay" />
  </div>
</template>

<style>
/* Линии рисуются псевдоэлементами узлов; стили общие для ветвей (OrgChartBranch) */
.oc-wrap { position: relative; min-height: 0; display: flex; flex-direction: column; }
.oc-viewport {
  --oc-gap: 22px; --oc-w: 1.5px;
  --oc-line: color-mix(in srgb, var(--text) 20%, transparent);
  --oc-path: var(--accent);
  position: relative; flex: 1; min-height: 0; overflow: auto; cursor: grab; outline: none;
  border: 1px solid var(--border); border-radius: var(--radius-lg);
  background:
    radial-gradient(circle at 1px 1px, color-mix(in srgb, var(--text) 9%, transparent) 1px, transparent 1.4px) 0 0 / 22px 22px,
    var(--surface-2);
  overscroll-behavior: contain;
}
.oc-viewport:focus-visible { box-shadow: 0 0 0 3px var(--focus); }
.oc-viewport.oc-dragging { cursor: grabbing; user-select: none; }
.oc-viewport.oc-dragging * { cursor: grabbing !important; }
.oc-stage { min-width: 100%; min-height: 100%; width: max-content; display: flex; justify-content: center; align-items: flex-start; padding: 32px; }
.oc-stage--horizontal { align-items: center; }
.oc-sizer { position: relative; flex: 0 0 auto; }
.oc-canvas { position: absolute; top: 0; left: 0; width: max-content; transform-origin: 0 0; }

.oc-level { position: relative; display: flex; margin: 0; padding: var(--oc-gap) 0 0; list-style: none; }
.oc-root { padding: 0 !important; gap: 28px; }
.oc-node { position: relative; display: flex; flex-direction: column; align-items: center; padding: var(--oc-gap) 8px 0; list-style: none; }
.oc-slot { position: relative; z-index: 1; border-radius: 14px; }
.oc-bar { position: absolute; z-index: 0; pointer-events: none; }
.oc-node::before, .oc-node::after, .oc-level::before { content: ''; position: absolute; box-sizing: border-box; pointer-events: none; }

/* ---- сверху вниз ---- */
.oc--vertical .oc-node::before, .oc--vertical .oc-node::after { top: 0; width: 50%; height: var(--oc-gap); border-top: var(--oc-w) solid var(--oc-line); }
.oc--vertical .oc-node::before { right: 50%; }
.oc--vertical .oc-node::after { left: 50%; border-left: var(--oc-w) solid var(--oc-line); }
.oc--vertical .oc-node:only-of-type::before { border: 0; }
.oc--vertical .oc-node:only-of-type::after { border-top: 0; }
.oc--vertical .oc-node:first-of-type:not(:only-of-type)::before { border: 0; }
.oc--vertical .oc-node:first-of-type:not(:only-of-type)::after { border-top-left-radius: 12px; }
.oc--vertical .oc-node:last-of-type:not(:only-of-type)::after { border: 0; }
.oc--vertical .oc-node:last-of-type:not(:only-of-type)::before { border-right: var(--oc-w) solid var(--oc-line); border-top-right-radius: 12px; }
.oc--vertical .oc-level .oc-level::before { top: 0; left: 50%; height: var(--oc-gap); border-left: var(--oc-w) solid var(--oc-line); }
.oc--vertical .oc-level:not(.oc-level--stack) > .oc-bar { top: var(--oc-gap); height: 0; border-top: var(--oc-w) solid var(--oc-path); }
.oc--vertical .oc-node--path::after { border-left-color: var(--oc-path); }
.oc--vertical .oc-node--path:last-of-type:not(:only-of-type)::before { border-right-color: var(--oc-path); }
.oc--vertical .oc-node--path::before, .oc--vertical .oc-node--path::after { border-radius: 0 !important; }

/* ---- нижний уровень столбиком: ствол под центром родителя, карточки справа ---- */
.oc--vertical .oc-level--stack { display: grid; grid-template-columns: 1fr 28px 1fr; align-items: start; }
.oc--vertical .oc-level.oc-level--stack > .oc-node { grid-column: 3; align-items: flex-start; padding: 10px 0 0; }
.oc--vertical .oc-level.oc-level--stack > .oc-node:first-of-type { padding-top: 0; }
.oc--vertical .oc-level.oc-level--stack > .oc-node::before { left: -14px; top: 0; bottom: 0; right: auto; width: 0; height: auto; border: 0; border-left: var(--oc-w) solid var(--oc-line); border-radius: 0; }
.oc--vertical .oc-level.oc-level--stack > .oc-node::after { left: -14px; top: calc(50% + 5px); right: auto; width: 14px; height: 0; border: 0; border-top: var(--oc-w) solid var(--oc-line); border-radius: 0; }
.oc--vertical .oc-level.oc-level--stack > .oc-node:first-of-type::after { top: 50%; }
.oc--vertical .oc-level.oc-level--stack > .oc-node:last-of-type::before { bottom: auto; width: 14px; height: calc(50% + 5px); border-bottom: var(--oc-w) solid var(--oc-line); border-bottom-left-radius: 10px; }
.oc--vertical .oc-level.oc-level--stack > .oc-node:last-of-type::after { display: none; }
.oc--vertical .oc-level.oc-level--stack > .oc-bar { left: 50%; width: 0; border-left: var(--oc-w) solid var(--oc-path); }
.oc--vertical .oc-level.oc-level--stack > .oc-node.oc-node--path::after { border-top-color: var(--oc-path); }
.oc--vertical .oc-level.oc-level--stack > .oc-node.oc-node--path:last-of-type::before { border-color: var(--oc-path); border-radius: 0; }

/* ---- слева направо ---- */
.oc--horizontal .oc-level { flex-direction: column; align-items: flex-start; padding: 0 0 0 var(--oc-gap); }
.oc--horizontal .oc-node { flex-direction: row; align-items: center; padding: 6px 0 6px var(--oc-gap); }
.oc--horizontal .oc-node::before, .oc--horizontal .oc-node::after { left: 0; width: var(--oc-gap); height: 50%; border-left: var(--oc-w) solid var(--oc-line); }
.oc--horizontal .oc-node::before { top: 0; }
.oc--horizontal .oc-node::after { top: 50%; border-top: var(--oc-w) solid var(--oc-line); }
.oc--horizontal .oc-node:only-of-type::before { border: 0; }
.oc--horizontal .oc-node:only-of-type::after { border-left: 0; }
.oc--horizontal .oc-node:first-of-type:not(:only-of-type)::before { border: 0; }
.oc--horizontal .oc-node:first-of-type:not(:only-of-type)::after { border-top-left-radius: 12px; }
.oc--horizontal .oc-node:last-of-type:not(:only-of-type)::after { border: 0; }
.oc--horizontal .oc-node:last-of-type:not(:only-of-type)::before { border-bottom: var(--oc-w) solid var(--oc-line); border-bottom-left-radius: 12px; }
.oc--horizontal .oc-level .oc-level::before { left: 0; top: 50%; width: var(--oc-gap); border-top: var(--oc-w) solid var(--oc-line); }
.oc--horizontal .oc-level > .oc-bar { left: var(--oc-gap); width: 0; border-left: var(--oc-w) solid var(--oc-path); }
.oc--horizontal .oc-node--path::after { border-top-color: var(--oc-path); }
.oc--horizontal .oc-node--path:last-of-type:not(:only-of-type)::before { border-bottom-color: var(--oc-path); }
.oc--horizontal .oc-node--path::before, .oc--horizontal .oc-node--path::after { border-radius: 0 !important; }

.oc-root > .oc-node { padding: 0 !important; }
.oc-root > .oc-node::before, .oc-root > .oc-node::after { display: none; }
.oc-level--path::before { border-color: var(--oc-path) !important; }

/* Подсветка найденного узла */
.oc-slot.oc-flash { animation: oc-flash 1.7s var(--ease); }
@keyframes oc-flash {
  0%, 100% { box-shadow: 0 0 0 0 transparent; }
  15%, 55% { box-shadow: 0 0 0 6px color-mix(in srgb, var(--accent) 38%, transparent); }
}
@media (prefers-reduced-motion: reduce) {
  .oc-slot.oc-flash { animation: none; box-shadow: 0 0 0 4px color-mix(in srgb, var(--accent) 38%, transparent); }
}
</style>
