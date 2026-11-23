/**
 * Lite3 navigation on the card, in the dialogs, in the safety row and on the target card (docs/dog/ui-design.md 19):
 * nothing new for a dog that cannot navigate; each state shows what it should; buttons are grey with the reason
 * while this page has no control; avoidance off is asked once and then flagged; no speed selector without levels;
 * the start dialog needs control, a passed check and "狗已站好". The backend is mocked.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { nextTick } from 'vue'
import Lite3Nav from '@/components/dog/Lite3Nav.vue'
import Lite3Body from '@/components/dog/Lite3Body.vue'
import DogNavConfirm from '@/components/dog/DogNavConfirm.vue'
import DogSafety from '@/components/dog/DogSafety.vue'
import TargetCard from '@/components/target/TargetCard.vue'
import { useDogStore } from '@/stores/dog'
import { useDog2Store } from '@/stores/dogv2'
import { dog2Api, NAV_SETTINGS_DEFAULT, type Dog2, type Dog2Nav, type Dog2NavCapability, type Dog2NavCheck } from '@/api/dogv2'
import type { TargetView } from '@/api/targets'
import { ApiError } from '@/api/http'
import { createMemoryHistory, createRouter } from 'vue-router'
import SettingsView from '@/views/SettingsView.vue'
import DogNavSettingsCard from '@/components/settings/DogNavSettingsCard.vue'
import { historyApi, type HistoryStatus } from '@/api/history'
import { resolveConfig, setConfigForTest } from '@/config/runtime'

vi.mock('@/api/dogv2', async (importOriginal) => {
  const real = await importOriginal<typeof import('@/api/dogv2')>()
  return {
    ...real,
    dog2Api: {
      ...real.dog2Api, list: vi.fn(), take: vi.fn(), release: vi.fn(), teleop: vi.fn(), command: vi.fn(),
      nav: vi.fn(), navPrepare: vi.fn(async () => ({ result: 'done' as const })), navCheck: vi.fn(), navStart: vi.fn(), navPause: vi.fn(), navResume: vi.fn(), navCancel: vi.fn(), navOptions: vi.fn(), navSettings: vi.fn(),
    },
    dogRoutesApi: { list: vi.fn(async () => []), get: vi.fn(), create: vi.fn(), update: vi.fn(), remove: vi.fn(), fromRoute: vi.fn() },
  }
})
const api = vi.mocked(dog2Api)

const CAP: Dog2NavCapability = {
  kind: 'gps', avoidance: true, speed_levels: [{ id: 'slow', mps: 0.12 }, { id: 'mid', mps: 0.2 }, { id: 'fast', mps: 0.3 }],
  default_speed: 'slow', arrive_radius_m: [1, 20], max_points: 200, dry_run: true,
}
const READY = { loc: true, nav2: true, lidar: true, gnss: 'fix', heading: 'imu_aligned' }
const PTS = [{ lat: 22.5801, lon: 113.9401, name: 'A' }, { lat: 22.5805, lon: 113.9405, name: '桥头' }, { lat: 22.581, lon: 113.941, name: 'C' }]
const OK: Dog2NavCheck = { ok: true, problems: [], area: null, areaSource: 'none', totalM: 0, firstM: 42 }
const RUNNING: Dog2Nav = {
  state: 'running', task_id: 'n1', index: 1, count: 3, to_point_m: 42.4, to_end_m: 118, eta_s: 980, speed_mps: 0.11, speed_level: 'slow',
  avoidance: true, front_m: 4.2, points: PTS, ready: READY, taskId: 'n1',
}

let current: Dog2[] = []
function dog(nav: Dog2Nav | null, extra: Partial<Dog2> = {}): Dog2 {
  return {
    id: 'lite3-01', label: 'Lite3', model: 'lite3', software: '0.2.0', online: true, enabled: true, mode: 'new', gateway: 'x',
    statusAgeMs: 100, telemetryAgeMs: 100, status: {}, position: { fix: 'single', lat: 22.58, lon: 113.94, heading_source: 'imu_aligned' }, positionAgeMs: 300,
    telemetry: { basic_state: 2, basic_state_name: '站立（力控）', battery_pct: 80, rpy: [0, 0, 0], vel_body: [0, 0, 0], feedback_age_s: 0.05 },
    control: { held: false, mine: false, session: null, endedReason: null }, video: {}, lastSeenAt: Date.now(), navCapability: CAP, nav, ...extra,
  }
}

/** Puts the dog list in both stores (the Lite3 card reads the bridged state). */
async function withDog(d: Dog2): Promise<void> {
  useDogStore()
  current = [d]
  useDog2Store().dogs = current
  await nextTick()
}
/** This page holds control of the dog (and the dog list says so, else the store would count control as lost). */
async function mine(): Promise<void> {
  const v2 = useDog2Store()
  current = current.map((d) => ({ ...d, control: { held: true, mine: true, session: 'web-1', endedReason: null } }))
  v2.dogs = current
  v2.hold.dog = 'lite3-01'
  v2.hold.session = 'web-1'
  await nextTick()
}
const settle = async () => {
  await new Promise((r) => setTimeout(r, 5))
  await flushPromises()
}

