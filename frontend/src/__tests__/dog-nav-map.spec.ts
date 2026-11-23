/**
 * Dog navigation on the map (docs/dog/ui-design.md 19.5): picking a goal or a route on the live page (the map comes
 * to the main view while the dog stays operated), the draggable numbered points with the check's refused ones in
 * red, and the navigation layer (task points, planned path, arrival radius circles, allowed area, pose, the pause
 * reason and "避障关" next to the dog) that follows the layer switch and draws nothing for other dogs.
 */
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { h, nextTick } from 'vue'
import L from 'leaflet'
import MapCanvas from '@/components/map/MapCanvas.vue'
import DogRouteEditLayer from '@/components/map/DogRouteEditLayer.vue'
import DogNavLayer from '@/components/map/DogNavLayer.vue'
import MonitorView from '@/views/MonitorView.vue'
import { resolveConfig, setConfigForTest } from '@/config/runtime'
import { useLayersStore } from '@/stores/layers'
import { useDog2Store } from '@/stores/dogv2'
import { useDogStore } from '@/stores/dog'
import { useControlStore } from '@/stores/control'
import { dog2Api, type Dog2, type Dog2Nav, type Dog2NavCapability, type Dog2NavCheck } from '@/api/dogv2'
import { TEST_DRONE, useTestDrone } from './testDrone'

vi.mock('@/api/dogv2', async (orig) => {
  const real = await orig<typeof import('@/api/dogv2')>()
  return {
    ...real,
    dog2Api: { ...real.dog2Api, list: vi.fn(), nav: vi.fn(), navPrepare: vi.fn(async () => ({ result: 'done' as const })), navCheck: vi.fn() },
  }
})
const api = vi.mocked(dog2Api)

const CAP: Dog2NavCapability = { kind: 'gps', avoidance: true, speed_levels: [], arrive_radius_m: [1, 20], max_points: 200 }
const PTS = [{ lat: 22.5801, lon: 113.9401 }, { lat: 22.5805, lon: 113.9405 }, { lat: 22.581, lon: 113.941 }]
const OK: Dog2NavCheck = { ok: true, problems: [], area: [[22.57, 113.93], [22.57, 113.95], [22.59, 113.95]], areaSource: 'dog', totalM: 120, firstM: 30 }

let current: Dog2[] = []
function dog(nav: Dog2Nav | null, extra: Partial<Dog2> = {}): Dog2 {
  return {
    id: 'lite3-01', label: 'Lite3', model: 'lite3', software: '0.2.0', online: true, enabled: true, mode: 'new', gateway: 'x',
    statusAgeMs: 100, telemetryAgeMs: 100, status: {}, position: { fix: 'single', lat: 22.58, lon: 113.94, heading_source: 'imu_aligned' }, positionAgeMs: 300,
    telemetry: { basic_state: 2, basic_state_name: '站立（力控）', battery_pct: 80, rpy: [0, 0, 0], vel_body: [0, 0, 0], feedback_age_s: 0.05 },
    control: { held: false, mine: false, session: null, endedReason: null }, video: {}, lastSeenAt: Date.now(), navCapability: CAP, nav, ...extra,
  }
}
const settle = async (ms = 5) => {
  await new Promise((r) => setTimeout(r, ms))
  await flushPromises()
}

/** Every layer on the map with a Leaflet className (paths) or a divIcon className (markers). */
function classes(map: L.Map): string[] {
  const out: string[] = []
  map.eachLayer((l) => {
    const c = (l as L.Path).options?.className
    if (l instanceof L.Marker) {
      const ic = l.options.icon as L.DivIcon | undefined
      if (ic?.options.className) out.push(ic.options.className)
    } else if (c) out.push(c)
  })
  return out
}
function markers(map: L.Map, cls: string): L.Marker[] {
  const out: L.Marker[] = []
  map.eachLayer((l) => {
    if (l instanceof L.Marker && String((l.options.icon as L.DivIcon | undefined)?.options.className ?? '').split(' ').includes(cls)) out.push(l)
  })
  return out
}

