<template>
  <div v-if="loading" class="tempty">Загрузка…</div>
  <template v-else>
    <div class="ccard" style="margin-bottom:16px">
      <div class="ctitle">Настройка порогов светофора</div>
      <p style="font-size:.75rem;color:var(--c-muted);margin-bottom:12px">
        Зелёный — норма, жёлтый — внимание, красный — критично.
        Для направления «меньше — лучше» (текучесть, время закрытия) пороги задают верхнюю
        границу зелёной и жёлтой зон. Для «больше — лучше» (офферы, испытательный срок) — нижнюю.
        Метрики без значения за месяц считаются красными.
      </p>
      <div class="twrap">
        <div class="tscroll">
          <table>
            <thead><tr><th>Метрика</th><th>Направление</th><th>Зелёный порог</th><th>Жёлтый порог</th><th>Включён</th><th></th></tr></thead>
            <tbody>
              <tr v-for="r in rules" :key="r.metric_key">
                <td class="td-p">{{ r.label }}</td>
                <td>
                  <select class="fs" v-model="r.direction" style="width:170px">
                    <option value="higher_is_better">Больше — лучше</option>
                    <option value="lower_is_better">Меньше — лучше</option>
                  </select>
                </td>
                <td><input class="fi" type="number" step="0.01" v-model="r.green_threshold" style="width:80px"></td>
                <td><input class="fi" type="number" step="0.01" v-model="r.yellow_threshold" style="width:80px"></td>
                <td><input type="checkbox" v-model="r.enabled"></td>
                <td><button class="btn btn-p" style="font-size:.75rem;padding:2px 8px" @click="saveRule(r)">Сохранить</button></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <div class="ccard">
      <div class="ctitle">
        Текущие бенчмарки
        <router-link class="btn btn-g" style="font-size:.75rem;padding:4px 8px" to="/hr/benchmarks">Все бенчмарки</router-link>
      </div>
      <div class="twrap">
        <div class="tscroll">
          <table>
            <thead><tr><th>Метрика</th><th>Год</th><th>Цель</th><th>Факт</th></tr></thead>
            <tbody>
              <tr v-for="b in benchmarks" :key="b.id">
                <td class="td-p">{{ b.metric_label }}</td>
                <td class="td-mono">{{ b.year }}</td>
                <td class="td-mono">{{ b.target_value ?? '—' }}</td>
                <td class="td-mono">
                  <span class="light-dot" :class="'light-'+b.status"></span>
                  {{ b.current_value ?? '—' }}
                </td>
              </tr>
              <tr v-if="!benchmarks.length"><td colspan="4" class="tempty">Нет бенчмарков</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </template>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api/client.js'
import { toastOk } from '../composables/useToast.js'

const loading = ref(true)
const rules = ref([])
const benchmarks = ref([])

async function loadData() {
  loading.value = true
  try {
    rules.value = await api.get('/traffic-light/with-metrics')
    benchmarks.value = await api.get('/hr/benchmarks')
  } finally { loading.value = false }
}

async function saveRule(r) {
  try {
    await api.put(`/traffic-light/${r.metric_key}`, {
      green_threshold: r.green_threshold !== null ? Number(r.green_threshold) : null,
      yellow_threshold: r.yellow_threshold !== null ? Number(r.yellow_threshold) : null,
      direction: r.direction,
      enabled: r.enabled,
    })
    toastOk('Сохранено')
  } catch { /* the API layer already surfaced the reason as a toast */ }
}

onMounted(loadData)
</script>
