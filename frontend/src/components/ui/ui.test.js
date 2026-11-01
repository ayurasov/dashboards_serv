import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import KpiCard from './KpiCard.vue'
import SegmentedControl from './SegmentedControl.vue'
import LightBadge from './LightBadge.vue'
import EmptyState from './EmptyState.vue'

describe('KpiCard', () => {
  it('shows value with unit, light and a good delta for lower-is-better metric', () => {
    const w = mount(KpiCard, { props: { label: 'Текучесть', value: 2, unit: '%', light: 'green', delta: -1.87, direction: 'lower_is_better', target: 5 } })
    expect(w.classes()).toContain('l-green')
    expect(w.find('.value').text()).toBe('2%')
    expect(w.find('.delta').classes()).toContain('delta-good')
    expect(w.find('.delta').text()).toContain('−1,87 п.п.')
    expect(w.text()).toContain('цель 5%')
  })
  it('marks growth of a lower-is-better metric as bad and prefers percent delta', () => {
    const w = mount(KpiCard, { props: { label: 'В работе', value: 274, deltaPct: 12.5, direction: 'lower_is_better', deltaLabel: 'к прошлой неделе' } })
    expect(w.find('.delta').classes()).toContain('delta-bad')
    expect(w.find('.delta').text()).toContain('+12,5%')
    expect(w.text()).toContain('к прошлой неделе')
  })
  it('renders a dash for missing value and light label when no delta', () => {
    const w = mount(KpiCard, { props: { label: 'Пусто', value: null, light: 'red' } })
    expect(w.find('.value').text()).toBe('—')
    expect(w.text()).toContain('Критично')
  })
})

describe('SegmentedControl', () => {
  it('emits the chosen value and marks the active option', async () => {
    const w = mount(SegmentedControl, { props: { modelValue: 'quarter', options: [{ value: 'month', label: 'Месяцы' }, { value: 'quarter', label: 'Кварталы' }] } })
    expect(w.find('button.active').text()).toBe('Кварталы')
    await w.findAll('button')[0].trigger('click')
    expect(w.emitted('update:modelValue')[0]).toEqual(['month'])
  })
})

describe('LightBadge and EmptyState', () => {
  it('labels lights in Russian', () => {
    expect(mount(LightBadge, { props: { light: 'yellow' } }).text()).toBe('Внимание')
    expect(mount(LightBadge, { props: { light: 'red', dot: true } }).attributes('title')).toBe('Критично')
  })
  it('renders title, text and slot', () => {
    const w = mount(EmptyState, { props: { title: 'Нет данных', text: 'Добавьте месяц' }, slots: { default: '<button>Добавить</button>' } })
    expect(w.text()).toContain('Нет данных')
    expect(w.find('button').text()).toBe('Добавить')
  })
})
