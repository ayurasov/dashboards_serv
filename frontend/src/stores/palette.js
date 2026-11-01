import { defineStore } from 'pinia'
import { api } from '@/api/client'

/** Палитра «Сдержанная» — до ответа сервера и если он недоступен. Совпадает с app/services/registry.py. */
export const FALLBACK = {
  traffic_light: { green: '#3f9f6b', yellow: '#d29a2f', red: '#d1495b', neutral: '#a3acb9' },
  charts: ['#c8302c', '#3f6fb5', '#3f9f6b', '#d29a2f', '#7a5ba6', '#2c9aa6', '#8a8f98'],
  brand: { primary: '#c8302c', muted: '#6b7280' },
}

function shade(hex, amount) {
  const n = parseInt(hex.slice(1).padEnd(6, '0'), 16)
  const ch = (v) => Math.max(0, Math.min(255, Math.round(v * (1 + amount))))
  const r = ch(n >> 16), g = ch((n >> 8) & 255), b = ch(n & 255)
  return `#${((r << 16) | (g << 8) | b).toString(16).padStart(6, '0')}`
}

export function applyPalette(colors) {
  const c = { ...FALLBACK, ...colors }
  const root = document.documentElement.style
  const tl = { ...FALLBACK.traffic_light, ...(c.traffic_light || {}) }
  root.setProperty('--light-green', tl.green)
  root.setProperty('--light-yellow', tl.yellow)
  root.setProperty('--light-red', tl.red)
  root.setProperty('--light-gray', tl.neutral)
  const charts = c.charts?.length ? c.charts : FALLBACK.charts
  charts.slice(0, 7).forEach((color, i) => root.setProperty(`--chart-${i + 1}`, color))
  const brand = c.brand?.primary || FALLBACK.brand.primary
  root.setProperty('--brand', brand)
  root.setProperty('--brand-hover', shade(brand, -0.12))
}

export const usePaletteStore = defineStore('palette', {
  state: () => ({ colors: FALLBACK, name: '' }),
  getters: {
    chartColors: (s) => (s.colors.charts?.length ? s.colors.charts : FALLBACK.charts),
    lightColors: (s) => ({ ...FALLBACK.traffic_light, ...(s.colors.traffic_light || {}) }),
  },
  actions: {
    async load() {
      try {
        const palette = await api.get('/palette/active', null, { silent: true })
        this.colors = palette.colors
        this.name = palette.name
      } catch {
        this.colors = FALLBACK
      }
      applyPalette(this.colors)
    },
    preview(colors) {
      applyPalette(colors)
    },
    reset() {
      applyPalette(this.colors)
    },
  },
})