let wrappers: VueWrapper[] = []
function keep<T extends VueWrapper>(w: T): T {
  wrappers.push(w)
  return w
}

describe('Lite3 navigation area', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    api.list.mockImplementation(async () => ({ mode: 'mock', broker: true, dogs: structuredClone(current) }))
    api.nav.mockResolvedValue({ capability: CAP, settings: NAV_SETTINGS_DEFAULT, nav: null, task: null })
    api.navCheck.mockResolvedValue(OK)
  })
  afterEach(() => {
    wrappers.forEach((w) => w.unmount())
    wrappers = []
    vi.clearAllMocks()
  })

  it('a dog that cannot navigate gets nothing new: no area, no end-navigation button', async () => {
    await withDog(dog(null, { navCapability: null }))
    const body = keep(mount(Lite3Body))
    expect(body.find('[data-test=lite3-nav]').exists()).toBe(false)
    const safe = keep(mount(DogSafety, { props: { dog: 'lite3', variant: 'card', selected: false } }))
    expect(safe.find('.caret').exists()).toBe(false)
    expect(safe.find('[data-test=dog-nav-end]').exists()).toBe(false)
    expect(api.nav).not.toHaveBeenCalled()
    expect(api.navPrepare).not.toHaveBeenCalled()
  })

  it('idle: the readiness line says which item is missing; opening the area asks for the dog\'s settings', async () => {
    await withDog(dog({ state: 'idle', ready: { ...READY, heading: 'course', lidar: null } }))
    const w = keep(mount(Lite3Body))
    await settle()
    expect(api.nav).toHaveBeenCalledWith('lite3-01')
    expect(api.navPrepare).toHaveBeenCalledWith('lite3-01')
    const nav = w.get('[data-test=lite3-nav]')
    expect(nav.get('[data-test=nav-state]').text()).toBe('空闲')
    const ready = nav.get('[data-test=nav-ready]').text()
    expect(ready).toContain('GPS ✓')
    expect(ready).toContain('朝向 ✕')
    expect(ready).toContain('避障雷达 –')
    expect(nav.get('[data-test=nav-ready-why]').text()).toBe('朝向没对齐：用按住移动沿一个方向直走 15 米以上，中途别按转向键')
    // the groups keep their order: preparation, navigation, then the data groups
    const order = ['lite3-prep', 'lite3-nav', 'lite3-motion', 'lite3-position', 'lite3-board'].map((id) => w.html().indexOf(`dog-sec-${id}`))
    expect(order.every((x, i) => x >= 0 && (i === 0 || x > order[i - 1]!))).toBe(true)
  })

  it('running: point i/n, distances, ETA; pause and end are grey with the reason until this page holds control', async () => {
    await withDog(dog(RUNNING))
    const w = keep(mount(Lite3Body))
    await settle()
    // a task on: the navigation group stays where it is (after preparation)
    expect(w.html().indexOf('dog-sec-lite3-nav')).toBeGreaterThan(w.html().indexOf('dog-sec-lite3-prep'))
    const nav = w.get('[data-test=lite3-nav]')
    // the task's buttons are the first row under the state, above the progress (pausing does not move them)
    expect(nav.html().indexOf('nav-pause')).toBeLessThan(nav.html().indexOf('nav-progress'))
    expect(nav.get('[data-test=nav-state]').text()).toBe('走着')
    expect(nav.get('[data-test=nav-progress]').text()).toBe('走向第 2/3 个点（桥头）')
    expect(nav.text()).toContain('离这个点 42 m · 离终点 118 m · 约 16 分钟')
    expect(nav.text()).toContain('速度 0.11 m/s · 前方 4.2 m')
    const pause = nav.get('[data-test=nav-pause]')
    expect(pause.attributes('disabled')).toBeDefined()
    expect(pause.attributes('title')).toBe('先「取得控制」')
    expect(nav.find('[data-test=nav-start]').exists()).toBe(false)

    await mine()
    expect(pause.attributes('disabled')).toBeUndefined()
    api.navPause.mockResolvedValue({ result: 'done' })
    await pause.trigger('click')
    await flushPromises()
    expect(api.navPause).toHaveBeenCalledWith('lite3-01')
    api.navCancel.mockResolvedValue({ result: 'done' })
    await nav.get('[data-test=nav-cancel]').trigger('click')
    await flushPromises()
    expect(api.navCancel).toHaveBeenCalledWith('lite3-01')
  })

  it('paused by an obstacle: the reason, what to do, resume and "turn avoidance off"', async () => {
    await withDog(dog({ ...RUNNING, state: 'paused', reason: 'blocked', reason_text: '前方 0.5 m 有东西，停了 20 秒' }))
    await mine()
    const w = keep(mount(Lite3Nav))
    await settle()
    expect(w.get('[data-test=nav-state]').text()).toBe('暂停')
    const r = w.get('[data-test=nav-reason]').text()
    expect(r).toContain('暂停：前方有障碍，绕不过去')
    expect(r).toContain('前方 0.5 m 有东西，停了 20 秒')
    expect(r).toContain('绕开障碍后「继续」、关掉避障，或按住方向键接管')
    expect(r).toContain('按住方向键可以接管')
    expect(w.find('[data-test=nav-pause]').exists()).toBe(false)
    api.navResume.mockResolvedValue({ result: 'done' })
    await w.get('[data-test=nav-resume]').trigger('click')
    await flushPromises()
    expect(api.navResume).toHaveBeenCalledWith('lite3-01')
    expect(w.find('[data-test=nav-avoid-off-now]').exists()).toBe(true)
  })

  it('an unknown pause reason is shown as the dog wrote it', async () => {
    await withDog(dog({ ...RUNNING, state: 'paused', reason: 'battery_low', reason_text: '电量低于 25%' }))
    const w = keep(mount(Lite3Nav))
    expect(w.get('[data-test=nav-reason]').text()).toContain('暂停：电量低于 25%')
    expect(w.find('[data-test=nav-avoid-off-now]').exists()).toBe(false)
  })

  it('avoidance off: asked once with the fact, then "避障关" on the card; on again without asking', async () => {
    await withDog(dog({ state: 'idle', ready: READY }))
    const w = keep(mount(Lite3Nav))
    const dlg = keep(mount(DogNavConfirm, { attachTo: document.body }))
    await settle()
    expect(w.find('[data-test=nav-avoid-off]').exists()).toBe(false)
    await w.get('[data-test=nav-avoid]').trigger('click')
    await nextTick()
    expect(dlg.text()).toContain('关掉以后，狗不绕障碍，也不会因为障碍停下。')
    await dlg.get('[data-test=nav-dlg-avoid-off]').trigger('click')
    await flushPromises()
    expect(w.find('[data-test=nav-avoid-off]').exists()).toBe(true)
    expect(api.navOptions).not.toHaveBeenCalled()    // no task: kept for the next start

    await w.get('[data-test=nav-avoid]').trigger('click')
    await flushPromises()
    expect(useDog2Store().navDialog).toBeNull()
    expect(w.find('[data-test=nav-avoid-off]').exists()).toBe(false)
  })

  it('walking with avoidance off: "避障关" from the dog\'s own word', async () => {
    await withDog(dog({ ...RUNNING, avoidance: false }))
    const w = keep(mount(Lite3Nav))
    expect(w.find('[data-test=nav-avoid-off]').exists()).toBe(true)
    expect(w.text()).not.toContain('前方 4.2 m')
  })

  it('speed levels: the ones the dog reports; none at all when it reports none', async () => {
    await withDog(dog(RUNNING))
    await mine()
    const w = keep(mount(Lite3Nav))
    const seg = w.get('[data-test=nav-speed]')
    expect(seg.findAll('button').map((b) => b.text())).toEqual(['慢 0.12 m/s', '中 0.2 m/s', '快 0.3 m/s'])
    expect(seg.find('button.on').text()).toBe('慢 0.12 m/s')
    api.navOptions.mockResolvedValue({ result: 'done' })
    await seg.findAll('button')[1]!.trigger('click')
    await flushPromises()
    expect(api.navOptions).toHaveBeenCalledWith('lite3-01', { speedLevel: 'mid' })
    w.unmount()

    await withDog(dog(RUNNING, { navCapability: { ...CAP, speed_levels: [] } }))
    const w2 = keep(mount(Lite3Nav))
    expect(w2.find('[data-test=nav-speed]').exists()).toBe(false)
  })

  it('typed-in speed: only when the dog reports its limit; Enter sends it while walking, out of range says so', async () => {
    await withDog(dog(RUNNING))
    await mine()
    const w = keep(mount(Lite3Nav))
    expect(w.find('[data-test=nav-speed-custom]').exists()).toBe(false)     // CAP has no speed_max_mps
    w.unmount()

    await withDog(dog(RUNNING, { navCapability: { ...CAP, speed_max_mps: 1.0 } }))
    const w2 = keep(mount(Lite3Nav))
    const box = w2.get('[data-test=nav-speed-input]')
    api.navOptions.mockResolvedValue({ result: 'done' })
    await box.setValue('1.5')
    await box.trigger('keydown', { key: 'Enter' })
    expect(w2.get('[data-test=nav-speed-bad]').text()).toBe('速度要在 0.05 ~ 1 m/s 之间')
    expect(api.navOptions).not.toHaveBeenCalled()
    await box.setValue('0.8')
    await box.trigger('keydown', { key: 'Enter' })
    await flushPromises()
    expect(api.navOptions).toHaveBeenCalledWith('lite3-01', { speedMps: 0.8 })
    w2.unmount()

    // the dog walking at a typed-in speed: the box is the active choice and shows it, no level is lit
    await withDog(dog({ ...RUNNING, speed_level: 'custom', speed_target_mps: 0.8 }, { navCapability: { ...CAP, speed_max_mps: 1.0 } }))
    const w3 = keep(mount(Lite3Nav))
    expect(w3.get('[data-test=nav-speed-custom]').classes()).toContain('on')
    expect((w3.get('[data-test=nav-speed-input]').element as HTMLInputElement).value).toBe('0.8')
    expect(w3.get('[data-test=nav-speed]').find('button.on').exists()).toBe(false)
  })

  it('start: grey until there are points, the check passed and this page holds control; problems are listed', async () => {
    await withDog(dog({ state: 'idle', ready: READY }))
    const w = keep(mount(Lite3Nav))
    await settle()
    const start = () => w.get('[data-test=nav-start]')
    expect(start().attributes('title')).toBe('先「取得控制」')
    await mine()
    expect(start().attributes('title')).toBe('先在地图上点目标或画路线')

    api.navCheck.mockResolvedValueOnce({ ...OK, ok: false, problems: [{ code: 'outside_area', text: '点在允许区域外', index: 1 }, { code: 'too_far', text: '第一个点离狗太远' }] })
    useDog2Store().draftOpen('lite3-01', PTS.slice(0, 2))
    await settle()
    expect(w.get('[data-test=nav-problems]').text()).toContain('第 2 个点：点在允许区域外')
    expect(w.get('[data-test=nav-problems]').text()).toContain('第一个点离狗太远')
    expect(start().attributes('disabled')).toBeDefined()
    expect(start().attributes('title')).toBe('点在允许区域外')

    useDog2Store().draftMove(1, PTS[2]!)
    await new Promise((r) => setTimeout(r, 320))
    await flushPromises()
    expect(w.find('[data-test=nav-problems]').exists()).toBe(false)
    expect(start().attributes('disabled')).toBeUndefined()
    expect(w.get('[data-test=nav-draft]').text()).toContain('2 个点 · 总长 0 m · 第一个点离狗 42 m')
    await start().trigger('click')
    expect(useDog2Store().navDialog).toMatchObject({ kind: 'start', dog: 'lite3-01', points: [PTS[0], { ...PTS[1], lat: PTS[2]!.lat, lon: PTS[2]!.lon }] })
  })

  it('arrived and ended are shown while idle', async () => {
    await withDog(dog({ state: 'arrived', count: 3, ready: READY }))
    const w = keep(mount(Lite3Nav))
    expect(w.get('[data-test=nav-last]').text()).toBe('到了 · 共 3 个点')
    w.unmount()
    await withDog(dog({ state: 'ended', reason: 'link_lost', ready: READY }))
    const w2 = keep(mount(Lite3Nav))
    expect(w2.get('[data-test=nav-last]').text()).toBe('结束：和平台断开')
  })
})

