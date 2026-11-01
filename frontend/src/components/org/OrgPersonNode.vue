<script setup>
import OrgAvatar from './OrgAvatar.vue'

/** Карточка сотрудника на схеме «Люди»: должность, подразделение, прямые подчинённые и вся ветка. */
defineProps({
  person: { type: Object, required: true },
  unitName: { type: String, default: '' },
  childCount: { type: Number, default: 0 },
  expanded: { type: Boolean, default: false },
  onPath: { type: Boolean, default: false },
  selected: { type: Boolean, default: false },
  me: { type: Boolean, default: false },
  compact: { type: Boolean, default: false },
})
const emit = defineEmits(['select', 'toggle'])
</script>

<template>
  <article class="person-node" :class="{ path: onPath, selected, compact }" tabindex="0" role="button" :aria-pressed="selected"
           :aria-label="`${person.full_name}: подробнее`" :data-person-id="person.id" @click="emit('select', person.id)"
           @keydown.enter.self.prevent="emit('select', person.id)" @keydown.space.self.prevent="emit('select', person.id)">
    <span v-if="me" class="me-badge">Вы</span>
    <div class="body">
      <OrgAvatar :person="person" :size="compact ? 30 : 40" />
      <div class="text">
        <strong>{{ person.full_name }}</strong>
        <small v-if="person.position" class="position">{{ person.position }}</small>
        <small v-if="unitName && !compact" class="unit">{{ unitName }}</small>
      </div>
    </div>
    <div v-if="person.report_count" class="counts">
      <span title="Прямые подчинённые"><b class="num">{{ person.report_count }}</b> прямых</span>
      <span v-if="person.branch_count > person.report_count" title="Вся ветка подчинения"><b class="num">{{ person.branch_count.toLocaleString('ru-RU') }}</b> в ветке</span>
    </div>
    <button v-if="childCount" type="button" class="toggle" :aria-expanded="expanded" @click.stop="emit('toggle', person.id)">
      {{ expanded ? 'Скрыть подчинённых' : `Подчинённые: ${childCount}` }}<i class="chev" aria-hidden="true" />
    </button>
  </article>
</template>

<style scoped>
.person-node {
  position: relative; width: 236px; display: flex; flex-direction: column; cursor: pointer;
  background: var(--surface); border: 1px solid var(--border); border-radius: 14px; box-shadow: var(--shadow-sm);
  transition: border-color var(--t-fast), box-shadow var(--t-fast);
}
.person-node:hover { box-shadow: var(--shadow); border-color: var(--border-strong); }
.person-node:focus-visible { outline: none; box-shadow: 0 0 0 3px var(--focus); }
.person-node.path { border-color: color-mix(in srgb, var(--accent) 45%, var(--border)); }
.person-node.selected { border-color: var(--accent); box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 22%, transparent), var(--shadow); }
.person-node.compact { width: 196px; }
.me-badge {
  position: absolute; top: -10px; right: 12px; height: 20px; padding: 0 9px; display: inline-flex; align-items: center;
  border-radius: var(--radius-pill); background: var(--text); color: var(--bg-elevated); font-size: 10.5px; font-weight: 650; box-shadow: var(--shadow-sm);
}
.body { display: flex; align-items: center; gap: 11px; padding: 13px 13px 10px; min-width: 0; }
.compact .body { padding: 10px 11px 8px; gap: 9px; }
.text { display: flex; flex-direction: column; min-width: 0; line-height: 1.3; }
.text strong { font-size: var(--fs-sm); font-weight: 640; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; overflow-wrap: anywhere; }
.position { margin-top: 1px; font-size: var(--fs-xs); color: var(--text-2); display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.unit { margin-top: 1px; font-size: var(--fs-xs); color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.counts { display: flex; flex-wrap: wrap; gap: 4px 10px; padding: 0 13px 11px; font-size: var(--fs-xs); color: var(--muted); }
.counts span { display: inline-flex; align-items: center; gap: 4px; }
.counts b { color: var(--text); font-weight: 680; }
.toggle {
  display: flex; align-items: center; justify-content: center; gap: 5px; margin-top: auto; height: 30px;
  border: 0; border-top: 1px solid var(--border); border-radius: 0 0 13px 13px; background: var(--surface-2);
  color: var(--text-2); font-size: var(--fs-xs); font-weight: 600; cursor: pointer;
}
.toggle:hover { background: var(--surface-3); color: var(--text); }
.toggle:focus-visible { outline: 2px solid var(--focus); outline-offset: -2px; }
.toggle[aria-expanded='true'] { color: var(--accent); }
.chev { width: 6px; height: 6px; margin: -3px 0 0 3px; border-right: 1.8px solid currentColor; border-bottom: 1.8px solid currentColor; transform: rotate(45deg); }
.toggle[aria-expanded='true'] .chev { margin-top: 3px; transform: rotate(-135deg); }
</style>
