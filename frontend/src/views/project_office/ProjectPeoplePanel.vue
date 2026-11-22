<script setup>
/** Люди месяца: часы по сотрудникам (сопоставленные) и внешним авторам + блок сопоставлений. */
import { computed, ref } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import AppModal from '@/components/ui/AppModal.vue'
import { projectOfficeApi } from '@/api/services'
import { useAsync } from '@/composables/useAsync'
import { useAuthStore } from '@/stores/auth'
import { toastOk } from '@/composables/useToast'
import { formatNumber } from '@/utils/format'

defineProps({
  people: { type: Array, default: () => [] },
  matched: { type: Number, default: 0 },
  total: { type: Number, default: 0 },
})
const auth = useAuthStore()
const canManage = computed(() => auth.can('project_office', 'manager'))

const identitiesOpen = ref(false)
const identities = useAsync(() => projectOfficeApi.identities(), { immediate: false })
const unmatched = useAsync(() => projectOfficeApi.unmatched(), { immediate: false })
function openIdentities() {
  identitiesOpen.value = true
  identities.reload()
  unmatched.reload()
}
const users = useAsync(() => projectOfficeApi.employees(), { immediate: false })
const picked = ref({})
async function link(email) {
  const user_id = Number(picked.value[email])
  if (!user_id) return
  try {
    await projectOfficeApi.addIdentity({ external_email: email, user_id, service: '*' })
    toastOk(`Автор ${email} сопоставлен`)
    unmatched.reload()
    identities.reload()
  } catch { /* тост уже показан */ }
}
async function remove(id) {
  try {
    await projectOfficeApi.deleteIdentity(id)
    identities.reload()
    unmatched.reload()
  } catch { /* тост уже показан */ }
}
const fmt = (v) => formatNumber(v)
</script>

<template>
  <section class="card">
    <header class="card-head">
      <h3>Люди месяца</h3>
      <span class="hint">{{ matched }} из {{ total }} авторов сопоставлены</span>
      <span class="spacer" />
      <button class="btn btn-sm" type="button" @click="openIdentities">
        <AppIcon name="link" :size="13" />Сопоставления
        <span v-if="unmatched.data.value?.length" class="badge badge-yellow count">{{ unmatched.data.value.length }}</span>
      </button>
    </header>
    <div class="card-body">
      <p v-if="!people.length" class="muted">Трудозатрат за месяц нет</p>
      <table v-else class="table table-compact">
        <thead>
          <tr><th>Кто</th><th class="num">Часы, ч</th></tr>
        </thead>
        <tbody>
          <tr v-for="p in people.slice(0, 12)" :key="p.email">
            <td>
              <template v-if="p.user_id">{{ p.name }}</template>
              <template v-else><span class="muted">{{ p.email }}</span> <span class="badge">внешний</span></template>
            </td>
            <td class="num">{{ fmt(p.hours) }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <AppModal v-if="identitiesOpen" title="Сопоставление авторов" :width="640" @close="identitiesOpen = false">
      <p class="muted intro">
        Авторы Jira и GitLab сопоставляются сотрудникам автоматически по e-mail. Здесь — исключения:
        другая почта, CI-бот, несколько учёток. Несопоставленные авторы не попадают в часы людей.
      </p>
      <h4>Не сопоставлены</h4>
      <p v-if="unmatched.loading.value && !unmatched.data.value" class="muted">Загрузка…</p>
      <p v-else-if="!unmatched.data.value?.length" class="muted ok-note">
        <AppIcon name="check" :size="14" />Все авторы сопоставлены
      </p>
      <table v-else class="table table-compact">
        <thead><tr><th>Автор</th><th class="num">Jira, ч</th><th class="num">Коммиты</th><th v-if="canManage">Сотрудник</th></tr></thead>
        <tbody>
          <tr v-for="a in unmatched.data.value" :key="a.email">
            <td>{{ a.email }}</td>
            <td class="num">{{ fmt(a.jira_hours) }}</td>
            <td class="num">{{ a.gitlab_commits }}</td>
            <td v-if="canManage" class="link-cell">
              <select v-model="picked[a.email]" class="select select-sm">
                <option :value="null">— выбрать —</option>
                <option v-for="u in users.data.value || []" :key="u.id" :value="u.id">{{ u.full_name }}</option>
              </select>
              <button class="btn btn-sm" type="button" :disabled="!picked[a.email]" @click="link(a.email)">
                <AppIcon name="link" :size="13" />Связать
              </button>
              <button class="btn btn-sm btn-ghost" type="button" title="Обновить список сотрудников" @click="users.reload()">
                <AppIcon name="refresh" :size="13" />
              </button>
            </td>
          </tr>
        </tbody>
      </table>
      <template v-if="identities.data.value?.length">
        <h4>Сопоставления</h4>
        <table class="table table-compact">
          <thead><tr><th>Автор</th><th>Сотрудник</th><th v-if="canManage"></th></tr></thead>
          <tbody>
            <tr v-for="i in identities.data.value" :key="i.id">
              <td>{{ i.external_email }} <span class="badge">{{ i.service }}</span></td>
              <td>{{ i.user_name }}</td>
              <td v-if="canManage" class="link-cell">
                <button class="btn btn-sm btn-danger" type="button" @click="remove(i.id)"><AppIcon name="trash" :size="13" /></button>
              </td>
            </tr>
          </tbody>
        </table>
      </template>
      <template #footer>
        <button class="btn" type="button" @click="identitiesOpen = false">Закрыть</button>
      </template>
    </AppModal>
  </section>
</template>

<style scoped>
.intro { margin-bottom: 12px; line-height: 1.5; }
h4 { font-size: var(--fs-sm); margin: 14px 0 8px; }
.count { margin-left: 4px; }
.link-cell { display: flex; gap: 6px; align-items: center; justify-content: flex-end; }
.link-cell .select { width: 200px; }
.ok-note { display: flex; gap: 6px; align-items: center; }
</style>
