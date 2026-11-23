/**
 * Interface language (docs/i18n.md). Chinese is the default and the source text: every UI string is written in
 * Chinese and wrapped in t('…'); the Chinese text is the key into the English dictionaries in ./en/*.ts. With the
 * language set to Chinese, t() returns its argument unchanged, so the Chinese interface is exactly what it was.
 *
 * The language is chosen in Settings → 系统与接入 and remembered per browser (localStorage). There is no detection
 * of the browser's language. Switching reloads the page, so tables built when a module loads are rebuilt too.
 *
 * Text that comes from the backend (rejection reasons, alerts, step names…) is translated where it arrives
 * (api/http.ts, services/ws.ts) by translateIncoming(), using the templates in ./backend/*.ts.
 */
import { ref } from 'vue'

export type Lang = 'zh' | 'en'
export type Params = Record<string, string | number | boolean | null | undefined>

const LANG_KEY = 'uav.lang'

function readLang(): Lang {
  try {
    return localStorage.getItem(LANG_KEY) === 'en' ? 'en' : 'zh'
  } catch {
    return 'zh'
  }
}

/** Current interface language. Reactive, so templates that call t() re-render if it changes. */
export const lang = ref<Lang>(readLang())

/** Chinese source text → English. Empty until loadLanguage() has run (only in English mode). */
export const EN: Record<string, string> = {}

/**
 * Fills {name} placeholders. English plurals: {n|drone|drones} gives "drone" when n is 1 and "drones" otherwise
 * (the number itself is written separately: '{n} {n|drone|drones}').
 */
function fill(s: string, params?: Params): string {
  if (!params) return s
  return s
    .replace(/\{(\w+)\|([^|{}]*)\|([^|{}]*)\}/g, (whole, k: string, one: string, many: string) =>
      k in params ? (Number(params[k]) === 1 ? one : many) : whole)
    .replace(/\{(\w+)\}/g, (whole, k: string) => (k in params ? String(params[k] ?? '') : whole))
}

/**
 * Translates one UI string. `zh` is the Chinese text (also the dictionary key); `{name}` placeholders are filled
 * from `params` in either language. A string with no English entry stays Chinese.
 */
export function t(zh: string, params?: Params): string {
  const s = lang.value === 'en' ? EN[zh] ?? zh : zh
  return fill(s, params)
}

/**
 * Like t(), for a Chinese word that means different things in different places (标记 = the "Mark" button, or "Tags"
 * in a flight log). The English entry is looked up as '<ctx>::中文' first, then as '中文'. Chinese ignores `ctx`.
 */
export function tc(ctx: string, zh: string, params?: Params): string {
  const s = lang.value === 'en' ? EN[ctx + '::' + zh] ?? EN[zh] ?? zh : zh
  return fill(s, params)
}

export const isEn = (): boolean => lang.value === 'en'

/** BCP 47 locale for dates and times: 24-hour clock in both languages. */
export const dateLocale = (): string => (lang.value === 'en' ? 'en-GB' : 'zh-CN')

/** Saves the language and reloads the page. */
export function setLang(l: Lang): void {
  if (l === lang.value) return
  try {
    localStorage.setItem(LANG_KEY, l)
  } catch {
    /* storage unavailable: the language applies until the reload only */
  }
  lang.value = l
  window.location.reload()
}

/** Called once at start-up: marks the document's language for screen readers, hyphenation and fonts. */
export function applyDocumentLang(): void {
  document.documentElement.lang = lang.value === 'en' ? 'en' : 'zh-CN'
}

// ---------------------------------------------------------------- backend text

const CJK = /[㐀-鿿豈-﫿]/

/**
 * One backend message template: Chinese with {0}, {1}… (or {name}) for the parts the backend fills in, and the
 * English with the same placeholders. Captured parts are translated again (they are often a mode or phase name).
 */
export type BackendTemplate = readonly [zh: string, en: string]

interface Compiled {
  re: RegExp
  names: string[]
  en: string
  weight: number
}

const exact = new Map<string, string>()
const patterns: Compiled[] = []

