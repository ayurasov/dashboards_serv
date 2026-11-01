<script setup>
import { computed, ref } from 'vue'
import AppModal from '@/components/ui/AppModal.vue'
import SegmentedControl from '@/components/ui/SegmentedControl.vue'
import OrgIcon from './OrgIcon.vue'
import { orgApi } from '@/api/org'
import { LEVEL_FORMS, ORG_VIEWS, UNIT_FORMS, countText, kindValueFromLabel } from '@/domain/org'

/**
 * Типы уровней и вложенность: типы (цвет, название, порядок; используемый удалить нельзя),
 * предел вложенности с запасом относительно текущей глубины, вид оргсхемы по умолчанию.
 * Действует для всех пользователей.
 */
const props = defineProps({ settings: { type: Object, required: true } })
const emit = defineEmits(['close', 'saved'])

const LIMITS = { min: 2, max: 30 }
let seq = 0
const kinds = ref(props.settings.unit_kinds.map((k) => ({ ...k, key: `k${seq++}`, isNew: false })))
const maxDepth = ref(props.settings.max_depth)
const defaultView = ref(props.settings.default_view)
const saving = ref(false)
const error = ref('')

const used = (kind) => (kind.isNew ? 0 : props.settings.used_kinds?.[kind.value] || 0)
const current = computed(() => props.settings.current_depth || 0)
const minDepth = computed(() => Math.max(LIMITS.min, current.value))
const depthValue = computed(() => Number(maxDepth.value) || 0)
const depthInvalid = computed(() => depthValue.value < minDepth.value || depthValue.value > LIMITS.max)
const share = computed(() => Math.min(100, Math.round((current.value / Math.max(1, depthValue.value)) * 100)))
const depthNote = computed(() => {
  const spare = depthValue.value - current.value
  if (depthValue.value < current.value) return `меньше текущей глубины — так сохранить нельзя`
  if (spare === 0) return 'предел достигнут: вложить ещё уровень не получится'
  if (spare === 1) return 'можно вложить ещё один уровень'
  return `запас ${countText(spare, LEVEL_FORMS)}`
})
const unknownKinds = computed(() => Object.keys(props.settings.used_kinds || {}).filter((v) => !props.settings.unit_kinds.some((k) => k.value === v)))
const labelsMissing = computed(() => kinds.value.some((k) => !k.label.trim()))
const viewOptions = ORG_VIEWS.map((v) => ({ value: v.value, label: v.label, title: v.hint }))

function addKind() {
  kinds.value = [...kinds.value, { value: '', label: '', color: '#4f7cff', key: `k${seq++}`, isNew: true }]
}
function move(index, step) {
  const list = [...kinds.value]
  const [item] = list.splice(index, 1)
  list.splice(index + step, 0, item)
  kinds.value = list
}
function remove(index) {
  kinds.value = kinds.value.filter((_, i) => i !== index)
}

