<script setup>
import { computed } from 'vue'
import OrgAvatar from './OrgAvatar.vue'
import { PEOPLE_FORMS, UNIT_FORMS, countText } from '@/domain/org'
import { plural } from '@/utils/format'

/**
 * Карточка подразделения на оргсхеме: тип цветом, основной руководитель (и «+N»), штат уровня
 * и численность ветки, раскрытие вложенных, «Вы здесь».
 */
const props = defineProps({
  unit: { type: Object, required: true },
  kind: { type: Object, required: true },
  head: { type: Object, default: null },
  expanded: { type: Boolean, default: false },
  onPath: { type: Boolean, default: false },
  selected: { type: Boolean, default: false },
  mine: { type: Boolean, default: false },
  compact: { type: Boolean, default: false },
})
const emit = defineEmits(['select', 'toggle', 'select-person'])

const extraHeads = computed(() => Math.max(0, (props.unit.head_ids || []).length - (props.head ? 1 : 0)))
const children = computed(() => props.unit.child_count || 0)
// Как в «Подразделениях»: все, для кого уровень основной, вместе с руководителем
const staff = computed(() => props.unit.employee_count ?? 0)
</script>

<template>
  <article class="unit-card" :class="{ path: onPath, selected, compact, mine }" :style="{ '--kind': kind.color }"
           tabindex="0" role="button" :aria-pressed="selected" :aria-label="`${kind.label} «${unit.name}»: подробнее`"
           :data-unit-id="unit.id" @click="emit('select', unit.id)"
           @keydown.enter.self.prevent="emit('select', unit.id)" @keydown.space.self.prevent="emit('select', unit.id)">
    <span v-if="mine" class="mine-badge">Вы здесь</span>
    <header class="head">
      <span class="kind"><i />{{ kind.label }}</span>
      <h3 :title="unit.name">{{ unit.name }}</h3>
    </header>

    <button v-if="head" type="button" class="head-person" :title="`Руководитель: ${head.full_name}`"
            @click.stop="emit('select-person', head.id)">
      <OrgAvatar :person="head" :size="compact ? 24 : 32" />
      <span class="who">
        <span class="name">{{ head.full_name }}</span>
        <small v-if="!compact">{{ head.position || 'Руководитель' }}</small>
      </span>
      <span v-if="extraHeads" class="extra" :title="`Ещё ${extraHeads} ${plural(extraHeads, ['руководитель', 'руководителя', 'руководителей'])}`">+{{ extraHeads }}</span>
    </button>
    <p v-else class="no-head"><span class="ghost" aria-hidden="true" />Руководитель не назначен</p>

    <div class="stats">
      <span class="stat" title="Числятся в подразделении, включая руководителя">
        <b class="num">{{ staff.toLocaleString('ru-RU') }}</b> {{ plural(staff, PEOPLE_FORMS) }}
      </span>
      <span v-if="children" class="stat muted" title="Вместе с вложенными подразделениями">
        <b class="num">{{ (unit.branch_employee_count || 0).toLocaleString('ru-RU') }}</b> в ветке
      </span>
    </div>

    <button v-if="children" type="button" class="toggle" :aria-expanded="expanded"
            :aria-label="`${expanded ? 'Свернуть' : 'Показать'} ${countText(children, UNIT_FORMS)}`"
            @click.stop="emit('toggle', unit.id)">
      {{ countText(children, UNIT_FORMS) }}<i class="chev" aria-hidden="true" />
    </button>
  </article>
</template>

<style scoped>
.unit-card {
  position: relative; width: 252px; display: flex; flex-direction: column; text-align: left; cursor: pointer;
  background: var(--surface); border: 1px solid var(--border); border-radius: 14px; box-shadow: var(--shadow-sm);
  transition: border-color var(--t-fast), box-shadow var(--t-fast), transform var(--t-fast);
}
.unit-card::before { content: ''; position: absolute; left: 14px; right: 14px; top: -1px; height: 3px; border-radius: 0 0 3px 3px; background: var(--kind); opacity: .9; }
.unit-card:hover { box-shadow: var(--shadow); border-color: var(--border-strong); }
.unit-card:focus-visible { outline: none; box-shadow: 0 0 0 3px var(--focus); }
.unit-card.path { border-color: color-mix(in srgb, var(--accent) 45%, var(--border)); }
.unit-card.selected { border-color: var(--accent); box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 22%, transparent), var(--shadow); }
.unit-card.compact { width: 210px; }

