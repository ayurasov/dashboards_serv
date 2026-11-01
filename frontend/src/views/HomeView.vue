<script setup>
import { computed } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import LightBadge from '@/components/ui/LightBadge.vue'
import { api } from '@/api/client'
import { useAsync } from '@/composables/useAsync'
import { useAuthStore, LEVEL_LABELS } from '@/stores/auth'
import { deltaTone, formatDateTime, formatDelta, formatNumber, formatRelative } from '@/utils/format'
import { LIGHT_LABELS } from '@/utils/lights'

/** Обзор: главное по каждой доступной службе — показатели, светофор, свежесть данных. */
const auth = useAuthStore()
const { data, loading, error, reload } = useAsync(() => api.get('/overview'))

const greeting = computed(() => {
  const h = new Date().getHours()
  const part = h < 5 ? 'Доброй ночи' : h < 12 ? 'Доброе утро' : h < 18 ? 'Добрый день' : 'Добрый вечер'
  // «Фамилия Имя Отчество» → имя; иначе — как записано
  const words = (auth.user?.full_name || '').split(/\s+/).filter(Boolean)
  const name = words.length === 3 ? words[1] : words.join(' ')
  return name ? `${part}, ${name}` : part
})
const active = computed(() => (data.value?.services || []).filter((s) => s.has_dashboard))
const waiting = computed(() => (data.value?.services || []).filter((s) => !s.has_dashboard))
const DATASETS = { tp_weekly: 'Недельный отчёт ТП', naumen: 'Заявки Naumen', partnerships: 'Партнёрства' }

function lightTotal(counts) {
  return counts ? counts.green + counts.yellow + counts.red : 0
}
</script>

<template>
  <div class="page">
    <PageHeader :title="greeting" description="Главное по службам, к которым у вас есть доступ" />

    <div v-if="loading && !data" class="cards">
      <div v-for="i in 3" :key="i" class="card skeleton" style="height: 260px" />
    </div>

    <EmptyState v-else-if="error && !data" icon="alert" title="Не удалось загрузить обзор" :text="error.message">
      <button class="btn" type="button" @click="reload()"><AppIcon name="refresh" :size="14" />Повторить</button>
    </EmptyState>

    <EmptyState v-else-if="data && !data.services.length" icon="lock" title="Нет доступа к службам"
                text="Администратор ещё не выдал вам доступ ни к одной службе. Обратитесь к нему — после этого здесь появятся показатели." />

    <div v-else class="cards">
      <article v-for="s in active" :key="s.key" class="card service">
        <header class="s-head">
          <span class="s-icon"><AppIcon :name="s.icon" :size="20" /></span>
          <div class="s-titles">
            <h2>{{ s.title }}</h2>
            <p>{{ s.period || 'Нет данных' }}</p>
          </div>
          <span v-if="!auth.isAdmin" class="badge">{{ LEVEL_LABELS[s.level] }}</span>
        </header>

        <div v-if="s.empty" class="s-empty muted">Данные ещё не загружены</div>
        <template v-else>
          <div v-if="lightTotal(s.light_counts)" class="lights" :title="`Светофор: ${s.light_counts.green} в норме, ${s.light_counts.yellow} требуют внимания, ${s.light_counts.red} критично`">
            <div class="bar">
              <span v-for="l in ['green', 'yellow', 'red']" v-show="s.light_counts[l]" :key="l" :class="l" :style="{ flex: s.light_counts[l] }" />
            </div>
            <div class="legend">
              <span v-for="l in ['green', 'yellow', 'red']" :key="l"><LightBadge :light="l" dot /> {{ LIGHT_LABELS[l] }} <b class="num">{{ s.light_counts[l] }}</b></span>
            </div>
          </div>
          <p v-if="s.missing?.length" class="missing" :title="s.missing.join(', ')">
            <AppIcon name="alert" :size="13" />Не заполнено со светофором: <b class="num">{{ s.missing.length }}</b> — критичное нарушение
          </p>
          <dl class="kpis">
            <div v-for="k in s.kpis" :key="k.label" class="kpi">
              <dt :title="k.label">{{ k.label }}</dt>
              <dd class="num">
                <LightBadge v-if="k.light && k.light !== 'gray'" :light="k.light" dot />
                {{ formatNumber(k.value, { unit: k.unit }) }}
                <small v-if="k.delta !== null && k.delta !== undefined" :class="`delta-${deltaTone(k.delta, k.direction)}`">{{ formatDelta(k.delta, k.unit) }}</small>
              </dd>
            </div>
          </dl>
        </template>

        <footer class="s-foot">
          <span v-if="s.data_updated_at" class="muted" :title="formatDateTime(s.data_updated_at)">Обновлено {{ formatRelative(s.data_updated_at) }}</span>
          <span class="spacer" />
          <router-link :to="s.route_prefix" class="btn btn-sm">Открыть дашборд <AppIcon name="chevron-right" :size="14" /></router-link>
        </footer>
      </article>
    </div>

    <section v-if="data?.recent_imports?.length" class="card">
      <header class="card-head"><h3>Последние загрузки данных</h3></header>
      <div class="card-body">
        <ul class="imports">
          <li v-for="i in data.recent_imports" :key="i.id">
            <AppIcon name="upload" :size="15" class="muted" />
            <span><b>{{ DATASETS[i.dataset] || i.dataset }}</b> · {{ i.filename }}</span>
            <span class="muted">добавлено {{ i.rows_created }}, обновлено {{ i.rows_updated }}</span>
            <span class="spacer" />
            <span class="muted">{{ i.username }} · {{ formatRelative(i.created_at) }}</span>
          </li>
        </ul>
      </div>
    </section>

    <section v-if="waiting.length" class="waiting">
      <h3 class="muted">Службы без дашборда</h3>
      <p class="muted">Доступ выдан, показатели появятся в следующих версиях:
        <span v-for="(s, i) in waiting" :key="s.key">{{ s.title }}{{ i < waiting.length - 1 ? ', ' : '' }}</span>
      </p>
    </section>
  </div>
