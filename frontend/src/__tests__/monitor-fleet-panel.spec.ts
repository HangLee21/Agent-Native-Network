import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { setConfigForTest } from '@/config/runtime'
import { useTelemetryStore } from '@/stores/telemetry'
import { useControlStore } from '@/stores/control'
import { useExecutionStore } from '@/stores/execution'
import { useConfirmStore } from '@/stores/confirm'
import { useFleetStore } from '@/stores/fleet'
import { useFlightActions } from '@/composables/useFlightActions'
import { useFlightPhase } from '@/composables/useFlightPhase'
import SafetyFooter from '@/components/monitor/SafetyFooter.vue'
import MonitorRail from '@/components/monitor/MonitorRail.vue'
import HoldButton from '@/components/control/HoldButton.vue'
import type { ProximityPair } from '@/api/drones'
import { device, legacyPath, TEST_DRONE, useTestDrone } from './testDrone'

/**
 * The side panel with every drone's card at the bottom (ui-design.md §2.2): each card's safety buttons call that
 * drone's own, unchanged API with the same confirmation, also while another drone is selected (R-28); the phase bar
 * and the "what next" hint follow the drone's state. A is the selected test drone, B the other one.
 */
const B = 'RC-B'
type Call = { method: string; path: string; body: unknown }
let calls: Call[] = []
const sent = () => calls.filter((c) => c.method !== 'GET')

function responseFor(path: string): unknown {
  if (path.endsWith('/executions/current/resume')) return { active: true, state: 'EXECUTING', routeName: 'R', total: 3, reachedCount: 1, log: [], waypoints: [], mode: 'STOP_AND_GO', message: '' }
  return { id: `c${calls.length}`, type: path, label: path, channel: 'SERVICES', status: 'SENT', createdAt: 1, sentAt: 1, completedAt: null, resultCode: null, message: null }
}

function online(sn: string, modeCode: number): void {
  const tel = useTelemetryStore(sn)
  tel.gateway = { mode: 'mock', gatewaySn: sn, droneSn: `M4E-${sn}`, gatewayOnline: true, droneOnline: true, droneModel: null, rcModel: null }
  tel.lastUpdateAt = Date.now()
  tel.now = Date.now()
  tel.drone = { modeCode, relativeHeight: 40, horizontalSpeed: 0, batteryPercent: 80, heightLimit: 120 } as never
}

function granted(sn: string, drcReady = true): void {
  useControlStore(sn).snapshot = { control: 'GRANTED', message: '', drcState: drcReady ? 2 : 0, drcReady, drcRequested: true, heartbeatRttMs: 40, lastHeartbeatAckAt: 0, rcButtonsDisabled: true }
}

function pausedByProximity(sn: string): void {
  useExecutionStore(sn).current = { active: true, state: 'PAUSED', pauseReason: 'PROXIMITY', reachedCount: 1, total: 3 } as never
}

const cardOf = (w: VueWrapper, sn: string) => w.find(`[data-test=fleet-card][data-sn="${sn}"]`)
type AskFn = ReturnType<typeof useConfirmStore>['ask']

