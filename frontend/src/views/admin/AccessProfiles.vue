<script setup>
import PageHeader from '@/components/ui/PageHeader.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
</script>

<template>
  <div class="page">
    <PageHeader title="Профили доступа" description="Шаблоны прав для уровней сотрудников" />
    <EmptyState icon="shield" title="Раздел в разработке" text="Появится в версии 0.2.0." />
  </div>
</template>
