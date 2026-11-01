<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppIcon from '@/components/ui/AppIcon.vue'
import { GUIDE_PDF, guide } from '@/docs/guides'

/**
 * Руководство внутри приложения: тот же документ, что в PDF и DOCX (docs/manuals), с оглавлением,
 * поиском по тексту разделов и переходом по якорям (ссылка «?» в верхней панели ведёт сюда).
 */
const route = useRoute()
const router = useRouter()
const kind = computed(() => route.meta.guideKind || 'user')
const doc = computed(() => guide(kind.value))
const pdf = computed(() => GUIDE_PDF[kind.value])
const articleEl = ref(null)
const query = ref('')
const activeId = ref('')
const zoomed = ref(null)
const sectionText = ref({})

const tocHeadings = computed(() => doc.value.headings.filter((h) => h.level <= 2))
const tocItems = computed(() => {
  const needle = query.value.trim().toLowerCase()
  if (!needle) return tocHeadings.value
  return doc.value.headings.filter((h) => h.level <= 3 && (h.text.toLowerCase().includes(needle) || (sectionText.value[h.id] || '').includes(needle)))
})
const subtitle = computed(() => [doc.value.meta.subtitle, doc.value.meta.date].filter(Boolean).join(' · '))

function headingElements() {
  return [...(articleEl.value?.querySelectorAll('h1, h2, h3, h4') || [])]
}
function collectSectionText() {
  const texts = {}
  for (const heading of headingElements()) {
    let text = ''
    for (let node = heading.nextElementSibling; node && !/^H[1-4]$/.test(node.tagName); node = node.nextElementSibling) text += ` ${node.textContent}`
    texts[heading.id] = text.toLowerCase()
  }
  sectionText.value = texts
}
function go(id) {
  const target = document.getElementById(id)
  if (!target) return
  target.scrollIntoView({ block: 'start', behavior: 'smooth' })
  activeId.value = id
  if (route.hash !== `#${id}`) router.replace({ hash: `#${id}` })
}
function onArticleClick(event) {
  const link = event.target.closest('a[href^="#"]')
  if (link) { event.preventDefault(); go(decodeURIComponent(link.getAttribute('href').slice(1))); return }
  const image = event.target.closest('figure img')
  if (image) zoomed.value = { src: image.getAttribute('src'), alt: image.getAttribute('alt') }
}
function onKey(event) {
  if (event.key === 'Escape') zoomed.value = null
}

let observer = null
onMounted(async () => {
  await nextTick()
  collectSectionText()
  activeId.value = doc.value.headings[0]?.id || ''
  if (route.hash) setTimeout(() => go(decodeURIComponent(route.hash.slice(1))), 50)
  window.addEventListener('keydown', onKey)
  if (typeof IntersectionObserver === 'undefined') return
  observer = new IntersectionObserver((entries) => {
    const visible = entries.filter((e) => e.isIntersecting).map((e) => e.target.id)
    if (visible.length) activeId.value = visible[0]
  }, { rootMargin: '0px 0px -70% 0px' })
  for (const h of headingElements()) observer.observe(h)
})
onBeforeUnmount(() => {
  observer?.disconnect()
  window.removeEventListener('keydown', onKey)
})

const activeTocId = computed(() => {
  const index = doc.value.headings.findIndex((h) => h.id === activeId.value)
  for (let i = index; i >= 0; i--) if (doc.value.headings[i].level <= 2) return doc.value.headings[i].id
  return ''
})
</script>

<template>
  <div class="guide">
    <header class="g-head">
      <span class="mark"><AppIcon :name="kind === 'admin' ? 'shield' : 'book'" :size="20" /></span>
      <div class="titles">
        <h1>{{ kind === 'admin' ? 'Руководство администратора' : 'Руководство пользователя' }}</h1>
        <p v-if="subtitle">{{ subtitle }}</p>
      </div>
      <div class="spacer" />
      <template v-if="pdf.url">
        <a class="btn btn-sm" :href="pdf.url" target="_blank" rel="noopener"><AppIcon name="external" :size="13" />Открыть PDF</a>
        <a class="btn btn-sm btn-primary" :href="pdf.url" :download="pdf.name"><AppIcon name="download" :size="13" />Скачать PDF</a>
      </template>
    </header>

    <div class="layout">
      <nav class="toc card scroll-thin" aria-label="Содержание">
        <label class="search"><AppIcon name="search" :size="14" /><input v-model="query" type="search" placeholder="Найти в руководстве" /></label>
        <p v-if="query && !tocItems.length" class="muted none">Ничего не найдено</p>
        <ul>
          <li v-for="h in tocItems" :key="h.id" :class="[`lvl-${h.level}`, { active: !query && h.id === activeTocId }]">
            <a :href="`#${h.id}`" @click.prevent="go(h.id)">{{ h.text }}</a>
          </li>
        </ul>
      </nav>
      <article ref="articleEl" class="content card" @click="onArticleClick" v-html="doc.html" />
    </div>

    <div v-if="zoomed" class="zoom" role="dialog" aria-modal="true" @click="zoomed = null">
      <img :src="zoomed.src" :alt="zoomed.alt" />
      <p>{{ zoomed.alt }}</p>
    </div>
  </div>
