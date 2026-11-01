<script setup>
import AppIcon from '@/components/ui/AppIcon.vue'
import AppModal from '@/components/ui/AppModal.vue'

/** Удаление пользователя с предложением отключить вместо удаления (история и доступ сохранятся). */
defineProps({
  user: { type: Object, required: true },
  busy: { type: Boolean, default: false },
  error: { type: String, default: '' },
})
const emit = defineEmits(['close', 'delete', 'disable'])
</script>

<template>
  <AppModal title="Удалить пользователя?" :subtitle="`${user.full_name} · ${user.username}`" :width="'min(480px, calc(100vw - 48px))'" @close="emit('close')">
    <p class="text">Учётная запись будет удалена без возможности восстановления. Записи журнала изменений сохранятся.</p>
    <p v-if="user.is_active" class="hint"><AppIcon name="info" :size="14" />Если сотрудник просто ушёл, лучше отключить его: вход будет запрещён, а карточка, доступ и место в структуре сохранятся.</p>
    <p v-if="error" class="error" role="alert"><AppIcon name="alert" :size="14" />{{ error }}</p>
    <template #footer>
      <button class="btn" type="button" @click="emit('close')">Отмена</button>
      <span class="spacer" />
      <button v-if="user.is_active" class="btn" type="button" :disabled="busy" @click="emit('disable')">Отключить</button>
      <button class="btn btn-primary danger" type="button" :disabled="busy" data-testid="delete-confirm" @click="emit('delete')">{{ busy ? 'Удаление…' : 'Удалить' }}</button>
    </template>
  </AppModal>
</template>

<style scoped>
.text { color: var(--text-2); }
.hint { display: flex; gap: 8px; align-items: flex-start; margin-top: 12px; padding: 10px 12px; border-radius: var(--radius); background: var(--surface-2); font-size: var(--fs-sm); color: var(--text-2); }
.hint :deep(svg) { flex: 0 0 auto; margin-top: 2px; color: var(--accent); }
.error { display: flex; align-items: center; gap: 6px; margin-top: 12px; font-size: var(--fs-sm); color: var(--light-red); }
.danger { background: var(--light-red); border-color: var(--light-red); }
.danger:hover:not(:disabled) { background: color-mix(in srgb, var(--light-red) 88%, #000); border-color: color-mix(in srgb, var(--light-red) 88%, #000); }
</style>
