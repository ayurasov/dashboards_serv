<script setup>
import { computed, ref, watch } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import AppModal from '@/components/ui/AppModal.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import FilterBar from '@/components/ui/FilterBar.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import LightBadge from '@/components/ui/LightBadge.vue'
import PdfButton from '@/components/ui/PdfButton.vue'
import PartnershipForm from '@/components/product/PartnershipForm.vue'
import { partnershipsApi } from '@/api/services'
import { useAsync } from '@/composables/useAsync'
import { useQueryState } from '@/composables/useQueryState'
import { confirm } from '@/composables/useConfirm'
import { toastOk } from '@/composables/useToast'
import { useAuthStore } from '@/stores/auth'
import { formatDate, formatDateTime, formatNumber, plural } from '@/utils/format'
import { LIGHT_LABELS } from '@/utils/lights'
import {
  LIGHT_FILTERS, certAgeYears, countByLight, formatYears, lightParts, lightReason, lightSegments, orderStatuses,
  sortPartnerships,
} from '@/domain/partnerships'

const auth = useAuthStore()
const canEdit = computed(() => auth.can('project_product', 'editor'))
const { state: f, reset, isDefault } = useQueryState({
  year: '', status: '', almi_product: '', direction: '', type: '', light: '', search: '', sort: 'partner', dir: 'asc',
})

const options = useAsync(() => partnershipsApi.options())
const opts = computed(() => options.data.value || { statuses: [], almi_products: [], directions: [], types: [], years: [] })
const years = computed(() => [...opts.value.years].sort((a, b) => b - a))
const statuses = computed(() => orderStatuses(opts.value.statuses))

// Поиск уходит на сервер с задержкой, пока человек печатает
const query = ref(f.search.trim())
let timer
watch(() => f.search, (v) => {
  clearTimeout(timer)
  timer = setTimeout(() => { query.value = v.trim() }, 300)
})

// Светофор отбирается на странице: так полоса оценок показывает все записи выборки
const params = computed(() => ({ year: f.year, status: f.status, almi_product: f.almi_product, direction: f.direction, type: f.type, search: query.value }))
const exportParams = computed(() => ({ ...params.value, light: f.light }))
const { data, loading, reload, error } = useAsync(() => partnershipsApi.list(params.value), { immediate: false })
watch(params, () => reload(), { immediate: true, deep: true })

const all = computed(() => data.value || [])
const rows = computed(() => sortPartnerships(f.light ? all.value.filter((r) => r.light === f.light) : all.value, f.sort, f.dir))
const segments = computed(() => lightSegments(countByLight(all.value)))
const summary = computed(() => {
  const n = rows.value.length
  const word = plural(n, ['запись', 'записи', 'записей'])
  return f.light ? `${formatNumber(n)} из ${formatNumber(all.value.length)}` : `${formatNumber(n)} ${word}`
})
const empty = computed(() => data.value && !all.value.length && isDefault())

const COLUMNS = [
  { key: 'light', label: '', title: 'Светофор', cls: 'col-light' },
  { key: 'partner', label: 'Партнёр' },
  { key: 'product', label: 'Продукт партнёра' },
  { key: 'almi_product', label: 'Продукт АЛМИ' },
  { key: 'status', label: 'Статус' },
  { key: 'cert_date', label: 'Сертификат' },
  { key: 'docs', label: 'Документы', title: 'NDA и соглашение' },
]
function sortBy(key) {
  if (f.sort === key) f.dir = f.dir === 'asc' ? 'desc' : 'asc'
  else {
    f.sort = key
    f.dir = ['cert_date', 'docs'].includes(key) ? 'desc' : 'asc'
  }
}
function toggleLight(light) {
  f.light = f.light === light ? '' : light
}

// ---------- подсказка к светофору ----------
const tip = ref(null)
function showTip(event, record) {
  const rect = event.currentTarget.getBoundingClientRect()
  const below = rect.bottom + 190 < window.innerHeight
  tip.value = { record, x: rect.left - 6, y: below ? rect.bottom + 8 : rect.top - 8, below }
}
const hideTip = () => { tip.value = null }

// ---------- карточка, форма, удаление ----------
const viewing = ref(null)
const editing = ref(null)
const exporting = ref(false)

