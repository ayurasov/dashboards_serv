<script setup>
import { computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import AppShell from '@/components/layout/AppShell.vue'
import ToastHost from '@/components/ui/ToastHost.vue'
import ConfirmDialog from '@/components/ui/ConfirmDialog.vue'
import { useAuthStore } from '@/stores/auth'
import { useAppStore } from '@/stores/app'
import { usePaletteStore } from '@/stores/palette'

const route = useRoute()
const auth = useAuthStore()
const app = useAppStore()
const palette = usePaletteStore()

const bare = computed(() => route.meta.bare || !auth.isLoggedIn)

watch(() => auth.user?.id, async (id) => {
  if (!id) return
  await Promise.all([app.loadServices(), app.loadVersion(), palette.load()])
}, { immediate: true })
</script>

<template>
  <router-view v-if="bare" />
  <AppShell v-else>
    <router-view v-slot="{ Component, route: r }">
      <transition name="fade" mode="out-in">
        <component :is="Component" :key="r.path" />
      </transition>
    </router-view>
  </AppShell>
  <ToastHost />
  <ConfirmDialog />
</template>