</template>

<style scoped>
.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: var(--sp-4); }
.service { display: flex; flex-direction: column; padding: 20px; gap: 16px; transition: box-shadow var(--t), border-color var(--t); }
.service:hover { box-shadow: var(--shadow); border-color: var(--border-strong); }
.s-head { display: flex; align-items: flex-start; gap: 12px; }
.s-icon { width: 40px; height: 40px; display: grid; place-items: center; border-radius: 12px; background: var(--brand-soft); color: var(--brand); flex: 0 0 40px; }
.s-titles { flex: 1; min-width: 0; }
.s-titles h2 { font-size: var(--fs-md); }
.s-titles p { font-size: var(--fs-sm); color: var(--muted); margin-top: 2px; }
.s-empty { padding: 30px 0; text-align: center; }
.lights .bar { display: flex; height: 8px; border-radius: 99px; overflow: hidden; gap: 2px; background: var(--surface-3); }
.lights .bar span { min-width: 4px; }
.bar .green { background: var(--light-green); } .bar .yellow { background: var(--light-yellow); } .bar .red { background: var(--light-red); }
.legend { display: flex; gap: 14px; margin-top: 8px; font-size: var(--fs-xs); color: var(--muted); }
.legend span { display: inline-flex; align-items: center; gap: 5px; }
.legend b { color: var(--text); }
.kpis { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px 18px; margin: 0; }
.kpi { min-width: 0; display: flex; flex-direction: column; justify-content: space-between; }
.kpi dt { font-size: var(--fs-xs); color: var(--muted); line-height: 1.3; display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.kpi dd { margin: 3px 0 0; display: flex; align-items: center; flex-wrap: wrap; gap: 2px 6px; font-size: 19px; font-weight: 660; letter-spacing: -0.01em; }
.kpi dd small { font-size: var(--fs-xs); font-weight: 600; }
.s-foot { display: flex; align-items: center; gap: 8px; margin-top: auto; padding-top: 14px; border-top: 1px solid var(--border); font-size: var(--fs-sm); }
.s-foot > .muted { min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.imports { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; }
.imports li { display: flex; align-items: center; gap: 10px; padding: 9px 0; border-bottom: 1px solid var(--border); font-size: var(--fs-sm); flex-wrap: wrap; }
.imports li:last-child { border-bottom: 0; }
.waiting h3 { font-size: var(--fs-sm); font-weight: 600; margin-bottom: 4px; }
.waiting p { font-size: var(--fs-sm); }
.missing { display: flex; align-items: center; gap: 6px; margin: -4px 0 12px; font-size: var(--fs-xs); font-weight: 560; color: var(--light-red); }
</style>
