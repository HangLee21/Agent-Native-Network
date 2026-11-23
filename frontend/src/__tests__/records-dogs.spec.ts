import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import HistoryView from '@/views/HistoryView.vue'
import { resolveConfig, setConfigForTest } from '@/config/runtime'
import { historyApi, type FlightEvent, type SessionSummary } from '@/api/history'
import { dogRecordsApi, dogName, type DogRecordDetail, type DogRecordSummary, type DogSample } from '@/api/dogRecords'
import { dog2Api } from '@/api/dogv2'
import { useRoutesStore } from '@/stores/routes'
import { useConfirmStore } from '@/stores/confirm'
import { buildTrack, dogDetail, dogSample, dogState, dronePair, mergedItems, trackState } from '@/utils/jointReplay'
import { parseRefs, refsParam } from '@/utils/records'

/** Records of drones and dogs on one page, replayed together in any combination (D-40). */
function flight(id: string, over: Partial<SessionSummary> = {}): SessionSummary {
  return {
    id, status: 'CLOSED', startedAt: 1_000_000, takeoffAt: 1_100_000, landedAt: 1_400_000, endedAt: 1_430_000, outcome: 'LANDED',
    routeId: null, routeName: '巡检 1', distanceMeters: 190, maxRelativeHeight: 30, maxHomeDistance: 60, maxHorizontalSpeed: 5,
    batteryStart: 90, batteryEnd: 80, alertCount: 0, maxAlertLevel: null, commandCount: 3, simulated: false, resumed: false,
    protectedFlag: false, videoStatus: null, trackPreview: null, gatewaySn: 'RC-A', droneSn: 'AC-A', together: [], ...over,
  }
}

function dogRec(id: string, over: Partial<DogRecordSummary> = {}): DogRecordSummary {
  return {
    kind: 'dog', id, status: 'CLOSED', dogId: 'lite3-01', dogModel: 'lite3', dogLabel: 'lite3-01', startedAt: 1_200_000, takeoffAt: 1_200_000,
    landedAt: 1_500_000, endedAt: 1_500_000, outcome: 'ENDED', startReason: '取得控制', routeId: null, routeName: null, distanceMeters: 42,
    maxRelativeHeight: null, maxHorizontalSpeed: 0.6, batteryStart: 80, batteryEnd: 78, alertCount: 1, maxAlertLevel: 'WARNING',
    commandCount: 4, simulated: false, resumed: false, protectedFlag: false, videoStatus: 'READY', videoBytes: 2_000_000,
    trackPreview: [[22.5, 113.9], [22.5001, 113.9001]], together: [{ kind: 'drone', id: 'f1', device: 'RC-A' }], ...over,
  }
}

let wrapper: VueWrapper | null = null
let router: Router

async function mountHistory(): Promise<VueWrapper> {
  router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/history', component: HistoryView },
    { path: '/history/together', component: { template: '<div />' } },
    { path: '/history/:id', component: { template: '<div />' } },
  ] })
  await router.push('/history')
  await router.isReady()
  wrapper = mount(HistoryView, { global: { plugins: [router] }, attachTo: document.body })
  await flushPromises()
  return wrapper
}

