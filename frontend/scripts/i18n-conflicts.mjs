#!/usr/bin/env node
/**
 * Lists Chinese keys that two English dictionaries (src/i18n/en/*.ts) translate differently (docs/i18n.md).
 * The dictionaries are merged into one map, so only one of the translations would be shown everywhere.
 * Fix by agreeing on one English, or by giving one place its own key with tc('<context>', '中文').
 *   node scripts/i18n-conflicts.mjs        exit code 1 when there is a conflict
 */
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', 'src', 'i18n', 'en')
const unescape = (s) => s.replace(/\\(['"\\])/g, '$1').replace(/\\n/g, '\n')
// 'key': 'value'  or  'key':\n    'value'  (values may be split with +; only the first piece is compared)
const ENTRY = /^\s*(['"])((?:\\.|(?!\1).)*)\1\s*:\s*\n?\s*(['"])((?:\\.|(?!\3).)*)\3/gm

export function conflicts() {
  const seen = new Map()
  for (const f of fs.readdirSync(DIR).filter((f) => f.endsWith('.ts')).sort()) {
    const src = fs.readFileSync(path.join(DIR, f), 'utf8')
    let m
    while ((m = ENTRY.exec(src))) {
      const k = unescape(m[2])
      const v = unescape(m[4])
      const list = seen.get(k) ?? []
      list.push({ file: f, value: v })
      seen.set(k, list)
    }
  }
  return [...seen.entries()].filter(([, l]) => new Set(l.map((x) => x.value)).size > 1)
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const c = conflicts()
  for (const [k, l] of c) console.log(`${k}\n${l.map((x) => `    ${x.file.padEnd(14)} ${x.value}`).join('\n')}`)
  console.log(c.length ? `\n${c.length} conflicting key(s)` : 'no conflicts')
  process.exit(c.length ? 1 : 0)
}
