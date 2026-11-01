<script setup>
import { computed, ref, watch } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import AuditDiff from '@/components/admin/AuditDiff.vue'
import UserAvatar from '@/components/admin/UserAvatar.vue'
import { adminApi } from '@/api/services'
import { useAsync } from '@/composables/useAsync'
import { useQueryState } from '@/composables/useQueryState'
import { ACTION_TONES, actionLabel, entityLabel, pageRange } from '@/domain/admin'
import { formatDateTime, formatNumber, formatRelative } from '@/utils/format'

/** Журнал изменений: кто, когда и что изменил; фильтры — в адресной строке. */
const { state: f, reset, isDefault } = useQueryState({
  entity_type: '', action: '', username: '', service_key: '', search: '', date_from: '', date_to: '', page: 1, page_size: 50,
})
const PAGE_SIZES = [25, 50, 100, 200]

const facets = useAsync(() => adminApi.auditFacets(), { initial: { entity_types: [], actions: [], usernames: [], services: [] } })
const services = useAsync(() => adminApi.services(), { initial: [] })
const serviceTitle = computed(() => Object.fromEntries((services.data.value || []).map((s) => [s.key, s.short_title || s.title])))
const serviceLabels = computed(() => Object.fromEntries((services.data.value || []).map((s) => [s.key, s.title])))

const filters = computed(() => ({
  entity_type: f.entity_type, action: f.action, username: f.username, service_key: f.service_key,
  search: f.search.trim(), date_from: f.date_from, date_to: f.date_to,
}))
// Новый фильтр — снова с первой страницы
watch(() => JSON.stringify([filters.value, f.page_size]), () => { f.page = 1 })
const params = computed(() => ({ ...filters.value, page: f.page, page_size: f.page_size }))

const { data, loading, reload } = useAsync(() => adminApi.audit(params.value), { immediate: false })
let timer
watch(params, (now, before) => {
  clearTimeout(timer)
  timer = setTimeout(reload, before && now.search !== before.search ? 300 : 0)
}, { immediate: true, deep: true })

// Адрес со страницей за пределами выборки (например, после удаления записей) — на последнюю страницу
watch(data, (d) => {
  if (d && !d.items.length && d.total && f.page > 1) f.page = Math.max(1, Math.ceil(d.total / f.page_size))
})

const items = computed(() => data.value?.items || [])
const total = computed(() => data.value?.total || 0)
const pageCount = computed(() => Math.max(1, Math.ceil(total.value / f.page_size)))
const pages = computed(() => pageRange(f.page, pageCount.value))
const rangeText = computed(() => {
  if (!total.value) return ''
  const from = (f.page - 1) * f.page_size + 1
  const to = Math.min(total.value, f.page * f.page_size)
  return `${formatNumber(from)}–${formatNumber(to)} из ${formatNumber(total.value)}`
})

function go(page) {
  if (page < 1 || page > pageCount.value || page === f.page) return
  f.page = page
  expanded.value = new Set()
}

const expanded = ref(new Set())
function toggle(id) {
  const next = new Set(expanded.value)
  next.has(id) ? next.delete(id) : next.add(id)
  expanded.value = next
}
const hasDetails = (e) => !!(e.before || e.after)

const exporting = ref(false)
async function exportCsv() {
  exporting.value = true
  try { await adminApi.exportAudit(filters.value) } catch {} finally { exporting.value = false }
}
</script>

