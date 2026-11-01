<script setup>
import { computed, ref, watch } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import SegmentedControl from '@/components/ui/SegmentedControl.vue'
import OrgIcon from '@/components/org/OrgIcon.vue'
import PlanChips from './PlanChips.vue'
import TransferBanner from './TransferBanner.vue'
import TransferFile from './TransferFile.vue'
import { orgApi } from '@/api/org'
import { PLAN_ACTIONS, PLAN_FILTERS, filterStructureDepartments, structureChips } from '@/domain/org'

/**
 * Перенос структуры: выгрузка JSON (подразделения, типы, порядок, коды, руководители по email,
 * настройки) и загрузка — проверка (план без записи) → применение одной транзакцией.
 */
const emit = defineEmits(['applied'])

const exporting = ref(false)
async function download() {
  exporting.value = true
  try { await orgApi.exportStructure() } catch {} finally { exporting.value = false }
}

const file = ref(null)
const bundle = ref(null)
const applySettings = ref(true)
const plan = ref(null)
const result = ref(null)
const busy = ref('')
const error = ref('')
const filter = ref('changes')

watch(file, async (value) => {
  plan.value = null
  result.value = null
  error.value = ''
  bundle.value = null
  if (!value) return
  try {
    bundle.value = JSON.parse(await value.text())
  } catch {
    error.value = 'Файл не читается как JSON — выберите выгрузку структуры (dashboards-structure-….json)'
  }
})
watch(applySettings, () => { if (plan.value && !result.value) check() })

async function run(apply) {
  if (!bundle.value || busy.value) return null
  busy.value = apply ? 'apply' : 'check'
  error.value = ''
  try {
    return await orgApi.importStructure({ bundle: bundle.value, applySettings: applySettings.value, apply })
  } catch (e) {
    error.value = e.message
    return null
  } finally {
    busy.value = ''
  }
}
async function check() {
  result.value = null
  const next = await run(false)
  if (next) {
    plan.value = next
    filter.value = next.summary.errors ? 'changes' : filter.value
  }
}
async function apply() {
  const applied = await run(true)
  if (!applied) return
  if (applied.rejected) {
    plan.value = applied
    return
  }
  const s = applied.summary
  result.value = { create: s.create, update: s.update, heads: s.add_heads, settings: applied.settings_applied }
  emit('applied')
  // План после применения: всё должно стать «без изменений»
  const fresh = await run(false)
  if (fresh) plan.value = fresh
}

const chips = computed(() => structureChips(plan.value?.summary))
const departments = computed(() => filterStructureDepartments(plan.value?.departments || [], filter.value))
const heads = computed(() => (plan.value?.heads || []).filter((h) => filter.value === 'all' || h.action !== 'exists'))
const FIELD = { kind: 'Тип', sort_order: 'Порядок', code: 'Код', name: 'Название', external_id: 'Внешний ID' }
const resultText = computed(() => {
  const r = result.value
  if (!r) return ''
  const parts = [`новых подразделений: ${r.create}`, `изменено: ${r.update}`, `назначено руководителей: ${r.heads}`]
  if (r.settings) parts.push('настройки структуры перенесены')
  return parts.join(' · ')
})
</script>

