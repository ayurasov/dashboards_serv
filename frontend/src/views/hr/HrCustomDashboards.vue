<script setup>
import { computed, ref } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import SegmentedControl from '@/components/ui/SegmentedControl.vue'
import CustomWidget from '@/components/hr/CustomWidget.vue'
import DashboardEditor from '@/components/hr/DashboardEditor.vue'
import { hrApi } from '@/api/services'
import { useAsync } from '@/composables/useAsync'
import { useQueryState } from '@/composables/useQueryState'
import { confirm } from '@/composables/useConfirm'
import { toastOk } from '@/composables/useToast'
import { useAuthStore } from '@/stores/auth'
import { formatDate, plural } from '@/utils/format'
import { layoutBlocks, splitDashboards, widgetKeys } from '@/domain/hrWidgets'

const auth = useAuthStore()
const canShare = computed(() => auth.can('hr', 'editor'))
const { state: q } = useQueryState({ id: 0, months: 12 })

const list = useAsync(() => hrApi.dashboards())
const defs = useAsync(() => hrApi.metrics())
const analytics = useAsync(() => hrApi.dashboard([]))

const sections = computed(() => splitDashboards(list.data.value, auth.user?.id))
const active = computed(() => {
  const all = list.data.value || []
  return all.find((d) => d.id === q.id) || sections.value.mine[0] || sections.value.shared[0] || null
})
const blocks = computed(() => layoutBlocks(active.value?.widgets))

const PERIODS = [{ value: 3, label: '3 мес.' }, { value: 6, label: '6 мес.' }, { value: 12, label: '12 мес.' }, { value: 0, label: 'Все' }]
const series = computed(() => {
  const all = analytics.data.value?.series || []
  return q.months ? all.slice(-q.months) : all
})
const periodText = computed(() => {
  const s = series.value
  if (!s.length) return ''
  return s.length === 1 ? s[0].label : `${s[0].label} — ${s[s.length - 1].label}`
})
const widgetCount = (d) => `${d.widgets.length} ${plural(d.widgets.length, ['виджет', 'виджета', 'виджетов'])}`

// ---------- редактор ----------
const editing = ref(null)
function openNew() {
  editing.value = { name: '', is_shared: false, widgets: [] }
}
/** Заготовка для первого дашборда: две карточки и график — чтобы было с чего начать. */
const STARTER = [
  { widget_type: 'metric_card', title: '', config: { metric_key: 'turnover' }, sort_order: 0 },
  { widget_type: 'metric_card', title: '', config: { metric_key: 'avg_time_to_fill' }, sort_order: 1 },
  { widget_type: 'line_chart', title: 'Текучесть', config: { metric_keys: ['turnover', 'turnover_company'] }, sort_order: 2 },
]
function openStarter() {
  const known = new Set((defs.data.value || []).map((d) => d.key))
  const usable = (w) => !known.size || widgetKeys(w).every((k) => known.has(k))
  editing.value = { name: 'Мой дашборд', is_shared: false, widgets: STARTER.filter(usable) }
}
function openEdit(d) {
  editing.value = d
}
function openCopy(d) {
  editing.value = { name: `${d.name} (копия)`, is_shared: false, widgets: d.widgets }
}
async function onSaved(saved) {
  const isNew = !editing.value.id
  editing.value = null
  toastOk(isNew ? 'Дашборд создан' : 'Дашборд сохранён')
  await list.reload()
  q.id = saved.id
}
async function remove(d) {
  const ok = await confirm({
    title: `Удалить дашборд «${d.name}»?`,
    message: d.is_shared ? 'Дашборд общий — он пропадёт у всех пользователей службы персонала.' : 'Отменить удаление нельзя.',
    confirmText: 'Удалить', danger: true,
  })
  if (!ok) return
  try { await hrApi.deleteDashboard(d.id) } catch { return } // ошибку показал клиент API
  toastOk('Дашборд удалён')
  q.id = 0
  list.reload()
}
</script>

