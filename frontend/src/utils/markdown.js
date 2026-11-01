/**
 * Небольшой разборщик Markdown для руководства пользователя внутри приложения.
 *
 * Поддерживает то, что используют руководства: титульный блок YAML, заголовки, абзацы,
 * маркированные и нумерованные списки, таблицы, цитаты, рисунки, жирный текст, курсив,
 * код и ссылки. Текст экранируется; ссылки — только http(s), mailto и якоря внутри документа.
 */
const ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }

export function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, (char) => ESCAPES[char])
}

export function slugify(text) {
  return String(text)
    .toLowerCase()
    .replace(/[«»"'`*_]/g, '')
    .replace(/[^\p{L}\p{N}]+/gu, '-')
    .replace(/^-+|-+$/g, '') || 'section'
}

function safeHref(href) {
  if (/^#[\p{L}\p{N}_-]*$/u.test(href)) return href
  if (/^(https?:|mailto:)/i.test(href)) return href
  return null
}

const INLINE = /`([^`]+)`|!\[([^\]]*)\]\(([^)\s]+)\)|\[([^\]]+)\]\(([^)\s]+)\)|\*\*(.+?)\*\*|\*([^*\s](?:[^*]*[^*\s])?)\*/g

export function renderInline(text, options = {}) {
  let html = ''
  let last = 0
  for (const match of text.matchAll(INLINE)) {
    html += escapeHtml(text.slice(last, match.index))
    last = match.index + match[0].length
    const [, code, alt, src, label, href, bold, italic] = match
    if (code !== undefined) html += `<code>${escapeHtml(code)}</code>`
    else if (src !== undefined) {
      const url = options.resolveImage ? options.resolveImage(src) : src
      html += url ? `<img src="${escapeHtml(url)}" alt="${escapeHtml(alt)}" loading="lazy">` : escapeHtml(alt)
    } else if (href !== undefined) {
      const safe = safeHref(href)
      const inner = renderInline(label, options)
      if (!safe) html += inner
      else if (safe.startsWith('#')) html += `<a href="${escapeHtml(safe)}">${inner}</a>`
      else html += `<a href="${escapeHtml(safe)}" target="_blank" rel="noopener noreferrer">${inner}</a>`
    } else if (bold !== undefined) html += `<strong>${renderInline(bold, options)}</strong>`
    else html += `<em>${renderInline(italic, options)}</em>`
  }
  return html + escapeHtml(text.slice(last))
}

function frontMatter(lines) {
  const meta = {}
  if (lines[0]?.trim() !== '---') return { meta, start: 0 }
  const end = lines.findIndex((line, index) => index > 0 && line.trim() === '---')
  if (end === -1) return { meta, start: 0 }
  for (const line of lines.slice(1, end)) {
    const match = line.match(/^([\w-]+):\s*"?(.*?)"?\s*$/)
    if (match) meta[match[1]] = match[2]
  }
  return { meta, start: end + 1 }
}

function splitRow(line) {
  return line.trim().replace(/^\|/, '').replace(/\|$/, '').split(/(?<!\\)\|/).map((cell) => cell.trim().replace(/\\\|/g, '|'))
}

const TABLE_SEPARATOR = /^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$/
const BULLET = /^[-*+]\s+(.*)$/
const ORDERED = /^(\d+)[.)]\s+(.*)$/
const FIGURE = /^!\[([^\]]*)\]\(([^)\s]+)\)\s*$/

/**
 * Возвращает { html, headings, meta }: headings — заголовки с уровнем и якорем для оглавления,
 * meta — поля титульного блока (title, subtitle, date).
 */
export function renderMarkdown(source, options = {}) {
  const lines = String(source).replace(/\r\n?/g, '\n').split('\n')
  const { meta, start } = frontMatter(lines)
  const headings = []
  const usedIds = new Map()
  const out = []
  let paragraph = []

  const flush = () => {
    if (paragraph.length) out.push(`<p>${renderInline(paragraph.join(' '), options)}</p>`)
    paragraph = []
  }
  const uniqueId = (text) => {
    const base = slugify(text)
    const seen = usedIds.get(base) || 0
    usedIds.set(base, seen + 1)
    return seen ? `${base}-${seen + 1}` : base
  }

  for (let i = start; i < lines.length; i++) {
    const line = lines[i]
    const trimmed = line.trim()
    if (!trimmed) { flush(); continue }

    const heading = trimmed.match(/^(#{1,6})\s+(.+?)\s*#*$/)
    if (heading) {
      flush()
      const level = heading[1].length
      const text = heading[2]
      const id = uniqueId(text)
      headings.push({ level, text: text.replace(/\*\*|`/g, ''), id })
      out.push(`<h${level} id="${escapeHtml(id)}">${renderInline(text, options)}</h${level}>`)
      continue
    }

    if (/^(-{3,}|\*{3,}|_{3,})$/.test(trimmed)) { flush(); out.push('<hr>'); continue }

    const figure = trimmed.match(FIGURE)
    if (figure) {
      flush()
      const url = options.resolveImage ? options.resolveImage(figure[2]) : figure[2]
      if (url) {
        out.push(`<figure><img src="${escapeHtml(url)}" alt="${escapeHtml(figure[1])}" loading="lazy">${figure[1] ? `<figcaption>${renderInline(figure[1], options)}</figcaption>` : ''}</figure>`)
      }
      continue
    }

    if (trimmed.startsWith('|') && TABLE_SEPARATOR.test(lines[i + 1]?.trim() || '')) {
      flush()
      const header = splitRow(trimmed)
      const rows = []
      i += 2
      while (i < lines.length && lines[i].trim().startsWith('|')) rows.push(splitRow(lines[i++]))
      i -= 1
      const head = header.map((cell) => `<th>${renderInline(cell, options)}</th>`).join('')
      const body = rows.map((row) => `<tr>${header.map((_, index) => `<td>${renderInline(row[index] || '', options)}</td>`).join('')}</tr>`).join('')
      out.push(`<div class="md-table"><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`)
      continue
    }

    if (trimmed.startsWith('>')) {
      flush()
      const quoted = []
      while (i < lines.length && lines[i].trim().startsWith('>')) quoted.push(lines[i++].trim().replace(/^>\s?/, ''))
      i -= 1
      out.push(`<blockquote>${renderMarkdown(quoted.join('\n'), options).html}</blockquote>`)
      continue
    }

    const bullet = trimmed.match(BULLET)
    const ordered = trimmed.match(ORDERED)
    if (bullet || ordered) {
      flush()
      const pattern = bullet ? BULLET : ORDERED
      const items = []
      while (i < lines.length) {
        const current = lines[i].trim()
        const item = current.match(pattern)
        if (item) items.push(bullet ? item[1] : item[2])
        else if (current && /^\s{2,}\S/.test(lines[i]) && items.length) items[items.length - 1] += ` ${current}`
        else break
        i++
      }
      i -= 1
      const tag = bullet ? 'ul' : 'ol'
      const startAttr = ordered && ordered[1] !== '1' ? ` start="${Number(ordered[1])}"` : ''
      out.push(`<${tag}${startAttr}>${items.map((item) => `<li>${renderInline(item, options)}</li>`).join('')}</${tag}>`)
      continue
    }

    paragraph.push(trimmed)
  }
  flush()
  return { html: out.join('\n'), headings, meta }
}
