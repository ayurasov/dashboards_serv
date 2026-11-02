<script setup>
import { computed, ref } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import { accessApi, directoryApi } from '@/api/access'
import { useAsync } from '@/composables/useAsync'

/**
 * «Вход по домену» (ADR-0008): состояние входа по учётной записи домена (LDAP), настройки без секретов,
 * замечания, проверка подключения и поиск учётной записи без входа; синхронизация с AD — в «Импорт и экспорт».
 */
const { data: status, loading, reload } = useAsync(() => directoryApi.ldapStatus())
const profiles = useAsync(() => accessApi.profiles())
const config = computed(() => status.value?.config || null)
const profileName = (key) => profiles.data.value?.find((p) => p.key === key)?.name || ''

const state = computed(() => {
  if (!status.value) return null
  if (status.value.enabled) return { tone: 'on', label: 'Включён', text: 'Сотрудники входят с логином и паролем домена' }
  if (status.value.configured) return { tone: 'warn', label: 'Настроен, но выключен', text: 'Задайте AUTH_LDAP_ENABLED=true и перезапустите сервер' }
  return { tone: 'off', label: 'Не настроен', text: 'Вход по домену не настроен — сотрудники входят по паролю системы' }
})

const TLS = {
  ldaps: { label: 'LDAPS', text: 'Соединение шифруется TLS', tone: 'ok' },
  starttls: { label: 'StartTLS', text: 'ldap:// с переходом на TLS', tone: 'ok' },
  none: { label: 'Без шифрования', text: 'Пароли идут по сети открыто — только для стенда', tone: 'bad' },
}
const CREATE = {
  no: 'Не создаются — войти могут только заведённые заранее',
  active: 'Создаются при первом входе и сразу активны',
  inactive: 'Создаются при первом входе отключёнными — доступ выдаёт администратор',
}
const MATCHED = { directory: 'по идентификатору каталога', ad_sync: 'по синхронизации с AD', email: 'по e-mail' }

const ENV = [
  { name: 'AUTH_LDAP_ENABLED', text: 'Включить вход по домену', example: 'true', required: true },
  { name: 'AUTH_LDAP_URL', text: 'Адрес контроллера домена', example: 'ldaps://dc.company.local:636', required: true },
  { name: 'AUTH_LDAP_BASE_DN', text: 'База поиска учётных записей', example: 'DC=company,DC=local', required: true },
  { name: 'AUTH_LDAP_BIND_DN', text: 'Служебная учётная запись (только чтение)', example: 'CN=svc-dashboards,OU=Service,DC=company,DC=local' },
  { name: 'AUTH_LDAP_BIND_PASSWORD', text: 'Пароль служебной учётной записи', example: '••••••••' },
  { name: 'AUTH_LDAP_START_TLS', text: 'StartTLS для ldap:// (для ldaps:// не нужен)', example: 'true' },
  { name: 'AUTH_LDAP_CA_FILE', text: 'Сертификат центра сертификации домена', example: '/etc/ssl/company-ca.pem' },
  { name: 'AUTH_LDAP_USER_FILTER', text: 'Фильтр поиска; {login} — введённый логин', example: '(&(objectClass=person)(sAMAccountName={login}))' },
  { name: 'AUTH_LDAP_CREATE_USERS', text: 'Первый вход без учётной записи: active · inactive · пусто — не создавать', example: 'inactive' },
  { name: 'AUTH_LDAP_DEFAULT_PROFILE', text: 'Ключ профиля доступа для созданных при входе', example: 'employee' },
  { name: 'AUTH_LDAP_GROUP_PROFILES', text: 'Профили по группам: «DN группы=ключ профиля», через «;»', example: 'CN=Directors,OU=Groups,DC=company,DC=local=director' },
  { name: 'AUTH_LDAP_ADMIN_GROUP', text: 'Группа, участники которой создаются администраторами', example: 'CN=Dashboards Admins,OU=Groups,DC=company,DC=local' },
  { name: 'AUTH_LDAP_LOGIN_HINT', text: 'Подсказка на странице входа', example: 'Логин и пароль, как при входе в Windows' },
  { name: 'AUTH_LDAP_ATTR_ID · _EMAIL · _NAME · _LOGIN', text: 'Атрибуты каталога (FreeIPA: entryUUID, mail, cn, uid)', example: 'objectGUID · mail · displayName · sAMAccountName' },
]

