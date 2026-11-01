<script setup>
import { computed } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import FilterBar from '@/components/ui/FilterBar.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import SegmentedControl from '@/components/ui/SegmentedControl.vue'
import EChart from '@/components/charts/EChart.vue'
import NaumenKpi from '@/components/tp/NaumenKpi.vue'
import NaumenChartCard from '@/components/tp/NaumenChartCard.vue'
import { axisNumber, chartColors, cssVar } from '@/components/charts/echarts'
import { tpApi } from '@/api/services'
import { useAsync } from '@/composables/useAsync'
import { useQueryState } from '@/composables/useQueryState'
import { useAppStore } from '@/stores/app'
import { usePaletteStore } from '@/stores/palette'
import { formatNumber, formatPercent, monthLabel, plural } from '@/utils/format'
import {
  DIVERGENCE, QUICK_MONTHS, QUICK_WEEKS, coverageLight, divergenceRows, filterByYear, formatDeviation, formatHours,
  formatSigned, hoursHint, lastPeriods, parsePeriod, periodCount, share, sumBy, weekAxisLabel, weekRangeText,
  withReport, yearsOf,
} from '@/domain/naumen'

const app = useAppStore()
const palette = usePaletteStore()
const { state: f, reset, isDefault } = useQueryState({ by: 'weeks', year: 0, last: 26, basis: 'typical', only: false })
const { data, loading } = useAsync(() => tpApi.naumenMatch())

const weekly = computed(() => f.by === 'weeks')
const unit = computed(() => (weekly.value ? 'weeks' : 'months'))
const QUICK = computed(() => (weekly.value ? QUICK_WEEKS : QUICK_MONTHS))
const base = computed(() => (weekly.value ? data.value?.weeks || [] : withReport(data.value?.months || [])))
const years = computed(() => yearsOf(base.value))
const rows = computed(() => lastPeriods(filterByYear(base.value, f.year), f.last))
const first = computed(() => loading.value && !data.value)
const noReport = computed(() => !!data.value && !data.value.weeks_count)

function setBy(value) {
  if (value === f.by) return
  f.by = value
  f.last = value === 'weeks' ? 26 : 12
}
function pickYear(year) {
  f.year = year
  if (year) f.last = 0
}

// ---------- показатели ----------
const tpReceived = computed(() => sumBy(rows.value, 'tp_new_received'))
const nmRegistered = computed(() => sumBy(rows.value, 'naumen_registered'))
const coverage = computed(() => share(nmRegistered.value, tpReceived.value))
const tpSolved = computed(() => sumBy(rows.value, 'tp_solved'))
const nmSolved = computed(() => sumBy(rows.value, 'naumen_solved'))
const nmOverdue = computed(() => sumBy(rows.value, 'naumen_overdue'))
const div = computed(() => divergenceRows(rows.value, f.basis))
const flagged = computed(() => div.value.rows.filter((r) => r.level))
const strong = computed(() => flagged.value.filter((r) => r.level === 'red').length)
const periodWord = (n) => (weekly.value ? plural(n, ['неделя', 'недели', 'недель']) : plural(n, ['месяц', 'месяца', 'месяцев']))
const periodWordGen = (n) => (weekly.value ? plural(n, ['недели', 'недель', 'недель']) : plural(n, ['месяца', 'месяцев', 'месяцев']))
const summary = computed(() => {
  const list = rows.value
  if (!list.length) return ''
  const name = (r) => (weekly.value ? r.period : monthLabel(r.period, true))
  return `${name(list[0])} — ${name(list[list.length - 1])} · ${periodCount(list.length, unit.value)}`
})

