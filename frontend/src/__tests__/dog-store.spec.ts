/**
 * Browser side of the dog control (review 2026-11-07): command states only move forward, the clock offset uses quick
 * round trips, a silent backend makes the dog offline, the Lite3 stand toggle is never sent twice, holds start only
 * after the previous one ended, and control taken while leaving the page is handed straight back.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useDogStore } from '@/stores/dog'
import { useDog2Store } from '@/stores/dogv2'
import { dogApi, type DogCommand, type Lite3State } from '@/api/dog'

vi.mock('@/api/dog', async (importOriginal) => {
  const real = await importOriginal<typeof import('@/api/dog')>()
  return {
    ...real,
    beacon: vi.fn(),
    dogApi: {
      ...real.dogApi,
      time: vi.fn(),
      s10Hold: vi.fn(),
      s10ArmHold: vi.fn(),
      lite3: vi.fn(),
      s10Action: vi.fn(),
    },
  }
})

function cmd(state: DogCommand['state'], over: Partial<DogCommand> = {}): DogCommand {
  return { id: 'c1', dogId: 's10', action: 'snapshot', label: '拍照', params: {}, state, detail: null, error: null, result: null, jobId: null, createdAt: 1, finishedAt: null, ...over }
}

function lite3(over: Partial<Lite3State['robot']> = {}): Lite3State {
  return {
    dogId: 'lite3', kind: 'lite3', name: 'Lite3', link: { state: 'online', lastOkAt: Date.now(), rttMs: 20 }, serverTime: Date.now(),
    statusAt: Date.now(), robot: { connected: true, robot_state: '站立（力控）', feedback_age: 0.1, controller: null, ...over },
  }
}

/** A promise the test resolves by hand. */
function later<T>(): { p: Promise<T>; resolve: (v: T) => void } {
  let resolve!: (v: T) => void
  const p = new Promise<T>((r) => (resolve = r))
  return { p, resolve }
}
const flush = () => new Promise((r) => setTimeout(r, 0))

describe('dog store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.mocked(dogApi.time).mockReset()
    vi.mocked(dogApi.s10Hold).mockReset()
    vi.mocked(dogApi.lite3).mockReset()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('a late REST reply never turns a finished command back into running', () => {
    const store = useDogStore()
    store.onCommand(cmd('sent'))
    store.onCommand(cmd('done'))          // pushed over the WebSocket
    store.onCommand(cmd('running'))       // the slow REST reply of the same command
    expect(store.commands.s10[0]!.state).toBe('done')
  })

  it('a dog whose state stops arriving shows offline, whatever its last state said', () => {
    vi.useFakeTimers()
    const store = useDogStore()
    store.onState(lite3(), true)
    expect(store.online('lite3')).toBe(true)
    vi.advanceTimersByTime(4000)
    store.tick = Date.now()
    expect(store.online('lite3')).toBe(false)
  })

  it('a page that stops hearing about a connected dog says so, and does not call the dog lost (field test 2026-11-10)', () => {
    vi.useFakeTimers()
    const store = useDogStore()
    store.onState(lite3({ controller: 'platform' }), true)    // being controlled from this platform: "active"
    vi.advanceTimersByTime(10_000)
    store.tick = Date.now()
    expect(store.online('lite3')).toBe(false)                 // controls stay off on stale data
    expect(store.pageStale('lite3')).toBe(true)
    expect(store.staleSecs('lite3')).toBe(10)
    expect(store.lost('lite3')).toBe(false)
    expect(store.important('lite3')).toBe(true)               // its tile stays, showing the last data
  })

  it('a dog the backend reports gone while active is still lost', () => {
    vi.useFakeTimers()
    const store = useDogStore()
    store.onState(lite3({ controller: 'platform' }), true)
    const gone = lite3()
    gone.link = { state: 'offline', lastOkAt: Date.now(), rttMs: null }
    store.onState(gone, true)
    expect(store.pageStale('lite3')).toBe(false)
    expect(store.lost('lite3')).toBe(true)
  })

  it('the Lite3 stand toggle is not sent twice within 3 s (new dog system since 2026-11-10)', async () => {
    const store = useDogStore()
    const v2 = useDog2Store()
    v2.dogs = [{ id: 'lite3-01', model: 'lite3', control: { held: true, mine: true, session: 'sess', endedReason: null } }] as never
    const send = vi.spyOn(v2, 'command').mockResolvedValue({ result: 'done' })
    store.l3.session = 'sess'
    await store.l3Mode('stand', '趴下')
    await store.l3Mode('stand', '起立')
    expect(send.mock.calls.filter((c) => c[1] === 'stand_toggle')).toHaveLength(1)
  })

  it('the old path\'s Lite3 pushes are ignored: the Lite3 comes from the new dog system only', () => {
    const store = useDogStore()
    store.onState(lite3())
    expect(store.lite3).toBeUndefined()
  })

  it('a new S10 hold starts only after the previous one has been ended', async () => {
    const store = useDogStore()
    const end1 = later<object>()
    const calls: string[] = []
    vi.mocked(dogApi.s10Hold).mockImplementation(((b: { op: string; session?: string }) => {
      calls.push(b.op)
      if (b.op === 'start') return Promise.resolve({ session: `s${calls.length}` })
      if (b.op === 'end') return end1.p
      return Promise.resolve({ ok: true })
    }) as never)
    await store.s10HoldStart('fwd', 0.1, 0, 0, '前进')
    const ending = store.s10HoldEnd('松手')   // in flight: not answered yet…
    // the operator switches direction at once
    const second = store.s10HoldStart('left', 0, 0.1, 0, '左移')
    await flush()
    expect(calls.filter((c) => c === 'start')).toHaveLength(1)   // …so the second start waits
    end1.resolve({ confirmed: true })
    await ending
    await second
    expect(calls.filter((c) => c === 'start')).toHaveLength(2)
    expect(calls.indexOf('end')).toBeLessThan(calls.lastIndexOf('start'))
    await store.s10HoldEnd('松手')
  })

  it('the clock offset comes from the quickest recent round trip', async () => {
    const store = useDogStore()
    let now = 1_000_000
    const spy = vi.spyOn(Date, 'now').mockImplementation(() => now)
    // a quick sample: 100 ms round trip, the server is 5 s ahead
    vi.mocked(dogApi.time).mockImplementationOnce((async () => {
      const mid = now + 50
      now += 100
      return { serverMs: mid + 5000, mode: 'mock' }
    }) as never)
    await store.syncTime()
    expect(Math.round(store.serverOffsetMs)).toBe(5000)
    // then a slow, lopsided one (1.2 s, the reply sat in a queue): its midpoint is 0.5 s off and must not be used
    now += 5000
    vi.mocked(dogApi.time).mockImplementationOnce((async () => {
      const sent = now
      now += 1200
      return { serverMs: sent + 100 + 5000, mode: 'mock' }
    }) as never)
    await store.syncTime()
    spy.mockRestore()
    expect(Math.round(store.serverOffsetMs)).toBe(5000)
  })
})
