<script setup>
import { computed, ref } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import LightBadge from '@/components/ui/LightBadge.vue'
import { TABLE_COLUMNS, clientInfo, metricDigits, tableRows, totals, weekLight } from '@/domain/tp'
import { formatNumber, plural } from '@/utils/format'

/** Детальная таблица недель: поиск, сортировка по столбцу, точки светофора, строка итогов. */
const props = defineProps({
  rows: { type: Array, required: true },
  rules: { type: Object, default: () => ({}) },
  client: { type: String, default: '' },
})

const search = ref('')
const sortKey = ref('period')
const sortDir = ref('desc')
const METRICS = TABLE_COLUMNS.slice(1)

function sortBy(key) {
  if (sortKey.value === key) sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  else {
    sortKey.value = key
    sortDir.value = key === 'period' ? 'asc' : 'desc'
  }
}

const list = computed(() => tableRows(props.rows, { search: search.value, client: props.client, sortKey: sortKey.value, sortDir: sortDir.value }))
const sums = computed(() => totals(list.value, METRICS.map((c) => c.key)))
const cell = (value, key) => formatNumber(value, { digits: metricDigits(key) })
const dots = computed(() => list.value.map((r) => Object.fromEntries(METRICS.filter((c) => c.dot).map((c) => [c.key, weekLight(r, c.key, props.rules[c.key])]))))

const hint = computed(() => {
  const n = list.value.length
  const parts = [`${n} ${plural(n, ['неделя', 'недели', 'недель'])}`]
  const c = clientInfo(props.client)
  if (c) parts.push(`только недели с трудозатратами клиента «${c.label}»`)
  return parts.join(' · ')
})
</script>

<template>
  <section class="card tp-table">
    <header class="card-head head">
      <div class="titles">
        <h3>Детальная таблица</h3>
        <p class="hint">{{ hint }}</p>
      </div>
      <span class="spacer" />
      <label class="search"><AppIcon name="search" :size="14" /><input v-model="search" type="search" placeholder="Неделя, напр. 2025-W24" aria-label="Поиск недели" /></label>
    </header>
    <p class="legend muted">
      Точка — оценка недели по светофору. В итогах «В работе», «Решено / получено» и среднее время — средние за недели, остальное — суммы.
    </p>
    <div class="table-wrap scroll-thin wrap">
      <table class="table table-compact">
        <thead>
          <tr>
            <th v-for="c in TABLE_COLUMNS" :key="c.key" class="sortable" :class="{ num: c.key !== 'period', first: c.key === 'period', picked: c.key === client }"
                :aria-sort="sortKey === c.key ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'" @click="sortBy(c.key)">
              <span class="th">{{ c.label }}<span v-if="c.unit" class="th-unit">, {{ c.unit }}</span>
                <AppIcon v-if="sortKey === c.key" :name="sortDir === 'asc' ? 'arrow-up' : 'arrow-down'" :size="11" class="sort-icon" />
              </span>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(r, i) in list" :key="r.id ?? r.period">
            <td class="first nowrap">
              <span class="period num">{{ r.period }}</span>
              <span v-if="r.note" class="note" :title="r.note"><AppIcon name="note" :size="12" /></span>
            </td>
            <td v-for="c in METRICS" :key="c.key" class="num" :class="{ picked: c.key === client, empty: r[c.key] === null || r[c.key] === undefined }">
              <span class="val">
                <LightBadge v-if="c.dot && dots[i][c.key]" :light="dots[i][c.key]" dot />{{ cell(r[c.key], c.key) }}
              </span>
            </td>
          </tr>
        </tbody>
        <tfoot v-if="list.length">
          <tr>
            <td class="first nowrap">Итого</td>
            <td v-for="c in METRICS" :key="c.key" class="num" :class="{ picked: c.key === client }">{{ cell(sums[c.key], c.key) }}</td>
          </tr>
        </tfoot>
      </table>
      <EmptyState v-if="!list.length" compact icon="search" title="Ничего не найдено" text="Измените поиск или фильтр клиента." />
    </div>
  </section>
</template>

<style scoped>
.tp-table { display: flex; flex-direction: column; min-width: 0; }
.head { flex-wrap: wrap; }
.titles { min-width: 0; }
.hint { margin-top: 2px; font-size: var(--fs-xs); color: var(--muted); }
.legend { padding: 6px var(--sp-5) 12px; font-size: var(--fs-xs); }
.wrap { max-height: 560px; border-top: 1px solid var(--border); border-radius: 0 0 var(--radius-lg) var(--radius-lg); }
.search { display: flex; align-items: center; gap: 8px; height: 32px; padding: 0 10px; border: 1px solid var(--border-strong); border-radius: var(--radius); color: var(--muted); min-width: 230px; background: var(--surface); }
.search input { border: 0; outline: 0; background: transparent; width: 100%; color: var(--text); font-size: var(--fs-sm); }
.search:focus-within { border-color: var(--accent); box-shadow: 0 0 0 3px var(--focus); }
.th { display: inline-flex; align-items: center; gap: 2px; }
.th-unit { text-transform: none; letter-spacing: 0; font-weight: 500; }
.sort-icon { margin-left: 2px; }
.table th.num .th { justify-content: flex-end; }
.first { position: sticky; left: 0; z-index: 1; background: var(--surface); }
.table th.first { z-index: 2; background: var(--surface-2); }
.table tbody tr:hover td.first { background: var(--row-hover); }
.period { font-weight: 560; }
.note { display: inline-flex; vertical-align: -1px; margin-left: 6px; color: var(--muted); cursor: help; }
.val { display: inline-flex; align-items: center; gap: 6px; justify-content: flex-end; }
td.empty { color: var(--faint); }
td.picked { background: color-mix(in srgb, var(--accent) 6%, transparent); }
.table th.picked { color: var(--text); background: color-mix(in srgb, var(--accent) 8%, var(--surface-2)); }
.table tfoot td { position: sticky; bottom: 0; z-index: 1; border-bottom: 0; }
.table tfoot td.picked { background: color-mix(in srgb, var(--accent) 8%, var(--surface-2)); }
.table tfoot td.first { z-index: 2; background: var(--surface-2); }
@media (max-width: 640px) { .search { min-width: 0; flex: 1 1 100%; } }
</style>