</template>

<style scoped>
.guide { max-width: 1240px; margin: 0 auto; }
.g-head { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 18px; }
.mark { width: 42px; height: 42px; display: grid; place-items: center; border-radius: 12px; background: var(--brand-soft); color: var(--brand); }
.titles h1 { font-size: var(--fs-xl); }
.titles p { font-size: var(--fs-sm); color: var(--muted); }
.layout { display: grid; grid-template-columns: 270px minmax(0, 1fr); gap: 24px; align-items: start; }
.toc { position: sticky; top: calc(var(--topbar-h) + 16px); max-height: calc(100vh - var(--topbar-h) - 40px); overflow-y: auto; padding: 12px; }
.search { display: flex; align-items: center; gap: 8px; padding: 0 10px; height: 34px; border: 1px solid var(--border-strong); border-radius: 9px; color: var(--muted); margin-bottom: 10px; }
.search input { border: 0; outline: 0; background: transparent; width: 100%; font-size: var(--fs-sm); color: var(--text); }
.search:focus-within { border-color: var(--accent); }
.none { padding: 6px 8px; font-size: var(--fs-sm); }
.toc ul { list-style: none; margin: 0; padding: 0; }
.toc a { display: block; padding: 5px 9px; border-radius: 7px; color: var(--text-2); font-size: var(--fs-sm); line-height: 1.35; }
.toc a:hover { background: var(--surface-3); color: var(--text); }
.toc .lvl-1 { margin-top: 6px; }
.toc .lvl-1 a { font-weight: 600; color: var(--text); }
.toc .lvl-2 a { padding-left: 20px; }
.toc .lvl-3 a { padding-left: 30px; font-size: var(--fs-xs); }
.toc li.active a { background: var(--brand-soft); color: var(--brand); }
.content { padding: 10px 40px 40px; font-size: 14.5px; line-height: 1.65; color: var(--text-2); }
.content :deep(h1) { font-size: 22px; margin: 36px 0 12px; padding-top: 24px; border-top: 1px solid var(--border); scroll-margin-top: calc(var(--topbar-h) + 16px); color: var(--text); }
.content :deep(h1:first-child) { border-top: 0; padding-top: 0; margin-top: 24px; }
.content :deep(h2) { font-size: 17.5px; margin: 28px 0 10px; scroll-margin-top: calc(var(--topbar-h) + 16px); color: var(--text); }
.content :deep(h3) { font-size: 15px; margin: 22px 0 8px; scroll-margin-top: calc(var(--topbar-h) + 16px); color: var(--text); }
.content :deep(p) { margin: 0 0 11px; }
.content :deep(ul), .content :deep(ol) { margin: 0 0 13px; padding-left: 22px; }
.content :deep(li) { margin: 4px 0; }
.content :deep(strong) { color: var(--text); }
.content :deep(code) { background: var(--surface-3); border-radius: 5px; padding: 1px 6px; font-size: 13px; font-family: var(--font-mono); }
.content :deep(a) { color: var(--accent); }
.content :deep(blockquote) { margin: 14px 0; padding: 10px 16px; border-left: 3px solid var(--brand); background: var(--surface-2); border-radius: 0 10px 10px 0; }
.content :deep(blockquote p:last-child) { margin-bottom: 0; }
.content :deep(.md-table) { overflow-x: auto; margin: 0 0 16px; }
.content :deep(table) { border-collapse: collapse; width: 100%; font-size: 13.5px; }
.content :deep(th), .content :deep(td) { border: 1px solid var(--border); padding: 7px 11px; text-align: left; vertical-align: top; }
.content :deep(th) { background: var(--surface-2); color: var(--text); font-weight: 600; }
.content :deep(figure) { margin: 18px 0 22px; text-align: center; }
.content :deep(figure img) { max-width: 100%; height: auto; border: 1px solid var(--border); border-radius: 12px; box-shadow: var(--shadow); cursor: zoom-in; display: inline-block; }
.content :deep(figcaption) { margin-top: 8px; font-size: var(--fs-sm); color: var(--muted); }
.zoom { position: fixed; inset: 0; z-index: 400; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; padding: 24px; background: rgba(10, 12, 18, .85); cursor: zoom-out; }
.zoom img { max-width: 96vw; max-height: 86vh; border-radius: 10px; }
.zoom p { color: #e8eaef; font-size: var(--fs-sm); }
@media (max-width: 960px) { .layout { grid-template-columns: 1fr; } .toc { position: static; max-height: 260px; } .content { padding: 6px 18px 24px; } }
</style>
