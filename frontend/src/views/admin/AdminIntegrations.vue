<script setup>
import { computed, ref } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import PageTabs from '@/components/ui/PageTabs.vue'
import InboundKeys from '@/components/integrations/InboundKeys.vue'
import IntegrationCard from '@/components/integrations/IntegrationCard.vue'
import IntegrationEditor from '@/components/integrations/IntegrationEditor.vue'
import KindPicker from '@/components/integrations/KindPicker.vue'
import RunsJournal from '@/components/integrations/RunsJournal.vue'
import { integrationsApi } from '@/api/integrations'
import { useAsync } from '@/composables/useAsync'
import { useQueryState } from '@/composables/useQueryState'
import { useAuthStore } from '@/stores/auth'
import { kindIcon, sortIntegrations } from '@/domain/integrations'

/**
 * «Интеграции» (ADR-0011, администратор и integrations.manage): подключения к корпоративным системам
 * карточками — состояние, проверка, включение, действия «Запустить», расписание, журнал запусков;
 * «Подключить систему» — все виды, которые знает сервер, в порядке сервера (форма настроек строится по их
 * описанию); карточки — в том же порядке видов, внутри вида — по названию; ключи для входящих вызовов.
 * Вид «только администратор» (Confluence) остальным виден только для чтения.
 */
const auth = useAuthStore()
const { state: q } = useQueryState({ tab: 'connections' })
const TABS = [
  { key: 'connections', label: 'Подключения', icon: 'plug' },
  { key: 'keys', label: 'Ключи для входящих вызовов', short: 'Ключи', icon: 'key' },
]
const tab = computed({ get: () => (TABS.some((t) => t.key === q.tab) ? q.tab : 'connections'), set: (v) => { q.tab = v } })

const kinds = useAsync(() => integrationsApi.kinds(), { initial: [] })
const { data, loading, error, reload } = useAsync(() => integrationsApi.list())
const list = computed(() => data.value || [])
const kindOf = (key) => (kinds.data.value || []).find((k) => k.kind === key) || null
const stats = computed(() => ({
  total: list.value.length,
  enabled: list.value.filter((i) => i.enabled).length,
  errors: list.value.filter((i) => i.health === 'error').length,
}))

function replace(row) {
  data.value = list.value.map((i) => (i.id === row.id ? row : i))
}
function removed(row) {
  data.value = list.value.filter((i) => i.id !== row.id)
}

const picking = ref(false)
const editing = ref(null) // { kind, integration }
const journal = ref(null)
function pick(kind) {
  picking.value = false
  editing.value = { kind, integration: null }
}
function edit(integration) {
  const kind = kindOf(integration.kind) || integration.connector
  if (kind && integration.can_manage !== false) editing.value = { kind, integration }
}
function saved(row) {
  const exists = list.value.some((i) => i.id === row.id)
  data.value = sortIntegrations(exists ? list.value.map((i) => (i.id === row.id ? row : i)) : [...list.value, row], kinds.data.value || [])
  editing.value = null
}
</script>

<template>
  <div class="page integrations-page">
    <PageHeader title="Интеграции" description="Подключения к корпоративным системам: проверка, расписание, запуск и журнал; ключи для входящих вызовов">
      <router-link v-if="auth.inbox || auth.hasCapability('data.manage')" to="/inbox" class="btn btn-ghost"><AppIcon name="inbox" :size="15" />Входящие данные</router-link>
      <button v-if="tab === 'connections'" type="button" class="btn btn-primary" :disabled="kinds.loading.value && !kinds.data.value?.length" data-testid="integration-add" @click="picking = true">
        <AppIcon name="plus" :size="15" />Подключить систему
      </button>
    </PageHeader>

    <PageTabs v-model="tab" :tabs="TABS" label="Разделы интеграций" />

    <template v-if="tab === 'connections'">
      <div v-if="list.length" class="stats">
        <span><b class="num">{{ stats.total }}</b> подключений</span>
        <span><b class="num">{{ stats.enabled }}</b> включено</span>
        <span v-if="stats.errors" class="bad"><b class="num">{{ stats.errors }}</b> с ошибкой</span>
      </div>

      <div v-if="loading && !data" class="grid grid-2"><div class="skeleton" style="height: 280px" /><div class="skeleton" style="height: 280px" /></div>
      <EmptyState v-else-if="error && !data" class="card" icon="alert" title="Не удалось загрузить подключения" :text="error.message">
        <button class="btn btn-sm" type="button" @click="reload()">Повторить</button>
      </EmptyState>

      <section v-else-if="!list.length" class="card empty-card" data-testid="integrations-empty">
        <EmptyState icon="plug" title="Подключений пока нет" text="Подключите систему компании: структура и сотрудники из «По Делу», проекты «Пульса», показатели Jira и Bitrix24, публикация в Confluence, вложения писем Exchange, выгрузки 1С. Забранные данные попадают во «Входящие» и применяются по их правилам.">
          <button type="button" class="btn btn-primary" @click="picking = true"><AppIcon name="plus" :size="15" />Подключить систему</button>
        </EmptyState>
        <ul v-if="kinds.data.value?.length" class="kind-teaser" aria-label="Доступные системы">
          <li v-for="k in kinds.data.value" :key="k.kind"><AppIcon :name="kindIcon(k.kind)" :size="14" />{{ k.title }}</li>
        </ul>
      </section>

      <div v-else class="cards">
        <IntegrationCard v-for="i in list" :key="i.id" :integration="i" :kind="kindOf(i.kind)"
                         @edit="edit" @journal="journal = $event" @changed="replace" @removed="removed" />
      </div>
    </template>

    <InboundKeys v-else-if="tab === 'keys'" />

    <KindPicker v-if="picking" :kinds="kinds.data.value || []" :integrations="list" :is-admin="auth.isAdmin" @close="picking = false" @pick="pick" />
    <IntegrationEditor v-if="editing" :key="editing.integration?.id || `new-${editing.kind.kind}`" :kind="editing.kind" :integration="editing.integration" @close="editing = null" @saved="saved" />
    <RunsJournal v-if="journal" :integration="journal" :kind="kindOf(journal.kind)" @close="journal = null" />
  </div>
</template>

<style scoped>
.integrations-page { max-width: 1400px; }
.stats { display: flex; flex-wrap: wrap; gap: 6px 20px; font-size: var(--fs-sm); color: var(--muted); }
.stats b { color: var(--text); font-weight: 700; margin-right: 4px; }
.stats .bad, .stats .bad b { color: var(--light-red); }
.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 440px), 1fr)); gap: var(--sp-4); align-items: start; }
.empty-card { padding-bottom: 24px; }
.kind-teaser { list-style: none; margin: 0 auto; padding: 0 24px; display: flex; flex-wrap: wrap; justify-content: center; gap: 6px; max-width: 760px; }
.kind-teaser li { display: inline-flex; align-items: center; gap: 6px; height: 28px; padding: 0 11px; border-radius: 99px; background: var(--surface-3); font-size: var(--fs-sm); color: var(--text-2); }
</style>
