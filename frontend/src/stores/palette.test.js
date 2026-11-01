import { describe, expect, it } from 'vitest'
import { applyPalette, FALLBACK } from './palette'

const prop = (name) => document.documentElement.style.getPropertyValue(name)

describe('applyPalette', () => {
  it('заполняет все семь цветов графиков, повторяя короткую палитру', () => {
    applyPalette({ charts: ['#111111', '#222222', '#333333'] })
    expect([1, 2, 3, 4, 5, 6, 7].map((i) => prop(`--chart-${i}`))).toEqual(
      ['#111111', '#222222', '#333333', '#111111', '#222222', '#333333', '#111111'])
  })

  it('применяет фирменные цвета и светофор, недостающее — из палитры по умолчанию', () => {
    applyPalette({ brand: { primary: '#123456' }, traffic_light: { red: '#ff0000' } })
    expect(prop('--brand')).toBe('#123456')
    expect(prop('--brand-muted')).toBe(FALLBACK.brand.muted)
    expect(prop('--light-red')).toBe('#ff0000')
    expect(prop('--light-green')).toBe(FALLBACK.traffic_light.green)
  })
})
