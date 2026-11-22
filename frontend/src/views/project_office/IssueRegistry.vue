<script setup>
/** Реестр задач Jira (окно сырья): фильтры, пагинация, счётчик MR и связка «задача → код». */
import { computed, ref, watch } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import AppModal from '@/components/ui/AppModal.vue'
import { projectOfficeApi } from '@/api/services'
import { useAsync } from '@/composables/useAsync'
import { useQueryState } from '@/composables/useQueryState'
import { formatDate, formatNumber } from '@/utils/format'

const { state: q } = useQueryState({ project: '', status: '', search: '', open: false, page: 1 })
const filters = computed(() => ({
  project: q.project || undefined, status: q.status || undefined, search: q.search || undefined,
  open_only: q.open || undefined, page: q.page, page_size: 50,
}))
const { data, loading, error, reload } = useAsync(() => projectOfficeApi.issues(filters.value))
watch(() => ({ ...q }), () => { q.page = 1; reload() })

const openIssue = ref(null)
const mrs = useAsync(() => projectOfficeApi.issueMergeRequests(openIssue.value?.key), { immediate: false })
async function showMrs(issue) {
  openIssue.value = issue
  await mrs.reload()
}
const pages = computed(() => data.value ? Math.max(1, Math.ceil(data.value.total / data.value.page_size)) : 1)
const fmtDate = (v) => (v ? formatDate(v) : '—')
</script>
<template>
  <div class="page">
    <PageHeader title="Задачи Jira" description="Окно сырья 90 дней по обновлению; фильтры сохраняются в адресе" />

    <div class="card filter-bar">
      <div class="row-wrap">
        <input v-model="q.project" class="input input-sm" placeholder="Проект (ключ)" style="width: 120px" />
        <input v-model="q.status" class="input input-sm" placeholder="Статус" style="width: 160px" />
        <input v-model="q.search" class="input input-sm" placeholder="Поиск по ключу и теме" style="width: 260px" />
        <label class="check"><input v-model="q.open" type="checkbox" />Только открытые</label>
      </div>
    </div>

    <EmptyState v-if="loading && !data" icon="clock" title="Загрузка…" />
    <EmptyState v-else-if="error && !data" icon="alert" title="Не удалось загрузить" :text="error.message" />
    <section v-else-if="data?.items?.length" class="card">
      <div class="card-body">
        <table class="table table-compact">
          <thead>
            <tr>
              <th>Ключ</th><th>Тема</th><th>Статус</th><th>Исполнитель</th>
              <th class="num">Часы</th><th class="num">MR</th><th>Обновлена</th><th>Решена</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="i in data.items" :key="i.key" class="clickable" @click="showMrs(i)">
              <td class="nowrap">{{ i.key }}</td>
              <td>{{ i.summary }}</td>
              <td><span class="badge" :class="i.resolved ? 'badge-green' : 'badge-yellow'">{{ i.status }}</span></td>
              <td class="muted nowrap">{{ i.assignee_name || i.assignee_email || '—' }}</td>
              <td class="num">{{ formatNumber(i.timespent_hours) }}</td>
              <td class="num">
                <button v-if="i.merge_requests" class="btn btn-sm btn-ghost" type="button"
                        :title="`Мерж-реквесты задачи`" @click.stop="showMrs(i)">
                  <AppIcon name="code" :size="13" />{{ i.merge_requests }}
                </button>
                <span v-else class="muted">—</span>
              </td>
              <td class="muted nowrap">{{ fmtDate(i.updated) }}</td>
              <td class="muted nowrap">{{ fmtDate(i.resolved) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <footer class="card-body pagination">
        <span class="muted">{{ formatNumber(data.total) }} задач · страница {{ q.page }} из {{ pages }}</span>
        <span class="spacer" />
        <button class="btn btn-sm" :disabled="q.page <= 1" type="button" @click="q.page--">← Прошлые</button>
        <button class="btn btn-sm" :disabled="q.page >= pages" type="button" @click="q.page++">Следующие →</button>
      </footer>
    </section>
    <EmptyState v-else icon="search" title="Задач по фильтрам нет" text="Измените фильтры или расширьте окно сырья в подключении Jira" />

    <AppModal v-if="openIssue" :title="`${openIssue.key}: мерж-реквесты`" :subtitle="openIssue.summary" :width="640" @close="openIssue = null">
      <p v-if="mrs.loading.value && !mrs.data.value" class="muted">Загрузка…</p>
      <p v-else-if="!mrs.data.value?.length" class="muted">У задачи нет связанных мерж-реквестов в окне сырья GitLab.</p>
      <table v-else class="table table-compact">
        <thead><tr><th>Реквест</th><th>Состояние</th><th>Автор</th><th class="num">Ревью, ч</th><th>Слит</th></tr></thead>
        <tbody>
          <tr v-for="m in mrs.data.value" :key="m.id">
            <td>{{ m.title }}</td>
            <td><span class="badge" :class="m.state === 'merged' ? 'badge-green' : m.state === 'opened' ? 'badge-blue' : ''">{{ m.state }}</span></td>
            <td class="muted nowrap">{{ m.author_email }}</td>
            <td class="num">{{ m.review_hours ?? '—' }}</td>
            <td class="muted nowrap">{{ fmtDate(m.merged) }}</td>
          </tr>
        </tbody>
      </table>
      <template #footer>
        <button class="btn" type="button" @click="openIssue = null">Закрыть</button>
      </template>
    </AppModal>
  </div>
</template>

<style scoped>
.filter-bar { padding: 12px 16px; }
.pagination { display: flex; align-items: center; gap: 8px; }
</style>
