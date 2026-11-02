<script setup>
import { computed } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import { checkDetails, checkHint } from '@/domain/integrations'
import { formatDateTime } from '@/utils/format'

/** Итог проверки подключения: успех или ошибка с текстом, подсказка по коду, подробности (версия и т. п.). */
const props = defineProps({
  result: { type: Object, required: true },
  kind: { type: Object, default: null },
})
const details = computed(() => checkDetails(props.result.details))
const hint = computed(() => (props.result.ok ? '' : checkHint(props.result, props.kind)))
</script>

<template>
  <div class="check-result" :class="result.ok ? 'ok' : 'bad'" role="status">
    <p class="msg"><AppIcon :name="result.ok ? 'check' : 'alert'" :size="15" /><span>{{ result.message || (result.ok ? 'Подключение работает' : 'Проверка не прошла') }}</span></p>
    <p v-if="hint" class="hint">{{ hint }}</p>
    <dl v-if="details.length && details.length <= 3" class="details">
      <div v-for="d in details" :key="d.key"><dt>{{ d.key }}</dt><dd>{{ d.value }}</dd></div>
    </dl>
    <details v-else-if="details.length" class="more">
      <summary>Подробности · {{ details.length }}</summary>
      <dl class="details">
        <div v-for="d in details" :key="d.key"><dt>{{ d.key }}</dt><dd>{{ d.value }}</dd></div>
      </dl>
    </details>
    <p v-if="result.checked_at" class="when">{{ result.draft ? 'Проверены несохранённые значения' : 'Проверены сохранённые настройки' }} · {{ formatDateTime(result.checked_at) }}</p>
  </div>
</template>

<style scoped>
.check-result { --tone: var(--light-green); display: flex; flex-direction: column; gap: 6px; padding: 10px 12px; border-radius: 10px;
  border: 1px solid color-mix(in srgb, var(--tone) 35%, var(--border)); background: color-mix(in srgb, var(--tone) 7%, var(--surface)); }
.check-result.bad { --tone: var(--light-red); }
.msg { display: flex; align-items: flex-start; gap: 8px; font-size: var(--fs-sm); font-weight: 600; color: color-mix(in srgb, var(--tone) 65%, var(--text)); overflow-wrap: anywhere; }
.msg :deep(svg) { flex: 0 0 auto; margin-top: 2px; }
.hint { font-size: var(--fs-xs); color: var(--text-2); }
.details { margin: 0; display: flex; flex-wrap: wrap; gap: 4px 18px; font-size: var(--fs-xs); }
.details div { display: flex; gap: 6px; min-width: 0; }
.details dt { color: var(--muted); }
.details dd { margin: 0; color: var(--text); font-family: var(--font-mono); overflow-wrap: anywhere; }
.when { font-size: var(--fs-xs); color: var(--muted); }
.more summary { font-size: var(--fs-xs); color: var(--text-2); cursor: pointer; }
.more .details { margin-top: 6px; }
</style>
