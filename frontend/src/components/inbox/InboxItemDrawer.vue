<script setup>
import { computed, ref, watch } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import AppModal from '@/components/ui/AppModal.vue'
import SideDrawer from '@/components/admin/SideDrawer.vue'
import TransferBanner from '@/components/transfer/TransferBanner.vue'
import InboxPlan from './InboxPlan.vue'
import { inboxApi } from '@/api/inbox'
import { toastOk } from '@/composables/useToast'
import {
  fileSize, optionValues, optionsChanged, optionsPayload, planBlocked, sourceInfo, statusBadge,
} from '@/domain/inbox'
import { formatDateTime, formatRelative } from '@/utils/format'

/**
 * Элемент входящих: откуда и когда пришёл, набор, статус и сообщение, параметры набора, план (или итог
 * применения) и действия по item.actions: «Применить», «Отклонить» с причиной, «Повторить» (можно
 * выбрать другой набор), «Скачать исходный файл». У повтора — ссылка на исходный элемент.
 */
const props = defineProps({
  id: { type: Number, required: true },
  datasets: { type: Array, default: () => [] },
})
const emit = defineEmits(['close', 'changed', 'open'])

const item = ref(null)
const loading = ref(false)
const loadError = ref('')
const busy = ref('')
const rejected = ref('')
const opts = ref({})
const decisions = ref({})

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    set(await inboxApi.item(props.id))
  } catch (e) {
    loadError.value = e.message
    item.value = null
  } finally {
    loading.value = false
  }
}
function set(next) {
  item.value = next
  opts.value = optionValues(next?.option_fields || [], next?.options || {})
  decisions.value = { ...(next?.options?.decisions || {}) }
}
watch(() => props.id, () => { rejected.value = ''; load() }, { immediate: true })

const badge = computed(() => statusBadge(item.value))
const source = computed(() => sourceInfo(item.value))
const fields = computed(() => item.value?.option_fields || [])
const isEmployees = computed(() => item.value?.dataset === 'employees')
const decisionsChanged = computed(() => isEmployees.value && JSON.stringify(decisions.value) !== JSON.stringify(item.value?.options?.decisions || {}))
const dirty = computed(() => optionsChanged(fields.value, opts.value, item.value?.options) || decisionsChanged.value)
const payload = computed(() => {
  const out = optionsPayload(fields.value, opts.value, item.value?.options)
  if (isEmployees.value) out.decisions = decisions.value
  return out
})
const shownPlan = computed(() => item.value?.result || item.value?.plan || null)
const planTitle = computed(() => (item.value?.result ? 'Итог применения' : item.value?.status === 'applied' ? 'Применённый план' : 'Что изменится'))
const datasetOptions = computed(() => props.datasets.filter((d) => d.can_apply))
const applyHint = computed(() => {
  const it = item.value
  if (!it) return ''
  if (it.actions?.apply) return dirty.value ? 'Параметры изменены — план будет построен и применён с ними.' : 'Всё будет записано одной операцией; при ошибках ничего не записывается.'
  if (planBlocked(it)) return 'В плане ошибки — исправьте файл или данные системы и нажмите «Повторить».'
  if (it.status === 'pending' && !it.has_content) return 'Исходный файл удалён по сроку хранения.'
  return ''
})

const banner = computed(() => {
  const it = item.value
  if (!it) return null
  switch (it.status) {
    case 'applied': return { tone: 'ok', title: 'Применён', text: [it.message, it.applied_at ? `${formatDateTime(it.applied_at)}${it.applied_by ? ` · ${it.applied_by}` : ''}` : ''].filter(Boolean).join(' — ') }
    case 'error': return { tone: 'error', title: 'Ошибка обработки', text: it.error || it.message }
    case 'rejected': return { tone: 'info', title: 'Отклонён', text: it.message }
    case 'duplicate': return { tone: 'info', title: 'Повтор уже полученного файла', text: it.message }
    case 'received': return { tone: 'warn', title: 'Набор не распознан', text: it.message || 'Выберите набор и нажмите «Повторить»' }
    case 'pending': return { tone: planBlocked(it) ? 'error' : 'warn', title: planBlocked(it) ? 'План с ошибками — применить нельзя' : 'План готов — проверьте и примените', text: it.message }
    default: return it.message ? { tone: 'info', title: it.status_label, text: it.message } : null
  }
})

// ---------------------------------------------------------------- действия
async function act(kind, fn) {
  busy.value = kind
  try {
    return await fn()
  } catch {
    return null
  } finally {
    busy.value = ''
  }
}