describe('start dialog', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    api.list.mockImplementation(async () => ({ mode: 'mock', broker: true, dogs: structuredClone(current) }))
    api.nav.mockResolvedValue({ capability: CAP, settings: { ...NAV_SETTINGS_DEFAULT, arriveRadiusM: 4 }, nav: null, task: null })
    api.navCheck.mockResolvedValue(OK)
  })
  afterEach(() => {
    wrappers.forEach((w) => w.unmount())
    wrappers = []
    vi.clearAllMocks()
  })

  async function open(points = [PTS[1]!], extra = {}): Promise<{ w: VueWrapper; done: Promise<boolean> }> {
    const w = keep(mount(DogNavConfirm, { attachTo: document.body }))
    const done = useDog2Store().askStart('lite3-01', points, extra)
    await settle()
    return { w, done }
  }

  it('needs control, a passed check and "狗已站好"; sends the chosen options and closes on the dog\'s yes', async () => {
    await withDog(dog({ state: 'idle', ready: READY }))
    const { w, done } = await open()
    expect(api.navCheck).toHaveBeenCalledWith('lite3-01', [PTS[1]])
    expect(w.get('[data-test=nav-dlg-points]').text()).toBe('1 个点（桥头）· 离狗 42 m')
    expect(w.text()).toContain('没设：只限第一个点离狗不超过 300 m')
    const go = () => w.get('[data-test=nav-dlg-start]')
    expect(go().attributes('title')).toBe('先「取得控制」')
    await mine()
    expect(go().attributes('title')).toBe('先勾「狗已站好」')
    await w.get('[data-test=nav-dlg-standing]').setValue(true)
    expect(go().attributes('disabled')).toBeUndefined()
    expect((w.get('[data-test=nav-dlg-radius]').element as HTMLInputElement).value).toBe('4')

    api.navStart.mockResolvedValue({ result: 'done', taskId: 'n2' })
    await go().trigger('click')
    await flushPromises()
    expect(api.navStart).toHaveBeenCalledWith('lite3-01', { points: [PTS[1]], avoidance: true, arriveRadiusM: 4, standingConfirmed: true, speedLevel: 'slow' })
    expect(await done).toBe(true)
    expect(w.find('[data-test=dog-nav-dialog]').exists()).toBe(false)
  })

  it('a typed-in speed chosen on the card is the dialog\'s choice and is sent instead of a level', async () => {
    await withDog(dog({ state: 'idle', ready: READY }, { navCapability: { ...CAP, speed_max_mps: 1.0 } }))
    useDog2Store().navNext['lite3-01'] = { avoidance: null, speedLevel: null, speedMps: 0.6 }
    const { w } = await open()
    await mine()
    expect((w.get('[data-test=nav-dlg-custom] input[type=radio]').element as HTMLInputElement).checked).toBe(true)
    await w.get('[data-test=nav-dlg-standing]').setValue(true)
    api.navStart.mockResolvedValue({ result: 'done', taskId: 'n3' })
    await w.get('[data-test=nav-dlg-start]').trigger('click')
    await flushPromises()
    expect(api.navStart).toHaveBeenCalledWith('lite3-01', { points: [PTS[1]], avoidance: true, arriveRadiusM: 4, standingConfirmed: true, speedMps: 0.6 })
  })

  it('avoidance off in the dialog states the fact; no speed row and no level sent when the dog reports none', async () => {
    await withDog(dog({ state: 'idle', ready: READY }, { navCapability: { ...CAP, speed_levels: [] } }))
    await mine()
    const { w } = await open(PTS)
    expect(w.find('[data-test=nav-dlg-speed]').exists()).toBe(false)
    await w.get('[data-test=nav-dlg-avoid]').setValue(false)
    expect(w.get('[data-test=nav-dlg-avoid-fact]').text()).toBe('关掉以后，狗不绕障碍，也不会因为障碍停下。')
    await w.get('[data-test=nav-dlg-standing]').setValue(true)
    api.navStart.mockResolvedValue({ result: 'done' })
    await w.get('[data-test=nav-dlg-start]').trigger('click')
    await flushPromises()
    const body = api.navStart.mock.calls[0]![1]
    expect(body.avoidance).toBe(false)
    expect('speedLevel' in body).toBe(false)
  })

  it('a check that did not pass keeps start grey and lists the problems', async () => {
    await withDog(dog({ state: 'idle', ready: READY }))
    await mine()
    api.navCheck.mockResolvedValue({ ...OK, ok: false, problems: [{ code: 'outside_area', text: '点在允许区域外', index: 0 }] })
    const { w } = await open()
    await w.get('[data-test=nav-dlg-standing]').setValue(true)
    expect(w.get('[data-test=nav-dlg-problems]').text()).toBe('第 1 个点：点在允许区域外')
    expect(w.get('[data-test=nav-dlg-start]').attributes('disabled')).toBeDefined()
  })

  it('the platform\'s 400 and the dog\'s refusal are shown in the dialog, which stays open', async () => {
    await withDog(dog({ state: 'idle', ready: { ...READY, gnss: 'none' } }))
    await mine()
    const { w, done } = await open()
    expect(w.get('[data-test=nav-dlg-ready]').text()).toContain('GPS：没定位')
    await w.get('[data-test=nav-dlg-standing]').setValue(true)
    api.navStart.mockRejectedValueOnce(new ApiError('检查没通过', 400, { error: '检查没通过', code: 'too_far', problems: [{ code: 'too_far', text: '第一个点离狗 420 m', index: 0 }] }))
    await w.get('[data-test=nav-dlg-start]').trigger('click')
    await flushPromises()
    expect(w.get('[data-test=nav-dlg-answer]').text()).toContain('第 1 个点：第一个点离狗 420 m')

    api.navStart.mockResolvedValueOnce({ result: 'rejected', code: 'gnss_poor', text: 'GPS 没定位' })
    await w.get('[data-test=nav-dlg-start]').trigger('click')
    await flushPromises()
    expect(w.get('[data-test=nav-dlg-answer]').text()).toBe('狗没执行：GPS 没定位')
    expect(w.get('[data-test=nav-dlg-cancel]').text()).toBe('关闭')
    await w.get('[data-test=nav-dlg-cancel]').trigger('click')
    expect(await done).toBe(false)
  })

  it('"只算不走" from the engineering page is sent as dryRun', async () => {
    await withDog(dog({ state: 'idle', ready: READY }))
    await mine()
    const { w } = await open([PTS[0]!], { dryRun: true })
    expect(w.text()).toContain('狗照常规划，不动')
    await w.get('[data-test=nav-dlg-standing]').setValue(true)
    api.navStart.mockResolvedValue({ result: 'done' })
    await w.get('[data-test=nav-dlg-start]').trigger('click')
    await flushPromises()
    expect(api.navStart.mock.calls[0]![1]).toMatchObject({ dryRun: true })
  })
})