// ---------- графики ----------
const theme = computed(() => {
  void app.resolvedTheme
  void palette.colors
  const c = chartColors()
  return { report: c[1], naumen: c[3], muted: cssVar('--muted'), border: cssVar('--border') }
})
const SOURCE = { report: 'Отчёт ТП', naumen: 'Naumen' }
const categories = computed(() => rows.value.map((r) => r.period))
const axisLabel = (value) => (weekly.value ? weekAxisLabel(value) : monthLabel(value, true))
const dot = (color) => `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px;background:${color}"></span>`
function titleOf(index) {
  const r = rows.value[index]
  if (!r) return ''
  const p = parsePeriod(r.period)
  const text = p ? `${r.period} <span style="color:${theme.value.muted};font-weight:400">· ${weekRangeText(p.year, p.week)}</span>` : monthLabel(r.period)
  return `<div style="margin-bottom:4px;font-weight:600">${text}</div>`
}
const dense = computed(() => rows.value.length > 26)
const xAxis = (extra = {}) => ({
  type: 'category', data: categories.value, boundaryGap: !dense.value || extra.boundaryGap,
  axisLabel: { formatter: axisLabel, lineHeight: 14, hideOverlap: true }, ...extra,
})
function pairSeries(name, values, color) {
  if (dense.value) {
    return { name, type: 'line', showSymbol: false, symbolSize: 7, connectNulls: true, lineStyle: { width: 2 }, itemStyle: { color }, data: values }
  }
  return { name, type: 'bar', barMaxWidth: 16, barGap: '20%', itemStyle: { color, borderRadius: [4, 4, 0, 0] }, data: values }
}
function pairOption(tpKey, nmKey, format = (v) => formatNumber(v)) {
  const { report, naumen } = theme.value
  return {
    legend: { data: [SOURCE.report, SOURCE.naumen] },
    tooltip: {
      formatter: (items) => {
        const r = rows.value[items[0].dataIndex]
        const s = share(r?.[nmKey], r?.[tpKey])
        const tail = s === null ? '' : `<div style="margin-top:4px;color:${theme.value.muted}">В Naumen ${formatPercent(s)} от отчёта</div>`
        return titleOf(items[0].dataIndex) + items.map((p) => `${dot(p.color)}${p.seriesName}: <b>${format(p.value)}</b>`).join('<br>') + tail
      },
    },
    xAxis: xAxis(),
    yAxis: { type: 'value', minInterval: 1, axisLabel: { formatter: axisNumber } },
    series: [
      pairSeries(SOURCE.report, rows.value.map((r) => r[tpKey]), report),
      pairSeries(SOURCE.naumen, rows.value.map((r) => r[nmKey]), naumen),
    ],
  }
}
const receivedOption = computed(() => pairOption('tp_new_received', 'naumen_registered'))
const solvedOption = computed(() => pairOption('tp_solved', 'naumen_solved'))

/** РусГидро: часы и заявки — разные единицы, поэтому два графика с общей осью времени, а не две оси Y. */
const rushydroOption = computed(() => {
  const { report, naumen, muted } = theme.value
  const series = (name, key, color, i) => (dense.value
    ? { name, type: 'line', xAxisIndex: i, yAxisIndex: i, showSymbol: false, connectNulls: true, lineStyle: { width: 2 }, itemStyle: { color }, areaStyle: { opacity: 0.1 }, data: rows.value.map((r) => r[key]) }
    : { name, type: 'bar', xAxisIndex: i, yAxisIndex: i, barMaxWidth: 16, itemStyle: { color, borderRadius: [4, 4, 0, 0] }, data: rows.value.map((r) => r[key]) })
  const sub = (text, top) => ({ text, left: 0, top, textStyle: { fontSize: 11, fontWeight: 500, color: muted } })
  return {
    legend: { show: false },
    title: [sub('Трудозатраты по РусГидро, ч · отчёт ТП', 0), sub('Заявки организаций РусГидро, шт. · Naumen', '50%')],
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    grid: [
      { left: 8, right: 16, top: 22, height: '32%', containLabel: true },
      { left: 8, right: 16, top: '62%', bottom: 4, containLabel: true },
    ],
    tooltip: {
      formatter: (items) => {
        const r = rows.value[items[0].dataIndex]
        return `${titleOf(items[0].dataIndex)}${dot(report)}Трудозатраты: <b>${formatHours(r?.tp_rushydro_hours)}</b><br>${dot(naumen)}Заявки в Naumen: <b>${formatNumber(r?.naumen_rushydro)}</b>`
      },
    },
    xAxis: [
      xAxis({ gridIndex: 0, axisLabel: { show: false } }),
      xAxis({ gridIndex: 1 }),
    ],
    yAxis: [
      { type: 'value', gridIndex: 0, splitNumber: 3, axisLabel: { formatter: axisNumber } },
      { type: 'value', gridIndex: 1, splitNumber: 3, minInterval: 1, axisLabel: { formatter: axisNumber } },
    ],
    series: [series('Трудозатраты', 'tp_rushydro_hours', report, 0), series('Заявки', 'naumen_rushydro', naumen, 1)],
  }
})

