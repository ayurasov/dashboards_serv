<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import AppIcon from '@/components/ui/AppIcon.vue'
import ReasonList from './ReasonList.vue'
import StatusChip from './StatusChip.vue'
import { reportsApi } from '@/api/reports'
import { useAsync } from '@/composables/useAsync'
import { INDICATOR_FORMS, STATUS_ORDER, count, statusSegments } from '@/domain/reports'
import { LIGHT_LABELS } from '@/utils/lights'

/**
 * Карточка «Обзора»: статус области пользователя из сквозного отчёта — статус, подразделения по
 * статусам, пропуски данных, три главные причины и переход к отчёту. Пустой отчёт — карточки нет.
 */
const router = useRouter()
const { data } = useAsync(() => reportsApi.summary())
const show = computed(() => data.value && !data.value.empty)
const title = computed(() => (data.value?.roots?.length === 1 ? data.value.roots[0].name : 'ваша область'))
const segments = computed(() => statusSegments(data.value?.counts || {}))
const total = computed(() => STATUS_ORDER.reduce((sum, k) => sum + (data.value?.counts?.[k] || 0), 0))
const notes = computed(() => (data.value?.roots || []).filter((r) => r.note))
function open(unit) {
  router.push({ path: '/reports', query: unit ? { unit: String(unit) } : {} })
}
</script>

<template>
  <section v-if="show" class="card rsum" :class="`s-${data.status}`" data-testid="report-summary">
    <div class="rs-status">
      <span class="lamp" aria-hidden="true"><i /></span>
      <div class="rs-titles">
        <p class="eyebrow">Сквозной отчёт · {{ data.period_label }}</p>
        <h2>Статус: {{ title }}</h2>
        <div class="rs-line">
          <StatusChip :status="data.status" :label="data.status_label" size="lg" />
          <span class="muted">{{ count(data.indicators, INDICATOR_FORMS) }} в отчёте</span>
        </div>
      </div>
    </div>

    <div v-if="total > 1" class="rs-counts">
      <span class="rs-label">Подразделения · {{ total }}</span>
      <div class="bar" role="img" :aria-label="segments.map((s) => `${LIGHT_LABELS[s.light]}: ${s.value}`).join(', ')">
        <span v-for="s in segments" :key="s.light" :class="s.light" :style="{ flexGrow: s.value }" />
      </div>
      <div class="legend">
        <span v-for="l in ['red', 'yellow', 'green']" :key="l" :class="{ zero: !data.counts[l] }"><i :class="l" />{{ LIGHT_LABELS[l] }} <b class="num">{{ data.counts[l] || 0 }}</b></span>
      </div>
    </div>

    <div class="rs-why">
      <span class="rs-label">Главные причины</span>
      <ReasonList v-if="data.top.length" :items="data.top" dense @select="open" />
      <p v-else class="ok"><AppIcon name="check" :size="14" :stroke="2.4" />Все оценённые показатели в норме</p>
    </div>

    <footer class="rs-foot">
      <p v-if="data.missing_total" class="miss" role="alert">
        <AppIcon name="alert" :size="14" /><span>Не заполнено показателей: <b class="num">{{ data.missing_total }}</b> — критичное нарушение полноты</span>
      </p>
      <p v-for="r in notes" :key="r.id" class="note"><AppIcon name="eye" :size="14" /><span>{{ r.note.status_label }}: {{ r.note.comment }}</span></p>
      <span class="spacer" />
      <router-link to="/reports" class="btn btn-sm" data-testid="report-summary-open">Открыть сквозной отчёт <AppIcon name="chevron-right" :size="14" /></router-link>
    </footer>
  </section>
</template>