function openRow(row) {
  hideTip()
  viewing.value = row
}
function edit(row) {
  viewing.value = null
  editing.value = row || {}
}
function onSaved() {
  editing.value = null
  reload()
  options.reload()
}
function onDeleted() {
  editing.value = null
  viewing.value = null
  reload()
  options.reload()
}
async function remove(row) {
  const ok = await confirm({ title: 'Удалить партнёрство?', message: `${row.partner}${row.product ? ` — ${row.product}` : ''}\nДействие попадёт в журнал изменений.`, confirmText: 'Удалить', danger: true })
  if (!ok) return
  try { await partnershipsApi.remove(row.id) } catch { return } // ошибку показал клиент API
  toastOk('Партнёрство удалено')
  onDeleted()
}
async function exportXlsx() {
  exporting.value = true
  try { await partnershipsApi.exportXlsx(exportParams.value) } catch {} finally { exporting.value = false }
}

const age = (r) => (r.cert_date ? formatYears(certAgeYears(r.cert_date)) : '')
const linkText = (url) => String(url || '').replace(/^https?:\/\//, '').replace(/\/$/, '')
const bitrixText = (url) => {
  const task = String(url || '').match(/task\/view\/(\d+)/)
  return task ? `Задача №${task[1]}` : linkText(url)
}
const href = (url) => (/^https?:\/\//i.test(url) ? url : `https://${url}`)
const createDefaults = computed(() => ({ status: f.status || 'В работе', almi_product: f.almi_product, direction: f.direction, type: f.type || 'ПО' }))
</script>

<template>
  <div class="page">
    <PageHeader title="Реестр партнёрств" description="Сертификации продуктов партнёров: статус, документы, срок сертификата">
      <button v-if="auth.canExport" class="btn" type="button" :disabled="exporting" title="Выгрузить записи с текущими фильтрами" @click="exportXlsx"><AppIcon name="sheet" :size="15" />{{ exporting ? 'Выгрузка…' : 'Excel' }}</button>
      <PdfButton report="partnerships/registry" :params="exportParams" />
      <button v-if="canEdit" class="btn btn-primary" type="button" @click="edit()"><AppIcon name="plus" :size="15" />Добавить</button>
    </PageHeader>

    <FilterBar :resettable="!isDefault()" @reset="reset">
      <label class="search"><AppIcon name="search" :size="14" /><input v-model="f.search" type="search" placeholder="Партнёр, продукт, направление, версия" aria-label="Поиск" /></label>
      <label class="field"><span>Год</span>
        <select v-model="f.year" class="select"><option value="">Все</option><option v-for="y in years" :key="y" :value="String(y)">{{ y }}</option></select>
      </label>
      <label class="field"><span>Статус</span>
        <select v-model="f.status" class="select"><option value="">Все</option><option v-for="s in statuses" :key="s" :value="s">{{ s }}</option></select>
      </label>
      <label class="field"><span>Продукт АЛМИ</span>
        <select v-model="f.almi_product" class="select"><option value="">Все</option><option v-for="p in opts.almi_products" :key="p" :value="p">{{ p }}</option></select>
      </label>
      <label class="field"><span>Направление</span>
        <select v-model="f.direction" class="select narrow"><option value="">Все</option><option v-for="d in opts.directions" :key="d" :value="d">{{ d }}</option></select>
      </label>
      <label class="field"><span>Тип</span>
        <select v-model="f.type" class="select short"><option value="">Все</option><option v-for="t in opts.types" :key="t" :value="t">{{ t }}</option></select>
      </label>
      <label class="field"><span>Светофор</span>
        <select v-model="f.light" class="select short"><option value="">Все</option><option v-for="l in LIGHT_FILTERS" :key="l.value" :value="l.value">{{ l.label }}</option></select>
      </label>
    </FilterBar>

    <EmptyState v-if="empty" icon="handshake" title="Реестр пуст" text="Добавьте первое партнёрство: партнёра, продукт, статус сертификации и документы.">
      <button v-if="canEdit" class="btn btn-primary" type="button" @click="edit()"><AppIcon name="plus" :size="15" />Добавить партнёрство</button>
    </EmptyState>

    <template v-else>
      <div v-if="all.length" class="card strip">
        <span class="strip-count num">{{ summary }}</span>
        <div class="track" aria-hidden="true">
          <span v-for="s in segments" v-show="s.count" :key="s.light" class="seg" :class="[s.light, { dim: f.light && f.light !== s.light }]" :style="{ flexGrow: s.count }" />
        </div>
        <div class="strip-chips">
          <button v-for="s in segments" :key="s.light" type="button" class="lchip" :class="{ active: f.light === s.light }" :aria-pressed="f.light === s.light"
                  :title="f.light === s.light ? 'Показать все записи' : `Показать только: ${LIGHT_LABELS[s.light].toLowerCase()}`" @click="toggleLight(s.light)">
            <LightBadge :light="s.light" dot />{{ LIGHT_LABELS[s.light] }}<b class="num">{{ formatNumber(s.count) }}</b>
          </button>
        </div>
      </div>

      <section class="card">
        <div class="table-wrap scroll-thin">
          <table class="table">
            <thead>
              <tr>
                <th v-for="c in COLUMNS" :key="c.key" class="sortable" :class="c.cls" :title="c.title || ''" :aria-sort="f.sort === c.key ? (f.dir === 'asc' ? 'ascending' : 'descending') : 'none'" @click="sortBy(c.key)">
                  <AppIcon v-if="c.key === 'light'" name="traffic" :size="13" class="th-icon" />{{ c.label }}<AppIcon v-if="f.sort === c.key" :name="f.dir === 'asc' ? 'arrow-up' : 'arrow-down'" :size="11" class="sort-icon" />
                </th>
                <th v-if="canEdit" class="col-actions"><span class="sr-only">Действия</span></th>
              </tr>
            </thead>
            <tbody v-if="data">
              <tr v-for="r in rows" :key="r.id" class="clickable" tabindex="0" @click="openRow(r)" @keydown.enter.self="openRow(r)">
                <td class="col-light">
                  <span class="light-hit" tabindex="0" :aria-label="`Светофор: ${LIGHT_LABELS[r.light]}`" @mouseenter="showTip($event, r)" @mouseleave="hideTip" @focus="showTip($event, r)" @blur="hideTip">
                    <span class="ldot" :class="r.light" />
                  </span>
                </td>
                <td class="col-partner">
                  <div class="partner">
                    <span class="strong">{{ r.partner }}</span>
                    <span v-if="r.comment" class="meta-icon" :title="r.comment"><AppIcon name="note" :size="13" /></span>
                  </div>
                </td>
                <td class="col-product">
                  <span class="clamp">{{ r.product || '—' }}</span>
                  <div class="sub ellipsis" :title="[r.type, r.direction].filter(Boolean).join(' · ')">{{ [r.type, r.direction].filter(Boolean).join(' · ') }}</div>
                </td>
                <td class="col-almi">
                  <div>{{ r.almi_product || '—' }}</div>
                  <div v-if="r.almi_version" class="sub">{{ r.almi_version }}</div>
                </td>
                <td class="nowrap"><span class="badge" :class="`badge-${r.status_light || 'gray'}`">{{ r.status || '—' }}</span></td>
                <td class="nowrap num">
                  <div>{{ formatDate(r.cert_date) }}</div>
                  <div v-if="r.cert_date" class="sub">{{ age(r) }}</div>
                </td>
                <td class="nowrap">
                  <div class="docs">
                    <span class="doc" :class="{ on: r.nda }" :title="r.nda ? 'NDA подписан' : 'NDA не подписан'"><AppIcon :name="r.nda ? 'check' : 'minus'" :size="11" :stroke="2.4" />NDA</span>
                    <span class="doc" :class="{ on: r.agreement }" :title="r.agreement ? 'Соглашение подписано' : 'Соглашение не подписано'"><AppIcon :name="r.agreement ? 'check' : 'minus'" :size="11" :stroke="2.4" />Соглашение</span>
                  </div>
                </td>
                <td v-if="canEdit" class="col-actions" @click.stop>
                  <div class="row-actions">
                    <button class="btn btn-icon btn-sm btn-ghost" type="button" title="Изменить" @click="edit(r)"><AppIcon name="edit" :size="14" /></button>
                    <button class="btn btn-icon btn-sm btn-ghost" type="button" title="Удалить" @click="remove(r)"><AppIcon name="trash" :size="14" /></button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
          <div v-if="loading && !data" class="skel">
            <div v-for="i in 8" :key="i" class="skeleton" />
          </div>
          <EmptyState v-else-if="error && !data" compact icon="alert" title="Не удалось загрузить реестр" :text="error.message">
            <button class="btn btn-sm" type="button" @click="reload()"><AppIcon name="refresh" :size="14" />Повторить</button>
          </EmptyState>
          <EmptyState v-else-if="data && !rows.length" compact icon="search" title="Ничего не найдено" text="Измените условия поиска или сбросьте фильтры.">
            <button class="btn btn-sm" type="button" @click="reset">Сбросить фильтры</button>
          </EmptyState>
        </div>
      </section>
    </template>

    <Teleport to="body">
      <div v-if="tip" class="light-tip" :class="{ above: !tip.below }" :style="{ left: `${tip.x}px`, top: `${tip.y}px` }" role="tooltip">
        <div class="tip-head"><LightBadge :light="tip.record.light" /><span v-if="lightReason(tip.record)" class="muted">Определили: {{ lightReason(tip.record, false) }}</span></div>
        <ul>
          <li v-for="p in lightParts(tip.record)" :key="p.key" :class="{ skipped: p.skipped }">
            <LightBadge :light="p.light" dot /><span class="tip-label">{{ p.label }}</span><span class="tip-value">{{ p.value }}</span>
          </li>
        </ul>
        <p class="tip-foot">Итог — худшая из оценок</p>
      </div>
    </Teleport>

    <AppModal v-if="viewing" :title="viewing.partner" :subtitle="viewing.product || 'Продукт не указан'" :width="640" @close="viewing = null">
      <div class="details">
        <section class="verdict" :class="`v-${viewing.light}`">
          <div class="verdict-head">
            <LightBadge :light="viewing.light" />
            <span v-if="lightReason(viewing)" class="muted">Определили: {{ lightReason(viewing, false) }}</span>
          </div>
          <ul class="parts">
            <li v-for="p in lightParts(viewing)" :key="p.key" :class="{ skipped: p.skipped }">
              <LightBadge :light="p.light" dot />
              <span class="part-label">{{ p.label }}</span>
              <span class="part-value">{{ p.value }}</span>
              <span class="part-light">{{ p.skipped ? 'не учитывается' : LIGHT_LABELS[p.light] }}</span>
            </li>
          </ul>
          <p class="verdict-note">Оценка записи — худшая из оценок частей; правила задаются в разделе <router-link to="/settings/partnership-lights" class="link" @click="viewing = null">«Светофор»</router-link>.</p>
        </section>

        <dl class="facts">
          <div><dt>Направление</dt><dd>{{ viewing.direction || '—' }}</dd></div>
          <div><dt>Тип</dt><dd>{{ viewing.type || '—' }}</dd></div>
          <div><dt>Продукт АЛМИ</dt><dd>{{ viewing.almi_product || '—' }}</dd></div>
          <div><dt>Версия</dt><dd>{{ viewing.almi_version || '—' }}</dd></div>
          <div><dt>Статус</dt><dd><span class="badge" :class="`badge-${viewing.status_light || 'gray'}`">{{ viewing.status || '—' }}</span></dd></div>
          <div><dt>Дата сертификата</dt><dd class="num">{{ formatDate(viewing.cert_date) }}<span v-if="viewing.cert_date" class="muted"> · {{ age(viewing) }}</span></dd></div>
          <div><dt>NDA</dt><dd>{{ viewing.nda ? 'Подписан' : 'Не подписан' }}</dd></div>
          <div><dt>Соглашение</dt><dd>{{ viewing.agreement ? 'Подписано' : 'Не подписано' }}</dd></div>
          <div v-if="viewing.last_modified"><dt>Дата изменения</dt><dd class="num">{{ formatDate(viewing.last_modified) }}</dd></div>
          <div><dt>Задача в Битрикс24</dt>
            <dd><a v-if="viewing.bitrix" :href="href(viewing.bitrix)" target="_blank" rel="noopener" class="link ext" :title="viewing.bitrix"><span class="ellipsis">{{ bitrixText(viewing.bitrix) }}</span><AppIcon name="external" :size="12" /></a><span v-else>—</span></dd>
          </div>
          <div><dt>Сайт партнёра</dt>
            <dd><a v-if="viewing.website" :href="href(viewing.website)" target="_blank" rel="noopener" class="link ext" :title="viewing.website"><span class="ellipsis">{{ linkText(viewing.website) }}</span><AppIcon name="external" :size="12" /></a><span v-else>—</span></dd>
          </div>
          <div v-if="viewing.comment" class="full"><dt>Комментарий</dt><dd class="comment">{{ viewing.comment }}</dd></div>
        </dl>
        <p class="stamp">Добавлено {{ formatDateTime(viewing.created_at) }}<template v-if="viewing.updated_at && formatDateTime(viewing.updated_at) !== formatDateTime(viewing.created_at)"> · изменено {{ formatDateTime(viewing.updated_at) }}</template></p>
      </div>
      <template #footer>
        <template v-if="canEdit">
          <button class="btn btn-ghost btn-danger" type="button" @click="remove(viewing)"><AppIcon name="trash" :size="14" />Удалить</button>
          <span class="spacer" />
          <button class="btn" type="button" @click="viewing = null">Закрыть</button>
          <button class="btn btn-primary" type="button" @click="edit(viewing)"><AppIcon name="edit" :size="14" />Изменить</button>
        </template>
        <button v-else class="btn" type="button" @click="viewing = null">Закрыть</button>
      </template>
    </AppModal>

    <PartnershipForm v-if="editing" :record="editing.id ? editing : null" :options="opts" :defaults="createDefaults" removable
                     @close="editing = null" @saved="onSaved" @deleted="onDeleted" />
  </div>
</template>

<style scoped>
.search { display: flex; align-items: center; gap: 8px; height: 32px; padding: 0 10px; border: 1px solid var(--border-strong); border-radius: var(--radius); color: var(--muted); min-width: 260px; flex: 1 1 260px; max-width: 360px; background: var(--surface); }
.search input { border: 0; outline: 0; background: transparent; width: 100%; color: var(--text); font-size: var(--fs-sm); }
.search:focus-within { border-color: var(--chart-2); box-shadow: 0 0 0 3px var(--focus); }
.select.narrow { max-width: 220px; }
.select.short { min-width: 120px !important; }

.strip { display: flex; align-items: center; gap: 12px 16px; flex-wrap: wrap; padding: 10px 16px; }
.strip-count { font-size: var(--fs-sm); font-weight: 600; color: var(--text); white-space: nowrap; min-width: 84px; }
.track { flex: 1 1 200px; display: flex; gap: 2px; height: 8px; border-radius: 4px; overflow: hidden; background: var(--surface-3); }
.seg { min-width: 4px; transition: opacity var(--t-fast); }
.seg.green { background: var(--light-green); }
.seg.yellow { background: var(--light-yellow); }
.seg.red { background: var(--light-red); }
.seg.dim { opacity: .25; }
.strip-chips { display: flex; gap: 6px; flex-wrap: wrap; }
.lchip { display: inline-flex; align-items: center; gap: 7px; height: 28px; padding: 0 10px; border: 1px solid var(--border); border-radius: var(--radius-pill); background: var(--surface); color: var(--text-2); font-size: var(--fs-sm); cursor: pointer; transition: all var(--t-fast); }
.lchip b { color: var(--text); font-weight: 650; }
.lchip:hover { border-color: var(--border-strong); color: var(--text); }
.lchip.active { border-color: var(--text-2); background: var(--surface-3); color: var(--text); box-shadow: inset 0 0 0 1px var(--text-2); }

.th-icon { display: inline-block; vertical-align: -2px; }
.sort-icon { display: inline-block; margin-left: 4px; vertical-align: -1px; }
.col-light { width: 36px; padding-right: 0 !important; }
.light-hit { display: inline-grid; place-items: center; width: 22px; height: 22px; border-radius: 50%; cursor: help; }
.light-hit:hover, .light-hit:focus-visible { background: var(--surface-3); }
.ldot { width: 10px; height: 10px; border-radius: 50%; background: var(--light-gray); }
.ldot.green { background: var(--light-green); box-shadow: 0 0 0 3px color-mix(in srgb, var(--light-green) 18%, transparent); }
.ldot.yellow { background: var(--light-yellow); box-shadow: 0 0 0 3px color-mix(in srgb, var(--light-yellow) 20%, transparent); }
.ldot.red { background: var(--light-red); box-shadow: 0 0 0 3px color-mix(in srgb, var(--light-red) 18%, transparent); }
.col-partner { min-width: 150px; max-width: 240px; }
.partner { display: flex; align-items: flex-start; gap: 6px; }
.strong { font-weight: 580; }
.meta-icon { color: var(--faint); margin-top: 3px; }
.col-product { min-width: 180px; max-width: 300px; }
.col-product .sub { max-width: 280px; }
.col-almi { min-width: 110px; }
.docs { display: flex; flex-direction: column; align-items: flex-start; gap: 3px; }
.doc { display: inline-flex; align-items: center; gap: 3px; height: 19px; padding: 0 7px 0 5px; border-radius: var(--radius-pill); font-size: var(--fs-xs); font-weight: 560; color: var(--faint); border: 1px solid transparent; }
.doc.on { color: var(--light-green); border: 1px solid transparent; background: color-mix(in srgb, var(--light-green) 12%, transparent); }
.clamp { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.sub { font-size: var(--fs-xs); color: var(--muted); margin-top: 1px; }
.col-actions { width: 72px; }
.row-actions { display: flex; gap: 2px; justify-content: flex-end; opacity: .45; transition: opacity var(--t-fast); }
tr:hover .row-actions, .row-actions:focus-within { opacity: 1; }
.skel { display: flex; flex-direction: column; gap: 8px; padding: 12px; }
.skel .skeleton { height: 38px; }

.light-tip { position: fixed; z-index: 250; width: 320px; padding: 12px 14px; border-radius: 12px; background: var(--bg-elevated); border: 1px solid var(--border); box-shadow: var(--shadow-lg); font-size: var(--fs-sm); pointer-events: none; animation: tip-in .12s var(--ease); }
.light-tip.above { transform: translateY(-100%); }
.tip-head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; font-size: var(--fs-xs); }
.light-tip ul { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.light-tip li { display: flex; align-items: center; gap: 8px; }
.light-tip li.skipped { opacity: .6; }
.tip-label { color: var(--muted); width: 128px; flex: 0 0 auto; }
.tip-value { color: var(--text); }
.tip-foot { margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--border); font-size: var(--fs-xs); color: var(--muted); }
@keyframes tip-in { from { opacity: 0; } }

.details { display: flex; flex-direction: column; gap: var(--sp-5); }
.verdict { padding: 14px 16px; border-radius: var(--radius); border: 1px solid var(--border); background: var(--surface-2); }
.verdict-head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; font-size: var(--fs-sm); }
.parts { list-style: none; margin: 12px 0 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
.parts li { display: grid; grid-template-columns: 8px 140px 1fr auto; align-items: center; gap: 10px; font-size: var(--fs-sm); }
.parts li.skipped { opacity: .6; }
.part-label { color: var(--muted); }
.part-value { color: var(--text); }
.part-light { color: var(--text-2); font-size: var(--fs-xs); }
.verdict-note { margin-top: 12px; font-size: var(--fs-xs); color: var(--muted); }
.facts { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px 24px; margin: 0; }
.facts .full { grid-column: 1 / -1; }
.facts dt { font-size: var(--fs-xs); text-transform: uppercase; letter-spacing: .04em; color: var(--muted); font-weight: 600; margin-bottom: 3px; }
.facts dd { margin: 0; color: var(--text); word-break: break-word; }
.ext { display: inline-flex; align-items: center; gap: 4px; max-width: 100%; }
.ext :deep(svg) { flex: 0 0 auto; }
.comment { white-space: pre-line; color: var(--text-2); }
.stamp { font-size: var(--fs-xs); color: var(--faint); }
@media (max-width: 640px) { .facts { grid-template-columns: 1fr; } .parts li { grid-template-columns: 8px 1fr auto; } .part-value { grid-column: 2 / -1; } }
</style>