describe('records page with dogs', () => {
  beforeEach(() => {
    localStorage.clear()
    setConfigForTest(resolveConfig({}, 'http://x'))
    setActivePinia(createPinia())
    vi.spyOn(useRoutesStore(), 'refresh').mockResolvedValue()
    vi.spyOn(useConfirmStore(), 'ask').mockResolvedValue(true)
    vi.spyOn(dog2Api, 'list').mockResolvedValue({ mode: 'on', broker: true, dogs: [] })
  })

  afterEach(() => {
    wrapper?.unmount()
    wrapper = null
    vi.restoreAllMocks()
  })

  it('lists flights and dog records by start time, and opens a dog record in the joint replay', async () => {
    vi.spyOn(historyApi, 'list').mockResolvedValue([flight('f1')])
    vi.spyOn(dogRecordsApi, 'list').mockResolvedValue([dogRec('d1')])
    const w = await mountHistory()
    const rows = w.findAll('tbody tr')
    expect(rows.map((r) => r.attributes('data-test'))).toEqual(['row-dog', 'row-drone'])
    expect(rows[0]!.text()).toContain('Lite3')
    expect(rows[0]!.text()).toContain('正常结束')
    expect(rows[0]!.text()).toContain('—')               // no route for a dog
    // a dog walks a 轨迹, a drone flies a 航迹: with dogs in the list the column says 轨迹
    expect(w.find('thead').text()).toContain('轨迹')
    expect(w.find('thead').text()).not.toContain('航迹')
    await rows[0]!.trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe('/history/together?ids=dog:d1')
  })

  it('replays a flight together with the dog records overlapping it, and any ticked rows together', async () => {
    vi.spyOn(historyApi, 'list').mockResolvedValue([flight('f1'), flight('f2', { takeoffAt: 9_000_000, landedAt: 9_100_000, endedAt: 9_100_000 })])
    vi.spyOn(dogRecordsApi, 'list').mockResolvedValue([dogRec('d1')])
    const w = await mountHistory()
    const drone = w.findAll('[data-test=row-drone]')
    const late = drone.find((r) => !r.find('[data-test=together]').exists())
    expect(late).toBeDefined()                           // f2: nothing at the same time
    const f1 = drone.find((r) => r.find('[data-test=together]').exists())!
    expect(f1.get('[data-test=together]').attributes('title')).toContain('Lite3')
    await f1.get('[data-test=together]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query.ids).toBe('f1,dog:d1')

    await router.push('/history')
    await flushPromises()
    expect(w.find('[data-test=play-selected]').exists()).toBe(false)
    const boxes = w.findAll('tbody input[type=checkbox]')
    await boxes[0]!.setValue(true)
    await boxes[2]!.setValue(true)
    expect(w.get('[data-test=play-selected]').text()).toContain('一起回放（2）')
    await w.get('[data-test=play-selected]').trigger('click')
    await flushPromises()
    expect(parseRefs(String(router.currentRoute.value.query.ids))).toHaveLength(2)
  })

  it('a dog result hides the flights; deleting ticked rows goes to each kind\'s API', async () => {
    const list = vi.spyOn(historyApi, 'list').mockResolvedValue([flight('f1')])
    vi.spyOn(dogRecordsApi, 'list').mockResolvedValue([dogRec('d1'), dogRec('d2', { outcome: 'SOFT_ESTOP', startedAt: 1_600_000, trackPreview: null })])
    const removeDogs = vi.spyOn(dogRecordsApi, 'removeMany').mockResolvedValue({ deleted: 1, skipped: [] })
    const removeFlights = vi.spyOn(historyApi, 'removeMany').mockResolvedValue({ deleted: 1, skipped: [] })
    const w = await mountHistory()
    await w.get('thead input[type=checkbox]').setValue(true)
    await w.get('[data-test=delete-selected]').trigger('click')
    await flushPromises()
    expect(removeFlights).toHaveBeenCalledWith(['f1'])
    expect(removeDogs.mock.calls[0]![0].sort()).toEqual(['d1', 'd2'])

    list.mockClear()
    await w.get('[data-test=filter-outcome]').setValue('dog:SOFT_ESTOP')
    await flushPromises()
    expect(list).not.toHaveBeenCalled()
    const rows = w.findAll('tbody tr')
    expect(rows).toHaveLength(1)
    expect(rows[0]!.text()).toContain('软急停')
    expect(rows[0]!.text()).toContain('无轨迹')
  })
})

describe('replay helpers for drones and dogs', () => {
  it('writes and reads record references of both kinds', () => {
    const refs = parseRefs('f1, dog:d1,f1,dog:d1,dog:')
    expect(refs).toEqual([{ kind: 'drone', id: 'f1' }, { kind: 'dog', id: 'd1' }])
    expect(refsParam(refs)).toBe('f1,dog:d1')
  })

  it('names a dog by its label, else its model', () => {
    expect(dogName({ dogModel: 'lite3', dogLabel: 'lite3-01', dogId: 'lite3-01' })).toBe('Lite3')
    expect(dogName({ dogModel: 'lite3', dogLabel: '小白', dogId: 'lite3-01' })).toBe('小白')
    expect(dogName({ dogModel: null, dogLabel: null, dogId: 'x-1' })).toBe('x-1')
  })

  it('builds a dog track from the flight-shaped data: no phases, its own state, state events in the list', () => {
    const detail = { ...dogRec('d1'), sampleCount: 2, videoWanted: true, videoMessage: null, videoPath: 'dog/lite3-01-rgb', videoParts: null,
      videoOffsetMs: 0, recording: false, takeoffEllipsoidHeight: null, homeLat: null, homeLon: null, routeSnapshot: null } as DogRecordDetail
    const s = (ts: number, over: Partial<DogSample> = {}): DogSample => ({
      ts, sampleSource: 'DOG', lat: 22.5, lon: 113.9, horizontalSpeed: 0.4, attitudeHead: 90, attitudePitch: null, attitudeRoll: null, battery: 80,
      altitude: 12, fix: 'single', sats: 14, headingSource: 'imu_aligned', basicState: 6, basicStateName: 'FORCE_CONTROL', motionState: 1,
      gaitState: 0, mode: 'new', controlHeld: true, controlLabel: '实时监控', yaw: 12, ...over,
    })
    const events: FlightEvent[] = [
      { id: 1, ts: 1_250_000, eventType: 'MODE', eventLevel: 'INFO', title: '板卡模式：老系统 → 新系统', payload: null },
      { id: 2, ts: 1_260_000, eventType: 'ALERT_RAISED', eventLevel: 'CRITICAL', title: '软急停', payload: { code: 'SOFT_ESTOP' } },
    ]
    const dog = buildTrack('d1', 'Lite3', '#a3e635', dogDetail(detail), [s(1_200_000), s(1_300_000, { lat: null, lon: null })].map(dogSample), events, [], 'dog')
    expect(dog.kind).toBe('dog')
    expect(dog.phases).toEqual([])
    const at = dogState(trackState(dog, 1_300_000))!
    expect(at.lat).toBe(22.5)                             // carried forward without a fix
    expect(at.fix).toBe('single')
    expect(at.basicStateName).toBe('FORCE_CONTROL')
    expect(at.height).toBeNull()
    const items = mergedItems([dog])
    expect(items.map((i) => i.text)).toEqual(['板卡模式：老系统 → 新系统', '软急停'])
    expect(dronePair([dog])).toBeNull()
  })
})
