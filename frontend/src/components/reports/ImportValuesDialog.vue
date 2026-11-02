<script setup>
import { computed, ref, watch } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import AppModal from '@/components/ui/AppModal.vue'
import SegmentedControl from '@/components/ui/SegmentedControl.vue'
import PlanChips from '@/components/transfer/PlanChips.vue'
import TransferBanner from '@/components/transfer/TransferBanner.vue'
import TransferFile from '@/components/transfer/TransferFile.vue'
import { reportsApi } from '@/api/reports'
import { toastOk } from '@/composables/useToast'
import { IMPORT_ACTIONS, IMPORT_CLEAR_COLUMN, IMPORT_COLUMNS, IMPORT_FILTERS, cellStateText, filterImportRows, importChips } from '@/domain/reports'
import { monthLabel } from '@/utils/format'

/**
 * Загрузка значений показателей из Excel или CSV (как «Импорт и экспорт» 0.2.0): файл → проверка
 * (план: строки с действием и ошибками) → применение одной операцией. Шаблон — CSV по форме страницы.
 */
defineProps({
  period: { type: String, required: true },
})
const emit = defineEmits(['close', 'applied', 'template'])

const file = ref(null)
const plan = ref(null)
const result = ref('')
const busy = ref('')
const error = ref('')
const filter = ref('changes')
watch(file, () => {
  plan.value = null
  result.value = ''
  error.value = ''
})

async function run(apply) {
  busy.value = apply ? 'apply' : 'check'
  error.value = ''
  try {
    return await reportsApi.importValues({ file: file.value, apply })
  } catch (e) {
    error.value = e.message
    return null
  } finally {
    busy.value = ''
  }
}
async function check() {
  const next = await run(false)
  if (!next) return
  plan.value = next
  filter.value = next.summary.errors ? 'errors' : 'changes'
}
async function apply() {
  const applied = await run(true)
  if (!applied) return
  plan.value = applied
  if (applied.rejected) {
    filter.value = 'errors'
    return
  }
  const s = applied.summary
  result.value = `Новых значений: ${s.create} · изменено: ${s.update}${s.cleared ? ` · очищено: ${s.cleared}` : ''} · без изменений: ${s.unchanged}`
  toastOk('Значения показателей загружены')
  emit('applied')
}
const rows = computed(() => filterImportRows(plan.value?.rows || [], filter.value))
const chips = computed(() => importChips(plan.value?.summary))
const unitName = (path) => String(path || '').split(' / ').at(-1)
</script>

