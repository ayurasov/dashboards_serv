<script setup>
import { computed } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import MissingAlert from './MissingAlert.vue'
import ReasonList from './ReasonList.vue'
import { STATUS_ORDER, UNIT_FORMS, count, noteByline, reasonText, statusSegments, unitsByStatus, violationsText } from '@/domain/reports'
import { LIGHT_LABELS } from '@/utils/lights'
import { plural } from '@/utils/format'

/**
 * Сводка вершины области: крупный статус, подразделения по статусам (полоса и «кто именно»),
 * «почему такой статус», пропуски данных и заметка «под контролем».
 */
const props = defineProps({
  data: { type: Object, required: true },
  rated: { type: Number, default: 0 },
  hiddenNote: { type: String, default: '' },
  canEnter: { type: Boolean, default: false },
  canOpen: { type: Function, default: () => true },
})
const emit = defineEmits(['select'])

const units = computed(() => props.data.units || [])
const roots = computed(() => units.value.filter((u) => (props.data.roots || []).includes(u.id)))
const single = computed(() => (roots.value.length === 1 ? roots.value[0] : null))
const summary = computed(() => props.data.summary || {})
const status = computed(() => summary.value.status || 'gray')

const counts = computed(() => summary.value.units || {})
const total = computed(() => STATUS_ORDER.reduce((sum, k) => sum + (counts.value[k] || 0), 0))
const segments = computed(() => statusSegments(counts.value))
const byStatus = computed(() => unitsByStatus(units.value, props.data.roots))
// Кто именно: сначала верхние уровни (ближе к вершине), не больше трёх на статус
const LIMIT = 3
const who = computed(() => ['red', 'yellow'].filter((s) => byStatus.value[s].length).map((s) => {
  const list = byStatus.value[s].map((u, i) => ({ u, i })).sort((a, b) => a.u.depth - b.u.depth || a.i - b.i).map((x) => x.u)
  return { status: s, label: LIGHT_LABELS[s], items: list.slice(0, LIMIT), more: list.length - LIMIT, rest: list.slice(LIMIT).map((u) => u.name).join(', ') }
}))

// Причины: у одной вершины — её объяснение; у нескольких — причины худших вершин
const reasons = computed(() => {
  if (single.value) return single.value.explanation
  const ordered = [...roots.value].sort((a, b) => STATUS_ORDER.indexOf(a.status) - STATUS_ORDER.indexOf(b.status))
  const items = ordered.flatMap((r) => r.explanation?.items || [])
  return { status: status.value, text: ordered[0]?.explanation?.text || '', items: items.slice(0, 5), more: Math.max(0, items.length - 5) }
})
const okText = computed(() => reasonText(reasons.value?.text) || 'Оценённых показателей нет')

const basis = computed(() => {
  const n = props.rated
  if (!n) return 'Нет оценённых показателей за период'
  const forms = props.hiddenNote ? ['доступному показателю', 'доступным показателям', 'доступным показателям'] : ['показателю', 'показателям', 'показателям']
  return `Статус по ${n.toLocaleString('ru-RU')} ${plural(n, forms)}`
})
const violations = computed(() => violationsText(summary.value))
const notes = computed(() => roots.value.filter((r) => r.note))
</script>

