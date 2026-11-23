import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import JointReplayView from '@/views/JointReplayView.vue'
import { setConfigForTest } from '@/config/runtime'
import { useFleetStore } from '@/stores/fleet'
import { device } from './testDrone'
import type { FlightCommand, FlightEvent, Sample, SessionDetail } from '@/api/history'
import { axis, buildTrack, mergedItems, proximitySpans, recordedAt, separationAt, within } from '@/utils/jointReplay'

/** Two-drone replay helpers (D-33, ui-design.md 2.7.1). */
const LAT = 22.58
const LON = 113.94
const east = (m: number) => m / (111_320 * Math.cos((LAT * Math.PI) / 180))

function sample(ts: number, eastM: number, rel: number): Sample {
  return { ts, deviceTs: null, sampleSource: 'OSD', lat: LAT, lon: LON + east(eastM), ellipsoidHeight: null, relativeHeight: rel, drcHeight: null,
    horizontalSpeed: 0, verticalSpeed: 0, attitudeHead: 0, attitudePitch: 0, attitudeRoll: 0, gimbalPitch: 0, gimbalYaw: null, gimbalRoll: 0,
    zoomFactor: 1, battery: 90, remainFlightTime: null, returnHomePower: null, modeCode: 3, gpsNumber: null, rtkNumber: null, windSpeed: null,
    windDirection: null, homeDistance: null, heightLimit: 120 }
}

function detail(over: Partial<SessionDetail>): SessionDetail {
  return { id: 'x', status: 'CLOSED', startedAt: 0, takeoffAt: null, landedAt: null, endedAt: null, takeoffEllipsoidHeight: null, ...over } as SessionDetail
}

function event(ts: number, eventType: string, code: string, message = ''): FlightEvent {
  return { id: ts, ts, eventType, eventLevel: 'WARNING', title: '两机靠近', payload: { code, message } }
}

const cmd = (createdAt: number, label: string): FlightCommand =>
  ({ id: `c${createdAt}`, commandType: 'FlyToPoint', label, channel: null, status: 'ACKED', createdAt, sentAt: createdAt, completedAt: createdAt, resultCode: 0, message: '设备已确认', params: null })

// A flies 10 s from 1000, B 10 s from 6000 (5 s overlap); A at 0 m east and 30 m, B 20 m east and 45 m above the same ground
const A = buildTrack('a', 'A', '#378ADD', detail({ startedAt: 1000, takeoffAt: 1000, endedAt: 11_000, takeoffEllipsoidHeight: 100 }),
  [sample(1000, 0, 30), sample(11_000, 0, 30)],
  [event(7000, 'ALERT_RAISED', 'PROXIMITY', 'A 与 B：水平 20 m'), event(9000, 'ALERT_CLEARED', 'PROXIMITY'), event(8000, 'ALERT_RAISED', 'LOW_BATTERY')],
  [cmd(2000, '飞向目标点')])
const B = buildTrack('b', 'B', '#D85A30', detail({ startedAt: 6000, takeoffAt: 6000, endedAt: 16_000, takeoffEllipsoidHeight: 102 }),
  [sample(6000, 20, 43), sample(16_000, 20, 43)],
  [event(7100, 'ALERT_RAISED', 'PROXIMITY', 'A 与 B：水平 20 m'), event(9500, 'ALERT_CLEARED', 'PROXIMITY')],
  [cmd(6500, '一键起飞')])

describe('two-drone replay', () => {
  it('puts both flights on one axis and knows when each was recorded', () => {
    expect(axis([A, B])).toEqual({ start: 1000, end: 16_000 })
    expect(recordedAt(B, 3000)).toBe(false)
    expect(recordedAt(B, 7000)).toBe(true)
  })

  it('measures the separation on a common height reference', () => {
    expect(separationAt(A, B, 3000)).toBeNull() // B not recorded yet
    const s = separationAt(A, B, 8000)!
    expect(s.horizontalM).toBeCloseTo(20, 0)
    // relative heights 30 and 43 from take-off points at 100 and 102 m ellipsoid: 130 vs 145
    expect(s.verticalM).toBeCloseTo(15, 5)
  })

  it('merges the proximity alarm both records hold into one period and one row', () => {
    const spans = proximitySpans([A, B])
    expect(spans).toEqual([[7000, 9500]])
    expect(within(spans, 9200)).toBe(true)
    const items = mergedItems([A, B])
    expect(items.map((i) => [i.ts, i.track])).toEqual([[2000, 0], [6500, 1], [7000, -1], [8000, 0]])
    expect(items.find((i) => i.track === -1)!.text).toBe('A 与 B：水平 20 m')
  })
})

