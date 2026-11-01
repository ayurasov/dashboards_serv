<script setup>
import { nextTick, onBeforeUnmount, ref } from 'vue'
import OrgIcon from './OrgIcon.vue'
import { TABLE_COLUMNS } from '@/domain/org'

/**
 * Вид «Таблица»: путь, тип, уровень, руководитель, штат, ветка, вложенные. Сортировка — по
 * заголовку; отступ по уровню — только в порядке дерева.
 */
const props = defineProps({
  rows: { type: Array, required: true },
  sort: { type: Object, required: true },
  indent: { type: Boolean, default: true },
  selectedId: { type: Number, default: null },
  myUnitId: { type: Number, default: null },
  totals: { type: Object, default: null },
})
const emit = defineEmits(['sort', 'select-unit', 'select-person'])

const scroller = ref(null)
const flashId = ref(null)
let timer = null
onBeforeUnmount(() => clearTimeout(timer))

async function focus(id, { flash = false } = {}) {
  await nextTick()
  const row = scroller.value?.querySelector(`tr[data-unit-id="${id}"]`)
  if (!row) return
  const box = scroller.value.getBoundingClientRect()
  const r = row.getBoundingClientRect()
  if (r.top < box.top + 40 || r.bottom > box.bottom) {
    scroller.value.scrollTo({ top: scroller.value.scrollTop + r.top - box.top - box.height / 3, behavior: 'smooth' })
  }
  if (flash) {
    flashId.value = null
    await nextTick()
    flashId.value = id
    clearTimeout(timer)
    timer = setTimeout(() => { flashId.value = null }, 1800)
  }
}
defineExpose({ focus })

const ariaSort = (key) => (props.sort.key === key ? (props.sort.dir === 'asc' ? 'ascending' : 'descending') : 'none')
</script>

<template>
  <section class="org-table card">
    <div ref="scroller" class="table-wrap scroll-thin">
      <table class="table">
        <thead>
          <tr>
            <th v-for="col in TABLE_COLUMNS" :key="col.key" :class="{ num: col.num, sorted: sort.key === col.key }" :aria-sort="ariaSort(col.key)" :title="col.hint">
              <button type="button" class="sort" @click="emit('sort', col.key)">
                {{ col.label }}
                <OrgIcon :name="sort.key === col.key && sort.dir === 'desc' ? 'arrow-down' : 'arrow-up'" :size="12" :stroke="2.2" class="arrow" />
              </button>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.id" class="clickable" :class="{ selected: row.id === selectedId, flash: row.id === flashId }"
              :data-unit-id="row.id" tabindex="0" @click="emit('select-unit', row.id)" @keydown.enter="emit('select-unit', row.id)">
            <td class="path-cell" :style="{ '--level': indent ? Math.min(row.level - 1, 10) : 0 }">
              <span class="unit-name">{{ row.name }}<span v-if="row.id === myUnitId" class="you">Вы здесь</span></span>
              <small v-if="row.parentPath && !indent" :title="row.parentPath">{{ row.parentPath }}</small>
            </td>
            <td><span class="kind" :style="{ '--kind': row.kindColor }"><i />{{ row.kindLabel }}</span></td>
            <td class="num muted">{{ row.level }}</td>
            <td class="head-cell">
              <button v-if="row.headId" type="button" class="link-btn" @click.stop="emit('select-person', row.headId)">{{ row.headName }}</button>
              <span v-else class="no-head">не назначен</span>
              <span v-if="row.headCount > 1" class="more" :title="`Руководителей: ${row.headCount}`">+{{ row.headCount - 1 }}</span>
            </td>
            <td class="num strong">{{ row.staff.toLocaleString('ru-RU') }}</td>
            <td class="num">{{ row.branch.toLocaleString('ru-RU') }}</td>
            <td class="num muted">{{ row.nested || '—' }}</td>
          </tr>
        </tbody>
        <tfoot v-if="totals && rows.length">
          <tr>
            <td colspan="4">Итого: {{ totals.label }}</td>
            <td class="num">{{ totals.staff.toLocaleString('ru-RU') }}</td>
            <td class="num">{{ totals.branch === null ? '—' : totals.branch.toLocaleString('ru-RU') }}</td>
            <td />
          </tr>
        </tfoot>
      </table>
      <p v-if="!rows.length" class="empty">Нет подразделений этого типа</p>
    </div>
  </section>
