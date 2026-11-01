<script setup>
import PageHeader from '@/components/ui/PageHeader.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
</script>

<template>
  <div class="page">
    <PageHeader title="Вход по домену" description="Вход по учётной записи домена (LDAP) и синхронизация с Active Directory" />
    <EmptyState icon="key" title="Раздел в разработке" text="Появится в версии 0.2.0." />
  </div>
</template>
