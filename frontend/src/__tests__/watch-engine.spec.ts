import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { telemetrySocket } from '@/services/ws'
import { createWatchEngine } from '@/views/watch/engine'
import type { DeviceView } from '@/api/drones'

const dev: DeviceView = { droneSn: 'D1', gatewaySn: 'RC1', label: 'A', color: '#4a90e8', online: true, droneOnline: true, enabled: true, model: 'M4E', firstSeenAt: 1, lastSeenAt: 1, simulated: true }

function telemetry(i: number) {
  return {
    type: 'telemetry', ts: Date.now(), gatewaySn: 'RC1', droneSn: 'D1',
    data: { sn: 'D1', timestamp: 1_793_853_800_000 + i * 100, lat: 22.58 + i * 1e-6, lon: 113.94, ellipsoidHeight: 30, relativeHeight: 25, horizontalSpeed: 5, verticalSpeed: 0,
      attitudeHead: 0, gimbalPitch: -90, gimbalYaw: 0, batteryPercent: 90, modeCode: 17, gpsNumber: 30, windSpeed: 1, highFrequency: false },
  }
}

describe('监视台 engine (memory leak, 2026-11-09)', () => {
  beforeEach(() => { vi.spyOn(window, 'setInterval').mockReturnValue(0 as unknown as ReturnType<typeof setInterval>) })
  afterEach(() => vi.restoreAllMocks())

  it('live telemetry is merged at most twice a second, not on every message', () => {
    const E = createWatchEngine({ drones: [dev], byGateway: (sn) => (sn === 'RC1' || sn === 'D1' ? dev : undefined) }, () => null)
    E.startLive()
    E.syncLive([dev])
    const start = E.ui.version
    let now = 0
    // 10 telemetry messages per second for 5 s, one frame every 16 ms
    for (let i = 0; i < 50; i++) {
      telemetrySocket.dispatch(telemetry(i))
      for (let k = 0; k < 6; k++) { now += 16.7; E.step(now, 16.7) }
    }
    const rebuilds = E.ui.version - start
    expect(rebuilds).toBeGreaterThan(0)
    expect(rebuilds).toBeLessThanOrEqual(11)
    expect(E.S.flights).toHaveLength(1)
    E.stop()
  })

  it('a landed flight stays whole on the live screen after its record closes', async () => {
    const { historyApi } = await import('@/api/history')
    const samples = Array.from({ length: 600 }, (_, i) => ({ ...telemetry(i).data, ts: 1_793_853_800_000 + i * 100 + 50, deviceTs: 1_793_853_800_000 + i * 100, battery: 90, sampleSource: 'OSD' }))
    vi.spyOn(historyApi, 'get').mockResolvedValue({ id: 'S1', startedAt: 1_793_853_800_000, clockOffsetMs: 50, takeoffLat: 22.58, takeoffLon: 113.94, takeoffEllipsoidHeight: 5 } as never)
    vi.spyOn(historyApi, 'samples').mockResolvedValue(samples as never)
    vi.spyOn(historyApi, 'events').mockResolvedValue([])
    vi.spyOn(historyApi, 'commands').mockResolvedValue([])
    let current: string | null = 'S1'
    const E = createWatchEngine({ drones: [dev], byGateway: (sn) => (sn === 'RC1' || sn === 'D1' ? dev : undefined) }, () => current)
    E.startLive()
    E.syncLive([dev])
    await new Promise((r) => setTimeout(r, 0))
    let now = 0
    const frames = (n: number) => { for (let k = 0; k < n; k++) { now += 100; E.step(now, 100) } }
    frames(10)
    expect(E.S.flights[0]!.id).toBe('S1')
    expect(E.S.flights[0]!.n).toBe(600)
    // landed: the record closes, telemetry keeps coming from the drone on the ground
    current = null
    E.syncLive([dev])
    for (let i = 600; i < 1000; i++) { telemetrySocket.dispatch(telemetry(i)); frames(1) }
    frames(6) // past the half-second merge interval
    expect(E.S.flights[0]!.id).toBe('S1')
    expect(E.S.flights[0]!.n).toBe(1000)
    E.stop()
  })
})
