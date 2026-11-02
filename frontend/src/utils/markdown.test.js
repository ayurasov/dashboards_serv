import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { escapeHtml, renderInline, renderMarkdown, slugify } from './markdown'

describe('markdown for the in-app user guide', () => {
  it('escapes text and keeps only safe links', () => {
    expect(escapeHtml('<b>&"')).toBe('&lt;b&gt;&amp;&quot;')
    expect(renderInline('**Кнопка** и *курсив*, `<code>`')).toBe('<strong>Кнопка</strong> и <em>курсив</em>, <code>&lt;code&gt;</code>')
    expect(renderInline('[раздел](#vkhod-v-sistemu)')).toBe('<a href="#vkhod-v-sistemu">раздел</a>')
    expect(renderInline('[сайт](https://example.ru)')).toContain('target="_blank" rel="noopener noreferrer"')
    expect(renderInline('[опасно](javascript:void)')).toBe('опасно')
  })

  it('builds headings with unique anchors, tables, lists, quotes and figures', () => {
    const source = [
      '---', 'title: "Дашборды — руководство"', 'subtitle: "Версия 0.1.0"', '---', '',
      '# Вход в систему', 'Откройте **адрес** системы.', 'Вторая строка абзаца.', '',
      '## Вход в систему', '',
      '| Понятие | Что это |', '| --- | --- |', '| Задача | Единица работы |', '',
      '1. Первый', '2. Второй', '', '- пункт', '- ещё', '',
      '> **Совет.** Полезно.', '',
      '![Экран входа](images/user/01-login.png)',
    ].join('\n')
    const { html, headings, meta } = renderMarkdown(source, { resolveImage: (src) => `/assets/${src.split('/').pop()}` })
    expect(meta).toEqual({ title: 'Дашборды — руководство', subtitle: 'Версия 0.1.0' })
    expect(headings).toEqual([
      { level: 1, text: 'Вход в систему', id: 'вход-в-систему' },
      { level: 2, text: 'Вход в систему', id: 'вход-в-систему-2' },
    ])
    expect(html).toContain('<p>Откройте <strong>адрес</strong> системы. Вторая строка абзаца.</p>')
    expect(html).toContain('<thead><tr><th>Понятие</th><th>Что это</th></tr></thead><tbody><tr><td>Задача</td><td>Единица работы</td></tr></tbody>')
    expect(html).toContain('<ol><li>Первый</li><li>Второй</li></ol>')
    expect(html).toContain('<ul><li>пункт</li><li>ещё</li></ul>')
    expect(html).toContain('<blockquote><p><strong>Совет.</strong> Полезно.</p></blockquote>')
    expect(html).toContain('<figure><img src="/assets/01-login.png" alt="Экран входа" loading="lazy"><figcaption>Экран входа</figcaption></figure>')
    expect(slugify('«Мои задачи»')).toBe('мои-задачи')
  })

  it('renders the whole user guide with every screenshot resolved', () => {
    const source = readFileSync(resolve(process.cwd(), '../docs/manuals/user-guide.md'), 'utf8')
    const missing = []
    const { html, headings, meta } = renderMarkdown(source, {
      resolveImage: (src) => { if (!src.startsWith('images/user/')) missing.push(src); return src },
    })
    expect(meta.title).toContain('руководство пользователя')
    expect(headings.filter((h) => h.level === 1).length).toBeGreaterThan(5)
    expect(new Set(headings.map((h) => h.id)).size).toBe(headings.length)
    expect(missing).toEqual([])
    expect(html).not.toMatch(/<script|javascript:/i)
  })

  it('renders fenced code blocks as is, also inside list items', () => {
    const source = [
      '1. Отправьте файл:', '', '   ```bash', '   curl -X POST "/api/inbound/v1/files" \\', '     -F "file=@a.csv"', '   ```', '',
      '```json', '[{"indicator": "jira.resolved", "jql": "a < \\"{month_start}\\""}]', '# не заголовок', '```', '',
      'Абзац после кода.',
    ].join('\n')
    const { html, headings } = renderMarkdown(source)
    expect(headings).toEqual([])
    expect(html).toContain('<pre class="md-code" data-lang="bash"><code>curl -X POST &quot;/api/inbound/v1/files&quot; \\\n  -F &quot;file=@a.csv&quot;</code></pre>')
    expect(html).toContain('<pre class="md-code" data-lang="json"><code>[{&quot;indicator&quot;: &quot;jira.resolved&quot;, &quot;jql&quot;: &quot;a &lt; \\&quot;{month_start}\\&quot;&quot;}]\n# не заголовок</code></pre>')
    expect(html).toContain('<p>Абзац после кода.</p>')
  })

  it('renders the whole admin guide with every screenshot resolved', () => {
    const source = readFileSync(resolve(process.cwd(), '../docs/manuals/admin-guide.md'), 'utf8')
    const missing = []
    const { html, headings, meta } = renderMarkdown(source, {
      resolveImage: (src) => { if (!src.startsWith('images/admin/')) missing.push(src); return src },
    })
    expect(meta.title).toContain('руководство администратора')
    expect(new Set(headings.map((h) => h.id)).size).toBe(headings.length)
    expect(missing).toEqual([])
    expect(html).not.toMatch(/<script|javascript:/i)
    // Строки «# …» внутри примеров кода — не заголовки
    expect(headings.some((h) => h.text.startsWith('Маркетинговые проекты'))).toBe(false)
  })

  it('every «?» help anchor of the router exists in its guide', () => {
    const routes = readFileSync(resolve(process.cwd(), 'src/router/index.js'), 'utf8')
    const ids = {
      user: new Set(renderMarkdown(readFileSync(resolve(process.cwd(), '../docs/manuals/user-guide.md'), 'utf8')).headings.map((h) => h.id)),
      admin: new Set(renderMarkdown(readFileSync(resolve(process.cwd(), '../docs/manuals/admin-guide.md'), 'utf8')).headings.map((h) => h.id)),
    }
    const anchors = routes.split('\n').filter((line) => /guide: '/.test(line) && /path: '/.test(line)).map((line) => ({
      path: line.match(/path: '([^']+)'/)[1],
      id: line.match(/guide: '([^']+)'/)[1],
      kind: /guideKind: 'admin'/.test(line) && !/path: '\/guide/.test(line) ? 'admin' : 'user',
    }))
    expect(anchors.length).toBeGreaterThan(20)
    expect(anchors).toContainEqual({ path: '/inbox', id: 'входящие-данные', kind: 'user' })
    expect(anchors).toContainEqual({ path: '/admin/integrations', id: 'интеграции', kind: 'admin' })
    expect(anchors.filter((a) => !ids[a.kind].has(a.id))).toEqual([])
  })
})