describe('safety row and target card', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    api.list.mockImplementation(async () => ({ mode: 'mock', broker: true, dogs: structuredClone(current) }))
    api.nav.mockResolvedValue({ capability: CAP, settings: NAV_SETTINGS_DEFAULT, nav: null, task: null })
    api.navCheck.mockResolvedValue(OK)
  })
  afterEach(() => {
    wrappers.forEach((w) => w.unmount())
    wrappers = []
    vi.clearAllMocks()
  })

  it('the safety row gets "结束导航" (in the menu next to 停止) while a task is on; grey with the reason without control', async () => {
    await withDog(dog(RUNNING))
    const w = keep(mount(DogSafety, { props: { dog: 'lite3', variant: 'card', selected: false } }))
    // stop and soft stop keep their places; the end of the navigation is in the ▾ menu, as for the S10
    expect(w.findAll('.acts > *').length).toBe(3)
    await w.get('.caret').trigger('click')
    const end = w.get('[data-test=dog-nav-end]')
    expect(end.attributes('disabled')).toBeDefined()
    expect(end.attributes('title')).toBe('由别处控制：按「停止」也会结束导航')
    await mine()
    expect(w.text()).toContain('导航中 · 2/3')
    api.navCancel.mockResolvedValue({ result: 'done' })
    await w.get('[data-test=dog-nav-end]').trigger('click')
    await flushPromises()
    expect(api.navCancel).toHaveBeenCalledWith('lite3-01')
    expect(w.find('[data-test=dog-nav-menu]').exists()).toBe(false)

    current = [dog({ state: 'idle', ready: READY })]
    useDog2Store().dogs = current
    await nextTick()
    expect(w.find('.caret').exists()).toBe(false)
    expect(w.findAll('.acts > *').length).toBe(2)
  })

  function target(): TargetView {
    return {
      id: 't1', createdAt: 1, updatedAt: 1, source: 'OPERATOR', label: '红色箱子', confidence: null, input: 'TAP',
      image: { lens: 'wide', x: 0.5, y: 0.8, w: 0, h: 0, frameTimestamp: null }, state: 'MEASURED', method: 'LASER',
      lat: 22.58, lon: 113.94, ellipsoidHeight: 25, relativeHeight: 0, distance: 120, accuracyM: 0.8, laserState: 'NORMAL',
      rawAltitude: 25, altitudeReference: 'ELLIPSOID', geoidOffsetM: null, lowConfidence: false, zoomAtSelect: 2, message: null,
      warnings: [], action: null, suggestedAction: null, stopPoint: null, backPoint: null, commandId: null, check: null, expiresAt: null,
    }
  }

  it('"让狗过去" only while this page controls a dog that can navigate; it opens the start dialog with the target', async () => {
    await withDog(dog(null, { navCapability: null }))
    await mine()
    const w = keep(mount(TargetCard, { props: { target: target() } }))
    expect(w.find('[data-test=target-send-dog]').exists()).toBe(false)

    current = [dog({ state: 'idle', ready: READY })]
    useDog2Store().dogs = current
    useDog2Store().hold.session = null
    await nextTick()
    expect(w.find('[data-test=target-send-dog]').exists()).toBe(false)
    await mine()
    await w.get('[data-test=target-send-dog]').trigger('click')
    expect(useDog2Store().navDialog).toMatchObject({ kind: 'start', dog: 'lite3-01', points: [{ lat: 22.58, lon: 113.94, name: '红色箱子' }], source: '红色箱子' })
  })
})

