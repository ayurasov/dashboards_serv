<script setup>
import { computed, ref } from 'vue'
import versionsMarkdown from '@docs/versions.md?raw'
import AppModal from '@/components/ui/AppModal.vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import { renderInline } from '@/utils/markdown'
import { parseVersions } from '@/utils/versions'

/** История версий простым языком — docs/versions.md («## Версия …», «### Раздел», пункты). */
const emit = defineEmits(['close'])

const releases = computed(() => parseVersions(versionsMarkdown))
const expanded = ref(new Set(releases.value.length ? [releases.value[0].version] : []))

function toggle(version) {
  const next = new Set(expanded.value)
  next.has(version) ? next.delete(version) : next.add(version)
  expanded.value = next
}
</script>

<template>
  <AppModal title="Что нового" subtitle="Изменения «Дашбордов компании» по версиям" :width="720" @close="emit('close')">
    <div class="releases">
      <article v-for="(r, i) in releases" :key="r.version" class="release" :class="{ open: expanded.has(r.version), latest: i === 0 }">
        <button class="toggle" type="button" @click="toggle(r.version)">
          <span class="mark">{{ i === 0 ? 'NEW' : 'v' }}</span>
          <span class="copy">
            <strong>Версия {{ r.version }}</strong>
            <small v-if="r.intro.length">{{ r.intro[0] }}</small>
          </span>
          <AppIcon :name="expanded.has(r.version) ? 'chevron-up' : 'chevron-down'" :size="16" />
        </button>
        <div v-if="expanded.has(r.version)" class="content">
          <p v-for="p in r.intro.slice(1)" :key="p" v-html="renderInline(p)" />
          <section v-for="s in r.sections" :key="s.title">
            <h3>{{ s.title }}</h3>
            <p v-for="p in s.paragraphs" :key="p" v-html="renderInline(p)" />
            <ul v-if="s.items.length"><li v-for="item in s.items" :key="item" v-html="renderInline(item)" /></ul>
          </section>
        </div>
      </article>
    </div>
  </AppModal>
</template>

<style scoped>
.releases { display: flex; flex-direction: column; gap: 10px; }
.release { border: 1px solid var(--border); border-radius: 12px; overflow: hidden; }
.release.latest { border-color: color-mix(in srgb, var(--brand) 35%, var(--border)); }
.toggle { width: 100%; display: flex; align-items: flex-start; gap: 12px; padding: 14px 16px; border: 0; background: transparent; text-align: left; cursor: pointer; color: var(--text); }
.toggle:hover { background: var(--surface-2); }
.mark { flex: 0 0 auto; width: 36px; height: 22px; display: grid; place-items: center; border-radius: 6px; background: var(--surface-3); color: var(--text-2); font-size: 9.5px; font-weight: 750; letter-spacing: .05em; }
.latest .mark { background: var(--brand); color: #fff; }
.copy { flex: 1; display: flex; flex-direction: column; gap: 3px; }
.copy small { color: var(--muted); font-size: var(--fs-sm); line-height: 1.4; }
.content { padding: 0 18px 16px 64px; font-size: var(--fs-base); color: var(--text-2); }
.content h3 { margin: 14px 0 6px; font-size: var(--fs-base); color: var(--text); }
.content ul { margin: 0; padding-left: 18px; }
.content li { margin: 4px 0; }
.content p { margin: 6px 0; }
</style>
