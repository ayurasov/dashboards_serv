<script setup>
import { computed, ref, watch } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import AppModal from '@/components/ui/AppModal.vue'
import TransferFile from '@/components/transfer/TransferFile.vue'
import { inboxApi } from '@/api/inbox'
import { optionValues } from '@/domain/inbox'

/**
 * «Загрузить файл»: файл, набор (распознать по имени и содержимому или выбрать), параметры набора,
 * «применить сразу, если без ошибок». Загруженный файл становится элементом входящих — окно
 * отдаёт его странице, она открывает элемент с планом.
 */
const props = defineProps({
  datasets: { type: Array, default: () => [] },
  maxMb: { type: Number, default: 20 },
})
const emit = defineEmits(['close', 'uploaded'])

const file = ref(null)
const dataset = ref('')
const apply = ref(false)
const busy = ref(false)
const error = ref('')
const opts = ref({})
const available = computed(() => props.datasets.filter((d) => d.can_apply))
const chosen = computed(() => props.datasets.find((d) => d.key === dataset.value) || null)
watch(chosen, (d) => { opts.value = optionValues(d?.options || [], {}) }, { immediate: true })
watch([file, dataset], () => { error.value = '' })
const tooBig = computed(() => file.value && file.value.size > props.maxMb * 1024 * 1024)

async function submit() {
  if (!file.value || tooBig.value) return
  busy.value = true
  error.value = ''
  try {
    const item = await inboxApi.upload({ file: file.value, dataset: dataset.value, apply: apply.value, options: chosen.value?.options?.length ? opts.value : null })
    emit('uploaded', item)
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <AppModal title="Загрузить файл" subtitle="Файл станет элементом входящих: сначала план — что создастся, изменится и какие ошибки, — затем применение" :width="620" @close="emit('close')">
    <div class="stack up">
      <TransferFile v-model="file" accept=".xlsx,.xlsm,.csv,.txt,.json" :hint="`Excel, CSV или JSON — до ${maxMb} МБ`" testid="inbox-file" />
      <p v-if="tooBig" class="form-error" role="alert"><AppIcon name="alert" :size="14" />Файл больше {{ maxMb }} МБ — сервер его не примет</p>

      <label class="field">
        <span>Набор данных</span>
        <select v-model="dataset" class="select" data-testid="inbox-dataset">
          <option value="">Распознать автоматически — по имени и содержимому</option>
          <option v-for="d in available" :key="d.key" :value="d.key">{{ d.label }}</option>
        </select>
      </label>
      <div v-if="chosen" class="ds">
        <p>{{ chosen.description }}</p>
        <p class="muted">Форматы: {{ chosen.formats }}<template v-if="chosen.patterns?.length"> · распознаётся по имени: <code v-for="p in chosen.patterns.slice(0, 3)" :key="p">{{ p }}</code></template></p>
      </div>
      <p v-else class="muted small">Если набор не распознается, элемент будет ждать: выберите набор в нём и нажмите «Повторить».</p>

      <div v-if="chosen?.options?.length" class="opt-grid">
        <template v-for="f in chosen.options" :key="f.key">
          <label v-if="f.type === 'bool'" class="check"><input v-model="opts[f.key]" type="checkbox" /><span>{{ f.label }}<small v-if="f.hint">{{ f.hint }}</small></span></label>
          <label v-else class="field">
            <span>{{ f.label }}</span>
            <select v-model="opts[f.key]" class="select"><option v-for="o in f.options" :key="o.value" :value="o.value">{{ o.label }}</option></select>
            <small v-if="f.hint" class="help">{{ f.hint }}</small>
          </label>
        </template>
      </div>

      <label class="check apply"><input v-model="apply" type="checkbox" data-testid="inbox-apply-now" /><span>Применить сразу, если в плане нет ошибок<small>Иначе план ждёт подтверждения: его можно проверить и применить или отклонить</small></span></label>
      <p v-if="error" class="form-error" role="alert" data-testid="upload-error"><AppIcon name="alert" :size="14" />{{ error }}</p>
    </div>
    <template #footer>
      <button type="button" class="btn" @click="emit('close')">Отмена</button>
      <button type="button" class="btn btn-primary" :disabled="!file || busy || tooBig" data-testid="inbox-upload-submit" @click="submit">
        <AppIcon name="upload" :size="15" />{{ busy ? 'Загружаю…' : 'Загрузить' }}
      </button>
    </template>
  </AppModal>
</template>

<style scoped>
.up { gap: 14px; }
.ds { display: flex; flex-direction: column; gap: 4px; padding: 10px 12px; border-radius: 10px; background: var(--surface-2); border: 1px solid var(--border); font-size: var(--fs-sm); color: var(--text-2); }
.ds code { margin-left: 4px; padding: 0 5px; border-radius: 4px; background: var(--surface-3); font-family: var(--font-mono); font-size: var(--fs-xs); }
.muted { color: var(--muted); }
.small { font-size: var(--fs-sm); }
.opt-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px 18px; }
.check { align-items: flex-start; }
.check input { margin-top: 2px; flex: 0 0 auto; }
.check span { display: flex; flex-direction: column; font-size: var(--fs-sm); }
.check small, .help { font-size: var(--fs-xs); color: var(--muted); }
.form-error { display: flex; align-items: flex-start; gap: 6px; font-size: var(--fs-sm); color: var(--light-red); }
.form-error :deep(svg) { margin-top: 2px; flex: 0 0 auto; }
</style>
