/** Разбор docs/versions.md: «## Версия …», вводный абзац, «### Раздел», пункты списка. */
export function parseVersions(markdown) {
  const releases = []
  let release = null
  let section = null
  for (const raw of markdown.split(/\r?\n/)) {
    const line = raw.trim()
    const head = line.match(/^## Версия\s+(.+)$/)
    const sub = line.match(/^###\s+(.+)$/)
    if (head) {
      release = { version: head[1].trim(), intro: [], sections: [] }
      releases.push(release)
      section = null
    } else if (!release || !line || line.startsWith('# ')) {
      continue
    } else if (sub) {
      section = { title: sub[1].trim(), items: [], paragraphs: [] }
      release.sections.push(section)
    } else if (!section) {
      release.intro.push(line)
    } else if (line.startsWith('- ')) {
      section.items.push(line.slice(2))
    } else {
      section.paragraphs.push(line)
    }
  }
  return releases
}
