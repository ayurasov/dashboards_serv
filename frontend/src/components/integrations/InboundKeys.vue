<script setup>
import { computed, ref } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import AppModal from '@/components/ui/AppModal.vue'
import CodeBlock from '@/components/ui/CodeBlock.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import OneTimeKey from './OneTimeKey.vue'
import { integrationsApi } from '@/api/integrations'
import { useAsync } from '@/composables/useAsync'
import { confirm } from '@/composables/useConfirm'
import { toastOk } from '@/composables/useToast'
import { SCOPES, curlExample, keyState } from '@/domain/integrations'
import { formatDateTime, formatNumber, formatRelative } from '@/utils/format'

/**
 * Ключи для входящих вызовов: 1С, скрипты и другие системы кладут файлы во «Входящие» запросом
 * POST /api/inbound/v1/files с заголовком Authorization: Bearer dash_…. Ключ показывается один раз;
 * «выпустить заново» заменяет значение, «отозвать» — ключ перестаёт работать сразу.
 */
const { data, loading, error, reload } = useAsync(() => integrationsApi.keys())
const keys = computed(() => data.value || [])
const active = computed(() => keys.value.filter((k) => k.active).length)
const origin = typeof window !== 'undefined' ? window.location.origin : ''
const example = computed(() => curlExample({ origin, dataset: 'indicators', filename: 'Показатели из 1С.csv', apply: true }))

// выпуск
const createOpen = ref(false)
const form = ref({ name: '', scopes: ['files'] })
const formError = ref('')
const busy = ref('')
const shown = ref(null)
function openCreate() {
  form.value = { name: '', scopes: ['files'] }
  formError.value = ''
  createOpen.value = true
}
function toggleScope(value) {
  const list = form.value.scopes
  form.value.scopes = list.includes(value) ? list.filter((s) => s !== value) : [...list, value]
}
async function issue() {
  if (!form.value.name.trim()) {
    formError.value = 'Укажите название ключа — по нему ключ узнают в журнале и во «Входящих»'
    return
  }
  if (!form.value.scopes.length) {
    formError.value = 'Выберите хотя бы одну область'
    return
  }
  busy.value = 'issue'
  try {
    const item = await integrationsApi.issueKey({ name: form.value.name.trim(), scopes: form.value.scopes })
    createOpen.value = false
    shown.value = { item, reissued: false }
    reload()
  } catch (e) {
    formError.value = e.fields?.name || e.fields?.scopes || e.message
  } finally {
    busy.value = ''
  }
}

async function reissue(key) {
  const ok = await confirm({
    title: `Выпустить ключ «${key.name}» заново?`,
    message: `Будет выпущено новое значение. Прежнее (${key.prefix}…) перестанет работать сразу — обновите его в системе, которая отправляет файлы.`,
    confirmText: 'Выпустить заново',
  })
  if (!ok) return
  busy.value = `reissue:${key.id}`
  try {
    const item = await integrationsApi.reissueKey(key.id)
    shown.value = { item, reissued: true }
    reload()
  } catch {} finally {
    busy.value = ''
  }
}

async function revoke(key) {
  const ok = await confirm({
    title: `Отозвать ключ «${key.name}»?`,
    message: 'Ключ перестанет работать сразу; запросы с ним получат «Ключ недействителен или отозван». Запись останется для журнала и элементов входящих. Отменить отзыв нельзя — понадобится новый ключ.',
    confirmText: 'Отозвать', danger: true,
  })
  if (!ok) return
  busy.value = `revoke:${key.id}`
  try {
    await integrationsApi.revokeKey(key.id)
    toastOk(`Ключ «${key.name}» отозван`)
    reload()
  } catch {} finally {
    busy.value = ''
  }
}
</script>