describe('settings: 狗的导航', () => {
  beforeEach(() => {
    localStorage.clear()
    globalThis.ResizeObserver ??= class {
      observe() {}
      disconnect() {}
    } as unknown as typeof ResizeObserver
    setConfigForTest(resolveConfig({}, 'http://x'))
    setActivePinia(createPinia())
    api.list.mockImplementation(async () => ({ mode: 'mock', broker: true, dogs: structuredClone(current) }))
    api.nav.mockResolvedValue({ capability: CAP, settings: NAV_SETTINGS_DEFAULT, nav: null, task: null })
  })
  afterEach(() => {
    wrappers.forEach((w) => w.unmount())
    wrappers = []
    vi.restoreAllMocks()
    vi.clearAllMocks()
  })

  async function settings(): Promise<VueWrapper> {
    const status = { recorder: { enabled: true, paused: false, pausedMessage: null, queueSize: 0, droppedTotal: 0, pendingRows: 0, currentSessionId: null },
      video: { configured: true, recordingEnabled: true, diskLow: false, freeBytes: 1e10, minFreeBytes: 5e9, transcode: false, autoStartStream: true, recordQuality: 1 },
      sessions: 0, samples: 0 } as HistoryStatus
    vi.spyOn(historyApi, 'status').mockResolvedValue(status)
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/settings', component: SettingsView }] })
    await router.push('/settings')
    await router.isReady()
    const w = keep(mount(SettingsView, { global: { plugins: [router] }, attachTo: document.body }))
    await flushPromises()
    return w
  }

  it('the section is listed only when a dog can navigate', async () => {
    current = [dog(null, { navCapability: null })]
    const w = await settings()
    expect(w.find('[data-test=settings-nav-dognav]').exists()).toBe(false)
    w.unmount()
    current = [dog({ state: 'idle' })]
    const w2 = await settings()
    expect(w2.get('[data-test=settings-nav-dognav]').text()).toContain('狗的导航')
  })

  it('one dog\'s defaults: loaded, edited within the dog\'s range, saved in one request', async () => {
    api.nav.mockResolvedValue({ capability: CAP, settings: { ...NAV_SETTINGS_DEFAULT, speedLevel: 'mid' }, nav: null, task: null })
    const w = keep(mount(DogNavSettingsCard, { props: { dog: dog({ state: 'idle' }) }, attachTo: document.body }))
    await settle()
    expect((w.get('[data-test=dog-nav-speed]').element as HTMLSelectElement).value).toBe('mid')
    expect(w.get('[data-test=dog-nav-speed]').findAll('option').map((o) => o.text())).toEqual(['狗的默认档', '慢 0.12 m/s', '中 0.2 m/s', '快 0.3 m/s'])
    const save = () => w.get('[data-test=dog-nav-save]')
    expect(save().attributes('disabled')).toBeDefined()
    await w.get('[data-test=dog-nav-radius]').setValue(30)
    expect(w.text()).toContain('到达半径要在 1–20 m 之间')
    expect(save().attributes('disabled')).toBeDefined()
    await w.get('[data-test=dog-nav-radius]').setValue(5)
    await w.get('[data-test=dog-nav-avoid-default]').setValue(false)
    api.navSettings.mockImplementation(async (_id, body) => body)
    await save().trigger('click')
    await flushPromises()
    expect(api.navSettings).toHaveBeenCalledWith('lite3-01', { avoidanceDefault: false, arriveRadiusM: 5, speedLevel: 'mid', area: null, useAircraftZone: true, maxFirstM: 300 })
    expect(w.get('[data-test=dog-nav-msg]').text()).toBe('已保存')
  })

  it('no default speed selector when the dog reports no levels', async () => {
    const w = keep(mount(DogNavSettingsCard, { props: { dog: dog({ state: 'idle' }, { navCapability: { ...CAP, speed_levels: [] } }) }, attachTo: document.body }))
    await settle()
    expect(w.find('[data-test=dog-nav-speed]').exists()).toBe(false)
  })
})