</template>

<style scoped>
.org-table { display: flex; flex-direction: column; min-height: 0; overflow: hidden; }
.table-wrap { flex: 1; min-height: 0; overflow: auto; border-radius: var(--radius-lg); }
.table th { padding: 0; }
.table th .sort { display: inline-flex; align-items: center; gap: 4px; width: 100%; padding: 10px 14px; border: 0; background: transparent; font: inherit; color: inherit; text-transform: inherit; letter-spacing: inherit; cursor: pointer; }
.table th.num .sort { flex-direction: row-reverse; justify-content: flex-start; }
.table th .sort:hover { color: var(--text); }
.table th .sort:focus-visible { outline: 2px solid var(--focus); outline-offset: -2px; }
.arrow { opacity: 0; transition: opacity var(--t-fast); }
.table th:hover .arrow { opacity: .45; }
.table th.sorted { color: var(--text); }
.table th.sorted .arrow { opacity: 1; }
.table td { padding: 9px 14px; }
.table tbody tr.selected { background: color-mix(in srgb, var(--accent) 10%, transparent); }
.table tbody tr.selected td:first-child { box-shadow: inset 3px 0 0 var(--accent); }
.table tbody tr:focus-visible { outline: 2px solid var(--focus); outline-offset: -2px; }
.table tbody tr.flash { animation: row-flash 1.7s var(--ease); }
@keyframes row-flash { 15%, 55% { background: color-mix(in srgb, var(--accent) 18%, transparent); } }
.path-cell { padding-left: calc(14px + var(--level) * 18px) !important; min-width: 280px; max-width: 460px; }
.unit-name { display: flex; align-items: center; gap: 8px; font-weight: 600; }
.path-cell small { display: block; font-size: var(--fs-xs); color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.you { height: 18px; padding: 0 7px; display: inline-flex; align-items: center; border-radius: var(--radius-pill); background: var(--text); color: var(--bg-elevated); font-size: 10.5px; font-weight: 650; }
.kind { display: inline-flex; align-items: center; gap: 6px; white-space: nowrap; font-size: var(--fs-sm); color: color-mix(in srgb, var(--kind) 80%, var(--text)); font-weight: 560; }
.kind i { width: 8px; height: 8px; border-radius: 3px; background: var(--kind); }
.head-cell { white-space: nowrap; }
.link-btn { padding: 0; border: 0; background: transparent; color: var(--text); font: inherit; cursor: pointer; text-align: left; }
.link-btn:hover { color: var(--accent); text-decoration: underline; }
.no-head { color: color-mix(in srgb, var(--light-yellow) 80%, var(--text)); font-size: var(--fs-sm); }
.more { margin-left: 6px; padding: 1px 6px; border-radius: var(--radius-pill); background: var(--surface-3); font-size: var(--fs-xs); color: var(--text-2); font-weight: 600; }
.strong { font-weight: 640; }
.muted { color: var(--muted); }
.table tfoot td { position: sticky; bottom: 0; }
.empty { padding: 32px; text-align: center; color: var(--muted); }
@media (max-width: 760px) {
  .path-cell { min-width: 190px; max-width: 240px; }
  .table th:first-child, .table td:first-child { position: sticky; left: 0; z-index: 1; background: var(--surface); box-shadow: 1px 0 0 var(--border); }
  .table th:first-child { z-index: 2; background: var(--surface-2); }
  .table tbody tr.selected td:first-child { background: color-mix(in srgb, var(--accent) 10%, var(--surface)); }
  .table tfoot td:first-child { background: var(--surface-2); }
}
</style>
