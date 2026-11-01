<script setup>
import PageHeader from '@/components/ui/PageHeader.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
</script>

<template>
  <div class="page">
    <PageHeader title="Импорт и экспорт" description="Перенос структуры и сотрудников, синхронизация с Active Directory" />
    <EmptyState icon="upload" title="Раздел в разработке" text="Появится в версии 0.2.0." />
  </div>
</template>