async function save() {
  error.value = ''
  if (labelsMissing.value) {
    error.value = 'У каждого типа должно быть название'
    return
  }
  if (depthInvalid.value) {
    error.value = `Предел вложенности — от ${minDepth.value} до ${LIMITS.max}`
    return
  }
  const taken = kinds.value.filter((k) => !k.isNew).map((k) => k.value)
  const unitKinds = kinds.value.map((k) => {
    const value = k.isNew ? kindValueFromLabel(k.label, taken) : k.value
    taken.push(value)
    return { value, label: k.label.trim(), color: k.color }
  })
  saving.value = true
  try {
    const saved = await orgApi.saveSettings({ unit_kinds: unitKinds, max_depth: depthValue.value, default_view: defaultView.value })
    emit('saved', saved)
  } catch (e) {
    error.value = e.message
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <AppModal title="Типы уровней и вложенность" subtitle="Действует для всех пользователей" :width="640" @close="emit('close')">
    <section class="block">
      <h3>Типы уровней</h3>
      <p class="hint">Тип подписывает подразделение и задаёт цвет карточки на оргсхеме. Используемый тип удалить нельзя — сначала смените его у подразделений.</p>
      <ol class="kinds">
        <li v-for="(k, i) in kinds" :key="k.key" class="kind" :class="{ unused: !k.isNew && !used(k) }">
          <label class="swatch" :style="{ background: k.color }" :title="`Цвет: ${k.color}`">
            <input v-model="k.color" type="color" :aria-label="`Цвет типа «${k.label || 'новый'}»`" />
          </label>
          <input v-model="k.label" class="input input-sm kind-name" maxlength="60" placeholder="Название типа" :aria-label="`Название типа ${i + 1}`" />
          <code class="code" :title="k.isNew ? 'Ключ появится при сохранении' : 'Ключ для загрузки и API'">{{ k.isNew ? 'новый' : k.value }}</code>
          <span class="usage" :class="{ on: used(k) }">{{ used(k) ? countText(used(k), UNIT_FORMS) : k.isNew ? 'будет добавлен' : 'не используется' }}</span>
          <span class="moves">
            <button type="button" class="btn btn-ghost btn-icon btn-sm" :disabled="i === 0" :aria-label="`Выше: ${k.label}`" title="Выше" @click="move(i, -1)"><OrgIcon name="chevron-up" :size="14" /></button>
            <button type="button" class="btn btn-ghost btn-icon btn-sm" :disabled="i === kinds.length - 1" :aria-label="`Ниже: ${k.label}`" title="Ниже" @click="move(i, 1)"><OrgIcon name="chevron-down" :size="14" /></button>
            <button type="button" class="btn btn-ghost btn-icon btn-sm btn-danger" :disabled="kinds.length === 1 || used(k) > 0"
                    :title="used(k) ? `Используется: ${countText(used(k), UNIT_FORMS)} — сначала смените тип у них` : 'Удалить тип'"
                    :aria-label="`Удалить тип ${k.label}`" @click="remove(i)"><OrgIcon name="trash" :size="14" /></button>
          </span>
        </li>
      </ol>
      <p v-if="unknownKinds.length" class="warn"><OrgIcon name="alert" :size="14" />В структуре есть подразделения с типом, которого нет в списке: {{ unknownKinds.join(', ') }}.</p>
      <button type="button" class="btn btn-sm add" @click="addKind"><OrgIcon name="plus" :size="14" />Добавить тип</button>
    </section>

    <section class="block">
      <h3>Вложенность</h3>
      <div class="depth">
        <label class="field"><span>Предел уровней</span>
          <input v-model.number="maxDepth" class="input num" :class="{ invalid: depthInvalid }" type="number" :min="minDepth" :max="LIMITS.max" data-testid="org-max-depth" />
        </label>
        <div class="gauge-wrap">
          <div class="gauge" role="meter" :aria-valuenow="current" :aria-valuemin="0" :aria-valuemax="depthValue" :aria-label="`Используется ${current} из ${depthValue} уровней`">
            <span :style="{ width: `${share}%` }" :class="{ warn: current >= depthValue - 1, over: current > depthValue }" />
          </div>
          <p class="gauge-text">Сейчас <b>{{ current }}</b> из {{ depthValue || '—' }} · {{ depthNote }}</p>
        </div>
      </div>
      <p class="hint">Компания — первый уровень. От {{ LIMITS.min }} до {{ LIMITS.max }}; меньше текущей глубины структуры задать нельзя.</p>
    </section>

    <section class="block">
      <h3>Вид оргсхемы по умолчанию</h3>
      <SegmentedControl v-model="defaultView" :options="viewOptions" />
      <p class="hint">Каждый может переключить вид — его выбор запоминается.</p>
    </section>

    <p v-if="error" class="form-error" role="alert"><OrgIcon name="alert" :size="14" />{{ error }}</p>
    <template #footer>
      <button class="btn" type="button" @click="emit('close')">Отмена</button>
      <button class="btn btn-primary" type="button" :disabled="saving" data-testid="org-settings-save" @click="save">{{ saving ? 'Сохранение…' : 'Сохранить' }}</button>
    </template>
  </AppModal>
</template>

<style scoped>
.block + .block { margin-top: 22px; padding-top: 18px; border-top: 1px solid var(--border); }
h3 { font-size: var(--fs-base); font-weight: 650; }
.hint { margin-top: 4px; font-size: var(--fs-sm); color: var(--muted); line-height: 1.45; }
.kinds { list-style: none; margin: 12px 0 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.kind { display: grid; grid-template-columns: 30px minmax(0, 1fr) 96px 132px auto; gap: 8px; align-items: center; }
.swatch { position: relative; width: 30px; height: 30px; border-radius: 9px; box-shadow: inset 0 0 0 1px rgba(0, 0, 0, .12); overflow: hidden; cursor: pointer; }
.swatch input { position: absolute; inset: -8px; width: calc(100% + 16px); height: calc(100% + 16px); opacity: 0; cursor: pointer; }
.swatch:focus-within { box-shadow: 0 0 0 3px var(--focus); }
.kind-name { height: 30px; }
.unused .kind-name { color: var(--text-2); }
.code { font-family: var(--font-mono); font-size: var(--fs-xs); color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.usage { font-size: var(--fs-xs); color: var(--muted); white-space: nowrap; }
.usage.on { color: var(--light-green); font-weight: 600; }
.moves { display: inline-flex; gap: 2px; }
.add { margin-top: 10px; }
.warn { display: flex; align-items: center; gap: 6px; margin-top: 10px; font-size: var(--fs-sm); color: color-mix(in srgb, var(--light-yellow) 75%, var(--text)); }
.depth { display: flex; align-items: flex-end; gap: 18px; margin-top: 12px; flex-wrap: wrap; }
.depth .input { width: 110px; }
.gauge-wrap { flex: 1; min-width: 220px; padding-bottom: 2px; }
.gauge { height: 8px; border-radius: var(--radius-pill); background: var(--surface-3); overflow: hidden; }
.gauge span { display: block; height: 100%; border-radius: inherit; background: var(--accent); transition: width var(--t); }
.gauge span.warn { background: var(--light-yellow); }
.gauge span.over { background: var(--light-red); }
.gauge-text { margin-top: 6px; font-size: var(--fs-sm); color: var(--text-2); }
.form-error { display: flex; align-items: flex-start; gap: 6px; margin-top: 16px; font-size: var(--fs-sm); color: var(--light-red); line-height: 1.45; }
@media (max-width: 640px) {
  .kind { grid-template-columns: 30px minmax(0, 1fr) auto; }
  .code, .usage { display: none; }
}
</style>
