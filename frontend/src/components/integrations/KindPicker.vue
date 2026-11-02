<script setup>
import AppIcon from '@/components/ui/AppIcon.vue'
import AppModal from '@/components/ui/AppModal.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import { adminOnlyFor, kindIcon, richPreview } from '@/domain/integrations'

/**
 * «Подключить систему»: все виды подключений сервера в его порядке (order: «По Делу», «Пульс проекта», Jira,
 * Confluence, Bitrix24, почтовый ящик Exchange, 1С, папка «Входящие») с описанием и действиями; одиночный вид,
 * который уже подключён, недоступен; вид «только администратор» (Confluence) — недоступен остальным, с пояснением.
 */
const props = defineProps({
  kinds: { type: Array, default: () => [] },
  integrations: { type: Array, default: () => [] },
  isAdmin: { type: Boolean, default: true },
})
const emit = defineEmits(['close', 'pick'])
const taken = (kind) => kind.singleton && props.integrations.some((i) => i.kind === kind.kind)
const locked = (kind) => adminOnlyFor(kind, props.isAdmin)
const unavailable = (kind) => taken(kind) || locked(kind)
</script>

<template>
  <AppModal title="Подключить систему" subtitle="Выберите систему — форма настроек, проверка и действия зависят от вида подключения" :width="760" @close="emit('close')">
    <EmptyState v-if="!kinds.length" compact icon="plug" title="Видов подключений нет" text="Сервер не сообщил ни одного вида подключения: коннекторы регистрируются в app/integrations/connectors." />
    <ul v-else class="kinds" role="list">
      <li v-for="k in kinds" :key="k.kind">
        <button type="button" class="kind" :disabled="unavailable(k)" :data-kind="k.kind" :data-testid="`kind-${k.kind}`" @click="emit('pick', k)">
          <span class="k-icon"><AppIcon :name="kindIcon(k.kind)" :size="20" /></span>
          <span class="k-text">
            <b>{{ k.title }}</b>
            <span class="desc">{{ richPreview(k.description, 200) || 'Без описания' }}</span>
            <span v-if="k.actions?.length" class="acts">{{ k.actions.map((a) => a.label).join(' · ') }}</span>
            <span v-if="taken(k)" class="taken">Уже подключено — такое подключение может быть только одно</span>
            <span v-else-if="locked(k)" class="taken" data-testid="kind-admin-only"><AppIcon name="lock" :size="12" />{{ k.admin_only_note || 'Только администратор' }}</span>
            <span v-else-if="k.admin_only_note" class="admin-note">{{ k.admin_only_note }}</span>
          </span>
          <AppIcon v-if="!unavailable(k)" name="chevron-right" :size="16" class="chev" />
        </button>
      </li>
    </ul>
  </AppModal>
</template>

<style scoped>
.kinds { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.kind { width: 100%; height: 100%; display: flex; align-items: flex-start; gap: 12px; padding: 14px; border: 1px solid var(--border); border-radius: 12px; background: var(--surface); color: var(--text); text-align: left; cursor: pointer; transition: border-color var(--t-fast), background var(--t-fast); }
.kind:hover:not(:disabled) { border-color: var(--accent); background: color-mix(in srgb, var(--accent) 4%, var(--surface)); }
.kind:disabled { cursor: not-allowed; opacity: .6; }
.k-icon { width: 40px; height: 40px; flex: 0 0 40px; display: grid; place-items: center; border-radius: 12px; background: var(--brand-soft); color: var(--brand); }
.k-text { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 3px; }
.k-text b { font-size: var(--fs-base); font-weight: 650; }
.desc { font-size: var(--fs-sm); color: var(--text-2); line-height: 1.45; }
.acts { font-size: var(--fs-xs); color: var(--muted); }
.taken { display: inline-flex; align-items: center; gap: 4px; font-size: var(--fs-xs); color: color-mix(in srgb, var(--light-yellow) 80%, var(--text)); }
.admin-note { font-size: var(--fs-xs); color: var(--muted); }
.chev { flex: 0 0 auto; margin-top: 12px; color: var(--faint); }
@media (max-width: 640px) { .kinds { grid-template-columns: minmax(0, 1fr); } }
</style>
