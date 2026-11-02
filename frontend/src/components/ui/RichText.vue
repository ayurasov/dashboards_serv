<script setup>
import { computed, ref, useId } from 'vue'
import CodeBlock from './CodeBlock.vue'
import { isLongText, richBlocks, richPreview } from '@/domain/integrations'

/**
 * Длинное описание или подсказка с кодом (например, пример для 1С в описании коннектора): переносы строк
 * сохраняются, код в тройных обратных кавычках — моноширинным блоком; длинное сворачивается под
 * «Подробнее».
 */
const props = defineProps({
  text: { type: String, default: '' },
  limit: { type: Number, default: 220 },
  compact: { type: Boolean, default: false },
})
const open = ref(false)
const id = useId()
const long = computed(() => isLongText(props.text, props.limit))
const blocks = computed(() => richBlocks(props.text))
const preview = computed(() => richPreview(props.text, props.limit))
</script>

<template>
  <div v-if="text" class="rich" :class="{ compact }">
    <div v-if="!long || open" :id="id" class="full">
      <template v-for="(b, i) in blocks" :key="i">
        <CodeBlock v-if="b.type === 'code'" :code="b.value" class="code" />
        <p v-else class="txt">{{ b.value }}</p>
      </template>
    </div>
    <p v-else class="txt">{{ preview }}</p>
    <button v-if="long" type="button" class="more" :aria-expanded="open" :aria-controls="id" @click="open = !open">{{ open ? 'Свернуть' : 'Подробнее' }}</button>
  </div>
</template>

<style scoped>
.rich { display: flex; flex-direction: column; align-items: flex-start; gap: 6px; min-width: 0; font-size: var(--fs-sm); color: var(--text-2); line-height: 1.5; }
.rich.compact { gap: 3px; font-size: var(--fs-xs); color: var(--muted); line-height: 1.4; }
.full { display: flex; flex-direction: column; gap: 8px; min-width: 0; max-width: 100%; align-self: stretch; }
.compact .full { gap: 4px; }
.txt { white-space: pre-wrap; overflow-wrap: anywhere; margin: 0; }
.code { width: 100%; }
.more { padding: 0; border: 0; background: transparent; color: var(--accent); font-size: inherit; font-weight: 560; cursor: pointer; }
.more:hover { text-decoration: underline; }
</style>
