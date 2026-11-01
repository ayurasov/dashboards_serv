<script setup>
import { computed } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import { auditDiff } from '@/domain/admin'
import { plural } from '@/utils/format'

/** Подробности записи журнала: «было → стало» таблицей «поле — значение». */
const props = defineProps({
  entry: { type: Object, required: true },
  labels: { type: Object, default: () => ({}) },
})
const diff = computed(() => auditDiff(props.entry.before, props.entry.after, { labels: props.labels }))
const HEADINGS = { diff: ['Было', 'Стало'], after: [null, 'Значение'], before: ['Значение до удаления', null] }
</script>

<template>
  <div class="audit-diff">
    <table v-if="diff.rows.length" class="kv" :class="diff.mode">
      <thead>
        <tr>
          <th class="k">Поле</th>
          <th v-if="HEADINGS[diff.mode][0]">{{ HEADINGS[diff.mode][0] }}</th>
          <th v-if="diff.mode === 'diff'" class="arrow" />
          <th v-if="HEADINGS[diff.mode][1]">{{ HEADINGS[diff.mode][1] }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="r in diff.rows" :key="r.path">
          <td class="k"><span :class="{ raw: !r.known }" :title="r.path">{{ r.label }}</span></td>
          <td v-if="diff.mode !== 'after'" class="v" :class="{ old: diff.mode === 'diff', empty: r.beforeText === '—' }">
            <span v-if="r.beforeColors" class="swatches"><i v-for="(c, i) in r.beforeColors" :key="i" :style="{ background: c }" :title="c" /></span>
            <span v-else>{{ r.beforeText }}</span>
          </td>
          <td v-if="diff.mode === 'diff'" class="arrow"><AppIcon name="chevron-right" :size="14" /></td>
          <td v-if="diff.mode !== 'before'" class="v" :class="{ new: diff.mode === 'diff', empty: r.afterText === '—' }">
            <span v-if="r.afterColors" class="swatches"><i v-for="(c, i) in r.afterColors" :key="i" :style="{ background: c }" :title="c" /></span>
            <span v-else>{{ r.afterText }}</span>
          </td>
        </tr>
      </tbody>
    </table>
    <p v-else class="muted none">Подробности для этого действия не записываются</p>
    <p v-if="diff.unchanged" class="muted foot">
      Ещё {{ diff.unchanged }} {{ plural(diff.unchanged, ['поле', 'поля', 'полей']) }} без изменений
    </p>
  </div>
</template>

<style scoped>
.kv { width: 100%; max-width: 920px; table-layout: fixed; border-collapse: separate; border-spacing: 0; font-size: var(--fs-sm); background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; }
.kv th { padding: 7px 12px; text-align: left; font-size: var(--fs-xs); font-weight: 620; color: var(--muted); background: var(--surface-2); border-bottom: 1px solid var(--border); text-transform: none; letter-spacing: 0; }
.kv td { padding: 7px 12px; border-bottom: 1px solid var(--border); vertical-align: top; }
.kv tbody tr:last-child td { border-bottom: 0; }
.k { width: 30%; color: var(--text-2); font-weight: 540; }
.raw { font-family: var(--font-mono); font-size: var(--fs-xs); font-weight: 500; }
.v { word-break: break-word; white-space: pre-line; font-variant-numeric: tabular-nums; }
.old { color: var(--muted); }
.old:not(.empty) span:not(.swatches) { text-decoration: line-through; text-decoration-color: color-mix(in srgb, var(--light-red) 55%, transparent); }
.empty { color: var(--faint); font-weight: 400; }
.new { color: var(--text); font-weight: 540; }
.arrow { width: 28px; padding-left: 0 !important; padding-right: 0 !important; color: var(--faint); }
.swatches { display: inline-flex; gap: 3px; vertical-align: middle; }
.swatches i { width: 16px; height: 16px; border-radius: 4px; box-shadow: inset 0 0 0 1px rgba(0, 0, 0, .12); }
.none { font-size: var(--fs-sm); }
.foot { margin-top: 6px; font-size: var(--fs-xs); }
</style>