async function apply() {
  const result = await act('apply', () => inboxApi.apply(item.value.id, dirty.value ? payload.value : undefined))
  if (!result) return
  set(result.item)
  rejected.value = result.rejected ? result.detail || 'В свежем плане ошибки' : ''
  if (!result.rejected) toastOk(result.item.message ? `Применено: ${result.item.message}` : 'Файл применён')
  emit('changed', result.item)
}

async function recalc() {
  const next = await act('recalc', () => inboxApi.retry(item.value.id, { dataset: item.value.dataset, options: payload.value }))
  if (!next) return
  rejected.value = ''
  set(next)
  toastOk('План построен заново')
  emit('changed', next)
}

// повтор: другой набор или распознать заново
const retryOpen = ref(false)
const retryDataset = ref('')
const retryApply = ref(false)
function openRetry() {
  retryDataset.value = item.value?.dataset || ''
  retryApply.value = false
  retryOpen.value = true
}
async function retry() {
  const sameDataset = retryDataset.value === (item.value.dataset || '')
  const next = await act('retry', () => inboxApi.retry(item.value.id, {
    dataset: retryDataset.value || null,
    options: sameDataset && dirty.value ? payload.value : null,
    apply: retryApply.value,
  }))
  if (!next) return
  retryOpen.value = false
  rejected.value = ''
  set(next)
  toastOk(next.status === 'applied' ? 'План построен и применён' : next.status === 'duplicate' ? 'Этот файл с таким набором уже получен' : 'План построен заново')
  emit('changed', next)
}

// отклонение с причиной
const rejectOpen = ref(false)
const reason = ref('')
async function reject() {
  const next = await act('reject', () => inboxApi.reject(item.value.id, reason.value.trim()))
  if (!next) return
  rejectOpen.value = false
  reason.value = ''
  set(next)
  toastOk('Элемент отклонён — данные не записаны')
  emit('changed', next)
}

async function downloadFile() {
  await act('download', () => inboxApi.download(item.value))
}
</script>