describe('dog navigation on the map', () => {
  beforeAll(() => {
    globalThis.ResizeObserver ??= class {
      observe() {}
      disconnect() {}
    } as unknown as typeof ResizeObserver
  })
  beforeEach(() => {
    localStorage.clear()
    setConfigForTest(resolveConfig({}, 'http://x'))
    setActivePinia(createPinia())
    useLayersStore().setBaseMap('osm')    // WGS84 base map: what is drawn is what the platform holds
    api.list.mockImplementation(async () => ({ mode: 'mock', broker: true, dogs: structuredClone(current) }))
    api.navCheck.mockResolvedValue(OK)
  })
  afterEach(() => {
    document.body.innerHTML = ''
    vi.clearAllMocks()
  })

  async function showMap(layer: 'edit' | 'nav') {
    let map: L.Map | null = null
    const w = mount(MapCanvas, {
      props: { center: { lat: 22.58, lon: 113.94 }, zoom: 17, onReady: (m: L.Map) => { map = m } },
      slots: { default: () => h(layer === 'edit' ? DogRouteEditLayer : DogNavLayer) }, attachTo: document.body,
    })
    await flushPromises()
    return { w, map: () => map! }
  }

  it('route editing: numbered points, the refused one red; drag moves it, right-click deletes it', async () => {
    const v2 = useDog2Store()
    api.navCheck.mockResolvedValueOnce({ ...OK, ok: false, problems: [{ code: 'outside_area', text: '点在允许区域外', index: 1 }] })
    const { w, map } = await showMap('edit')
    v2.draftOpen('lite3-01', PTS)
    await settle()
    const pts = markers(map(), 'dog-route-pt')
    expect(pts).toHaveLength(3)
    const html = pts.map((m) => (m.options.icon as L.DivIcon).options.html as string)
    expect(html[0]).toContain('#a3e635')
    expect(html[1]).toContain('var(--danger)')
    expect(html[2]).toContain('>3</div>')
    expect(classes(map())).toContain('dog-route-line')

    pts[0]!.setLatLng([22.5799, 113.9399])
    pts[0]!.fire('dragend')
    expect(v2.navDraft?.points[0]).toEqual({ lat: 22.5799, lon: 113.9399 })
    await nextTick()
    markers(map(), 'dog-route-pt')[2]!.fire('contextmenu', { originalEvent: new MouseEvent('contextmenu') })
    expect(v2.navDraft?.points).toHaveLength(2)
    await nextTick()
    expect(markers(map(), 'dog-route-pt')).toHaveLength(2)

    v2.draftClear()
    await nextTick()
    expect(markers(map(), 'dog-route-pt')).toHaveLength(0)
    w.unmount()
  })

  it('a task: points (reached ones grey), planned path, arrival radius circles, area, pose; tags when paused or avoidance off', async () => {
    const v2 = useDog2Store()
    current = [dog({
      state: 'paused', reason: 'blocked', index: 1, count: 3, avoidance: false, points: PTS.map((p) => [p.lat, p.lon] as [number, number]),
      path: [[22.5801, 113.9401], [22.5803, 113.9403], [22.5805, 113.9405]], pose: { lat: 22.5802, lon: 113.9402, std_m: 2.4 }, arriveRadiusM: 4,
    })]
    v2.dogs = current
    v2.navArea['lite3-01'] = OK.area
    const { w, map } = await showMap('nav')
    await nextTick()
    const c = classes(map())
    expect(c.filter((x) => x.startsWith('dog-nav-pt'))).toEqual(['dog-nav-pt done', 'dog-nav-pt cur', 'dog-nav-pt next'])
    expect(c).toContain('dog-nav-line')
    expect(c).toContain('dog-nav-path')
    expect(c).toContain('dog-nav-area')
    expect(c).toContain('dog-nav-pose')
    expect(c).toContain('dog-nav-std')
    const circles: number[] = []
    map().eachLayer((l) => { if (l instanceof L.Circle && l.options.className === 'dog-nav-radius') circles.push(l.getRadius()) })
    expect(circles).toEqual([4, 4, 4])
    const tag = (markers(map(), 'dog-nav-tag')[0]!.options.icon as L.DivIcon).options.html as string
    expect(tag).toContain('暂停：前方有障碍，绕不过去')
    expect(tag).toContain('避障关')

    useLayersStore().set('dogNav', false)
    await nextTick()
    expect(classes(map()).filter((x) => x.startsWith('dog-nav'))).toEqual([])
    w.unmount()
  })

  it('draws nothing for a dog that cannot navigate, or one without a task', async () => {
    const v2 = useDog2Store()
    v2.dogs = [dog({ state: 'running', index: 0, count: 1, points: [[22.58, 113.94]] }, { navCapability: null })]
    const { w, map } = await showMap('nav')
    await nextTick()
    expect(classes(map()).filter((x) => x.startsWith('dog-nav'))).toEqual([])
    v2.dogs = [dog({ state: 'idle', points: [[22.58, 113.94]] })]
    await nextTick()
    expect(classes(map()).filter((x) => x.startsWith('dog-nav'))).toEqual([])
    w.unmount()
  })
})

