<script setup>
import { computed, ref, watch } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import ToggleSwitch from '@/components/admin/ToggleSwitch.vue'
import { inboxApi } from '@/api/inbox'
import { useAsync } from '@/composables/useAsync'
import { toastOk } from '@/composables/useToast'
import { SOURCE_ICONS, cloneMatrix, rulesChanges, rulesMatrix } from '@/domain/inbox'

/**
 * Правила «применять сразу» (data.manage): для каждого источника (папка, приём по API, подключения)
 * и набора — применять ли план без ошибок автоматически. Загрузку в интерфейсе применяет сам
 * загрузивший, поэтому для неё правила нет.
 */
const props = defineProps({
  meta: { type: Object, default: null },
})

const { data, loading, error, reload } = useAsync(() => inboxApi.rules())
const original = computed(() => rulesMatrix(data.value || [], { datasets: props.meta?.datasets || [], sources: props.meta?.sources || [] }))
const draft = ref(cloneMatrix(original.value))
watch(original, (m) => { draft.value = cloneMatrix(m) })
const changes = computed(() => rulesChanges(original.value, draft.value))
const saving = ref(false)

const services = computed(() => Object.fromEntries((props.meta?.datasets || []).map((d) => [d.key, d.formats])))
const columnOn = (source) => draft.value.rows.length && draft.value.rows.every((r) => r.cells[source])
function setColumn(source, value) {
  for (const row of draft.value.rows) row.cells[source] = value
}

async function save() {
  saving.value = true
  try {
    const saved = await inboxApi.saveRules(changes.value)
    data.value = saved
    toastOk(`Правила сохранены: изменено ${changes.value.length || 'ничего'}`)
  } catch {} finally {
    saving.value = false
  }
}
</script>

<template>
  <section class="card rules" data-testid="inbox-rules">
    <header class="card-head">
      <h3>Применять сразу</h3>
      <span class="hint">План без ошибок применяется без подтверждения; с ошибками — всегда ждёт</span>
    </header>
    <div class="card-body stack">
      <p class="explain">
        Включите для источника и набора, которым доверяете: например, недельный отчёт техподдержки из папки или значения показателей из 1С по ключу.
        Остальное ждёт подтверждения на вкладке «Элементы». Загрузку в интерфейсе применяет загрузивший — для неё правила нет.
      </p>

      <div v-if="loading && !data" class="skeleton" style="height: 260px" />
      <EmptyState v-else-if="error && !data" compact icon="alert" title="Не удалось загрузить правила" :text="error.message">
        <button class="btn btn-sm" type="button" @click="reload()">Повторить</button>
      </EmptyState>

      <div v-else class="table-wrap bordered">
        <table class="table matrix">
          <thead>
            <tr>
              <th>Набор данных</th>
              <th v-for="s in draft.sources" :key="s.key" class="col">
                <span class="src"><AppIcon :name="SOURCE_ICONS[s.key] || 'file'" :size="14" />{{ s.label }}</span>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in draft.rows" :key="row.key" :data-dataset="row.key">
              <th scope="row" class="ds"><b>{{ row.label }}</b><small v-if="services[row.key]">{{ services[row.key] }}</small></th>
              <td v-for="s in draft.sources" :key="s.key" class="col" :data-label="s.label">
                <ToggleSwitch v-model="row.cells[s.key]" :title="`${s.label}: ${row.label} — применять сразу`" :data-testid="`rule-${s.key}-${row.key}`" class="cell-switch" />
              </td>
            </tr>
          </tbody>
          <tfoot>
            <tr>
              <td>Для всех наборов</td>
              <td v-for="s in draft.sources" :key="s.key" class="col" :data-label="s.label">
                <button type="button" class="btn btn-ghost btn-sm" @click="setColumn(s.key, !columnOn(s.key))">{{ columnOn(s.key) ? 'Выключить все' : 'Включить все' }}</button>
              </td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
    <footer v-if="changes.length" class="save-bar">
      <span class="muted">Изменено правил: {{ changes.length }}</span>
      <span class="spacer" />
      <button type="button" class="btn" :disabled="saving" @click="draft = cloneMatrix(original)">Отменить</button>
      <button type="button" class="btn btn-primary" :disabled="saving" data-testid="rules-save" @click="save"><AppIcon name="check" :size="15" />{{ saving ? 'Сохраняю…' : 'Сохранить' }}</button>
    </footer>
  </section>
</template>

<style scoped>
.rules .card-head { flex-wrap: wrap; row-gap: 2px; }
.explain { max-width: 820px; font-size: var(--fs-sm); color: var(--text-2); line-height: 1.5; }
.bordered { border: 1px solid var(--border); border-radius: 12px; }
.matrix th.col, .matrix td.col { text-align: center; width: 180px; }
.src { display: inline-flex; align-items: center; gap: 6px; }
.matrix th.ds { text-align: left; font-weight: 500; text-transform: none; letter-spacing: 0; font-size: var(--fs-base); color: var(--text); background: transparent; position: static; border-bottom: 1px solid var(--border); padding: 10px 14px; white-space: normal; }
.matrix th.ds b { display: block; font-weight: 600; }
.matrix th.ds small { display: block; font-size: var(--fs-xs); color: var(--muted); }
.matrix tbody tr:last-child th.ds { border-bottom: 0; }
.cell-switch { justify-content: center; }
.matrix tfoot td { font-weight: 500; font-size: var(--fs-sm); color: var(--muted); }
.save-bar { position: sticky; bottom: 0; display: flex; align-items: center; gap: 10px; padding: 12px 20px; border-top: 1px solid var(--border); background: color-mix(in srgb, var(--surface-2) 94%, transparent); backdrop-filter: blur(6px); border-radius: 0 0 var(--radius-lg) var(--radius-lg); }
.muted { color: var(--muted); font-size: var(--fs-sm); }
@media (max-width: 720px) {
  .matrix thead { display: none; }
  .matrix tr { display: grid; grid-template-columns: 1fr; padding: 10px 12px; border-bottom: 1px solid var(--border); }
  .matrix th.ds { padding: 0 0 6px; border: 0; }
  .matrix td, .matrix td.col { display: flex; align-items: center; justify-content: space-between; gap: 10px; width: auto; padding: 4px 0; border: 0; text-align: left; }
  .matrix td.col::before { content: attr(data-label); font-size: var(--fs-sm); color: var(--text-2); }
  .matrix tfoot tr { background: var(--surface-2); }
  .save-bar { padding: 10px 16px; flex-wrap: wrap; }
}
</style>
