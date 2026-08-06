import { createApp } from 'vue'
import { createPinia } from 'pinia'
import router from './router.js'
import App from './App.vue'
import { usePaletteStore } from './stores/palette.js'
import './style.css'

// The palette's *-l variants are derived per theme, so the theme has to be on the
// document before the palette is applied.
document.documentElement.setAttribute('data-theme', localStorage.getItem('hr_theme') || 'light')

const app = createApp(App)
app.use(createPinia())
app.use(router)

// Charts read their colours at first render, so the palette must be resolved before
// mount — otherwise every chart paints with fallback colours and repaints a moment
// later. An unreachable API must not white-screen the app, hence the deadline.
Promise.race([
  usePaletteStore().load(),
  new Promise(resolve => setTimeout(resolve, 1500)),
]).finally(() => app.mount('#app'))