const timeOption = computed(() => {
  const { report, naumen } = theme.value
  const line = (name, key, color) => ({ name, type: 'line', smooth: 0.25, smoothMonotone: 'x', showSymbol: !dense.value, symbolSize: 7, connectNulls: true, lineStyle: { width: 2 }, itemStyle: { color }, data: rows.value.map((r) => r[key]) })
  return {
    legend: { data: ['Отчёт ТП · AlterOS', 'Naumen · от регистрации до решения'] },
    tooltip: {
      formatter: (items) => titleOf(items[0].dataIndex) + items
        .map((p) => `${dot(p.color)}${p.seriesName}: <b>${formatHours(p.value)}</b> <span style="color:${theme.value.muted}">${hoursHint(p.value)}</span>`).join('<br>'),
    },
    xAxis: xAxis({ boundaryGap: false }),
    yAxis: { type: 'log', logBase: 10, min: 1, axisLabel: { formatter: axisNumber } },
    series: [line('Отчёт ТП · AlterOS', 'tp_altos_avg_time', report), line('Naumen · от регистрации до решения', 'naumen_avg_resolve_hours', naumen)],
  }
})

// ---------- таблица расхождений ----------
const tableRows = computed(() => {
  const list = [...div.value.rows].reverse()
  return f.only ? list.filter((r) => r.level) : list
})
const expectedText = computed(() => {
  const e = div.value.expected
  if (f.basis === 'direct') return 'Ожидается, что в Naumen столько же заявок, сколько в отчёте.'
  return `Обычно в Naumen ${formatPercent(e.received, 0)} принятых по отчёту заявок и ${formatPercent(e.solved, 0)} решённых — это ожидаемая доля для выбранного периода.`
})
const levelText = `Жёлтым — доля отличается от ожидаемой больше чем на ${DIVERGENCE.yellow * 100}%, красным — больше чем на ${DIVERGENCE.red * 100}%. `
  + `Не подсвечиваются отклонения в пределах обычных случайных колебаний (на малых числах они велики) и периоды, где по отчёту меньше ${DIVERGENCE.minBase} заявок.`
function cellTitle(d, expected) {
  if (d.share === null) return ''
  const exp = f.basis === 'direct' ? 'один к одному' : `обычная ${formatPercent(expected, 0)}`
  return `Отчёт − Naumen: ${formatSigned(d.diff)}. Доля Naumen ${formatPercent(d.share, 0)} (${exp}), отклонение ${formatDeviation(d.deviation)}`
}
function periodName(r) {
  return weekly.value ? r.period : monthLabel(r.period)
}
function periodSub(r) {
  return weekly.value ? weekRangeText(r.year, r.week, { short: true }) : ''
}

const NOTES = computed(() => ({
  received: `«Принято новых заявок» из недельного отчёта и заявки, зарегистрированные в Naumen за ту же ${weekly.value ? 'ISO-неделю' : 'календарный месяц'}. `
    + 'Стабильная доля Naumen означает, что часть обращений просто не регистрируется в системе; резкие отклонения — повод сверить период.',
  solved: '«Решено за неделю» из отчёта и заявки Naumen с датой решения в этом периоде. Отчёт может считать решённые обращения, закрытые без заявки.',
  rushydro: 'Часы работы с РусГидро по отчёту и заявки организаций группы в Naumen — по названию (РусГидро, ГЭС, энерго…). Единицы разные, поэтому сравнивайте форму кривых, а не значения.',
  time: 'Отчёт — среднее время решения AlterOS. Naumen — календарное время от регистрации до решения, вместе с ожиданием и выходными, поэтому почти всегда больше.',
}))
</script>

