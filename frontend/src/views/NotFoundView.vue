<script setup>
import EmptyState from '@/components/ui/EmptyState.vue'
</script>

<template>
  <div class="page">
    <EmptyState :heading="1" icon="search" title="Страница не найдена" text="Возможно, ссылка устарела или в адресе опечатка.">
      <router-link to="/" class="btn btn-primary">На главную</router-link>
    </EmptyState>
  </div>
</template>
