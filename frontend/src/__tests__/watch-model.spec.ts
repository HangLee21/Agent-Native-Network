import { describe, expect, it } from 'vitest'
import type { FlightCommand, FlightEvent, Sample } from '@/api/history'
import {
  buildFlight, buildPairs, footCorners, makeScene, mapCut, pairMinAt, stateAt, timelineCut, type FlightInput,
} from '@/views/watch/model'

const T0 = 1_793_853_800_000
const LAT = 29.6032, LON = 103.5949

/** A flight going east at 5 m/s, `modes` one per 2 s, height 25 m once airborne. */
function samples(modes: number[], eastOffset = 0, height = 25): Sample[] {
  return modes.map((m, i) => {
    const air = ![0, 1, 2].includes(m)
    const east = eastOffset + i * 10
    return {
      ts: T0 + i * 2000 + 1500, deviceTs: T0 + i * 2000, sampleSource: 'OSD', lat: LAT, lon: LON + east / (111320 * Math.cos(LAT * Math.PI / 180)),
      ellipsoidHeight: 350 + (air ? height : 0), relativeHeight: air ? height : 0, drcHeight: null, horizontalSpeed: air ? 5 : 0, verticalSpeed: 0,
      attitudeHead: 90, attitudePitch: null, attitudeRoll: null, gimbalPitch: -90, gimbalYaw: 90, gimbalRoll: null, zoomFactor: null, battery: 80 - i,
      remainFlightTime: null, returnHomePower: null, modeCode: m, gpsNumber: 30, rtkNumber: null, windSpeed: 1, windDirection: null, homeDistance: null, heightLimit: null,
    }
  })
}
function input(id: string, s: Sample[], over: Partial<FlightInput> = {}): FlightInput {
  const events: FlightEvent[] = [{ id: 1, ts: T0 + 5000, eventType: 'EXECUTION', eventLevel: 'INFO', title: '航线执行：飞向航点 1', payload: { state: 'FLYING', currentIndex: 0, total: 3 } }]
  const commands: FlightCommand[] = [{ id: 'c1', commandType: 'FlyToPoint', label: '航线执行：飞向航点 1', channel: null, status: 'ACKED', createdAt: T0 + 5000, sentAt: T0 + 5000, completedAt: T0 + 5100, resultCode: 0, message: '设备已确认', params: null }]
  return {
    id, gatewaySn: `RC-${id}`, label: id, color: '#4a90e8', devName: 'Matrice 4E', droneSn: `SN-${id}`,
    detail: { takeoffLat: LAT, takeoffLon: LON, takeoffEllipsoidHeight: 350, homeLat: LAT, homeLon: LON, takeoffAt: T0 + 2000, clockOffsetMs: 1500, routeName: '双机A', routeSnapshot: null, outcome: 'COMPLETED', rawAtTakeoff: null },
    samples: s, events, commands, live: false, sessionId: id, ...over,
  }
}

describe('监视台 model', () => {
  it('cut-off: live and a replay with the route hidden stop at the watched moment; the timeline in live goes to now', () => {
    expect(mapCut('live', false, 100)).toBe(100)
    expect(mapCut('replay', true, 100)).toBe(100)
    expect(mapCut('replay', false, 100)).toBe(Infinity)
    expect(timelineCut('live', true, 100, 500)).toBe(500)
    expect(timelineCut('replay', true, 100, 500)).toBe(100)
    expect(timelineCut('replay', false, 100, 500)).toBe(Infinity)
  })

  it('audience feed lists only the aircraft state changes, never routes or commands', () => {
    const inp = input('A', samples([0, 1, 4, 17, 17, 15, 17, 9, 10, 0]))
    const f = buildFlight(makeScene([inp]), inp)!
    expect(f.plog.map((r) => r.title)).toEqual(['起飞', '遇到障碍，自动避障', '避开障碍，继续飞行', '开始返航', '开始降落', '已降落'])
    expect(f.plog.some((r) => /航线|航点|指令/.test(r.title))).toBe(false)
    // the engineering feed still has them
    expect(f.log.some((r) => r.kind === 'cmd')).toBe(true)
    expect(f.phaseSegs.map((s) => s.ph)).toEqual(['ground', 'ready', 'takeoff', 'fly', 'avoid', 'fly', 'rth', 'land', 'ground'])
  })

  it('a live flight keeps its last state past the last sample and reports how stale it is', () => {
    const inp = input('A', samples([0, 4, 17, 17]), { live: true })
    const f = buildFlight(makeScene([inp]), inp)!
    const st = stateAt(f, f.t1 + 8000)
    expect(st.inside).toBe(true)
    expect(st.stale).toBe(8000)
    expect(st.rel).toBeCloseTo(25)
    const closed = buildFlight(makeScene([inp]), { ...inp, live: false })!
    expect(stateAt(closed, closed.t1 + 8000).after).toBe(true)
  })

  it('closest approach so far: only moments up to the cut count', () => {
    // B flies parallel 60 m south of A, then crosses closer to 12 m and leaves again
    const a = samples([0, 4, 17, 17, 17, 17, 17, 17])
    const b = samples([0, 4, 17, 17, 17, 17, 17, 17]).map((s, i) => ({ ...s, lat: LAT - [60, 60, 60, 40, 12, 40, 60, 60][i]! / 111320 }))
    const ia = input('A', a), ib = input('B', b)
    const sc = makeScene([ia, ib])
    const pairs = buildPairs([buildFlight(sc, ia)!, buildFlight(sc, ib)!])
    expect(pairs).toHaveLength(1)
    const p = pairs[0]!
    expect(pairMinAt(p, Infinity)!.d).toBeLessThan(13)
    const early = pairMinAt(p, T0 + 6000)!
    expect(early.d).toBeGreaterThan(39)
    expect(early.t).toBeLessThanOrEqual(T0 + 6000)
  })

  it('camera footprint: straight down when asked, ahead of the aircraft and capped when the gimbal looks forward', () => {
    const st = { x: 0, y: 0, z: 25, rel: 25, gp: -30, gy: 0, head: 0 }
    const nadir = footCorners(st, 'nadir')!
    const cy = nadir.reduce((s, c) => s + c[1], 0) / 4
    expect(Math.abs(cy)).toBeLessThan(1e-6)
    const fwd = footCorners(st, 'gimbal')!
    expect(Math.min(...fwd.map((c) => c[1]))).toBeGreaterThan(10)
    expect(Math.max(...fwd.map((c) => Math.hypot(c[0], c[1])))).toBeLessThanOrEqual(100.01)
    expect(footCorners({ ...st, rel: 1 }, 'nadir')).toBeNull()
  })
})
