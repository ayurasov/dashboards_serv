<script setup>
import { computed, ref } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import ToggleSwitch from '@/components/admin/ToggleSwitch.vue'
import IndicatorEditor from '@/components/reports/IndicatorEditor.vue'
import RuleBands from '@/components/reports/RuleBands.vue'
import ServiceUnitsCard from '@/components/reports/ServiceUnitsCard.vue'
import { reportsApi } from '@/api/reports'
import { useAsync } from '@/composables/useAsync'
import { confirm } from '@/composables/useConfirm'
import { toastError, toastOk } from '@/composables/useToast'
import { INDICATOR_FORMS, VALUE_FORMS, count, groupByClass, ruleSummary, sourceText } from '@/domain/reports'
import { DATA_CLASS_HINTS } from '@/domain/access'
import { plural } from '@/utils/format'

/**
 * Показатели сквозного отчёта (ADR-0010, полномочие reports.manage): каталог по классам данных —
 * источник, служба-владелец, правило светофора, свёртка, где ожидается, сколько значений, активность;
 * добавление, изменение, удаление (со значениями — после подтверждения); подразделения служб.
 */
const meta = useAsync(() => reportsApi.meta())
const { data, loading, error, reload } = useAsync(() => reportsApi.indicators())
const list = computed(() => data.value || [])
const groups = computed(() => groupByClass(list.value, meta.data.value?.data_classes || []))
const kindLabel = computed(() => Object.fromEntries((meta.data.value?.unit_kinds || []).map((k) => [k.value, k.label])))
const sourceNames = computed(() => Object.fromEntries((meta.data.value?.sources || []).map((s) => [s.key, s.name])))
const stats = computed(() => ({
  total: list.value.length,
  active: list.value.filter((i) => i.is_active).length,
  manual: list.value.filter((i) => i.source_type === 'manual').length,
  computed: list.value.filter((i) => i.source_type === 'computed').length,
}))

const editing = ref(null) // null — закрыто; { indicator: null } — новый
function edit(indicator = null) { editing.value = { indicator } }
function afterSave(saved) {
  toastOk(editing.value?.indicator ? `Показатель «${saved.name}» сохранён` : `Показатель «${saved.name}» добавлен`)
  editing.value = null
  reload()
}

async function setActive(ind, value) {
  try {
    await reportsApi.updateIndicator(ind.id, { is_active: value })
    toastOk(value ? `«${ind.name}» снова в отчётах` : `«${ind.name}» выключен: в отчёты не попадает, значения сохранены`)
  } catch {} finally {
    reload()
  }
}

async function remove(ind) {
  const ok = await confirm({
    title: `Удалить показатель «${ind.name}»?`,
    message: 'Показатель исчезнет из каталога и отчётов. Если нужно лишь убрать его из отчётов, выключите его — значения сохранятся.',
    confirmText: 'Удалить', danger: true,
  })
  if (!ok) return
  let result
  try {
    result = await reportsApi.deleteIndicator(ind.id)
  } catch (e) {
    if (e.code !== 'indicator_has_values') {
      toastError(e.message)
      return
    }
    const force = await confirm({
      title: 'У показателя есть сохранённые значения',
      message: `${e.message}.\n\nУдалить показатель вместе со значениями? Отменить это будет нельзя.`,
      confirmText: 'Удалить вместе со значениями', danger: true,
    })
    if (!force) return
    try {
      result = await reportsApi.deleteIndicator(ind.id, true)
    } catch (err) {
      toastError(err.message)
      return
    }
  }
  toastOk(result?.message || 'Показатель удалён')
  reload()
}
</script>

