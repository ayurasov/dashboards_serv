<script setup>
import AppIcon from '@/components/ui/AppIcon.vue'
import { useAuthStore } from '@/stores/auth'

/**
 * Пустые «Входящие»: четыре пути, которыми данные попадают в систему, — папка на сервере, загрузка
 * файла, приём по API с ключом, подключения к системам. Любой путь ведёт к одному плану.
 */
defineProps({
  folderPath: { type: String, default: '' },
  canManage: { type: Boolean, default: false },
})
const emit = defineEmits(['upload', 'folder'])
const auth = useAuthStore()
</script>

<template>
  <section class="ways card" data-testid="inbox-ways">
    <header class="ways-head">
      <span class="w-icon"><AppIcon name="inbox" :size="22" /></span>
      <div>
        <h2>Входящих пока нет</h2>
        <p>Любой файл, откуда бы он ни пришёл, попадает сюда и проходит один путь: распознавание набора → план (что создастся, изменится, ошибки) → применение — сразу по правилу или после подтверждения. Повтор того же файла распознаётся и дважды не применяется.</p>
      </div>
    </header>
    <ol class="list">
      <li>
        <span class="n">1</span>
        <div>
          <h3><AppIcon name="folder" :size="15" />Папка «Входящие» на сервере</h3>
          <p>Выгрузки кладут в подпапку набора — <code>tp-weekly/</code>, <code>hr-months/</code>, <code>indicators/</code>… — или в корень. Планировщик забирает файлы сам.</p>
          <p v-if="folderPath" class="mono">{{ folderPath }}</p>
          <p v-else-if="canManage" class="muted">Папка не настроена: задайте INBOX_DIR на сервере.</p>
          <button v-if="canManage" type="button" class="btn btn-sm" @click="emit('folder')">Состояние папки</button>
        </div>
      </li>
      <li>
        <span class="n">2</span>
        <div>
          <h3><AppIcon name="upload" :size="15" />Загрузка файла</h3>
          <p>Excel, CSV или JSON прямо здесь: набор распознаётся или выбирается, план показывается до применения.</p>
          <button type="button" class="btn btn-primary btn-sm" data-testid="ways-upload" @click="emit('upload')"><AppIcon name="upload" :size="14" />Загрузить файл</button>
        </div>
      </li>
      <li>
        <span class="n">3</span>
        <div>
          <h3><AppIcon name="key" :size="15" />Приём по API с ключом</h3>
          <p>1С, скрипты и другие системы отправляют файл запросом <code>POST /api/inbound/v1/files</code> с ключом <code>dash_…</code> — без папки и почты.</p>
          <router-link v-if="auth.hasCapability('integrations.manage')" to="/admin/integrations?tab=keys" class="btn btn-sm">Выпустить ключ</router-link>
          <p v-else class="muted">Ключ выпускает администратор интеграций.</p>
        </div>
      </li>
      <li>
        <span class="n">4</span>
        <div>
          <h3><AppIcon name="plug" :size="15" />Подключения к системам</h3>
          <p>«По Делу», «Пульс проекта», Jira, Bitrix24, почта Exchange, 1С — по расписанию или по кнопке «Запустить»; забранные файлы и данные — здесь.</p>
          <router-link v-if="auth.hasCapability('integrations.manage')" to="/admin/integrations" class="btn btn-sm">Интеграции</router-link>
        </div>
      </li>
    </ol>
  </section>
</template>

<style scoped>
.ways { padding: 22px 24px; display: flex; flex-direction: column; gap: 20px; }
.ways-head { display: flex; gap: 16px; align-items: flex-start; }
.w-icon { width: 46px; height: 46px; flex: 0 0 46px; display: grid; place-items: center; border-radius: 14px; background: var(--brand-soft); color: var(--brand); }
.ways-head h2 { font-size: var(--fs-lg); }
.ways-head p { margin-top: 4px; max-width: 820px; font-size: var(--fs-sm); color: var(--text-2); line-height: 1.55; }
.list { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; }
.list li { display: flex; gap: 12px; padding: 14px; border: 1px solid var(--border); border-radius: 12px; background: var(--surface-2); }
.list li > div { display: flex; flex-direction: column; gap: 6px; min-width: 0; align-items: flex-start; }
.n { width: 24px; height: 24px; flex: 0 0 24px; display: grid; place-items: center; border-radius: 50%; background: var(--surface-3); color: var(--text-2); font-size: var(--fs-xs); font-weight: 700; }
.list h3 { display: flex; align-items: center; gap: 6px; font-size: var(--fs-sm); font-weight: 650; }
.list p { font-size: var(--fs-sm); color: var(--text-2); line-height: 1.5; }
.list code, .mono { font-family: var(--font-mono); font-size: var(--fs-xs); overflow-wrap: anywhere; }
.list code { padding: 0 4px; border-radius: 4px; background: var(--surface-3); }
.muted { color: var(--muted) !important; }
@media (max-width: 1200px) { .list { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 640px) {
  .ways { padding: 18px 16px; }
  .ways-head { flex-direction: column; gap: 10px; }
  .list { grid-template-columns: minmax(0, 1fr); }
}
</style>
