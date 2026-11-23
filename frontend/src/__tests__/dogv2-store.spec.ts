/**
 * New dog system, browser side: hold beats leave every 100 ms without waiting for the previous one (the old Lite3
 * path waited and lost control 9 times in the 2026-11-09 field test), an idle beat keeps control, a 409 means
 * control is gone.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useDog2Store } from '@/stores/dogv2'
import { dog2Api } from '@/api/dogv2'
import { ApiError } from '@/api/http'

vi.mock('@/api/dogv2', async (importOriginal) => {
  const real = await importOriginal<typeof import('@/api/dogv2')>()
  return {
    ...real,
    dog2Api: { ...real.dog2Api, list: vi.fn(), take: vi.fn(), release: vi.fn(), teleop: vi.fn(), command: vi.fn() },
  }
})

const api = vi.mocked(dog2Api)

describe('new dog store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
    api.list.mockResolvedValue({ mode: 'mock', broker: true, dogs: [] })
    api.take.mockResolvedValue({ result: 'done', session: 'web-1' })
    api.release.mockResolvedValue({ result: 'done' })
  })
  afterEach(() => {
    vi.useRealTimers()
    vi.clearAllMocks()
  })

  it('sends a beat every 100 ms while held, even when replies never come', async () => {
    api.teleop.mockReturnValue(new Promise<never>(() => undefined))   // the backend never answers
    const s = useDog2Store()
    await s.take('lite3-01')
    s.setAxes([1, 0, 0])
    expect(api.teleop).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(250)
    // three beats out and none answered: the store holds back the fourth rather than piling up
    expect(api.teleop).toHaveBeenCalledTimes(3)
  })

  it('does not wait: answered beats keep flowing at the rhythm', async () => {
    api.teleop.mockResolvedValue({ ok: true, seq: 1 })
    const s = useDog2Store()
    await s.take('lite3-01')
    s.setAxes([0, 0, 1])
    await vi.advanceTimersByTimeAsync(1000)
    const calls = api.teleop.mock.calls.length
    expect(calls).toBeGreaterThanOrEqual(10)
    expect(calls).toBeLessThanOrEqual(12)
    expect(api.teleop.mock.calls[api.teleop.mock.calls.length - 1]?.[2]).toEqual([0, 0, 1])
  })

  it('a released key goes out at once, then idle beats about every 0.8 s keep control', async () => {
    api.teleop.mockResolvedValue({ ok: true, seq: 1 })
    const s = useDog2Store()
    await s.take('lite3-01')
    s.setAxes([1, 0, 0])
    await vi.advanceTimersByTimeAsync(300)
    api.teleop.mockClear()
    s.setAxes([0, 0, 0])
    expect(api.teleop).toHaveBeenCalledTimes(1)
    expect(api.teleop.mock.calls[0]?.[2]).toEqual([0, 0, 0])
    await vi.advanceTimersByTimeAsync(2000)
    expect(api.teleop.mock.calls.length).toBeGreaterThanOrEqual(2)
    expect(api.teleop.mock.calls.length).toBeLessThanOrEqual(4)
  })

  it('a 409 on a beat means control is gone; nothing more is sent', async () => {
    api.teleop.mockRejectedValue(new ApiError('控制已解除：浏览器没有心跳', 409))
    const s = useDog2Store()
    await s.take('lite3-01')
    s.setAxes([1, 0, 0])
    await vi.advanceTimersByTimeAsync(50)
    expect(s.hold.session).toBeNull()
    expect(s.hold.lostReason).toBe('浏览器没有心跳')
    const n = api.teleop.mock.calls.length
    await vi.advanceTimersByTimeAsync(500)
    expect(api.teleop.mock.calls.length).toBe(n)
  })

  it('numbers every beat so the backend can drop one that arrives late', async () => {
    api.teleop.mockResolvedValue({ ok: true, seq: 1 })
    const s = useDog2Store()
    await s.take('lite3-01')
    s.setAxes([1, 0, 0])
    await vi.advanceTimersByTimeAsync(250)
    s.setAxes([0, 0, 0])
    const ns = api.teleop.mock.calls.map((c) => c[3] as number)
    expect(ns.length).toBeGreaterThanOrEqual(3)
    ns.forEach((n, i) => { if (i > 0) expect(n).toBe((ns[i - 1] ?? 0) + 1) })
  })

  it('leaving hands control back', async () => {
    api.teleop.mockResolvedValue({ ok: true, seq: 1 })
    const s = useDog2Store()
    await s.take('lite3-01')
    s.leave('离开新狗系统页')
    await vi.advanceTimersByTimeAsync(10)
    expect(api.release).toHaveBeenCalledWith('lite3-01', 'web-1', '离开新狗系统页')
    expect(s.hold.session).toBeNull()
  })
  it('a poll that does not come back is abandoned after 2 s and the next one goes out (field test 2026-11-10)', async () => {
    const signals: (AbortSignal | undefined)[] = []
    api.list.mockImplementationOnce((sig?: AbortSignal) => {
      signals.push(sig)
      return new Promise<never>(() => undefined)               // stuck
    })
    api.list.mockImplementation((sig?: AbortSignal) => {
      signals.push(sig)
      return Promise.resolve({ mode: 'on', broker: true, dogs: [] })
    })
    const s = useDog2Store()
    s.start(700)
    await vi.advanceTimersByTimeAsync(1500)
    expect(api.list).toHaveBeenCalledTimes(1)                    // no pile-up behind the stuck one
    await vi.advanceTimersByTimeAsync(700)
    expect(api.list).toHaveBeenCalledTimes(2)
    expect(signals[0]?.aborted).toBe(true)
    expect(s.mode).toBe('on')
    s.stop()
  })
})
