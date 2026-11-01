<script setup>
import { computed, ref } from 'vue'
import SegmentedControl from '@/components/ui/SegmentedControl.vue'
import PlanChips from './PlanChips.vue'
import PlanUsersTable from './PlanUsersTable.vue'
import TransferBanner from './TransferBanner.vue'
import { PLAN_FILTERS, listChips } from '@/domain/org'

/** План загрузки списком или синхронизации с AD: сводка, новые подразделения, отключения, строки. */
const props = defineProps({
  plan: { type: Object, required: true },
  title: { type: String, default: 'Что изменится' },
  source: { type: String, default: '' },
})
const filter = ref(props.plan.summary.errors ? 'errors' : 'changes')
const chips = computed(() => listChips(props.plan.summary))
</script>

<template>
  <section class="card plan" data-testid="import-plan">
    <header class="plan-head">
      <div>
        <h2>{{ title }}</h2>
        <p v-if="source" class="muted">{{ source }}</p>
      </div>
      <PlanChips :chips="chips" />
    </header>

    <TransferBanner v-if="plan.rejected" tone="error" :title="plan.detail || 'Ничего не записано'" text="Строки с ошибками отмечены ниже — исправьте их и проверьте снова." class="inset" />
    <TransferBanner v-if="plan.cycles.length" tone="error" title="Получились бы циклы подчинения" class="inset">
      <ul class="err-list"><li v-for="c in plan.cycles" :key="c">{{ c }}</li></ul>
    </TransferBanner>

    <div v-if="plan.departments.length" class="plan-block">
      <h3>Будут созданы подразделения · {{ plan.departments.length }}</h3>
      <ul class="list-inline"><li v-for="d in plan.departments" :key="d.key">{{ d.path }}</li></ul>
    </div>
    <div v-if="plan.deactivate.length" class="plan-block">
      <h3>Будут отключены · {{ plan.deactivate.length }}</h3>
      <ul class="list-inline"><li v-for="u in plan.deactivate" :key="u.user_id">{{ u.name }}<template v-if="u.email"> · {{ u.email }}</template></li></ul>
    </div>

    <div class="plan-block">
      <div class="block-title">
        <h3>Сотрудники</h3>
        <SegmentedControl v-model="filter" :options="PLAN_FILTERS" size="sm" />
      </div>
      <PlanUsersTable :users="plan.users" :filter="filter" />
    </div>

    <footer class="plan-foot"><slot name="footer" /></footer>
  </section>
</template>

<style scoped src="./transfer.css"></style>
<style scoped>
.err-list { margin: 4px 0 0; padding-left: 18px; }
</style>
