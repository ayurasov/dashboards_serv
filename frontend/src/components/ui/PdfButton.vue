<script setup>
import { ref } from 'vue'
import AppIcon from './AppIcon.vue'
import { commonApi } from '@/api/services'

/** Кнопка PDF-отчёта: report — путь после /api/pdf/, params — текущие фильтры страницы. */
const props = defineProps({
  report: { type: String, required: true },
  params: { type: Object, default: () => ({}) },
  label: { type: String, default: 'PDF' },
})
const busy = ref(false)
async function run() {
  busy.value = true
  try { await commonApi.pdf(props.report, props.params) } catch {} finally { busy.value = false }
}
</script>

<template>
  <button class="btn" type="button" :disabled="busy" title="Сформировать PDF-отчёт с текущими фильтрами" @click="run">
    <AppIcon name="pdf" :size="15" />{{ busy ? 'Формируется…' : label }}
  </button>
</template>
