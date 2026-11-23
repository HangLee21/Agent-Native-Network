import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { setConfigForTest } from '@/config/runtime'
import { useTelemetryStore } from '@/stores/telemetry'
import { useControlStore } from '@/stores/control'
import { useExecutionStore } from '@/stores/execution'
import { useManualStore } from '@/stores/manual'
import { useTargetsStore } from '@/stores/targets'
import { useOverlaysStore } from '@/stores/overlays'
import { useLiveStore } from '@/stores/live'
import { useConfirmStore } from '@/stores/confirm'
import { useTasksStore } from '@/stores/tasks'
import SafetyFooter from '@/components/monitor/SafetyFooter.vue'
import PanelHeader from '@/components/monitor/PanelHeader.vue'
import HeightLimitControl from '@/components/monitor/HeightLimitControl.vue'
import StickTask from '@/components/monitor/tasks/StickTask.vue'
import OrbitTask from '@/components/monitor/tasks/OrbitTask.vue'
import CameraRail from '@/components/video/CameraRail.vue'
import type { TargetView } from '@/api/targets'
import { legacyPath, useTestDrone } from './testDrone'

/**
 * The redesigned monitor must not change any API (ui-design.md §2.2): every assertion below names the
 * exact method, path and body the former button sent. Since D-29 the calls go to the test drone's
 * /api/v1/drones/{sn}/… endpoint; `legacyPath` maps exactly that prefix back (any other drone stays visible).
 */
type Call = { method: string; path: string; body: unknown }
let calls: Call[] = []

function record(path: string) {
  return { id: `c${calls.length}`, type: path, label: path, channel: 'SERVICES', status: 'SENT', createdAt: 1, sentAt: 1, completedAt: null, resultCode: null, message: null }
}

function responseFor(path: string): unknown {
  if (path === '/api/v1/executions/current/abort') return { active: false, state: 'ABORTED', routeName: 'A', total: 2, reachedCount: 1, log: [], waypoints: [], mode: 'STOP_AND_GO', message: '' }
  if (path === '/api/v1/targets/active/stop') return { target: target({ state: 'ABORTED' }), decision: 'STOPPED', message: '', commandId: null }
  if (path === '/api/v1/targets/ai/stop') return { on: false }
  if (path.startsWith('/api/v1/manual/')) return { active: false, exiting: false, scale: 0.3, maxScale: 0.5, message: '', heightClamped: false, zoneBlocked: false, gimbalMoving: false, log: [] }
  if (path === '/api/v1/control/request') return { control: 'REQUESTING', message: '', drcState: 0, drcReady: false, drcRequested: false, heartbeatRttMs: -1, lastHeartbeatAckAt: 0, rcButtonsDisabled: false }
  return record(path)
}

function target(over: Partial<TargetView> = {}): TargetView {
  return {
    id: 't1', createdAt: 1, updatedAt: 1, source: 'OPERATOR', label: null, confidence: null, input: 'TAP',
    image: null, state: 'ACTIVE', method: 'LASER', lat: 22.58, lon: 113.94, ellipsoidHeight: 25, relativeHeight: 0, distance: 120,
    accuracyM: 0.8, laserState: 'NORMAL', rawAltitude: 25, altitudeReference: 'ELLIPSOID', geoidOffsetM: null, lowConfidence: false,
    zoomAtSelect: 2, message: null, warnings: [], action: 'APPROACH', suggestedAction: null, stopPoint: null, backPoint: null, commandId: null,
    check: null, expiresAt: null, ...over,
  } as TargetView
}

function online(modeCode: number, gatewayOnline = true): void {
  const tel = useTelemetryStore()
  tel.gateway = { mode: 'mock', gatewaySn: 'RC', droneSn: 'M4E', gatewayOnline, droneOnline: true, droneModel: null, rcModel: null }
  tel.lastUpdateAt = Date.now()
  tel.drone = { modeCode, relativeHeight: 40, horizontalSpeed: 0, heightLimit: 120 } as never
}