<template>
  <div class="page">
    <PageHeader title="Мои дашборды" description="Собственные подборки показателей службы персонала">
      <button class="btn btn-primary" type="button" @click="openNew"><AppIcon name="plus" :size="15" />Создать дашборд</button>
    </PageHeader>

    <div v-if="list.loading.value && !list.data.value" class="layout">
      <div class="skeleton" style="height: 240px" /><div class="skeleton" style="height: 420px" />
    </div>

    <EmptyState v-else-if="list.data.value && !list.data.value.length" icon="layout" title="Дашбордов пока нет"
                text="Соберите свою подборку из карточек метрик, графиков, таблиц и заметок. Личные дашборды видите только вы.">
      <button class="btn btn-primary" type="button" @click="openNew"><AppIcon name="plus" :size="15" />Создать дашборд</button>
      <button class="btn" type="button" @click="openStarter">Начать с заготовки</button>
    </EmptyState>

    <div v-else-if="list.data.value" class="layout">
      <!-- список дашбордов -->
      <nav class="card dash-list" aria-label="Дашборды">
        <template v-for="s in [{ key: 'mine', label: 'Мои', items: sections.mine }, { key: 'shared', label: 'Общие', items: sections.shared }]" :key="s.key">
          <div v-if="s.items.length || s.key === 'mine'" class="list-section">
            <span class="list-title">{{ s.label }}</span>
            <button v-for="d in s.items" :key="d.id" type="button" class="list-item" :class="{ active: active?.id === d.id }" :aria-current="active?.id === d.id ? 'page' : undefined" @click="q.id = d.id">
              <AppIcon :name="d.is_shared ? 'users' : 'layout'" :size="15" class="list-icon" />
              <span class="list-text">
                <span class="list-name ellipsis">{{ d.name }}</span>
                <span class="list-meta ellipsis">{{ s.key === 'shared' ? (d.owner_name || 'Без автора') : (d.is_shared ? 'общий · ' : '') + widgetCount(d) }}</span>
              </span>
            </button>
            <p v-if="!s.items.length" class="list-empty muted">Своих дашбордов нет</p>
          </div>
        </template>
      </nav>

      <!-- выбранный дашборд -->
      <div v-if="active" class="stack main">
        <section class="card dash-head">
          <div class="titles">
            <h2>{{ active.name }}</h2>
            <p class="meta">
              <span class="badge" :class="active.is_shared ? 'badge-brand' : 'badge-gray'">{{ active.is_shared ? 'Общий' : 'Личный' }}</span>
              <span v-if="!active.can_edit || active.owner_id !== auth.user?.id">{{ active.owner_name }}</span>
              <span>изменён {{ formatDate(active.updated_at) }}</span>
            </p>
          </div>
          <SegmentedControl v-model="q.months" :options="PERIODS" size="sm" />
          <div class="head-actions">
            <template v-if="active.can_edit">
              <button class="btn btn-sm" type="button" @click="openEdit(active)"><AppIcon name="edit" :size="13" />Изменить</button>
              <button class="btn btn-sm btn-icon btn-ghost" type="button" title="Удалить дашборд" @click="remove(active)"><AppIcon name="trash" :size="14" /></button>
            </template>
            <button v-else class="btn btn-sm" type="button" title="Создать личную копию, которую можно изменять" @click="openCopy(active)"><AppIcon name="copy" :size="13" />Создать копию</button>
          </div>
        </section>

        <div v-if="analytics.loading.value && !analytics.data.value" class="widgets">
          <div class="skeleton wide" style="height: 112px" />
          <div class="skeleton" style="height: 340px" /><div class="skeleton" style="height: 340px" />
        </div>
        <EmptyState v-else-if="!blocks.length" compact icon="grid" title="В дашборде пока нет виджетов"
                    :text="active.can_edit ? 'Добавьте карточки метрик, графики, таблицы или заметки.' : 'Автор ещё не добавил виджеты.'">
          <button v-if="active.can_edit" class="btn btn-primary" type="button" @click="openEdit(active)"><AppIcon name="plus" :size="15" />Добавить виджеты</button>
        </EmptyState>
        <div v-else class="widgets">
          <template v-for="b in blocks" :key="b.key">
            <div v-if="b.kind === 'cards'" class="grid grid-kpi wide">
              <CustomWidget v-for="w in b.items" :key="w.id" :widget="w" :series="series" :defs="defs.data.value || []" />
            </div>
            <div v-else class="w" :class="{ wide: b.wide }">
              <CustomWidget :widget="b.widget" :series="series" :defs="defs.data.value || []" :periodText="periodText" />
            </div>
          </template>
        </div>
      </div>
    </div>

    <DashboardEditor v-if="editing" :dashboard="editing" :defs="defs.data.value || []" :canShare="canShare" @close="editing = null" @saved="onSaved" />
  </div>
</template>

<style scoped>
.layout { display: grid; grid-template-columns: 252px minmax(0, 1fr); gap: var(--sp-4); align-items: start; }
@media (max-width: 960px) { .layout { grid-template-columns: minmax(0, 1fr); } }

.dash-list { padding: 10px; display: flex; flex-direction: column; gap: 10px; }
@media (min-width: 961px) { .dash-list { position: sticky; top: calc(var(--topbar-h) + var(--sp-4)); } }
.list-section { display: flex; flex-direction: column; gap: 2px; }
.list-title { padding: 4px 8px; font-size: var(--fs-xs); font-weight: 650; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); }
.list-item { display: flex; align-items: flex-start; gap: 10px; width: 100%; padding: 8px; border: 0; border-radius: var(--radius-sm); background: transparent; text-align: left; cursor: pointer; color: var(--text-2); transition: background var(--t-fast); }
.list-item:hover { background: var(--surface-3); color: var(--text); }
.list-item.active { background: var(--brand-soft); color: var(--text); }
.list-item.active .list-icon { color: var(--brand); }
.list-icon { margin-top: 2px; color: var(--muted); }
.list-text { display: flex; flex-direction: column; min-width: 0; }
.list-name { font-size: var(--fs-base); font-weight: 560; }
.list-meta { font-size: var(--fs-xs); color: var(--muted); }
.list-empty { padding: 4px 8px; font-size: var(--fs-sm); }

.main { gap: var(--sp-4); }
.dash-head { display: flex; flex-wrap: wrap; align-items: center; gap: 12px 16px; padding: 14px 18px; }
.titles { flex: 1 1 240px; min-width: 0; }
.titles h2 { font-size: var(--fs-lg); font-weight: 650; }
.meta { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 10px; margin-top: 4px; font-size: var(--fs-sm); color: var(--muted); }
.head-actions { display: flex; align-items: center; gap: 6px; }

.widgets { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--sp-4); }
.wide { grid-column: 1 / -1; }
.w { min-width: 0; display: flex; flex-direction: column; }
.w > :deep(*) { flex: 1; }
@media (max-width: 1100px) { .widgets { grid-template-columns: minmax(0, 1fr); } }
</style>
