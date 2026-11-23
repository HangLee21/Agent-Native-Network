import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useTelemetryStore } from '@/stores/telemetry'
import type { DroneTelemetry } from '@/api/types'
import { droneGroups, flattenRaw } from '@/components/drone/infoFields'

function sample(over: Partial<DroneTelemetry> = {}): DroneTelemetry {
  return {
    sn: 'M4E', timestamp: Date.now(), lat: 22.58, lon: 113.94, ellipsoidHeight: 45, relativeHeight: 20,
    horizontalSpeed: 5, verticalSpeed: 0, attitudePitch: -3, attitudeRoll: 0, attitudeHead: 90, gimbalPitch: -30,
    gimbalRoll: 0, gimbalYaw: 0, zoomFactor: 2, batteryPercent: 80, remainFlightTime: 1500, returnHomePower: 18,
    landingPower: 8, modeCode: 17, gear: 1, homeLat: 22.58, homeLon: 113.94, homeDistance: 10, heightLimit: 120,
    nearHeightLimit: false, nearAreaLimit: false, gpsNumber: 20, rtkNumber: 0, windSpeed: 3.2, windDirection: 3,
    controlSource: 'A', trackId: 't', highFrequency: false,
    raw: { battery: { capacity_percent: 80, batteries: [{ index: 0, voltage: 16000 }] }, mode_code: 17 }, ...over,
  }
}

describe('telemetry store (R-02, R-05)', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('tracks freshness, airborne state and the flight track', () => {
    const s = useTelemetryStore()
    s.gateway = { mode: 'mock', gatewaySn: 'RC', droneSn: 'M4E', gatewayOnline: true, droneOnline: true, droneModel: 'Matrice 4E', rcModel: 'DJI RC Plus 2' }
    s.applyTelemetry(sample({ modeCode: 0 }))
    s.applyTelemetry(sample({ lat: 22.581 }))
    s.applyTelemetry(sample({ lat: 22.582 }))
    expect(s.online).toBe(true)
    expect(s.airborne).toBe(true)
    expect(s.track.length).toBe(2)
  })

  it('merges high-frequency DRC telemetry into the last full snapshot', () => {
    const s = useTelemetryStore()
    s.applyTelemetry(sample())
    s.applyTelemetry(sample({ highFrequency: true, lat: 22.6, batteryPercent: null, raw: { drc_height: 70 } }))
    expect(s.drone?.lat).toBe(22.6)
    expect(s.drone?.batteryPercent).toBe(80)
    expect(s.drone?.raw.drc_height).toBe(70)
  })

  it('keeps the last fix while the drone reports no position, and says so', () => {
    const s = useTelemetryStore()
    s.applyTelemetry(sample({ modeCode: 0 }))
    expect(s.locating).toBe(false)
    // powered on without satellites: the backend passes lat/lon as null instead of the 0/0 the drone sends
    s.applyTelemetry(sample({ modeCode: 0, lat: null, lon: null, homeLat: null, homeLon: null, gpsNumber: 0 }))
    expect(s.locating).toBe(true)
    expect(s.position).toEqual({ lat: 22.58, lon: 113.94 })
    expect(s.home).toBeNull()
    const pos = droneGroups(s.drone, null).find((g) => g.title === '位置与高度')!.rows
    expect(pos.find((r) => r.label === '纬度')!.value).toBe('定位中')
    s.applyTelemetry(sample({ modeCode: 0, lat: 22.59 }))
    expect(s.locating).toBe(false)
    expect(s.position).toEqual({ lat: 22.59, lon: 113.94 })
  })

  it('has no position at all before the first fix', () => {
    const s = useTelemetryStore()
    s.applyTelemetry(sample({ modeCode: 0, lat: null, lon: null, gpsNumber: 0 }))
    expect(s.locating).toBe(true)
    expect(s.position).toBeNull()
  })

  it('exposes every raw field and labels height references explicitly', () => {
    const groups = droneGroups(sample(), null)
    const heights = groups.find((g) => g.title === '位置与高度')!.rows.map((r) => r.label)
    expect(heights).toContain('相对起飞点高度')
    expect(heights).toContain('椭球高')
    const raw = flattenRaw(sample().raw)
    expect(raw.map((r) => r.label)).toContain('battery.batteries[0].voltage')
  })
})
