<script setup>
import { onBeforeUnmount, reactive, ref, watch } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import AppModal from '@/components/ui/AppModal.vue'
import ColorField from './ColorField.vue'
import PalettePreview from './PalettePreview.vue'
import ToggleSwitch from './ToggleSwitch.vue'
import { adminApi } from '@/api/services'
import { usePaletteStore } from '@/stores/palette'
import { BRAND_SLOTS, CHART_SLOTS, formFieldErrors, LIGHT_SLOTS, normalizePalette, paletteProblem } from '@/domain/admin'

/**
 * Редактор палитры. Пока окно открыто, цвета можно примерить на весь интерфейс (только у себя);
 * при закрытии восстанавливается активная палитра.
 */
const props = defineProps({
  palette: { type: Object, default: null },
  base: { type: Object, default: null },
  name: { type: String, default: '' },
})
const emit = defineEmits(['close', 'saved'])

const store = usePaletteStore()
const isNew = !props.palette?.id
const form = reactive({
  name: props.palette?.name || props.name || 'Новая палитра',
  colors: normalizePalette(props.palette?.colors || props.base || store.colors),
})
const live = ref(true)
const saving = ref(false)
const formError = ref('')
const fieldErrors = ref({})

watch([live, () => form.colors], () => (live.value ? store.preview(form.colors) : store.reset()), { deep: true, immediate: true })
onBeforeUnmount(() => store.reset())

function restore() {
  form.colors = normalizePalette(props.palette?.colors || props.base || store.colors)
}

async function save() {
  formError.value = ''
  fieldErrors.value = {}
  const name = form.name.trim()
  if (!name) { fieldErrors.value = { name: 'Укажите название' }; return }
  const problem = paletteProblem(form.colors)
  if (problem) { formError.value = problem; return }
  saving.value = true
  try {
    const body = { name, colors: form.colors }
    const saved = isNew ? await adminApi.createPalette(body) : await adminApi.updatePalette(props.palette.id, body)
    emit('saved', saved)
  } catch (e) {
    formError.value = e.message
    fieldErrors.value = formFieldErrors(e.fields)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <AppModal :title="isNew ? 'Новая палитра' : 'Изменение палитры'" :subtitle="isNew ? 'Цвета светофора, графиков и акцентов интерфейса' : palette.name" :width="1020" @close="emit('close')">
    <form id="palette-form" class="editor" novalidate @submit.prevent="save">
      <div class="fields">
        <label class="field"><span>Название</span>
          <input v-model="form.name" class="input" :class="{ invalid: fieldErrors.name }" maxlength="200" />
          <span v-if="fieldErrors.name" class="error">{{ fieldErrors.name }}</span>
        </label>

        <section>
          <h4>Светофор</h4>
          <div class="colors">
            <ColorField v-for="s in LIGHT_SLOTS" :key="s.key" v-model="form.colors.traffic_light[s.key]" :label="s.label" />
          </div>
        </section>

        <section>
          <h4>Серии графиков <span class="muted">по порядку</span></h4>
          <div class="colors">
            <ColorField v-for="i in CHART_SLOTS" :key="i" v-model="form.colors.charts[i - 1]" :label="`Серия ${i}`" />
          </div>
        </section>

        <section>
          <h4>Акцент интерфейса</h4>
          <div class="colors">
            <ColorField v-for="s in BRAND_SLOTS" :key="s.key" v-model="form.colors.brand[s.key]" :label="s.label" />
          </div>
          <p class="help">Основной цвет — кнопки, активный раздел меню, выделение.</p>
        </section>
      </div>

      <aside class="side">
        <div class="side-head">
          <h4>Предпросмотр</h4>
          <button class="btn btn-ghost btn-sm" type="button" title="Вернуть исходные цвета" @click="restore"><AppIcon name="refresh" :size="13" />Сбросить цвета</button>
        </div>
        <div class="preview-box"><PalettePreview :colors="form.colors" /></div>
        <ToggleSwitch v-model="live" label="Примерить на весь интерфейс" />
        <p class="help">Пока окно открыто, цвета видите только вы. Для всех пользователей палитра применится после того, как её сделают активной.</p>
      </aside>
    </form>
    <p v-if="formError" class="form-error"><AppIcon name="alert" :size="14" />{{ formError }}</p>
    <template #footer>
      <button class="btn" type="button" @click="emit('close')">Отмена</button>
      <button class="btn btn-primary" type="submit" form="palette-form" :disabled="saving">{{ saving ? 'Сохранение…' : isNew ? 'Создать палитру' : 'Сохранить' }}</button>
    </template>
  </AppModal>
</template>

<style scoped>
.editor { display: grid; grid-template-columns: minmax(0, 1fr) 360px; gap: 24px; }
.fields { display: flex; flex-direction: column; gap: 18px; min-width: 0; }
h4 { font-size: var(--fs-sm); font-weight: 620; margin-bottom: 8px; color: var(--text); }
h4 .muted { font-weight: 500; }
.colors { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }
.side { display: flex; flex-direction: column; gap: 12px; align-self: start; position: sticky; top: 0; padding: 14px; border-radius: 14px; background: var(--surface-2); border: 1px solid var(--border); }
.side-head { display: flex; align-items: center; justify-content: space-between; }
.side-head h4 { margin: 0; }
.preview-box { padding: 12px; border-radius: 12px; background: var(--bg); border: 1px solid var(--border); }
.help { font-size: var(--fs-xs); color: var(--muted); }
section .help { margin-top: 6px; }
.error { font-size: var(--fs-xs); color: var(--light-red); }
.form-error { display: flex; align-items: center; gap: 6px; margin-top: 12px; font-size: var(--fs-sm); color: var(--light-red); }
@media (max-width: 900px) { .editor { grid-template-columns: 1fr; } .side { position: static; } .colors { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
</style>
