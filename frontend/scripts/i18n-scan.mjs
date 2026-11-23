#!/usr/bin/env node
/**
 * Finds interface text that the English mode would leave in Chinese (docs/i18n.md).
 *
 *   node scripts/i18n-scan.mjs                 # every source file under src/
 *   node scripts/i18n-scan.mjs src/views/PlanView.vue src/components/route
 *
 * Reports, per file:
 *   untranslated  Chinese text outside t('…') / tb('…') (template text, attributes, string literals)
 *   missing       t('…') keys with no English entry in src/i18n/en/*.ts
 *   dynamic       t(`…${x}…`) — keys must be fixed strings; use t('… {x} …', { x })
 * Comments are ignored, and so is any line containing "i18n-ignore" (or a whole file containing "i18n-ignore-file").
 * Exit code 1 when anything is reported.
 */
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const SRC = path.join(ROOT, 'src')
const CJK = /[㐀-鿿豈-﫿]/

function walkFiles(p, out = []) {
  const st = fs.statSync(p)
  if (st.isDirectory()) {
    for (const f of fs.readdirSync(p)) {
      if (f === '__tests__' || f === 'i18n' || f === 'node_modules') continue
      walkFiles(path.join(p, f), out)
    }
  } else if (/\.(vue|ts)$/.test(p) && !/\.spec\.ts$/.test(p) && !/\.d\.ts$/.test(p)) {
    out.push(p)
  }
  return out
}

/** Blanks out comments (keeping line breaks so line numbers stay right). */
function stripComments(src) {
  const keepLines = (m) => m.replace(/[^\n]/g, ' ')
  let s = src.replace(/<!--[\s\S]*?-->/g, keepLines)
  // block and line comments outside strings: a small scanner
  let out = ''
  let i = 0
  let q = null
  while (i < s.length) {
    const c = s[i]
    const n = s[i + 1]
    if (q) {
      out += c
      if (c === '\\') { out += n ?? ''; i += 2; continue }
      if (c === q) q = null
      i++
      continue
    }
    if (c === "'" || c === '"' || c === '`') { q = c; out += c; i++; continue }
    if (c === '/' && n === '*') {
      const end = s.indexOf('*/', i + 2)
      const stop = end < 0 ? s.length : end + 2
      out += keepLines(s.slice(i, stop))
      i = stop
      continue
    }
    if (c === '/' && n === '/' && (i === 0 || s[i - 1] !== ':')) {
      const end = s.indexOf('\n', i)
      const stop = end < 0 ? s.length : end
      out += keepLines(s.slice(i, stop))
      i = stop
      continue
    }
    // a quote inside template text (e.g. 飞手's) must not start a "string"
    if (c === '>' ) { out += c; i++; continue }
    out += c
    i++
  }
  return out
}

function unescape(s) {
  return s.replace(/\\(['"`\\])/g, '$1').replace(/\\n/g, '\n')
}

const CALL = /(?<![\w$.])(t\(|tb\(|tc\(\s*'[\w-]+',)\s*(['"`])((?:\\.|(?!\2)[\s\S])*?)\2/g

export function loadEnglish() {
  const dir = path.join(SRC, 'i18n', 'en')
  const keys = new Set()
  if (!fs.existsSync(dir)) return keys
  for (const f of fs.readdirSync(dir)) {
    if (!f.endsWith('.ts')) continue
    const src = fs.readFileSync(path.join(dir, f), 'utf8')
    // entries are  'key': 'value',  or  "key": "value",
    const re = /^\s*(['"])((?:\\.|(?!\1).)*)\1\s*:/gm
    let m
    while ((m = re.exec(src))) keys.add(unescape(m[2]))
  }
  return keys
}

export function scanFile(file, english) {
  const raw = fs.readFileSync(file, 'utf8')
  // a Chinese source file with a separate English counterpart (e.g. the manual's HTML) marks itself as a whole
  if (raw.includes('i18n-ignore-file')) return []
  const lines = raw.split('\n')
  const ignored = new Set(lines.map((l, i) => (l.includes('i18n-ignore') ? i : -1)).filter((i) => i >= 0))
  let s = stripComments(raw)
  const issues = []
  const lineOf = (idx) => s.slice(0, idx).split('\n').length - 1
  // keys of t()/tb() calls
  s = s.replace(CALL, (whole, fn, q, body, offset) => {
    const ln = lineOf(offset)
    if (!ignored.has(ln)) {
      if (q === '`' && body.includes('${')) issues.push({ kind: 'dynamic', line: ln + 1, text: body })
      else if (fn === 't(' && CJK.test(body) && !english.has(unescape(body))) issues.push({ kind: 'missing', line: ln + 1, text: unescape(body) })
      else if (fn.startsWith('tc') && CJK.test(body)) {
        const ctx = /'([\w-]+)'/.exec(fn)[1]
        if (!english.has(ctx + '::' + unescape(body)) && !english.has(unescape(body))) issues.push({ kind: 'missing', line: ln + 1, text: ctx + '::' + unescape(body) })
      }
    }
    return whole.replace(/[^\n]/g, ' ')
  })
  s.split('\n').forEach((l, i) => {
    if (ignored.has(i) || !CJK.test(l)) return
    issues.push({ kind: 'untranslated', line: i + 1, text: l.trim().slice(0, 160) })
  })
  return issues
}

export function scan(paths) {
  const english = loadEnglish()
  const files = (paths.length ? paths : [SRC]).flatMap((p) => walkFiles(path.resolve(ROOT, p)))
  const report = []
  for (const f of files) {
    const issues = scanFile(f, english)
    if (issues.length) report.push({ file: path.relative(ROOT, f), issues })
  }
  return report
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const report = scan(process.argv.slice(2))
  let n = 0
  for (const r of report) {
    console.log(r.file)
    for (const i of r.issues) {
      n++
      console.log(`  ${String(i.line).padStart(4)}  ${i.kind.padEnd(12)} ${i.text}`)
    }
  }
  console.log(n ? `\n${n} issue(s) in ${report.length} file(s)` : 'no issues')
  process.exit(n ? 1 : 0)
}