<template>
  <div class="page">
    <PageHeader title="Журнал изменений" description="Кто, когда и что изменил: данные служб, пользователи, настройки и входы в систему">
      <button class="btn" type="button" :disabled="exporting || !total" @click="exportCsv">
        <AppIcon name="download" :size="15" />{{ exporting ? 'Выгрузка…' : 'Выгрузить CSV' }}
      </button>
    </PageHeader>

    <div class="card filters" role="search">
      <label class="search"><AppIcon name="search" :size="14" /><input v-model="f.search" type="search" placeholder="Описание или ID объекта" aria-label="Поиск" /></label>
      <select v-model="f.entity_type" class="select" aria-label="Объект" :class="{ set: f.entity_type }">
        <option value="">Все объекты</option>
        <option v-for="t in facets.data.value.entity_types" :key="t" :value="t">{{ entityLabel(t) }}</option>
      </select>
      <select v-model="f.action" class="select" aria-label="Действие" :class="{ set: f.action }">
        <option value="">Все действия</option>
        <option v-for="a in facets.data.value.actions" :key="a" :value="a">{{ actionLabel(a) }}</option>
      </select>
      <select v-model="f.username" class="select" aria-label="Пользователь" :class="{ set: f.username }">
        <option value="">Все пользователи</option>
        <option v-for="u in facets.data.value.usernames" :key="u" :value="u">{{ u }}</option>
      </select>
      <select v-model="f.service_key" class="select" aria-label="Служба" :class="{ set: f.service_key }">
        <option value="">Все службы</option>
        <option v-for="s in facets.data.value.services" :key="s" :value="s">{{ serviceLabels[s] || s }}</option>
      </select>
      <div class="dates">
        <span class="lbl">Период</span>
        <input v-model="f.date_from" class="input" type="date" aria-label="С даты" :max="f.date_to || undefined" />
        <span class="dash">—</span>
        <input v-model="f.date_to" class="input" type="date" aria-label="По дату" :min="f.date_from || undefined" />
      </div>
      <button v-if="!isDefault()" class="btn btn-ghost btn-sm reset" type="button" @click="reset"><AppIcon name="refresh" :size="13" />Сбросить</button>
    </div>

    <section class="card">
      <div class="table-wrap">
        <table class="table audit">
          <thead>
            <tr>
              <th class="when">Время</th>
              <th>Пользователь</th>
              <th>Действие</th>
              <th>Объект</th>
              <th>Описание</th>
              <th>Служба</th>
              <th class="chev-col" />
            </tr>
          </thead>
          <tbody v-for="e in items" :key="e.id" :class="{ open: expanded.has(e.id) }">
            <tr class="clickable main" :aria-expanded="expanded.has(e.id)" tabindex="0" @click="toggle(e.id)" @keydown.enter="toggle(e.id)">
              <td class="when num nowrap" :title="formatRelative(e.occurred_at)">{{ formatDateTime(e.occurred_at) }}</td>
              <td class="nowrap"><span class="who"><UserAvatar :name="e.username" :seed="e.username" :size="22" />{{ e.username }}</span></td>
              <td><span class="badge" :class="`tone-${ACTION_TONES[e.action] || 'gray'}`">{{ actionLabel(e.action) }}</span></td>
              <td class="nowrap">
                {{ entityLabel(e.entity_type) }}<span v-if="e.entity_id" class="eid">{{ e.entity_id }}</span>
              </td>
              <td class="summary">{{ e.summary || '—' }}</td>
              <td class="muted nowrap">{{ e.service_key ? serviceTitle[e.service_key] || e.service_key : '—' }}</td>
              <td class="chev-col">
                <AppIcon name="chevron-down" :size="15" class="chev" :class="{ dim: !hasDetails(e) }" />
              </td>
            </tr>
            <tr v-if="expanded.has(e.id)" class="details">
              <td colspan="7">
                <AuditDiff :entry="e" :labels="serviceLabels" />
                <dl class="meta">
                  <div><dt>Время</dt><dd class="num">{{ formatDateTime(e.occurred_at) }} · {{ formatRelative(e.occurred_at) }}</dd></div>
                  <div><dt>Объект</dt><dd>{{ entityLabel(e.entity_type) }} <code v-if="e.entity_id">{{ e.entity_id }}</code></dd></div>
                  <div><dt>IP-адрес</dt><dd class="num">{{ e.ip_address || '—' }}</dd></div>
                  <div><dt>Запись</dt><dd class="num">№ {{ e.id }}</dd></div>
                </dl>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-if="loading && !data" class="skeleton-rows"><div v-for="i in 8" :key="i" class="skeleton" /></div>
        <EmptyState v-else-if="data && !items.length" compact icon="history" title="Записей не найдено"
                    :text="isDefault() ? 'Журнал пока пуст.' : 'Измените фильтры или период.'">
          <button v-if="!isDefault()" class="btn btn-sm" type="button" @click="reset">Сбросить фильтры</button>
        </EmptyState>
      </div>

      <footer v-if="total" class="pager">
        <span class="muted num">{{ rangeText }}</span>
        <span class="spacer" />
        <label class="size">На странице
          <select v-model.number="f.page_size" class="select select-sm">
            <option v-for="n in PAGE_SIZES" :key="n" :value="n">{{ n }}</option>
          </select>
        </label>
        <nav class="pages" aria-label="Страницы">
          <button class="btn btn-ghost btn-icon btn-sm" type="button" :disabled="f.page <= 1" aria-label="Предыдущая" @click="go(f.page - 1)">
            <AppIcon name="chevron-left" :size="15" />
          </button>
          <template v-for="(p, i) in pages" :key="`${p}-${i}`">
            <span v-if="p === '…'" class="gap">…</span>
            <button v-else class="page-btn num" :class="{ active: p === f.page }" type="button" :aria-current="p === f.page ? 'page' : undefined" @click="go(p)">{{ p }}</button>
          </template>
          <button class="btn btn-ghost btn-icon btn-sm" type="button" :disabled="f.page >= pageCount" aria-label="Следующая" @click="go(f.page + 1)">
            <AppIcon name="chevron-right" :size="15" />
          </button>
        </nav>
      </footer>
    </section>
  </div>
