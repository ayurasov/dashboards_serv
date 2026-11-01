import { createApp } from 'vue'
import { createPinia } from 'pinia'
import '@fontsource-variable/inter'
import '@/styles/tokens.css'
import '@/styles/base.css'
import App from '@/App.vue'
import router from '@/router'
import { configureClient } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import { useAppStore } from '@/stores/app'
import { usePaletteStore } from '@/stores/palette'

const app = createApp(App)
const pinia = createPinia()
app.use(pinia)

configureClient({
  unauthorized() {
    const auth = useAuthStore()
    auth.setUser(null)
    const current = router.currentRoute.value
    if (!current.meta.public) router.push({ name: 'login', query: { redirect: current.fullPath, expired: '1' } })
  },
  passwordChangeRequired() {
    router.push({ name: 'profile', query: { password: 'required' } })
  },
})

const appStore = useAppStore()
appStore.applyTheme()
matchMedia('(prefers-color-scheme: dark)').addEventListener?.('change', () => appStore.applyTheme())

app.use(router)
usePaletteStore().load()
app.mount('#app')
