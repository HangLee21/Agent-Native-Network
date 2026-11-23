import { describe, expect, it } from 'vitest'
import type { FlightCommand, FlightEvent, Sample } from '@/api/history'
import {
  alertMarks, elapsed, executionWindows, fillForward, indexAt, linkGaps, nextTime, phases, photoMarks, prevTime, sampleHeight, stateAt, videoAt,
} from '@/utils/replay'

function sample(ts: number, over: Partial<Sample> = {}): Sample {
  return {
    ts, deviceTs: ts, sampleSource: 'OSD', lat: 22.58, lon: 113.94, ellipsoidHeight: null, relativeHeight: null, drcHeight: null,
    horizontalSpeed: null, verticalSpeed: null, attitudeHead: null, attitudePitch: null, attitudeRoll: null, gimbalPitch: null,
    gimbalYaw: null, gimbalRoll: null, zoomFactor: null, battery: null, remainFlightTime: null, returnHomePower: null, modeCode: null,
    gpsNumber: null, rtkNumber: null, windSpeed: null, windDirection: null, homeDistance: null, heightLimit: null, ...over,
  }
}

function ev(ts: number, eventType: string, payload: Record<string, unknown> | null = null, eventLevel: FlightEvent['eventLevel'] = 'INFO'): FlightEvent {
  return { id: ts, ts, eventType, eventLevel, title: eventType, payload }
}

describe('replay helpers', () => {
  it('uses the OSD relative height, and the DRC height converted by its reference (ellipsoid, confirmed in the field)', () => {
    const drc = sample(0, { sampleSource: 'DRC', drcHeight: 65 })
    expect(sampleHeight(sample(0, { relativeHeight: 30 }), 25)).toBe(30)
    expect(sampleHeight(drc, 25)).toBe(40) // default: ellipsoid
    expect(sampleHeight(drc, 25, 'UNKNOWN')).toBeNull()
    expect(sampleHeight(drc, null)).toBeNull() // no take-off height to convert from
    expect(sampleHeight(drc, 25, 'ELLIPSOID')).toBe(40)
    expect(sampleHeight(drc, 25, 'RELATIVE')).toBe(65)
  })

  it('carries OSD values forward over DRC rows and interpolates position', () => {
    const filled = fillForward([
      sample(1000, { relativeHeight: 30, battery: 80, modeCode: 17, lat: 22.58 }),
      sample(1500, { sampleSource: 'DRC', lat: 22.581, drcHeight: 55 }),
      sample(2000, { sampleSource: 'DRC', lat: 22.582 }),
    ], 25, 'UNKNOWN')
    expect(filled[2]!.battery).toBe(80)
    expect(filled[2]!.modeCode).toBe(17)
    expect(filled[1]!.height).toBe(30) // DRC height not used while UNKNOWN
    expect(indexAt(filled, 1700)).toBe(1)
    expect(indexAt(filled, 500)).toBe(-1)
    expect(stateAt(filled, 1750)!.lat).toBeCloseTo(22.5815, 6)
  })

  it('charts the DRC height between OSD rows by default', () => {
    const filled = fillForward([
      sample(1000, { relativeHeight: 30 }),
      sample(1500, { sampleSource: 'DRC', drcHeight: 56 }),
      sample(2000, { sampleSource: 'DRC' }),
    ], 25)
    expect(filled.map((f) => f.height)).toEqual([30, 31, 31])
  })

  it('derives phases from the flight mode and marks route execution', () => {
    const filled = fillForward([0, 1000, 2000, 3000, 4000, 5000, 6000].map((ts, i) =>
      sample(ts, { modeCode: [0, 4, 17, 17, 9, 10, 0][i]! })), null)
    const events = [ev(1500, 'EXECUTION', { state: 'FLYING' }), ev(3500, 'EXECUTION', { state: 'COMPLETED' })]
    expect(executionWindows(events)).toEqual([[1500, 3500]])
    expect(phases(filled, events).map((p) => p.kind)).toEqual(['takeoff', 'route', 'rth', 'landing'])
    // standby after landing does not stretch the landing phase
    const landed = fillForward([0, 1000, 2000, 3000, 4000].map((ts, i) => sample(ts, { modeCode: [10, 10, 0, 0, 0][i]! })), null)
    expect(phases(landed, [])).toEqual([{ kind: 'landing', start: 0, end: 2000 }])
  })

  it('finds link gaps, alerts and photos', () => {
    const filled = [{ ts: 0 }, { ts: 500 }, { ts: 9000 }, { ts: 9500 }]
    expect(linkGaps(filled, [])).toEqual([[500, 9000]])
    expect(linkGaps([{ ts: 0 }, { ts: 500 }], [ev(100, 'LINK_LOST'), ev(400, 'LINK_RESTORED')])).toEqual([[100, 400]])
    expect(alertMarks([ev(1, 'ALERT_RAISED', null, 'CRITICAL'), ev(2, 'ALERT_CLEARED')])).toHaveLength(1)
    const cmd = (commandType: string, status: FlightCommand['status']): FlightCommand => ({
      id: commandType, commandType, label: commandType, channel: 'DRC', status, createdAt: 10, sentAt: 11, completedAt: 12,
      resultCode: 0, message: null, params: null,
    })
    expect(photoMarks([cmd('TakePhoto', 'ACKED'), cmd('TakePhoto', 'FAILED'), cmd('ReturnHome', 'ACKED')])).toEqual([
      { ts: 12, kind: 'TakePhoto', level: 'INFO', label: '拍照' },
    ])
  })

  it('jumps between event times and maps the cursor to a video part', () => {
    expect(nextTime([10, 20, 30], 20)).toBe(30)
    expect(prevTime([10, 20, 30], 20)).toBe(10)
    expect(nextTime([10], 10)).toBeNull()
    const parts = [{ index: 0, startAt: 1000, durationMs: 5000 }, { index: 1, startAt: 8000, durationMs: 2000 }]
    expect(videoAt(parts, 3000, 0)).toEqual({ index: 0, seconds: 2 })
    expect(videoAt(parts, 7000, 0)).toBeNull()
    expect(videoAt(parts, 9500, 500)).toEqual({ index: 1, seconds: 1 })
    expect(elapsed(3_725_000)).toBe('1:02:05')
    expect(elapsed(65_000)).toBe('1:05')
  })
})
