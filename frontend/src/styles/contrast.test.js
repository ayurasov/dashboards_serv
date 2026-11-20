import { readFileSync, readdirSync } from 'node:fs'
import { relative } from 'node:path'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

/**
 * Контраст текста по токенам (WCAG 2.1 AA, обычный текст — не ниже 4.5:1): приглушённый текст --muted на всех
 * поверхностях темы и текст значков .badge-* на их подложке поверх поверхностей — в светлой и тёмной теме.
 * Цвета вычисляются из tokens.css и base.css (var(), #hex, rgba(), color-mix in srgb), как в браузере.
 */
const DIR = resolve(process.cwd(), 'src/styles')
const tokensCss = readFileSync(resolve(DIR, 'tokens.css'), 'utf8')
const baseCss = readFileSync(resolve(DIR, 'base.css'), 'utf8')
const AA = 4.5

function block(css, selector) {
  const start = css.indexOf(`${selector} {`)
  if (start < 0) throw new Error(`нет блока ${selector}`)
  const body = css.slice(css.indexOf('{', start) + 1, css.indexOf('\n}', start))
  return Object.fromEntries([...body.replace(/\/\*[\s\S]*?\*\//g, '').matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)].map((m) => [m[1], m[2].trim()]))
}

const ROOT = block(tokensCss, ':root')
const THEMES = {
  light: { ...ROOT, ...block(tokensCss, ":root, [data-theme='light']") },
  dark: { ...ROOT, ...block(tokensCss, ":root, [data-theme='light']"), ...block(tokensCss, "[data-theme='dark']") },
}

/** Аргументы верхнего уровня функции: «a, color-mix(b, c), d» → ['a', 'color-mix(b, c)', 'd']. */
function args(text) {
  const out = []
  let depth = 0
  let current = ''
  for (const ch of text) {
    if (ch === '(') depth++
    if (ch === ')') depth--
    if (ch === ',' && depth === 0) {
      out.push(current.trim())
      current = ''
    } else current += ch
  }
  out.push(current.trim())
  return out
}

/** Цвет CSS → { r, g, b, a } (каналы 0…255). */
function color(expr, vars) {
  const text = expr.trim()
  if (text === 'transparent') return { r: 0, g: 0, b: 0, a: 0 }
  let m = text.match(/^var\((--[\w-]+)\)$/)
  if (m) return color(vars[m[1]], vars)
  m = text.match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i)
  if (m) {
    const hex = m[1].length === 3 ? [...m[1]].map((c) => c + c).join('') : m[1]
    return { r: parseInt(hex.slice(0, 2), 16), g: parseInt(hex.slice(2, 4), 16), b: parseInt(hex.slice(4, 6), 16), a: 1 }
  }
  m = text.match(/^rgba?\((.+)\)$/)
  if (m) {
    const [r, g, b, a = 1] = m[1].split(/[\s,/]+/).filter(Boolean).map(Number)
    return { r, g, b, a }
  }
  m = text.match(/^color-mix\((.+)\)$/)
  if (m) {
    const [space, first, second] = args(m[1])
    if (space !== 'in srgb') throw new Error(`пространство ${space}`)
    const part = (s) => { const p = s.match(/^(.*?)\s+([\d.]+)%$/); return p ? [p[1], Number(p[2]) / 100] : [s, null] }
    const [aText, pa] = part(first)
    const [bText, pb] = part(second)
    const wa = pa ?? 1 - pb
    const wb = pb ?? 1 - wa
    const A = color(aText, vars)
    const B = color(bText, vars)
    // Смешение с учётом прозрачности (premultiplied), как color-mix в браузере
    const alpha = A.a * wa + B.a * wb
    const ch = (k) => (alpha ? (A[k] * A.a * wa + B[k] * B.a * wb) / alpha : 0)
    return { r: ch('r'), g: ch('g'), b: ch('b'), a: alpha }
  }
  throw new Error(`не разобран цвет «${text}»`)
}

const over = (top, bottom) => ({
  r: top.r * top.a + bottom.r * (1 - top.a), g: top.g * top.a + bottom.g * (1 - top.a), b: top.b * top.a + bottom.b * (1 - top.a), a: 1,
})
const lin = (v) => { const c = v / 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4 }
const luminance = (c) => 0.2126 * lin(c.r) + 0.7152 * lin(c.g) + 0.0722 * lin(c.b)
function contrast(fg, bg) {
  const a = luminance(fg) + 0.05
  const b = luminance(bg) + 0.05
  return Math.max(a, b) / Math.min(a, b)
}

const SURFACES = ['--bg', '--bg-elevated', '--surface', '--surface-2', '--surface-3', '--sidebar-bg', '--row-hover']
const BADGE_SURFACES = ['--bg-elevated', '--surface', '--surface-2', '--surface-3', '--row-hover']
const BADGES = Object.fromEntries([...baseCss.matchAll(/\.badge-(\w+)\s*\{\s*background:\s*([^;]+);\s*color:\s*([^;]+);\s*\}/g)]
  .map((m) => [m[1], { background: m[2], color: m[3] }]))

describe.each(Object.keys(THEMES))('контраст, тема %s', (theme) => {
  const vars = THEMES[theme]

  it.each(SURFACES)('приглушённый текст на %s — не ниже 4.5:1', (surface) => {
    expect(contrast(color('var(--muted)', vars), color(`var(${surface})`, vars))).toBeGreaterThanOrEqual(AA)
  })

  it('значки описаны все: зелёный, жёлтый, красный, синий, серый, фирменный', () => {
    expect(Object.keys(BADGES).sort()).toEqual(['blue', 'brand', 'gray', 'green', 'red', 'yellow'])
  })

  it.each(Object.keys(BADGES))('текст значка %s на его подложке — не ниже 4.5:1', (name) => {
    const badge = BADGES[name]
    const fg = color(badge.color, vars)
    for (const surface of BADGE_SURFACES) {
      const bg = over(color(badge.background, vars), color(`var(${surface})`, vars))
      expect(contrast(over(fg, bg), bg), `${name} на ${surface}`).toBeGreaterThanOrEqual(AA)
    }
  })

  it.each(['delta-good', 'delta-bad'])('текст %s на поверхностях — не ниже 4.5:1', (name) => {
    const rule = baseCss.match(new RegExp(`\\.${name}\\s*\\{\\s*color:\\s*([^;]+);`))
    expect(rule, name).not.toBeNull()
    for (const surface of SURFACES) {
      expect(contrast(color(rule[1], vars), color(`var(${surface})`, vars)), `${name} на ${surface}`).toBeGreaterThanOrEqual(AA)
    }
  })

  it('оттенок статуса сохраняется: зелёный — зелёный, жёлтый — жёлтый, красный — красный', () => {
    const hue = ({ r, g, b }) => {
      const max = Math.max(r, g, b)
      const min = Math.min(r, g, b)
      const d = max - min
      const h = max === r ? ((g - b) / d) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4
      return (h * 60 + 360) % 360
    }
    expect(hue(color('var(--on-green)', vars))).toBeCloseTo(hue(color('var(--light-green)', vars)), 0)
    expect(hue(color('var(--on-yellow)', vars))).toBeCloseTo(hue(color('var(--light-yellow)', vars)), 0)
    expect(hue(color('var(--on-red)', vars))).toBeCloseTo(hue(color('var(--light-red)', vars)), 0)
  })
})

describe('вычисление цвета', () => {
  it('color-mix с прозрачным — прозрачность, а не потемнение', () => {
    const mixed = color('color-mix(in srgb, #3f9f6b 14%, transparent)', {})
    expect(mixed.a).toBeCloseTo(0.14, 5)
    expect([mixed.r, mixed.g, mixed.b].map(Math.round)).toEqual([63, 159, 107])
    expect(contrast({ r: 0, g: 0, b: 0 }, { r: 255, g: 255, b: 255 })).toBeCloseTo(21, 5)
  })
})

describe('цвет var(--faint) — только декоративные элементы', () => {
  // --faint ниже 4.5:1 (WCAG AA): смысловой текст — всегда --muted (см. tokens.css).
  // Тест следит, чтобы var(--faint) в color: не появлялся вне этого списка декоративных
  // мест (стрелки, разделители, hover-рамки, плейсхолдеры, отключённые кнопки).
  const allowed = new Set([
  'components/admin/AccessEditor.vue: .link-btn:disabled { color: var(--faint); cursor: not-allowed; }',
  'components/admin/AuditDiff.vue: .arrow { width: 28px; padding-left: 0 !important; padding-right: 0 !important; color: var(--faint); }',
  'components/admin/DimensionControl.vue: .cls:hover:not(.locked) { border-color: var(--faint); color: var(--text); }',
  'components/admin/UnitPicker.vue: .control:hover:not(:disabled) { border-color: var(--faint); }',
  'components/admin/UserDrawer.vue: .ev-chev { color: var(--faint); transition: transform var(--t-fast); }',
  'components/integrations/KindPicker.vue: .chev { flex: 0 0 auto; margin-top: 12px; color: var(--faint); }',
  'components/integrations/ScheduleEditor.vue: .day:hover { border-color: var(--faint); color: var(--text); }',
  'components/layout/AppSidebar.vue: .chev { color: var(--faint); transition: transform var(--t); transform: rotate(-90deg); }',
  'components/layout/AppTopbar.vue: .sep { color: var(--faint); }',
  'components/org/OrgGroupCard.vue: .group-card:hover { border-color: var(--faint); background: var(--surface); }',
  'components/org/OrgPersonPanel.vue: .p-crumbs :deep(svg) { color: var(--faint); margin-right: 2px; }',
  'components/org/OrgPicker.vue: .picker-field:hover:not(:disabled) { border-color: var(--faint); }',
  'components/org/OrgSearch.vue: .box:hover { border-color: var(--faint); }',
  'components/org/OrgTreeView.vue: .sep { margin: 0 5px; color: var(--faint); }',
  'components/reports/ReasonList.vue: .r-go { flex: 0 0 auto; margin-top: 3px; color: var(--faint); transition: color var(--t-fast), transform var(--t-fast); }',
  'components/reports/ReportUnitPanel.vue: .crumbs .sep { color: var(--faint); }',
  'components/reports/ReportUnitPanel.vue: .k-lock, .k-go { color: var(--faint); }',
  'components/tp/TpRegWeekDialog.vue: .affix:hover { border-color: var(--faint); }',
  'views/InboxView.vue: .gap { min-width: 20px; text-align: center; color: var(--faint); }',
  'views/admin/AccessProfiles.vue: .p-foot .btn-danger:disabled { color: var(--faint); opacity: .45; }',
  'views/admin/AdminAudit.vue: .chev { color: var(--faint); transition: transform var(--t-fast), color var(--t-fast); }',
  'views/admin/AdminAudit.vue: .gap { min-width: 20px; text-align: center; color: var(--faint); }',
  'views/admin/AdminSystem.vue: .c-go { color: var(--faint); }',
  'views/admin/AdminUsers.vue: .dot { color: var(--faint); }',
  'views/product/PartnershipsDashboard.vue: .legend-item .go { color: var(--faint); opacity: 0; transition: opacity var(--t-fast); }',
  'views/product/PartnershipsRegistry.vue: .meta-icon { color: var(--faint); margin-top: 3px; }',
  'views/product/PartnershipsTimeline.vue: .sep { color: var(--faint); margin: 0 1px; }',
  'views/reports/ReportsEntry.vue: .cm { width: 30px; height: 32px; display: grid; place-items: center; padding: 0; border: 1px solid transparent; border-radius: 8px; background: transparent; color: var(--faint); cursor: pointer; }',
  'views/reports/ReportsEntry.vue: .in::placeholder { color: var(--faint); font-weight: 400; }',
  ])
  const src = resolve(process.cwd(), 'src')
  const files = []
  const walk = (dir) => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      if (entry.isDirectory()) walk(resolve(dir, entry.name))
      else if (entry.name.endsWith('.vue')) files.push(resolve(dir, entry.name))
    }
  }
  walk(src)
  const found = []
  for (const file of files) {
    for (const line of readFileSync(file, 'utf8').split('\n')) {
      if (line.includes('color: var(--faint)')) {
        found.push(`${relative(src, file).replaceAll('\\', '/')}: ${line.trim().replace(/\s+/g, ' ')}`)
      }
    }
  }
  it('все использования color: var(--faint) — в списке декоративных', () => {
    const unexpected = found.filter((f) => !allowed.has(f))
    expect(unexpected, `смысловой текст не должен использовать --faint (ниже AA):\n${unexpected.join('\n')}`).toEqual([])
  })
  it('список декоративных мест актуален: каждый пункт существует в коде', () => {
    expect(found.filter((f) => allowed.has(f)).length, 'устаревшие пункты списка удалите').toBe(allowed.size)
  })
})
