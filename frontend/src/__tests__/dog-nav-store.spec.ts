/**
 * Outdoor navigation, browser side (docs/dog/ui-design.md 19; contract 户外GPS导航-架构.md 6.2): the nav endpoints and
 * their reply notes, the platform's 400 with problems, the map draft and its debounced check (an old answer never
 * overwrites a newer one), the dialogs' promises, the Lite3 bridge, and the wording helpers. The backend is mocked.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import { useDog2Store } from '@/stores/dogv2'
import { useDogStore } from '@/stores/dog'
import { dog2Api, dogRoutesApi, type Dog2, type Dog2Nav, type Dog2NavCapability, type Dog2NavCheck } from '@/api/dogv2'
import { ApiError } from '@/api/http'
import { etaText, navAdvice, navPoints, navReason, navReasonDetail, navSummary, navTaskOn, progressText, readyItems, readyLines, speedLevels } from '@/components/dog/dogNav'
import { lite3Next, type Lite3NextInput } from '@/components/dog/dogFlow'
import type { Lite3State } from '@/api/dog'

vi.mock('@/api/dogv2', async (importOriginal) => {
  const real = await importOriginal<typeof import('@/api/dogv2')>()
  return {
    ...real,
    dog2Api: {
      ...real.dog2Api, list: vi.fn(), take: vi.fn(), release: vi.fn(), teleop: vi.fn(), command: vi.fn(),
      nav: vi.fn(), navPrepare: vi.fn(async () => ({ result: 'done' as const })), navCheck: vi.fn(), navStart: vi.fn(), navPause: vi.fn(), navResume: vi.fn(), navCancel: vi.fn(), navOptions: vi.fn(), navSettings: vi.fn(),
    },
    dogRoutesApi: { list: vi.fn(), get: vi.fn(), create: vi.fn(), update: vi.fn(), remove: vi.fn(), fromRoute: vi.fn() },
  }
})
const api = vi.mocked(dog2Api)
const routesApi = vi.mocked(dogRoutesApi)

const CAP: Dog2NavCapability = {
  kind: 'gps', avoidance: true, speed_levels: [{ id: 'slow', mps: 0.12 }, { id: 'mid', mps: 0.2 }, { id: 'fast', mps: 0.3 }],
  default_speed: 'slow', arrive_radius_m: [1, 20], max_points: 200, dry_run: true,
}
const P1 = { lat: 22.5801, lon: 113.9401 }
const P2 = { lat: 22.5805, lon: 113.9405 }
const OK: Dog2NavCheck = { ok: true, problems: [], area: [[22.57, 113.93], [22.57, 113.95], [22.59, 113.95]], areaSource: 'dog', totalM: 60, firstM: 40 }

function dog(nav: Dog2Nav | null, extra: Partial<Dog2> = {}): Dog2 {
  return {
    id: 'lite3-01', label: 'Lite3', model: 'lite3', software: '0.2.0', online: true, enabled: true, mode: 'new', gateway: 'x',
    statusAgeMs: 100, telemetryAgeMs: 100, status: {}, position: null, positionAgeMs: null,
    telemetry: { basic_state: 2, basic_state_name: '站立（力控）', battery_pct: 80, rpy: [0, 0, 0], vel_body: [0, 0, 0], feedback_age_s: 0.05 },
    control: { held: false, mine: false, session: null, endedReason: null }, video: {}, lastSeenAt: Date.now(), navCapability: CAP, nav, ...extra,
  }
}

describe('dog navigation store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
    api.list.mockResolvedValue({ mode: 'mock', broker: true, dogs: [] })
    api.navCheck.mockResolvedValue(OK)
  })
  afterEach(() => {
    vi.useRealTimers()
    vi.clearAllMocks()
  })

  it('starts, and words the dog\'s answer the way every dog command is worded', async () => {
    const s = useDog2Store()
    api.navStart.mockResolvedValue({ result: 'done', taskId: 'n1' })
    const r = await s.navStart('lite3-01', { points: [P1], avoidance: true, arriveRadiusM: 3, standingConfirmed: true })
    expect(api.navStart).toHaveBeenCalledWith('lite3-01', { points: [P1], avoidance: true, arriveRadiusM: 3, standingConfirmed: true })
    expect(r?.result).toBe('done')
    expect(s.notes[0]).toMatchObject({ tone: 'ok', text: '开始导航：狗已执行' })

    api.navStart.mockResolvedValue({ result: 'rejected', code: 'gnss_poor', text: 'GPS 没定位' })
    await s.navStart('lite3-01', { points: [P1], standingConfirmed: true })
    expect(s.notes[0]).toMatchObject({ tone: 'bad', text: '开始导航：狗没执行：GPS 没定位' })

    api.navPause.mockResolvedValue({ result: 'no_reply' })
    await s.navPause('lite3-01')
    expect(s.notes[0]).toMatchObject({ tone: 'warn', text: '暂停导航：没收到回复：狗可能已经收到，先看狗的状态' })
    expect(api.list).toHaveBeenCalled()    // the state after the command is fetched at once
  })

  it('a refused check (HTTP 400) comes back as rejected with its problems; nothing went to the dog', async () => {
    const s = useDog2Store()
    api.navStart.mockRejectedValue(new ApiError('第一个点离狗太远', 400, { error: '第一个点离狗太远', code: 'too_far', problems: [{ code: 'too_far', text: '第一个点离狗 420 m，上限 300 m', index: 0 }] }))
    const r = await s.navStart('lite3-01', { points: [P1], standingConfirmed: true })
    expect(r).toMatchObject({ result: 'rejected', code: 'too_far', problems: [{ code: 'too_far', index: 0 }] })
    expect(s.notes[0]?.tone).toBe('bad')
  })

  it('sends the options and names each change', async () => {
    const s = useDog2Store()
    api.navOptions.mockResolvedValue({ result: 'done' })
    await s.navOptions('lite3-01', { avoidance: false })
    expect(api.navOptions).toHaveBeenCalledWith('lite3-01', { avoidance: false })
    expect(s.notes[0]?.text).toBe('关掉自动避障：狗已执行')
    await s.navOptions('lite3-01', { speedLevel: 'mid' })
    expect(s.notes[0]?.text).toBe('换速度档位：狗已执行')
  })

  it('checks the draft after each change; an old answer never overwrites a newer one', async () => {
    const s = useDog2Store()
    s.draftOpen('lite3-01', [P1])
    await vi.advanceTimersByTimeAsync(1)
    expect(api.navCheck).toHaveBeenLastCalledWith('lite3-01', [P1])
    expect(s.navDraft?.check?.ok).toBe(true)
    expect(s.navArea['lite3-01']).toEqual(OK.area)

    // two quick edits: one check, 300 ms after the last
    api.navCheck.mockClear()
    s.draftAdd(P2)
    await vi.advanceTimersByTimeAsync(100)
    s.draftMove(1, { lat: 22.581, lon: 113.941 })
    await vi.advanceTimersByTimeAsync(299)
    expect(api.navCheck).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(2)
    expect(api.navCheck).toHaveBeenCalledTimes(1)
    expect(s.navDraft?.points).toEqual([P1, { lat: 22.581, lon: 113.941 }])

    // a slow answer to an older version arrives after the newer one
    let slow!: (v: Dog2NavCheck) => void
    api.navCheck.mockReturnValueOnce(new Promise((r) => (slow = r)))
    s.draftRemove(1)
    await vi.advanceTimersByTimeAsync(301)
    api.navCheck.mockResolvedValueOnce({ ...OK, ok: false, problems: [{ code: 'outside_area', text: '点在允许区域外', index: 0 }] })
    s.draftMove(0, P2)
    await vi.advanceTimersByTimeAsync(301)
    slow(OK)
    await vi.advanceTimersByTimeAsync(1)
    expect(s.navDraft?.check?.ok).toBe(false)
    expect(s.navDraft?.check?.problems[0]?.text).toBe('点在允许区域外')

    s.draftClear()
    expect(s.navDraft).toBeNull()
  })

  it('a check that could not be done says why', async () => {
    const s = useDog2Store()
    api.navCheck.mockRejectedValue(new ApiError('连不上狗', 503))
    s.draftOpen('lite3-01', [P1])
    await vi.advanceTimersByTimeAsync(1)
    expect(s.navDraft?.check).toBeNull()
    expect(s.navDraft?.checkError).toBe('连不上狗')
  })

  it('opens saved routes and imports aircraft routes into the draft', async () => {
    const s = useDog2Store()
    routesApi.get.mockResolvedValue({ id: 7, name: '河边', points: [P1, P2] })
    expect(await s.routeOpen('lite3-01', { id: 7, name: '河边', points: [] })).toBeNull()
    expect(s.navDraft).toMatchObject({ dog: 'lite3-01', routeId: 7, routeName: '河边', points: [P1, P2] })
    s.draftAdd({ lat: 22.6, lon: 113.9 })
    expect(s.navDraft?.routeId).toBeNull()    // edited: no longer that saved route

    routesApi.fromRoute.mockResolvedValue({ id: 8, name: '巡检 A', points: [P2] })
    routesApi.list.mockResolvedValue([])
    expect(await s.routeImport('lite3-01', 'r-uuid')).toBeNull()
    expect(routesApi.fromRoute).toHaveBeenCalledWith('r-uuid')
    expect(s.navDraft).toMatchObject({ routeId: 8, points: [P2] })

    routesApi.create.mockResolvedValue({ id: 9, name: '新路线', points: [P2] })
    const saved = await s.routeSave('新路线', [P2])
    expect(routesApi.create).toHaveBeenCalledWith({ name: '新路线', points: [P2] })
    expect(typeof saved).toBe('object')
    expect(s.navDraft?.routeId).toBe(9)
  })

  it('the dialogs resolve with the operator\'s answer; a new one cancels the old', async () => {
    const s = useDog2Store()
    const first = s.askStart('lite3-01', [P1], { source: '目标 1' })
    expect(s.navDialog).toMatchObject({ kind: 'start', dog: 'lite3-01', points: [P1], source: '目标 1', dryRun: false })
    const second = s.askAvoidanceOff('lite3-01')
    expect(await first).toBe(false)
    expect(s.navDialog?.kind).toBe('avoidanceOff')
    s.dialogDone(true)
    expect(await second).toBe(true)
    expect(s.navDialog).toBeNull()
  })
})

describe('Lite3 navigation bridge', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    api.list.mockResolvedValue({ mode: 'mock', broker: true, dogs: [] })
  })
  afterEach(() => vi.clearAllMocks())

  it('is empty for a dog that cannot navigate', async () => {
    const ds = useDogStore()
    useDog2Store().dogs = [dog(null, { navCapability: null })]
    await nextTick()
    expect(ds.lite3).toBeDefined()
    expect(ds.l3NavDog).toBeNull()
    expect(ds.l3NavCap).toBeNull()
    expect(ds.l3Nav).toBeNull()
  })

  it('avoidance off is asked once; while idle it is kept for the next start, while walking it is sent', async () => {
    const ds = useDogStore()
    const v2 = useDog2Store()
    v2.dogs = [dog({ state: 'idle' })]
    await nextTick()
    const p = ds.l3NavAvoidance(false, false)
    expect(v2.navDialog?.kind).toBe('avoidanceOff')
    v2.dialogDone(true)
    await p
    expect(v2.navNext['lite3-01']).toEqual({ avoidance: false, speedLevel: null, speedMps: null })
    expect(api.navOptions).not.toHaveBeenCalled()

    // turning it back on is not asked
    await ds.l3NavAvoidance(true, false)
    expect(v2.navDialog).toBeNull()
    expect(v2.navNext['lite3-01']?.avoidance).toBe(true)

    // while walking: sent, and a refusal goes into the dog's note
    api.navOptions.mockResolvedValue({ result: 'rejected', code: 'no_task', text: '没有任务' })
    const q = ds.l3NavAvoidance(false, true)
    v2.dialogDone(true)
    await q
    expect(api.navOptions).toHaveBeenCalledWith('lite3-01', { avoidance: false })
    expect(ds.notes.lite3?.cls).toBe('bad')

    // cancelled confirmation: nothing sent
    api.navOptions.mockClear()
    const c = ds.l3NavAvoidance(false, true)
    v2.dialogDone(false)
    await c
    expect(api.navOptions).not.toHaveBeenCalled()
  })

  it('ending the navigation counts as a stop for multi-step sequences', async () => {
    const ds = useDogStore()
    useDog2Store().dogs = [dog({ state: 'running', index: 0, count: 1 })]
    await nextTick()
    api.navCancel.mockResolvedValue({ result: 'done' })
    const before = ds.stopSeq
    await ds.l3NavCancel()
    expect(api.navCancel).toHaveBeenCalledWith('lite3-01')
    expect(ds.stopSeq).toBe(before + 1)
  })
})

describe('navigation wording', () => {
  it('reads the task points in either shape and counts from 1 for people', () => {
    expect(navPoints({ state: 'running', points: [[22.1, 113.1], [22.2, 113.2]] })).toEqual([{ lat: 22.1, lon: 113.1 }, { lat: 22.2, lon: 113.2 }])
    const pts = navPoints({ state: 'running', points: [{ lat: 22.1, lon: 113.1, name: '桥头' }] })
    expect(pts).toEqual([{ lat: 22.1, lon: 113.1, name: '桥头' }])
    expect(progressText({ state: 'running', index: 0, count: 1 }, pts)).toBe('走向第 1/1 个点（桥头）')
    expect(progressText({ state: 'running', index: 1, count: 3 }, [])).toBe('走向第 2/3 个点')
  })

  it('names known reasons, shows unknown ones as the dog wrote them', () => {
    expect(navReason({ reason: 'blocked', reason_text: 'front 0.5 m for 20 s' })).toBe('前方有障碍，绕不过去')
    expect(navReasonDetail({ reason: 'blocked', reason_text: 'front 0.5 m for 20 s' })).toBe('front 0.5 m for 20 s')
    expect(navReason({ reason: 'new_reason', reason_text: '狗的新原因' })).toBe('狗的新原因')
    expect(navReason({ reason: 'new_reason', reason_text: null })).toBe('new_reason')
    expect(navReasonDetail({ reason: 'new_reason', reason_text: '狗的新原因' })).toBeNull()
  })

  it('task on = starting, running or paused', () => {
    expect(['starting', 'running', 'paused'].map((state) => navTaskOn({ state }))).toEqual([true, true, true])
    expect(['idle', 'arrived', 'ended'].map((state) => navTaskOn({ state }))).toEqual([false, false, false])
    expect(navTaskOn(null)).toBe(false)
  })

  it('readiness says which item is missing; an unknown lidar is not a problem', () => {
    const items = readyItems({ loc: true, nav2: true, lidar: null, gnss: 'fix', heading: 'course' })
    expect(items.map((i) => [i.key, i.ok])).toEqual([['gnss', true], ['heading', false], ['loc', true], ['lidar', null]])
    expect(items.find((i) => i.key === 'heading')?.text).toBe('朝向没对齐：用按住移动沿一个方向直走 15 米以上，中途别按转向键')
    expect(readyItems({ loc: false, nav2: false, lidar: false, gnss: 'none', heading: 'imu_aligned' }).filter((i) => i.ok === false).map((i) => i.key))
      .toEqual(['gnss', 'loc', 'lidar', 'nav2'])
  })

  it('readiness lines: one per problem; the board\'s text only when it adds something (ui-design.md 20.5)', () => {
    const HEADING = '朝向没对齐：用按住移动沿一个方向直走 15 米以上，中途别按转向键'
    const base = { loc: true, nav2: true, lidar: true, gnss: 'fix', heading: 'imu_aligned' }
    // the board says the same as the heading line: one line, the platform's (the right way to align)
    expect(readyLines({ ...base, heading: 'none', text: '朝向还没对齐：用按住移动向前直走一段' })).toEqual([HEADING])
    // a localisation line from the board is not repeated either
    expect(readyLines({ ...base, loc: false, text: '定位融合还没好' })).toEqual(['定位融合还没好'])
    // the board's GPS text says more: it replaces the platform's "GPS：<state>"
    expect(readyLines({ ...base, gnss: 'single', heading: 'none', text: 'GPS 精度因子 3.2，超过 2.5' })).toEqual(['GPS 精度因子 3.2，超过 2.5', HEADING])
    // something the list does not have (ROS side, motion process): added after the platform's lines
    expect(readyLines({ ...base, heading: 'none', text: '板卡缺 ROS 软件包：nav2_bringup' })).toEqual([HEADING, '板卡缺 ROS 软件包：nav2_bringup'])
    // about an item the platform does not count as missing: the board's word is shown
    expect(readyLines({ ...base, heading: undefined, text: '朝向还没对齐：用按住移动向前直走一段' })).toEqual(['朝向还没对齐：用按住移动向前直走一段'])
    expect(readyLines({ ...base, text: null })).toEqual([])
    expect(readyLines(undefined)).toEqual([])
    expect(navAdvice('heading_unknown')).toBe('用按住移动沿一个方向直走 15 米以上（中途别按转向键）对齐朝向，再点「继续」')
  })

  it('the folded navigation group says the task, or the state and the ready items', () => {
    expect(navSummary(null)).toEqual({ text: '还没收到狗的导航状态', cls: 'dim' })
    expect(navSummary({ state: 'idle', ready: { loc: true, nav2: true, lidar: null, gnss: 'fix', heading: 'none' } }))
      .toEqual({ text: '空闲 · GPS ✓ 朝向 ✕ 定位 ✓ 避障雷达 –', cls: 'warnc' })
    expect(navSummary({ state: 'running', index: 1, count: 3, to_end_m: 118.4 })).toEqual({ text: '导航中 · 2/3 · 离终点 118 m', cls: 'run' })
    expect(navSummary({ state: 'paused', reason: 'blocked' }).cls).toBe('warnc')
  })

  it('speed levels only when the dog reports some; ETA in minutes or seconds', () => {
    expect(speedLevels({ ...CAP, speed_levels: [] })).toEqual([])
    expect(speedLevels(CAP).map((l) => l.id)).toEqual(['slow', 'mid', 'fast'])
    expect(etaText(980)).toBe('约 16 分钟')
    expect(etaText(42)).toBe('约 42 秒')
    expect(etaText(null)).toBe('—')
  })

  it('the next-step line shows the task only for a dog with one, controlled from this page', () => {
    const l: Lite3State = { dogId: 'lite3', kind: 'lite3', name: 'Lite3', link: { state: 'online', lastOkAt: 1, rttMs: 1 }, serverTime: 1, statusAt: 1, robot: { connected: true, robot_state: '站立（力控）' } }
    const base: Lite3NextInput = { l, online: true, mine: true, holding: false, pose: 'standing', marks: { moving: false, low: true, estopAt: 0, selfSit: false }, endedReason: null, feedbackAge: 0.1 }
    expect(lite3Next(base).text).toBe('可以走了：按住右下角的方向键，松手即停')
    expect(lite3Next({ ...base, nav: null }).text).toBe('可以走了：按住右下角的方向键，松手即停')
    const run = lite3Next({ ...base, nav: { state: 'running', index: 1, count: 3, to_end_m: 118.4 } })
    expect(run.text).toBe('导航中 · 2/3 · 离终点 118 m')
    expect(run.fix?.key).toBe('l3navcancel')
    const paused = lite3Next({ ...base, nav: { state: 'paused', reason: 'takeover' } })
    expect(paused.text).toBe('导航暂停：人工接管')
    expect(paused.fix?.key).toBe('l3navresume')
    expect(lite3Next({ ...base, mine: false, nav: { state: 'running' } }).fix?.key).toBe('arm')
  })
})
