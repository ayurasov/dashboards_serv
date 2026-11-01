<script setup>
import AppIcon from './AppIcon.vue'

defineProps({
  icon: { type: String, default: 'info' },
  title: { type: String, default: 'Нет данных' },
  text: { type: String, default: '' },
  compact: { type: Boolean, default: false },
  // Уровень заголовка, если пустое состояние — содержимое всей страницы («Нет доступа», «Не найдено»)
  heading: { type: Number, default: 0 },
})
</script>

<template>
  <div class="empty" :class="{ compact }">
    <span class="icon"><AppIcon :name="icon" :size="compact ? 18 : 22" /></span>
    <component :is="heading ? `h${heading}` : 'strong'" class="title">{{ title }}</component>
    <p v-if="text">{{ text }}</p>
    <div v-if="$slots.default" class="actions"><slot /></div>
  </div>
</template>

<style scoped>
.empty { display: flex; flex-direction: column; align-items: center; text-align: center; gap: 6px; padding: 48px 24px; color: var(--muted); }
.empty.compact { padding: 24px 16px; }
.icon { width: 46px; height: 46px; display: grid; place-items: center; border-radius: 14px; background: var(--surface-3); color: var(--text-2); margin-bottom: 6px; }
.compact .icon { width: 36px; height: 36px; border-radius: 10px; }
.title { color: var(--text); font-size: var(--fs-md); font-weight: 620; margin: 0; }
p { max-width: 460px; font-size: var(--fs-sm); }
.actions { margin-top: 10px; display: flex; gap: 8px; }
</style>
