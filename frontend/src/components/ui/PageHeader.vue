<script setup>
import { formatRelative, formatDateTime } from '@/utils/format'

/** Заголовок страницы: название, пояснение, свежесть данных, действия справа. */
defineProps({
  title: { type: String, required: true },
  description: { type: String, default: '' },
  updatedAt: { type: [String, Date], default: null },
})
</script>

<template>
  <div class="page-header">
    <div class="titles">
      <h1>{{ title }}</h1>
      <p v-if="description || updatedAt" class="desc">
        <span v-if="description">{{ description }}</span>
        <span v-if="updatedAt" class="updated" :title="formatDateTime(updatedAt)">Данные обновлены {{ formatRelative(updatedAt) }}</span>
      </p>
    </div>
    <div v-if="$slots.default" class="page-actions">
      <slot />
    </div>
  </div>
</template>

<style scoped>
.page-header { display: flex; align-items: flex-end; gap: var(--sp-4); flex-wrap: wrap; }
.titles { flex: 1 1 320px; min-width: 0; }
h1 { font-size: var(--fs-xl); font-weight: 680; letter-spacing: -0.02em; line-height: 1.2; }
.desc { margin-top: 5px; display: flex; flex-wrap: wrap; gap: 4px 14px; font-size: var(--fs-sm); color: var(--muted); }
.updated::before { content: ''; display: inline-block; width: 6px; height: 6px; margin-right: 6px; border-radius: 50%; background: var(--light-green); vertical-align: 1px; }
.page-actions { display: flex; flex-wrap: wrap; align-items: center; gap: var(--sp-2); }
</style>
