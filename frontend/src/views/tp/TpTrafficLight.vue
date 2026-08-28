<template>
  <div v-if="loading" class="tempty">Загрузка…</div>
  <div v-else>
    <div class="filters">
      <button class="btn btn-p" @click="save" :disabled="saving">{{ saving ? 'Сохранение…' : 'Сохранить' }}</button>
      <button class="btn btn-g" @click="load">Сбросить</button>
    </div>

    <div class="twrap" style="margin-top:12px">
      <div class="tscroll">
        <table>
          <thead>
            <tr><th>Показатель</th><th>Включён</th><th>Направление</th><th>Зелёный ≤/≥</th><th>Жёлтый ≤/≥</th></tr>
          </thead>
          <tbody>
            <tr v-for="(rule, key) in rules" :key="key">
              <td class="td-p">{{ LABELS[key] || key }}</td>
              <td><input type="checkbox" v-model="rule.enabled"></td>
              <td>
                <select class="cfsel" v-model="rule.direction">
                  <option value="less">меньше = лучше</option>
                  <option value="more">больше = лучше</option>
                </select>
              </td>
              <td><input class="fi" type="number" v-model.number="rule.green" style="width:80px"></td>
              <td><input class="fi" type="number" v-model.number="rule.yellow" style="width:80px"></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { tpApi } from '../../api/tp.js'

const loading = ref(true)
const saving  = ref(false)
const rules   = ref({})

const LABELS = {
  total_in_work: 'В работе (всего)', avail_total: 'Доступность (всего)',
  new_received: 'Новых получено', total_solved_week: 'Решено за неделю',
  ratio_solved_received: 'Коэф. решения', altos_avg_time: 'AltOS ср.время (ч)',
  altoffice_avg_time: 'AltOffice ср.время (ч)', altos_avail_total: 'AltOS дост. всего',
  altoffice_avail_total: 'AltOffice дост. всего',
}

async function load() {
  loading.value = true
  try { rules.value = await tpApi.getSetting('traffic_rules') }
  finally { loading.value = false }
}

async function save() {
  saving.value = true
  try { await tpApi.putSetting('traffic_rules', rules.value) }
  finally { saving.value = false }
}

onMounted(load)
</script>