<template>
  <section class="hero card" :class="`s-${status}`" data-testid="report-hero" :aria-label="`Статус: ${summary.status_label}`">
    <div class="h-main">
      <div class="h-status">
        <span class="h-lamp" aria-hidden="true"><i /></span>
        <div class="h-titles">
          <p class="h-eyebrow">Статус за {{ data.period_label.toLowerCase() }}</p>
          <h2 class="h-word" data-testid="report-status">{{ summary.status_label }}</h2>
          <p class="h-where">
            <template v-if="single"><b>{{ single.name }}</b><span class="muted"> · {{ single.kind_label }}</span></template>
            <template v-else><b>Ваша область</b><span class="muted"> · {{ count(roots.length, UNIT_FORMS) }}</span></template>
          </p>
          <p class="h-basis" title="Статус — худший из статусов показателей подразделения и вложенных подразделений">{{ basis }}</p>
        </div>
      </div>

      <div v-if="total > 1" class="h-dist">
        <div class="d-head">
          <span>Подразделения по статусу</span>
          <b class="num">{{ total }}</b>
        </div>
        <div class="seg-bar" role="img" :aria-label="segments.map((s) => `${LIGHT_LABELS[s.light]}: ${s.value}`).join(', ')">
          <span v-for="s in segments" :key="s.light" :class="s.light" :style="{ flexGrow: s.value }" :title="`${LIGHT_LABELS[s.light]}: ${s.value}`" />
        </div>
        <ul class="seg-legend">
          <li v-for="s in ['red', 'yellow', 'green']" :key="s" :class="{ zero: !counts[s] }"><i :class="s" />{{ LIGHT_LABELS[s] }} <b class="num">{{ counts[s] || 0 }}</b></li>
          <li v-if="counts.gray" class="gray"><i class="gray" />{{ LIGHT_LABELS.gray }} <b class="num">{{ counts.gray }}</b></li>
        </ul>
        <dl v-if="who.length" class="who">
          <div v-for="w in who" :key="w.status" :class="`w-${w.status}`">
            <dt>{{ w.label }}</dt>
            <dd>
              <button v-for="u in w.items" :key="u.id" type="button" class="who-chip" :title="u.path" @click="emit('select', u.id)">{{ u.name }}</button>
              <span v-if="w.more > 0" class="who-more" :title="w.rest">и ещё {{ w.more }}</span>
            </dd>
          </div>
        </dl>
      </div>
    </div>

    <div class="h-why">
      <h3>Почему такой статус</h3>
      <ReasonList v-if="reasons?.items?.length" :items="reasons.items" :can-open="canOpen" @select="(id) => emit('select', id)" />
      <p v-else class="h-ok"><AppIcon name="check" :size="15" :stroke="2.4" />{{ okText }}</p>
      <button v-if="reasons?.more && single" type="button" class="h-more" @click="emit('select', single.id)">
        Ещё {{ reasons.more }} — в панели «{{ single.name }}»<AppIcon name="chevron-right" :size="13" />
      </button>
    </div>

    <footer v-if="summary.missing_total || notes.length" class="h-foot">
      <MissingAlert v-if="summary.missing_total" :items="violations.items" :hidden="violations.hidden" :period="data.period_label" @select="(id) => emit('select', id)">
        <router-link v-if="canEnter && violations.items.length" :to="{ path: '/reports/entry', query: { period: data.period } }" class="btn btn-sm">
          <AppIcon name="edit" :size="13" />Заполнить
        </router-link>
      </MissingAlert>
      <div v-for="r in notes" :key="r.id" class="h-note" data-testid="report-note">
        <span class="n-icon"><AppIcon name="eye" :size="15" /></span>
        <div class="n-text">
          <strong>{{ r.note.status_label }}<template v-if="!single"> · {{ r.name }}</template></strong>
          <p>{{ r.note.comment }}</p>
          <small v-if="noteByline(r.note)">{{ noteByline(r.note) }}</small>
        </div>
      </div>
    </footer>
  </section>
</template>

<style scoped>
.hero {
  --tone: var(--light-gray);
  display: grid; grid-template-columns: minmax(0, 5fr) minmax(0, 7fr); overflow: hidden; position: relative;
}
.s-green { --tone: var(--light-green); }
.s-yellow { --tone: var(--light-yellow); }
.s-red { --tone: var(--light-red); }
.hero::before { content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 4px; background: var(--tone); }

.h-main {
  display: flex; flex-direction: column; gap: 22px; padding: 24px 26px 22px 30px; min-width: 0;
  background: linear-gradient(150deg, color-mix(in srgb, var(--tone) 10%, var(--surface)) 0%, var(--surface) 72%);
}
.h-status { display: flex; align-items: flex-start; gap: 18px; }
.h-lamp { position: relative; width: 56px; height: 56px; flex: 0 0 56px; margin-top: 4px; border-radius: 50%; background: color-mix(in srgb, var(--tone) 16%, transparent); display: grid; place-items: center; }
.h-lamp i { width: 30px; height: 30px; border-radius: 50%; background: var(--tone); box-shadow: 0 0 0 5px color-mix(in srgb, var(--tone) 22%, transparent), 0 6px 18px color-mix(in srgb, var(--tone) 45%, transparent); }
.h-titles { min-width: 0; }
.h-eyebrow { font-size: var(--fs-xs); font-weight: 650; letter-spacing: .06em; text-transform: uppercase; color: var(--muted); }
.h-word { margin-top: 2px; font-size: 40px; line-height: 1.05; font-weight: 720; letter-spacing: -0.025em; color: color-mix(in srgb, var(--tone) 78%, var(--text)); }
.s-gray .h-word { color: var(--text-2); }
.h-where { margin-top: 8px; font-size: var(--fs-md); line-height: 1.35; overflow-wrap: anywhere; }
.h-where b { font-weight: 650; }
.h-basis { margin-top: 3px; font-size: var(--fs-sm); color: var(--muted); }

