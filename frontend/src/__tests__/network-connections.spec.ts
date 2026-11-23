import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises } from '@vue/test-utils'
import { useNetworkStore } from '@/stores/network'
import { declaredMeasuredFixture, legacyGatewayFixture, measuredCapabilities, networkConfig } from './fixtures/network'
// @ts-expect-error plain JavaScript test fixture
import { makeSnapshot } from '../../../scripts/network-studio/mock.mjs'
let store: ReturnType<typeof useNetworkStore>
let fetcher: ReturnType<typeof vi.fn>
let current = declaredMeasuredFixture()
const reply = (body: unknown) => ({ ok: true, json: async () => body })
const serverA = { apiBaseUrl: 'https://server-a.test', protocol: 'network-v1' as const }
const serverB = { apiBaseUrl: 'https://server-b.test', protocol: 'network-v1' as const }
const gateway = { apiBaseUrl: 'http://127.0.0.1:8794', protocol: 'lora-v1' as const }
beforeEach(() => {
  localStorage.clear(); setActivePinia(createPinia()); store = useNetworkStore(); current = declaredMeasuredFixture()
  fetcher = vi.fn(async (url: string) => {
    if (url === '/network-config.json') return reply(networkConfig(false))
    if (url.endsWith('/capabilities')) return reply(measuredCapabilities)
    if (url.endsWith('/snapshot')) return reply(current)
    if (url.endsWith('/topology')) return reply(legacyGatewayFixture())
    if (url.endsWith('/replays')) return reply([])
    throw new Error('unexpected request ' + url)
  })
  vi.stubGlobal('fetch', fetcher)
})
afterEach(() => { store.stop(); vi.restoreAllMocks(); vi.unstubAllGlobals(); localStorage.clear() })

