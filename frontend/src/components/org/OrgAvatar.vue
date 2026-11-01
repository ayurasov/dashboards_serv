<script setup>
import { computed, ref, watch } from 'vue'
import { avatarTone, initials } from '@/domain/org'

/** Аватар сотрудника: фото (/api/org/people/{id}/avatar), без него или при ошибке — инициалы. */
const props = defineProps({
  person: { type: Object, default: null },
  name: { type: String, default: '' },
  size: { type: Number, default: 32 },
  ring: { type: Boolean, default: false },
})
const failed = ref(false)
watch(() => props.person?.id, () => { failed.value = false })

const label = computed(() => props.person?.full_name || props.name || '')
const src = computed(() => (props.person?.has_avatar && !failed.value ? `/api/org/people/${props.person.id}/avatar` : ''))
const style = computed(() => ({
  width: `${props.size}px`,
  height: `${props.size}px`,
  fontSize: `${Math.max(9, Math.round(props.size * 0.37))}px`,
  '--tone': `var(--chart-${avatarTone(label.value)})`,
}))
</script>

<template>
  <span class="org-avatar" :class="{ ring, muted: person && person.is_active === false }" :style="style" aria-hidden="true">
    <img v-if="src" :src="src" alt="" loading="lazy" decoding="async" @error="failed = true" />
    <template v-else>{{ initials(label) }}</template>
  </span>
</template>

<style scoped>
.org-avatar {
  flex: 0 0 auto; display: inline-grid; place-items: center; overflow: hidden; border-radius: 50%;
  font-weight: 650; letter-spacing: .01em; line-height: 1; user-select: none;
  background: color-mix(in srgb, var(--tone) 15%, var(--surface));
  color: color-mix(in srgb, var(--tone) 80%, var(--text));
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--tone) 20%, transparent);
}
.org-avatar.ring { box-shadow: 0 0 0 2px var(--surface), 0 0 0 3.5px color-mix(in srgb, var(--tone) 35%, transparent); }
.org-avatar img { width: 100%; height: 100%; object-fit: cover; }
.org-avatar.muted { filter: grayscale(1); opacity: .6; }
</style>