.h-dist { display: flex; flex-direction: column; gap: 9px; padding-top: 18px; border-top: 1px dashed color-mix(in srgb, var(--tone) 25%, var(--border)); }
.d-head { display: flex; align-items: baseline; justify-content: space-between; font-size: var(--fs-xs); font-weight: 650; letter-spacing: .05em; text-transform: uppercase; color: var(--muted); }
.d-head b { font-size: var(--fs-sm); color: var(--text); letter-spacing: 0; }
.seg-bar { display: flex; gap: 2px; height: 8px; border-radius: 99px; overflow: hidden; background: var(--surface-3); }
.seg-bar span { min-width: 6px; flex-basis: 0; }
.seg-bar span:first-child { border-radius: 99px 0 0 99px; }
.seg-bar span:last-child { border-radius: 0 99px 99px 0; }
.seg-bar span:only-child { border-radius: 99px; }
.seg-bar .red, .seg-legend i.red { background: var(--light-red); }
.seg-bar .yellow, .seg-legend i.yellow { background: var(--light-yellow); }
.seg-bar .green, .seg-legend i.green { background: var(--light-green); }
.seg-bar .gray, .seg-legend i.gray { background: var(--light-gray); }
.seg-legend { display: flex; flex-wrap: wrap; gap: 4px 16px; margin: 0; padding: 0; list-style: none; font-size: var(--fs-sm); color: var(--text-2); }
.seg-legend li { display: inline-flex; align-items: center; gap: 6px; }
.seg-legend li.zero { color: var(--faint); }
.seg-legend i { width: 8px; height: 8px; border-radius: 50%; }
.seg-legend b { color: var(--text); font-weight: 680; }
.seg-legend .zero b { color: var(--faint); }

.who { display: flex; flex-direction: column; gap: 6px; margin: 4px 0 0; }
.who > div { display: grid; grid-template-columns: 74px minmax(0, 1fr); gap: 8px; align-items: baseline; }
.who dt { font-size: var(--fs-xs); font-weight: 620; color: var(--muted); }
.who dd { margin: 0; display: flex; flex-wrap: wrap; gap: 5px; }
.who-chip {
  --c: var(--light-gray); height: 24px; max-width: 100%; padding: 0 9px; border-radius: 7px; border: 1px solid color-mix(in srgb, var(--c) 35%, var(--border));
  background: color-mix(in srgb, var(--c) 9%, var(--surface)); color: var(--text); font-size: var(--fs-xs); font-weight: 580; cursor: pointer;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; transition: border-color var(--t-fast), background var(--t-fast);
}
.w-red .who-chip { --c: var(--light-red); }
.w-yellow .who-chip { --c: var(--light-yellow); }
.who-chip:hover { border-color: var(--c); background: color-mix(in srgb, var(--c) 16%, var(--surface)); }
.who-more { align-self: center; font-size: var(--fs-xs); color: var(--muted); }

.h-why { display: flex; flex-direction: column; gap: 6px; padding: 22px 22px 18px; border-left: 1px solid var(--border); min-width: 0; }
.h-why h3 { padding: 0 10px; font-size: var(--fs-xs); font-weight: 650; letter-spacing: .05em; text-transform: uppercase; color: var(--muted); }
.h-ok { display: flex; align-items: center; gap: 8px; padding: 8px 10px; font-size: var(--fs-base); color: var(--text-2); }
.h-ok :deep(svg) { color: var(--light-green); }
.h-more { align-self: flex-start; display: inline-flex; align-items: center; gap: 4px; margin: 2px 0 0 10px; padding: 0; border: 0; background: transparent; color: var(--accent); font-size: var(--fs-sm); cursor: pointer; }
.h-more:hover { text-decoration: underline; }

.h-foot { grid-column: 1 / -1; display: flex; flex-direction: column; gap: 10px; padding: 14px 22px 16px 30px; border-top: 1px solid var(--border); background: var(--surface-2); }
.h-note { display: flex; align-items: flex-start; gap: 12px; padding: 10px 14px; border-radius: var(--radius); border: 1px solid color-mix(in srgb, var(--accent) 28%, var(--border)); background: color-mix(in srgb, var(--accent) 6%, var(--surface)); }
.n-icon { width: 28px; height: 28px; flex: 0 0 28px; display: grid; place-items: center; border-radius: 50%; background: color-mix(in srgb, var(--accent) 14%, transparent); color: var(--accent); }
.n-text { min-width: 0; font-size: var(--fs-sm); line-height: 1.45; }
.n-text strong { color: var(--accent); font-weight: 650; }
.n-text p { color: var(--text); }
.n-text small { color: var(--muted); font-size: var(--fs-xs); }

@media (max-width: 1100px) {
  .hero { grid-template-columns: minmax(0, 1fr); }
  .h-why { border-left: 0; border-top: 1px solid var(--border); }
}
@media (max-width: 640px) {
  .h-main { padding: 18px 16px 16px 20px; gap: 16px; }
  .h-status { gap: 14px; }
  .h-lamp { width: 44px; height: 44px; flex-basis: 44px; }
  .h-lamp i { width: 22px; height: 22px; }
  .h-word { font-size: 32px; }
  .h-why { padding: 16px 10px 12px; }
  .h-foot { padding: 12px 14px 14px 18px; }
  .who > div { grid-template-columns: minmax(0, 1fr); gap: 4px; }
}
</style>