<template>
  <div class="keys stack">
    <section class="card">
      <header class="card-head">
        <h3>Ключи для входящих вызовов</h3>
        <span class="hint">{{ keys.length ? `Действуют: ${active} из ${keys.length}` : '' }}</span>
        <span class="spacer" />
        <button type="button" class="btn btn-primary btn-sm" data-testid="key-create" @click="openCreate"><AppIcon name="plus" :size="14" />Выпустить ключ</button>
      </header>
      <div class="card-body">
        <p class="explain">Ключ даёт внешней системе (1С, скрипту, другой системе компании) право положить файл во «Входящие» и узнать, что с ним стало. Ключ привязан к названию — по нему файлы видны в списке входящих и в журнале. Сохраняется только отпечаток ключа: значение показывается один раз.</p>
        <div v-if="loading && !data" class="skeleton" style="height: 140px" />
        <EmptyState v-else-if="error && !data" compact icon="alert" title="Не удалось загрузить ключи" :text="error.message" />
        <EmptyState v-else-if="!keys.length" compact icon="key" title="Ключей пока нет" text="Выпустите ключ для каждой системы, которая будет отправлять файлы: так их легче различать и отзывать по одному.">
          <button type="button" class="btn btn-sm" @click="openCreate">Выпустить ключ</button>
        </EmptyState>
        <div v-else class="table-wrap bordered">
          <table class="table table-compact keys-table" data-testid="keys-table">
            <thead><tr><th>Название</th><th>Ключ</th><th>Области</th><th>Выпущен</th><th>Последний вызов</th><th class="num">Файлов</th><th>Состояние</th><th /></tr></thead>
            <tbody>
              <tr v-for="k in keys" :key="k.id" :class="{ revoked: !k.active }" :data-key="k.name">
                <td><b>{{ k.name }}</b></td>
                <td class="mono nowrap">{{ k.prefix }}…</td>
                <td><span v-for="s in k.scope_labels" :key="s" class="scope">{{ s }}</span></td>
                <td class="nowrap"><span class="lbl">Выпущен: </span>{{ formatDateTime(k.issued_at) }}<small v-if="k.issued_by">{{ k.issued_by }}</small></td>
                <td class="nowrap"><span class="lbl">Последний вызов: </span><template v-if="k.last_used_at">{{ formatRelative(k.last_used_at) }}</template><span v-else class="muted">не было</span></td>
                <td class="num"><span class="lbl">Файлов: </span>{{ formatNumber(k.items_received) }}</td>
                <td><span class="badge" :class="`badge-${keyState(k).tone}`">{{ keyState(k).label }}</span><small v-if="k.revoked_at">{{ formatDateTime(k.revoked_at) }}</small></td>
                <td class="acts">
                  <template v-if="k.active">
                    <button type="button" class="btn btn-sm btn-ghost" :disabled="!!busy" :data-testid="`key-reissue-${k.id}`" @click="reissue(k)">Выпустить заново</button>
                    <button type="button" class="btn btn-sm btn-ghost btn-danger" :disabled="!!busy" :data-testid="`key-revoke-${k.id}`" @click="revoke(k)">Отозвать</button>
                  </template>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>

    <section class="card">
      <header class="card-head"><h3>Как отправить файл</h3></header>
      <div class="card-body usage">
        <div class="stack">
          <CodeBlock :code="example" label="curl" testid="keys-curl" />
          <p class="explain"><code>dataset</code> — набор (<code>indicators</code>, <code>tp-weekly</code>, <code>hr-months</code>…); без него набор распознаётся по имени и содержимому. <code>apply=true</code> — применить, если план без ошибок и для источника «Приём по API» и набора включено «применять сразу» (Входящие → Правила); <code>apply=false</code> — только план, ждать подтверждения.</p>
        </div>
        <ul class="facts">
          <li><b>Ответ</b> — номер элемента, статус (<code>pending</code>, <code>applied</code>, <code>error</code>, <code>duplicate</code>), сводка плана и ошибки. Тот же файл второй раз — <code>200</code> со статусом «повтор».</li>
          <li><b>Статус позже</b> — <code>GET /api/inbound/v1/files/{id}</code> (область «Чтение статусов»), проверка ключа — <code>GET /api/inbound/v1/ping</code>.</li>
          <li><b>1С</b> — регламентное задание отправляет выгрузку тем же запросом: <code>HTTPСоединение</code> + <code>HTTPЗапрос</code>, заголовок <code>Authorization: Bearer dash_…</code>, тело <code>multipart/form-data</code> с полем <code>file</code>.</li>
          <li><b>Ошибки</b> — <code>401</code> ключ неверен или отозван, <code>403</code> не хватает области, <code>413</code> файл слишком большой, <code>429</code> слишком часто (смотрите <code>Retry-After</code>).</li>
        </ul>
      </div>
    </section>

    <AppModal v-if="createOpen" title="Выпустить ключ" subtitle="Значение ключа покажется один раз — сразу сохраните его в системе-отправителе" :width="520" @close="createOpen = false">
      <form class="stack" novalidate @submit.prevent="issue">
        <label class="field">
          <span>Название</span>
          <input v-model="form.name" class="input" maxlength="120" placeholder="Например, «1С: ЗУП» или «Скрипт выгрузки Naumen»" data-testid="key-name" />
          <small class="help">Кто будет отправлять файлы — так ключ виден во «Входящих» и в журнале</small>
        </label>
        <fieldset class="scopes">
          <legend>Что разрешено</legend>
          <label v-for="s in SCOPES" :key="s.value" class="check">
            <input type="checkbox" :checked="form.scopes.includes(s.value)" :data-testid="`key-scope-${s.value}`" @change="toggleScope(s.value)" />
            <span>{{ s.label }}<small>{{ s.hint }}</small></span>
          </label>
        </fieldset>
        <p v-if="formError" class="form-error" role="alert"><AppIcon name="alert" :size="14" />{{ formError }}</p>
        <button type="submit" class="sr-only" tabindex="-1">Выпустить</button>
      </form>
      <template #footer>
        <button type="button" class="btn" @click="createOpen = false">Отмена</button>
        <button type="button" class="btn btn-primary" :disabled="!!busy" data-testid="key-issue" @click="issue"><AppIcon name="key" :size="15" />{{ busy === 'issue' ? 'Выпускаю…' : 'Выпустить' }}</button>
      </template>
    </AppModal>

    <OneTimeKey v-if="shown" :item="shown.item" :reissued="shown.reissued" @close="shown = null" />
  </div>
