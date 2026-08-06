<template>
  <div v-if="loading" class="tempty">Загрузка…</div>
  <template v-else>
    <div class="filters">
      <div class="tinfo" style="flex:1;margin:0">
        Правила светофора партнёрств. Всего партнёрств: {{ total }}.
      </div>
      <router-link class="btn btn-g" to="/product">Дашборд партнёрств</router-link>
      <button v-if="canEdit" class="btn btn-p" :disabled="!dirty" @click="save">Сохранить</button>
    </div>

    <div v-if="!canEdit" class="tinfo" style="margin-bottom:12px">
      Изменять правила может только администратор.
    </div>

    <div v-for="g in groups" :key="g.key" class="ccard" style="margin-bottom:16px">
      <div class="ctitle">{{ g.title }}</div>
      <p class="dset-hint">{{ HINTS[g.key] }}</p>
      <div class="twrap">
        <div class="tscroll">
          <table>
            <thead>
              <tr>
                <th>Правило</th>
                <th style="width:180px">Светофор</th>
                <th v-if="g.key === 'cert_age'" style="width:150px">Порог, лет</th>
                <th style="width:110px">Партнёрств</th>
                <th style="width:90px">Доля</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in g.rules" :key="r.key">
                <td class="td-p">{{ r.label }}</td>
                <td>
                  <select v-if="canEdit" class="fs" v-model="r.light">
                    <option v-for="l in LIGHT_OPTIONS" :key="l.value" :value="l.value">{{ l.label }}</option>
                  </select>
                  <template v-else>
                    <span class="light-dot" :class="'light-' + r.light"></span>
                    {{ lightLabel(r.light) }}
                  </template>
                </td>
                <td v-if="g.key === 'cert_age'">
                  <input v-if="canEdit && r.threshold !== null" class="fi" type="number"
                         step="0.5" min="0.5" v-model.number="r.threshold" style="width:90px">
                  <span v-else class="td-muted">{{ r.threshold === null ? 'свыше' : r.threshold }}</span>
                </td>
                <td class="td-mono">{{ statOf(r.key).count }}</td>
                <td class="td-mono">{{ statOf(r.key).share }}%</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <div class="ccard">
      <div class="ctitle">Сводка по светофору</div>
      <div class="twrap">
        <div class="tscroll">
          <table>
            <thead><tr><th>Группа</th><th>Правило</th><th>Светофор</th><th>Партнёрств</th><th>Доля</th></tr></thead>
            <tbody>
              <tr v-for="row in rows" :key="row.key">
                <td class="td-muted">{{ row.group }}</td>
                <td class="td-p">{{ row.label }}</td>
                <td><span class="light-dot" :class="'light-' + row.light"></span> {{ lightLabel(row.light) }}</td>
                <td class="td-mono">{{ row.count }}</td>
                <td class="td-mono">{{ row.share }}%</td>
              </tr>
              <tr v-if="!rows.length"><td colspan="5" class="tempty">Нет данных о партнёрствах</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </template>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api/client.js'
import { useAuthStore } from '../stores/auth.js'
import { toastOk } from '../composables/useToast.js'

const auth = useAuthStore()
const canEdit = computed(() => auth.isAdmin)

const loading = ref(true)
const rules = ref([])
const saved = ref([])
const rows = ref([])

const LIGHT_OPTIONS = [
  { value: 'green', label: 'Норма' },
  { value: 'yellow', label: 'Внимание' },
  { value: 'red', label: 'Критично' },
  { value: 'gray', label: 'Не оценивается' },
]
const LIGHT_LABELS = Object.fromEntries(LIGHT_OPTIONS.map(l => [l.value, l.label]))
function lightLabel(light) { return LIGHT_LABELS[light] || light }

const GROUP_ORDER = ['status', 'nda', 'agreement', 'cert_age']
const HINTS = {
  status: 'Статусы партнёрств категориальные, поэтому цвет задаётся для каждого статуса, а не порогом.',
  nda: 'Цвет для подписанного и неподписанного NDA.',
  agreement: 'Цвет для подписанного и неподписанного соглашения.',
  cert_age: 'Правила проверяются сверху вниз: порог — максимальный возраст сертификата в годах, ' +
            'последнее правило действует для всего, что старше.',
}

const groups = computed(() => GROUP_ORDER
  .map(key => ({
    key,
    title: rules.value.find(r => r.group_key === key)?.group || key,
    rules: rules.value.filter(r => r.group_key === key),
  }))
  .filter(g => g.rules.length))

const total = computed(() => rows.value
  .filter(r => r.group === groups.value.find(g => g.key === 'status')?.title)
  .reduce((sum, r) => sum + r.count, 0))

const statsByKey = computed(() => Object.fromEntries(rows.value.map(r => [r.key, r])))
function statOf(key) { return statsByKey.value[key] || { count: 0, share: 0 } }

/** Only changed rules are sent, and a threshold of 0 or less would be rejected. */
const changed = computed(() => {
  const before = Object.fromEntries(saved.value.map(r => [r.key, r]))
  const out = []
  for (const r of rules.value) {
    const b = before[r.key]
    if (!b) continue
    const item = { key: r.key }
    if (r.light !== b.light) item.light = r.light
    if (r.threshold !== null && Number(r.threshold) > 0 && Number(r.threshold) !== b.threshold) {
      item.threshold = Number(r.threshold)
    }
    if (item.light !== undefined || item.threshold !== undefined) out.push(item)
  }
  return out
})

const dirty = computed(() => changed.value.length > 0)

async function loadData() {
  loading.value = true
  try {
    rules.value = await api.get('/partnerships/traffic-light/rules')
    saved.value = rules.value.map(r => ({ ...r }))
    try {
      rows.value = await api.get('/partnerships/traffic-light')
    } catch { /* the rules are still editable without partnership records */ }
  } finally { loading.value = false }
}

async function save() {
  try {
    rules.value = await api.put('/partnerships/traffic-light/rules', { rules: changed.value })
    saved.value = rules.value.map(r => ({ ...r }))
    rows.value = await api.get('/partnerships/traffic-light')
    toastOk('Правила светофора сохранены')
  } catch { /* the API layer already surfaced the reason as a toast */ }
}

onMounted(loadData)
</script>
