import { afterEach, describe, expect, it } from 'vitest'
import { lang, t, tc } from '@/i18n'

afterEach(() => {
  lang.value = 'zh'
})

describe('Monitor page in English', () => {
  it('uses the glossary names on the safety buttons', () => {
    lang.value = 'en'
    expect(t('起飞')).toBe('Take off')
    expect(t('一键起飞')).toBe('Take off')
    expect(t('返航')).toBe('Return home')
    expect(t('取消返航')).toBe('Cancel RTH')
    expect(tc('monitor', '急停')).toBe('E-stop')
    expect(t('急停 {name}', { name: 'A' })).toBe('E-stop A')
    expect(t('停止')).toBe('Stop')
    expect(tc('monitor', '申请控制权')).toBe('Request control')
    expect(t('释放控制权')).toBe('Release control')
    expect(t('进入 DRC')).toBe('Enter DRC')
  })

  it('keeps words with two meanings apart', () => {
    lang.value = 'en'
    expect(tc('verb', '设置')).toBe('Set')
    expect(t('设置')).toBe('Settings')
    expect(tc('phase', '控制权')).toBe('Control')
  })

  it('writes whole sentences, with or without a drone name', () => {
    lang.value = 'en'
    expect(t('下一步：执行航线，或按下方「起飞」')).toBe('Next: run a route, or press "Take off" below')
    expect(t('下一步：执行航线，或按下方 {name} 的「起飞」', { name: 'B' })).toBe('Next: run a route, or press "Take off" for B below')
    expect(t('{n} 个航点 · {len} · 最高 {h} m', { n: 1, len: '320 m', h: 60 })).toBe('1 waypoint · 320 m · max 60 m')
    expect(t('{n} 台设备待启用（{names}）→ 设置', { n: 2, names: 'C, D' })).toBe('2 devices to enable (C, D) → Settings')
  })

  it('strips the hover suffix from the stop label in English too', () => {
    lang.value = 'en'
    expect(t('停止执行 · 悬停').replace(t(' · 悬停'), '')).toBe('Stop route')
    lang.value = 'zh'
    expect(t('停止执行 · 悬停').replace(t(' · 悬停'), '')).toBe('停止执行')
  })
})
