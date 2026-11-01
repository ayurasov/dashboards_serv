<script setup>
import AppIcon from '@/components/ui/AppIcon.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'
import { GUIDE_PDF } from '@/docs/guides'

/** «О программе»: назначение, возможности, документация, версия. */
const app = useAppStore()
const auth = useAuthStore()
const VERSION = __APP_VERSION__

const FEATURES = [
  { icon: 'home', title: 'Обзор', text: 'Главные показатели всех доступных служб на одной странице: светофор, динамика, свежесть данных.' },
  { icon: 'traffic', title: 'Сквозной отчёт', text: 'Статус компании и подразделений по показателям всех служб: от общей картины до нужной глубины — в пределах ваших прав.' },
  { icon: 'org', title: 'Структура компании', text: 'Оргсхема, люди, дерево и таблица подразделений; руководители и подчинённость.' },
  { icon: 'users', title: 'Служба персонала', text: 'Найм, адаптация и текучесть по месяцам, реестр приёмов и увольнений, сводка по периодам, цели.' },
  { icon: 'headset', title: 'Техническая поддержка', text: 'Недельный отчёт: нагрузка, трудозатраты по клиентам, решение заявок; аналитика заявок Naumen SD.' },
  { icon: 'handshake', title: 'Партнёрства', text: 'Реестр технологических партнёрств и сертификаций совместимости со светофором каждой записи.' },
  { icon: 'traffic', title: 'Светофор', text: 'Пороги «норма — внимание — критично» для метрик настраивает руководитель службы.' },
  { icon: 'pdf', title: 'Отчёты', text: 'PDF-отчёты и выгрузки в Excel по каждой странице — с текущими фильтрами.' },
  { icon: 'shield', title: 'Доступ', text: 'Уровни доступа к службам: просмотр, ввод данных, управление; журнал всех изменений.' },
]
</script>

<template>
  <div class="page about">
    <PageHeader title="О программе" />
    <section class="card hero">
      <img src="/logo.png" width="56" height="56" alt="" />
      <div class="hero-text">
        <h2>Дашборды компании</h2>
        <p>Показатели служб АЛМИ Партнер в одном месте — для руководителей и сотрудников служб</p>
      </div>
      <div class="version">
        <span class="muted">Версия</span>
        <strong class="num" data-testid="about-version">{{ VERSION }}</strong>
        <button class="btn btn-sm btn-ghost" type="button" @click="app.openReleaseNotes()"><AppIcon name="sparkles" :size="13" />Что нового</button>
      </div>
    </section>

    <section class="stack">
      <h3 class="h3">Возможности</h3>
      <div class="features">
        <div v-for="f in FEATURES" :key="f.title" class="card feature">
          <span class="f-icon"><AppIcon :name="f.icon" :size="18" /></span>
          <div><h4>{{ f.title }}</h4><p>{{ f.text }}</p></div>
        </div>
      </div>
    </section>

    <section class="stack">
      <h3 class="h3">Документация</h3>
      <div class="grid grid-2">
        <div class="card doc">
          <AppIcon name="book" :size="22" />
          <div>
            <h4>Руководство пользователя</h4>
            <p>Работа с дашбордами служб, фильтры, ввод данных, отчёты и выгрузки — с иллюстрациями.</p>
            <div class="row-wrap">
              <router-link to="/guide" class="btn btn-sm">Открыть</router-link>
              <a v-if="GUIDE_PDF.user.url" :href="GUIDE_PDF.user.url" :download="GUIDE_PDF.user.name" class="btn btn-sm btn-ghost"><AppIcon name="download" :size="13" />PDF</a>
            </div>
          </div>
        </div>
        <div v-if="auth.isAdmin" class="card doc">
          <AppIcon name="shield" :size="22" />
          <div>
            <h4>Руководство администратора</h4>
            <p>Пользователи и доступ, подразделения, светофор, загрузка данных, журнал, палитры, обслуживание.</p>
            <div class="row-wrap">
              <router-link to="/guide/admin" class="btn btn-sm">Открыть</router-link>
              <a v-if="GUIDE_PDF.admin.url" :href="GUIDE_PDF.admin.url" :download="GUIDE_PDF.admin.name" class="btn btn-sm btn-ghost"><AppIcon name="download" :size="13" />PDF</a>
            </div>
          </div>
        </div>
      </div>
    </section>
    <p class="muted copyright">© Александр Юрасов, 2026</p>
  </div>
</template>

<style scoped>
.about { max-width: 1100px; }
.hero { display: flex; align-items: center; gap: 18px; padding: 24px; flex-wrap: wrap; }
.hero img { border-radius: 14px; }
.hero-text { flex: 1; min-width: 240px; }
.hero-text h2 { font-size: 20px; }
.hero-text p { color: var(--muted); margin-top: 3px; }
.version { display: flex; align-items: center; gap: 10px; }
.version strong { font-size: 20px; }
.h3 { font-size: var(--fs-md); }
.features { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 12px; }
.feature { display: flex; gap: 12px; padding: 16px; }
.f-icon { width: 36px; height: 36px; flex: 0 0 36px; display: grid; place-items: center; border-radius: 10px; background: var(--surface-3); color: var(--text-2); }
.feature h4, .doc h4 { font-size: var(--fs-base); margin-bottom: 3px; }
.feature p, .doc p { font-size: var(--fs-sm); color: var(--muted); }
.doc { display: flex; gap: 14px; padding: 18px; color: var(--brand); }
.doc > div { color: var(--text); display: flex; flex-direction: column; gap: 10px; }
.copyright { font-size: var(--fs-xs); }
</style>