function escapeRe(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function compile(list: readonly BackendTemplate[]): void {
  for (const [zh, en] of list) {
    const names: string[] = []
    const parts = zh.split(/\{(\w+)\}/g)
    if (parts.length === 1) {
      exact.set(zh, en)
      continue
    }
    let src = ''
    let literal = 0
    parts.forEach((p, i) => {
      if (i % 2 === 1) {
        names.push(p)
        src += '([\\s\\S]+?)'
      } else {
        src += escapeRe(p)
        literal += p.length
      }
    })
    // a template that is almost all placeholder would match unrelated text (names people typed)
    if (literal < 2) continue
    patterns.push({ re: new RegExp('^' + src + '$'), names, en, weight: literal })
  }
}

// English is a separate download, fetched only when the interface is in English (Chinese pages never load it)
const enLoaders = import.meta.glob<{ default: Record<string, string> }>('./en/*.ts')
const backendLoaders = import.meta.glob<{ default: readonly BackendTemplate[] }>('./backend/*.ts')
let loaded = false

/**
 * Loads the English dictionaries and backend templates. main.ts awaits it before importing the app, because many
 * modules build label tables with t() when they load. Does nothing in Chinese mode unless `force` (tests).
 */
export async function loadLanguage(force = false): Promise<void> {
  if (loaded || (!force && lang.value !== 'en')) return
  const [en, backend] = await Promise.all([
    Promise.all(Object.keys(enLoaders).sort().map((k) => enLoaders[k]!())),
    Promise.all(Object.keys(backendLoaders).sort().map((k) => backendLoaders[k]!())),
  ])
  for (const m of en) Object.assign(EN, m.default)
  for (const m of backend) compile(m.default)
  // the most specific template wins
  patterns.sort((a, b) => b.weight - a.weight)
  cache.clear()
  loaded = true
}

const cache = new Map<string, string>()

function translateOne(s: string, depth: number): string {
  const hit = exact.get(s) ?? EN[s]
  if (hit !== undefined) return hit
  for (const p of patterns) {
    const m = p.re.exec(s)
    if (!m) continue
    const vals: Record<string, string> = {}
    p.names.forEach((n, i) => {
      const v = m[i + 1] ?? ''
      vals[n] = depth < 3 && CJK.test(v) ? translateText(v, depth + 1) : v
    })
    return p.en.replace(/\{(\w+)\}/g, (whole, k: string) => vals[k] ?? whole)
  }
  return s
}

/** Splits on sentence and list separators the backend joins messages with, keeping the separators. */
const SEPARATORS = /(；|。|\n|，|、|：)/

function translateText(s: string, depth = 0): string {
  const whole = translateOne(s, depth)
  if (whole !== s) return whole
  if (depth > 0 && !SEPARATORS.test(s)) return s
  const pieces = s.split(SEPARATORS)
  if (pieces.length === 1) return s
  let changed = false
  const out = pieces.map((p) => {
    if (p === '；') return '; '
    if (p === '。') return '. '
    if (p === '，') return ', '
    if (p === '、') return ', '
    if (p === '：') return ': '
    if (p === '\n') return p
    const tr = translateOne(p.trim(), depth)
    if (tr !== p.trim()) changed = true
    return tr
  })
  return changed ? out.join('').replace(/\s+$/, '').replace(/ {2,}/g, ' ') : s
}

/**
 * Translates a message the backend wrote in Chinese. Returns it unchanged in Chinese mode or when no template fits.
 */
export function tb(s: string | null | undefined): string {
  if (s === null || s === undefined) return ''
  if (lang.value !== 'en' || !CJK.test(s)) return s
  let r = cache.get(s)
  if (r === undefined) {
    r = translateText(s)
    if (cache.size > 5000) cache.clear()
    cache.set(s, r)
  }
  return r
}

/**
 * Translates every Chinese string inside data received from the backend (HTTP responses, WebSocket pushes).
 * Only in English mode; in Chinese mode the data is returned as it is. Object keys are never changed.
 */
export function translateIncoming<T>(data: T): T {
  if (lang.value !== 'en') return data
  return walk(data, 0) as T
}

/** Fields that hold what people typed (route and device names…): never translated, so saving them back is safe. */
const USER_TEXT_KEYS = new Set(['name', 'routeName', 'droneName', 'displayName', 'nickname', 'note', 'remark', 'comment', 'description', 'messages'])

function walk(v: unknown, depth: number): unknown {
  if (typeof v === 'string') return CJK.test(v) ? tb(v) : v
  if (depth > 12 || v === null || typeof v !== 'object') return v
  if (Array.isArray(v)) {
    for (let i = 0; i < v.length; i++) {
      const x = v[i]
      if (typeof x === 'string' || (x !== null && typeof x === 'object')) v[i] = walk(x, depth + 1)
    }
    return v
  }
  const o = v as Record<string, unknown>
  for (const k of Object.keys(o)) {
    if (USER_TEXT_KEYS.has(k)) continue
    const x = o[k]
    if (typeof x === 'string' || (x !== null && typeof x === 'object')) o[k] = walk(x, depth + 1)
  }
  return o
}
