<script setup>
import { computed } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import SideDrawer from '@/components/admin/SideDrawer.vue'
import { integrationsApi } from '@/api/integrations'
import { useAsync } from '@/composables/useAsync'
import { runCounters, runDuration, runStatus } from '@/domain/integrations'
import { formatDateTime, formatNumber, formatRelative } from '@/utils/format'

/** Журнал запусков подключения: повод, кто запустил, время, итог, счётчики сводки, текст ошибки. */
const props = defineProps({
  integration: { type: Object, required: true },
  kind: { type: Object, default: null },
})
const emit = defineEmits(['close'])
const LIMIT = 100
const { data, loading, error, reload } = useAsync(() => integrationsApi.runs(props.integration.id, LIMIT))
const runs = computed(() => data.value || [])
const actionLabel = (key) => (props.kind?.actions || []).find((a) => a.key === key)?.label || key
</script>

<template>
  <SideDrawer :title="`Журнал запусков: ${integration.name}`" :width="880" sheet @close="emit('close')">
    <template #header>
      <div class="jh">
        <h2>Журнал запусков</h2>
        <p class="muted">{{ integration.name }} · последние {{ LIMIT }}</p>
      </div>
    </template>
    <div class="row-wrap top">
      <span class="muted">Запуски вручную, по расписанию и командой; сервер хранит последние записи каждого подключения.</span>
      <span class="spacer" />
      <button type="button" class="btn btn-sm" :disabled="loading" @click="reload()"><AppIcon name="refresh" :size="13" />Обновить</button>
    </div>
    <div v-if="loading && !data" class="skeleton" style="height: 240px" />
    <EmptyState v-else-if="error && !data" compact icon="alert" title="Не удалось загрузить журнал" :text="error.message" />
    <EmptyState v-else-if="!runs.length" compact icon="history" title="Запусков пока не было" text="Запустите действие кнопкой «Запустить» на карточке или задайте расписание." />
    <div v-else class="table-wrap bordered">
      <table class="table table-compact runs" data-testid="runs-table">
        <thead><tr><th>Начало</th><th>Действие</th><th>Повод</th><th>Кто</th><th>Итог</th><th class="num">Длительность</th><th>Сводка</th></tr></thead>
        <tbody>
          <tr v-for="r in runs" :key="r.id" :class="`s-${r.status}`">
            <td class="nowrap" :title="formatRelative(r.started_at)"><span class="lbl">Начало: </span>{{ formatDateTime(r.started_at) }}</td>
            <td><b>{{ actionLabel(r.action) }}</b></td>
            <td><span class="lbl">Повод: </span>{{ r.trigger_label }}</td>
            <td><span class="lbl">Кто: </span>{{ r.username || '—' }}</td>
            <td><span class="badge" :class="`badge-${runStatus(r).tone}`">{{ runStatus(r).label }}</span></td>
            <td class="num"><span class="lbl">Длительность: </span>{{ runDuration(r) }}</td>
            <td class="sum">
              <p v-if="r.message && r.message !== r.error">{{ r.message }}</p>
              <p v-if="runCounters(r.summary).length" class="counters">
                <span v-for="c in runCounters(r.summary)" :key="c.key">{{ c.label }}: <b class="num">{{ formatNumber(c.value) }}</b></span>
              </p>
              <p v-if="r.error" class="err">{{ r.error }}</p>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </SideDrawer>
</template>

<style scoped>
.jh h2 { font-size: 16px; }
.jh p { font-size: var(--fs-xs); }
.muted { color: var(--muted); font-size: var(--fs-sm); }
.top { margin-bottom: 12px; }
.bordered { border: 1px solid var(--border); border-radius: 12px; }
.runs td { vertical-align: top; font-size: var(--fs-sm); }
.sum { min-width: 240px; }
.sum p + p { margin-top: 3px; }
.counters { display: flex; flex-wrap: wrap; gap: 2px 12px; font-size: var(--fs-xs); color: var(--text-2); }
.err { color: var(--light-red); font-size: var(--fs-xs); overflow-wrap: anywhere; white-space: pre-line; }
.lbl { display: none; color: var(--muted); }
@media (max-width: 760px) {
  .runs thead { display: none; }
  .runs, .runs tbody { display: block; }
  .runs tr { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 3px 10px; padding: 10px 12px; border-bottom: 1px solid var(--border); }
  .runs td { display: block; padding: 0; border: 0; text-align: left; }
  .runs td:nth-child(5) { grid-column: 2; grid-row: 1; }
  .runs td:not(:nth-child(5)) { grid-column: 1 / -1; }
  .runs td:nth-child(2) { grid-row: 1; grid-column: 1; }
  .runs .lbl { display: inline; }
  .runs td.num { text-align: left; }
  .sum { min-width: 0; }
}
</style>
