<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import PageTabs from '@/components/ui/PageTabs.vue'
import InboxFolder from '@/components/inbox/InboxFolder.vue'
import InboxItemDrawer from '@/components/inbox/InboxItemDrawer.vue'
import InboxRules from '@/components/inbox/InboxRules.vue'
import InboxUploadDialog from '@/components/inbox/InboxUploadDialog.vue'
import InboxWays from '@/components/inbox/InboxWays.vue'
import { inboxApi } from '@/api/inbox'
import { useAsync } from '@/composables/useAsync'
import { useQueryState } from '@/composables/useQueryState'
import { toastError, toastInfo, toastOk } from '@/composables/useToast'
import { useAuthStore } from '@/stores/auth'
import { pageRange } from '@/domain/admin'
import {
  SOURCE_LABELS, STATUS_HINTS, STATUS_LABELS, STATUS_ORDER, fileSize, itemSummary, planBlocked, sourceInfo, statusBadge,
} from '@/domain/inbox'
import { formatDateTime, formatNumber, formatRelative } from '@/utils/format'

/**
 * «Входящие данные» (ADR-0011): все файлы, откуда бы они ни пришли (папка, загрузка, приём по API,
 * подключения), — со статусом, источником, набором и сводкой плана; карточка элемента с планом и
 * действиями; «Загрузить файл». Ведущему входящие (data.manage) — ещё правила «применять сразу» и
 * папка. Остальным (редакторам служб, ведущим структуру и отчёты) — свои наборы и свои загрузки.
 */
const auth = useAuthStore()
const { state: f } = useQueryState({
  tab: 'items', status: '', dataset: '', source: '', q: '', date_from: '', date_to: '', page: 1, page_size: 50, item: 0,
})
const PAGE_SIZES = [25, 50, 100, 200]

const meta = useAsync(() => inboxApi.datasets())
const canManage = computed(() => !!meta.data.value?.can_manage)
const datasets = computed(() => meta.data.value?.datasets || [])
// В фильтре — наборы, элементы которых пользователь видит: ведущему входящие — все, остальным — свои
const filterDatasets = computed(() => (canManage.value ? datasets.value : datasets.value.filter((d) => d.can_apply)))
const sources = computed(() => meta.data.value?.sources || Object.entries(SOURCE_LABELS).map(([key, label]) => ({ key, label })))
const tabs = computed(() => [
  { key: 'items', label: 'Элементы', icon: 'inbox' },
  ...(canManage.value ? [{ key: 'rules', label: 'Правила', icon: 'settings' }, { key: 'folder', label: 'Папка', icon: 'folder' }] : []),
])
const tab = computed({
  get: () => (tabs.value.some((t) => t.key === f.tab) ? f.tab : 'items'),
  set: (v) => { f.tab = v },
})

// ---------------------------------------------------------------- список
const filters = computed(() => ({
  dataset: f.dataset, source: f.source, q: f.q.trim(), date_from: f.date_from, date_to: f.date_to,
}))
const filtered = computed(() => Object.values(filters.value).some(Boolean) || !!f.status)
watch(() => JSON.stringify([filters.value, f.status, f.page_size]), () => { f.page = 1 })
const params = computed(() => ({ ...filters.value, status: f.status, page: f.page, page_size: f.page_size }))

const { data, loading, error, reload } = useAsync(() => inboxApi.list(params.value), { immediate: false })
let timer
watch(params, (now, before) => {
  clearTimeout(timer)
  timer = setTimeout(reload, before && now.q !== before.q ? 300 : 0)
}, { immediate: true, deep: true })
// Счётчик «ожидают» в меню — с сервера (/api/auth/me): обновляется после применения, отклонения и загрузки,
// а при опросе списка — когда без фильтров изменилось число ожидающих (файл пришёл из папки или подключения)
let seenPending = null
watch(data, (d) => {
  if (d && !d.items.length && d.total && f.page > 1) f.page = Math.max(1, Math.ceil(d.total / f.page_size))
  if (!d?.counts || Object.values(filters.value).some(Boolean)) return
  const pending = d.counts.pending || 0
  if (seenPending !== null && pending !== seenPending) auth.refreshInbox()
  seenPending = pending
})

