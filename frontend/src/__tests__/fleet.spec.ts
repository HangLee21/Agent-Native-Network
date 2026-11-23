import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent, h } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { setConfigForTest } from '@/config/runtime'
import { telemetrySocket } from '@/services/ws'
import { useFleetStore } from '@/stores/fleet'
import { useTelemetryStore } from '@/stores/telemetry'
import { useControlStore } from '@/stores/control'
import { useConfirmStore } from '@/stores/confirm'
import { useFlightActions } from '@/composables/useFlightActions'
import { controlApi } from '@/api/control'
import type { DroneTelemetry } from '@/api/types'
import AlertBanner from '@/components/layout/AlertBanner.vue'
import { device } from './testDrone'

/** Two drones in one UI (D-31, R-28): separate state, explicit endpoints, commands bound to their drone. */
const A = device({ gatewaySn: 'RC-A', droneSn: 'M4E-A', label: 'A' })
const B = device({ gatewaySn: 'RC-B', droneSn: 'M4E-B', label: 'B', color: '#D85A30' })

function telemetry(sn: string, lat: number): DroneTelemetry {
  return { sn, timestamp: 1, lat, lon: 113.94, modeCode: 0, highFrequency: false, raw: {} } as unknown as DroneTelemetry
}

describe('fleet and per-drone stores', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    setConfigForTest({ apiBaseUrl: 'http://api.test', wsUrl: '', map: { coordSys: 'WGS84', tileUrl: '', subdomains: '', attribution: '', maxZoom: 19, apiKey: '' } })
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      const u = String(url)
      const body = /\/(commands|alerts|track|drones)(\?|$)/.test(u) ? []
        : u.endsWith('/flight/return-home') ? { id: 'c1', type: 'rth', label: '一键返航', channel: 'SERVICES', status: 'SENT', createdAt: 1, sentAt: 1,
          completedAt: null, resultCode: null, message: null }
        : {}
      return new Response(JSON.stringify(body), { status: 200 })
    }))
    try {
      localStorage.clear()
    } catch {
      /* no storage */
    }
  })

  afterEach(() => vi.unstubAllGlobals())

  it('routes each push to its own drone and ignores untagged ones', () => {
    useTelemetryStore('RC-A').start()
    useTelemetryStore('RC-B').start()
    telemetrySocket.dispatch({ type: 'telemetry', ts: 1, gatewaySn: 'RC-A', droneSn: 'M4E-A', data: telemetry('M4E-A', 22.1) })
    telemetrySocket.dispatch({ type: 'telemetry', ts: 2, gatewaySn: 'RC-B', droneSn: 'M4E-B', data: telemetry('M4E-B', 22.2) })
    telemetrySocket.dispatch({ type: 'telemetry', ts: 3, data: telemetry('X', 99) }) // platform-level: no drone
    expect(useTelemetryStore('RC-A').drone?.lat).toBe(22.1)
    expect(useTelemetryStore('RC-B').drone?.lat).toBe(22.2)
    expect(useTelemetryStore('RC-A')).not.toBe(useTelemetryStore('RC-B'))
  })

  it('selects an enabled drone, online first, and keeps a valid selection', () => {
    const fleet = useFleetStore()
    fleet.apply([{ ...A, online: false }, B, device({ gatewaySn: 'RC-C', droneSn: null, label: 'C', enabled: false })])
    expect(fleet.selectedSn).toBe('RC-B')
    expect(fleet.pending.map((d) => d.label)).toEqual(['C'])
    fleet.select('RC-A')
    expect(fleet.selected?.label).toBe('A')
    fleet.apply([{ ...A, enabled: false }, B]) // A disabled from the settings page
    expect(fleet.selectedSn).toBe('RC-B')
    expect(fleet.label('M4E-B')).toBe('B') // aircraft or RC SN
  })

  it('calls the per-drone endpoint of the drone it names', async () => {
    await controlApi('RC-B').takeoff({ relativeHeight: 30, securityTakeoffHeight: 20, rthAltitude: 60, rcLostAction: 'RETURN_HOME', maxSpeed: 10 })
    expect(vi.mocked(fetch).mock.calls[0]![0]).toBe('http://api.test/api/v1/drones/RC-B/flight/takeoff')
    expect(() => controlApi('').state()).toThrow('未选择飞机')
  })

  it('a confirmation opened for A still goes to A after the operator selects B', async () => {
    const fleet = useFleetStore()
    fleet.apply([A, B])
    fleet.select('RC-A')
    let answer!: (ok: boolean) => void
    vi.spyOn(useConfirmStore(), 'ask').mockImplementation(() => new Promise<boolean>((r) => (answer = r)))
    let actions!: ReturnType<typeof useFlightActions>
    mount(defineComponent({ setup() { actions = useFlightActions(); return () => h('div') } }))
    const pending = actions.returnHome()
    fleet.select('RC-B') // selection changes while the dialog is open
    answer(true)
    await pending
    await flushPromises()
    expect(vi.mocked(fetch).mock.calls.map((c) => String(c[0]))).toContain('http://api.test/api/v1/drones/RC-A/flight/return-home')
    expect(useControlStore('RC-A').commands.length).toBe(1)
    expect(useControlStore('RC-B').commands.length).toBe(0)
  })

  it('says a stop is not confirmed yet, and that a lost drone is judged where it was last seen', async () => {
    const fleet = useFleetStore()
    fleet.apply([A, B])
    const blind = { code: 'PROXIMITY_BLIND', level: 'WARNING', title: '靠近监测看不到 B', message: 'B 已 12 秒没有位置数据', suggestion: '', since: 1 }
    fleet.onProximity({ a: 'M4E-A', b: 'M4E-B', aLabel: 'A', bLabel: 'B', horizontalM: 30, verticalM: 0, closingSpeedMps: 8, predictedMinM: 4,
      thresholdM: 40, level: 'hold', stopped: [], stopping: ['A'], stale: ['B'], staleSeconds: 12, active: true, since: 1 })
    const w = mount(AlertBanner)
    await flushPromises() // the stores' first load (empty alerts) is done
    useControlStore('RC-A').alerts = [blind] as never
    useControlStore('RC-B').alerts = [blind] as never
    await flushPromises()
    expect(w.text()).toContain('正在让 A 悬停（还在移动）')
    expect(w.text()).not.toContain('已让 A 悬停')
    expect(w.text()).toContain('B 已 12 秒没有位置数据，按最后位置判断')
    expect(w.findAll('[data-code=PROXIMITY_BLIND]')).toHaveLength(1) // platform-level: once, not under each drone
  })
})
