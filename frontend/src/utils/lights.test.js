import { describe, expect, it } from 'vitest'
import { countLights, evaluate, worst } from './lights'

const lower = { direction: 'lower_is_better', green_threshold: 5, yellow_threshold: 8, enabled: true }
const higher = { direction: 'higher_is_better', green_threshold: 90, yellow_threshold: 75, enabled: true }

describe('traffic light (same rules as the server)', () => {
  it('lower is better', () => {
    expect(evaluate(5, lower)).toBe('green')
    expect(evaluate(7, lower)).toBe('yellow')
    expect(evaluate(9, lower)).toBe('red')
  })
  it('higher is better', () => {
    expect(evaluate(95, higher)).toBe('green')
    expect(evaluate(80, higher)).toBe('yellow')
    expect(evaluate(50, higher)).toBe('red')
  })
  it('gray without value, rule or when disabled', () => {
    expect(evaluate(null, lower)).toBe('gray')
    expect(evaluate(1, null)).toBe('gray')
    expect(evaluate(1, { ...lower, enabled: false })).toBe('gray')
  })
  it('scales thresholds for sums over several weeks', () => {
    expect(evaluate(30, lower, 4)).toBe('yellow')
    expect(evaluate(40, lower, 4)).toBe('red')
    expect(evaluate(20, lower, 4)).toBe('green')
  })
  it('accepts legacy rule keys green/yellow', () => {
    expect(evaluate(3, { direction: 'lower_is_better', green: 5, yellow: 8, enabled: true })).toBe('green')
  })
  it('worst and counts', () => {
    expect(worst(['green', 'yellow', 'gray'])).toBe('yellow')
    expect(worst(['gray'])).toBe('gray')
    expect(countLights(['red', 'green', 'red', undefined])).toEqual({ green: 1, yellow: 0, red: 2, gray: 1 })
  })
})

describe('незаполненный показатель со светофором', () => {
  it('подпись — «Нет данных», а не цвет', async () => {
    const { lightLabel, MISSING_LABEL } = await import('./lights')
    expect(lightLabel('gray', true)).toBe(MISSING_LABEL)
    expect(lightLabel('gray')).toBe('Нет оценки')
    expect(lightLabel('red')).toBe('Критично')
  })
})
