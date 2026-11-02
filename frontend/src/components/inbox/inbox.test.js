import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import InboxPlan from './InboxPlan.vue'

/** План значений показателей со строкой «очистить» — в форме ответа /api/inbox/{id}. */
const PLAN = {
  summary: { rows: 2, create: 0, update: 1, cleared: 1, unchanged: 0, errors: 0 },
  rows: [
    { line: 1, department: 'PROJ', department_path: 'АЛМИ Партнер / Проектная служба', indicator: 'puls.progress', indicator_name: 'Средний прогресс проектов', period: '2026-11', clear: true, action: 'clear', before: { value: 50, target: null, comment: '' }, after: null, errors: [] },
    { line: 2, department: 'PROJ', department_path: 'АЛМИ Партнер / Проектная служба', indicator: 'puls.projects', indicator_name: 'Проекты в работе', period: '2026-11', clear: false, action: 'update', before: { value: 2, target: null, comment: '' }, after: { value: 0, target: null, comment: '' }, errors: [] },
  ],
  can_apply: true,
}

describe('InboxPlan — строка «очистить»', () => {
  it('действие «Очистить», «станет» — значение удалится, предупреждение и чип сводки', () => {
    const w = mount(InboxPlan, { props: { plan: PLAN } })
    const clearRow = w.findAll('tbody tr').find((tr) => tr.text().includes('Средний прогресс проектов'))
    expect(clearRow.classes()).toContain('clear')
    expect(clearRow.find('.badge').text()).toBe('Очистить')
    expect(clearRow.text()).toContain('значение удалится')
    expect(w.find('[data-testid=plan-clears]').text()).toContain('Очистить значения · 1')
    expect(w.text()).toContain('Очистится')
  })

  it('без строк «очистить» — без предупреждения', () => {
    const w = mount(InboxPlan, { props: { plan: { ...PLAN, summary: { ...PLAN.summary, cleared: 0 }, rows: [PLAN.rows[1]] } } })
    expect(w.find('[data-testid=plan-clears]').exists()).toBe(false)
    expect(w.text()).not.toContain('Очистится')
  })
})
