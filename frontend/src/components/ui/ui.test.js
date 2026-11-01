import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import KpiCard from './KpiCard.vue'
import SegmentedControl from './SegmentedControl.vue'
import LightBadge from './LightBadge.vue'
import EmptyState from './EmptyState.vue'
import AppModal from './AppModal.vue'
import ChartCard from './ChartCard.vue'
import { isTopModal, openModals, popModal, pushModal, trapFocus } from './modalStack'

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

describe('AppModal: доступность и вложенные окна', () => {
  const mountModal = (props = {}, slots = {}) => mount(AppModal, {
    props: { title: 'Новая цель', subtitle: 'Подзаголовок', ...props },
    slots: { default: '<input id="a" /><button id="b" type="button">B</button>', ...slots },
    attachTo: document.body,
  })
  const press = (key, init = {}) => document.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true, ...init }))

  it('окно названо заголовком и описано подзаголовком', () => {
    const w = mountModal()
    const dialog = document.querySelector('[role=dialog]')
    const title = document.getElementById(dialog.getAttribute('aria-labelledby'))
    expect(title.textContent).toBe('Новая цель')
    expect(document.getElementById(dialog.getAttribute('aria-describedby')).textContent).toBe('Подзаголовок')
    w.unmount()
  })

  it('Esc закрывает только верхнее окно; прокрутка страницы возвращается после закрытия всех окон', async () => {
    const lower = mountModal({ title: 'Форма' })
    const upper = mountModal({ title: 'Подтверждение' })
    expect(document.body.style.overflow).toBe('hidden')
    press('Escape')
    expect(upper.emitted('close')).toHaveLength(1)
    expect(lower.emitted('close')).toBeUndefined()
    upper.unmount()
    expect(document.body.style.overflow).toBe('hidden')
    press('Escape')
    expect(lower.emitted('close')).toHaveLength(1)
    lower.unmount()
    expect(document.body.style.overflow).toBe('')
  })

  it('фокус возвращается к элементу, который открыл окно', () => {
    const opener = document.createElement('button')
    document.body.appendChild(opener)
    opener.focus()
    const w = mountModal()
    expect(document.activeElement).not.toBe(opener)
    w.unmount()
    expect(document.activeElement).toBe(opener)
    opener.remove()
  })
})

describe('modalStack.trapFocus', () => {
  it('Tab с последнего элемента — на первый, Shift+Tab с первого — на последний', () => {
    const box = document.createElement('div')
    box.innerHTML = '<button id="x1">1</button><input id="x2" /><button id="x3" disabled>3</button><button id="x4">4</button>'
    document.body.appendChild(box)
    // jsdom не считает геометрию — элементы «видимы» для проверки
    for (const el of box.querySelectorAll('*')) el.getClientRects = () => [{}]
    const last = box.querySelector('#x4')
    const first = box.querySelector('#x1')
    last.focus()
    const tab = new KeyboardEvent('keydown', { key: 'Tab', cancelable: true })
    trapFocus(tab, box)
    expect(tab.defaultPrevented).toBe(true)
    expect(document.activeElement).toBe(first)
    const back = new KeyboardEvent('keydown', { key: 'Tab', shiftKey: true, cancelable: true })
    trapFocus(back, box)
    expect(document.activeElement).toBe(last)
    // В середине окна Tab работает как обычно
    box.querySelector('#x2').focus()
    const middle = new KeyboardEvent('keydown', { key: 'Tab', cancelable: true })
    trapFocus(middle, box)
    expect(middle.defaultPrevented).toBe(false)
    box.remove()
  })
  it('стопка окон: верхнее — последнее открытое', () => {
    const a = pushModal()
    const b = pushModal()
    expect(isTopModal(b)).toBe(true)
    expect(isTopModal(a)).toBe(false)
    popModal(b)
    expect(isTopModal(a)).toBe(true)
    popModal(a)
    expect(openModals()).toBe(0)
  })
})

describe('ChartCard', () => {
  it('во время первой загрузки — заглушка, а не «нет данных»', () => {
    const loading = mount(ChartCard, { props: { title: 'График', loading: true, empty: true }, slots: { default: '<div class="chart" />' } })
    expect(loading.find('.skeleton').exists()).toBe(true)
    expect(loading.text()).not.toContain('Нет данных')
    expect(loading.find('.chart').exists()).toBe(false)
    const empty = mount(ChartCard, { props: { title: 'График', empty: true } })
    expect(empty.text()).toContain('Нет данных за выбранный период')
    const ready = mount(ChartCard, { props: { title: 'График' }, slots: { default: '<div class="chart" />' } })
    expect(ready.find('.chart').exists()).toBe(true)
  })
})

describe('KpiCard: незаполненный показатель со светофором', () => {
  it('показывает «Не заполнено» как нарушение, светофор — «Нет данных»', async () => {
    const { default: KpiCard } = await import('./KpiCard.vue')
    const w = mount(KpiCard, { props: { label: 'Текучесть', value: null, unit: '%', light: 'gray', missing: true } })
    expect(w.classes()).toContain('missing')
    expect(w.find('.missing-flag').text()).toBe('Не заполнено')
    expect(w.find('.light').attributes('title')).toBe('Нет данных')
  })
})
