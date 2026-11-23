import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { resolveConfig, setConfigForTest } from '@/config/runtime'
import { telemetrySocket, type WsMessage } from '@/services/ws'
import DemoMap from '@/views/demo/DemoMap.vue'
import { useDemoStore } from '@/views/demo/useDemoStore'
import { demoApi, type DemoDrone, type DemoState, type DronesFrame } from '@/views/demo/demoApi'

/** The platform reports an aircraft without satellite fix with an empty position: the demo pages must carry on. */
const HOME = { lat: 29.60318, lon: 103.59502 }

function drone(label: 'A' | 'B', lat: number | null, lon: number | null): DemoDrone {
  return {
    id: `SIM-${label}`, label, online: true, lat, lon, relativeHeight: 30, ellipsoidHeight: 379, heading: 90, horizontalSpeed: 5,
    verticalSpeed: 0, battery: 90, gimbalPitch: -90, gimbalYaw: 0, phase: 'FLYING',
    execution: { routeId: 'r', state: 'FLYING', currentIndex: 1, total: 3, pauseReason: null, message: null },
    video: null, homeLat: HOME.lat, homeLon: label === 'A' ? HOME.lon : HOME.lon + 0.0003,
  }
}

const frame = (drones: DemoDrone[]): WsMessage => ({ type: 'demo-drones', data: { drones, link: null, proximity: null } as DronesFrame }) as WsMessage

describe('demo pages without a position fix', () => {
  beforeAll(() => {
    globalThis.ResizeObserver ??= class {
      observe() {}
      disconnect() {}
    } as unknown as typeof ResizeObserver
  })

  beforeEach(() => {
    setConfigForTest(resolveConfig({}, 'http://x'))
    setActivePinia(createPinia())
    vi.spyOn(telemetrySocket, 'start').mockImplementation(() => {})
    vi.spyOn(demoApi, 'snapshot').mockReturnValue(new Promise(() => {}))
  })

  afterEach(() => {
    useDemoStore().stop()
    vi.restoreAllMocks()
  })

  it('keeps the last track point and the marker where the aircraft was last seen', async () => {
    const demo = useDemoStore()
    demo.start()
    demo.state = { stage: 'S1_EXPLORE', routes: {}, dogMode: 'SIM' } as unknown as DemoState
    const w = mount(DemoMap, { attachTo: document.body })
    await flushPromises()

    const seenA = drone('A', HOME.lat + 0.0002, HOME.lon)
    telemetrySocket.dispatch(frame([seenA, drone('B', HOME.lat, HOME.lon + 0.0003)]))
    await flushPromises()
    expect(demo.tracks.A).toHaveLength(1)
    expect(document.querySelectorAll('.demo-drone')).toHaveLength(2)

    // A loses its fix in flight: no new track point, no error, its marker stays
    expect(() => telemetrySocket.dispatch(frame([drone('A', null, null), drone('B', HOME.lat, HOME.lon + 0.0004)]))).not.toThrow()
    await flushPromises()
    expect(demo.byLabel.A?.lat).toBeNull()
    expect(demo.tracks.A).toHaveLength(1)
    expect(demo.tracks.B).toHaveLength(2)
    expect(document.querySelectorAll('.demo-drone')).toHaveLength(2)

    // and picks up again once the fix is back
    telemetrySocket.dispatch(frame([drone('A', HOME.lat + 0.0004, HOME.lon), drone('B', HOME.lat, HOME.lon + 0.0004)]))
    await flushPromises()
    expect(demo.tracks.A).toHaveLength(2)
    w.unmount()
  })
})
