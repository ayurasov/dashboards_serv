<script setup>
import { computed } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import { adminApi } from '@/api/services'
import { useAsync } from '@/composables/useAsync'
import { useAppStore } from '@/stores/app'
import { formatMinutes } from '@/domain/admin'
import { formatDateTime, formatNumber, formatRelative, plural } from '@/utils/format'

/** О системе: версия, состояние базы данных, объём данных, параметры сервера. */
const app = useAppStore()
const { data: info, loading, error, reload } = useAsync(() => adminApi.systemInfo())

const ENVIRONMENTS = { production: 'Рабочая среда', development: 'Разработка', test: 'Тестовая среда', testing: 'Тестовая среда', staging: 'Предрабочая среда' }
const DIALECTS = { sqlite: 'SQLite', postgresql: 'PostgreSQL', mysql: 'MySQL' }
const DATASETS = { tp_weekly: 'Недельный отчёт ТП', naumen: 'Заявки Naumen', partnerships: 'Партнёрства' }

const isProduction = computed(() => info.value?.environment === 'production')
const db = computed(() => info.value?.database || {})

const COUNTS = [
  { key: 'users', label: 'Пользователи', icon: 'users', to: '/admin/users' },
  { key: 'active_sessions', label: 'Активные сессии', icon: 'key' },
  { key: 'hr_months', label: 'Месяцы службы персонала', icon: 'calendar', to: '/hr/data' },
  { key: 'tp_weeks', label: 'Недели отчёта ТП', icon: 'table', to: '/tp/registry' },
  { key: 'naumen_tickets', label: 'Заявки Naumen', icon: 'ticket', to: '/tp/naumen' },
  { key: 'partnerships', label: 'Партнёрства', icon: 'handshake', to: '/product/registry' },
  { key: 'audit_entries', label: 'Записи журнала', icon: 'history', to: '/admin/audit' },
]

const settings = computed(() => {
  const s = info.value?.settings || {}
  const hours = s.session_lifetime_hours
  return [
    { label: 'Срок действия сессии', value: hours === undefined ? '—' : `${hours} ${plural(hours, ['час', 'часа', 'часов'])}`, hint: 'После этого нужно войти заново' },
    { label: 'Выход при бездействии', value: formatMinutes(s.session_idle_minutes), hint: 'Сессия завершается, если не было действий' },
    { label: 'Минимальная длина пароля', value: s.password_min_length ? `${s.password_min_length} ${plural(s.password_min_length, ['символ', 'символа', 'символов'])}` : '—' },
    { label: 'Наибольший размер загрузки', value: s.max_upload_mb ? `${s.max_upload_mb} МБ` : '—', hint: 'Файлы Excel и CSV при импорте' },
    { label: 'Демонстрационные данные', value: s.demo_data ? 'Включены' : 'Выключены', hint: s.demo_data ? 'База заполняется примерами при запуске' : '' },
  ]
})
</script>

