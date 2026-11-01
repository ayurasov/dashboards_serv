<script setup>
import { computed, reactive, ref, watch } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import { adminApi } from '@/api/services'
import { reportsApi } from '@/api/reports'
import { useAsync } from '@/composables/useAsync'
import { toastOk } from '@/composables/useToast'

/**
 * «Подразделения служб»: к какому подразделению структуры относятся вычисляемые показатели службы
 * (заявки техподдержки, партнёрства, кадровые метрики). Без настройки — по коду (HR, TECH, PROJ).
 */
const props = defineProps({
  sourceNames: { type: Object, default: () => ({}) },
})
const settings = useAsync(() => reportsApi.settings())
const departments = useAsync(() => adminApi.departments())
const draft = reactive({})
watch(() => settings.data.value, (value) => {
  for (const s of value?.services || []) draft[s.key] = s.configured ?? ''
}, { immediate: true })
const options = computed(() => (departments.data.value || []).map((d) => ({
  id: d.id, label: `${' '.repeat(Math.max(0, (d.level || 1) - 1))}${d.name}${d.code ? ` · ${d.code}` : ''}`,
})))
const dirty = computed(() => (settings.data.value?.services || []).some((s) => (s.configured ?? '') !== draft[s.key]))
const busy = ref(false)
async function save() {
  busy.value = true
  try {
    const units = Object.fromEntries((settings.data.value?.services || []).map((s) => [s.key, draft[s.key] === '' ? null : Number(draft[s.key])]))
    settings.data.value = await reportsApi.saveSettings(units)
    toastOk('Подразделения служб сохранены')
  } catch {} finally {
    busy.value = false
  }
}
const sourceList = (keys) => keys.map((k) => props.sourceNames[k] || k).join(', ')
</script>

<template>
  <section class="card su" data-testid="service-units">
    <header class="card-head">
      <h3>Подразделения служб</h3>
      <span class="hint">К какому подразделению структуры относятся показатели из данных службы</span>
    </header>
    <div class="card-body">
      <div v-if="settings.loading.value && !settings.data.value" class="skeleton" style="height: 120px" />
      <ul v-else class="su-list">
        <li v-for="s in settings.data.value?.services || []" :key="s.key">
          <div class="su-text">
            <strong>{{ s.title }}</strong>
            <small>{{ sourceList(s.sources) }}</small>
          </div>
          <div class="su-pick">
            <select v-model="draft[s.key]" class="select" :aria-label="`Подразделение службы «${s.title}»`" :data-service="s.key">
              <option value="">По коду {{ s.default_code }}{{ !s.configured && s.unit ? ` — ${s.unit.name}` : !s.configured ? ' — не найдено' : '' }}</option>
              <option v-for="o in options" :key="o.id" :value="o.id">{{ o.label }}</option>
            </select>
            <small v-if="s.unit" class="now" :title="s.unit.path"><AppIcon name="check" :size="12" />{{ s.unit.path }}</small>
            <small v-else class="now warn"><AppIcon name="alert" :size="12" />Подразделение не найдено — показатели службы не попадут в отчёт</small>
          </div>
        </li>
      </ul>
      <div class="su-foot">
        <span class="muted">Без выбора — подразделение с кодом службы по умолчанию.</span>
        <button class="btn btn-primary btn-sm" type="button" :disabled="!dirty || busy" data-testid="service-units-save" @click="save">{{ busy ? 'Сохраняю…' : 'Сохранить' }}</button>
      </div>
    </div>
  </section>
</template>

<style scoped>
.su-list { display: flex; flex-direction: column; margin: 0; padding: 0; list-style: none; }
.su-list li { display: grid; grid-template-columns: minmax(0, 2fr) minmax(0, 3fr); gap: 8px 20px; padding: 12px 0; border-bottom: 1px solid var(--border); }
.su-list li:first-child { padding-top: 0; }
.su-text { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.su-text strong { font-size: var(--fs-base); font-weight: 620; }
.su-text small, .now { font-size: var(--fs-xs); color: var(--muted); }
.su-pick { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.now { display: flex; align-items: center; gap: 5px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.now :deep(svg) { color: var(--light-green); flex: 0 0 auto; }
.now.warn, .now.warn :deep(svg) { color: var(--light-red); }
.su-foot { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding-top: 12px; font-size: var(--fs-sm); }
@media (max-width: 760px) { .su-list li { grid-template-columns: minmax(0, 1fr); } }
</style>
