<script setup>
import { computed } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import { checkDetails, checkHint, checkState, checkWarnings } from '@/domain/integrations'
import { formatDateTime } from '@/utils/format'

/**
 * Итог проверки подключения: «Подключено» (зелёный), «Подключено с замечаниями» (жёлтый: подключение работает, но
 * не всё — замечания списком) или ошибка с текстом и подсказкой по коду (красный). Подробности — подписями вида
 * подключения (detail_labels): немного — строкой, больше — под «Подробности»; служебные ключи — в свёрнутых
 * «Технических подробностях».
 */
const props = defineProps({
  result: { type: Object, required: true },
  kind: { type: Object, default: null },
})
const state = computed(() => checkState(props.result))
const warnings = computed(() => checkWarnings(props.result))
const details = computed(() => checkDetails(props.result.details, props.kind))
// Коротко (до трёх подробностей без списков) — строкой под сообщением, иначе — свёрнуто
const inline = computed(() => details.value.main.length <= 3 && details.value.main.every((d) => !d.items && d.text.length <= 60))
const hint = computed(() => (props.result.ok ? '' : checkHint(props.result, props.kind)))
const message = computed(() => props.result.message || (props.result.ok ? 'Подключение работает' : 'Проверка не прошла'))
</script>

<template>
  <div class="check-result" :class="state.tone" role="status" :data-state="state.tone">
    <p class="msg"><AppIcon :name="state.icon" :size="15" /><span>{{ state.tone === 'warn' ? state.title : message }}</span></p>
    <p v-if="state.tone === 'warn'" class="sub" data-testid="check-message">{{ message }}</p>
    <p v-if="hint" class="hint">{{ hint }}</p>
    <ul v-if="warnings.length" class="warnings" data-testid="check-warnings" aria-label="Замечания">
      <li v-for="(w, n) in warnings" :key="n">{{ w }}</li>
    </ul>
    <dl v-if="details.main.length && inline" class="details row" data-testid="check-details">
      <div v-for="d in details.main" :key="d.key"><dt>{{ d.label }}</dt><dd>{{ d.text }}</dd></div>
    </dl>
    <details v-else-if="details.main.length" class="more" data-testid="check-details">
      <summary>Подробности · {{ details.main.length }}</summary>
      <dl class="details grid">
        <div v-for="d in details.main" :key="d.key" :data-detail="d.key">
          <dt>{{ d.label }}</dt>
          <dd v-if="d.items"><ul class="items"><li v-for="(line, n) in d.items" :key="n">{{ line }}</li></ul></dd>
          <dd v-else>{{ d.text }}</dd>
        </div>
      </dl>
    </details>
    <details v-if="details.technical.length" class="more tech" data-testid="check-technical">
      <summary>Технические подробности · {{ details.technical.length }}</summary>
      <dl class="details grid mono">
        <div v-for="d in details.technical" :key="d.key"><dt>{{ d.key }}</dt><dd>{{ d.value }}</dd></div>
      </dl>
    </details>
    <p v-if="result.checked_at" class="when">{{ result.draft ? 'Проверены несохранённые значения' : 'Проверены сохранённые настройки' }} · {{ formatDateTime(result.checked_at) }}</p>
  </div>
</template>

<style scoped>
.check-result { --tone: var(--light-green); display: flex; flex-direction: column; gap: 6px; padding: 10px 12px; border-radius: 10px; min-width: 0;
  border: 1px solid color-mix(in srgb, var(--tone) 35%, var(--border)); background: color-mix(in srgb, var(--tone) 7%, var(--surface)); }
.check-result.warn { --tone: var(--light-yellow); }
.check-result.bad { --tone: var(--light-red); }
.msg { display: flex; align-items: flex-start; gap: 8px; font-size: var(--fs-sm); font-weight: 600; color: color-mix(in srgb, var(--tone) 65%, var(--text)); overflow-wrap: anywhere; }
.warn .msg { color: color-mix(in srgb, var(--tone) 55%, var(--text)); }
.msg :deep(svg) { flex: 0 0 auto; margin-top: 2px; }
.sub { font-size: var(--fs-sm); color: var(--text); padding-left: 23px; overflow-wrap: anywhere; }
.hint { font-size: var(--fs-xs); color: var(--text-2); }
.warnings { margin: 0; padding: 0 0 0 23px; display: flex; flex-direction: column; gap: 3px; font-size: var(--fs-sm); color: var(--text); line-height: 1.45; }
.warnings li { list-style: none; position: relative; overflow-wrap: anywhere; }
.warnings li::before { content: ''; position: absolute; left: -13px; top: .6em; width: 5px; height: 5px; border-radius: 50%; background: color-mix(in srgb, var(--tone) 80%, var(--text)); }
.details { margin: 0; font-size: var(--fs-xs); }
.details.row { display: flex; flex-wrap: wrap; gap: 4px 18px; }
.details.row div { display: flex; gap: 6px; min-width: 0; }
.details.grid { display: grid; grid-template-columns: minmax(120px, max-content) minmax(0, 1fr); gap: 5px 14px; margin-top: 6px; }
.details.grid div { display: contents; }
.details dt { color: var(--muted); }
.details dd { margin: 0; color: var(--text); overflow-wrap: anywhere; min-width: 0; }
.details.mono dd { font-family: var(--font-mono); }
.items { margin: 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 4px; }
.items li { padding-left: 1em; text-indent: -1em; }
.when { font-size: var(--fs-xs); color: var(--muted); }
.more summary { font-size: var(--fs-xs); color: var(--text-2); cursor: pointer; }
.tech summary { color: var(--muted); }
@media (max-width: 560px) {
  .details.grid { grid-template-columns: minmax(0, 1fr); gap: 1px 0; }
  .details.grid dd { margin-bottom: 5px; }
  .sub, .warnings { padding-left: 0; }
  .warnings { padding-left: 13px; }
}
</style>
