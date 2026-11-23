import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'
import SafetyReport from '@/components/route/SafetyReport.vue'
import { useSafetyStore } from '@/stores/safety'
import { useMapOverlaysStore } from '@/stores/overlays'
import { violationsOf } from '@/api/safety'

describe('safety layer UI (S-01, S-02)', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('lists violations and links them to waypoints', () => {
    const w = mount(SafetyReport, {
      props: {
        checking: false,
        error: null,
        result: { passed: false, violations: [{ code: 'ABOVE_HEIGHT_LIMIT', message: '航点 2：高度 150 m 超过平台限高 120 m', waypointIndex: 1 }] },
      },
    })
    expect(w.text()).toContain('安全检查未通过（1 项）')
    expect(w.text()).toContain('超过平台限高')
  })

  it('shows the safe zone layer only when enabled', () => {
    const s = useSafetyStore()
    const ov = useMapOverlaysStore()
    const base = { maxHeight: 120, minHeight: 20, maxSpeed: 15, minTakeoffBattery: 25, unknownHeightPolicy: 'DUAL_CHECK' as const, updatedAt: 0 }
    const zone: [number, number][] = [[1, 1], [1, 2], [2, 2]]
    s.apply({ ...base, safeZoneEnabled: false, safeZone: zone })
    expect(ov.safeZone).toBeNull()
    s.apply({ ...base, safeZoneEnabled: true, safeZone: zone })
    expect(ov.safeZone).toHaveLength(3)
  })

  it('extracts violations from a 422 error body', () => {
    expect(violationsOf({ passed: false, violations: [{ code: 'X', message: 'm', waypointIndex: null }] })).toHaveLength(1)
    expect(violationsOf(null)).toEqual([])
  })
})