<template>
  <SideDrawer :title="item?.filename || 'Элемент входящих'" :width="820" sheet @close="emit('close')">
    <template #header>
      <div class="dh">
        <span class="file-icon"><AppIcon name="file" :size="18" /></span>
        <div class="dh-text">
          <h2 data-testid="inbox-item-title">{{ item?.filename || (loading ? 'Загрузка…' : 'Элемент входящих') }}</h2>
          <p v-if="item" class="muted">№ {{ item.id }} · {{ fileSize(item.size) }}<template v-if="item.dataset_label"> · {{ item.dataset_label }}</template></p>
        </div>
        <span v-if="item" class="badge" :class="`badge-${badge.tone}`" data-testid="inbox-item-status">{{ badge.label }}</span>
      </div>
    </template>

    <div v-if="loading && !item" class="stack"><div class="skeleton" style="height: 70px" /><div class="skeleton" style="height: 220px" /></div>
    <TransferBanner v-else-if="loadError && !item" tone="error" title="Не удалось открыть элемент" :text="loadError" />

    <div v-else-if="item" class="body-stack">
      <TransferBanner v-if="banner" :tone="banner.tone" :title="banner.title" :text="banner.text" data-testid="inbox-item-message">
        <template v-if="item.status === 'duplicate' && item.duplicate_of" #actions>
          <button type="button" class="btn btn-sm" data-testid="open-original" @click="emit('open', item.duplicate_of)"><AppIcon name="external" :size="13" />Элемент №{{ item.duplicate_of }}</button>
        </template>
      </TransferBanner>

      <dl class="facts">
        <div><dt>Источник</dt><dd><AppIcon :name="source.icon" :size="13" /> {{ source.label }}<small v-if="source.detail && source.detail !== source.label"> · {{ source.detail }}</small></dd></div>
        <div><dt>Набор</dt><dd>{{ item.dataset_label || 'не распознан' }}</dd></div>
        <div><dt>Получен</dt><dd>{{ formatDateTime(item.received_at) }} <small>· {{ formatRelative(item.received_at) }}<template v-if="item.received_by && item.source !== 'upload'"> · {{ item.received_by }}</template></small></dd></div>
        <div v-if="item.processed_at"><dt>Обработан</dt><dd>{{ formatDateTime(item.processed_at) }}</dd></div>
        <div v-if="item.applied_at"><dt>Применён</dt><dd>{{ formatDateTime(item.applied_at) }}<small v-if="item.applied_by"> · {{ item.applied_by }}</small></dd></div>
        <div v-if="item.source_ref && item.source !== 'folder'"><dt>Ссылка источника</dt><dd class="mono">{{ item.source_ref }}</dd></div>
        <div><dt>SHA-256</dt><dd class="mono" :title="item.sha256">{{ item.sha256?.slice(0, 16) }}…</dd></div>
        <div v-if="!item.has_content"><dt>Исходный файл</dt><dd class="muted">не сохранён или удалён по сроку хранения</dd></div>
      </dl>

      <section v-if="item.status === 'received' && item.actions.retry" class="pick card-lite">
        <h3>Какой это набор?</h3>
        <p class="muted">Набор не распознан по имени и содержимому. Выберите его — план построится тем же движком, что у загрузки на странице службы.</p>
        <div class="row-wrap">
          <select v-model="retryDataset" class="select pick-select" aria-label="Набор данных" data-testid="pick-dataset">
            <option value="" disabled>Выберите набор…</option>
            <option v-for="d in datasetOptions" :key="d.key" :value="d.key">{{ d.label }}</option>
          </select>
          <button type="button" class="btn btn-primary" :disabled="!retryDataset || !!busy" @click="retry"><AppIcon name="refresh" :size="15" />{{ busy === 'retry' ? 'Строю план…' : 'Построить план' }}</button>
        </div>
      </section>

      <section v-if="fields.length && (item.actions.apply || item.actions.retry)" class="card-lite options" data-testid="inbox-options">
        <h3>Параметры набора</h3>
        <div class="opt-grid">
          <template v-for="f in fields" :key="f.key">
            <label v-if="f.type === 'bool'" class="check">
              <input v-model="opts[f.key]" type="checkbox" :data-testid="`option-${f.key}`" />
              <span>{{ f.label }}<small v-if="f.hint">{{ f.hint }}</small></span>
            </label>
            <label v-else class="field">
              <span>{{ f.label }}</span>
              <select v-model="opts[f.key]" class="select" :data-testid="`option-${f.key}`">
                <option v-for="o in f.options" :key="o.value" :value="o.value">{{ o.label }}</option>
              </select>
              <small v-if="f.hint" class="help">{{ f.hint }}</small>
            </label>
          </template>
        </div>
        <div v-if="dirty" class="row-wrap dirty-row">
          <span class="muted">Параметры изменены.</span>
          <button type="button" class="btn btn-sm" :disabled="!!busy || !item.actions.retry" data-testid="recalc" @click="recalc"><AppIcon name="refresh" :size="13" />{{ busy === 'recalc' ? 'Пересчёт…' : 'Пересчитать план' }}</button>
        </div>
      </section>

      <InboxPlan v-if="shownPlan" :plan="shownPlan" :title="planTitle" :rejected="rejected"
                 :decisions="isEmployees && (item.actions.apply || item.actions.retry) && item.status === 'pending' ? decisions : null"
                 @update:decisions="decisions = $event" />
      <p v-else-if="item.status !== 'received'" class="no-plan muted">Плана нет: {{ item.status === 'duplicate' ? 'повтор не обрабатывается' : item.status === 'error' ? 'файл не удалось разобрать' : 'набор не распознан' }}.</p>
      <p v-if="decisionsChanged" class="muted note">Решения по сотрудникам изменены — пересчитайте план или примените с ними.</p>
    </div>

    <template v-if="item" #footer>
      <button v-if="item.actions.download" type="button" class="btn btn-ghost" :disabled="!!busy" data-testid="inbox-download" @click="downloadFile">
        <AppIcon name="download" :size="15" /><span class="hide-sm">Скачать исходный файл</span><span class="show-sm">Файл</span>
      </button>
      <span class="spacer" />
      <span v-if="applyHint" class="foot-hint">{{ applyHint }}</span>
      <button v-if="item.actions.reject" type="button" class="btn btn-danger" :disabled="!!busy" data-testid="inbox-reject" @click="rejectOpen = true">Отклонить</button>
      <button v-if="item.actions.retry && item.status !== 'received'" type="button" class="btn" :disabled="!!busy" data-testid="inbox-retry" @click="openRetry">
        <AppIcon name="refresh" :size="15" />Повторить
      </button>
      <button v-if="item.status === 'pending'" type="button" class="btn btn-primary" :disabled="!item.actions.apply || !!busy" data-testid="inbox-apply" @click="apply">
        <AppIcon name="check" :size="15" />{{ busy === 'apply' ? 'Применяю…' : 'Применить' }}
      </button>
    </template>
  </SideDrawer>

  <AppModal v-if="retryOpen" title="Повторить обработку" subtitle="Набор распознаётся заново (или берётся выбранный), план строится по текущим данным системы" :width="520" @close="retryOpen = false">
    <div class="stack">
      <label class="field">
        <span>Набор данных</span>
        <select v-model="retryDataset" class="select" data-testid="retry-dataset">
          <option value="">Распознать заново по имени и содержимому</option>
          <option v-for="d in datasetOptions" :key="d.key" :value="d.key">{{ d.label }}{{ d.key === item?.dataset ? ' (сейчас)' : '' }}</option>
        </select>
        <small class="help">{{ datasets.find((d) => d.key === retryDataset)?.description || 'Подпапка, шаблон имени и содержимое файла' }}</small>
      </label>
      <label class="check"><input v-model="retryApply" type="checkbox" />Применить сразу, если в плане не будет ошибок</label>
    </div>
    <template #footer>
      <button type="button" class="btn" @click="retryOpen = false">Отмена</button>
      <button type="button" class="btn btn-primary" :disabled="!!busy" data-testid="retry-confirm" @click="retry"><AppIcon name="refresh" :size="15" />{{ busy === 'retry' ? 'Строю план…' : 'Повторить' }}</button>
    </template>
  </AppModal>

  <AppModal v-if="rejectOpen" title="Отклонить элемент?" :subtitle="item?.filename" :width="480" @close="rejectOpen = false">
    <div class="stack">
      <p class="muted">Данные из файла не будут записаны. Отклонённый элемент можно обработать снова кнопкой «Повторить», пока исходный файл хранится.</p>
      <label class="field">
        <span>Причина <small class="muted">— необязательно, видна в журнале</small></span>
        <textarea v-model="reason" class="textarea" rows="3" maxlength="1000" placeholder="Например: выгрузка за неверный месяц" data-testid="reject-reason" />
      </label>
    </div>
    <template #footer>
      <button type="button" class="btn" @click="rejectOpen = false">Отмена</button>
      <button type="button" class="btn btn-primary danger" :disabled="!!busy" data-testid="reject-confirm" @click="reject">{{ busy === 'reject' ? 'Отклоняю…' : 'Отклонить' }}</button>
    </template>
  </AppModal>
