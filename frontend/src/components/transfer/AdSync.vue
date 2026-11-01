<script setup>
import { computed, ref } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import OrgIcon from '@/components/org/OrgIcon.vue'
import ImportPlanView from './ImportPlanView.vue'
import TransferBanner from './TransferBanner.vue'
import { orgApi } from '@/api/org'
import { useAsync } from '@/composables/useAsync'
import { toastOk } from '@/composables/useToast'

/**
 * Синхронизация с Active Directory: подключение (без секретов), проверка — план изменений,
 * синхронизация одной транзакцией; для регулярного запуска — команда сервера.
 */
const emit = defineEmits(['applied'])
const status = useAsync(() => orgApi.adStatus())
const config = computed(() => status.data.value?.config || null)
const ready = computed(() => !!status.data.value?.configured && !!status.data.value?.ldap3_available)

const createMissing = ref(false)
const deactivateMissing = ref(false)
const plan = ref(null)
const result = ref(null)
const busy = ref('')
const error = ref('')
const CLI = 'docker compose exec app python -m app.cli org-sync --ad --apply'

async function run(apply) {
  busy.value = apply ? 'apply' : 'check'
  error.value = ''
  try {
    return await orgApi.adSync({ createMissing: createMissing.value, deactivateMissing: deactivateMissing.value, apply })
  } catch (e) {
    error.value = e.message
    return null
  } finally {
    busy.value = ''
  }
}
async function check() {
  result.value = null
  const next = await run(false)
  if (next) plan.value = next
}
async function sync() {
  const applied = await run(true)
  if (!applied) return
  plan.value = applied
  if (applied.rejected) return
  const s = applied.summary
  result.value = `Новых подразделений: ${s.create_departments} · новых сотрудников: ${s.create_users} · изменено: ${s.update_users} · отключено: ${s.deactivate_users}`
  emit('applied')
  const fresh = await run(false)
  if (fresh) plan.value = fresh
}
function reset() {
  plan.value = null
  result.value = null
}
async function copy() {
  try {
    await navigator.clipboard.writeText(`${CLI} --create-missing`)
    toastOk('Команда скопирована')
  } catch {}
}
const pathSource = computed(() => (config.value?.path_source === 'ou'
  ? 'по организационным единицам (OU)'
  : `из атрибутов ${(config.value?.path_attributes || []).join(' / ')}`))
</script>