describe('picking a dog\'s points on the live page', () => {
  const stubs = {
    FleetLayers: true, LayerPanel: true, DroneInfoPanel: true, TargetDialog: true, TakeoffDialog: true, StickControlOverlay: true, CameraRail: true,
    PanelHeader: true, TaskArea: true, ActivityBar: true, SafetyFooter: true, MonitorRail: true, VideoPanel: true, DogMain: true, DogPanel: true,
    DogDrawer: true, DogThumb: true, HoldPad: true, ManualContent: true, DogRouteEditLayer: true, MapCanvas: true,
  }

  beforeEach(() => {
    localStorage.clear()
    setConfigForTest(resolveConfig({}, 'http://x'))
    setActivePinia(createPinia())
    useTestDrone()
    api.list.mockImplementation(async () => ({ mode: 'mock', broker: true, dogs: structuredClone(current) }))
    api.navCheck.mockResolvedValue(OK)
  })
  afterEach(() => vi.clearAllMocks())

  it('goal: the map comes large, one click is the goal and is checked; route: every click adds a point until "完成"', async () => {
    const dogs = useDogStore()
    const v2 = useDog2Store()
    current = [dog({ state: 'idle' })]
    v2.dogs = current
    await nextTick()
    dogs.select('lite3')
    const w = mount(MonitorView, { global: { stubs } })
    await flushPromises()
    const map = () => w.getComponent(MapCanvas)
    expect(w.get('[data-test=map-pane]').classes()).not.toContain('main')

    const control = useControlStore(TEST_DRONE)
    control.pickingTarget = 'dogGoal'
    await nextTick()
    expect(w.get('[data-test=map-pane]').classes()).toContain('main')
    expect(w.get('[data-test=dog-pick-hint]').text()).toContain('在地图上单击选择狗的目标点')
    map().vm.$emit('map-click', PTS[0])
    await settle()
    expect(control.pickingTarget).toBeNull()
    expect(v2.navDraft).toMatchObject({ dog: 'lite3-01', points: [PTS[0]] })
    expect(api.navCheck).toHaveBeenCalledWith('lite3-01', [PTS[0]])

    control.pickingTarget = 'dogRoute'
    await nextTick()
    expect(w.get('[data-test=dog-pick-hint]').text()).toContain('单击地图依次添加路线点')
    map().vm.$emit('map-click', PTS[1])
    map().vm.$emit('map-click', PTS[2])
    expect(v2.navDraft?.points).toEqual(PTS)
    expect(control.pickingTarget).toBe('dogRoute')
    await w.get('[data-test=dog-pick-done]').trigger('click')
    expect(control.pickingTarget).toBeNull()
    expect(v2.navDraft?.points).toHaveLength(3)

    // switching away from the dog ends picking
    control.pickingTarget = 'dogRoute'
    await nextTick()
    dogs.select(null)
    await nextTick()
    expect(control.pickingTarget).toBeNull()
    w.unmount()
  })
})