<template>
  <div class="transfer">
    <section class="card block">
      <div class="block-head">
        <span class="b-icon"><AppIcon name="download" :size="18" /></span>
        <div class="b-text">
          <h2>Выгрузить структуру</h2>
          <p>Файл JSON: подразделения с типами, порядком, кодами и руководителями (по email), а также типы уровней, предел вложенности и вид оргсхемы. Сотрудники выгружаются на вкладке «Сотрудники».</p>
        </div>
        <button type="button" class="btn" :disabled="exporting" data-testid="structure-export" @click="download">
          <AppIcon name="download" :size="15" />{{ exporting ? 'Готовлю файл…' : 'Скачать JSON' }}
        </button>
      </div>
    </section>

    <section class="card block">
      <div class="block-head">
        <span class="b-icon"><AppIcon name="upload" :size="18" /></span>
        <div class="b-text">
          <h2>Загрузить структуру</h2>
          <p>Подразделения сопоставляются по пути от верхнего уровня: новые создаются, у существующих меняются тип, порядок и код. Подразделения, которых нет в файле, не удаляются; руководители только добавляются.</p>
        </div>
      </div>
      <div class="block-body">
        <TransferFile v-model="file" accept=".json" hint="JSON — выгрузка структуры из этой или другой системы «Дашборды компании»" testid="structure-file" />
        <label class="check"><input v-model="applySettings" type="checkbox" /> Перенести и настройки структуры: типы уровней, предел вложенности, вид по умолчанию</label>
        <p v-if="error" class="form-error" role="alert"><AppIcon name="alert" :size="14" />{{ error }}</p>
        <div class="actions">
          <button type="button" class="btn btn-primary" :disabled="!bundle || !!busy" data-testid="structure-check" @click="check">
            <AppIcon name="search" :size="15" />{{ busy === 'check' ? 'Проверяю…' : 'Проверить' }}
          </button>
          <span class="muted">Проверка ничего не записывает — покажет, что изменится.</span>
        </div>
      </div>
    </section>

    <TransferBanner v-if="result" title="Структура загружена" :text="resultText" data-testid="structure-applied" />

    <section v-if="plan" class="card plan" data-testid="structure-plan">
      <header class="plan-head">
        <div>
          <h2>{{ result ? 'Структура после загрузки' : 'Что изменится' }}</h2>
          <p class="muted">{{ file?.name }}</p>
        </div>
        <PlanChips :chips="chips" />
      </header>

      <TransferBanner v-if="plan.rejected || plan.errors.length" tone="error" title="В файле есть ошибки — ничего не записано" class="inset">
        <ul class="err-list"><li v-for="e in plan.errors" :key="e">{{ e }}</li></ul>
      </TransferBanner>

      <div v-if="plan.settings.length" class="plan-block">
        <h3>Настройки структуры</h3>
        <div class="table-wrap bordered">
          <table class="table table-compact">
            <thead><tr><th>Настройка</th><th>Сейчас</th><th>Из файла</th></tr></thead>
            <tbody><tr v-for="s in plan.settings" :key="s.key"><td>{{ s.label }}</td><td class="muted">{{ s.current }}</td><td><b>{{ s.incoming }}</b></td></tr></tbody>
          </table>
        </div>
      </div>

      <div class="plan-block">
        <div class="block-title">
          <h3>Подразделения</h3>
          <SegmentedControl v-model="filter" :options="PLAN_FILTERS" size="sm" />
        </div>
        <div v-if="departments.length" class="table-wrap bordered scroll-thin">
          <table class="table table-compact">
            <thead><tr><th>Путь</th><th>Действие</th><th>Изменения</th></tr></thead>
            <tbody>
              <tr v-for="d in departments" :key="d.key">
                <td class="path">{{ d.path }}</td>
                <td><span class="badge" :class="`badge-${PLAN_ACTIONS[d.action].tone}`">{{ d.action === 'create' ? 'Новое' : PLAN_ACTIONS[d.action].label }}</span></td>
                <td class="changes">
                  <span v-for="c in d.changes" :key="c.field"><span class="lbl">{{ FIELD[c.field] || c.field }}:</span> <s>{{ c.old ?? '—' }}</s> → {{ c.new ?? '—' }}</span>
                  <span v-if="!d.changes.length" class="muted">—</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-else class="empty">{{ filter === 'errors' ? 'Ошибки — в списке выше' : filter === 'changes' ? 'Изменений в подразделениях нет — всё совпадает с системой' : 'В файле нет подразделений' }}</p>
      </div>

      <div v-if="heads.length" class="plan-block">
        <h3>Руководители</h3>
        <div class="table-wrap bordered scroll-thin">
          <table class="table table-compact">
            <thead><tr><th>Подразделение</th><th>Руководитель</th><th>Действие</th></tr></thead>
            <tbody>
              <tr v-for="h in heads" :key="`${h.department_key}-${h.email}`">
                <td class="path">{{ h.path }}</td>
                <td>{{ h.name || h.email }}<OrgIcon v-if="h.primary" name="star" :size="11" class="star" /><small v-if="h.name" class="sub">{{ h.email }}</small></td>
                <td><span class="badge" :class="`badge-${PLAN_ACTIONS[h.action].tone}`">{{ PLAN_ACTIONS[h.action].label }}</span></td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-if="plan.summary.pending_heads" class="muted small">«Нет в системе» — назначатся после загрузки сотрудников с этими email (вкладка «Сотрудники», столбец «Руководит»).</p>
      </div>

      <div v-if="plan.missing_in_file.length" class="plan-block">
        <h3>Есть в системе, нет в файле — останутся</h3>
        <p class="missing">{{ plan.missing_in_file.join(' · ') }}</p>
      </div>

      <footer class="plan-foot">
        <button type="button" class="btn btn-primary" :disabled="!plan.can_apply || !!busy || !!result" data-testid="structure-apply" @click="apply">
          <AppIcon name="check" :size="15" />{{ busy === 'apply' ? 'Применяю…' : 'Применить' }}
        </button>
        <span class="muted">
          <template v-if="result">Изменения применены. Выберите другой файл, чтобы загрузить ещё.</template>
          <template v-else-if="!plan.can_apply">Исправьте ошибки в файле и проверьте снова.</template>
          <template v-else>Всё будет записано одной операцией и попадёт в журнал изменений.</template>
        </span>
      </footer>
    </section>
  </div>
</template>

<style scoped src="./transfer.css"></style>
<style scoped>
.path { min-width: 260px; }
.changes span { display: block; font-size: var(--fs-sm); }
.changes .lbl { color: var(--muted); }
.changes s { color: var(--muted); }
.sub { display: block; font-size: var(--fs-xs); color: var(--muted); }
.star { display: inline-block; margin-left: 5px; color: color-mix(in srgb, var(--light-yellow) 85%, var(--text)); vertical-align: -1px; }
.missing { font-size: var(--fs-sm); color: var(--text-2); line-height: 1.6; }
.err-list { margin: 4px 0 0; padding-left: 18px; }
.small { font-size: var(--fs-xs); margin-top: 6px; }
</style>
