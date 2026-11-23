import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises } from '@vue/test-utils'
import { useNetworkStore } from '@/stores/network'
import { networkConfig } from './fixtures/network'
// @ts-expect-error plain JavaScript fixture
import { makeSnapshot } from '../../../scripts/network-studio/mock.mjs'
let snapshot = makeSnapshot({ at: 100000 })
const capabilities = { schema: 'network.capabilities.v1', mock: true, recording: true, sourceSelection: true, sources: [{ id: 'synthetic-lab', label: 'Lab' }], selectedSourceId: 'synthetic-lab', scenario: 'nominal' }
let fetchMock: ReturnType<typeof vi.fn>
let store: ReturnType<typeof useNetworkStore>
const response = (body: unknown) => ({ ok: true, json: async () => body })
beforeEach(() => {
  setActivePinia(createPinia()); snapshot = makeSnapshot({ at: 100000 }); store = useNetworkStore()
  fetchMock = vi.fn(async (input: string) => {
    if (input === '/network-mock-config.json') return response(networkConfig())
    if (input.endsWith('/capabilities')) return response(capabilities)
    if (input.endsWith('/snapshot')) return response(snapshot)
    if (input.endsWith('/replays')) return response([])
    if (input.includes('/replays/sample')) return response({ schema: 'network.replay.v1', id: 'sample', frames: [snapshot, { ...snapshot, observedAt: 101000 }] })
    throw new Error('unexpected request ' + input)
  })
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => { store.stop(); vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers() })

describe('independent network observer', () => {
  it('starts from explicit configuration and never calls a flight/device API', async () => {
    await store.start('mock'); expect(store.status).toBe('online'); expect(store.snapshot?.provenance).toBe('synthetic')
    expect(fetchMock.mock.calls.map(c => c[0]).every(path => path === '/network-mock-config.json' || path.startsWith('/api/v1/network/'))).toBe(true)
  })
  it('makes no backend request when production configuration is disabled', async () => {
    fetchMock.mockResolvedValue(response(networkConfig(false)))
    await store.start('mock'); expect(store.status).toBe('disabled'); expect(fetchMock).toHaveBeenCalledTimes(1)
  })
  it('retains the last snapshot but marks interrupted observation on failure', async () => {
    await store.start('mock'); const before = store.snapshot
    fetchMock.mockRejectedValue(new Error('connection lost'))
    await store.refresh(); expect(store.snapshot).toBe(before); expect(store.status).toBe('error'); expect(store.interrupted).toBe(true)
    expect(store.recent).toBe(0)
  })
  it('aborts stale pending requests when paused and ignores late old-source results', async () => {
    await store.start('mock'); const before = store.snapshot
    let finish: ((value: unknown) => void) | undefined
    fetchMock.mockImplementation(() => new Promise(resolve => { finish = resolve }))
    const refresh = store.refresh(); store.togglePause()
    finish!(response({ ...snapshot, sourceId: 'old-source' })); await refresh
    expect(store.paused).toBe(true); expect(store.snapshot).toBe(before)
  })
  it('keeps replay separate from live polling and allows deterministic seeking', async () => {
    await store.start('mock'); await store.openReplay('sample')
    expect(store.mode).toBe('replay'); store.seek(1); expect(store.now).toBe(101000)
    const calls = fetchMock.mock.calls.length; await store.refresh(); expect(fetchMock).toHaveBeenCalledTimes(calls)
    await store.goLive(); expect(store.mode).toBe('live'); expect(store.snapshot?.observedAt).toBe(100000)
  })
  it('does not apply a late response after leaving the page', async () => {
    await store.start('mock'); const before = store.snapshot
    let finish: ((value: unknown) => void) | undefined
    fetchMock.mockImplementation(() => new Promise(resolve => { finish = resolve }))
    const pending = store.refresh(); store.stop(); finish!(response({ ...snapshot, sourceId: 'late' })); await pending
    expect(store.snapshot).toBe(before)
  })
  it('rejects older epochs within one service instance but accepts a restarted instance', async () => {
    snapshot = { ...snapshot, epoch: 3 }; await store.start('mock')
    snapshot = { ...snapshot, epoch: 2 }; await store.refresh(); expect(store.status).toBe('error')
    snapshot = { ...snapshot, epoch: 0, instanceId: 'new-instance' }; await store.refresh(); expect(store.status).toBe('online')
  })
  it('retries initialization after configuration or capabilities fail', async () => {
    fetchMock.mockRejectedValueOnce(new Error('service not ready'))
    await store.start('mock'); expect(store.status).toBe('error')
    await store.retry(); expect(store.status).toBe('online')
  })
  it('preserves actual frame spacing at the selected replay speed', async () => {
    await store.start('mock')
    fetchMock.mockResolvedValueOnce(response({ schema: 'network.replay.v1', id: 'timed', frames: [snapshot, { ...snapshot, observedAt: 104000 }] }))
    await store.openReplay('timed')
    vi.useFakeTimers(); store.play(); await vi.advanceTimersByTimeAsync(2000); expect(store.frame).toBe(0)
    await vi.advanceTimersByTimeAsync(2000); expect(store.frame).toBe(1); expect(store.playing).toBe(false)
    store.seek(0); store.setSpeed(4); store.play(); await vi.advanceTimersByTimeAsync(999); expect(store.frame).toBe(0)
    await vi.advanceTimersByTimeAsync(1); expect(store.frame).toBe(1)
  })
  it('does not label an intentionally paused observer as a broken connection', async () => {
    await store.start('mock'); store.togglePause(); vi.useFakeTimers(); await vi.advanceTimersByTimeAsync(10000)
    expect(store.interrupted).toBe(false)
  })
  it('does not apply a source selection response after the page stops', async () => {
    await store.start('mock'); let finish: ((value: unknown) => void) | undefined
    fetchMock.mockImplementation(() => new Promise(resolve => { finish = resolve }))
    const selecting = store.selectSource('other'); store.stop()
    finish!(response({ ...capabilities, selectedSourceId: 'other' })); await selecting
    expect(store.capabilities?.selectedSourceId).toBe('synthetic-lab')
  })
  it('cancels polling while hidden and resumes only when visible', async () => {
    await store.start('mock'); let hidden = false
    vi.spyOn(document, 'hidden', 'get').mockImplementation(() => hidden)
    hidden = true; document.dispatchEvent(new Event('visibilitychange'))
    const calls = fetchMock.mock.calls.length; await store.refresh(); expect(fetchMock).toHaveBeenCalledTimes(calls)
    hidden = false; document.dispatchEvent(new Event('visibilitychange')); await flushPromises()
    expect(fetchMock.mock.calls.length).toBeGreaterThan(calls)
  })
})
