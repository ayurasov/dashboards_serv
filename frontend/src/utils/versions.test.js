import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { parseVersions } from './versions'
import pkg from '../../package.json'

describe('version history (docs/versions.md)', () => {
  it('parses releases, intro and sections', () => {
    const md = ['# Версии', '', '## Версия 0.2.0 (Декабрь 2026 г.)', '', 'Кратко о версии.', '', '### Обзор', '', '- пункт один', '- пункт два', 'абзац', '', '## Версия 0.1.0', '### Старт', '- первый'].join('\n')
    const releases = parseVersions(md)
    expect(releases.map((r) => r.version)).toEqual(['0.2.0 (Декабрь 2026 г.)', '0.1.0'])
    expect(releases[0].intro).toEqual(['Кратко о версии.'])
    expect(releases[0].sections[0]).toEqual({ title: 'Обзор', items: ['пункт один', 'пункт два'], paragraphs: ['абзац'] })
  })
  it('latest entry of docs/versions.md matches package.json version', () => {
    const md = readFileSync(resolve(process.cwd(), '../docs/versions.md'), 'utf8')
    const [latest] = parseVersions(md)
    expect(latest.version.startsWith(pkg.version)).toBe(true)
    expect(latest.sections.length).toBeGreaterThan(0)
  })
})