<template>
  <div class="page">
    <PageHeader title="Отчёт и Naumen" description="Недельный отчёт техподдержки в сравнении с заявками Naumen Service Desk" />

    <EmptyState v-if="noReport" icon="layers" title="Сравнивать пока не с чем"
                text="Для сопоставления нужны недели отчёта ТП и выгрузка заявок Naumen. Загрузите их на страницах «Недельный отчёт» и «Заявки Naumen».">
      <router-link to="/tp/registry" class="btn">Недельный отчёт</router-link>
      <router-link to="/tp/naumen" class="btn">Заявки Naumen</router-link>
    </EmptyState>

    <template v-else>
      <FilterBar :summary="summary" :resettable="!isDefault()" @reset="reset">
        <div class="field"><span>Шаг</span>
          <SegmentedControl :modelValue="f.by" size="sm" :options="[{ value: 'weeks', label: 'Недели' }, { value: 'months', label: 'Месяцы' }]" @update:modelValue="setBy" />
        </div>
        <div class="field"><span>Период</span>
          <div class="row-wrap chips">
            <button v-for="q in QUICK" :key="q.value" type="button" class="chip" :class="{ active: f.last === q.value }" @click="f.last = q.value">{{ q.label }}</button>
          </div>
        </div>
        <div class="field"><span>Год</span>
          <div class="row-wrap chips">
            <button type="button" class="chip" :class="{ active: !f.year }" @click="pickYear(0)">Все</button>
            <button v-for="y in years" :key="y" type="button" class="chip num" :class="{ active: f.year === y }" @click="pickYear(y)">{{ y }}</button>
          </div>
        </div>
      </FilterBar>

      <EmptyState v-if="data && !rows.length" icon="filter" title="Нет периодов по выбранным фильтрам" text="Выберите другой год или период.">
        <button class="btn" type="button" @click="reset"><AppIcon name="refresh" :size="14" />Сбросить фильтры</button>
      </EmptyState>

      <template v-else>
        <div class="kpis">
          <NaumenKpi label="Принято по отчёту" :value="tpReceived" :digits="0" :caption="`за ${periodCount(rows.length, unit)}`" :loading="first" />
          <NaumenKpi label="Зарегистрировано в Naumen" :value="nmRegistered" :caption="`за те же ${weekly ? 'недели' : 'месяцы'}`" :loading="first" />
          <NaumenKpi label="Доля заявок в Naumen" :value="coverage" unit="%" :light="coverageLight(coverage)" caption="зарегистрировано от принятых по отчёту"
                     hint="От 85% — норма, от 60% — внимание, меньше — критично" :loading="first" />
          <NaumenKpi label="Решено по отчёту" :value="tpSolved" :digits="0" :caption="`в Naumen — ${formatNumber(nmSolved)} (${formatPercent(share(nmSolved, tpSolved), 0)})`" :loading="first" />
          <NaumenKpi label="Просрочено в Naumen" :value="nmOverdue" :caption="`${formatPercent(share(nmOverdue, nmRegistered))} от зарегистрированных`" :loading="first" />
          <NaumenKpi :label="`${weekly ? 'Недель' : 'Месяцев'} с расхождением`" :value="flagged.length" :light="strong ? 'red' : flagged.length ? 'yellow' : 'green'"
                     :caption="`из ${rows.length}${strong ? `, сильных — ${strong}` : ''}`" :hint="levelText" :loading="first" />
        </div>

        <div class="grid grid-2">
          <NaumenChartCard title="Принято и зарегистрировано" :hint="`Заявок за ${weekly ? 'неделю' : 'месяц'}`" :note="NOTES.received" :loading="first" :empty="!rows.length">
            <EChart :option="receivedOption" />
          </NaumenChartCard>
          <NaumenChartCard title="Решено" :hint="`Заявок за ${weekly ? 'неделю' : 'месяц'}`" :note="NOTES.solved" :loading="first" :empty="!rows.length">
            <EChart :option="solvedOption" />
          </NaumenChartCard>
          <NaumenChartCard title="РусГидро: трудозатраты и заявки" hint="Два ряда с общей шкалой времени" :note="NOTES.rushydro" :height="300" :loading="first" :empty="!rows.length">
            <EChart :option="rushydroOption" />
          </NaumenChartCard>
          <NaumenChartCard title="Среднее время решения" hint="Часы, логарифмическая шкала: каждая линия сетки — в 10 раз больше" :note="NOTES.time" :height="300" :loading="first" :empty="!rows.length">
            <EChart :option="timeOption" />
          </NaumenChartCard>
        </div>

        <section class="card">
          <header class="card-head table-head">
            <div class="titles">
              <h3>Расхождения по {{ weekly ? 'неделям' : 'месяцам' }}</h3>
              <p class="hint">{{ expectedText }} {{ levelText }}</p>
            </div>
            <span class="spacer" />
            <div class="table-tools">
              <SegmentedControl v-model="f.basis" size="sm" :options="[{ value: 'typical', label: 'С обычной долей', title: 'Сравнивать долю Naumen с обычной для выбранного периода' }, { value: 'direct', label: 'Один к одному', title: 'Ожидать в Naumen столько же заявок, сколько в отчёте' }]" />
              <button type="button" class="chip" :class="{ active: f.only }" :aria-pressed="f.only" @click="f.only = !f.only">
                Только расхождения<span class="num chip-count">{{ flagged.length }}</span>
              </button>
            </div>
          </header>
          <div class="card-body flush">
            <div v-if="first" class="skeleton" style="height: 320px; margin: 0 16px 16px" />
            <div v-else class="table-wrap match-wrap scroll-thin">
              <table class="table table-compact match">
                <thead>
                  <tr class="head-groups">
                    <th rowspan="2" class="sticky-col">{{ weekly ? 'Неделя' : 'Месяц' }}</th>
                    <th colspan="3" class="group-th">Принято</th>
                    <th colspan="3" class="group-th">Решено</th>
                    <th rowspan="2" class="num group-th solo" title="«Итого в работе заявок» из отчёта; для месяцев — среднее по неделям">В работе<span class="th-sub">отчёт</span></th>
                    <th colspan="2" class="group-th">РусГидро</th>
                    <th colspan="2" class="group-th">Время решения, ч</th>
                    <th rowspan="2" class="num group-th solo">Просрочено<span class="th-sub">Naumen</span></th>
                  </tr>
                  <tr class="head-cols">
                    <th class="num group-start">Отчёт</th><th class="num">Naumen</th><th class="num" title="Доля Naumen от отчёта">Доля</th>
                    <th class="num group-start">Отчёт</th><th class="num">Naumen</th><th class="num" title="Доля Naumen от отчёта">Доля</th>
                    <th class="num group-start" title="Трудозатраты по РусГидро, ч">Часы</th><th class="num" title="Заявки организаций РусГидро в Naumen">Заявки</th>
                    <th class="num group-start" title="Среднее время решения AlterOS по отчёту">Отчёт</th><th class="num" title="От регистрации до решения">Naumen</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="r in tableRows" :key="r.period" :class="r.level ? `flag-${r.level}` : ''">
                    <td class="sticky-col">
                      <div class="period"><span class="period-code num">{{ periodName(r) }}</span></div>
                      <div v-if="periodSub(r)" class="period-dates num">{{ periodSub(r) }}</div>
                    </td>
                    <template v-for="pair in [['received', 'tp_new_received', 'naumen_registered'], ['solved', 'tp_solved', 'naumen_solved']]" :key="pair[0]">
                      <td class="num group-start">{{ formatNumber(r[pair[1]], { digits: 0 }) }}</td>
                      <td class="num">{{ formatNumber(r[pair[2]]) }}</td>
                      <td class="num" :title="cellTitle(r[pair[0]], div.expected[pair[0]])">
                        <span v-if="r[pair[0]].level" class="badge" :class="`badge-${r[pair[0]].level}`">{{ formatPercent(r[pair[0]].share, 0) }}</span>
                        <span v-else class="muted">{{ formatPercent(r[pair[0]].share, 0) }}</span>
                      </td>
                    </template>
                    <td class="num group-start">{{ formatNumber(r.tp_in_work, { digits: 0 }) }}</td>
                    <td class="num group-start">{{ formatNumber(r.tp_rushydro_hours, { digits: 0 }) }}</td>
                    <td class="num">{{ formatNumber(r.naumen_rushydro) }}</td>
                    <td class="num group-start">{{ formatNumber(r.tp_altos_avg_time, { digits: 1 }) }}</td>
                    <td class="num" :title="hoursHint(r.naumen_avg_resolve_hours)">{{ formatNumber(r.naumen_avg_resolve_hours, { digits: 0 }) }}</td>
                    <td class="num group-start">{{ formatNumber(r.naumen_overdue) }}</td>
                  </tr>
                </tbody>
              </table>
              <EmptyState v-if="!tableRows.length" compact icon="check" title="Заметных расхождений нет"
                          :text="`Во всех ${periodWordGen(rows.length)} выборки доля Naumen близка к ожидаемой.`" />
            </div>
          </div>
          <footer class="legend">
            <span>{{ weekly ? 'Недели сопоставляются по году и номеру ISO-недели.' : 'Месяцы — календарные; неделя отчёта относится к месяцу своего понедельника. Месяцы без недельного отчёта не показываются.' }}</span>
            <span class="spacer" />
            <span class="muted">{{ tableRows.length }} {{ periodWord(tableRows.length) }}</span>
            <router-link to="/tp/naumen" class="link">Заявки Naumen</router-link>
          </footer>
        </section>
      </template>
    </template>
  </div>
