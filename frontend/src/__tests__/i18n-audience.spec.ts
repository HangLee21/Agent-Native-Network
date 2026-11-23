import { afterEach, describe, expect, it } from 'vitest'
import { lang, t, tb } from '@/i18n'

describe('English for the demo and Watch pages', () => {
  afterEach(() => {
    lang.value = 'zh'
  })

  it('gives whole-sentence English with placeholders and plurals', () => {
    lang.value = 'en'
    expect(t('{label} 机', { label: 'A' })).toBe('Drone A')
    expect(t('{n} 点', { n: 1 })).toBe('1 point')
    expect(t('{n} 点', { n: 5 })).toBe('5 points')
    expect(t('实时 · {labels} 共 {n} 架', { labels: 'A, B', n: 2 })).toBe('Live · A, B (2 drones)')
    expect(t('失联 {n} 秒', { n: 7 })).toBe('Link lost 7 s')
  })

  it('translates the backend words the demo pages compare against', () => {
    lang.value = 'en'
    // message-log party and semantic-map cell labels arrive translated; tb() gives the same text
    expect(tb('狗')).toBe('Dog')
    expect(tb('可通行')).toBe('Passable')
    expect(tb('未知')).toBe('Unknown')
    lang.value = 'zh'
    expect(tb('狗')).toBe('狗')
    expect(t('{label} 机', { label: 'A' })).toBe('A 机')
  })
})
