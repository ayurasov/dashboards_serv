<script setup>
/** Таблица «проекты × часы»: факт месяца, прошлый месяц, план (редактирует менеджер службы). */
import { ref } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import { projectOfficeApi } from '@/api/services'
import { toastError } from '@/composables/useToast'
import { formatNumber } from '@/utils/format'


const props = defineProps({
  month: { type: String, required: true },
  projects: { type: Array, default: () => [] },
  canManage: { type: Boolean, default: false },
})
const emit = defineEmits(['changed'])
const editing = ref(null)
const draft = ref('')

function startEdit(projectKey, current) {
  editing.value = projectKey
  draft.value = current === null || current === undefined ? '' : String(current)
}
async function save(projectKey) {
  const hours = draft.value.trim() === '' ? 0 : Number(draft.value.replace(',', '.'))
  if (!Number.isFinite(hours) || hours < 0) {
    toastError('Часы — неотрицательное число')
    return
  }
  try {
    if (hours > 0) {
      await projectOfficeApi.setPlan(projectKey, { month: props.month, hours })
    } else {
      await projectOfficeApi.deletePlan(projectKey, props.month)
    }
    editing.value = null
    emit('changed')
  } catch { /* тост уже показан клиентом API */ }
}
const fmt = (v) => (v === null || v === undefined ? '—' : formatNumber(v))
</script>

<template>
  <section class="card">
    <header class="card-head">
      <h3>Часы по проектам</h3>
      <span class="hint">факт месяца · предыдущий · план{{ canManage ? ' — план редактируется' : '' }}</span>
    </header>
    <div class="card-body">
      <p v-if="!projects.length" class="muted">Трудозатрат за месяц нет</p>
      <table v-else class="table table-compact">
        <thead>
          <tr>
            <th>Проект</th>
            <th class="num">Факт, ч</th>
            <th class="num">Прошлый, ч</th>
            <th class="num">План, ч</th>
            <th v-if="canManage"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="p in projects" :key="p.project_key">
            <td>{{ p.project_key }}</td>
            <td class="num">{{ fmt(p.hours) }}</td>
            <td class="num muted">{{ fmt(p.prev_hours) }}</td>
            <td class="num">
              <template v-if="editing === p.project_key">
                <input v-model="draft" class="input input-sm plan-input" type="text" inputmode="decimal"
                       :aria-label="`План часов ${p.project_key}`" @keyup.enter="save(p.project_key)"
                       @keyup.esc="editing = null" />
              </template>
              <template v-else>{{ fmt(p.plan_hours) }}</template>
            </td>
            <td v-if="canManage" class="actions">
              <template v-if="editing === p.project_key">
                <button class="btn btn-sm" type="button" @click="save(p.project_key)"><AppIcon name="check" :size="13" />Сохранить</button>
                <button class="btn btn-sm btn-ghost" type="button" @click="editing = null">Отмена</button>
              </template>
              <button v-else class="btn btn-sm btn-ghost" type="button"
                      :title="p.plan_hours ? 'Изменить или очистить план (0 — удалить)' : 'Задать план часов'"
                      @click="startEdit(p.project_key, p.plan_hours)">
                <AppIcon :name="p.plan_hours ? 'edit' : 'plus'" :size="13" />{{ p.plan_hours ? 'Изменить' : 'План' }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style scoped>
.actions { display: flex; gap: 6px; justify-content: flex-end; }
.plan-input { width: 90px; text-align: right; height: 28px; }
</style>