.mine-badge {
  position: absolute; top: -10px; right: 12px; z-index: 2; height: 20px; padding: 0 8px; display: inline-flex; align-items: center;
  border-radius: var(--radius-pill); background: var(--text); color: var(--bg-elevated);
  font-size: 10.5px; font-weight: 650; letter-spacing: .02em; box-shadow: var(--shadow-sm);
}
.head { padding: 14px 14px 8px; }
.compact .head { padding: 12px 12px 6px; }
.kind { display: inline-flex; align-items: center; gap: 6px; font-size: var(--fs-xs); font-weight: 620; color: color-mix(in srgb, var(--kind) 80%, var(--text)); letter-spacing: .01em; }
.kind i { width: 7px; height: 7px; border-radius: 50%; background: var(--kind); }
h3 { margin-top: 3px; font-size: 14px; font-weight: 640; line-height: 1.3; letter-spacing: -0.005em; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; overflow-wrap: anywhere; }
.compact h3 { font-size: 13px; }

.head-person {
  display: flex; align-items: center; gap: 9px; margin: 0 8px; padding: 6px; min-width: 0; border: 0; border-radius: 10px;
  background: transparent; color: inherit; text-align: left; cursor: pointer; transition: background var(--t-fast);
}
.head-person:hover { background: var(--surface-3); }
.head-person:focus-visible { outline: 2px solid var(--focus); outline-offset: 0; }
.who { display: flex; flex-direction: column; min-width: 0; flex: 1; line-height: 1.3; }
.name { font-size: var(--fs-sm); font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.who small { font-size: var(--fs-xs); color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.extra { flex: 0 0 auto; height: 20px; padding: 0 7px; display: inline-grid; place-items: center; border-radius: var(--radius-pill); background: var(--surface-3); color: var(--text-2); font-size: var(--fs-xs); font-weight: 620; }
.no-head { display: flex; align-items: center; gap: 9px; margin: 0 8px; padding: 6px; font-size: var(--fs-sm); color: var(--muted); }
.ghost { width: 32px; height: 32px; flex: 0 0 32px; border-radius: 50%; border: 1.5px dashed var(--border-strong); }
.compact .ghost { width: 24px; height: 24px; flex-basis: 24px; }

.stats { display: flex; flex-wrap: wrap; gap: 4px 12px; padding: 8px 14px 12px; font-size: var(--fs-xs); color: var(--text-2); }
.compact .stats { padding: 6px 12px 10px; }
.stat b { font-size: var(--fs-sm); font-weight: 680; color: var(--text); }
.stat.muted, .stat.muted b { color: var(--muted); font-weight: 600; }

.toggle {
  display: flex; align-items: center; justify-content: center; gap: 5px; margin-top: auto; height: 32px; padding: 0 10px;
  border: 0; border-top: 1px solid var(--border); border-radius: 0 0 13px 13px; background: var(--surface-2);
  color: var(--text-2); font-size: var(--fs-xs); font-weight: 600; cursor: pointer; transition: background var(--t-fast), color var(--t-fast);
}
.toggle:hover { background: var(--surface-3); color: var(--text); }
.toggle:focus-visible { outline: 2px solid var(--focus); outline-offset: -2px; }
.toggle[aria-expanded='true'] { color: var(--accent); }
.compact .toggle { height: 28px; }
.chev { width: 6px; height: 6px; margin: -3px 0 0 3px; border-right: 1.8px solid currentColor; border-bottom: 1.8px solid currentColor; transform: rotate(45deg); transition: transform var(--t-fast); }
.toggle[aria-expanded='true'] .chev { margin-top: 3px; transform: rotate(-135deg); }
</style>