<template>
  <div class="page narrow">
    <PageHeader title="О системе" description="Версия, состояние базы данных, объём данных и параметры сервера">
      <button class="btn btn-ghost" type="button" :disabled="loading" @click="reload"><AppIcon name="refresh" :size="15" />Обновить</button>
      <a class="btn" href="/api/docs" target="_blank" rel="noopener"><AppIcon name="external" :size="15" />Документация API</a>
      <button class="btn" type="button" @click="app.openReleaseNotes()"><AppIcon name="sparkles" :size="15" />Что нового</button>
    </PageHeader>

    <EmptyState v-if="error && !info" icon="alert" title="Не удалось получить сведения" :text="error.message">
      <button class="btn btn-sm" type="button" @click="reload">Повторить</button>
    </EmptyState>

    <template v-else>
      <section class="card hero">
        <img src="/logo.png" width="48" height="48" alt="" />
        <div class="hero-text">
          <h2>{{ info?.name || 'Дашборды компании' }}</h2>
          <p v-if="info" class="row-wrap meta">
            <span>Версия <b class="num">{{ info.version }}</b></span>
            <span class="badge" :class="isProduction ? 'badge-green' : 'badge-yellow'">{{ ENVIRONMENTS[info.environment] || info.environment }}</span>
            <span class="muted">Python {{ info.python }}</span>
          </p>
          <span v-else class="skeleton line" />
        </div>
      </section>

      <div class="status-grid">
        <section class="card status" :class="info ? (db.schema_ok ? 'ok' : 'bad') : ''">
          <span class="s-icon"><AppIcon :name="!info ? 'layers' : db.schema_ok ? 'check' : 'alert'" :size="18" :stroke="2.2" /></span>
          <div class="s-body">
            <span class="s-label">Схема базы данных</span>
            <template v-if="info">
              <strong>{{ db.schema_ok ? 'Актуальна' : 'Требуется обновление' }}</strong>
              <span class="s-sub">
                <template v-if="db.schema_ok">Миграция <code>{{ db.schema_current }}</code></template>
                <template v-else>Текущая <code>{{ db.schema_current || 'нет' }}</code>, нужна <code>{{ db.schema_head }}</code>. Запустите миграции перед работой.</template>
              </span>
            </template>
            <span v-else class="skeleton line" />
          </div>
        </section>

        <section class="card status neutral">
          <span class="s-icon"><AppIcon name="server" :size="18" /></span>
          <div class="s-body">
            <span class="s-label">База данных</span>
            <template v-if="info">
              <strong>{{ DIALECTS[db.dialect] || db.dialect }}</strong>
              <span class="s-sub num">Версия сервера {{ db.server_version || '—' }}</span>
            </template>
            <span v-else class="skeleton line" />
          </div>
        </section>

        <section class="card status neutral">
          <span class="s-icon"><AppIcon name="upload" :size="18" /></span>
          <div class="s-body">
            <span class="s-label">Последняя загрузка данных</span>
            <template v-if="info?.last_import">
              <strong>{{ DATASETS[info.last_import.dataset] || info.last_import.dataset }}</strong>
              <span class="s-sub" :title="formatDateTime(info.last_import.created_at)">
                {{ info.last_import.filename }} · {{ info.last_import.username }} · {{ formatRelative(info.last_import.created_at) }}
              </span>
            </template>
            <template v-else-if="info"><strong>Загрузок не было</strong><span class="s-sub">Файлы ещё не импортировались</span></template>
            <span v-else class="skeleton line" />
          </div>
        </section>
      </div>

      <section class="card">
        <header class="card-head"><h3>Данные</h3><span class="hint">Количество записей в базе</span></header>
        <div class="card-body counts">
          <component :is="c.to ? 'router-link' : 'div'" v-for="c in COUNTS" :key="c.key" :to="c.to" class="count" :class="{ link: c.to }">
            <span class="c-icon"><AppIcon :name="c.icon" :size="16" /></span>
            <span class="c-text">
              <span class="c-value num">
                <template v-if="info">{{ formatNumber(info.counts[c.key]) }}</template>
                <span v-else class="skeleton line short" />
              </span>
              <span class="c-label">{{ c.label }}</span>
            </span>
            <AppIcon v-if="c.to" name="chevron-right" :size="14" class="c-go" />
          </component>
        </div>
      </section>

      <section class="card">
        <header class="card-head"><h3>Параметры сервера</h3><span class="hint">Задаются в настройках окружения при развёртывании</span></header>
        <div class="card-body">
          <dl class="settings">
            <div v-for="s in settings" :key="s.label" class="setting">
              <dt>{{ s.label }}<small v-if="s.hint">{{ s.hint }}</small></dt>
              <dd class="num"><template v-if="info">{{ s.value }}</template><span v-else class="skeleton line short" /></dd>
            </div>
          </dl>
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.narrow { max-width: 1100px; }
.hero { display: flex; align-items: center; gap: 16px; padding: 20px 22px; }
.hero img { border-radius: 12px; }
.hero-text { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 6px; }
.hero-text h2 { font-size: 19px; }
.meta { gap: 6px 14px; font-size: var(--fs-sm); color: var(--text-2); }
.meta b { font-weight: 650; color: var(--text); }
.skeleton.line { display: block; height: 14px; width: 180px; border-radius: 6px; }
.skeleton.line.short { width: 60px; display: inline-block; }
.status-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--sp-4); }
@media (max-width: 960px) { .status-grid { grid-template-columns: 1fr; } }
.status { display: flex; gap: 12px; padding: 16px 18px; min-width: 0; }
.s-icon { width: 36px; height: 36px; flex: 0 0 36px; display: grid; place-items: center; border-radius: 10px; background: var(--surface-3); color: var(--text-2); }
.status.ok .s-icon { background: color-mix(in srgb, var(--light-green) 14%, transparent); color: var(--light-green); }
.status.bad { border-color: color-mix(in srgb, var(--light-red) 45%, var(--border)); }
.status.bad .s-icon { background: color-mix(in srgb, var(--light-red) 13%, transparent); color: var(--light-red); }
.s-body { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.s-label { font-size: var(--fs-xs); color: var(--muted); }
.s-body strong { font-size: var(--fs-md); font-weight: 640; }
.s-sub { font-size: var(--fs-xs); color: var(--muted); overflow-wrap: anywhere; }
code { font-family: var(--font-mono); font-size: 11px; padding: 0 4px; border-radius: 4px; background: var(--surface-3); color: var(--text-2); }
.counts { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 10px; }
.count { display: flex; align-items: center; gap: 12px; padding: 12px 14px; border-radius: 12px; border: 1px solid var(--border); background: var(--surface-2); transition: border-color var(--t-fast), background var(--t-fast); }
.count.link:hover { border-color: var(--border-strong); background: var(--surface); }
.c-icon { width: 32px; height: 32px; flex: 0 0 32px; display: grid; place-items: center; border-radius: 9px; background: var(--surface); color: var(--muted); border: 1px solid var(--border); }
.c-text { flex: 1; display: flex; flex-direction: column; min-width: 0; line-height: 1.25; }
.c-value { font-size: 19px; font-weight: 680; letter-spacing: -0.01em; color: var(--text); }
.c-label { font-size: var(--fs-xs); color: var(--muted); }
.c-go { color: var(--faint); }
.count.link:hover .c-go { color: var(--text-2); }
.settings { margin: 0; display: flex; flex-direction: column; }
.setting { display: flex; align-items: baseline; justify-content: space-between; gap: 16px; padding: 10px 0; border-bottom: 1px dashed var(--border); }
.setting:last-child { border-bottom: 0; }
.setting dt { display: flex; flex-direction: column; color: var(--text-2); }
.setting dt small { font-size: var(--fs-xs); color: var(--muted); }
.setting dd { margin: 0; font-weight: 600; color: var(--text); white-space: nowrap; }
</style>