</template>

<style scoped>
.dh { display: flex; align-items: center; gap: 12px; min-width: 0; }
.file-icon { width: 38px; height: 38px; flex: 0 0 38px; display: grid; place-items: center; border-radius: 10px; background: color-mix(in srgb, var(--accent) 12%, transparent); color: var(--accent); }
.dh-text { flex: 1; min-width: 0; }
.dh-text h2 { font-size: 16px; overflow-wrap: anywhere; }
.dh-text p { font-size: var(--fs-xs); }
.muted { color: var(--muted); }
.body-stack { display: flex; flex-direction: column; gap: 16px; }
.facts { margin: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 10px 24px; }
.facts div { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
.facts dt { font-size: var(--fs-xs); color: var(--muted); }
.facts dd { margin: 0; font-size: var(--fs-sm); display: flex; align-items: baseline; flex-wrap: wrap; gap: 0 4px; overflow-wrap: anywhere; }
.facts dd :deep(svg) { align-self: center; color: var(--muted); }
.facts small { color: var(--muted); }
.mono { font-family: var(--font-mono); font-size: var(--fs-xs); }
.card-lite { display: flex; flex-direction: column; gap: 10px; padding: 14px 16px; border: 1px solid var(--border); border-radius: 12px; background: var(--surface-2); }
.card-lite h3 { font-size: var(--fs-sm); font-weight: 650; }
.card-lite p { font-size: var(--fs-sm); }
.pick-select { width: auto; min-width: 240px; max-width: 100%; flex: 1 1 240px; }
.opt-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 12px 18px; }
.check { align-items: flex-start; }
.check input { margin-top: 2px; }
.check span { display: flex; flex-direction: column; font-size: var(--fs-sm); }
.check small, .help { font-size: var(--fs-xs); color: var(--muted); }
.dirty-row { font-size: var(--fs-sm); }
.no-plan, .note { font-size: var(--fs-sm); }
.foot-hint { font-size: var(--fs-xs); color: var(--muted); max-width: 300px; text-align: right; }
.danger { background: var(--light-red); border-color: var(--light-red); }
.show-sm { display: none; }
@media (max-width: 720px) {
  .foot-hint { display: none; }
  .hide-sm { display: none; }
  .show-sm { display: inline; }
}
</style>