// Новые файлы приходят сами (папка, подключения) — список обновляется, пока страница открыта
let poll
onMounted(() => {
  poll = setInterval(() => {
    if (document.visibilityState === 'visible' && tab.value === 'items' && !f.item && !uploadOpen.value) reload()
  }, 30_000)
})
onBeforeUnmount(() => { clearInterval(poll); clearTimeout(timer) })

const items = computed(() => data.value?.items || [])
const total = computed(() => data.value?.total || 0)
const counts = computed(() => data.value?.counts || {})
const allCount = computed(() => Object.values(counts.value).reduce((a, b) => a + b, 0))
const statusChips = computed(() => STATUS_ORDER
  .filter((s) => counts.value[s] || s === f.status || s === 'pending')
  .map((s) => ({ key: s, label: STATUS_LABELS[s], count: counts.value[s] || 0, hint: STATUS_HINTS[s] })))
const pageCount = computed(() => Math.max(1, Math.ceil(total.value / f.page_size)))
const pages = computed(() => pageRange(f.page, pageCount.value))
const rangeText = computed(() => {
  if (!total.value) return ''
  const from = (f.page - 1) * f.page_size + 1
  const to = Math.min(total.value, f.page * f.page_size)
  return `${formatNumber(from)}–${formatNumber(to)} из ${formatNumber(total.value)}`
})
function go(page) {
  if (page >= 1 && page <= pageCount.value) f.page = page
}
const empty = computed(() => data.value && !allCount.value && !Object.values(filters.value).some(Boolean))

// Путь папки — для пустого состояния ведущему входящие
const folder = useAsync(() => inboxApi.folder(), { immediate: false })
watch([empty, canManage], ([e, m]) => { if (e && m && !folder.data.value) folder.reload() })

// ---------------------------------------------------------------- элемент и загрузка
function open(id) { f.item = id }
function onKey(event, id) {
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    open(id)
  }
}
function changed() {
  reload()
  auth.refreshInbox()
}

const uploadOpen = ref(false)
function uploaded(item) {
  uploadOpen.value = false
  const messages = {
    applied: () => toastOk(`Файл применён: ${item.message || item.dataset_label}`),
    pending: () => (planBlocked(item) ? toastError(`В плане ошибки — файл «${item.filename}» ждёт исправления`) : toastOk('Файл получен — проверьте план и примените')),
    duplicate: () => toastInfo(item.message || 'Этот файл уже получен'),
    received: () => toastInfo('Набор не распознан — выберите его в карточке элемента'),
    error: () => toastError(item.error || 'Файл не удалось обработать'),
  }
  ;(messages[item.status] || (() => toastOk('Файл получен')))()
  reload()
  auth.refreshInbox()
  open(item.id)
}

function resetFilters() {
  Object.assign(f, { status: '', dataset: '', source: '', q: '', date_from: '', date_to: '', page: 1 })
}
function showFolderItems() {
  resetFilters()
  f.tab = 'items'
  f.source = 'folder'
}
</script>

