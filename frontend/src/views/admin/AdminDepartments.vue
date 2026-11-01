<script setup>
import { computed, reactive, ref } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import AppModal from '@/components/ui/AppModal.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import UserAvatar from '@/components/admin/UserAvatar.vue'
import { adminApi } from '@/api/services'
import { useAsync } from '@/composables/useAsync'
import { confirm } from '@/composables/useConfirm'
import { toastOk } from '@/composables/useToast'
import { formFieldErrors } from '@/domain/admin'
import { plural } from '@/utils/format'

/** Подразделения: справочник для пользователей (ограничение «только свои подразделения» в службе персонала). */
const { data, loading, reload } = useAsync(() => adminApi.departments())
const users = useAsync(() => adminApi.users())

const members = computed(() => {
  const map = {}
  for (const u of users.data.value || []) {
    for (const d of u.departments) (map[d.id] ||= []).push(u)
  }
  return map
})
const rows = computed(() => (data.value || []).map((d) => ({ ...d, users: members.value[d.id] || [] })))
const withoutDepartment = computed(() => (users.data.value || []).filter((u) => !u.departments.length).length)
const summary = computed(() => {
  const n = rows.value.length
  return `${n} ${plural(n, ['подразделение', 'подразделения', 'подразделений'])}`
})
const MAX_AVATARS = 4

// ---------- форма ----------
const editing = ref(null)
const form = reactive({ name: '', code: '' })
const saving = ref(false)
const formError = ref('')
const fieldErrors = ref({})

function open(row = null) {
  editing.value = row || {}
  Object.assign(form, { name: row?.name || '', code: row?.code || '' })
  formError.value = ''
  fieldErrors.value = {}
}
async function save() {
  formError.value = ''
  fieldErrors.value = {}
  const body = { name: form.name.trim(), code: form.code.trim().toUpperCase() }
  if (!body.name) fieldErrors.value.name = 'Укажите название'
  if (!body.code) fieldErrors.value.code = 'Укажите код'
  if (Object.keys(fieldErrors.value).length) return
  saving.value = true
  try {
    if (editing.value.id) await adminApi.updateDepartment(editing.value.id, body)
    else await adminApi.createDepartment(body)
    toastOk(editing.value.id ? 'Подразделение изменено' : 'Подразделение добавлено')
    editing.value = null
    reload()
    users.reload()
  } catch (e) {
    formError.value = e.message
    fieldErrors.value = formFieldErrors(e.fields)
    if (/^Название/.test(e.message)) fieldErrors.value.name ||= 'Уже используется'
    if (/^Код/.test(e.message)) fieldErrors.value.code ||= 'Уже используется'
  } finally {
    saving.value = false
  }
}
async function remove(row) {
  const count = row.users.length
  const message = count
    ? `Подразделение указано у ${count} ${plural(count, ['пользователя', 'пользователей', 'пользователей'])} — у них оно будет снято. Ограничение «только свои подразделения» перестанет показывать его данные.`
    : 'Пользователей в подразделении нет.'
  if (!await confirm({ title: `Удалить «${row.name}»?`, message, confirmText: 'Удалить', danger: true })) return false
  const result = await adminApi.deleteDepartment(row.id)
  toastOk(result?.message || 'Подразделение удалено')
  reload()
  users.reload()
  return true
}
async function removeEditing() {
  const row = rows.value.find((r) => r.id === editing.value?.id)
  if (row && await remove(row)) editing.value = null
}
function names(list) {
  return list.map((u) => u.full_name).join('\n')
}
</script>

