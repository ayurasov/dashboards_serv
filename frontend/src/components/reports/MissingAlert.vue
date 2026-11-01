<script setup>
import AppIcon from '@/components/ui/AppIcon.vue'

/**
 * Пропуски данных — критичное нарушение полноты (как на дашборде службы персонала): красная плашка
 * с перечнем «Показатель — Подразделение»; подразделение открывается щелчком. hidden — пропуски
 * за пределом детализации (числом). Справа — действие (например, «Заполнить»).
 */
defineProps({
  items: { type: Array, default: () => [] },
  hidden: { type: String, default: '' },
  period: { type: String, default: '' },
  compact: { type: Boolean, default: false },
})
const emit = defineEmits(['select'])
</script>

<template>
  <div class="missing-alert" :class="{ compact }" role="alert" data-testid="report-missing">
    <AppIcon name="alert" :size="16" />
    <div class="ma-text">
      <strong>Не заполнены показатели{{ period ? ` за ${period.toLowerCase()}` : '' }}</strong> — критичное нарушение полноты:
      <template v-for="(v, i) in items" :key="`${v.unit_id}:${v.indicator}`">
        <button type="button" class="ma-item" :title="v.path || v.unit_name" @click="emit('select', v.unit_id)">
          <b>{{ v.indicator_name }}</b> — {{ v.unit_name }}</button><template v-if="i < items.length - 1">; </template>
      </template>
      <template v-if="hidden">{{ items.length ? '; ' : '' }}{{ hidden }}</template>.
      <span class="ma-hint">До заполнения они показываются как «Нет данных».</span>
    </div>
    <slot />
  </div>
</template>

<style scoped>
.missing-alert { display: flex; align-items: flex-start; gap: 10px; padding: 12px 14px; border-radius: var(--radius); border: 1px solid color-mix(in srgb, var(--light-red) 40%, var(--border)); background: color-mix(in srgb, var(--light-red) 8%, var(--surface)); color: var(--text); font-size: var(--fs-sm); line-height: 1.5; }
.missing-alert > svg { color: var(--light-red); flex: 0 0 auto; margin-top: 2px; }
.ma-text { flex: 1; min-width: 0; }
.ma-text > strong { color: var(--light-red); }
.ma-item { display: inline; padding: 0; border: 0; background: transparent; color: inherit; font: inherit; text-align: left; cursor: pointer; text-decoration: underline; text-decoration-color: color-mix(in srgb, var(--light-red) 45%, transparent); text-underline-offset: 3px; }
.ma-item:hover { color: var(--light-red); }
.ma-item b { font-weight: 640; }
.ma-hint { color: var(--muted); }
.compact { padding: 10px 12px; font-size: var(--fs-xs); }
.compact .ma-hint { display: none; }
.missing-alert :deep(.btn) { flex: 0 0 auto; }
</style>
