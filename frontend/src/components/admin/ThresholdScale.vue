<script setup>
import { computed } from 'vue'
import { ruleZones } from '@/domain/admin'
import { LIGHT_LABELS } from '@/utils/lights'

/** Шкала правила светофора: три зоны по возрастанию значения и их границы. */
const props = defineProps({
  rule: { type: Object, required: true },
  unit: { type: String, default: '' },
})
const zones = computed(() => ruleZones(props.rule, props.unit))
</script>

<template>
  <div class="scale" :class="{ off: !rule.enabled, empty: !zones.length }"
       :title="zones.length ? zones.map((z) => `${LIGHT_LABELS[z.light]}: ${z.text}`).join('\n') : 'Границы не заданы'">
    <template v-if="zones.length">
      <div class="bar">
        <span v-for="z in zones" :key="z.light" :class="z.light" />
      </div>
      <div class="ticks">
        <span v-for="z in zones" :key="z.light" class="num">{{ z.text }}</span>
      </div>
    </template>
    <template v-else>
      <div class="bar"><span class="none" /></div>
      <div class="ticks"><span>Границы не заданы</span></div>
    </template>
  </div>
</template>

<style scoped>
.scale { display: flex; flex-direction: column; gap: 5px; min-width: 0; transition: opacity var(--t-fast); }
.bar { display: flex; gap: 2px; height: 6px; }
.bar span { flex: 1; border-radius: 3px; }
.bar .green { background: var(--light-green); }
.bar .yellow { background: var(--light-yellow); }
.bar .red { background: var(--light-red); }
.bar .none { background: repeating-linear-gradient(90deg, var(--border-strong) 0 6px, transparent 6px 10px); }
.ticks { display: flex; gap: 2px; font-size: 10.5px; color: var(--muted); }
.ticks span { flex: 1; min-width: 0; text-align: center; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.empty .ticks span { text-align: left; }
.off { opacity: .45; filter: grayscale(.85); }
</style>