function granted(drcReady = true): void {
  useControlStore().snapshot = { control: 'GRANTED', message: '', drcState: drcReady ? 2 : 0, drcReady, drcRequested: true, heartbeatRttMs: 40, lastHeartbeatAckAt: 0, rcButtonsDisabled: true }
}

const sent = () => calls.filter((c) => c.method !== 'GET')
type AskFn = ReturnType<typeof useConfirmStore>['ask']

describe('redesigned monitor keeps every API call (ui-design.md §2.2)', () => {
  let ask: Mock<AskFn>

  beforeEach(() => {
    setActivePinia(createPinia())
    useTestDrone()
    setConfigForTest({ apiBaseUrl: 'http://api.test', wsUrl: '', map: { coordSys: 'WGS84', tileUrl: '', subdomains: '', attribution: '', maxZoom: 19, apiKey: '' } })
    calls = []
    vi.stubGlobal('fetch', vi.fn(async (url: string, init: RequestInit = {}) => {
      const path = legacyPath(String(url).replace('http://api.test', ''))
      calls.push({ method: init.method ?? 'GET', path, body: init.body ? JSON.parse(String(init.body)) : undefined })
      return new Response(JSON.stringify(responseFor(path)), { status: 200 })
    }))
    ask = vi.fn<AskFn>().mockResolvedValue(true)
    vi.spyOn(useConfirmStore(), 'ask').mockImplementation(ask)
  })

  afterEach(() => vi.unstubAllGlobals())

  it('the stop menu offers every stop, each with its original API', async () => {
    online(17)
    granted()
    useExecutionStore().current = { active: true } as never
    useTargetsStore().targets = [target()]
    useTargetsStore().ai = { on: true } as never
    useManualStore().snapshot = { active: true } as never
    const w = mount(SafetyFooter)
    const expected: Record<string, string> = {
      fly: '/api/v1/flight/fly-to/stop', orb: '/api/v1/flight/poi/exit', rte: '/api/v1/executions/current/abort',
      tgt: '/api/v1/targets/active/stop', ai: '/api/v1/targets/ai/stop', stk: '/api/v1/manual/stick/exit',
    }
    for (const [key, path] of Object.entries(expected)) {
      calls = []
      await w.find('[data-test=stop-menu-toggle]').trigger('click')
      await w.find(`[data-test=stop-${key}]`).trigger('click')
      await flushPromises()
      expect(sent()).toEqual([{ method: 'POST', path, body: undefined }])
    }
    // stopping a route keeps its confirmation, unchanged
    expect(ask).toHaveBeenCalledWith({ title: '停止执行', message: '将结束当前 flyto，飞机在当前位置悬停。确认停止？', confirmText: '停止', danger: true, focus: 'confirm' })
  })

  it('the main stop follows what moves the aircraft; idle it is the former 结束 flyto', async () => {
    online(3)
    granted()
    const w = mount(SafetyFooter)
    expect(w.find('[data-test=stop-main]').text()).toContain('停止 · 悬停')
    await w.find('[data-test=stop-main]').trigger('click')
    await flushPromises()
    expect(sent()).toEqual([{ method: 'POST', path: '/api/v1/flight/fly-to/stop', body: undefined }])

    useOverlaysStore().items = { target: { kind: 'target', data: {}, updatedAt: 2 } }
    online(17)
    await flushPromises()
    expect(w.find('[data-test=stop-main]').text()).toContain('结束飞往')
    useOverlaysStore().items = { target: { kind: 'target', data: {}, updatedAt: 2 }, poi: { kind: 'poi', data: {}, updatedAt: 3 } }
    await flushPromises()
    expect(w.find('[data-test=stop-main]').text()).toContain('退出环绕')
    useExecutionStore().current = { active: true } as never
    await flushPromises()
    expect(w.find('[data-test=stop-main]').text()).toContain('停止执行')
    useTargetsStore().targets = [target()]
    useTargetsStore().ai = { on: true } as never
    await flushPromises()
    expect(w.find('[data-test=stop-main]').text()).toContain('停止 AI')
  })

  it('a target orbit is ended with 退出环绕: the backend refuses 停止目标动作 for it (409)', async () => {
    online(17)
    granted()
    useTargetsStore().targets = [target({ action: 'ORBIT' })]
    const w = mount(SafetyFooter)
    expect(w.find('[data-test=stop-main]').text()).toContain('退出环绕 · 悬停')
    await w.find('[data-test=stop-main]').trigger('click')
    await flushPromises()
    expect(sent()).toEqual([{ method: 'POST', path: '/api/v1/flight/poi/exit', body: undefined }])
    // with AI on as well, the orbit is still what moves the aircraft; AI stays listed as still running
    useTargetsStore().ai = { on: true } as never
    await flushPromises()
    expect(w.find('[data-test=stop-main]').text()).toContain('退出环绕 · 悬停')
    expect(w.text()).toContain('AI 自动')
    // the explicit menu item keeps its own API
    calls = []
    await w.find('[data-test=stop-menu-toggle]').trigger('click')
    await w.find('[data-test=stop-tgt]').trigger('click')
    await flushPromises()
    expect(sent()).toEqual([{ method: 'POST', path: '/api/v1/targets/active/stop', body: undefined }])
  })

  it('take-off and return home share one place without changing their calls', async () => {
    online(0)
    const w = mount(SafetyFooter)
    expect(w.find('[data-test=takeoff]').exists()).toBe(true)
    expect(w.find('[data-test=return-home]').exists()).toBe(false)

    online(3)
    await flushPromises()
    await w.find('[data-test=return-home]').trigger('click')
    await flushPromises()
    expect(ask).toHaveBeenCalledWith({ title: '确认让 A 返航', message: '飞行器将按返航高度飞回 Home 点并降落。', confirmText: '返航', focus: 'confirm' })
    expect(sent()).toEqual([{ method: 'POST', path: '/api/v1/flight/return-home', body: undefined }])

    calls = []
    online(9)
    await flushPromises()
    await w.find('[data-test=cancel-return]').trigger('click')
    await flushPromises()
    expect(sent()).toEqual([{ method: 'POST', path: '/api/v1/flight/return-home/cancel', body: undefined }])

    // telemetry lost while the RC is online: return home stays reachable (never hidden behind take-off)
    useTelemetryStore().lastUpdateAt = 0
    useTelemetryStore().drone = { modeCode: 0 } as never
    await flushPromises()
    expect(w.find('[data-test=return-home]').exists()).toBe(true)
    expect(w.find('[data-test=takeoff]').exists()).toBe(false)
  })

  it('starting another moving task stops the running one first, with one confirmation', async () => {
    online(17)
    granted()
    useExecutionStore().current = { active: true } as never
    const tasks = useTasksStore()

    ask.mockResolvedValueOnce(false)
    await tasks.select('orb')
    expect(sent()).toEqual([])
    expect(tasks.selected).toBe('rte') // the running route's card opened by itself

    await tasks.select('orb')
    expect(ask).toHaveBeenLastCalledWith(expect.objectContaining({ title: '先停止航线执行，再开始环绕？', confirmText: '停止并开始环绕', danger: true }))
    expect(sent()).toEqual([{ method: 'POST', path: '/api/v1/executions/current/abort', body: undefined }])
    expect(tasks.selected).toBe('orb')
    expect(useControlStore().pickingTarget).toBe('poi')
  })

  it('panel header keeps control, DRC and release calls', async () => {
    online(0)
    const w = mount(PanelHeader, { global: { stubs: { RouterLink: true } } })
    await w.find('[data-test=request-control]').trigger('click')
    await flushPromises()
    expect(sent()).toEqual([{ method: 'POST', path: '/api/v1/control/request', body: undefined }])

    calls = []
    granted(false)
    await flushPromises()
    await w.find('[data-test=enter-drc]').trigger('click')
    await w.find('[data-test=panel-menu]').trigger('click')
    await w.find('[data-test=release-control]').trigger('click')
    await flushPromises()
    expect(sent()).toEqual([
      { method: 'POST', path: '/api/v1/control/drc/enter', body: undefined },
      { method: 'POST', path: '/api/v1/control/release', body: undefined },
    ])
    expect(w.find('[data-test=rc-disabled-hint]').exists()).toBe(true)
  })

  it('height limit, stick and orbit speed keep their calls', async () => {
    online(3)
    granted()
    const hl = mount(HeightLimitControl)
    await hl.find('[data-test=height-limit-set]').trigger('click')
    await flushPromises()
    expect(ask).toHaveBeenCalledWith({ title: '设置飞行器限高', message: '将飞行器自身限高（height_limit）设为 120 m？', confirmText: '设置' })

    const stick = mount(StickTask, { global: { stubs: { RouterLink: true } } })
    await stick.find('[data-test=stick-enter]').trigger('click')

    const orbit = mount(OrbitTask)
    await orbit.find('input[type=number]').setValue(-2)
    await orbit.find('[data-test=poi-speed]').trigger('click')
    await flushPromises()
    expect(sent()).toEqual([
      { method: 'PUT', path: '/api/v1/drone/height-limit', body: { value: 120 } },
      { method: 'POST', path: '/api/v1/manual/stick/enter', body: { scale: 0.3 } },
      { method: 'POST', path: '/api/v1/flight/poi/speed', body: { speed: -2 } },
    ])
  })

  it('camera rail keeps the payload, gimbal and video calls (and is locked without DRC)', async () => {
    online(3)
    granted()
    useLiveStore().status = { videoId: 'v', streaming: true, quality: 0, lens: 'wide', playback: { protocol: 'MOCK', url: null }, lenses: ['wide', 'zoom', 'ir'], pushConfigured: true }
    const w = mount(CameraRail)
    for (const sel of ['rail-photo', 'rail-record', 'rail-record-stop', 'zoom-in', 'lens-zoom', 'lens-thermal']) await w.find(`[data-test=${sel}]`).trigger('click')
    await w.find('[data-test=rail-gimbal]').trigger('click')
    for (const sel of ['gimbal-center', 'gimbal-down-preset', 'gimbal-yaw-center', 'gimbal-pitch-down']) await w.find(`[data-test=${sel}]`).trigger('click')
    await w.find('[data-test=rail-video]').trigger('click')
    await w.find('[data-test=rail-video-stop]').trigger('click')
    await flushPromises()
    expect(sent()).toEqual([
      { method: 'POST', path: '/api/v1/payload/photo', body: undefined },
      { method: 'POST', path: '/api/v1/payload/recording/start', body: undefined },
      { method: 'POST', path: '/api/v1/payload/recording/stop', body: undefined },
      { method: 'POST', path: '/api/v1/payload/zoom', body: { factor: 7, cameraType: 'zoom' } },
      { method: 'POST', path: '/api/v1/live/lens', body: { lens: 'zoom' } },
      { method: 'POST', path: '/api/v1/live/lens', body: { lens: 'thermal' } },
      { method: 'POST', path: '/api/v1/payload/gimbal/reset', body: { mode: 0 } },
      { method: 'POST', path: '/api/v1/payload/gimbal/reset', body: { mode: 1 } },
      { method: 'POST', path: '/api/v1/payload/gimbal/reset', body: { mode: 2 } },
      { method: 'POST', path: '/api/v1/payload/gimbal/reset', body: { mode: 3 } },
      { method: 'POST', path: '/api/v1/live/stop', body: undefined },
    ])

    calls = []
    useLiveStore().status = { ...useLiveStore().status!, streaming: false }
    useControlStore().snapshot = null
    await flushPromises()
    expect(w.find('[data-test=rail-photo]').attributes('disabled')).toBeDefined()
    await w.find('[data-test=rail-video]').trigger('click')
    await w.find('[data-test=rail-video-start]').trigger('click')
    await flushPromises()
    expect(sent()).toEqual([{ method: 'POST', path: '/api/v1/live/start', body: { quality: 0 } }])
  })
})