// ---------- проверка ----------
const login = ref('')
const testing = ref('')
const result = ref(null)
async function run(kind) {
  testing.value = kind
  try {
    result.value = await directoryApi.ldapTest(kind === 'find' ? login.value.trim() : '')
  } catch (e) {
    result.value = { ok: false, message: e.message, entries: null }
  } finally {
    testing.value = ''
  }
}
const resultTone = computed(() => {
  const r = result.value
  if (!r) return ''
  if (!r.ok) return 'bad'
  const e = r.entries
  if (!e) return 'ok'
  if (e.length !== 1 || e[0].disabled || (!e[0].account && !e[0].would_create)) return 'warn'
  return 'ok'
})
</script>

<template>
  <div class="page">
    <PageHeader title="Вход по домену" description="Вход по учётной записи домена (LDAP) и синхронизация с Active Directory">
      <button class="btn" type="button" :disabled="loading" @click="reload"><AppIcon name="refresh" :size="15" />Обновить</button>
    </PageHeader>

    <div v-if="loading && !status" class="stack"><div class="skeleton" style="height: 180px" /><div class="skeleton" style="height: 220px" /></div>

    <template v-else-if="status">
      <section class="card status" :class="`s-${state.tone}`" data-testid="ldap-status">
        <header class="st-head">
          <span class="st-icon"><AppIcon name="key" :size="20" /></span>
          <div class="st-titles">
            <h2>Вход по учётной записи домена</h2>
            <p>{{ state.text }}</p>
          </div>
          <span class="st-pill"><i />{{ state.label }}</span>
        </header>

        <div class="st-body">
          <dl class="facts">
            <div><dt>Пакет ldap3</dt><dd>{{ status.ldap3_available ? `установлен, версия ${status.ldap3_version}` : 'не установлен' }}</dd></div>
            <template v-if="config">
              <div><dt>Сервер</dt><dd class="mono">{{ config.url }}</dd></div>
              <div><dt>База поиска</dt><dd class="mono">{{ config.base_dn }}</dd></div>
              <div><dt>Служебная учётная запись</dt><dd><span v-if="config.bind_dn" class="mono">{{ config.bind_dn }}</span><span v-else>анонимная привязка</span><small v-if="config.bind_dn"> · пароль {{ config.bind_password_set ? 'задан' : 'не задан' }}</small></dd></div>
              <div><dt>Шифрование</dt><dd :class="`tls-${TLS[config.tls]?.tone}`"><b>{{ TLS[config.tls]?.label || config.tls }}</b> — {{ TLS[config.tls]?.text }}<small v-if="config.ca_file"> · CA: <span class="mono">{{ config.ca_file }}</span></small></dd></div>
              <div><dt>Новые сотрудники</dt><dd>{{ CREATE[config.create_users] || CREATE.no }}</dd></div>
              <div><dt>Профиль по умолчанию</dt><dd><template v-if="config.default_profile">{{ profileName(config.default_profile) || config.default_profile }} <span class="mono muted">{{ config.default_profile }}</span></template><span v-else class="muted">не задан</span></dd></div>
              <div><dt>Группа администраторов</dt><dd><span v-if="config.admin_group" class="mono">{{ config.admin_group }}</span><span v-else class="muted">не задана</span></dd></div>
              <div><dt>Фильтр поиска</dt><dd class="mono">{{ config.user_filter }}</dd></div>
              <div><dt>Атрибуты</dt><dd class="mono">{{ Object.values(config.attributes || {}).filter(Boolean).join(' · ') }}</dd></div>
              <div><dt>Подсказка на входе</dt><dd>{{ config.hint || 'по умолчанию' }}</dd></div>
              <div><dt>Ожидание ответа</dt><dd>{{ config.timeout }} с</dd></div>
            </template>
          </dl>

          <div v-if="config?.group_profiles?.length" class="groups">
            <h3>Профили по группам каталога <small>первое совпадение — при создании учётной записи</small></h3>
            <table class="table table-compact">
              <thead><tr><th>Группа</th><th>Профиль доступа</th></tr></thead>
              <tbody>
                <tr v-for="g in config.group_profiles" :key="g.group">
                  <td class="mono dn">{{ g.group }}</td>
                  <td><template v-if="profileName(g.profile)">{{ profileName(g.profile) }} <span class="mono muted">{{ g.profile }}</span></template><span v-else class="bad-key">{{ g.profile }} — нет такого профиля</span></td>
                </tr>
              </tbody>
            </table>
          </div>

          <ul v-if="status.problems?.length" class="problems" role="list">
            <li v-for="p in status.problems" :key="p"><AppIcon name="alert" :size="14" />{{ p }}</li>
          </ul>
          <p v-if="!status.configured" class="not-set"><AppIcon name="info" :size="15" />Вход по домену не настроен. Задайте переменные окружения сервера (ниже) и перезапустите приложение — секреты в интерфейс и API не попадают.</p>
        </div>
      </section>

      <div class="grid grid-2 two">
        <section class="card" data-testid="ldap-check">
          <header class="card-head"><h3>Проверка</h3><span class="hint">Пароль сотрудника не проверяется и не запрашивается</span></header>
          <div class="card-body stack">
            <div class="row-wrap">
              <button class="btn" type="button" :disabled="!!testing" @click="run('connect')"><AppIcon name="activity" :size="15" />{{ testing === 'connect' ? 'Проверяем…' : 'Проверить подключение' }}</button>
              <span class="muted small">Подключение и служебная привязка</span>
            </div>
            <form class="find" @submit.prevent="run('find')">
              <label class="field grow"><span>Найти учётную запись</span>
                <input v-model="login" class="input" name="login" placeholder="Логин, userPrincipalName или e-mail" autocapitalize="off" spellcheck="false" />
              </label>
              <button class="btn btn-primary" type="submit" :disabled="!!testing || !login.trim()"><AppIcon name="search" :size="15" />{{ testing === 'find' ? 'Ищем…' : 'Найти' }}</button>
            </form>

            <div v-if="result" class="result" :class="`r-${resultTone}`" role="status" data-testid="ldap-result">
              <p class="r-msg"><AppIcon :name="resultTone === 'ok' ? 'check' : 'alert'" :size="15" />{{ result.message }}</p>
              <article v-for="e in result.entries || []" :key="e.dn" class="entry">
                <header class="e-head">
                  <div><b>{{ e.name || e.login }}</b><span class="muted"> · {{ e.login }}<template v-if="e.email"> · {{ e.email }}</template></span></div>
                  <span v-if="e.disabled" class="badge badge-red">отключена в каталоге</span>
                </header>
                <p v-if="e.position" class="muted small">{{ e.position }}</p>
                <p class="mono dn">{{ e.dn }}</p>
                <dl class="e-facts">
                  <div><dt>В системе</dt>
                    <dd v-if="e.account">
                      <router-link :to="{ path: '/admin/users', query: { search: e.account.username } }" class="link">{{ e.account.full_name }} ({{ e.account.username }})</router-link>
                      <small> — сопоставлена {{ MATCHED[e.account.matched_by] || e.account.matched_by }}<template v-if="!e.account.is_active">, учётная запись отключена</template><template v-if="e.account.auth_source !== 'ldap'">; при входе перейдёт на вход по домену</template></small>
                    </dd>
                    <dd v-else-if="e.would_create">Будет создана при первом входе</dd>
                    <dd v-else class="bad">Учётной записи нет — вход будет отклонён</dd>
                  </div>
                  <div v-if="e.would_create"><dt>Профиль доступа</dt><dd>{{ e.profile ? (profileName(e.profile) || e.profile) : 'Индивидуальная настройка' }}</dd></div>
                  <div v-if="e.would_create"><dt>Роль</dt><dd>{{ e.admin ? 'Администратор (группа администраторов)' : 'Пользователь' }}</dd></div>
                  <div v-if="e.groups?.length"><dt>Группы</dt><dd class="chips"><span v-for="g in e.groups.slice(0, 8)" :key="g" class="chip-dn" :title="g">{{ g.split(',')[0].replace(/^CN=/i, '') }}</span><span v-if="e.groups.length > 8" class="muted small">и ещё {{ e.groups.length - 8 }}</span></dd></div>
                </dl>
              </article>
            </div>
          </div>
        </section>

        <section class="card">
          <header class="card-head"><h3>Синхронизация с Active Directory</h3></header>
          <div class="card-body stack">
            <p class="text">Подразделения, сотрудники и руководители из каталога: сначала план изменений, затем применение одной транзакцией. Адрес и учётные данные по умолчанию — те же, что у входа по домену (<code>AD_SYNC_*</code>).</p>
            <div><router-link to="/admin/org-transfer" class="btn"><AppIcon name="upload" :size="15" />Импорт и экспорт структуры</router-link></div>
          </div>
        </section>
      </div>

      <section class="card">
        <header class="card-head"><h3>Переменные окружения</h3><span class="hint">Задаются на сервере; после изменения — перезапуск</span></header>
        <div class="card-body flush table-wrap">
          <table class="table table-compact env">
            <thead><tr><th>Переменная</th><th>Назначение</th><th>Пример</th></tr></thead>
            <tbody>
              <tr v-for="v in ENV" :key="v.name">
                <td class="mono nowrap"><b>{{ v.name }}</b><span v-if="v.required" class="req" title="Обязательно">*</span></td>
                <td>{{ v.text }}</td>
                <td class="mono ex">{{ v.example }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.mono { font-family: var(--font-mono); font-size: var(--fs-xs); overflow-wrap: anywhere; }
.small { font-size: var(--fs-sm); }
.status { overflow: hidden; }
.st-head { display: flex; align-items: center; gap: 14px; padding: 18px 20px; border-bottom: 1px solid var(--border); }
.st-icon { width: 42px; height: 42px; flex: 0 0 42px; display: grid; place-items: center; border-radius: 12px; background: var(--surface-3); color: var(--muted); }
.s-on .st-icon { background: color-mix(in srgb, var(--light-green) 14%, transparent); color: var(--light-green); }
.s-warn .st-icon { background: color-mix(in srgb, var(--light-yellow) 16%, transparent); color: color-mix(in srgb, var(--light-yellow) 80%, var(--text)); }
.st-titles { flex: 1; min-width: 0; }
.st-titles h2 { font-size: var(--fs-md); }
.st-titles p { font-size: var(--fs-sm); color: var(--muted); margin-top: 2px; }
.st-pill { display: inline-flex; align-items: center; gap: 7px; height: 28px; padding: 0 12px; border-radius: 99px; font-size: var(--fs-sm); font-weight: 620; background: var(--surface-3); color: var(--muted); white-space: nowrap; }
.st-pill i { width: 8px; height: 8px; border-radius: 50%; background: currentColor; }
.s-on .st-pill { background: color-mix(in srgb, var(--light-green) 13%, transparent); color: var(--light-green); }
.s-warn .st-pill { background: color-mix(in srgb, var(--light-yellow) 16%, transparent); color: color-mix(in srgb, var(--light-yellow) 80%, var(--text)); }
.st-body { display: flex; flex-direction: column; gap: 16px; padding: 16px 20px 20px; }
.facts { margin: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 320px), 1fr)); gap: 10px 28px; }
.facts div { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.facts dt { font-size: var(--fs-xs); color: var(--muted); }
.facts dd { margin: 0; font-size: var(--fs-sm); color: var(--text); }
.facts dd small { color: var(--muted); }
.tls-bad b { color: var(--light-red); }
.tls-ok b { color: var(--light-green); }
.groups h3 { font-size: var(--fs-sm); margin-bottom: 6px; }
.groups h3 small { font-weight: 500; color: var(--muted); }
.groups .table { border: 1px solid var(--border); border-radius: var(--radius); }
.dn { color: var(--text-2); }
.bad-key { color: var(--light-red); font-size: var(--fs-sm); }
.problems { list-style: none; margin: 0; padding: 12px 14px; display: flex; flex-direction: column; gap: 6px; border-radius: var(--radius); background: color-mix(in srgb, var(--light-yellow) 10%, var(--surface)); border: 1px solid color-mix(in srgb, var(--light-yellow) 32%, var(--border)); }
.problems li { display: flex; gap: 8px; align-items: flex-start; font-size: var(--fs-sm); color: var(--text); }
.problems :deep(svg) { flex: 0 0 auto; margin-top: 2px; color: color-mix(in srgb, var(--light-yellow) 80%, var(--text)); }
.not-set { display: flex; gap: 8px; align-items: flex-start; font-size: var(--fs-sm); color: var(--text-2); }
.not-set :deep(svg) { flex: 0 0 auto; margin-top: 2px; color: var(--accent); }
.two { align-items: start; }
.find { display: flex; align-items: flex-end; gap: 8px; }
.grow { flex: 1; }
.result { display: flex; flex-direction: column; gap: 10px; padding: 12px 14px; border-radius: var(--radius-lg); border: 1px solid var(--border); background: var(--surface-2); }
.r-msg { display: flex; align-items: flex-start; gap: 8px; font-size: var(--fs-sm); font-weight: 560; }
.r-msg :deep(svg) { flex: 0 0 auto; margin-top: 2px; }
.r-ok .r-msg { color: var(--light-green); }
.r-warn .r-msg { color: color-mix(in srgb, var(--light-yellow) 80%, var(--text)); }
.r-bad .r-msg { color: var(--light-red); }
.r-bad { background: color-mix(in srgb, var(--light-red) 6%, var(--surface)); border-color: color-mix(in srgb, var(--light-red) 25%, var(--border)); }
.entry { display: flex; flex-direction: column; gap: 4px; padding: 12px; border-radius: var(--radius); background: var(--surface); border: 1px solid var(--border); }
.e-head { display: flex; align-items: flex-start; gap: 8px; justify-content: space-between; font-size: var(--fs-sm); }
.e-facts { margin: 6px 0 0; display: flex; flex-direction: column; gap: 6px; }
.e-facts div { display: grid; grid-template-columns: 120px minmax(0, 1fr); gap: 10px; font-size: var(--fs-sm); }
.e-facts dt { color: var(--muted); }
.e-facts dd { margin: 0; }
.e-facts small { color: var(--muted); }
.bad { color: var(--light-red); }
.chips { display: flex; flex-wrap: wrap; gap: 4px; }
.chip-dn { display: inline-flex; height: 20px; align-items: center; padding: 0 7px; border-radius: 6px; background: var(--surface-3); font-size: var(--fs-xs); color: var(--text-2); }
.text { font-size: var(--fs-sm); color: var(--text-2); line-height: 1.5; }
.text code { font-family: var(--font-mono); font-size: var(--fs-xs); }
.flush { padding: 8px 0 0; }
.env td { vertical-align: top; font-size: var(--fs-sm); }
.env .ex { color: var(--muted); max-width: 360px; }
.req { margin-left: 3px; color: var(--brand); font-weight: 700; }
@media (max-width: 640px) {
  .st-head { flex-wrap: wrap; }
  .find { flex-direction: column; align-items: stretch; }
  .e-facts div { grid-template-columns: minmax(0, 1fr); gap: 0; }
}
</style>
