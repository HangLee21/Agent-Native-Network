import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import HistoryView from '@/views/HistoryView.vue'
import ReplayView from '@/views/ReplayView.vue'
import { resolveConfig, setConfigForTest } from '@/config/runtime'
import { historyApi, type SessionDetail, type SessionSummary } from '@/api/history'
import { useConfirmStore } from '@/stores/confirm'
import { useRoutesStore } from '@/stores/routes'

/** Deleting only a flight's video keeps the flight record (user, 2026-11-01). */
function session(id: string, over: Partial<SessionSummary> = {}): SessionSummary {
  return {
    id, status: 'CLOSED', startedAt: 1_793_333_382_530, takeoffAt: 1_793_333_502_530, landedAt: 1_793_333_666_540,
    endedAt: 1_793_333_666_540, outcome: 'LANDED', routeId: null, routeName: null, distanceMeters: 190, maxRelativeHeight: 30,
    maxHomeDistance: 60, maxHorizontalSpeed: 5, batteryStart: 90, batteryEnd: 80, alertCount: 0, maxAlertLevel: null,
    commandCount: 3, simulated: false, resumed: false, protectedFlag: false, videoStatus: 'READY', videoBytes: 12_300_000,
    trackPreview: null, ...over,
  }
}

let wrapper: VueWrapper | null = null

async function mountHistory(): Promise<VueWrapper> {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/history', component: HistoryView }, { path: '/history/:id', component: HistoryView }] })
  await router.push('/history')
  await router.isReady()
  wrapper = mount(HistoryView, { global: { plugins: [router] }, attachTo: document.body })
  await flushPromises()
  return wrapper
}

describe('flight history: delete only the video', () => {
  beforeEach(() => {
    localStorage.clear()
    setConfigForTest(resolveConfig({}, 'http://x'))
    setActivePinia(createPinia())
    vi.spyOn(useRoutesStore(), 'refresh').mockResolvedValue()
    vi.spyOn(useConfirmStore(), 'ask').mockResolvedValue(true)
  })

  afterEach(() => {
    wrapper?.unmount()
    wrapper = null
    vi.restoreAllMocks()
  })

  it('shows the video size and deletes just the video of one flight', async () => {
    vi.spyOn(historyApi, 'list').mockResolvedValue([
      session('a'),
      session('b', { videoStatus: 'DELETED', videoBytes: null }),
      session('c', { protectedFlag: true }),
    ])
    const removeVideo = vi.spyOn(historyApi, 'removeVideo').mockResolvedValue({ id: 'a', freedBytes: 12_300_000 })
    const remove = vi.spyOn(historyApi, 'remove')
    const w = await mountHistory()
    const rows = w.findAll('tbody tr')
    expect(rows[0]!.text()).toContain('视频 12.3 MB')
    expect(rows[1]!.text()).toContain('录像已删除')
    expect(rows[1]!.find('[data-test=delete-video]').exists()).toBe(false)
    expect(rows[2]!.get('[data-test=delete-video]').attributes('disabled')).toBeDefined() // protected
    await rows[0]!.get('[data-test=delete-video]').trigger('click')
    await flushPromises()
    expect(removeVideo).toHaveBeenCalledWith('a')
    expect(remove).not.toHaveBeenCalled()
  })

  it('deletes the videos of the selected flights that have one', async () => {
    vi.spyOn(historyApi, 'list').mockResolvedValue([session('a'), session('b', { videoStatus: 'OFF', videoBytes: null }), session('c')])
    const removeVideos = vi.spyOn(historyApi, 'removeVideos').mockResolvedValue({ deleted: 2, skipped: [], freedBytes: 24_600_000 })
    const w = await mountHistory()
    expect(w.find('[data-test=delete-selected-videos]').exists()).toBe(false)
    await w.get('thead input[type=checkbox]').setValue(true)
    expect(w.get('[data-test=delete-selected-videos]').text()).toContain('只删录像（2）')
    await w.get('[data-test=delete-selected-videos]').trigger('click')
    await flushPromises()
    expect(removeVideos).toHaveBeenCalledWith(['a', 'c'])
  })
})