<template>
  <div class="page narrow">
    <PageHeader title="Подразделения" description="Справочник подразделений компании: привязка пользователей и ограничение доступа к данным службы персонала">
      <button class="btn btn-primary" type="button" @click="open()"><AppIcon name="plus" :size="15" />Добавить подразделение</button>
    </PageHeader>

    <section class="card">
      <header class="card-head">
        <h3>Все подразделения</h3>
        <span class="hint">{{ data ? summary : '' }}<template v-if="users.data.value && withoutDepartment"> · без подразделения: {{ withoutDepartment }} {{ plural(withoutDepartment, ['пользователь', 'пользователя', 'пользователей']) }}</template></span>
      </header>
      <div class="card-body table-wrap">
        <table v-if="data && rows.length" class="table">
          <thead>
            <tr><th>Название</th><th>Код</th><th>Пользователи</th><th class="actions-col" /></tr>
          </thead>
          <tbody>
            <tr v-for="d in rows" :key="d.id" class="clickable" @click="open(d)">
              <td class="name">{{ d.name }}</td>
              <td><span class="code">{{ d.code }}</span></td>
              <td>
                <div v-if="d.users.length" class="members" :title="names(d.users)">
                  <span class="stack-avatars">
                    <UserAvatar v-for="u in d.users.slice(0, MAX_AVATARS)" :key="u.id" :name="u.full_name" :seed="u.username" :size="26" />
                  </span>
                  <span class="num count">{{ d.users.length }}</span>
                  <span class="muted">{{ plural(d.users.length, ['пользователь', 'пользователя', 'пользователей']) }}</span>
                </div>
                <span v-else-if="users.data.value" class="faint">Нет пользователей</span>
                <span v-else class="skeleton count-skel" />
              </td>
              <td class="actions-col" @click.stop>
                <button class="btn btn-icon btn-sm btn-ghost" type="button" title="Изменить" @click="open(d)"><AppIcon name="edit" :size="14" /></button>
                <button class="btn btn-icon btn-sm btn-ghost" type="button" title="Удалить" @click="remove(d)"><AppIcon name="trash" :size="14" /></button>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-else-if="loading" class="skeleton-rows"><div v-for="i in 5" :key="i" class="skeleton" /></div>
        <EmptyState v-else icon="building" title="Подразделений пока нет" text="Добавьте подразделения, чтобы привязывать к ним пользователей.">
          <button class="btn btn-primary btn-sm" type="button" @click="open()">Добавить подразделение</button>
        </EmptyState>
      </div>
    </section>

    <p class="note muted"><AppIcon name="info" :size="14" />Подразделения пользователя задаются в его карточке в разделе «Пользователи».</p>

    <AppModal v-if="editing" :title="editing.id ? 'Подразделение' : 'Новое подразделение'" :subtitle="editing.id ? editing.name : ''" :width="480" @close="editing = null">
      <form id="dept-form" class="stack" novalidate @submit.prevent="save">
        <label class="field"><span>Название</span>
          <input v-model="form.name" class="input" :class="{ invalid: fieldErrors.name }" maxlength="200" placeholder="Например, Финансовая служба" />
          <span v-if="fieldErrors.name" class="error">{{ fieldErrors.name }}</span>
        </label>
        <label class="field"><span>Код</span>
          <input v-model="form.code" class="input code-input" :class="{ invalid: fieldErrors.code }" maxlength="50" placeholder="FIN"
                 @input="form.code = form.code.toUpperCase()" />
          <span v-if="fieldErrors.code" class="error">{{ fieldErrors.code }}</span>
          <span v-else class="help">Короткое обозначение латиницей; хранится заглавными буквами</span>
        </label>
        <p v-if="editing.id && members[editing.id]?.length" class="muted small">
          Подразделение указано у {{ members[editing.id].length }} {{ plural(members[editing.id].length, ['пользователя', 'пользователей', 'пользователей']) }}.
        </p>
      </form>
      <p v-if="formError" class="form-error"><AppIcon name="alert" :size="14" />{{ formError }}</p>
      <template #footer>
        <button v-if="editing.id" class="btn btn-ghost btn-danger" type="button" @click="removeEditing">
          <AppIcon name="trash" :size="14" />Удалить
        </button>
        <span class="spacer" />
        <button class="btn" type="button" @click="editing = null">Отмена</button>
        <button class="btn btn-primary" type="submit" form="dept-form" :disabled="saving">{{ saving ? 'Сохранение…' : 'Сохранить' }}</button>
      </template>
    </AppModal>
  </div>
</template>

<style scoped>
.narrow { max-width: 1100px; }
.card-body.table-wrap { padding: 8px 0 4px; }
.name { font-weight: 560; }
.code { display: inline-block; padding: 1px 7px; border-radius: 6px; background: var(--surface-3); font-family: var(--font-mono); font-size: var(--fs-xs); font-weight: 600; color: var(--text-2); letter-spacing: .03em; }
.members { display: inline-flex; align-items: center; gap: 8px; }
.stack-avatars { display: inline-flex; }
.stack-avatars > * { margin-left: -7px; box-shadow: 0 0 0 2px var(--surface); }
.stack-avatars > *:first-child { margin-left: 0; }
.count { font-weight: 620; }
.count-skel { display: inline-block; width: 90px; height: 18px; }
.actions-col { width: 90px; text-align: right; white-space: nowrap; }
.actions-col .btn { opacity: .6; }
tr:hover .actions-col .btn { opacity: 1; }
.skeleton-rows { display: flex; flex-direction: column; gap: 10px; padding: 8px 16px 16px; }
.skeleton-rows .skeleton { height: 40px; }
.note { display: flex; align-items: center; gap: 6px; font-size: var(--fs-sm); margin-top: -8px; }
.code-input { font-family: var(--font-mono); letter-spacing: .04em; }
.code-input::placeholder { font-family: var(--font-sans); letter-spacing: 0; }
.help { font-size: var(--fs-xs); color: var(--muted); }
.error { font-size: var(--fs-xs); color: var(--light-red); }
.small { font-size: var(--fs-sm); }
.form-error { display: flex; align-items: center; gap: 6px; margin-top: 12px; font-size: var(--fs-sm); color: var(--light-red); }
</style>
