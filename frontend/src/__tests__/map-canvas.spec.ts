import { beforeAll, beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, inject, ref } from 'vue'
import L from 'leaflet'
import MapCanvas from '@/components/map/MapCanvas.vue'
import DroneMarker from '@/components/map/DroneMarker.vue'
import { MAP_CONTEXT } from '@/components/map/mapContext'
import { resolveConfig, setConfigForTest } from '@/config/runtime'
import { useLayersStore } from '@/stores/layers'
import { useTelemetryStore } from '@/stores/telemetry'
import { toDisplay } from '@/utils/coord'
import { distance } from '@/utils/geo'
import { useTestDrone } from './testDrone'

/** Counts slot mounts so the test can see overlays being redrawn after a coordinate-system switch. */
let probeMounts = 0
const Probe = defineComponent({
  setup() {
    inject(MAP_CONTEXT)
    probeMounts++
    return () => h('i')
  },
})

const tileUrls = (m: L.Map): string[] => {
  const out: string[] = []
  m.eachLayer((l) => {
    if (l instanceof L.TileLayer) out.push((l as unknown as { _url: string })._url)
  })
  return out
}

describe('MapCanvas base maps (D-17)', () => {
  beforeAll(() => {
    globalThis.ResizeObserver ??= class {
      observe() {}
      disconnect() {}
    } as unknown as typeof ResizeObserver
  })

  beforeEach(() => {
    localStorage.clear()
    probeMounts = 0
    setConfigForTest(resolveConfig({}, 'http://x'))
    setActivePinia(createPinia())
  })

  it('swaps tiles in place within GCJ-02 and re-creates the map when switching to WGS84', async () => {
    const center = { lat: 22.58, lon: 113.94 }
    const w = mount(MapCanvas, { props: { center, zoom: 15 }, slots: { default: () => h(Probe) }, attachTo: document.body })
    const vm = w.vm as unknown as { map: L.Map; fromLatLng: (ll: L.LatLng) => { lat: number; lon: number } }
    await flushPromises()
    const first = vm.map
    expect(tileUrls(first)).toHaveLength(1)
    expect(tileUrls(first)[0]).toContain('webrd0')
    // displayed centre is the GCJ-02 position of the WGS84 centre
    const shown = toDisplay(center, 'GCJ02')
    expect(distance({ lat: first.getCenter().lat, lon: first.getCenter().lng }, shown)).toBeLessThan(0.01)
    expect(probeMounts).toBe(1)

    useLayersStore().setBaseMap('gaode-satellite')
    await flushPromises()
    expect(vm.map).toBe(first)
    expect(tileUrls(first)).toHaveLength(2)
    expect(probeMounts).toBe(1)

    useLayersStore().setBaseMap('osm')
    await flushPromises()
    const second = vm.map
    expect(second).not.toBe(first)
    expect(tileUrls(second)).toEqual(['https://tile.openstreetmap.org/{z}/{x}/{y}.png'])
    expect(probeMounts).toBe(2)
    // same WGS84 view and zoom carried across the re-mount, now without offset
    expect(distance({ lat: second.getCenter().lat, lon: second.getCenter().lng }, center)).toBeLessThan(0.05)
    expect(second.getZoom()).toBe(15)
    // clicks still come back as WGS84
    expect(distance(vm.fromLatLng(L.latLng(center.lat, center.lon)), center)).toBeLessThan(0.01)
    w.unmount()
  })

  it('reports clicks on a GCJ-02 map as WGS84', () => {
    const w = mount(MapCanvas, { attachTo: document.body })
    const vm = w.vm as unknown as { map: L.Map }
    const wgs = { lat: 30.5, lon: 114.3 }
    const d = toDisplay(wgs, 'GCJ02')
    vm.map.fire('click', { latlng: L.latLng(d.lat, d.lon) })
    const p = (w.emitted('map-click')![0] as [{ lat: number; lon: number }])[0]
    expect(distance(p, wgs)).toBeLessThan(0.01)
    w.unmount()
  })

  it('a map the operator moved stays put until following is turned back on', async () => {
    useTestDrone()
    const tel = useTelemetryStore()
    const follow = ref(true)
    const w = mount(defineComponent({
      setup: () => () => h(MapCanvas, { zoom: 17 }, { default: () => h(DroneMarker, { follow: follow.value }) }),
    }), { attachTo: document.body })
    const vm = w.findComponent(MapCanvas).vm as unknown as { map: L.Map; fromLatLng: (ll: L.LatLng) => { lat: number; lon: number } }
    const centre = () => vm.fromLatLng(vm.map.getCenter())
    const a = { lat: 22.5800, lon: 113.9400 }
    const b = { lat: 22.5810, lon: 113.9410 }
    tel.drone = { ...a, modeCode: 3 } as never
    await flushPromises()
    expect(distance(centre(), a)).toBeLessThan(1)

    // the operator dragged the map away: following is off (MonitorView turns it off on dragstart)
    follow.value = false
    vm.map.panBy([300, 200], { animate: false })
    const moved = centre()
    tel.drone = { ...b, modeCode: 3 } as never
    await flushPromises()
    expect(distance(centre(), moved)).toBeLessThan(1)

    follow.value = true // the follow button: back to the drone at once, without waiting for the next position
    await flushPromises()
    expect(distance(centre(), b)).toBeLessThan(1)
    w.unmount()
  })

  it('a drone without satellites stays at its last fix, marked 定位中, instead of jumping to 0/0', async () => {
    useTestDrone()
    const tel = useTelemetryStore()
    const w = mount(defineComponent({
      setup: () => () => h(MapCanvas, { zoom: 17 }, { default: () => h(DroneMarker, { follow: true }) }),
    }), { attachTo: document.body })
    const vm = w.findComponent(MapCanvas).vm as unknown as { map: L.Map; fromLatLng: (ll: L.LatLng) => { lat: number; lon: number } }
    const markerAt = () => {
      let p: { lat: number; lon: number } | null = null
      vm.map.eachLayer((l) => {
        if (l instanceof L.Marker) p = vm.fromLatLng(l.getLatLng())
      })
      return p
    }
    const a = { lat: 29.6032, lon: 103.595 }
    tel.applyTelemetry({ ...a, modeCode: 0, attitudeHead: 0, highFrequency: false, raw: {} } as never)
    await flushPromises()
    expect(document.body.textContent).not.toContain('定位中')

    tel.applyTelemetry({ lat: null, lon: null, modeCode: 0, attitudeHead: 0, highFrequency: false, raw: {} } as never)
    await flushPromises()
    expect(distance(markerAt()!, a)).toBeLessThan(1)
    expect(distance(vm.fromLatLng(vm.map.getCenter()), a)).toBeLessThan(1)
    expect(document.body.textContent).toContain('定位中')
    w.unmount()
  })
})
