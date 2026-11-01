<script setup>
import AppIcon from '@/components/ui/AppIcon.vue'
import { reasonParts } from '@/domain/reports'
import { LIGHT_LABELS } from '@/utils/lights'

/**
 * «Почему такой статус»: показатели и подразделения, которые определили статус. Подразделение причины
 * открывается щелчком (canOpen — видно ли оно пользователю); причина за пределом детализации — с замком.
 */
const props = defineProps({
  items: { type: Array, default: () => [] },
  canOpen: { type: Function, default: () => true },
  dense: { type: Boolean, default: false },
})
const emit = defineEmits(['select'])
const openable = (item) => !!item.unit_id && props.canOpen(item.unit_id)
</script>

<template>
  <ol class="reasons" :class="{ dense }" data-testid="report-reasons">
    <li v-for="(item, i) in items" :key="`${item.indicator}:${item.unit_id}:${i}`">
      <component :is="openable(item) ? 'button' : 'div'" :type="openable(item) ? 'button' : undefined" class="reason" :class="`t-${item.status}`"
                 :title="openable(item) ? `Открыть «${item.unit_name}»` : undefined" @click="openable(item) && emit('select', item.unit_id)">
        <i class="r-dot" :title="LIGHT_LABELS[item.status]" aria-hidden="true" />
        <span class="r-text">
          <span class="sr-only">{{ LIGHT_LABELS[item.status] }}: </span>
          <b v-if="reasonParts(item).lead">{{ reasonParts(item).lead }}</b>{{ reasonParts(item).rest }}
          <span v-if="item.detail_locked" class="r-lock" title="Причина во вложенных подразделениях за пределом вашей детализации">
            <AppIcon name="lock" :size="11" :stroke="2.2" />
          </span>
        </span>
        <AppIcon v-if="openable(item)" class="r-go" name="chevron-right" :size="14" />
      </component>
    </li>
  </ol>
</template>

<style scoped>
.reasons { display: flex; flex-direction: column; gap: 2px; margin: 0; padding: 0; list-style: none; }
.reason { --tone: var(--light-gray); display: flex; align-items: flex-start; gap: 10px; width: 100%; padding: 8px 10px; border: 0; border-radius: 10px; background: transparent; color: var(--text-2); font: inherit; font-size: var(--fs-sm); line-height: 1.45; text-align: left; }
button.reason { cursor: pointer; transition: background var(--t-fast); }
button.reason:hover { background: var(--surface-3); }
button.reason:focus-visible { outline: 2px solid var(--focus); outline-offset: -2px; }
.t-red { --tone: var(--light-red); }
.t-yellow { --tone: var(--light-yellow); }
.t-green { --tone: var(--light-green); }
.r-dot { width: 8px; height: 8px; flex: 0 0 8px; margin-top: 6px; border-radius: 50%; background: var(--tone); box-shadow: 0 0 0 3px color-mix(in srgb, var(--tone) 18%, transparent); }
.r-text { flex: 1; min-width: 0; overflow-wrap: anywhere; }
.r-text b { color: var(--text); font-weight: 640; }
.r-lock { display: inline-grid; place-items: center; width: 18px; height: 18px; margin-left: 5px; vertical-align: -3px; border-radius: 50%; background: var(--surface-3); color: var(--muted); }
.r-go { flex: 0 0 auto; margin-top: 3px; color: var(--faint); transition: color var(--t-fast), transform var(--t-fast); }
button.reason:hover .r-go { color: var(--text-2); transform: translateX(2px); }
.dense .reason { padding: 5px 8px; font-size: var(--fs-xs); }
.dense .r-dot { margin-top: 5px; width: 7px; height: 7px; flex-basis: 7px; }
</style>
