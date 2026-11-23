import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import VideoPanel from '@/components/video/VideoPanel.vue'
import FlightHud from '@/components/video/FlightHud.vue'
import { playWhep, type LiveStatus } from '@/api/live'
import { useLiveStore } from '@/stores/live'
import { useTelemetryStore } from '@/stores/telemetry'
import { useControlStore } from '@/stores/control'

vi.mock('@/api/live', async (importOriginal) => ({ ...(await importOriginal<typeof import('@/api/live')>()), playWhep: vi.fn() }))

/** A stand-in for hls.js: records each player so a test can fire its events. */
type Handler = (event: string, data: { fatal?: boolean; details?: string }) => void
const hlsMock = vi.hoisted(() => ({ players: [] as { url: string; destroyed: boolean; handlers: Record<string, Handler> }[] }))
vi.mock('hls.js', () => {
  class FakeHls {
    static Events = { ERROR: 'hlsError', MANIFEST_PARSED: 'hlsManifestParsed' }
    static isSupported = () => true
    url = ''
    destroyed = false
    handlers: Record<string, Handler> = {}
    constructor() {
      hlsMock.players.push(this)
    }
    on(event: string, fn: Handler) {
      this.handlers[event] = fn
    }
    loadSource(url: string) {
      this.url = url
    }
    attachMedia() {}
    destroy() {
      this.destroyed = true
    }
  }
  return { default: FakeHls }
})
const fire = (i: number, event: string, data: { fatal?: boolean; details?: string } = {}) => hlsMock.players[i]!.handlers[event]?.(event, data)

const whep = (url = 'http://media/live/v/whep'): LiveStatus =>
  ({ videoId: 'v', streaming: true, quality: 0, lens: 'wide', playback: { protocol: 'WHEP', url }, lenses: ['wide', 'zoom'], pushConfigured: true })
const fakeConnection = () => ({ close: vi.fn() }) as unknown as RTCPeerConnection
const notReady = () => new Error('WHEP 请求失败（HTTP 404）')
function online(): void {
  const tel = useTelemetryStore()
  tel.gateway = { mode: 'cloudapi', gatewaySn: 'RC', droneSn: 'M4E', gatewayOnline: true, droneOnline: true, droneModel: null, rcModel: null }
  tel.lastUpdateAt = Date.now()
  tel.now = Date.now()
}

describe('live video with telemetry (R-14, R-15)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.mocked(playWhep).mockReset()
    vi.stubGlobal('requestAnimationFrame', () => 0)
    vi.stubGlobal('cancelAnimationFrame', () => undefined)
  })

  it('shows the "video not started" state with a start button', () => {
    const tel = useTelemetryStore()
    tel.gateway = { mode: 'mock', gatewaySn: 'RC', droneSn: 'M4E', gatewayOnline: true, droneOnline: true, droneModel: null, rcModel: null }
    tel.lastUpdateAt = Date.now()
    useLiveStore().status = { videoId: 'v', streaming: false, quality: 0, lens: 'wide', playback: null, lenses: [], pushConfigured: true }
    const w = mount(VideoPanel)
    expect(w.text()).toContain('视频未开启')
    expect(w.find('[data-test=start-video]').attributes('disabled')).toBeUndefined()
  })

  it('renders the stream with the flight HUD when streaming (mock playback)', () => {
    useLiveStore().status = { videoId: 'v', streaming: true, quality: 0, lens: 'wide', playback: { protocol: 'MOCK', url: null }, lenses: ['wide', 'zoom', 'ir'], pushConfigured: true }
    const w = mount(VideoPanel)
    expect(w.find('[data-test=mock-feed]').exists()).toBe(true)
    expect(w.find('[data-test=hud]').exists()).toBe(true)
    expect(w.text()).toContain('关闭视频')
    expect(w.text()).toContain('红外')
  })

  it('marks the picture as not live when the device link is lost', () => {
    useLiveStore().status = { videoId: 'v', streaming: true, quality: 0, lens: 'wide', playback: { protocol: 'MOCK', url: null }, lenses: [], pushConfigured: true }
    const w = mount(VideoPanel) // telemetry store has no fresh data -> offline
    expect(w.find('[data-test=video-link-lost]').exists()).toBe(true)
    expect(w.text()).toContain('设备连接中断')
  })

  it('connects when mounted with the stream already running (back to the monitor from another page)', async () => {
    const conn = fakeConnection()
    vi.mocked(playWhep).mockResolvedValue(conn)
    online()
    useLiveStore().status = whep()
    const w = mount(VideoPanel)
    await flushPromises()
    expect(playWhep).toHaveBeenCalledTimes(1)
    expect(vi.mocked(playWhep).mock.calls[0]).toEqual(['http://media/live/v/whep', w.find('video').element])
    expect(w.text()).not.toContain('正在连接')
    w.unmount()
    expect(conn.close).toHaveBeenCalled()
  })

  it('keeps the connection on a status push with the same stream and reconnects when the stream changes', async () => {
    const first = fakeConnection()
    vi.mocked(playWhep).mockResolvedValueOnce(first).mockResolvedValueOnce(fakeConnection())
    const live = useLiveStore()
    live.status = whep()
    mount(VideoPanel)
    await flushPromises()
    live.status = { ...whep(), lens: 'zoom' }
    await flushPromises()
    live.status = { ...whep(), quality: 2 }
    await flushPromises()
    expect(playWhep).toHaveBeenCalledTimes(1)
    expect(first.close).not.toHaveBeenCalled()
    live.status = whep('http://media/live/v2/whep')
    await flushPromises()
    expect(playWhep).toHaveBeenCalledTimes(2)
    expect(first.close).toHaveBeenCalled()
  })

  it('closes a connection that completes after the monitor was left', async () => {
    let finish: (c: RTCPeerConnection) => void = () => undefined
    vi.mocked(playWhep).mockReturnValue(new Promise((r) => (finish = r)))
    online()
    useLiveStore().status = whep()
    const w = mount(VideoPanel)
    await flushPromises()
    expect(w.text()).toContain('正在连接')
    w.unmount()
    const late = fakeConnection()
    finish(late)
    await flushPromises()
    expect(late.close).toHaveBeenCalled()
  })

  it('HUD shows height, speeds, aircraft pitch and gimbal pitch', () => {
    const w = mount(FlightHud)
    for (const label of ['相对高度', '垂直速度', '水平速度', '飞机俯仰', '云台俯仰', '电量']) expect(w.text()).toContain(label)
  })
})

