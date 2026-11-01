<script setup>
import { ref } from 'vue'
import AppIcon from './AppIcon.vue'
import { commonApi } from '@/api/services'
import { useAuthStore } from '@/stores/auth'

/**
 * Кнопка PDF-отчёта: report — путь после /api/pdf/, params — текущие фильтры страницы.
 * Без права на выгрузку (ADR-0009) кнопки нет.
 */
const props = defineProps({
  report: { type: String, required: true },
  params: { type: Object, default: () => ({}) },
  label: { type: String, default: 'PDF' },
})
const auth = useAuthStore()
const busy = ref(false)
async function run() {
  busy.value = true
  try { await commonApi.pdf(props.report, props.params) } catch {} finally { busy.value = false }
}
</script>

<template>
  <button v-if="auth.canExport" class="btn" type="button" :disabled="busy" title="Сформировать PDF-отчёт с текущими фильтрами" @click="run">
    <AppIcon name="pdf" :size="15" />{{ busy ? 'Формируется…' : label }}
  </button>
</template>