<template>
  <div class="page inbox-page">
    <PageHeader title="Входящие данные" description="Файлы из папки, загрузки, приём по API и подключения: распознавание набора, план, применение">
      <button class="btn btn-ghost" type="button" :disabled="loading" @click="reload(); meta.reload()"><AppIcon name="refresh" :size="15" />Обновить</button>
      <button class="btn btn-primary" type="button" :disabled="!meta.data.value" data-testid="inbox-upload" @click="uploadOpen = true"><AppIcon name="upload" :size="15" />Загрузить файл</button>
    </PageHeader>

    <PageTabs v-if="tabs.length > 1" v-model="tab" :tabs="tabs" label="Разделы входящих" />

    <template v-if="tab === 'items'">
      <InboxWays v-if="empty" :folder-path="folder.data.value?.path || ''" :can-manage="canManage" @upload="uploadOpen = true" @folder="f.tab = 'folder'" />

      <template v-else>
        <div class="chips" role="group" aria-label="Статус">
          <button type="button" class="chip" :class="{ active: !f.status }" :aria-pressed="!f.status" @click="f.status = ''">Все <b class="num">{{ formatNumber(allCount) }}</b></button>
          <button v-for="c in statusChips" :key="c.key" type="button" class="chip" :class="[{ active: f.status === c.key }, `st-${c.key}`]" :aria-pressed="f.status === c.key"
                  :title="c.hint" :data-testid="`status-${c.key}`" @click="f.status = f.status === c.key ? '' : c.key">
            <i class="dot" />{{ c.label }} <b class="num">{{ formatNumber(c.count) }}</b>
          </button>
        </div>

        <div class="card filters" role="search">
          <label class="search"><AppIcon name="search" :size="14" /><input v-model="f.q" type="search" placeholder="Имя файла" aria-label="Поиск по имени файла" data-testid="inbox-search" /></label>
          <select v-model="f.dataset" class="select" aria-label="Набор" :class="{ set: f.dataset }" data-testid="filter-dataset">
            <option value="">Все наборы</option>
            <option value="none">Не распознан</option>
            <option v-for="d in filterDatasets" :key="d.key" :value="d.key">{{ d.label }}</option>
          </select>
          <select v-model="f.source" class="select" aria-label="Источник" :class="{ set: f.source }" data-testid="filter-source">
            <option value="">Все источники</option>
            <option v-for="s in sources" :key="s.key" :value="s.key">{{ s.label }}</option>
          </select>
          <div class="dates">
            <span class="lbl">Получен</span>
            <input v-model="f.date_from" class="input" type="date" aria-label="С даты" :max="f.date_to || undefined" />
            <span class="dash" aria-hidden="true">—</span>
            <input v-model="f.date_to" class="input" type="date" aria-label="По дату" :min="f.date_from || undefined" />
          </div>
          <button v-if="filtered" class="btn btn-ghost btn-sm reset" type="button" @click="resetFilters"><AppIcon name="refresh" :size="13" />Сбросить</button>
        </div>

        <section class="card list-card">
          <div class="table-wrap">
            <table class="table inbox-table" data-testid="inbox-table">
              <thead>
                <tr><th>Файл</th><th>Источник</th><th>Набор</th><th>Статус</th><th>Сводка</th><th class="when">Получен</th></tr>
              </thead>
              <tbody>
                <tr v-for="i in items" :key="i.id" class="clickable" :class="{ current: f.item === i.id }" tabindex="0" :data-item="i.id"
                    :aria-label="`${i.filename}: ${statusBadge(i).label}`" @click="open(i.id)" @keydown="onKey($event, i.id)">
                  <td class="file">
                    <div class="f-cell">
                      <span class="f-icon"><AppIcon name="file" :size="15" /></span>
                      <span class="f-text">
                        <b>{{ i.filename }}</b>
                        <span v-if="i.note" class="f-note" :title="i.note" data-testid="inbox-note">{{ i.note }}</span>
                        <small>{{ fileSize(i.size) }} · № {{ i.id }}</small>
                      </span>
                    </div>
                  </td>
                  <td class="src"><span class="s-label"><AppIcon :name="sourceInfo(i).icon" :size="14" />{{ sourceInfo(i).label }}</span><small v-if="sourceInfo(i).detail && sourceInfo(i).detail !== sourceInfo(i).label">{{ sourceInfo(i).detail }}</small></td>
                  <td class="ds"><span v-if="i.dataset_label">{{ i.dataset_label }}</span><span v-else class="muted">не распознан</span></td>
                  <td><span class="badge" :class="`badge-${statusBadge(i).tone}`">{{ statusBadge(i).label }}</span></td>
                  <td class="sum" :class="{ bad: i.status === 'error' || planBlocked(i) }">{{ itemSummary(i) || '—' }}</td>
                  <td class="when nowrap" :title="formatDateTime(i.received_at)"><span class="num">{{ formatDateTime(i.received_at) }}</span><small>{{ formatRelative(i.received_at) }}</small></td>
                </tr>
              </tbody>
            </table>
            <div v-if="loading && !data" class="skeleton-rows"><div v-for="n in 6" :key="n" class="skeleton" /></div>
            <EmptyState v-else-if="error && !data" compact icon="alert" title="Не удалось загрузить входящие" :text="error.message">
              <button class="btn btn-sm" type="button" @click="reload()">Повторить</button>
            </EmptyState>
            <EmptyState v-else-if="data && !items.length" compact icon="inbox" title="Ничего не найдено" text="Измените фильтры, статус или период.">
              <button class="btn btn-sm" type="button" @click="resetFilters">Сбросить фильтры</button>
            </EmptyState>
          </div>

          <footer v-if="total" class="pager">
            <span class="muted num">{{ rangeText }}</span>
            <span class="spacer" />
            <label class="size">На странице
              <select v-model.number="f.page_size" class="select select-sm"><option v-for="n in PAGE_SIZES" :key="n" :value="n">{{ n }}</option></select>
            </label>
            <nav class="pages" aria-label="Страницы">
              <button class="btn btn-ghost btn-icon btn-sm" type="button" :disabled="f.page <= 1" aria-label="Предыдущая" @click="go(f.page - 1)"><AppIcon name="chevron-left" :size="15" /></button>
              <template v-for="(p, i) in pages" :key="`${p}-${i}`">
                <span v-if="p === '…'" class="gap">…</span>
                <button v-else class="page-btn num" :class="{ active: p === f.page }" type="button" :aria-current="p === f.page ? 'page' : undefined" @click="go(p)">{{ p }}</button>
              </template>
              <button class="btn btn-ghost btn-icon btn-sm" type="button" :disabled="f.page >= pageCount" aria-label="Следующая" @click="go(f.page + 1)"><AppIcon name="chevron-right" :size="15" /></button>
            </nav>
          </footer>
        </section>
        <p v-if="meta.data.value" class="retention muted">Исходные файлы хранятся {{ meta.data.value.retention_days }} дней после обработки; размер файла — до {{ meta.data.value.max_mb }} МБ.</p>
      </template>
    </template>

    <InboxRules v-else-if="tab === 'rules'" :meta="meta.data.value" />
    <InboxFolder v-else-if="tab === 'folder'" :meta="meta.data.value" @show-items="showFolderItems" />

    <InboxItemDrawer v-if="f.item" :id="Number(f.item)" :datasets="datasets" @close="f.item = 0" @changed="changed" @open="open" />
    <InboxUploadDialog v-if="uploadOpen" :datasets="datasets" :max-mb="meta.data.value?.max_mb || 20" @close="uploadOpen = false" @uploaded="uploaded" />
  </div>