/**
 * First connection right after the drone starts pushing (2026-11-04 field test): the media server is not ready yet,
 * so the player keeps retrying for about 30 s and shows "connecting" instead of failing at once.
 */
describe('live video: retries while the stream is starting', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.mocked(playWhep).mockReset()
    hlsMock.players.length = 0
    vi.stubGlobal('requestAnimationFrame', () => 0)
    vi.stubGlobal('cancelAnimationFrame', () => undefined)
    // only the retry timers and the clock are faked: flushPromises keeps its real setImmediate
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'Date'] })
    online()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('retries a stream that is not ready yet and plays once it is, without showing an error', async () => {
    const conn = fakeConnection()
    vi.mocked(playWhep).mockRejectedValueOnce(notReady()).mockRejectedValueOnce(notReady()).mockResolvedValue(conn)
    useLiveStore().status = whep()
    const w = mount(VideoPanel)
    await flushPromises()
    expect(playWhep).toHaveBeenCalledTimes(1)
    expect(w.find('[data-test=video-connecting]').text()).toContain('正在连接视频')
    expect(w.find('[data-test=video-error]').exists()).toBe(false)

    await vi.advanceTimersByTimeAsync(2000)
    await flushPromises()
    expect(playWhep).toHaveBeenCalledTimes(2)
    expect(w.find('[data-test=video-connecting]').text()).toContain('正在自动重试')
    expect(w.text()).not.toContain('视频连接失败')

    await vi.advanceTimersByTimeAsync(2000)
    await flushPromises()
    expect(playWhep).toHaveBeenCalledTimes(3)
    expect(w.find('[data-test=video-connecting]').exists()).toBe(false)
    expect(w.find('[data-test=video-error]').exists()).toBe(false)
    expect(vi.getTimerCount()).toBe(0)
    w.unmount()
    expect(conn.close).toHaveBeenCalled()
  })

  it('field case 2026-11-05: the RC says "pushing" but nothing arrives, so 重新开启视频 sends the start command again', async () => {
    vi.mocked(playWhep).mockRejectedValue(notReady())
    useLiveStore().status = whep()
    const w = mount(VideoPanel)
    await flushPromises()
    expect(w.find('[data-test=video-restart]').exists()).toBe(false) // first try: no button yet
    await vi.advanceTimersByTimeAsync(2000)
    await flushPromises()
    await w.find('[data-test=video-connecting] [data-test=video-restart]').trigger('click')
    await flushPromises()
    // the start command went through the normal command path (no drone selected in this test, so it is refused locally)
    expect(useControlStore().byAction('live')?.label).toBe('开启直播')

    await vi.advanceTimersByTimeAsync(35_000) // gave up: the error offers it as well
    await flushPromises()
    expect(w.find('[data-test=video-error] [data-test=video-restart]').exists()).toBe(true)
    w.unmount()
  })

  it('shows the error with 重试 only after about 30 s, and 重试 starts a new window', async () => {
    vi.mocked(playWhep).mockRejectedValue(notReady())
    useLiveStore().status = whep()
    const w = mount(VideoPanel)
    await flushPromises()

    await vi.advanceTimersByTimeAsync(25_000)
    await flushPromises()
    expect(w.find('[data-test=video-connecting]').exists()).toBe(true)
    expect(w.find('[data-test=video-error]').exists()).toBe(false)

    await vi.advanceTimersByTimeAsync(10_000)
    await flushPromises()
    const tries = vi.mocked(playWhep).mock.calls.length
    expect(tries).toBeGreaterThanOrEqual(10) // 2 s, 2 s, 2 s, then every 3 s
    expect(tries).toBeLessThanOrEqual(12)
    expect(w.find('[data-test=video-connecting]').exists()).toBe(false)
    expect(w.find('[data-test=video-error]').text()).toContain('视频连接失败：WHEP 请求失败（HTTP 404）')
    expect(vi.getTimerCount()).toBe(0) // gave up: nothing left running

    await vi.advanceTimersByTimeAsync(10_000)
    expect(playWhep).toHaveBeenCalledTimes(tries)

    // 重试: a fresh window, so it keeps retrying again instead of failing at once
    await w.find('[data-test=video-retry]').trigger('click')
    await flushPromises()
    expect(playWhep).toHaveBeenCalledTimes(tries + 1)
    expect(w.find('[data-test=video-connecting]').exists()).toBe(true)
    expect(w.find('[data-test=video-error]').exists()).toBe(false)
    await vi.advanceTimersByTimeAsync(2000)
    await flushPromises()
    expect(playWhep).toHaveBeenCalledTimes(tries + 2)
    expect(w.find('[data-test=video-error]').exists()).toBe(false)
  })

  it('field case: WHEP 404 then HLS manifestLoadError is retried until the HLS playlist loads', async () => {
    vi.mocked(playWhep).mockRejectedValue(notReady())
    useLiveStore().status = { ...whep(), playback: { protocol: 'WHEP', url: 'http://media/live/v/whep', fallbackUrl: 'http://media/live/v/index.m3u8' } }
    const w = mount(VideoPanel)
    await flushPromises()
    expect(hlsMock.players).toHaveLength(1)
    expect(hlsMock.players[0]!.url).toBe('http://media/live/v/index.m3u8')

    fire(0, 'hlsError', { fatal: true, details: 'manifestLoadError' })
    await flushPromises()
    expect(w.text()).not.toContain('manifestLoadError')
    expect(w.find('[data-test=video-connecting]').exists()).toBe(true)

    await vi.advanceTimersByTimeAsync(2000)
    await flushPromises()
    expect(playWhep).toHaveBeenCalledTimes(2) // the whole sequence again: WHEP first, then HLS
    expect(hlsMock.players).toHaveLength(2)
    expect(hlsMock.players[0]!.destroyed).toBe(true)
    expect(w.find('[data-test=video-connecting]').exists()).toBe(true)

    fire(1, 'hlsManifestParsed')
    await flushPromises()
    expect(w.find('[data-test=video-connecting]').exists()).toBe(false)
    expect(w.find('[data-test=video-error]').exists()).toBe(false)
    // a late report from the first (failed) player changes nothing
    fire(0, 'hlsError', { fatal: true, details: 'manifestLoadError' })
    await vi.advanceTimersByTimeAsync(5000)
    expect(hlsMock.players).toHaveLength(2)
    expect(vi.getTimerCount()).toBe(0)
  })

  it('stops retrying when the panel is unmounted or the stream changes', async () => {
    vi.mocked(playWhep).mockRejectedValue(notReady())
    const live = useLiveStore()
    live.status = whep()
    const w = mount(VideoPanel)
    await flushPromises()
    expect(vi.getTimerCount()).toBe(1)

    // a new stream: the pending retry of the old one is dropped, a new window starts
    live.status = whep('http://media/live/v2/whep')
    await flushPromises()
    expect(vi.mocked(playWhep).mock.calls.map((c) => c[0])).toEqual(['http://media/live/v/whep', 'http://media/live/v2/whep'])
    expect(vi.getTimerCount()).toBe(1)

    w.unmount()
    expect(vi.getTimerCount()).toBe(0)
    await vi.advanceTimersByTimeAsync(30_000)
    expect(playWhep).toHaveBeenCalledTimes(2)
  })
})
