import userSource from '@docs/manuals/user-guide.md?raw'
import adminSource from '@docs/manuals/admin-guide.md?raw'
import { renderMarkdown } from '@/utils/markdown'

/**
 * Руководства внутри приложения — те же документы, что в docs/manuals (из них же собираются
 * PDF и DOCX). Иллюстрации — отдельные файлы сборки, загружаются по мере прокрутки.
 */
const images = import.meta.glob('../../../docs/manuals/images/**/*.{png,jpg,jpeg,svg}', { eager: true, query: '?url', import: 'default' })

export function resolveGuideImage(src) {
  return images[`../../../docs/manuals/${src.replace(/^\.\//, '')}`] || null
}

const SOURCES = { user: userSource, admin: adminSource }
const cache = {}

export function guide(kind = 'user') {
  if (!cache[kind]) cache[kind] = renderMarkdown(SOURCES[kind], { resolveImage: resolveGuideImage })
  return cache[kind]
}

// PDF руководств собираются tools/docs/build_manuals.py и попадают в сборку приложения:
// скачивается всегда руководство к работающей версии.
const pdfs = import.meta.glob('../../../docs/manuals/{user,admin}-guide.pdf', { eager: true, query: '?url', import: 'default' })

export const GUIDE_PDF = {
  user: { url: pdfs['../../../docs/manuals/user-guide.pdf'] || null, name: `dashboards-${__APP_VERSION__}-rukovodstvo-polzovatelya.pdf` },
  admin: { url: pdfs['../../../docs/manuals/admin-guide.pdf'] || null, name: `dashboards-${__APP_VERSION__}-rukovodstvo-administratora.pdf` },
}