</template>

<style scoped>
.chips { display: flex; flex-wrap: wrap; gap: 6px; }
.chip b { font-weight: 700; }
.chip .dot { width: 7px; height: 7px; border-radius: 50%; background: var(--faint); }
.st-pending .dot, .st-received .dot { background: var(--light-yellow); }
.st-error .dot { background: var(--light-red); }
.st-applied .dot { background: var(--light-green); }
.st-recognized .dot { background: var(--accent); }
.chip.active .dot { box-shadow: 0 0 0 2px var(--bg-elevated); }
.filters { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; padding: 12px 16px; }
.filters .select, .filters .input { height: 32px; width: auto; font-size: var(--fs-sm); }
.filters .select { min-width: 160px; max-width: 260px; color: var(--text-2); }
.filters .select.set { color: var(--text); border-color: color-mix(in srgb, var(--accent) 45%, var(--border-strong)); }
.search { display: flex; align-items: center; gap: 8px; height: 32px; padding: 0 10px; border: 1px solid var(--border-strong); border-radius: var(--radius); color: var(--muted); min-width: 200px; flex: 0 1 260px; background: var(--surface); }
.search input { border: 0; outline: 0; background: transparent; width: 100%; color: var(--text); font-size: var(--fs-sm); }
.search:focus-within { border-color: var(--accent); box-shadow: 0 0 0 3px var(--focus); }
.dates { display: inline-flex; align-items: center; gap: 8px; flex-wrap: wrap; min-width: 0; max-width: 100%; }
.dates .input { width: 140px; min-width: 0; flex: 1 1 120px; }
.lbl { font-size: var(--fs-xs); text-transform: uppercase; letter-spacing: .05em; color: var(--muted); font-weight: 620; }
.dash { color: var(--muted); }
.reset { margin-left: auto; }
.list-card { overflow: hidden; }
.inbox-table td { vertical-align: top; }
.inbox-table tr.current td { background: color-mix(in srgb, var(--accent) 6%, transparent); }
.file { min-width: 200px; }
.f-cell { display: flex; gap: 10px; align-items: flex-start; }
.f-icon { width: 28px; height: 28px; flex: 0 0 28px; display: grid; place-items: center; border-radius: 8px; background: var(--surface-3); color: var(--text-2); }
.f-text { display: flex; flex-direction: column; min-width: 0; }
.f-text b { font-weight: 600; overflow-wrap: anywhere; }
/* Пояснение источника («Задача «…» · автор»): одна строка, приглушённо, с многоточием. Ширина 0 + min-width 100% —
   строка не расширяет столбец, а занимает ту ширину, что дали имя файла и остальные столбцы */
