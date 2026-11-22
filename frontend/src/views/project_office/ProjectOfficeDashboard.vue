<script setup>
/** Дашборд «Проектного офиса»: часы из Jira против плана и ёмкости календаря, задачи,
 *  активность разработки из GitLab. Служба этапа 3 (ADR-0012). */
import { computed } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import KpiCard from '@/components/ui/KpiCard.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import LightsLegend from '@/components/ui/LightsLegend.vue'
import { projectOfficeApi } from '@/api/services'
import { useAsync } from '@/composables/useAsync'
import { useQueryState } from '@/composables/useQueryState'
import { useAuthStore } from '@/stores/auth'
import ProjectPeoplePanel from './ProjectPeoplePanel.vue'
import ProjectPlansCard from './ProjectPlansCard.vue'

const auth = useAuthStore()
const { state: q } = useQueryState({ month: '' })
const { data, loading, error, reload } = useAsync(() => projectOfficeApi.dashboard(q.month || undefined))
const canManage = computed(() => auth.can('project_office', 'manager'))
const period = computed(() => {
  if (!data.value?.month) return ''
  const [year, month] = data.value.month.split('-')
  return new Date(Number(year), Number(month) - 1, 1).toLocaleDateString('ru-RU', { month: 'long', year: 'numeric' })
})
const planCoverage = computed(() => {
  const d = data.value
  if (!d || !d.plan_total) return null
  return Math.round((d.hours_total / d.plan_total) * 100)
})
const months = computed(() => {
  const now = new Date()
  const out = []
  for (let i = 0; i < 12; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1)
    out.push({ value: `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`,
               label: d.toLocaleDateString('ru-RU', { month: 'long', year: 'numeric' }) })
  }
  return out
})
</script>

<template>
  <div class="page">
    <PageHeader :title="`Проектный офис${period ? ` · ${period}` : ''}`"
                description="Часы и проекты из Jira, активность разработки из GitLab — против плана и ёмкости календаря">
      <label class="period-picker">
        <span>Месяц</span>
        <select v-model="q.month" class="select select-sm" data-testid="po-month">
          <option value="">Последний с данными</option>
          <option v-for="m in months" :key="m.value" :value="m.value">{{ m.label }}</option>
        </select>
      </label>
    </PageHeader>
    <LightsLegend />

    <EmptyState v-if="loading && !data" icon="clock" title="Загрузка…" text="Собираем часы и активность" />
    <EmptyState v-else-if="error && !data" icon="alert" title="Не удалось загрузить дашборд" :text="error.message">
      <button class="btn" type="button" @click="reload()"><AppIcon name="refresh" :size="14" />Повторить</button>
    </EmptyState>
    <EmptyState v-else-if="!data || (!data.hours_total && !data.activity.merge_requests && !data.issues.resolved)"
                icon="plug" title="Сырьья ещё нет"
                text="Подключите Jira и GitLab в «Интеграции» и запустите действия «Сырьё: …» — здесь появятся часы, задачи и активность." />

    <template v-else>
      <p v-if="!data.calendar_precise" class="warn muted">
        <AppIcon name="alert" :size="13" /> Производственный календарь справочника не покрывает месяц — ёмкость посчитана по общему правилу
      </p>

      <div class="grid grid-kpi">
        <KpiCard label="Часы за месяц" :value="data.hours_total" unit="ч"
                  :about="{ description: 'Сумма трудозатрат Jira за месяц, по всем сопоставленным и внешним авторам.', direction: 'neutral' }"
                  :series="[]" />
        <KpiCard label="План часов" :value="data.plan_total" unit="ч"
                  :about="{ description: 'Сумма планов «проект × месяц»; план задаёт руководитель проекта в таблице ниже.', direction: 'neutral' }" />
        <KpiCard v-if="planCoverage !== null" label="Выполнение плана" :value="planCoverage" unit="%"
                  :about="{ description: 'Факт к плану за месяц.', direction: 'higher_is_better' }" />
        <KpiCard label="Ёмкость календаря" :value="data.capacity_hours" unit="ч"
                  :about="{ description: 'Рабочие дни месяца по производственному календарю РФ: 8 часов, предпраздничные — 7.', direction: 'neutral' }" />
        <KpiCard label="Задач решено" :value="data.issues.resolved" unit="шт."
                  :about="{ description: 'Задачи Jira, решённые в этом месяце (сырьё за окно 90 дней).', direction: 'higher_is_better' }" />
        <KpiCard label="Lead time p50" :value="data.issues.lead_p50 ?? '—'" unit="дн"
                  :about="{ description: 'Медиана времени от создания до решения задачи (решённые в этом месяце).', direction: 'lower_is_better' }" />
        <KpiCard label="Коммиты (4 нед.)" :value="data.activity.commits" unit="шт."
                  :about="{ description: `Коммиты GitLab за 4 недели, авторов: ${data.activity.commit_authors}.`, direction: 'neutral' }" />
        <KpiCard label="Успешность CI" :value="data.activity.pipelines_ok_pct ?? '—'" unit="%"
                  :about="{ description: 'Доля зелёных пайплайнов за 4 недели.', direction: 'higher_is_better' }" />
      </div>

      <div class="grid grid-2">
        <ProjectPlansCard :month="data.month" :projects="data.projects" :can-manage="canManage" @changed="reload()" />
        <ProjectPeoplePanel :people="data.people" :matched="data.people_matched" :total="data.people_total" />
      </div>
    </template>
  </div>
</template>

<style scoped>
.period-picker { display: inline-flex; align-items: center; gap: 8px; font-size: var(--fs-sm); color: var(--muted); }
.period-picker .select { width: auto; }
.warn { display: flex; align-items: center; gap: 6px; font-size: var(--fs-sm); }
</style>
