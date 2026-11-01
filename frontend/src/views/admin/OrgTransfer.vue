<script setup>
import { computed } from 'vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import OrgIcon from '@/components/org/OrgIcon.vue'
import AdSync from '@/components/transfer/AdSync.vue'
import EmployeesTransfer from '@/components/transfer/EmployeesTransfer.vue'
import ListImport from '@/components/transfer/ListImport.vue'
import StructureTransfer from '@/components/transfer/StructureTransfer.vue'
import { useQueryState } from '@/composables/useQueryState'

/**
 * Импорт и экспорт структуры (ADR-0007): перенос структуры и сотрудников между системами,
 * быстрая загрузка списком и синхронизация с Active Directory. Везде сначала «Проверить» —
 * план без записи, затем «Применить» одной транзакцией; при ошибках ничего не записывается.
 */
const TABS = [
  { key: 'structure', label: 'Структура', short: 'Структура', icon: 'org', component: StructureTransfer },
  { key: 'employees', label: 'Сотрудники', short: 'Сотрудники', icon: 'users', component: EmployeesTransfer },
  { key: 'list', label: 'Быстрая загрузка списком', short: 'Списком', icon: 'list', component: ListImport },
  { key: 'ad', label: 'Active Directory', short: 'AD', icon: 'link', component: AdSync },
]
const { state } = useQueryState({ tab: 'structure' })
const current = computed(() => TABS.find((t) => t.key === state.tab) || TABS[0])
</script>

<template>
  <div class="page transfer-page">
    <PageHeader title="Импорт и экспорт" description="Перенос структуры и сотрудников, загрузка списком, синхронизация с Active Directory">
      <router-link to="/org" class="btn btn-ghost"><OrgIcon name="org" :size="15" />Структура компании</router-link>
      <router-link to="/admin/departments" class="btn btn-ghost"><OrgIcon name="building" :size="15" />Подразделения</router-link>
    </PageHeader>

    <nav class="tabs" role="tablist" aria-label="Что переносить">
      <button v-for="t in TABS" :key="t.key" type="button" role="tab" class="tab" :class="{ active: current.key === t.key }"
              :aria-selected="current.key === t.key" :data-testid="`transfer-tab-${t.key}`" @click="state.tab = t.key">
        <OrgIcon :name="t.icon" :size="15" /><span class="full">{{ t.label }}</span><span class="short">{{ t.short }}</span>
      </button>
    </nav>

    <KeepAlive>
      <component :is="current.component" :key="current.key" />
    </KeepAlive>
  </div>
</template>

<style scoped>
.transfer-page { max-width: 1240px; }
.transfer-page :deep(.page-actions .btn-ghost) { color: var(--text-2); }
.tabs { display: flex; gap: 2px; border-bottom: 1px solid var(--border); overflow-x: auto; scrollbar-width: none; }
.tab {
  position: relative; display: inline-flex; align-items: center; gap: 8px; height: 40px; padding: 0 14px; border: 0; background: transparent;
  color: var(--text-2); font-size: var(--fs-base); font-weight: 560; cursor: pointer; white-space: nowrap; transition: color var(--t-fast);
}
.tab:hover { color: var(--text); }
.tab.active { color: var(--text); font-weight: 640; }
.tab.active::after { content: ''; position: absolute; left: 10px; right: 10px; bottom: -1px; height: 2px; border-radius: 2px; background: var(--brand); }
.tab:focus-visible { outline: 2px solid var(--focus); outline-offset: -2px; border-radius: 8px; }
.short { display: none; }
@media (max-width: 640px) {
  .tab { padding: 0 10px; gap: 6px; }
  .tab .full { display: none; }
  .tab .short { display: inline; }
  .transfer-page :deep(.page-actions) { display: none; }
}
</style>