<template>
  <AppModal title="Загрузка значений показателей" :subtitle="`Excel или CSV: строка — значение показателя подразделения за месяц. Форма страницы — ${monthLabel(period).toLowerCase()}.`" :width="920" @close="emit('close')">
    <div class="imp">
      <ul class="columns" aria-label="Столбцы файла">
        <li v-for="c in IMPORT_COLUMNS" :key="c"><code>{{ c }}</code><small v-if="c === 'Подразделение'">путь через «/» или код</small><small v-else-if="c === 'Показатель'">название или ключ</small><small v-else-if="c === 'Период'">ГГГГ-ММ</small></li>
        <li class="optional"><code>{{ IMPORT_CLEAR_COLUMN }}</code><small>необязательно: «да» — удалить значение</small></li>
      </ul>
      <p class="hint">Пустая ячейка файла не стирает сохранённое значение; чтобы удалить его, оставьте значение, цель и комментарий пустыми и напишите «да» в столбце «{{ IMPORT_CLEAR_COLUMN }}». Проверка ничего не записывает: сначала — план, затем «Применить».
        <button type="button" class="link-btn" data-testid="import-template" @click="emit('template')"><AppIcon name="download" :size="13" />Шаблон CSV за {{ monthLabel(period).toLowerCase() }}</button>
      </p>
      <TransferFile v-model="file" accept=".xlsx,.csv" hint="Excel (.xlsx) или CSV (UTF-8, разделитель «;» или «,»)" testid="values-file" />
      <p v-if="error" class="form-error" role="alert"><AppIcon name="alert" :size="14" />{{ error }}</p>

      <TransferBanner v-if="result" title="Значения загружены" :text="result" data-testid="import-applied" />

      <section v-if="plan" class="plan" data-testid="import-plan">
        <header class="plan-head">
          <h3>{{ result ? 'После загрузки' : 'Что изменится' }}</h3>
          <PlanChips :chips="chips" />
        </header>
        <TransferBanner v-if="plan.rejected" tone="error" :title="plan.detail || 'Ничего не записано'" text="Строки с ошибками отмечены ниже — исправьте файл и проверьте снова." />
        <SegmentedControl v-model="filter" :options="IMPORT_FILTERS" size="sm" />
        <div class="table-wrap bordered scroll-thin">
          <table class="table table-compact">
            <thead><tr><th class="num">Строка</th><th>Подразделение</th><th>Показатель</th><th>Период</th><th>Было</th><th>Станет</th><th>Действие</th></tr></thead>
            <tbody>
              <tr v-for="r in rows" :key="r.line" :class="{ err: r.errors.length }">
                <td class="num muted">{{ r.line }}</td>
                <td :title="r.department_path || r.department"><b>{{ unitName(r.department_path) || r.department || '—' }}</b></td>
                <td>{{ r.indicator_name || r.indicator || '—' }}</td>
                <td class="nowrap">{{ r.period }}</td>
                <td class="muted">{{ cellStateText(r.before) }}</td>
                <td :class="{ cleared: r.action === 'clear' }">{{ r.action === 'error' ? '—' : r.action === 'clear' ? 'значение удалится' : cellStateText(r.after) }}</td>
                <td>
                  <span class="badge" :class="`badge-${IMPORT_ACTIONS[r.action]?.tone || 'gray'}`">{{ IMPORT_ACTIONS[r.action]?.label || r.action }}</span>
                  <ul v-if="r.errors.length" class="errs"><li v-for="e in r.errors" :key="e">{{ e }}</li></ul>
                </td>
              </tr>
              <tr v-if="!rows.length"><td colspan="7" class="empty-row">Нет строк для показа в этом фильтре</td></tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>
    <template #footer>
      <span class="foot-note">{{ plan ? (result ? 'Изменения применены.' : plan.can_apply ? 'Всё будет записано одной операцией.' : 'Исправьте ошибки в файле и проверьте снова.') : '' }}</span>
      <button class="btn" type="button" @click="emit('close')">{{ result ? 'Готово' : 'Отмена' }}</button>
      <button v-if="!plan || plan.rejected || !plan.can_apply" class="btn btn-primary" type="button" :disabled="!file || !!busy" data-testid="import-check" @click="check">
        <AppIcon name="search" :size="15" />{{ busy === 'check' ? 'Проверяю…' : 'Проверить' }}
      </button>
      <button v-else class="btn btn-primary" type="button" :disabled="!!busy || !!result || !plan.can_apply" data-testid="import-apply" @click="apply">
        <AppIcon name="check" :size="15" />{{ busy === 'apply' ? 'Применяю…' : 'Применить' }}
      </button>
    </template>
  </AppModal>
</template>

<style scoped>
.imp { display: flex; flex-direction: column; gap: 14px; }
.columns { display: flex; flex-wrap: wrap; gap: 6px; margin: 0; padding: 0; list-style: none; }
.columns li { display: inline-flex; align-items: baseline; gap: 6px; padding: 4px 10px; border-radius: var(--radius-pill); background: var(--surface-2); border: 1px solid var(--border); }
.columns code { font-family: var(--font-sans); font-size: var(--fs-sm); font-weight: 600; color: var(--text); }
.columns small { font-size: var(--fs-xs); color: var(--muted); }
.columns li.optional { border-style: dashed; }
.cleared { font-style: italic; color: var(--text-2); }
.hint { font-size: var(--fs-sm); color: var(--muted); line-height: 1.5; }
.link-btn { display: inline-flex; align-items: center; gap: 5px; margin-left: 4px; padding: 0; border: 0; background: transparent; color: var(--accent); font-size: var(--fs-sm); cursor: pointer; }
.link-btn:hover { text-decoration: underline; }
.form-error { display: flex; align-items: flex-start; gap: 6px; font-size: var(--fs-sm); color: var(--light-red); }
.plan { display: flex; flex-direction: column; gap: 10px; }
.plan-head { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px 16px; }
.plan-head h3 { font-size: var(--fs-md); }
.bordered { border: 1px solid var(--border); border-radius: 12px; max-height: 340px; }
.bordered .table td { vertical-align: top; font-size: var(--fs-sm); }
.badge-blue { background: color-mix(in srgb, var(--accent) 13%, transparent); color: var(--on-blue); }
tr.err td { background: color-mix(in srgb, var(--light-red) 5%, transparent); }
.errs { margin: 4px 0 0; padding-left: 16px; font-size: var(--fs-xs); color: var(--light-red); }
.empty-row { text-align: center; color: var(--muted); }
.foot-note { flex: 1; align-self: center; font-size: var(--fs-sm); color: var(--muted); }
</style>
