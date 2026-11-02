<script setup>
import { computed, ref } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import CodeBlock from '@/components/ui/CodeBlock.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import TransferBanner from '@/components/transfer/TransferBanner.vue'
import { inboxApi } from '@/api/inbox'
import { useAsync } from '@/composables/useAsync'
import { useAuthStore } from '@/stores/auth'
import { toastOk } from '@/composables/useToast'
import { folderState, folderTree, scanText, workerState } from '@/domain/inbox'
import { curlExample } from '@/domain/integrations'
import { formatDateTime, formatRelative } from '@/utils/format'

/**
 * Папка «Входящие» (data.manage): путь и доступ, сколько файлов ждут, подпапки наборов с шаблонами
 * имени, последний разбор, отметка планировщика, «Проверить сейчас»; справка — как положить файл
 * в папку и как отправить его по API (curl, 1С).
 */
const props = defineProps({
  meta: { type: Object, default: null },
})
const emit = defineEmits(['show-items'])
const auth = useAuthStore()

const { data: folder, loading, error, reload } = useAsync(() => inboxApi.folder())
const state = computed(() => folderState(folder.value))
const worker = computed(() => workerState(folder.value?.worker))
const lastScan = computed(() => folder.value?.last_scan || null)
const datasets = computed(() => props.meta?.datasets || [])
const subfolders = computed(() => (folder.value?.folders || []).map((f) => ({ ...f, patterns: f.patterns || [] })))
const tree = computed(() => folderTree(folder.value, datasets.value))
const origin = typeof window !== 'undefined' ? window.location.origin : ''
const curl = computed(() => curlExample({ origin, dataset: 'tp-weekly', filename: 'Итоговый отчёт ТП.xlsx' }))

const scanning = ref(false)
const scan = ref(null)
async function scanNow() {
  scanning.value = true
  try {
    scan.value = await inboxApi.scan()
    toastOk(scan.value.taken ? `Папка разобрана: взято файлов — ${scan.value.taken}` : 'Папка проверена: новых файлов нет')
    await reload()
  } catch {} finally {
    scanning.value = false
  }
}
</script>