describe('side panel: every drone keeps its safety buttons (R-28, S-05)', () => {
  let ask: Mock<AskFn>

  beforeEach(() => {
    setActivePinia(createPinia())
    useTestDrone(device({ gatewaySn: B, droneSn: 'M4E-B', label: 'B', color: '#D85A30' }))
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

  it("B's card returns, stops and resumes B while A is selected", async () => {
    online(TEST_DRONE, 3)
    granted(TEST_DRONE)
    online(B, 3)
    granted(B)
    pausedByProximity(B)
    const w = mount(SafetyFooter, { global: { stubs: { RouterLink: true } } })

    // A (selected) keeps the former footer's button names; B's carry its name
    expect(cardOf(w, TEST_DRONE).find('[data-test=return-home]').exists()).toBe(true)
    expect(cardOf(w, TEST_DRONE).find('[data-test=estop]').text()).toContain('急停 A')
    expect(w.find('[data-test=stop-main]').text()).toContain('A')

    await cardOf(w, B).find('[data-test=fleet-rth]').trigger('click')
    await flushPromises()
    expect(ask).toHaveBeenCalledWith({ title: '确认让 B 返航', message: '飞行器将按返航高度飞回 Home 点并降落。', confirmText: '返航', focus: 'confirm' })
    cardOf(w, B).findComponent(HoldButton).vm.$emit('trigger')
    await flushPromises()
    expect(cardOf(w, B).find('[data-test=fleet-resume]').text()).toBe('继续 B 的航线')
    await cardOf(w, B).find('[data-test=fleet-resume]').trigger('click')
    await flushPromises()
    expect(sent()).toEqual([
      { method: 'POST', path: '/api/v1/drones/RC-B/flight/return-home', body: undefined },
      { method: 'POST', path: '/api/v1/drones/RC-B/flight/emergency-stop', body: undefined },
      { method: 'POST', path: '/api/v1/drones/RC-B/executions/current/resume', body: undefined },
    ])
    expect(useFleetStore().selectedSn).toBe(TEST_DRONE) // none of them changed the selection
  })

  it("take-off on B's card selects B and opens B's take-off confirmation, without sending anything", async () => {
    online(TEST_DRONE, 3)
    online(B, 0)
    const w = mount(SafetyFooter, { global: { stubs: { RouterLink: true } } })
    await cardOf(w, B).find('[data-test=fleet-takeoff]').trigger('click')
    await flushPromises()
    expect(useFleetStore().selectedSn).toBe(B)
    expect(useFlightActions(B).takeoffOpen.value).toBe(true)
    expect(useFlightActions(TEST_DRONE).takeoffOpen.value).toBe(false)
    expect(sent()).toEqual([])
  })

  it('the emergency stop is locked without DRC and says why', () => {
    online(B, 3)
    granted(B, false)
    const w = mount(SafetyFooter, { global: { stubs: { RouterLink: true } } })
    const hold = cardOf(w, B).find('[data-test=fleet-estop]')
    expect(hold.attributes('disabled')).toBeDefined()
    expect(hold.text()).toContain('DRC 未连接')
  })

  it('shows the distance of the two drones; amber / red while the proximity monitor reports them', async () => {
    online(TEST_DRONE, 3)
    online(B, 3)
    useTelemetryStore(TEST_DRONE).drone = { modeCode: 3, lat: 22.58, lon: 113.94, ellipsoidHeight: 60 } as never
    useTelemetryStore(B).drone = { modeCode: 3, lat: 22.58, lon: 113.9402, ellipsoidHeight: 66 } as never
    const w = mount(SafetyFooter, { global: { stubs: { RouterLink: true } } })
    expect(w.find('[data-test=pair-distance]').text().replace(/\s+/g, ' ')).toBe('A ↔ B 水平 21 m · 高度差 6 m')
    useFleetStore().proximity = [{ a: 'M4E-T', b: 'M4E-B', aLabel: 'A', bLabel: 'B', horizontalM: 12, verticalM: 3, level: 'hold', active: true } as ProximityPair]
    await flushPromises()
    expect(w.find('[data-test=pair-distance]').classes()).toContain('danger')
    expect(w.find('[data-test=pair-distance]').text()).toContain('靠近')
  })

  it("the collapsed rail keeps both drones' return home and emergency stop", async () => {
    online(TEST_DRONE, 3)
    granted(TEST_DRONE)
    online(B, 3)
    granted(B)
    const w = mount(MonitorRail)
    const b = w.find(`[data-test=rail-drone][data-sn="${B}"]`)
    await b.find('[data-test=rail-rth]').trigger('click')
    await flushPromises()
    b.findComponent(HoldButton).vm.$emit('trigger')
    await flushPromises()
    expect(ask).toHaveBeenCalledWith(expect.objectContaining({ title: '确认让 B 返航' }))
    expect(sent()).toEqual([
      { method: 'POST', path: '/api/v1/drones/RC-B/flight/return-home', body: undefined },
      { method: 'POST', path: '/api/v1/drones/RC-B/flight/emergency-stop', body: undefined },
    ])
    expect(w.findAll('[data-test=rail-estop]')).toHaveLength(2)
  })
})

describe('phase bar and next-step hint (ui-design.md §2.2)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    useTestDrone(device({ gatewaySn: B, droneSn: 'M4E-B', label: 'B' }))
  })

  const cur = (sn: string) => useFlightPhase(sn).steps.value.find((s) => s.cur)!

  it('follows connection, control and DRC on the ground', () => {
    expect(cur(TEST_DRONE).label).toBe('未连接')
    online(TEST_DRONE, 0)
    expect(cur(TEST_DRONE).label).toBe('控制权')
    expect(useFlightPhase(TEST_DRONE).hint.value?.text).toContain('申请控制权')
    granted(TEST_DRONE, false)
    expect(cur(TEST_DRONE).label).toBe('DRC 未连接')
    expect(useFlightPhase(TEST_DRONE).hint.value?.text).toContain('进入 DRC')
    granted(TEST_DRONE)
    expect(cur(TEST_DRONE)).toMatchObject({ label: '可起飞', warn: false })
    expect(useFlightPhase(TEST_DRONE).hint.value?.text).toBe('下一步：执行航线，或按下方 A 的「起飞」')
  })

  it('in the air: route progress, proximity pause (amber), return home, emergency stop', () => {
    online(TEST_DRONE, 3)
    granted(TEST_DRONE)
    useExecutionStore(TEST_DRONE).current = { active: true, state: 'EXECUTING', reachedCount: 2, total: 5 } as never
    expect(cur(TEST_DRONE)).toMatchObject({ label: '航线 2/5', warn: false })
    expect(useFlightPhase(TEST_DRONE).hint.value).toBeNull()

    pausedByProximity(TEST_DRONE)
    expect(cur(TEST_DRONE)).toMatchObject({ label: '航线暂停', warn: true })
    expect(useFlightPhase(TEST_DRONE).hint.value).toEqual({ text: '航线暂停（两机靠近）：拉开距离后按「继续 A 的航线」', warn: true })

    useExecutionStore(TEST_DRONE).current = null
    online(TEST_DRONE, 9)
    expect(cur(TEST_DRONE).label).toBe('返航中')
    expect(useFlightPhase(TEST_DRONE).hint.value?.text).toContain('A 的「取消返航」')

    online(TEST_DRONE, 3)
    useControlStore(TEST_DRONE).upsert({ id: 'e1', type: 'estop', label: '急停', channel: 'DRC', status: 'ACKED', createdAt: Date.now(), sentAt: Date.now(), completedAt: Date.now(), resultCode: 0, message: null })
    useControlStore(TEST_DRONE).lastByAction = { estop: 'e1' }
    expect(cur(TEST_DRONE)).toMatchObject({ label: '急停悬停', warn: true })
    expect(useFlightPhase(TEST_DRONE).hint.value?.text).toContain('急停后悬停')
  })
})
