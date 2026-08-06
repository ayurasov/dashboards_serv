<template>
  <div v-if="loading" class="tempty">Загрузка…</div>
  <div v-else-if="error" class="tempty">Ошибка: {{ error }}</div>
  <template v-else>
    <div class="filters">
      <input class="srch" placeholder="Поиск по партнёру или продукту…" v-model="search">
      <select class="fsel" v-model="fStatus">
        <option value="">Все статусы</option>
        <option v-for="s in statuses" :key="s" :value="s">{{ s }}</option>
      </select>
    </div>

    <div class="ccard">
      <div class="ctitle">Хронология партнёрств <span style="font-weight:400;color:var(--c-muted)">{{ events.length }} событий</span></div>
      <div v-if="!events.length" class="tempty">Нет событий</div>
      <div v-else class="tl">
        <template v-for="group in grouped" :key="group.year">
          <div class="tl-year">{{ group.year }}</div>
          <div v-for="e in group.items" :key="e.id" class="tl-item">
            <span class="tl-dot" :style="{ background: dotColor(e.status) }"></span>
            <div class="tl-date">{{ formatDate(e.last_modified || e.cert_date) }}</div>
            <div class="tl-title">{{ e.partner }}</div>
            <div class="tl-meta">
              <span>{{ e.product || '—' }}</span>
              <span class="sb" :class="statusClass(e.status)">{{ e.status }}</span>
              <span v-if="e.almi_product" class="td-muted">{{ e.almi_product }}</span>
            </div>
            <div v-if="e.comment" class="tl-comment">{{ e.comment }}</div>
          </div>
        </template>
      </div>
    </div>
  </template>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api/client.js'
import { usePaletteStore } from '../stores/palette.js'
import { statusClass, statusTone, formatDate } from '../api/partnerships.js'

const palette = usePaletteStore()
const loading = ref(true)
const error = ref('')
const rows = ref([])
const search = ref('')
const fStatus = ref('')

const statuses = computed(() => [...new Set(rows.value.map(r => r.status).filter(Boolean))])

const events = computed(() => {
  const q = search.value.trim().toLowerCase()
  return rows.value.filter(r => {
    if (fStatus.value && r.status !== fStatus.value) return false
    if (!q) return true
    return [r.partner, r.product].some(v => v?.toLowerCase().includes(q))
  })
})

const grouped = computed(() => {
  const out = []
  for (const e of events.value) {
    const year = String(e.last_modified || e.cert_date || '').slice(0, 4) || '—'
    const last = out[out.length - 1]
    if (last && last.year === year) last.items.push(e)
    else out.push({ year, items: [e] })
  }
  return out
})

function dotColor(status) {
  return palette.trafficLight[statusTone(status)]
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    rows.value = await api.get('/partnerships/timeline')
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>
