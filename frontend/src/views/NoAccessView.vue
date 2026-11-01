<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import EmptyState from '@/components/ui/EmptyState.vue'
import { useAppStore } from '@/stores/app'

const route = useRoute()
const app = useAppStore()
const service = computed(() => app.service(route.query.service)?.title)
</script>

<template>
  <div class="page">
    <EmptyState :heading="1" icon="lock" title="Нет доступа"
                :text="service ? `У вас нет нужного уровня доступа к службе «${service}». Его выдаёт администратор.` : 'Эта страница доступна только администратору.'">
      <router-link to="/" class="btn btn-primary">На главную</router-link>
    </EmptyState>
  </div>
</template>
