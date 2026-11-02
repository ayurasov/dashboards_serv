<script setup>
import { computed } from 'vue'
import { PLAN_ACTIONS, displayValue, filterPlanUsers } from '@/domain/org'
import { HISTORY_FIELDS } from '@/domain/org'

/** Строки плана загрузки списком и синхронизации с AD: сотрудник, подразделение, руководитель, что изменится. */
const props = defineProps({
  users: { type: Array, required: true },
  filter: { type: String, default: 'changes' },
})
const rows = computed(() => filterPlanUsers(props.users, props.filter))
const FIELDS = { ...HISTORY_FIELDS, full_name: 'ФИО', name: 'ФИО', email: 'Email', login: 'Логин', is_active: 'Активен', department_id: 'Подразделение', manager_id: 'Руководитель', external_id: 'Внешний ID', head: 'Руководит' }
const fieldLabel = (f) => FIELDS[f] || f
</script>

<template>
  <div class="table-wrap plan-table">
    <table class="table table-compact">
      <thead><tr><th class="num">Стр.</th><th>Сотрудник</th><th>Подразделение</th><th>Руководитель</th><th>Что изменится</th></tr></thead>
      <tbody>
        <tr v-for="u in rows" :key="`${u.line}-${u.email}`" :class="{ err: u.errors.length }">
          <td class="num muted">{{ u.line || '—' }}</td>
          <td class="who">
            <strong>{{ u.name || u.email || '—' }}</strong>
            <small v-if="u.email && u.name">{{ u.email }}</small>
            <span class="badge" :class="`badge-${PLAN_ACTIONS[u.action]?.tone || 'gray'}`">{{ PLAN_ACTIONS[u.action]?.label || u.action }}</span>
          </td>
          <td class="path">{{ u.department || '—' }}</td>
          <td>{{ u.manager || '—' }}<small v-if="u.manager" class="src">{{ u.manager_explicit ? 'явно' : 'по структуре' }}</small></td>
          <td class="what">
            <ul v-if="u.errors.length" class="errors"><li v-for="e in u.errors" :key="e">{{ e }}</li></ul>
            <ul v-if="u.changes.length" class="changes">
              <li v-for="c in u.changes" :key="c.field"><span class="lbl">{{ fieldLabel(c.field) }}:</span> <s v-if="displayValue(c.old) !== '—'">{{ displayValue(c.old) }}</s><template v-if="displayValue(c.old) !== '—'"> → </template>{{ displayValue(c.new) }}</li>
            </ul>
            <ul v-if="u.warnings.length" class="warnings"><li v-for="w in u.warnings" :key="w">{{ w }}</li></ul>
            <span v-if="!u.errors.length && !u.changes.length && !u.warnings.length" class="muted">{{ u.action === 'create' ? 'будет создан' : '—' }}</span>
          </td>
        </tr>
      </tbody>
    </table>
    <p v-if="!rows.length" class="empty">Нет строк по выбранному отбору</p>
  </div>
</template>

<style scoped>
.plan-table { border: 1px solid var(--border); border-radius: 12px; max-height: 520px; }
.table td { vertical-align: top; font-size: var(--fs-sm); }
.badge-blue { background: color-mix(in srgb, var(--accent) 13%, transparent); color: var(--on-blue); }
.who strong { display: block; font-weight: 600; }
.who small, .src { display: block; font-size: var(--fs-xs); color: var(--muted); }
.who .badge { margin-top: 4px; }
.path { min-width: 180px; color: var(--text-2); }
.what { min-width: 240px; }
.changes, .errors, .warnings { margin: 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 2px; }
.changes .lbl { color: var(--muted); }
.changes s { color: var(--muted); }
.errors { color: var(--light-red); }
.warnings { color: color-mix(in srgb, var(--light-yellow) 80%, var(--text)); }
tr.err td { background: color-mix(in srgb, var(--light-red) 4%, transparent); }
.muted { color: var(--muted); }
.empty { padding: 18px; text-align: center; font-size: var(--fs-sm); color: var(--muted); }
</style>
