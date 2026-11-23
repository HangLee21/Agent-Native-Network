import { afterEach, describe, expect, it } from 'vitest'
import { lang, t } from '@/i18n'
import type { FlightCommand, FlightEvent } from '@/api/history'
import { commandMarks, targetsAt } from '@/utils/replay'

afterEach(() => {
  lang.value = 'zh'
})

const cmd = (over: Partial<FlightCommand>): FlightCommand => ({
  id: 'c1', createdAt: 1000, completedAt: null, commandType: 'FlyTo', label: '飞往', status: 'ACKED', message: null, ...over,
} as FlightCommand)

describe('flight logs in English', () => {
  it('joins a command and its result with English punctuation', () => {
    expect(commandMarks([cmd({ label: '飞往', message: '已到达' })])[0]!.label).toBe('飞往：已到达')
    lang.value = 'en'
    expect(commandMarks([cmd({ label: 'Fly to', message: 'Arrived' })])[0]!.label).toBe('Fly to: Arrived')
  })

  it('names an unlabelled map target', () => {
    const e = { id: 'e1', ts: 10, eventType: 'TARGET_SELECTED', eventLevel: 'INFO', title: '', payload: { targetId: 'a', target: { input: 'MAP', lat: 1, lon: 2 } } } as unknown as FlightEvent
    expect(targetsAt([e], 20)[0]!.label).toBe('地图目标')
    lang.value = 'en'
    expect(targetsAt([e], 20)[0]!.label).toBe('Map target')
  })

  it('uses whole sentences with plurals', () => {
    lang.value = 'en'
    expect(t('已删除 {n} 条', { n: 1 })).toBe('Deleted 1 log')
    expect(t('已删除 {n} 条，跳过 {skipped} 条（受保护或正在记录）', { n: 3, skipped: 1 })).toBe('Deleted 3 logs, skipped 1 (protected or still logging)')
    expect(t('{n} 次飞行 · {m} 条遥测', { n: 2, m: 1 })).toBe('2 flights · 1 telemetry row')
    expect(t('{name} 阶段', { name: 'A' })).toBe('A phase')
  })
})