</template>

<style scoped>
.keys .card-head { flex-wrap: wrap; row-gap: 6px; }
.explain { max-width: 860px; margin-bottom: 14px; font-size: var(--fs-sm); color: var(--text-2); line-height: 1.55; }
.explain code, .facts code { font-family: var(--font-mono); font-size: var(--fs-xs); padding: 0 4px; border-radius: 4px; background: var(--surface-3); }
.bordered { border: 1px solid var(--border); border-radius: 12px; }
.keys-table td { vertical-align: top; font-size: var(--fs-sm); }
.keys-table td small { display: block; font-size: var(--fs-xs); color: var(--muted); }
.keys-table tr.revoked td { color: var(--muted); }
.mono { font-family: var(--font-mono); font-size: var(--fs-xs); }
.scope { display: inline-block; margin: 0 4px 3px 0; padding: 0 7px; border-radius: 99px; background: var(--surface-3); font-size: var(--fs-xs); color: var(--text-2); white-space: nowrap; }
.acts { text-align: right; white-space: nowrap; }
.muted { color: var(--muted); }
.lbl { display: none; color: var(--muted); }
.usage { display: grid; grid-template-columns: minmax(0, 1.2fr) minmax(0, 1fr); gap: 16px 28px; }
.usage .explain { margin: 0; }
.facts { margin: 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 10px; font-size: var(--fs-sm); color: var(--text-2); line-height: 1.5; }
.facts b { color: var(--text); font-weight: 620; }
.scopes { margin: 0; padding: 0; border: 0; display: flex; flex-direction: column; gap: 10px; }
.scopes legend { margin-bottom: 6px; font-size: var(--fs-sm); font-weight: 560; color: var(--text-2); }
.check { align-items: flex-start; }
.check input { margin-top: 2px; flex: 0 0 auto; }
.check span { display: flex; flex-direction: column; font-size: var(--fs-sm); }
.check small, .help { font-size: var(--fs-xs); color: var(--muted); }
.form-error { display: flex; align-items: flex-start; gap: 6px; font-size: var(--fs-sm); color: var(--light-red); }
.form-error :deep(svg) { margin-top: 2px; flex: 0 0 auto; }
@media (max-width: 1000px) { .usage { grid-template-columns: minmax(0, 1fr); } }
@media (max-width: 760px) {
  .keys-table thead { display: none; }
  .keys-table, .keys-table tbody { display: block; }
  .keys-table tr { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 3px 10px; padding: 10px 12px; border-bottom: 1px solid var(--border); }
  .keys-table td { display: block; padding: 0; border: 0; text-align: left; white-space: normal; }
  .keys-table td:not(:first-child) { grid-column: 1 / -1; }
  .keys-table td:nth-child(7) { grid-column: 2; grid-row: 1; }
  .keys-table td.acts { text-align: left; }
  .keys-table .lbl { display: inline; }
  .keys-table td small { display: inline; margin-left: 6px; }
}
</style>
