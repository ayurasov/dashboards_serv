<script setup>
import PageHeader from '@/components/ui/PageHeader.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
</script>

<template>
  <div class="page">
    <PageHeader title="Структура компании" description="Подразделения, руководители и сотрудники" />
    <EmptyState icon="org" title="Раздел в разработке" text="Появится в версии 0.2.0." />
  </div>
</template>
