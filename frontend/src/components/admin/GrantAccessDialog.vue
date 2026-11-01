<script setup>
import { computed, ref } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import AppModal from '@/components/ui/AppModal.vue'

/**
 * «Выдать доступ» (ADR-0008): включить учётную запись и выбрать способ входа — временный пароль
 * системы или учётная запись домена (если вход по домену включён).
 */
const props = defineProps({
  user: { type: Object, required: true },
  ldapEnabled: { type: Boolean, default: false },
  busy: { type: Boolean, default: false },
})
const emit = defineEmits(['close', 'confirm'])
const method = ref(props.ldapEnabled && props.user.auth_source === 'ldap' ? 'ldap' : 'password')
const noEmail = computed(() => !props.user.email)
</script>

<template>
  <AppModal title="Выдать доступ" :subtitle="`${user.full_name} · ${user.username}`" :width="'min(500px, calc(100vw - 48px))'" @close="emit('close')">
    <p v-if="!user.is_active" class="note"><AppIcon name="info" :size="14" />Учётная запись будет включена.</p>
    <div class="options" role="radiogroup" aria-label="Способ входа">
      <label class="option" :class="{ on: method === 'password' }">
        <input v-model="method" type="radio" value="password" name="grant-method" />
        <span class="radio" />
        <span class="o-text"><b>Временный пароль</b><small>Пароль покажется один раз — передайте его сотруднику; при первом входе он задаст свой.</small></span>
      </label>
      <label class="option" :class="{ on: method === 'ldap', off: !ldapEnabled || noEmail }">
        <input v-model="method" type="radio" value="ldap" name="grant-method" :disabled="!ldapEnabled || noEmail" />
        <span class="radio" />
        <span class="o-text"><b>Вход по учётной записи домена</b>
          <small v-if="!ldapEnabled">Вход по домену не настроен на сервере.</small>
          <small v-else-if="noEmail">Укажите сотруднику e-mail — по нему учётная запись сопоставится с каталогом.</small>
          <small v-else>Логин и пароль домена; пароль системы не нужен.</small>
        </span>
      </label>
    </div>
    <template #footer>
      <button class="btn" type="button" @click="emit('close')">Отмена</button>
      <button class="btn btn-primary" type="button" :disabled="busy" data-testid="grant-confirm" @click="emit('confirm', method)">{{ busy ? 'Выдача…' : 'Выдать доступ' }}</button>
    </template>
  </AppModal>
</template>

<style scoped>
.note { display: flex; align-items: center; gap: 7px; margin-bottom: 12px; font-size: var(--fs-sm); color: var(--text-2); }
.options { display: flex; flex-direction: column; gap: 8px; }
.option { position: relative; display: flex; gap: 12px; align-items: flex-start; padding: 12px 14px; border: 1px solid var(--border); border-radius: var(--radius-lg); cursor: pointer; transition: border-color var(--t-fast), background var(--t-fast); }
.option:hover:not(.off) { border-color: var(--border-strong); }
.option.on { border-color: color-mix(in srgb, var(--brand) 45%, var(--border)); background: color-mix(in srgb, var(--brand) 3%, var(--surface)); }
.option.off { opacity: .6; cursor: not-allowed; }
.option input { position: absolute; opacity: 0; width: 1px; height: 1px; }
.radio { width: 17px; height: 17px; flex: 0 0 17px; margin-top: 1px; border-radius: 50%; border: 1.5px solid var(--border-strong); background: var(--surface); }
.on .radio { border-color: var(--brand); box-shadow: inset 0 0 0 3.5px var(--surface), inset 0 0 0 9px var(--brand); }
.option:has(input:focus-visible) .radio { outline: 2px solid var(--focus); outline-offset: 2px; }
.o-text { display: flex; flex-direction: column; gap: 2px; }
.o-text b { font-weight: 600; }
.o-text small { font-size: var(--fs-sm); color: var(--muted); line-height: 1.4; }
</style>
