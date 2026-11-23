import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'
import { frameRect, toFrame, toFrameBox } from '@/utils/videoCoords'
import { targetMarks, targetsAt } from '@/utils/replay'
import type { TargetConfig, TargetView } from '@/api/targets'
import { DP, useTestDrone } from './testDrone'
import { useTargetsStore } from '@/stores/targets'
import { useControlStore } from '@/stores/control'
import TargetCard from '@/components/target/TargetCard.vue'
import type { FlightEvent } from '@/api/history'

function target(over: Partial<TargetView> = {}): TargetView {
  return {
    id: 't1', createdAt: 1, updatedAt: 1, source: 'OPERATOR', label: null, confidence: null, input: 'TAP',
    image: { lens: 'wide', x: 0.5, y: 0.8, w: 0, h: 0, frameTimestamp: null }, state: 'MEASURED', method: 'LASER',
    lat: 22.58, lon: 113.94, ellipsoidHeight: 25, relativeHeight: 0, distance: 120, accuracyM: 0.8, laserState: 'NORMAL',
    rawAltitude: 25, altitudeReference: 'ELLIPSOID', geoidOffsetM: null, lowConfidence: false, zoomAtSelect: 2, message: null,
    warnings: [], action: null, suggestedAction: null, stopPoint: null, backPoint: null, commandId: null, check: null, expiresAt: null,
    ...over,
  }
}

function config(over: Partial<TargetConfig> = {}): TargetConfig {
  return {
    laserFlyToEnabled: true, laserAltitudeReference: 'ELLIPSOID', geoidOffsetM: 0, minDistanceM: 10, stopDistanceM: 30, clearanceM: 10,
    maxLaserRangeM: 500, maxAccuracyM: 10, approachSpeed: 5, aboveHeightM: 30, aiLookLevel: 0, aiApproachLevel: 0, aiAboveLevel: 0,
    aiOrbitLevel: 0, aiMinConfidence: 0.8, aiMaxMoveM: 100, aiStopDistanceM: 50, aiExtraHeightM: 10, aiMaxAccuracyM: 5, aiCooldownS: 10,
    aiMaxPerMinute: 4, aiCountdownS: 5, aiForbiddenMoveLabels: ['person'], aiAllowedMoveLabels: [], aiWorkArea: [], updatedAt: 1,
    ...over,
  }
}

describe('click mapping on the letterboxed video (D-21)', () => {
  it('maps clicks to the visible frame and ignores the black bars', () => {
    // 1000×800 panel, 1920×1080 stream → 1000×562.5 frame, bars of 118.75 px top and bottom
    const r = frameRect(1000, 800, 1920, 1080)
    expect(r.width).toBeCloseTo(1000)
    expect(r.top).toBeCloseTo(118.75)
    expect(toFrame(500, 400, r)).toEqual({ x: 0.5, y: 0.5 })
    expect(toFrame(500, 50, r)).toBeNull() // on the top bar
    const corner = toFrame(0.001, 118.76, r)!
    expect(corner.x).toBeCloseTo(0)
    expect(corner.y).toBeCloseTo(0)
    // pillarbox: tall stream in a wide panel
    const p = frameRect(1600, 900, 1080, 1080)
    expect(p.left).toBe(350)
    expect(toFrame(100, 450, p)).toBeNull()
  })

  it('turns a drag into a normalised box clamped to the frame', () => {
    const r = frameRect(1000, 800, 1920, 1080)
    const b = toFrameBox(400, 300, 600, 500, r)!
    expect(b.x).toBeCloseTo(0.4)
    expect(b.w).toBeCloseTo(0.2)
    expect(b.y).toBeCloseTo((300 - 118.75) / 562.5)
    expect(toFrameBox(400, 0, 600, 60, r)).toBeNull() // entirely on the bar
    expect(toFrameBox(-50, 300, 100, 500, r)!.x).toBe(0) // clamped
    expect(frameRect(1000, 800, 0, 0)).toEqual({ left: 0, top: 0, width: 1000, height: 800 }) // unknown size: fills
  })
})