</template>

<style scoped>
.chips { gap: 6px; }
.kpis { display: grid; gap: var(--sp-4); grid-template-columns: repeat(6, minmax(0, 1fr)); }
@media (max-width: 1360px) { .kpis { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
@media (max-width: 640px) { .kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); } }

.table-head { flex-wrap: wrap; align-items: flex-start; gap: var(--sp-3); }
.table-head .titles { flex: 1 1 420px; min-width: 0; }
.table-head .hint { margin-top: 3px; max-width: 860px; font-size: var(--fs-xs); color: var(--muted); line-height: 1.45; }
.table-tools { display: flex; align-items: center; gap: var(--sp-2); flex-wrap: wrap; }
.chip-count { margin-left: 2px; font-size: var(--fs-xs); opacity: .65; }
.flush { padding: var(--sp-3) 0 0; }

.match-wrap { max-height: min(70vh, 720px); border-radius: 0; }
.match { font-size: var(--fs-sm); }
.match .head-groups th { top: 0; height: 34px; line-height: 18px; }
.match .head-cols th { top: 34px; }
.match .group-th { border-left: 1px solid var(--border); color: var(--text-2); }
.match .group-th.solo { vertical-align: bottom; }
.th-sub { display: block; font-size: 10.5px; text-transform: none; letter-spacing: 0; font-weight: 450; color: var(--muted); }
.group-start { border-left: 1px solid var(--border); }
.sticky-col { position: sticky; left: 0; z-index: 2; background: var(--surface); box-shadow: inset -1px 0 0 var(--border); min-width: 120px; }
.match thead th.sticky-col { z-index: 4; background: var(--surface-2); vertical-align: bottom; }
.match tbody tr:hover td.sticky-col { background: var(--row-hover); }
.match tbody tr.flag-red td.sticky-col { box-shadow: inset 3px 0 0 var(--light-red), inset -1px 0 0 var(--border); }
.match tbody tr.flag-yellow td.sticky-col { box-shadow: inset 3px 0 0 var(--light-yellow), inset -1px 0 0 var(--border); }
.period-code { font-weight: 620; color: var(--text); white-space: nowrap; }
.period-dates { font-size: var(--fs-xs); color: var(--muted); }
.legend { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 14px; padding: 10px var(--sp-5); border-top: 1px solid var(--border); font-size: var(--fs-xs); color: var(--text-2); }
</style>
