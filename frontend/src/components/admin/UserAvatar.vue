<script setup>
import { computed } from 'vue'
import { avatarTone, initials } from '@/domain/admin'

/** Аватар-инициалы; оттенок постоянный для логина (цвета серий палитры). */
const props = defineProps({
  name: { type: String, default: '' },
  seed: { type: String, default: '' },
  src: { type: String, default: '' },
  size: { type: Number, default: 34 },
  muted: { type: Boolean, default: false },
})
const style = computed(() => ({
  width: `${props.size}px`,
  height: `${props.size}px`,
  fontSize: `${Math.round(props.size * 0.36)}px`,
  '--tone': `var(--chart-${avatarTone(props.seed || props.name)})`,
}))
</script>

<template>
  <span class="avatar" :class="{ muted }" :style="style" aria-hidden="true">
    <img v-if="src" :src="src" alt="" />
    <template v-else>{{ initials(name) }}</template>
  </span>
</template>

<style scoped>
.avatar {
  flex: 0 0 auto; display: inline-grid; place-items: center; overflow: hidden; border-radius: 50%;
  font-weight: 650; letter-spacing: .01em; line-height: 1;
  background: color-mix(in srgb, var(--tone) 14%, var(--surface));
  color: color-mix(in srgb, var(--tone) 78%, var(--text));
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--tone) 18%, transparent);
}
.avatar img { width: 100%; height: 100%; object-fit: cover; }
.avatar.muted { filter: grayscale(1); opacity: .55; }
</style>