<style scoped>
.rsum {
  --tone: var(--light-gray);
  position: relative; display: grid; grid-template-columns: minmax(250px, 4fr) minmax(220px, 3fr) minmax(0, 6fr); overflow: hidden;
  background: linear-gradient(110deg, color-mix(in srgb, var(--tone) 8%, var(--surface)) 0%, var(--surface) 40%);
}
.rsum::before { content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 4px; background: var(--tone); }
.s-green { --tone: var(--light-green); }
.s-yellow { --tone: var(--light-yellow); }
.s-red { --tone: var(--light-red); }
.rs-status { display: flex; gap: 14px; padding: 20px 18px 16px 24px; min-width: 0; }
.lamp { width: 44px; height: 44px; flex: 0 0 44px; border-radius: 50%; display: grid; place-items: center; background: color-mix(in srgb, var(--tone) 16%, transparent); }
.lamp i { width: 22px; height: 22px; border-radius: 50%; background: var(--tone); box-shadow: 0 0 0 4px color-mix(in srgb, var(--tone) 22%, transparent); }
.rs-titles { min-width: 0; }
.eyebrow { font-size: var(--fs-xs); font-weight: 650; letter-spacing: .05em; text-transform: uppercase; color: var(--muted); }
h2 { margin-top: 3px; font-size: var(--fs-lg); line-height: 1.25; overflow-wrap: anywhere; }
.rs-line { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 10px; margin-top: 8px; font-size: var(--fs-xs); }
.rs-label { display: block; margin-bottom: 8px; font-size: var(--fs-xs); font-weight: 650; letter-spacing: .05em; text-transform: uppercase; color: var(--muted); }
.rs-counts { padding: 20px 18px 16px; border-left: 1px solid var(--border); min-width: 0; }
.bar { display: flex; gap: 2px; height: 8px; border-radius: 99px; overflow: hidden; background: var(--surface-3); }
.bar span { flex-basis: 0; min-width: 6px; }
.bar .red, .legend i.red { background: var(--light-red); }
.bar .yellow, .legend i.yellow { background: var(--light-yellow); }
.bar .green, .legend i.green { background: var(--light-green); }
.bar .gray { background: var(--light-gray); }
.legend { display: flex; flex-wrap: wrap; gap: 4px 12px; margin-top: 10px; font-size: var(--fs-xs); color: var(--text-2); }
.legend span { display: inline-flex; align-items: center; gap: 5px; }
.legend .zero { color: var(--faint); }
.legend i { width: 7px; height: 7px; border-radius: 50%; }
.legend b { color: var(--text); }
.legend .zero b { color: var(--faint); }
.rs-why { padding: 20px 18px 12px; border-left: 1px solid var(--border); min-width: 0; }
.rs-why .rs-label { margin-bottom: 4px; padding-left: 8px; }
.ok { display: flex; align-items: center; gap: 6px; padding: 4px 8px; font-size: var(--fs-sm); color: var(--text-2); }
.ok :deep(svg) { color: var(--light-green); }
.rs-foot { grid-column: 1 / -1; display: flex; flex-wrap: wrap; align-items: center; gap: 8px 16px; padding: 10px 18px 10px 24px; border-top: 1px solid var(--border); background: var(--surface-2); font-size: var(--fs-sm); }
.miss { display: inline-flex; align-items: flex-start; gap: 6px; color: var(--light-red); font-weight: 560; line-height: 1.4; }
.miss :deep(svg), .note :deep(svg) { flex: 0 0 auto; margin-top: 2px; }
.miss b { font-weight: 700; }
.note { display: inline-flex; align-items: flex-start; gap: 6px; min-width: 0; color: var(--accent); line-height: 1.4; }
@media (max-width: 1100px) {
  .rsum { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); }
  .rs-why { grid-column: 1 / -1; border-left: 0; border-top: 1px solid var(--border); }
}
@media (max-width: 640px) {
  .rsum { grid-template-columns: minmax(0, 1fr); }
  .rs-counts { border-left: 0; border-top: 1px solid var(--border); padding: 14px 16px; }
  .rs-status { padding: 16px 16px 14px 20px; }
  .rs-why { padding: 14px 8px 8px; }
  .rs-foot { padding: 10px 16px 12px 20px; }
  .rs-foot .btn { width: 100%; }
}
</style>