<template>
  <div class="page">
    <PageHeader title="Показатели" description="Каталог сквозного отчёта: откуда значение, как оценивается светофором и сворачивается по структуре">
      <router-link to="/reports" class="btn btn-ghost"><AppIcon name="traffic" :size="15" />Сквозной отчёт</router-link>
      <router-link to="/reports/entry" class="btn"><AppIcon name="edit" :size="15" />Ввод показателей</router-link>
      <button class="btn btn-primary" type="button" :disabled="!meta.data.value" data-testid="indicator-add" @click="edit(null)"><AppIcon name="plus" :size="15" />Добавить показатель</button>
    </PageHeader>

    <div class="explain card">
      <span class="ex-icon"><AppIcon name="layers" :size="18" /></span>
      <p>
        <b>Статус подразделения — худший из статусов его показателей и вложенных подразделений.</b>
        Нет своего значения — берётся свёртка вложенных (сумма или среднее). Не заполнено там, где значение ожидается, —
        «Нет данных» и критичное нарушение полноты. Показатели класса, недоступного пользователю, ему не показываются вовсе.
      </p>
    </div>

    <div v-if="data" class="stats">
      <span><b class="num">{{ stats.total }}</b> {{ plural(stats.total, INDICATOR_FORMS) }}</span>
      <span><b class="num">{{ stats.active }}</b> активных</span>
      <span><b class="num">{{ stats.manual }}</b> вводятся по подразделениям</span>
      <span><b class="num">{{ stats.computed }}</b> из данных служб</span>
    </div>

    <div v-if="loading && !data" class="skeleton" style="height: 360px; border-radius: var(--radius-lg)" />
    <EmptyState v-else-if="error && !data" class="card" icon="alert" title="Не удалось загрузить каталог" :text="error.message">
      <button class="btn btn-sm" type="button" @click="reload()">Повторить</button>
    </EmptyState>
    <EmptyState v-else-if="data && !list.length" class="card" icon="target" title="Каталог пуст" text="Добавьте первый показатель — вводимый по подразделениям или из данных службы.">
      <button class="btn btn-primary btn-sm" type="button" :disabled="!meta.data.value" @click="edit(null)">Добавить показатель</button>
    </EmptyState>

    <section v-for="g in groups" :key="g.key" class="card group" :data-class="g.key">
      <header class="card-head">
        <h3>{{ g.label }}</h3>
        <span class="count">{{ g.items.length }}</span>
        <span class="hint">{{ DATA_CLASS_HINTS[g.key] || '' }}</span>
      </header>
      <div class="card-body flush table-wrap">
        <table class="table cat">
          <thead>
            <tr><th>Показатель</th><th>Источник</th><th>Светофор</th><th>Свёртка</th><th>Ожидается</th><th class="num">Значений</th><th>Активен</th><th /></tr>
          </thead>
          <tbody>
            <tr v-for="ind in g.items" :key="ind.id" :class="{ off: !ind.is_active }" :data-indicator="ind.key">
              <td class="c-name">
                <strong>{{ ind.name }}<span v-if="ind.unit" class="unit">, {{ ind.unit }}</span></strong>
                <code>{{ ind.key }}</code>
                <small v-if="ind.description" :title="ind.description">{{ ind.description }}</small>
              </td>
              <td class="c-src">
                <span class="src" :class="ind.source_type"><AppIcon :name="ind.source_type === 'computed' ? 'refresh' : 'edit'" :size="12" />{{ ind.source_type === 'computed' ? 'Вычисляется' : 'Вводится' }}</span>
                <small>{{ ind.source_type === 'computed' ? (ind.source_name || ind.source_key) : sourceText(ind).replace('Вводит: ', '') }}</small>
                <small v-if="ind.source_type === 'computed' && ind.owner_service_title" class="faint">{{ ind.owner_service_title }}</small>
              </td>
              <td class="c-rule">
                <RuleBands :rule="ind" compact />
                <small v-if="ind.direction !== 'neutral'" :title="ruleSummary(ind)">{{ ind.direction_label }} · {{ ind.rule_label.toLowerCase() }}<template v-if="ind.default_target !== null"> · цель {{ ind.default_target.toLocaleString('ru-RU') }}</template></small>
              </td>
              <td>{{ ind.rollup_label }}</td>
              <td class="c-kinds">
                <template v-if="ind.expected_kinds.length"><span v-for="k in ind.expected_kinds" :key="k" class="kind">{{ kindLabel[k] || k }}</span></template>
                <span v-else class="faint">где есть значения</span>
              </td>
              <td class="num">
                <span v-if="ind.source_type === 'manual'" :title="count(ind.values_count, VALUE_FORMS)">{{ ind.values_count.toLocaleString('ru-RU') }}</span>
                <span v-else class="faint" title="Вычисляется — не хранится">—</span>
              </td>
              <td><ToggleSwitch :model-value="ind.is_active" :title="ind.is_active ? 'Выключить: показатель перестанет попадать в отчёты' : 'Включить'" @update:model-value="(v) => setActive(ind, v)" /></td>
              <td class="c-act">
                <button class="btn btn-sm btn-ghost btn-icon" type="button" :disabled="!meta.data.value" :aria-label="`Изменить «${ind.name}»`" title="Изменить" @click="edit(ind)"><AppIcon name="edit" :size="14" /></button>
                <button class="btn btn-sm btn-ghost btn-danger btn-icon" type="button" :aria-label="`Удалить «${ind.name}»`" title="Удалить" @click="remove(ind)"><AppIcon name="trash" :size="14" /></button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <ServiceUnitsCard :source-names="sourceNames" />

    <IndicatorEditor v-if="editing && meta.data.value" :indicator="editing.indicator" :meta="meta.data.value" @close="editing = null" @saved="afterSave" />
  </div>