.f-note { display: block; width: 0; min-width: 100%; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; font-size: var(--fs-xs); color: var(--muted); }
.f-text small, .src small, .when small { display: block; font-size: var(--fs-xs); color: var(--muted); }
.src { min-width: 140px; }
.s-label { display: inline-flex; align-items: center; gap: 6px; }
.s-label :deep(svg) { color: var(--muted); flex: 0 0 auto; }
.ds { min-width: 120px; }
.sum { min-width: 150px; max-width: 320px; font-size: var(--fs-sm); color: var(--text-2); }
.sum.bad { color: color-mix(in srgb, var(--light-red) 82%, var(--text)); }
.when { width: 140px; }
.when .num { font-size: var(--fs-sm); }
.muted { color: var(--muted); }
.skeleton-rows { display: flex; flex-direction: column; gap: 10px; padding: 14px; }
.skeleton-rows .skeleton { height: 40px; }
.pager { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; padding: 10px 14px; border-top: 1px solid var(--border); font-size: var(--fs-sm); }
.size { display: inline-flex; align-items: center; gap: 8px; color: var(--muted); }
.size .select { width: 72px; }
.pages { display: inline-flex; align-items: center; gap: 2px; }
.page-btn { min-width: 28px; height: 28px; padding: 0 6px; border: 0; border-radius: var(--radius-sm); background: transparent; color: var(--text-2); font-size: var(--fs-sm); cursor: pointer; }
.page-btn:hover { background: var(--surface-3); color: var(--text); }
.page-btn.active { background: var(--text); color: var(--bg-elevated); font-weight: 600; }
.gap { min-width: 20px; text-align: center; color: var(--faint); }
.retention { font-size: var(--fs-xs); }
@media (max-width: 860px) {
  .inbox-table thead { display: none; }
  .inbox-table, .inbox-table tbody { display: block; }
  .inbox-table tr { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 4px 12px; padding: 12px 14px; border-bottom: 1px solid var(--border); }
  .inbox-table td { display: block; padding: 0; border: 0; min-width: 0; max-width: none; width: auto; }
  .inbox-table td.file { grid-column: 1; min-width: 0; }
  .inbox-table td:nth-child(4) { grid-column: 2; grid-row: 1; justify-self: end; }
  .inbox-table td.src, .inbox-table td.ds, .inbox-table td.sum, .inbox-table td.when { grid-column: 1 / -1; }
  .inbox-table td.src small { display: inline; margin-left: 6px; }
  .inbox-table td.when { display: flex; gap: 8px; align-items: baseline; }
  .inbox-table td.when small { display: inline; }
  .inbox-table tbody tr:last-child { border-bottom: 0; }
}
@media (max-width: 640px) {
  .filters { padding: 12px; }
  .dates { width: 100%; flex-wrap: wrap; }
  .dates .lbl { flex-basis: 100%; }
  .dates .input { flex: 1 1 0; width: auto; }
  .search, .filters .select { flex: 1 1 100%; max-width: none; width: 100%; }
  .reset { margin-left: 0; }
}
</style>
