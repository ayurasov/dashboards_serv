<script setup>
import { computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import AppSidebar from './AppSidebar.vue'
import AppTopbar from './AppTopbar.vue'
import ReleaseNotesModal from '@/components/ReleaseNotesModal.vue'
import { useAppStore } from '@/stores/app'

const app = useAppStore()
const route = useRoute()
const width = computed(() => (app.sidebarCollapsed ? 'var(--sidebar-w-collapsed)' : 'var(--sidebar-w)'))
watch(() => route.fullPath, () => { app.mobileNavOpen = false })
</script>

<template>
  <div class="shell" :style="{ '--sb': width }">
    <AppSidebar />
    <div v-if="app.mobileNavOpen" class="scrim" @click="app.mobileNavOpen = false" />
    <div class="main">
      <AppTopbar />
      <main class="content">
        <slot />
      </main>
    </div>
    <ReleaseNotesModal v-if="app.releaseNotesOpen" @close="app.releaseNotesOpen = false" />
  </div>
</template>

<style scoped>
.shell { min-height: 100vh; }
.main { margin-left: var(--sb); min-height: 100vh; display: flex; flex-direction: column; transition: margin-left var(--t); }
.content { flex: 1; padding: var(--sp-6) var(--sp-8) var(--sp-10); }
.scrim { position: fixed; inset: 0; z-index: 40; background: var(--overlay); }
@media (max-width: 960px) {
  .main { margin-left: 0; }
  .content { padding: var(--sp-4) var(--sp-4) var(--sp-8); }
}
</style>