/** Archive the video again after a failed archive (field test 2026-11-04: a gap in the recording failed it). */
function detail(over: Partial<SessionDetail> = {}): SessionDetail {
  return {
    ...session('s1', { videoStatus: 'FAILED', videoBytes: null }), droneSn: 'M-A', gatewaySn: 'RC-A', takeoffLat: null, takeoffLon: null,
    takeoffEllipsoidHeight: null, homeLat: null, homeLon: null, sampleCount: 0, droppedItems: 0, delayMinMs: null, delayAvgMs: null,
    delayMaxMs: null, clockOffsetMs: null, routeSnapshot: null, rawAtTakeoff: null, rawAtLanding: null, videoWanted: true,
    videoMessage: '视频归档失败：MediaMTX /get HTTP 404', videoPath: 'live/x', videoParts: null, videoQuality: 1, videoOffsetMs: 0,
    recording: false, together: [], ...over,
  }
}

async function mountReplay(d: SessionDetail): Promise<VueWrapper> {
  vi.spyOn(historyApi, 'get').mockResolvedValue(d)
  vi.spyOn(historyApi, 'samples').mockResolvedValue([])
  vi.spyOn(historyApi, 'events').mockResolvedValue([])
  vi.spyOn(historyApi, 'commands').mockResolvedValue([])
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/history/:id', component: ReplayView }, { path: '/:p(.*)', component: { template: '<i />' } }] })
  await router.push(`/history/${d.id}`)
  await router.isReady()
  wrapper = mount(ReplayView, { global: { plugins: [router] }, attachTo: document.body })
  await flushPromises()
  return wrapper
}

describe('flight replay: archive the video again', () => {
  beforeAll(() => {
    globalThis.ResizeObserver ??= class {
      observe() {}
      disconnect() {}
    } as unknown as typeof ResizeObserver
  })

  beforeEach(() => {
    setConfigForTest(resolveConfig({}, 'http://x'))
    setActivePinia(createPinia())
  })

  afterEach(() => {
    wrapper?.unmount()
    wrapper = null
    vi.restoreAllMocks()
  })

  it('offers it after a failed archive and is disabled while the new archive runs', async () => {
    const archive = vi.spyOn(historyApi, 'archiveVideo')
      .mockResolvedValue(detail({ videoStatus: 'ARCHIVING', videoMessage: '已排队，等待重新归档视频' }))
    const w = await mountReplay(detail())
    const btn = w.get('[data-test=rearchive-video]')
    expect(btn.text()).toContain('重新归档视频')
    expect(btn.attributes('disabled')).toBeUndefined()
    expect(btn.attributes('title')).toContain('MediaMTX /get HTTP 404')
    await btn.trigger('click')
    await flushPromises()
    expect(archive).toHaveBeenCalledTimes(1)
    expect(archive).toHaveBeenCalledWith('s1')
    const busy = w.get('[data-test=rearchive-video]')
    expect(busy.attributes('disabled')).toBeDefined()
    expect(busy.text()).toContain('归档中')
    expect(w.text()).toContain('已排队，等待重新归档视频')
    await busy.trigger('click')
    expect(archive).toHaveBeenCalledTimes(1)
  })

  it('is offered for an empty or not-configured archive, not with a video, while recording or after deleting the video', async () => {
    for (const [over, shown] of [
      [{ videoStatus: 'NONE', videoMessage: '流媒体服务器上没有本次飞行时段的录像' }, true],
      [{ videoStatus: 'UNAVAILABLE' }, true],
      [{ videoStatus: 'READY', videoParts: [{ index: 0, file: 's1-0.mp4', startAt: 1_793_333_502_530, durationMs: 60_000, bytes: 10, transcoded: true }] }, false],
      [{ videoStatus: 'DELETED' }, false],
      [{ status: 'OPEN', videoStatus: 'PENDING', endedAt: null, recording: true }, false],
      [{ status: 'OPEN', videoStatus: 'FAILED', endedAt: null, recording: true }, false],
    ] as [Partial<SessionDetail>, boolean][]) {
      const w = await mountReplay(detail(over))
      expect(w.find('[data-test=rearchive-video]').exists(), JSON.stringify(over)).toBe(shown)
      w.unmount()
      wrapper = null
      vi.restoreAllMocks()
    }
  })
})
