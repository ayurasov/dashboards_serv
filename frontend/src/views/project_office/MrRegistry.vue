<script setup>
/** Реестр мерж-реквестов GitLab (окно сырья): состояние, авторы, время ревью, ключи Jira. */
import { computed, watch } from 'vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import { projectOfficeApi } from '@/api/services'
import { useAsync } from '@/composables/useAsync'
import { useQueryState } from '@/composables/useQueryState'
import { formatDate, formatNumber } from '@/utils/format'

const { state: q } = useQueryState({ state: '', author: '', jira: '', search: '', page: 1 })
const filters = computed(() => ({
  state: q.state || undefined, author: q.author || undefined, jira_key: q.jira || undefined,
  search: q.search || undefined, page: q.page, page_size: 50,
}))
const { data, loading, error, reload } = useAsync(() => projectOfficeApi.mergeRequests(filters.value))
watch(() => ({ ...q }), () => { q.page = 1; reload() })
const pages = computed(() => (data.value ? Math.max(1, Math.ceil(data.value.total / data.value.page_size)) : 1))
const fmtDate = (v) => (v ? formatDate(v) : '—')
</script>

<template>
  <div class="page">
    <PageHeader title="Мерж-реквесты GitLab" description="Связка «задача → код»: ключи Jira из названия и ветки; окно сырья — год" />

    <div class="card filter-bar">
      <div class="row-wrap">
        <select v-model="q.state" class="select select-sm" style="width: 140px">
          <option value="">Любое состояние</option>
          <option value="opened">Открыт</option>
          <option value="merged">Слит</option>
          <option value="closed">Закрыт</option>
        </select>
        <input v-model="q.author" class="input input-sm" placeholder="Автор (e-mail)" style="width: 220px" />
        <input v-model="q.jira" class="input input-sm" placeholder="Ключ Jira" style="width: 130px" />
        <input v-model="q.search" class="input input-sm" placeholder="Поиск по названию" style="width: 260px" />
      </div>
    </div>

    <EmptyState v-if="loading && !data" icon="clock" title="Загрузка…" />
    <EmptyState v-else-if="error && !data" icon="alert" title="Не удалось загрузить" :text="error.message" />
    <section v-else-if="data?.items?.length" class="card">
      <div class="card-body">
        <table class="table table-compact">
          <thead>
            <tr><th>Проект</th><th>Название</th><th>Состояние</th><th>Автор</th>
                <th>Jira</th><th class="num">Ревью, ч</th><th>Создан</th><th>Слит</th></tr>
          </thead>
          <tbody>
            <tr v-for="m in data.items" :key="m.id">
              <td class="nowrap muted">{{ m.project_path }}</td>
              <td>{{ m.title }}</td>
              <td><span class="badge" :class="m.state === 'merged' ? 'badge-green' : m.state === 'opened' ? 'badge-blue' : ''">{{ m.state }}</span></td>
              <td class="muted nowrap">{{ m.author_email || '—' }}</td>
              <td class="nowrap"><span v-for="k in m.jira_keys" :key="k" class="badge badge-gray jira-key">{{ k }}</span></td>
              <td class="num">{{ m.review_hours ?? '—' }}</td>
              <td class="muted nowrap">{{ fmtDate(m.created) }}</td>
              <td class="muted nowrap">{{ fmtDate(m.merged) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <footer class="card-body pagination">
        <span class="muted">{{ formatNumber(data.total) }} реквестов · страница {{ q.page }} из {{ pages }}</span>
        <span class="spacer" />
        <button class="btn btn-sm" :disabled="q.page <= 1" type="button" @click="q.page--">← Прошлые</button>
        <button class="btn btn-sm" :disabled="q.page >= pages" type="button" @click="q.page++">Следующие →</button>
      </footer>
    </section>
    <EmptyState v-else icon="search" title="Мерж-реквестов по фильтрам нет" text="Запустите действие «Сырьё: мерж-реквесты» подключения GitLab" />
  </div>
</template>

<style scoped>
.filter-bar { padding: 12px 16px; }
.pagination { display: flex; align-items: center; gap: 8px; }
.jira-key { margin-right: 4px; font-family: var(--font-mono); }
</style>
