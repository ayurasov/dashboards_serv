import { defineStore } from 'pinia'
import { api } from '../api/client.js'

const FALLBACK = {
  traffic_light: { green: '#5a9e68', yellow: '#c9974a', red: '#c97171', neutral: '#b8bec7' },
  charts: ['#5a9e68', '#6F8FBF', '#c9974a', '#8BBE9F', '#c97171', '#A9B2C3'],
  brand: { primary: '#c0392b', muted: '#6b6a65' },
}

/** Lighten a hex colour toward white — used for the *-l background variants. */
function tint(hex, amount = 0.82) {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex || '')
  if (!m) return hex
  const n = parseInt(m[1], 16)
  const mix = (c) => Math.round(c + (255 - c) * amount)
  const r = mix((n >> 16) & 255), g = mix((n >> 8) & 255), b = mix(n & 255)
  return '#' + [r, g, b].map(v => v.toString(16).padStart(2, '0')).join('')
}

export const usePaletteStore = defineStore('palette', {
  state: () => ({
    id: null,
    name: '',
    colors: structuredClone(FALLBACK),
    loaded: false,
  }),
  getters: {
    trafficLight: (s) => ({ ...FALLBACK.traffic_light, ...(s.colors.traffic_light || {}) }),
    chartColors: (s) => (s.colors.charts?.length ? s.colors.charts : FALLBACK.charts),
    brand: (s) => ({ ...FALLBACK.brand, ...(s.colors.brand || {}) }),
  },
  actions: {
    async load() {
      try {
        const p = await api.get('/palette')
        this.id = p.id
        this.name = p.name
        this.colors = { ...structuredClone(FALLBACK), ...p.colors }
      } catch {
        // Keep the fallback palette — the app must render even without the API.
        this.colors = structuredClone(FALLBACK)
      } finally {
        this.loaded = true
        this.apply()
      }
    },

    apply() {
      const tl = this.trafficLight
      const root = document.documentElement.style
      root.setProperty('--c-ok', tl.green)
      root.setProperty('--c-warn', tl.yellow)
      root.setProperty('--c-err', tl.red)
      root.setProperty('--c-faint', tl.neutral)
      const dark = document.documentElement.getAttribute('data-theme') === 'dark'
      const amt = dark ? -0.72 : 0.82
      root.setProperty('--c-ok-l', dark ? shade(tl.green) : tint(tl.green, amt))
      root.setProperty('--c-warn-l', dark ? shade(tl.yellow) : tint(tl.yellow, amt))
      root.setProperty('--c-err-l', dark ? shade(tl.red) : tint(tl.red, amt))
    },

    async save(id, payload) {
      const p = await api.put(`/palette/${id}`, payload)
      if (p.is_active) this._adopt(p)
      return p
    },

    async create(payload) {
      const p = await api.post('/palette', payload)
      if (p.is_active) this._adopt(p)
      return p
    },

    async activate(id) {
      const p = await api.put(`/palette/${id}/activate`, {})
      this._adopt(p)
      return p
    },

    _adopt(p) {
      this.id = p.id
      this.name = p.name
      this.colors = { ...structuredClone(FALLBACK), ...p.colors }
      this.apply()
    },
  },
})

/** Darken a hex colour toward black for dark-theme background variants. */
function shade(hex, amount = 0.72) {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex || '')
  if (!m) return hex
  const n = parseInt(m[1], 16)
  const mix = (c) => Math.round(c * (1 - amount))
  const r = mix((n >> 16) & 255), g = mix((n >> 8) & 255), b = mix(n & 255)
  return '#' + [r, g, b].map(v => v.toString(16).padStart(2, '0')).join('')
}
