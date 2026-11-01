<script setup>
import { ref } from 'vue'
import AppModal from './AppModal.vue'
import AppIcon from './AppIcon.vue'
import SegmentedControl from './SegmentedControl.vue'
import { upload } from '@/api/client'
import { toastOk } from '@/composables/useToast'

/**
 * Загрузка файла с выбором режима: «Дополнить» (новые записи добавляются, совпадающие обновляются)
 * или «Заменить» (данные раздела заменяются содержимым файла).
 */
const props = defineProps({
  title: { type: String, required: true },
  endpoint: { type: String, required: true },
  accept: { type: String, default: '.xlsx,.csv' },
  description: { type: String, default: '' },
  mergeHint: { type: String, default: 'Новые записи добавятся, совпадающие обновятся' },
  replaceHint: { type: String, default: 'Все записи раздела будут заменены содержимым файла' },
})
const emit = defineEmits(['close', 'done'])

const file = ref(null)
const mode = ref('merge')
const busy = ref(false)
const error = ref('')
const result = ref(null)
const dragging = ref(false)

function pick(event) {
  file.value = event.target.files?.[0] || null
  error.value = ''
}
function drop(event) {
  dragging.value = false
  file.value = event.dataTransfer.files?.[0] || null
  error.value = ''
}

async function submit() {
  if (!file.value) return
  busy.value = true
  error.value = ''
  try {
    result.value = await upload(props.endpoint, file.value, { mode: mode.value })
    toastOk(result.value.message || 'Файл загружен')
    emit('done', result.value)
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <AppModal :title="title" :subtitle="description" :width="520" @close="emit('close')">
    <div v-if="!result" class="stack">
      <label class="drop" :class="{ dragging, has: file }" @dragover.prevent="dragging = true" @dragleave="dragging = false" @drop.prevent="drop">
        <input type="file" :accept="accept" class="sr-only" @change="pick" />
        <AppIcon name="upload" :size="22" />
        <strong v-if="file">{{ file.name }}</strong>
        <strong v-else>Выберите файл или перетащите его сюда</strong>
        <span class="muted">Поддерживаются: {{ accept.replaceAll(',', ', ') }}</span>
      </label>
      <div class="field">
        <span>Режим загрузки</span>
        <SegmentedControl v-model="mode" :options="[{ value: 'merge', label: 'Дополнить' }, { value: 'replace', label: 'Заменить' }]" />
        <span class="help">{{ mode === 'merge' ? mergeHint : replaceHint }}</span>
      </div>
      <p v-if="mode === 'replace'" class="warn"><AppIcon name="alert" :size="14" /> Текущие данные будут удалены. Действие попадёт в журнал изменений.</p>
      <p v-if="error" class="err">{{ error }}</p>
    </div>
    <div v-else class="result">
      <AppIcon name="check" :size="22" />
      <div>
        <strong>Загрузка завершена</strong>
        <ul>
          <li>Добавлено: <b>{{ result.rows_created }}</b></li>
          <li>Обновлено: <b>{{ result.rows_updated }}</b></li>
          <li v-if="result.rows_skipped">Пропущено строк: <b>{{ result.rows_skipped }}</b></li>
        </ul>
      </div>
    </div>
    <template #footer>
      <template v-if="!result">
        <button class="btn" type="button" @click="emit('close')">Отмена</button>
        <button class="btn btn-primary" type="button" :disabled="!file || busy" @click="submit">
          {{ busy ? 'Загрузка…' : 'Загрузить' }}
        </button>
      </template>
      <button v-else class="btn btn-primary" type="button" @click="emit('close')">Готово</button>
    </template>
  </AppModal>
</template>

<style scoped>
.drop { display: flex; flex-direction: column; align-items: center; gap: 6px; padding: 26px 16px; border: 1.5px dashed var(--border-strong); border-radius: 12px; cursor: pointer; text-align: center; color: var(--text-2); transition: all var(--t-fast); }
.drop:hover, .drop.dragging { border-color: var(--accent); background: color-mix(in srgb, var(--accent) 6%, transparent); }
.drop.has { border-style: solid; }
.drop strong { color: var(--text); font-size: var(--fs-base); }
.drop .muted { font-size: var(--fs-xs); }
.warn { display: flex; gap: 6px; align-items: center; font-size: var(--fs-sm); color: color-mix(in srgb, var(--light-yellow) 75%, var(--text)); }
.err { font-size: var(--fs-sm); color: var(--light-red); }
.result { display: flex; gap: 12px; color: var(--light-green); }
.result strong { color: var(--text); }
.result ul { margin: 6px 0 0; padding-left: 18px; color: var(--text-2); }
</style>
