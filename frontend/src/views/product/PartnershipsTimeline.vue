<script setup>
import { computed } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import FilterBar from '@/components/ui/FilterBar.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import LightBadge from '@/components/ui/LightBadge.vue'
import { partnershipsApi } from '@/api/services'
import { useAsync } from '@/composables/useAsync'
import { useQueryState } from '@/composables/useQueryState'
import { formatNumber, plural } from '@/utils/format'
import { LIGHT_LABELS } from '@/utils/lights'
import { eventDate, eventKind, filterTimeline, groupTimeline, lightExplanation, orderStatuses } from '@/domain/partnerships'

const { state: f, reset, isDefault } = useQueryState({ almi_product: '', status: '', search: '' })
const { data, loading } = useAsync(() => partnershipsApi.timeline())

const all = computed(() => data.value || [])
const products = computed(() => [...new Set(all.value.map((r) => r.almi_product).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'ru')))
const statuses = computed(() => orderStatuses([...new Set(all.value.map((r) => r.status).filter(Boolean))]))
const events = computed(() => filterTimeline(all.value, f))
const years = computed(() => groupTimeline(events.value))
const eventsWord = (n) => plural(n, ['событие', 'события', 'событий'])
const summary = computed(() => (data.value ? `${formatNumber(events.value.length)} ${eventsWord(events.value.length)}` : ''))

