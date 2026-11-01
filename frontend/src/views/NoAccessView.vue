<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import EmptyState from '@/components/ui/EmptyState.vue'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'
import { CAPABILITIES } from '@/domain/access'

/** Нет доступа: причина приходит из охраны маршрутов (reason, service, page, capability). */
const route = useRoute()
const app = useAppStore()
const auth = useAuthStore()

const service = computed(() => app.service(route.query.service)?.title || '')
const page = computed(() => String(route.query.page || ''))
const what = computed(() => (page.value ? `Раздел «${page.value}»` : 'Этот раздел'))
const capability = computed(() => CAPABILITIES.find((c) => c.key === route.query.capability)?.label || '')

const text = computed(() => {
  switch (route.query.reason) {
    case 'records':
      return `${what.value} — исходные записи службы${service.value ? ` «${service.value}»` : ''}. Вам доступны дашборды и сводки; право на реестры и списки выдаёт администратор.`
    case 'personal':
      return `${what.value} содержит персональные данные — ФИО, должности, причины увольнения. Доступ к ним выдаёт администратор.`
    case 'financial':
      return `${what.value} содержит финансовые показатели. Доступ к ним выдаёт администратор.`
    case 'capability':
      return capability.value
        ? `Раздел доступен администратору и сотрудникам с полномочием «${capability.value}».`
        : 'Раздел доступен администратору и сотрудникам с особым полномочием.'
    case 'admin':
      return 'Эта страница доступна только администратору.'
    default:
      if (service.value) return `У вас нет нужного уровня доступа к службе «${service.value}». Его выдаёт администратор.`
      return 'Эта страница доступна только администратору.'
  }
})
</script>

<template>
  <div class="page">
    <EmptyState :heading="1" icon="lock" title="Нет доступа" :text="text">
      <router-link to="/" class="btn btn-primary">На главную</router-link>
      <router-link v-if="auth.isLoggedIn" to="/profile#my-access" class="btn">Мой доступ</router-link>
    </EmptyState>
  </div>
</template>
