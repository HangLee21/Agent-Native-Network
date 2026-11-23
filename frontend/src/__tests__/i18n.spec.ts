import { afterEach, describe, expect, it } from 'vitest'
import { lang, t, tb, tc, translateIncoming, EN } from '@/i18n'
import { modeLabel } from '@/utils/format'
// @ts-expect-error plain JS helper shared with the command line (scripts/i18n-scan.mjs)
import { scan } from '../../scripts/i18n-scan.mjs'
// @ts-expect-error plain JS helper shared with the command line (scripts/i18n-conflicts.mjs)
import { conflicts } from '../../scripts/i18n-conflicts.mjs'

afterEach(() => {
  lang.value = 'zh'
})

describe('interface language', () => {
  it('is Chinese by default and t() returns the Chinese text unchanged', () => {
    expect(lang.value).toBe('zh')
    expect(t('设置')).toBe('设置')
    expect(t('{n} 台', { n: 2 })).toBe('2 台')
    expect(tc('phase', '起飞')).toBe('起飞')
  })

  it('gives the English text, placeholders and plurals in English mode', () => {
    lang.value = 'en'
    expect(t('设置')).toBe('Settings')
    expect(t('{n} 台', { n: 1 })).toBe('1 device')
    expect(t('{n} 台', { n: 3 })).toBe('3 devices')
    expect(t('请求失败（HTTP {status}）', { status: 502 })).toBe('Request failed (HTTP 502)')
    expect(tc('phase', '起飞')).toBe('Takeoff')
    expect(tc('nowhere', '设置')).toBe('Settings')
    // a string without an entry stays Chinese rather than disappearing
    expect(t('没有这一条')).toBe('没有这一条')
  })

  it('keeps tables built from t() in step with the language they were built in', () => {
    // modules build their tables when they load; switching language reloads the page, so only the default is checked here
    expect(modeLabel(0)).toBe('待机')
  })

  it('translates backend text only in English mode and never touches names people typed', () => {
    const zh = { message: '无法连接后端服务', name: '设置', nested: [{ reason: '设置' }] }
    expect(translateIncoming(structuredClone(zh))).toEqual(zh)
    lang.value = 'en'
    const out = translateIncoming(structuredClone(zh))
    expect(out.message).toBe('Cannot reach the backend')
    expect(out.name).toBe('设置')
    expect(out.nested[0]?.reason).toBe('Settings')
    expect(tb('ok')).toBe('ok')
  })
})

describe('English dictionary', () => {
  it('has no empty entries and no Chinese left in the English text', () => {
    const bad = Object.entries(EN).filter(([, v]) => !v.trim() || /[一-鿿]/.test(v))
    expect(bad).toEqual([])
  })

  it('keeps every {placeholder} of the Chinese key in the English text', () => {
    const names = (s: string) => [...s.matchAll(/\{(\w+)(?:\|[^}]*)?\}/g)].map((m) => m[1]).sort()
    const bad = Object.entries(EN).filter(([k, v]) => {
      const a = new Set(names(k))
      const b = new Set(names(v))
      return [...a].some((x) => !b.has(x)) || [...b].some((x) => !a.has(x))
    })
    expect(bad).toEqual([])
  })

  it('gives each Chinese key one English across the dictionaries (else use tc())', () => {
    expect((conflicts() as [string, unknown][]).map(([k]) => k)).toEqual([])
  })

  it('covers every interface string in the source (node scripts/i18n-scan.mjs lists what is left)', () => {
    const report = scan([]) as { file: string; issues: { kind: string; line: number; text: string }[] }[]
    const lines = report.flatMap((r) => r.issues.map((i) => `${r.file}:${i.line} ${i.kind} ${i.text}`))
    expect(lines).toEqual([])
  })
})
