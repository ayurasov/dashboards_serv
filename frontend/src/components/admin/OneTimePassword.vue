<script setup>
import { ref } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import AppModal from '@/components/ui/AppModal.vue'
import { toastError } from '@/composables/useToast'
import { writeClipboard } from '@/utils/clipboard'

/** Временный пароль: показывается один раз, с кнопкой копирования. */
const props = defineProps({
  password: { type: String, required: true },
  user: { type: Object, default: () => ({}) },
  title: { type: String, default: 'Временный пароль' },
})
const emit = defineEmits(['close'])
const copied = ref('')

async function copy(kind) {
  const text = kind === 'both' ? `Логин: ${props.user.username}\nПароль: ${props.password}` : props.password
  if (await writeClipboard(text)) {
    copied.value = kind
    setTimeout(() => { if (copied.value === kind) copied.value = '' }, 2000)
  } else {
    toastError('Не удалось скопировать — выделите пароль и скопируйте вручную')
  }
}
</script>

<template>
  <AppModal :title="title" :subtitle="user.full_name ? `${user.full_name} · ${user.username}` : user.username" :width="'min(480px, calc(100vw - 48px))'" @close="emit('close')">
    <div class="secret">
      <code class="value" data-testid="temporary-password">{{ password }}</code>
      <button class="btn btn-sm" type="button" @click="copy('password')">
        <AppIcon :name="copied === 'password' ? 'check' : 'copy'" :size="14" />{{ copied === 'password' ? 'Скопировано' : 'Копировать' }}
      </button>
    </div>
    <ul class="notes">
      <li><AppIcon name="eye-off" :size="15" />Пароль показывается один раз — после закрытия окна посмотреть его снова нельзя.</li>
      <li><AppIcon name="lock" :size="15" />При первом входе пользователь задаст собственный пароль.</li>
    </ul>
    <template #footer>
      <button class="btn btn-ghost" type="button" @click="copy('both')">
        <AppIcon :name="copied === 'both' ? 'check' : 'copy'" :size="14" />{{ copied === 'both' ? 'Скопировано' : 'Копировать логин и пароль' }}
      </button>
      <span class="spacer" />
      <button class="btn btn-primary" type="button" @click="emit('close')">Готово</button>
    </template>
  </AppModal>
</template>

<style scoped>
.secret { display: flex; align-items: center; gap: 10px; padding: 12px 12px 12px 16px; border-radius: 12px; background: var(--surface-2); border: 1px dashed var(--border-strong); }
.value { flex: 1; min-width: 0; font-family: var(--font-mono); font-size: 18px; font-weight: 600; letter-spacing: .06em; color: var(--text); user-select: all; word-break: break-all; }
.notes { list-style: none; margin: 14px 0 0; padding: 0; display: flex; flex-direction: column; gap: 8px; font-size: var(--fs-sm); color: var(--text-2); }
.notes li { display: flex; gap: 8px; align-items: flex-start; }
.notes :deep(svg) { margin-top: 2px; color: var(--muted); }
</style>