describe('targets store', () => {
  beforeEach(() => setActivePinia(createPinia()))
  afterEach(() => vi.restoreAllMocks())

  it('upserts targets from broadcasts and keeps the newest snapshot', () => {
    const s = useTargetsStore()
    s.onTargetEvent({ event: 'TARGET_SELECTED', level: 'INFO', title: '', targetId: 't1', target: target({ state: 'MEASURING', updatedAt: 5 }) })
    s.onTargetEvent({ event: 'TARGET_MEASURED', level: 'INFO', title: '', targetId: 't1', target: target({ updatedAt: 9 }) })
    s.onTargetEvent({ event: 'TARGET_UPDATED', level: 'INFO', title: '', targetId: 't1', target: target({ state: 'MEASURING', updatedAt: 7 }) })
    expect(s.targets).toHaveLength(1)
    expect(s.targets[0]!.state).toBe('MEASURED')
    expect(s.selected?.id).toBe('t1')
    s.onTargetEvent({ event: 'TARGET_ACTION', level: 'INFO', title: '建议垂直爬升', targetId: 't1', decision: 'CLIMB_ONLY', target: target({ updatedAt: 10 }) })
    expect(s.decisions.t1!.decision).toBe('CLIMB_ONLY')
  })

  it('does not let an action reply built in the same millisecond bring a finished target back', () => {
    const s = useTargetsStore()
    // mock poi_enter is acknowledged at once: the end is pushed before the HTTP reply (same updatedAt) arrives
    s.upsert(target({ state: 'DONE', action: 'ORBIT', updatedAt: 20 }))
    s.upsert(target({ state: 'ACTIVE', action: 'ORBIT', updatedAt: 20 }))
    expect(s.targets[0]!.state).toBe('DONE')
    expect(s.active).toBeNull()
    s.upsert(target({ state: 'MEASURING', updatedAt: 21 }))
    expect(s.targets[0]!.state).toBe('MEASURING')
  })

  it('shows refusal reasons from the safety layer instead of a generic error', async () => {
    useTestDrone()
    const s = useTargetsStore()
    const refusal = { message: '安全检查未通过', details: { passed: false, violations: [{ code: 'TOO_CLOSE', message: '距目标 5 m，小于安全距离 10 m，不移动' }] } }
    const fetch = vi.fn(async (url: string) => String(url).endsWith('/targets/t1/actions')
      ? new Response(JSON.stringify(refusal), { status: 422 })
      : new Response(JSON.stringify({ targets: [], active: null, laser: null, config: config(), ai: null }), { status: 200 }))
    vi.stubGlobal('fetch', fetch)
    await s.act('t1', 'APPROACH')
    expect(s.lastError).toContain('不移动')
    expect(String(fetch.mock.calls[0]![0])).toContain(`${DP}/targets/t1/actions`) // the test drone's endpoint (D-29)
    vi.unstubAllGlobals()
  })
})

describe('target card', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('locks movement while the laser height reference is unconfirmed but keeps Look and Mark', () => {
    const s = useTargetsStore()
    s.config = config({ laserFlyToEnabled: false, laserAltitudeReference: 'UNKNOWN' })
    useControlStore().snapshot = { control: 'GRANTED', drcReady: true } as never
    const w = mount(TargetCard, { props: { target: target({ ellipsoidHeight: null, relativeHeight: null, altitudeReference: 'UNKNOWN' }) } })
    expect(w.find('[data-test=target-approach]').attributes('disabled')).toBeDefined()
    expect(w.find('[data-test=target-look]').attributes('disabled')).toBeUndefined()
    expect(w.text()).toContain('激光高度参考系是“未确认”')
    expect(w.text()).toContain('参考系未确认')
  })

  it('enables movement once laser fly-to is on, shows Stop while moving and Accept for AI proposals', () => {
    const s = useTargetsStore()
    s.config = config()
    useControlStore().snapshot = { control: 'GRANTED', drcReady: true } as never
    const w = mount(TargetCard, { props: { target: target() } })
    expect(w.find('[data-test=target-approach]').attributes('disabled')).toBeUndefined()
    const moving = mount(TargetCard, { props: { target: target({ state: 'ACTIVE', action: 'APPROACH' }) } })
    expect(moving.find('[data-test=target-stop]').exists()).toBe(true)
    expect(moving.find('[data-test=target-approach]').exists()).toBe(false)
    const ai = mount(TargetCard, { props: { target: target({ state: 'PROPOSED', source: 'AI:detector', label: 'vehicle', confidence: 0.91, lat: null, lon: null }) } })
    expect(ai.find('[data-test=target-accept]').exists()).toBe(true)
    expect(ai.text()).toContain('AI 只能建议目标')
  })
})

describe('replay target pins (flight history)', () => {
  const ev = (ts: number, eventType: string, payload: Record<string, unknown>): FlightEvent =>
    ({ id: ts, ts, eventType, eventLevel: 'INFO', title: eventType, payload })

  it('groups target snapshots by id and follows the cursor', () => {
    const events = [
      ev(10, 'TARGET_SELECTED', { targetId: 'a', target: { id: 'a', state: 'MEASURING', lat: null, lon: null } }),
      ev(20, 'TARGET_MEASURED', { targetId: 'a', target: { id: 'a', state: 'MEASURED', lat: 22.58, lon: 113.94, accuracyM: 0.6 } }),
      ev(30, 'TARGET_ACTION', { targetId: 'a', target: { id: 'a', state: 'ACTIVE', lat: 22.58, lon: 113.94, stopPoint: { lat: 22.579, lon: 113.94 } } }),
      ev(40, 'TARGET_END', { targetId: 'a', target: { id: 'a', state: 'CANCELLED', lat: 22.58, lon: 113.94 } }),
      ev(25, 'AI_AUTO', { on: true }),
    ].sort((x, y) => x.ts - y.ts)
    expect(targetsAt(events, 15)).toHaveLength(0)
    expect(targetsAt(events, 22)[0]!.accuracyM).toBe(0.6)
    expect(targetsAt(events, 35)[0]!.stop).toEqual({ lat: 22.579, lon: 113.94 })
    expect(targetsAt(events, 45)).toHaveLength(0) // cancelled
    expect(targetMarks(events).map((m) => m.kind)).toEqual(['TARGET_SELECTED', 'TARGET_MEASURED', 'AI_AUTO', 'TARGET_ACTION', 'TARGET_END'])
  })
})