describe('two-drone replay page', () => {
  beforeAll(() => {
    globalThis.ResizeObserver ??= class {
      observe() {}
      disconnect() {}
    } as unknown as typeof ResizeObserver
  })
  afterEach(() => vi.unstubAllGlobals())

  it('shows both drones, their separation and one merged list', async () => {
    setActivePinia(createPinia())
    setConfigForTest({ apiBaseUrl: 'http://api.test', wsUrl: '', map: { coordSys: 'WGS84', tileUrl: '', subdomains: '', attribution: '', maxZoom: 19, apiKey: '' } })
    useFleetStore().drones = [device({ gatewaySn: 'RC-A', droneSn: 'M-A', label: 'A' }), device({ gatewaySn: 'RC-B', droneSn: 'M-B', label: 'B', color: '#D85A30' })]
    const data: Record<string, unknown> = {
      '/sessions/a': { ...A.detail, id: 'a', gatewaySn: 'RC-A', droneSn: 'M-A', outcome: 'COMPLETED', routeName: '巡检东' },
      '/sessions/b': { ...B.detail, id: 'b', gatewaySn: 'RC-B', droneSn: 'M-B', outcome: 'STOPPED', routeName: null },
      '/sessions/a/samples': [sample(1000, 0, 30), sample(11_000, 0, 30)],
      '/sessions/b/samples': [sample(6000, 20, 43), sample(16_000, 20, 43)],
      '/sessions/a/events': A.events, '/sessions/b/events': B.events,
      '/sessions/a/commands': A.commands, '/sessions/b/commands': B.commands,
    }
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      const key = String(url).replace('http://api.test/api/v1/history', '')
      return new Response(JSON.stringify(data[key] ?? {}), { status: key in data ? 200 : 404 })
    }))
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/history/together', component: JointReplayView }, { path: '/:p(.*)', component: { template: '<i />' } }] })
    await router.push('/history/together?ids=b,a')
    const w = mount(JointReplayView, { global: { plugins: [router] }, attachTo: document.body })
    await flushPromises()
    // earliest take-off first, whatever the order of the ids
    expect(w.findAll('[data-test^=joint-chip]').map((c) => c.text())).toEqual([expect.stringContaining('A'), expect.stringContaining('B')])
    expect(w.find('[data-test=joint-chip-A]').text()).toContain('巡检东')
    expect(w.find('[data-test=joint-chip-A]').text()).toContain('航线完成')
    // the cursor starts at the first take-off, when only A is recorded
    expect(w.find('[data-test=joint-card-1]').text()).toContain('还没开始记录')
    expect(w.find('[data-test=joint-separation]').text()).toContain('此刻只有一架有位置')
    const rows = w.findAll('[data-test=joint-items] .item').map((r) => r.text())
    expect(rows).toHaveLength(4)
    expect(rows[2]).toContain('两机')
    w.unmount()
  })

  it('opens a dog record imported from its video (no positions) with the video as the main view', async () => {
    setActivePinia(createPinia())
    setConfigForTest({ apiBaseUrl: 'http://api.test', wsUrl: '', map: { coordSys: 'WGS84', tileUrl: '', subdomains: '', attribution: '', maxZoom: 19, apiKey: '' } })
    const rec = { kind: 'dog', id: 'd1', status: 'CLOSED', dogId: 'lite3-01', dogModel: 'lite3', dogLabel: 'lite3-01', startedAt: 1000, takeoffAt: 1000,
      landedAt: 61_000, endedAt: 61_000, outcome: null, together: [], videoStatus: 'READY', videoOffsetMs: 0, sampleCount: 0,
      videoParts: [{ index: 0, file: 'd1-0.mp4', startAt: 1000, durationMs: 60_000, bytes: 10, transcoded: true }] }
    const data: Record<string, unknown> = { '/d1': rec, '/d1/samples': [], '/d1/events': [], '/d1/commands': [] }
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      const key = String(url).replace('http://api.test/api/v1/dog-records', '')
      return new Response(JSON.stringify(data[key] ?? {}), { status: key in data ? 200 : 404 })
    }))
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/history/together', component: JointReplayView }, { path: '/:p(.*)', component: { template: '<i />' } }] })
    await router.push('/history/together?ids=dog:d1')
    const w = mount(JointReplayView, { global: { plugins: [router] }, attachTo: document.body })
    await flushPromises()
    expect(w.find('[data-test=joint-video]').exists()).toBe(true)
    expect(w.find('.video').classes()).toContain('main')
    expect(w.text()).not.toContain('这些记录都没有位置数据')
    expect(w.text()).not.toContain('视频为主')
    expect(w.find('[data-test=joint-card-0]').text()).toContain('没有位置数据')
    w.unmount()
  })
})
