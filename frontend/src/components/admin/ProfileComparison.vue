<script setup>
import { computed } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import { profileComparison } from '@/domain/access'

/** Сравнение профилей доступа «кто что видит»: столбцы — профили, строки — измерения и службы. */
const props = defineProps({
  profiles: { type: Array, default: () => [] },
  services: { type: Array, default: () => [] },
})
const emit = defineEmits(['edit'])
const table = computed(() => profileComparison(props.profiles, props.services))
const groups = computed(() => [
  { key: 'dimensions', label: 'Что видит', rows: table.value.rows.filter((r) => r.group === 'dimensions') },
  { key: 'services', label: 'Службы', rows: table.value.rows.filter((r) => r.group === 'services') },
])
</script>

<template>
  <div class="cmp-wrap scroll-thin">
    <table class="cmp" data-testid="profile-comparison">
      <thead>
        <tr>
          <th class="corner" scope="col"><span class="sr-only">Измерение</span></th>
          <th v-for="c in table.columns" :key="c.key || 'individual'" scope="col" :class="{ indiv: c.individual }">
            <button v-if="!c.individual" type="button" class="col-name" :title="`Изменить профиль «${c.name}»`" @click="emit('edit', c.id)">{{ c.name }}</button>
            <span v-else class="col-name static" title="Пользователи без профиля: как в версии 0.1.0">{{ c.name }}</span>
            <small v-if="!c.individual">{{ c.users_count }} польз.</small>
            <small v-else>по умолчанию</small>
          </th>
        </tr>
      </thead>
      <tbody v-for="g in groups" :key="g.key">
        <tr class="group"><th :colspan="table.columns.length + 1" scope="colgroup">{{ g.label }}</th></tr>
        <tr v-for="r in g.rows" :key="r.key">
          <th scope="row" :title="r.hint || ''">{{ r.label }}</th>
          <td v-for="(cell, i) in r.cells" :key="i" :class="[`t-${cell.tone}`, { indiv: table.columns[i].individual }]">
            <span v-if="cell.text === 'Да'" class="yes"><AppIcon name="check" :size="14" :stroke="2.4" /><span class="sr-only">Да</span></span>
            <span v-else-if="cell.text === 'Нет' || cell.text === '—'" class="no">—<span class="sr-only">Нет</span></span>
            <span v-else>{{ cell.text }}</span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.cmp-wrap { position: relative; overflow-x: auto; }
.cmp { width: 100%; min-width: 760px; border-collapse: separate; border-spacing: 0; font-size: var(--fs-sm); }
.cmp th, .cmp td { padding: 9px 12px; border-bottom: 1px solid var(--border); text-align: center; vertical-align: middle; }
.cmp thead th { position: sticky; top: 0; background: var(--surface-2); vertical-align: bottom; }
.cmp thead th small { display: block; margin-top: 1px; font-size: var(--fs-xs); font-weight: 500; color: var(--muted); }
.col-name { padding: 0; border: 0; background: none; color: var(--text); font-weight: 650; font-size: var(--fs-sm); line-height: 1.25; cursor: pointer; }
.col-name:hover { color: var(--brand); }
.col-name.static { cursor: default; color: var(--text-2); font-weight: 600; }
.cmp tbody th { position: sticky; left: 0; z-index: 1; text-align: left; font-weight: 560; color: var(--text-2); background: var(--surface); white-space: nowrap; }
.corner { position: sticky; left: 0; z-index: 2; min-width: 190px; }
.group th { padding: 12px 12px 6px; background: var(--surface); border-bottom: 1px solid var(--border); text-align: left; font-size: 10.5px; font-weight: 650; letter-spacing: .06em; text-transform: uppercase; color: var(--faint); }
.cmp tbody tr:not(.group):hover td, .cmp tbody tr:not(.group):hover th { background: var(--row-hover); }
.cmp tbody:last-child tr:last-child td, .cmp tbody:last-child tr:last-child th { border-bottom: 0; }
.cmp td { color: var(--text); font-weight: 540; white-space: nowrap; }
.t-mid { color: var(--text-2); }
.t-off .no { color: var(--faint); }
.yes { display: inline-grid; place-items: center; width: 22px; height: 22px; border-radius: 50%; background: color-mix(in srgb, var(--light-green) 14%, transparent); color: var(--light-green); }
.indiv { background: color-mix(in srgb, var(--surface-2) 70%, transparent); }
</style>