function dayMonth(value) {
  const [y, m, d] = String(value).slice(0, 10).split('-').map(Number)
  return new Date(y, m - 1, d).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' })
}
function jump(year) {
  document.getElementById(`year-${year}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}
</script>

<template>
  <div class="page">
    <PageHeader title="Хронология" description="Сертификации и изменения партнёрств — от новых к старым">
      <router-link to="/product/registry" class="btn"><AppIcon name="list" :size="15" />Реестр</router-link>
    </PageHeader>

    <FilterBar :summary="summary" :resettable="!isDefault()" @reset="reset">
      <label class="search"><AppIcon name="search" :size="14" /><input v-model="f.search" type="search" placeholder="Партнёр, продукт, версия, комментарий" aria-label="Поиск" /></label>
      <label class="field"><span>Продукт АЛМИ</span>
        <select v-model="f.almi_product" class="select"><option value="">Все</option><option v-for="p in products" :key="p" :value="p">{{ p }}</option></select>
      </label>
      <label class="field"><span>Статус</span>
        <select v-model="f.status" class="select"><option value="">Все</option><option v-for="s in statuses" :key="s" :value="s">{{ s }}</option></select>
      </label>
    </FilterBar>

    <div v-if="loading && !data" class="card timeline-skel">
      <div v-for="i in 6" :key="i" class="skel-row"><div class="skeleton" style="width: 90px; height: 14px" /><div class="skeleton" style="flex: 1; height: 58px" /></div>
    </div>

    <EmptyState v-else-if="data && !all.length" icon="clock" title="Событий пока нет"
                text="В хронологию попадают партнёрства с датой сертификата или датой изменения. Укажите их в реестре." />

    <EmptyState v-else-if="data && !events.length" icon="search" title="Ничего не найдено" text="Измените условия поиска или сбросьте фильтры.">
      <button class="btn" type="button" @click="reset">Сбросить фильтры</button>
    </EmptyState>

    <div v-else-if="data" class="layout">
      <nav class="years-nav" aria-label="Годы">
        <span class="nav-title">Годы</span>
        <button v-for="y in years" :key="y.year" type="button" class="nav-item" @click="jump(y.year)">
          <span>{{ y.year }}</span><span class="num muted">{{ y.count }}</span>
        </button>
      </nav>

      <div class="timeline">
        <section v-for="y in years" :id="`year-${y.year}`" :key="y.year" class="year">
          <header class="year-head">
            <h2 class="num">{{ y.year }}</h2>
            <span class="muted">{{ formatNumber(y.count) }} {{ eventsWord(y.count) }}</span>
          </header>

          <div v-for="m in y.months" :key="m.key" class="month">
            <div class="month-label">
              <span>{{ m.label }}</span>
              <span class="num faint">{{ m.items.length }}</span>
            </div>
            <ol class="events">
              <li v-for="r in m.items" :key="r.id" class="event">
                <span class="node" :class="r.light" :title="lightExplanation(r)" />
                <div class="event-body">
                  <div class="event-top">
                    <time class="date" :datetime="eventDate(r)">{{ dayMonth(eventDate(r)) }}</time>
                    <span class="kind" :class="{ change: r.last_modified }">{{ eventKind(r) }}</span>
                    <span class="spacer" />
                    <span class="light-label" :title="lightExplanation(r)"><LightBadge :light="r.light" dot />{{ LIGHT_LABELS[r.light] }}</span>
                  </div>
                  <div class="event-title">
                    <router-link :to="{ path: '/product/registry', query: { search: r.partner } }" class="partner" title="Найти в реестре">{{ r.partner }}</router-link>
                    <span v-if="r.product" class="product">{{ r.product }}</span>
                  </div>
                  <div class="event-meta">
                    <span v-if="r.almi_product" class="almi">
                      <AppIcon name="layers" :size="12" />{{ r.almi_product }}<template v-if="r.almi_version && r.almi_version !== r.almi_product"><span class="sep">·</span>{{ r.almi_version }}</template>
                    </span>
                    <span class="badge" :class="`badge-${r.status_light || 'gray'}`">{{ r.status || 'Без статуса' }}</span>
                    <span v-if="r.direction" class="muted ellipsis direction">{{ r.direction }}</span>
                  </div>
                  <p v-if="r.comment" class="comment">{{ r.comment }}</p>
                </div>
              </li>
            </ol>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<style scoped>
.search { display: flex; align-items: center; gap: 8px; height: 32px; padding: 0 10px; border: 1px solid var(--border-strong); border-radius: var(--radius); color: var(--muted); min-width: 260px; flex: 0 1 320px; background: var(--surface); }
.search input { border: 0; outline: 0; background: transparent; width: 100%; color: var(--text); font-size: var(--fs-sm); }
.search:focus-within { border-color: var(--chart-2); box-shadow: 0 0 0 3px var(--focus); }

.timeline-skel { padding: 20px; display: flex; flex-direction: column; gap: 14px; }
.skel-row { display: flex; gap: 24px; align-items: center; }

.layout { display: grid; grid-template-columns: 132px minmax(0, 1fr); gap: var(--sp-6); align-items: start; }
.years-nav { position: sticky; top: calc(var(--topbar-h) + 20px); display: flex; flex-direction: column; gap: 2px; }
.nav-title { font-size: var(--fs-xs); text-transform: uppercase; letter-spacing: .05em; color: var(--muted); font-weight: 620; padding: 0 10px 6px; }
.nav-item { display: flex; justify-content: space-between; align-items: center; height: 30px; padding: 0 10px; border: 0; border-radius: var(--radius-sm); background: transparent; color: var(--text-2); font-size: var(--fs-sm); font-weight: 560; cursor: pointer; font-variant-numeric: tabular-nums; transition: background var(--t-fast); }
.nav-item:hover { background: var(--surface-3); color: var(--text); }
.nav-item .muted { font-size: var(--fs-xs); font-weight: 500; }

.timeline { display: flex; flex-direction: column; gap: var(--sp-8); min-width: 0; }
.year { scroll-margin-top: calc(var(--topbar-h) + 16px); }
.year-head { display: flex; align-items: baseline; gap: 12px; padding-bottom: 10px; margin-bottom: 4px; border-bottom: 1px solid var(--border); }
.year-head h2 { font-size: var(--fs-xl); font-weight: 680; letter-spacing: -0.02em; }
.year-head .muted { font-size: var(--fs-sm); }

.month { display: grid; grid-template-columns: 120px minmax(0, 1fr); gap: var(--sp-4); padding-top: var(--sp-4); }
.month-label { display: flex; align-items: baseline; gap: 8px; padding-top: 12px; font-size: var(--fs-sm); font-weight: 620; color: var(--text); position: sticky; top: calc(var(--topbar-h) + 8px); align-self: start; }
.month-label .faint { font-size: var(--fs-xs); font-weight: 500; }

.events { list-style: none; margin: 0; padding: 0 0 0 22px; position: relative; display: flex; flex-direction: column; gap: 8px; }
.events::before { content: ''; position: absolute; left: 5px; top: 18px; bottom: 18px; width: 2px; border-radius: 1px; background: var(--border); }
.event { position: relative; }
.node { position: absolute; left: -22px; top: 15px; width: 12px; height: 12px; border-radius: 50%; background: var(--light-gray); box-shadow: 0 0 0 3px var(--bg); cursor: help; }
.node.green { background: var(--light-green); }
.node.yellow { background: var(--light-yellow); }
.node.red { background: var(--light-red); }
.event-body { padding: 10px 14px 12px; border: 1px solid var(--border); border-radius: var(--radius); background: var(--surface); box-shadow: var(--shadow-sm); transition: border-color var(--t-fast), box-shadow var(--t-fast); }
.event-body:hover { border-color: var(--border-strong); box-shadow: var(--shadow); }
.event-top { display: flex; align-items: center; gap: 10px; font-size: var(--fs-xs); }
.date { font-weight: 620; color: var(--text-2); font-variant-numeric: tabular-nums; }
.kind { color: var(--muted); text-transform: uppercase; letter-spacing: .05em; font-weight: 600; font-size: 10.5px; }
.kind.change { color: var(--chart-2); }
.light-label { display: inline-flex; align-items: center; gap: 6px; color: var(--muted); cursor: help; }
.event-title { display: flex; flex-wrap: wrap; align-items: baseline; gap: 2px 10px; margin-top: 4px; }
.partner { font-weight: 620; color: var(--text); }
.partner:hover { color: var(--chart-2); }
.product { color: var(--text-2); }
.event-meta { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 12px; margin-top: 8px; font-size: var(--fs-sm); }
.almi { display: inline-flex; align-items: center; gap: 5px; color: var(--text-2); }
.almi :deep(svg) { color: var(--muted); }
.sep { color: var(--faint); margin: 0 1px; }
.direction { max-width: 360px; }
.comment { margin-top: 8px; padding-top: 8px; border-top: 1px dashed var(--border); font-size: var(--fs-sm); color: var(--text-2); white-space: pre-line; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }

@media (max-width: 1100px) {
  .layout { grid-template-columns: minmax(0, 1fr); }
  .years-nav { position: static; flex-direction: row; flex-wrap: wrap; }
  .nav-title { display: none; }
  .nav-item { gap: 8px; border: 1px solid var(--border); border-radius: var(--radius-pill); background: var(--surface); }
}
@media (max-width: 720px) {
  .month { grid-template-columns: minmax(0, 1fr); gap: 4px; }
  .month-label { position: static; padding-top: 0; }
}
</style>
