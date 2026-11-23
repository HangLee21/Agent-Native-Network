import { afterEach, describe, expect, it, vi } from 'vitest'
import { loadNetworkConfig, NetworkClient } from '@/network/api'
import { declaredMeasuredFixture, legacyGatewayFixture, measuredCapabilities, networkConfig } from './fixtures/network'
// @ts-expect-error plain JavaScript fixture
import { makeSnapshot } from '../../../scripts/network-studio/mock.mjs'
const reply = (data: unknown) => ({ ok: true, json: async () => data })
const mockClient = () => new NetworkClient('/__network_mock', { workspace: 'mock' })
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

describe('network adapter boundary', () => {
  it('uses a configured server base instead of a component-local loopback constant', async () => {
    const fetcher = vi.fn().mockResolvedValue(reply(declaredMeasuredFixture()))
    vi.stubGlobal('fetch', fetcher)
    await new NetworkClient('https://example.test/network-bridge').snapshot()
    expect(fetcher.mock.calls[0]?.[0]).toBe('https://example.test/network-bridge/api/v1/network/snapshot')
  })
  it('does not fall back to fixture data when a backend fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 503 }))
    await expect(new NetworkClient('').snapshot()).rejects.toThrow('NETWORK_HTTP_503')
  })
  it('rejects malformed capability and replay-list responses', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply(null)))
    await expect(new NetworkClient('').capabilities()).rejects.toThrow('NETWORK_CAPABILITIES_INVALID')
    await expect(new NetworkClient('').sessions()).rejects.toThrow('NETWORK_REPLAYS_INVALID')
  })
  it('rejects invalid snapshots returned inside replay and backwards frame time', async () => {
    const s = declaredMeasuredFixture()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(reply({ schema: 'network.replay.v1', id: 'a', frames: [{}] }))
      .mockResolvedValueOnce(reply({ schema: 'network.replay.v1', id: 'a', frames: [s, { ...s, observedAt: 99000 }] })))
    await expect(new NetworkClient('').replay('a')).rejects.toThrow('NETWORK_SCHEMA_INVALID')
    await expect(new NetworkClient('').replay('a')).rejects.toThrow('NETWORK_REPLAY_ORDER_INVALID')
  })
  it('keeps production explicitly disabled and rejects the old ambiguous single-endpoint config', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(reply(networkConfig(false))).mockResolvedValueOnce(reply({ enabled: true, apiBaseUrl: '' })))
    expect((await loadNetworkConfig()).enabled).toBe(false)
    await expect(loadNetworkConfig()).rejects.toThrow('NETWORK_CONFIG_INVALID')
  })
  it('refuses embedded credentials and unsupported URL protocols', async () => {
    for (const apiBaseUrl of ['https://user:secret@example.test', 'file:///c:/data', 'https://host.test/?token=secret', 'https://host.test/#fragment']) {
      const cfg = networkConfig(); cfg.profiles.server.apiBaseUrl = apiBaseUrl
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply(cfg)))
      await expect(loadNetworkConfig()).rejects.toThrow('NETWORK_CONFIG_INVALID')
    }
  })
  it('rejects synthetic capabilities before fetching a snapshot in the real workspace', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply({ ...measuredCapabilities, mock: true })))
    await expect(new NetworkClient('').capabilities()).rejects.toThrow('NETWORK_SYNTHETIC_REJECTED')
  })
  it('rejects synthetic and undeclared network-v1 live data in the real workspace', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(reply(makeSnapshot())).mockResolvedValueOnce(reply({ ...declaredMeasuredFixture(), provenance: 'unknown' })))
    await expect(new NetworkClient('').snapshot()).rejects.toThrow('NETWORK_SYNTHETIC_REJECTED')
    await expect(new NetworkClient('').snapshot()).rejects.toThrow('NETWORK_PROVENANCE_UNVERIFIED')
  })
  it('rejects nested fake GPS even when the root claims measured provenance', async () => {
    const s = declaredMeasuredFixture(); s.nodes[1]!.position!.source = 'synthetic'
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply(s)))
    await expect(new NetworkClient('').snapshot()).rejects.toThrow('NETWORK_SYNTHETIC_REJECTED')
  })
  it('isolated mock accepts only synthetic data and rejects real capabilities and snapshots', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(reply(makeSnapshot())).mockResolvedValueOnce(reply(measuredCapabilities)).mockResolvedValueOnce(reply(declaredMeasuredFixture())))
    expect((await mockClient().snapshot()).provenance).toBe('synthetic')
    await expect(mockClient().capabilities()).rejects.toThrow('NETWORK_REAL_DATA_IN_MOCK')
    await expect(mockClient().snapshot()).rejects.toThrow('NETWORK_REAL_DATA_IN_MOCK')
  })
  it('rejects either provenance being mixed into the other workspace replay', async () => {
    const real = declaredMeasuredFixture(), fake = makeSnapshot({ at: 101000 })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply({ schema: 'network.replay.v1', id: 'mixed', frames: [real, fake] })))
    await expect(new NetworkClient('').replay('mixed')).rejects.toThrow('NETWORK_SYNTHETIC_REJECTED')
    await expect(mockClient().replay('mixed')).rejects.toThrow('NETWORK_REAL_DATA_IN_MOCK')
  })
  it('refuses a recording list with the wrong provenance', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply([{ id: 'demo', label: 'Demo', startedAt: 100000, frames: 2, synthetic: true }])))
    await expect(new NetworkClient('').sessions()).rejects.toThrow('NETWORK_REPLAY_PROVENANCE_MISMATCH')
  })
  it('keeps local normalized gateway reads read-only even if capabilities advertise writes', async () => {
    const fetcher = vi.fn().mockResolvedValue(reply({ ...measuredCapabilities, recording: true, sourceSelection: true }))
    vi.stubGlobal('fetch', fetcher)
    const client = new NetworkClient('http://gateway.test', { mode: 'gateway' })
    const caps = await client.capabilities(); expect(caps.recording).toBe(false); expect(caps.sourceSelection).toBe(false)
    await expect(client.record('start')).rejects.toThrow('NETWORK_GATEWAY_READ_ONLY')
    await expect(client.selectSource('other')).rejects.toThrow('NETWORK_GATEWAY_READ_ONLY')
    expect(fetcher).toHaveBeenCalledTimes(1)
  })
  it('reads old gateway topology via a constrained relay without inventing measured provenance', async () => {
    const fetcher = vi.fn().mockResolvedValue(reply(legacyGatewayFixture())); vi.stubGlobal('fetch', fetcher)
    const client = new NetworkClient('http://gateway.test:8794', { mode: 'gateway', protocol: 'lora-v1', gatewayRelayPath: '/__network_gateway' })
    expect((await client.capabilities()).recording).toBe(false)
    const s = await client.snapshot(); expect(s.provenance).toBe('unknown'); expect(s.nodes[1]!.label).toBe('NODE 01')
    const [url, options] = fetcher.mock.calls[0]!
    expect(url).toContain('/__network_gateway?base=http%3A%2F%2Fgateway.test%3A8794')
    expect(url).toContain('resource=%2Fapi%2Fv1%2Flora%2Ftopology'); expect(options.headers['X-Network-Gateway']).toBe('readonly')
    expect(options.method).toBe('GET'); expect(fetcher).toHaveBeenCalledTimes(1)
  })
  it('does not allow the demo entry to use a legacy gateway client', () => {
    expect(() => new NetworkClient('http://gateway.test', { workspace: 'mock', mode: 'gateway', protocol: 'lora-v1' })).toThrow('NETWORK_MOCK_CONFIG_INVALID')
  })
  it('loads a different config file for each entry and rejects HTTPS mixed content unless relayed', async () => {
    const fetcher = vi.fn().mockResolvedValue(reply(networkConfig(false))); vi.stubGlobal('fetch', fetcher)
    await loadNetworkConfig('real'); await loadNetworkConfig('mock')
    expect(fetcher.mock.calls.map(c => c[0])).toEqual(['/network-config.json', '/network-mock-config.json'])
    vi.stubGlobal('location', { origin: 'https://web.test', protocol: 'https:' })
    expect(() => new NetworkClient('http://server.test')).toThrow('NETWORK_MIXED_CONTENT')
    expect(() => new NetworkClient('http://gateway.test', { mode: 'gateway', gatewayRelayPath: '/__network_gateway' })).not.toThrow()
  })
})