</template>

<style scoped>
.explain { display: flex; gap: 14px; align-items: flex-start; padding: 14px 18px; background: color-mix(in srgb, var(--accent) 5%, var(--surface)); border-color: color-mix(in srgb, var(--accent) 22%, var(--border)); }
.ex-icon { width: 34px; height: 34px; flex: 0 0 34px; display: grid; place-items: center; border-radius: 10px; background: color-mix(in srgb, var(--accent) 14%, transparent); color: var(--accent); }
.explain p { font-size: var(--fs-sm); color: var(--text-2); line-height: 1.55; max-width: 1000px; }
.explain b { color: var(--text); font-weight: 650; }
.stats { display: flex; flex-wrap: wrap; gap: 6px 22px; font-size: var(--fs-sm); color: var(--muted); }
.stats b { color: var(--text); font-size: var(--fs-md); font-weight: 680; margin-right: 3px; }
.group .card-head { flex-wrap: wrap; }
.count { padding: 0 7px; border-radius: var(--radius-pill); background: var(--surface-3); color: var(--text-2); font-size: var(--fs-xs); font-weight: 650; }
.flush { padding: 12px 0 0; }
.cat td { vertical-align: top; font-size: var(--fs-sm); }
.cat tr.off td { color: var(--muted); }
.cat tr.off .c-name strong { color: var(--muted); }
.c-name { min-width: 240px; max-width: 360px; }
.c-name strong { display: block; font-size: var(--fs-base); font-weight: 630; }
.c-name .unit { font-weight: 500; color: var(--muted); }
.c-name code { font-family: var(--font-mono); font-size: var(--fs-xs); color: var(--faint); }
.c-name small { display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; margin-top: 2px; font-size: var(--fs-xs); color: var(--muted); line-height: 1.4; }
.c-src { min-width: 170px; }
.c-src small, .c-rule small { display: block; margin-top: 3px; font-size: var(--fs-xs); color: var(--muted); line-height: 1.4; }
.src { display: inline-flex; align-items: center; gap: 5px; height: 21px; white-space: nowrap; padding: 0 8px; border-radius: var(--radius-pill); font-size: var(--fs-xs); font-weight: 620; background: var(--surface-3); color: var(--text-2); }
.src.computed { background: color-mix(in srgb, var(--chart-2) 13%, transparent); color: color-mix(in srgb, var(--chart-2) 75%, var(--text)); }
.c-rule { min-width: 220px; max-width: 280px; }
.c-kinds { min-width: 120px; }
.kind { display: inline-block; margin: 0 4px 4px 0; padding: 1px 7px; border-radius: 6px; background: var(--surface-3); font-size: var(--fs-xs); color: var(--text-2); }
.faint { color: var(--faint); }
.c-act { white-space: nowrap; text-align: right; }
</style>