<template>
  <div class="folder stack">
    <div v-if="loading && !folder" class="skeleton" style="height: 220px; border-radius: var(--radius-lg)" />
    <EmptyState v-else-if="error && !folder" class="card" icon="alert" title="Не удалось получить состояние папки" :text="error.message">
      <button class="btn btn-sm" type="button" @click="reload()">Повторить</button>
    </EmptyState>

    <template v-else-if="folder">
      <section class="card status" :class="`s-${state.tone}`" data-testid="inbox-folder">
        <header class="st-head">
          <span class="st-icon"><AppIcon name="folder" :size="20" /></span>
          <div class="st-titles">
            <h2>Папка «Входящие»</h2>
            <p class="mono path">{{ folder.path || 'INBOX_DIR не задана' }}</p>
          </div>
          <span class="st-pill" data-testid="folder-state"><i />{{ state.label }}</span>
          <button type="button" class="btn btn-primary" :disabled="scanning || !folder.enabled" data-testid="folder-scan" @click="scanNow">
            <AppIcon name="refresh" :size="15" />{{ scanning ? 'Проверяю…' : 'Проверить сейчас' }}
          </button>
        </header>
        <div class="st-body">
          <p class="st-text">{{ state.text }}</p>
          <dl class="facts">
            <div><dt>Папка есть</dt><dd>{{ folder.exists ? 'да' : 'нет' }}</dd></div>
            <div><dt>Запись</dt><dd>{{ folder.writable ? 'разрешена' : 'нет прав' }}</dd></div>
            <div><dt>Ждут разбора</dt><dd data-testid="folder-waiting">{{ folder.waiting_files }}</dd></div>
            <div><dt>Файл берётся</dt><dd>через {{ folder.settle_seconds }} с без изменений</dd></div>
            <div><dt>Размер файла</dt><dd>до {{ folder.max_mb }} МБ</dd></div>
            <div><dt>Хранение исходных файлов</dt><dd>{{ folder.retention_days }} дней</dd></div>
          </dl>

          <div v-if="scan" class="scan">
            <TransferBanner :tone="scan.errors ? 'warn' : 'ok'" :title="scan.taken ? 'Папка разобрана' : 'Новых файлов нет'" :text="scanText(scan)" data-testid="folder-scan-result">
              <template v-if="scan.taken" #actions>
                <button type="button" class="btn btn-sm" @click="emit('show-items')">Показать в списке</button>
              </template>
            </TransferBanner>
            <ul v-if="scan.notes?.length" class="notes"><li v-for="n in scan.notes" :key="n">{{ n }}</li></ul>
          </div>

          <div class="grid grid-2 duo">
            <div class="mini">
              <h3>Последний разбор</h3>
              <template v-if="lastScan?.last_scan_at">
                <p>{{ formatDateTime(lastScan.last_scan_at) }} <span class="muted">· {{ formatRelative(lastScan.last_scan_at) }}</span></p>
                <p class="muted">{{ scanText(lastScan.last_result) }}</p>
              </template>
              <p v-else class="muted">Файлы из папки ещё не забирались.</p>
            </div>
            <div class="mini" :class="`w-${worker.tone}`" data-testid="worker-state">
              <h3>Планировщик <span class="w-pill">{{ worker.label }}</span></h3>
              <p class="muted">{{ worker.text }}</p>
            </div>
          </div>
        </div>
      </section>

      <section class="card">
        <header class="card-head"><h3>Подпапки наборов</h3><span class="hint">Файл в подпапке — набор известен; в корне — распознаётся по имени и содержимому</span></header>
        <div class="card-body flush table-wrap">
          <table class="table table-compact subs">
            <thead><tr><th>Подпапка</th><th>Набор</th><th>Распознаётся в корне по имени</th></tr></thead>
            <tbody>
              <tr v-for="f in subfolders" :key="f.folder">
                <td class="mono nowrap"><b>{{ f.folder }}/</b></td>
                <td>{{ f.label }}</td>
                <td><span v-for="p in f.patterns" :key="p" class="pat">{{ p }}</span><span v-if="!f.patterns.length" class="muted">по содержимому</span></td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section class="card help" data-testid="inbox-help">
        <header class="card-head"><h3>Как передать файлы</h3></header>
        <div class="card-body help-grid">
          <div class="stack">
            <h4><AppIcon name="folder" :size="15" />В папку на сервере</h4>
            <p>Положите файл в подпапку набора (или в корень — набор распознается). Файл берётся, когда не меняется дольше {{ folder.settle_seconds }} с — дописываемые файлы не трогаются; временные (<code>~$*</code>, <code>*.tmp</code>, <code>*.part</code>) пропускаются. Обработанный файл переносится в <code>processed/ГГГГ-ММ/</code> или <code>rejected/</code> вместе с отчётом <code>*.result.json</code>.</p>
            <CodeBlock :code="tree" label="Устройство папки" />
          </div>
          <div class="stack">
            <h4><AppIcon name="code" :size="15" />По API с ключом</h4>
            <p>Скрипты и другие системы отправляют файл запросом <code>POST /api/inbound/v1/files</code> с заголовком <code>Authorization: Bearer dash_…</code>. Ключ выпускается в «Интеграции → Ключи для входящих вызовов» и показывается один раз. <code>dataset</code> — необязательно: без него набор распознаётся.</p>
            <CodeBlock :code="curl" label="curl" testid="inbox-curl" />
            <p class="one-c"><b>1С.</b> Регламентное задание сохраняет выгрузку (ЗУП, Бухгалтерия) в подпапку «Входящих», если папка доступна по сети, или отправляет её тем же запросом: <code>HTTPСоединение</code> и <code>HTTPЗапрос</code> с заголовком <code>Authorization</code> и телом <code>multipart/form-data</code> (поле <code>file</code>). Повтор того же файла распознаётся и дважды не применяется.</p>
            <router-link v-if="auth.hasCapability('integrations.manage')" to="/admin/integrations?tab=keys" class="btn btn-sm align-start"><AppIcon name="key" :size="14" />Ключи для входящих вызовов</router-link>
          </div>
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.mono { font-family: var(--font-mono); font-size: var(--fs-xs); overflow-wrap: anywhere; }
.folder .card-head { flex-wrap: wrap; row-gap: 2px; }
.muted { color: var(--muted); }
.status { overflow: hidden; }
.st-head { display: flex; align-items: center; flex-wrap: wrap; gap: 12px 14px; padding: 18px 20px; border-bottom: 1px solid var(--border); }
.st-icon { width: 42px; height: 42px; flex: 0 0 42px; display: grid; place-items: center; border-radius: 12px; background: var(--surface-3); color: var(--muted); }
.s-green .st-icon { background: color-mix(in srgb, var(--light-green) 14%, transparent); color: var(--light-green); }
.s-yellow .st-icon { background: color-mix(in srgb, var(--light-yellow) 16%, transparent); color: color-mix(in srgb, var(--light-yellow) 80%, var(--text)); }
.s-red .st-icon { background: color-mix(in srgb, var(--light-red) 13%, transparent); color: var(--light-red); }
.st-titles { flex: 1 1 240px; min-width: 0; }
.st-titles h2 { font-size: var(--fs-md); }
.path { margin-top: 2px; color: var(--text-2); }
.st-pill { display: inline-flex; align-items: center; gap: 7px; height: 28px; padding: 0 12px; border-radius: 99px; font-size: var(--fs-sm); font-weight: 620; background: var(--surface-3); color: var(--muted); white-space: nowrap; }
.st-pill i { width: 8px; height: 8px; border-radius: 50%; background: currentColor; }
.s-green .st-pill { background: color-mix(in srgb, var(--light-green) 13%, transparent); color: var(--on-green); }
.s-yellow .st-pill { background: color-mix(in srgb, var(--light-yellow) 16%, transparent); color: var(--on-yellow); }
.s-red .st-pill { background: color-mix(in srgb, var(--light-red) 13%, transparent); color: var(--on-red); }
.st-body { display: flex; flex-direction: column; gap: 16px; padding: 16px 20px 20px; }
.st-text { font-size: var(--fs-sm); color: var(--text-2); }
.facts { margin: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 10px 24px; }
.facts div { display: flex; flex-direction: column; gap: 2px; }
.facts dt { font-size: var(--fs-xs); color: var(--muted); }
.facts dd { margin: 0; font-size: var(--fs-sm); }
.scan { display: flex; flex-direction: column; gap: 6px; }
.notes { margin: 0; padding-left: 18px; font-size: var(--fs-sm); color: var(--text-2); }
.duo { align-items: stretch; }
.mini { display: flex; flex-direction: column; gap: 4px; padding: 12px 14px; border: 1px solid var(--border); border-radius: 12px; background: var(--surface-2); font-size: var(--fs-sm); }
.mini h3 { display: flex; align-items: center; gap: 8px; font-size: var(--fs-sm); font-weight: 650; }
.w-pill { height: 20px; padding: 0 8px; border-radius: 99px; font-size: var(--fs-xs); font-weight: 620; line-height: 20px; background: var(--surface-3); color: var(--muted); }
.w-green .w-pill { background: color-mix(in srgb, var(--light-green) 13%, transparent); color: var(--on-green); }
.w-yellow .w-pill { background: color-mix(in srgb, var(--light-yellow) 16%, transparent); color: var(--on-yellow); }
.w-red .w-pill { background: color-mix(in srgb, var(--light-red) 13%, transparent); color: var(--on-red); }
.flush { padding: 8px 0 0; }
.subs td { vertical-align: top; font-size: var(--fs-sm); }
.pat { display: inline-block; margin: 0 4px 3px 0; padding: 0 6px; border-radius: 5px; background: var(--surface-3); font-family: var(--font-mono); font-size: var(--fs-xs); color: var(--text-2); }
.help-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px 28px; }
.help h4 { display: flex; align-items: center; gap: 8px; font-size: var(--fs-sm); font-weight: 650; }
.help p { font-size: var(--fs-sm); color: var(--text-2); line-height: 1.55; }
.help code { font-family: var(--font-mono); font-size: var(--fs-xs); padding: 0 4px; border-radius: 4px; background: var(--surface-3); overflow-wrap: anywhere; }
.align-start { align-self: flex-start; }
@media (max-width: 960px) { .help-grid { grid-template-columns: minmax(0, 1fr); } }
@media (max-width: 640px) {
  .subs thead { display: none; }
  .subs, .subs tbody { display: block; }
  .subs tr { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 2px 12px; padding: 8px 14px; border-bottom: 1px solid var(--border); }
  .subs td { display: block; padding: 0; border: 0; }
  .subs td:last-child { grid-column: 1 / -1; }
  .st-head .btn { width: 100%; }
  .st-head { padding: 16px; }
  .st-body { padding: 14px 16px 16px; }
}
</style>
