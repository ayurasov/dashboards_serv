<template>
  <div v-if="loading" class="tempty">Загрузка…</div>
  <template v-else>
    <div class="filters">
      <select class="fsel" v-model="filterEntity"><option value="">Все типы</option><option value="month">Месяцы</option><option value="employee">Сотрудники</option><option value="metric">Метрики</option><option value="user">Пользователи</option><option value="traffic_light">Светофор</option><option value="dashboard">Дашборды</option></select>
      <select class="fsel" v-model="filterAction"><option value="">Все действия</option><option value="create">Создание</option><option value="update">Изменение</option><option value="delete">Удаление</option></select>
      <input class="srch" placeholder="Пользователь…" v-model="filterUser" style="max-width:200px">
    </div>
    <div class="twrap">
      <div class="tscroll">
        <table>
          <thead><tr><th>Время</th><th>Пользователь</th><th>Действие</th><th>Объект</th><th>ID</th><th>Было</th><th>Стало</th></tr></thead>
          <tbody>
            <tr v-for="(e, i) in filtered" :key="i">
              <td class="td-mono">{{ formatTime(e.timestamp) }}</td>
              <td class="td-p">{{ e.username }}</td>
              <td><span class="sb" :class="actionClass(e.action)">{{ actionLabel(e.action) }}</span></td>
              <td class="td-muted">{{ entityLabel(e.entity_type) }}</td>
              <td class="td-mono">{{ e.entity_id }}</td>
              <td class="td-mono" style="max-width:200px;overflow:hidden;text-overflow:ellipsis">{{ e.before_json || '—' }}</td>
              <td class="td-mono" style="max-width:200px;overflow:hidden;text-overflow:ellipsis">{{ e.after_json || '—' }}</td>
            </tr>
            <tr v-if="!filtered.length"><td colspan="7" class="tempty">Нет записей</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </template>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api/client.js'

const loading = ref(true)
const entries = ref([])
const filterEntity = ref('')
const filterAction = ref('')
const filterUser = ref('')

const filtered = computed(() => {
  let list = entries.value
  if (filterEntity.value) list = list.filter(e => e.entity_type === filterEntity.value)
  if (filterAction.value) list = list.filter(e => e.action === filterAction.value)
  if (filterUser.value) list = list.filter(e => e.username?.toLowerCase().includes(filterUser.value.toLowerCase()))
  return list
})

function formatTime(ts) { return new Date(ts).toLocaleString('ru-RU') }
function actionLabel(a) { return { create: 'Создание', update: 'Изменение', delete: 'Удаление' }[a] || a }
function entityLabel(t) { return { month: 'Месяц', employee: 'Сотрудник', metric: 'Метрика', user: 'Пользователь', traffic_light: 'Светофор', dashboard: 'Дашборд' }[t] || t }
function actionClass(a) { return { create: 's-hired', delete: 's-fired', update: 's-fired' }[a] || 's-hired' }

async function loadData() {
  loading.value = true
  try { entries.value = await api.get('/audit?limit=500') } finally { loading.value = false }
}

onMounted(loadData)
</script>