</template>

<style scoped>
.search { display: flex; align-items: center; gap: 8px; height: 32px; padding: 0 10px; border: 1px solid var(--border-strong); border-radius: var(--radius); color: var(--muted); min-width: 220px; background: var(--surface); }
.search input { border: 0; outline: 0; background: transparent; width: 100%; color: var(--text); font-size: var(--fs-sm); }
.search:focus-within { border-color: var(--accent); box-shadow: 0 0 0 3px var(--focus); }
.filters { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; padding: 12px 16px; }
.filters .select, .filters .input { height: 32px; width: auto; font-size: var(--fs-sm); }
.filters .select { min-width: 150px; max-width: 210px; color: var(--text-2); }
.filters .select.set { color: var(--text); border-color: color-mix(in srgb, var(--accent) 45%, var(--border-strong)); }
.dates { display: inline-flex; align-items: center; gap: 8px; }
.dates .input { width: 140px; }
.lbl { font-size: var(--fs-xs); text-transform: uppercase; letter-spacing: .05em; color: var(--muted); font-weight: 620; }
.reset { margin-left: auto; }
.dash { color: var(--faint); }
.audit td { vertical-align: top; }
.when { width: 150px; }
.who { display: inline-flex; align-items: center; gap: 7px; }
.eid { margin-left: 6px; padding: 0 5px; border-radius: 4px; background: var(--surface-3); font-family: var(--font-mono); font-size: var(--fs-xs); color: var(--muted); }
.summary { min-width: 260px; color: var(--text); }
.chev-col { width: 36px; padding-left: 0; text-align: right; }
.chev { color: var(--faint); transition: transform var(--t-fast), color var(--t-fast); }
.chev.dim { opacity: .45; }
tr.main:hover .chev { color: var(--text-2); }
.open .chev { transform: rotate(180deg); color: var(--text-2); }
.open tr.main td { background: var(--surface-2); border-bottom-color: transparent; }
tr.main:focus-visible { outline: 2px solid var(--focus); outline-offset: -2px; }
.details td { padding: 4px 14px 16px 14px; background: var(--surface-2); }
.table tbody tr.details:hover { background: transparent; }
.meta { display: flex; flex-wrap: wrap; gap: 6px 28px; margin: 12px 0 0; font-size: var(--fs-xs); }
.meta dt { color: var(--muted); }
.meta dd { margin: 1px 0 0; color: var(--text-2); }
.meta code { font-family: var(--font-mono); }
.tone-green { background: color-mix(in srgb, var(--light-green) 14%, transparent); color: var(--light-green); }
.tone-red { background: color-mix(in srgb, var(--light-red) 13%, transparent); color: var(--light-red); }
.tone-yellow { background: color-mix(in srgb, var(--light-yellow) 16%, transparent); color: color-mix(in srgb, var(--light-yellow) 80%, var(--text)); }
.tone-blue { background: color-mix(in srgb, var(--accent) 13%, transparent); color: var(--accent); }
.tone-dark { background: color-mix(in srgb, var(--text) 9%, transparent); color: var(--text); }
.tone-gray { background: var(--surface-3); color: var(--muted); }
.skeleton-rows { display: flex; flex-direction: column; gap: 10px; padding: 14px; }
.skeleton-rows .skeleton { height: 34px; }
.pager { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; padding: 10px 14px; border-top: 1px solid var(--border); font-size: var(--fs-sm); }
.size { display: inline-flex; align-items: center; gap: 8px; color: var(--muted); }
.size .select { width: 72px; }
.pages { display: inline-flex; align-items: center; gap: 2px; }
.page-btn { min-width: 28px; height: 28px; padding: 0 6px; border: 0; border-radius: var(--radius-sm); background: transparent; color: var(--text-2); font-size: var(--fs-sm); cursor: pointer; }
.page-btn:hover { background: var(--surface-3); color: var(--text); }
.page-btn.active { background: var(--text); color: var(--bg-elevated); font-weight: 600; }
.gap { min-width: 20px; text-align: center; color: var(--faint); }
</style>
