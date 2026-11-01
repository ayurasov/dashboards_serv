<script setup>
import AppModal from './AppModal.vue'
import { confirmState, resolveConfirm } from '@/composables/useConfirm'
</script>

<template>
  <AppModal v-if="confirmState.open" :title="confirmState.title" :width="440" @close="resolveConfirm(false)">
    <p class="message">{{ confirmState.message }}</p>
    <template #footer>
      <button class="btn" type="button" @click="resolveConfirm(false)">Отмена</button>
      <button class="btn" :class="confirmState.danger ? 'btn-primary danger' : 'btn-primary'" type="button" @click="resolveConfirm(true)">
        {{ confirmState.confirmText }}
      </button>
    </template>
  </AppModal>
</template>

<style scoped>
.message { color: var(--text-2); white-space: pre-line; }
.danger { background: var(--light-red); border-color: var(--light-red); }
</style>
