import { afterEach, describe, expect, it } from 'vitest'
import { lang, t } from '@/i18n'

afterEach(() => {
  lang.value = 'zh'
})

describe('Plan page English', () => {
  it('keeps the Chinese unchanged, including the plural-only key', () => {
    expect(t('{n|个航点|个航点}', { n: 1 })).toBe('个航点')
    expect(t('已到达 {a}/{b}', { a: 1, b: 3 })).toBe('已到达 1/3')
  })

  it('uses singular and plural forms in English', () => {
    lang.value = 'en'
    expect(t('{n|个航点|个航点}', { n: 1 })).toBe('waypoint')
    expect(t('{n|个航点|个航点}', { n: 4 })).toBe('waypoints')
    expect(t('确认删除选中的 {n} 个航点？', { n: 2 })).toBe('Delete the 2 selected waypoints?')
    expect(t('安全检查未通过（{n} 项）', { n: 1 })).toBe('Safety check failed (1 issue)')
    expect(t('{n} 点 · 最高 {h} m', { n: 5, h: 60 })).toBe('5 pts · max 60 m')
    expect(t('已保存「{name}」', { name: '东门巡检' })).toBe('Saved "东门巡检"')
    expect(t('{head}：{list}', { head: 'Safety check failed', list: 'a; b' })).toBe('Safety check failed: a; b')
  })
})