describe('real connection lifecycle and NODE annotations', () => {
  it('starts with no source connected and does not read any backend', async () => {
    await store.start(); expect(store.status).toBe('disabled'); expect(store.snapshot).toBeNull()
    expect(fetcher.mock.calls.map(c => c[0])).toEqual(['/network-config.json'])
    expect(Object.keys(store.configuration.profiles)).toEqual(['server', 'gateway'])
  })
  it('keeps both profiles and never turns a saved browser URL into automatic connection permission', async () => {
    await store.start(); await store.connect('server', serverA); expect(store.status).toBe('online')
    store.disconnect(); fetcher.mockClear(); await store.start()
    expect(store.status).toBe('disabled'); expect(store.configuration.profiles.server).toEqual(serverA)
    expect(store.configuration.profiles.gateway).toEqual(gateway)
    expect(fetcher.mock.calls.map(c => c[0])).toEqual(['/network-config.json'])
  })
  it('clears all old source evidence immediately when changing connection mode', async () => {
    await store.start(); await store.connect('server', serverA); expect(store.snapshot).not.toBeNull()
    store.selectConnectionMode('gateway')
    expect(store.snapshot).toBeNull(); expect(store.capabilities).toBeNull(); expect(store.sessions).toEqual([])
    expect(store.replay).toBeNull(); expect(store.recording).toBeNull(); expect(store.status).toBe('disabled')
    expect(store.configuration.mode).toBe('gateway')
  })
  it('ignores a late old-server snapshot after switching to the gateway', async () => {
    await store.start(); await store.connect('server', serverA)
    let finish: ((r: unknown) => void) | undefined
    fetcher.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const pending = store.refresh(); store.selectConnectionMode('gateway')
    finish!(reply({ ...current, sourceId: 'late-server' })); await pending
    expect(store.snapshot).toBeNull(); expect(store.status).toBe('disabled')
  })
  it('ignores capabilities from a cancelled server connection after connecting the gateway', async () => {
    await store.start(); let finish: ((r: unknown) => void) | undefined
    fetcher.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const pending = store.connect('server', serverA)
    await store.connect('gateway', gateway); finish!(reply(measuredCapabilities)); await pending
    expect(store.configuration.mode).toBe('gateway'); expect(store.snapshot?.provenance).toBe('unknown')
    expect(store.capabilities?.recording).toBe(false)
  })
  it('aborts capability reads when hidden and recovers initialization when visible', async () => {
    await store.start(); let hidden = false, signal: AbortSignal | undefined, finish: ((r: unknown) => void) | undefined
    vi.spyOn(document, 'hidden', 'get').mockImplementation(() => hidden)
    fetcher.mockImplementationOnce((_url: string, options: RequestInit) => new Promise(resolve => { signal = options.signal as AbortSignal; finish = resolve }))
    const pending = store.connect('server', serverA)
    hidden = true; document.dispatchEvent(new Event('visibilitychange')); expect(signal!.aborted).toBe(true)
    hidden = false; document.dispatchEvent(new Event('visibilitychange')); await flushPromises()
    expect(store.status).toBe('online'); expect(store.snapshot?.provenance).toBe('measured')
    finish!(reply(measuredCapabilities)); await pending
    expect(store.status).toBe('online'); expect(store.configuration.profiles.server).toEqual(serverA)
  })
  it('uses only GET legacy topology and never treats it as authenticated measured data', async () => {
    await store.start(); await store.connect('gateway', gateway)
    expect(store.status).toBe('online'); expect(store.snapshot?.provenance).toBe('unknown')
    expect(store.snapshot?.nodes.find(n => n.label === 'NODE 01')?.tag).toBeUndefined()
    expect(store.capabilities?.sourceSelection).toBe(false); expect(store.capabilities?.recording).toBe(false)
    expect(fetcher.mock.calls.filter(c => c[0] !== '/network-config.json').every(c => c[0].endsWith('/api/v1/lora/topology') && c[1].method === 'GET')).toBe(true)
  })
  it('retains only last measured evidence if a real server begins returning synthetic data', async () => {
    await store.start(); await store.connect('server', serverA); const before = store.snapshot
    current = makeSnapshot(); await store.refresh()
    expect(store.snapshot).toBe(before); expect(store.snapshot?.provenance).toBe('measured')
    expect(store.error).toBe('NETWORK_SYNTHETIC_REJECTED'); expect(store.interrupted).toBe(true); expect(store.recent).toBe(0)
    expect(fetcher.mock.calls.every(c => !c[0].includes('__network_mock'))).toBe(true)
  })
  it('rejects a mock service before any nodes are read', async () => {
    await store.start(); fetcher.mockResolvedValueOnce(reply({ ...measuredCapabilities, mock: true }))
    await store.connect('server', serverA)
    expect(store.error).toBe('NETWORK_SYNTHETIC_REJECTED'); expect(store.snapshot).toBeNull()
    expect(fetcher.mock.calls.some(c => c[0].endsWith('/snapshot'))).toBe(false)
  })
  it('persists operator tags by endpoint without inferring them from the transport role', async () => {
    await store.start(); await store.connect('server', serverA)
    const id = store.snapshot!.nodes[1]!.id
    expect(store.displaySnapshot!.nodes[1]!.tag).toBe('node')
    store.setTag(id, 'robot'); expect(store.displaySnapshot!.nodes[1]!.tag).toBe('robot')
    await store.connect('server', serverB); expect(store.displaySnapshot!.nodes[1]!.tag).toBe('node')
    await store.connect('gateway', gateway); expect(store.displaySnapshot!.nodes.find(n => n.id === id)!.tag).toBe('node')
    await store.connect('server', serverA); expect(store.displaySnapshot!.nodes[1]!.tag).toBe('robot')
    expect(store.snapshot!.nodes[1]!.role).toBe('node'); expect(store.snapshot!.nodes[1]!.binding).toBeNull()
  })
  it('isolates tags by receiver source and refuses arbitrary tag values', async () => {
    await store.start(); await store.connect('server', serverA); const id = current.nodes[1]!.id
    store.setTag(id, 'drone'); current = { ...current, sourceId: 'other-receiver' }; await store.refresh()
    expect(store.displaySnapshot!.nodes[1]!.tag).toBe('node')
    store.setTag(id, 'UAV' as never); expect(store.displaySnapshot!.nodes[1]!.tag).toBe('node')
    current = { ...current, sourceId: 'test-receiver' }; await store.refresh()
    expect(store.displaySnapshot!.nodes[1]!.tag).toBe('drone')
  })
  it('does not apply a late recording result to a new connection', async () => {
    await store.start(); fetcher.mockResolvedValueOnce(reply({ ...measuredCapabilities, recording: true }))
    await store.connect('server', serverA); let finish: ((r: unknown) => void) | undefined
    fetcher.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const pending = store.toggleRecording(); store.selectConnectionMode('gateway')
    finish!(reply({ id: 'late-recording' })); await pending
    expect(store.recording).toBeNull(); expect(store.status).toBe('disabled'); expect(store.busy).toBe(false)
  })
  it('refuses an invalid credential URL without retaining old nodes or making a request', async () => {
    await store.start(); await store.connect('server', serverA); fetcher.mockClear()
    await store.connect('server', { ...serverA, apiBaseUrl: 'https://user:password@server.test' })
    expect(store.snapshot).toBeNull(); expect(store.error).toBe('NETWORK_CONFIG_INVALID'); expect(fetcher).not.toHaveBeenCalled()
  })
})