<template>
  <div class="transfer">
    <section class="card block">
      <div class="block-head">
        <span class="b-icon" :class="{ ok: ready }"><OrgIcon name="link" :size="18" /></span>
        <div class="b-text">
          <h2>Active Directory</h2>
          <p>Подразделения, должности и руководители берутся из каталога: сотрудники сопоставляются по objectGUID, затем по email; руководитель — атрибут manager.</p>
        </div>
        <span v-if="status.data.value" class="badge" :class="ready ? 'badge-green' : 'badge-gray'">{{ ready ? 'Подключение настроено' : 'Не настроено' }}</span>
      </div>

      <div v-if="status.loading.value && !status.data.value" class="block-body"><div class="skeleton" style="height: 120px" /></div>
      <div v-else-if="status.error.value" class="block-body">
        <TransferBanner tone="error" title="Не удалось получить настройки" :text="status.error.value.message" />
      </div>
      <div v-else-if="status.data.value && !status.data.value.configured" class="block-body">
        <TransferBanner tone="warn" title="Синхронизация не настроена">
          Задайте на сервере переменные <code>AD_SYNC_URL</code>, <code>AD_SYNC_BASE_DN</code>, <code>AD_SYNC_BIND_DN</code> и <code>AD_SYNC_BIND_PASSWORD</code>
          (или настройте вход по домену — синхронизация возьмёт его адрес и базу) и перезапустите приложение. Подробности — в руководстве администратора.
        </TransferBanner>
      </div>
      <div v-if="status.data.value" class="block-body">
        <dl v-if="config" class="config">
          <div><dt>Каталог</dt><dd class="mono">{{ config.url }}</dd></div>
          <div><dt>База поиска</dt><dd class="mono">{{ config.base_dn }}</dd></div>
          <div><dt>Подразделения</dt><dd>{{ pathSource }}</dd></div>
          <div><dt>Руководители подразделений</dt><dd>{{ config.detect_heads ? 'определяются по атрибуту manager' : 'не определяются' }}</dd></div>
          <div><dt>Шифрование</dt><dd>{{ config.url.startsWith('ldaps') ? 'LDAPS' : config.start_tls ? 'StartTLS' : 'нет' }}</dd></div>
          <div v-if="config.user_filter"><dt>Фильтр</dt><dd class="mono small">{{ config.user_filter }}</dd></div>
        </dl>
        <TransferBanner v-if="config && !status.data.value.ldap3_available" tone="error" title="На сервере не установлен пакет ldap3" text="Синхронизация недоступна, пока его не установят." />
        <label class="check" :class="{ disabled: !ready }"><input v-model="createMissing" type="checkbox" :disabled="!ready" data-testid="ad-create" @change="reset" />
          <span>Создавать сотрудников из AD<small>Новые сотрудники входят по учётной записи домена.</small></span>
        </label>
        <label class="check" :class="{ disabled: !ready }"><input v-model="deactivateMissing" type="checkbox" :disabled="!ready" data-testid="ad-deactivate" @change="reset" />
          <span>Отключать сотрудников, которых нет в AD<small>Только пришедших из AD — и тех, чья учётная запись в каталоге отключена.</small></span>
        </label>
        <p v-if="error" class="form-error" role="alert"><AppIcon name="alert" :size="14" />{{ error }}</p>
        <div class="actions">
          <button type="button" class="btn" :disabled="!ready || !!busy" data-testid="ad-check" @click="check">
            <AppIcon name="search" :size="15" />{{ busy === 'check' ? 'Проверяю…' : 'Проверить' }}
          </button>
          <button type="button" class="btn btn-primary" :disabled="!ready || !!busy || !plan?.can_apply || !!result" data-testid="ad-sync" @click="sync">
            <AppIcon name="refresh" :size="15" />{{ busy === 'apply' ? 'Синхронизирую…' : 'Синхронизировать' }}
          </button>
          <span v-if="!plan && ready" class="muted">Сначала проверьте — синхронизация применит показанный план.</span>
        </div>
      </div>
    </section>

    <section class="card block cli">
      <div class="block-head">
        <span class="b-icon"><OrgIcon name="terminal" :size="18" /></span>
        <div class="b-text">
          <h2>По расписанию</h2>
          <p>Для регулярной синхронизации добавьте команду в планировщик сервера (cron, systemd-таймер). Без <code>--apply</code> команда только покажет план; флаги <code>--create-missing</code> и <code>--deactivate-missing</code> — как отметки выше.</p>
          <div class="cmd">
            <code>{{ CLI }} --create-missing</code>
            <button type="button" class="btn btn-ghost btn-sm" title="Скопировать" @click="copy"><AppIcon name="copy" :size="14" />Скопировать</button>
          </div>
        </div>
      </div>
    </section>

    <TransferBanner v-if="result" title="Синхронизация выполнена" :text="result" />
    <ImportPlanView v-if="plan" :key="plan.applied ? 'a' : 'p'" :plan="plan" :title="result ? 'После синхронизации' : 'Что изменится'" source="Каталог Active Directory">
      <template #footer>
        <button type="button" class="btn btn-primary" :disabled="!plan.can_apply || !!busy || !!result" @click="sync">
          <AppIcon name="refresh" :size="15" />{{ busy === 'apply' ? 'Синхронизирую…' : 'Синхронизировать' }}
        </button>
        <span class="muted">{{ result ? 'Изменения применены.' : plan.can_apply ? 'Всё будет записано одной операцией.' : 'Исправьте данные в каталоге или в системе и проверьте снова.' }}</span>
      </template>
    </ImportPlanView>
  </div>
</template>

<style scoped src="./transfer.css"></style>
<style scoped>
.check.disabled { opacity: .55; cursor: not-allowed; }
.b-icon.ok { background: color-mix(in srgb, var(--light-green) 14%, transparent); color: var(--light-green); }
.config { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px 24px; margin: 0; padding: 14px 16px; border-radius: 12px; background: var(--surface-2); border: 1px solid var(--border); }
.config dt { font-size: var(--fs-xs); color: var(--muted); }
.config dd { margin: 2px 0 0; font-size: var(--fs-sm); color: var(--text); overflow-wrap: anywhere; }
.mono { font-family: var(--font-mono); }
.small { font-size: var(--fs-xs) !important; }
code { font-family: var(--font-mono); font-size: .92em; padding: 1px 5px; border-radius: 5px; background: var(--surface-3); }
.cmd { display: flex; align-items: center; gap: 8px; margin-top: 10px; padding: 6px 6px 6px 12px; border-radius: 10px; background: var(--surface-2); border: 1px solid var(--border); max-width: 640px; }
.cmd code { flex: 1; min-width: 0; padding: 0; background: transparent; overflow-x: auto; white-space: nowrap; font-size: var(--fs-sm); }
@media (max-width: 760px) {
  .config { grid-template-columns: 1fr; }
}
</style>
