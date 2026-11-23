import { afterEach, describe, expect, it } from 'vitest'
import { lang, t } from '@/i18n'

afterEach(() => {
  lang.value = 'zh'
})

describe('flight control, video and targets in English', () => {
  it('fills the safety texts with their values', () => {
    lang.value = 'en'
    expect(t('确认 {name} 起飞', { name: 'M4E-1' })).toBe('Confirm takeoff: M4E-1')
    expect(t('已解锁 · {n} 秒后上锁（点击上锁）', { n: 12 })).toBe('Unlocked · locks in 12 s (click to lock)')
    expect(t('平台限高 {h} m，超出将被安全层拒绝。', { h: 120 })).toBe('Platform altitude limit 120 m; anything higher is rejected by the safety check.')
    expect(t('{names} 正在空中：返航高度必须与它至少相差 {m} m，平台会检查。', { names: 'A, B', m: 10 }))
      .toBe("Already in the air: A, B. This drone's RTH altitude must differ from it by at least 10 m; the platform checks this.")
  })

  it('uses singular and plural vertex counts', () => {
    lang.value = 'en'
    expect(t('AI 工作区 · {n} 个顶点', { n: 1 })).toBe('AI work area · 1 vertex')
    expect(t('AI 工作区 · {n} 个顶点', { n: 4 })).toBe('AI work area · 4 vertices')
  })

  it('keeps the Chinese text in Chinese mode', () => {
    expect(t('确认 {name} 起飞', { name: 'M4E-1' })).toBe('确认 M4E-1 起飞')
    expect(t('紧急降落')).toBe('紧急降落')
  })
})
