<script setup>
import { ref } from 'vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import PageHeader from '@/components/ui/PageHeader.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import PalettePreview from '@/components/admin/PalettePreview.vue'
import PaletteEditor from '@/components/admin/PaletteEditor.vue'
import { adminApi } from '@/api/services'
import { useAsync } from '@/composables/useAsync'
import { confirm } from '@/composables/useConfirm'
import { toastOk } from '@/composables/useToast'
import { usePaletteStore } from '@/stores/palette'
import { LIGHT_SLOTS, normalizePalette } from '@/domain/admin'

/** Палитры: цвета светофора, графиков и акцента. Активная применяется у всех пользователей. */
const store = usePaletteStore()
const { data, loading, reload } = useAsync(() => adminApi.palettes())
const editor = ref(null)
const busy = ref(0)

/** Цвета для показа: недостающие дополнены, но серии графиков — как в палитре. */
function view(p) {
  const full = normalizePalette(p.colors)
  return { ...full, charts: p.colors?.charts?.length ? p.colors.charts : full.charts }
}

async function activate(p) {
  busy.value = p.id
  try {
    await adminApi.activatePalette(p.id)
    await store.load()
    toastOk(`Палитра «${p.name}» применена для всех пользователей`)
    reload()
  } catch {} finally {
    busy.value = 0
  }
}
async function remove(p) {
  if (!await confirm({ title: `Удалить палитру «${p.name}»?`, message: 'Палитру нельзя будет восстановить.', confirmText: 'Удалить', danger: true })) return
  let result
  try { result = await adminApi.deletePalette(p.id) } catch { return } // ошибку показал клиент API
  toastOk(result?.message || 'Палитра удалена')
  reload()
}
function create() {
  editor.value = { name: 'Новая палитра' }
}
function duplicate(p) {
  editor.value = { base: p.colors, name: `${p.name} — копия` }
}
function edit(p) {
  editor.value = { palette: p }
}
async function onSaved(saved) {
  const wasNew = !editor.value?.palette
  editor.value = null
  toastOk(wasNew ? `Палитра «${saved.name}» создана` : 'Палитра сохранена')
  reload()
  if (saved.is_active) await store.load()
}
</script>

<template>
  <div class="page">
    <PageHeader title="Палитры" description="Цвета светофора, графиков и акцента интерфейса. Активная палитра применяется у всех пользователей">
      <button class="btn btn-primary" type="button" @click="create"><AppIcon name="plus" :size="15" />Новая палитра</button>
    </PageHeader>

    <div v-if="loading && !data" class="cards">
      <div v-for="i in 3" :key="i" class="card skeleton" style="height: 360px" />
    </div>
    <EmptyState v-else-if="data && !data.length" icon="palette" title="Палитр нет" text="Создайте палитру — её можно будет сделать активной." />

    <div v-else class="cards">
      <article v-for="p in data" :key="p.id" class="card pal" :class="{ active: p.is_active }">
        <header class="pal-head">
          <div class="pal-title">
            <h3>{{ p.name }}</h3>
            <div class="row-wrap tags">
              <span v-if="p.is_active" class="badge badge-green"><AppIcon name="check" :size="11" :stroke="2.6" />Активна</span>
              <span v-if="p.is_preset" class="badge badge-gray">Встроенная</span>
            </div>
          </div>
          <div class="strip" aria-hidden="true">
            <i v-for="s in LIGHT_SLOTS" :key="s.key" :style="{ background: view(p).traffic_light[s.key] }" :title="`${s.label}: ${view(p).traffic_light[s.key]}`" />
            <b />
            <i v-for="(c, i) in view(p).charts" :key="i" :style="{ background: c }" :title="`Серия ${i + 1}: ${c}`" />
          </div>
        </header>

        <PalettePreview :colors="view(p)" />

        <footer class="pal-foot">
          <button v-if="!p.is_active" class="btn btn-sm" type="button" :disabled="!!busy" @click="activate(p)">
            <AppIcon name="check" :size="13" />{{ busy === p.id ? 'Применение…' : 'Сделать активной' }}
          </button>
          <span v-else class="active-note"><AppIcon name="users" :size="13" />Применяется для всех</span>
          <span class="spacer" />
          <button v-if="!p.is_preset" class="btn btn-sm btn-ghost" type="button" @click="edit(p)"><AppIcon name="edit" :size="13" />Изменить</button>
          <button class="btn btn-sm btn-ghost btn-icon" type="button" title="Создать на основе этой палитры" :aria-label="`Создать на основе «${p.name}»`" @click="duplicate(p)">
            <AppIcon name="copy" :size="14" />
          </button>
          <button v-if="!p.is_preset && !p.is_active" class="btn btn-sm btn-ghost btn-icon btn-danger" type="button" title="Удалить" :aria-label="`Удалить «${p.name}»`" @click="remove(p)">
            <AppIcon name="trash" :size="14" />
          </button>
        </footer>
      </article>
    </div>

    <p class="note muted"><AppIcon name="info" :size="14" />Встроенные палитры не изменяются — создайте на их основе свою.</p>

    <PaletteEditor v-if="editor" :palette="editor.palette" :base="editor.base" :name="editor.name" @close="editor = null" @saved="onSaved" />
  </div>
</template>

<style scoped>
.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: var(--sp-4); }
.pal { display: flex; flex-direction: column; gap: 14px; padding: 16px 18px 14px; transition: border-color var(--t), box-shadow var(--t); }
.pal:hover { box-shadow: var(--shadow); }
.pal.active { border-color: color-mix(in srgb, var(--light-green) 55%, var(--border)); box-shadow: 0 0 0 3px color-mix(in srgb, var(--light-green) 14%, transparent); }
.pal-head { display: flex; flex-direction: column; gap: 10px; }
.pal-title { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.pal-title h3 { font-size: var(--fs-md); }
.tags { gap: 6px; }
.strip { display: flex; align-items: center; gap: 3px; }
.strip i { flex: 1; height: 14px; border-radius: 4px; box-shadow: inset 0 0 0 1px rgba(0, 0, 0, .08); }
.strip b { width: 6px; flex: 0 0 6px; }
.pal-foot { display: flex; align-items: center; gap: 4px; padding-top: 12px; border-top: 1px solid var(--border); }
.active-note { display: inline-flex; align-items: center; gap: 6px; font-size: var(--fs-sm); color: var(--muted); }
.note { display: flex; align-items: center; gap: 6px; font-size: var(--fs-sm); }
</style>
