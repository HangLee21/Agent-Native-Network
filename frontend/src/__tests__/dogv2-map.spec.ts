import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { h } from 'vue'
import MapCanvas from '@/components/map/MapCanvas.vue'
import DogV2Layer from '@/components/map/DogV2Layer.vue'
import { resolveConfig, setConfigForTest } from '@/config/runtime'
import { useLayersStore } from '@/stores/layers'
import { useDog2Store } from '@/stores/dogv2'
import type { Dog2, Dog2List } from '@/api/dogv2'

const answer: { list: Dog2List } = { list: { mode: 'mock', broker: true, dogs: [] } }

vi.mock('@/api/dogv2', async (orig) => {
  const real = await orig<typeof import('@/api/dogv2')>()
  return { ...real, dog2Api: { ...real.dog2Api, list: vi.fn(async () => structuredClone(answer.list)) } }
})

function dog(position: Dog2['position'], extra: Partial<Dog2> = {}): Dog2 {
  return {
    id: 'lite3-01', label: 'Lite3', model: 'lite3', software: '0.2.0', online: true, enabled: true, mode: 'old',
    gateway: 'standby', statusAgeMs: 100, telemetryAgeMs: null, status: { gnss: { state: 'fix' } }, telemetry: null,
    position, positionAgeMs: 300, capabilities: { position: { source: 'gnss' } },
    control: { held: false, mine: false, session: null, endedReason: null }, video: {}, lastSeenAt: null, ...extra,
  }
}

const fix = { fix: 'single', lat: 22.5795, lon: 113.9398, heading_deg: 91.2, heading_source: 'imu_aligned', sats: 12 }

describe('new-system dogs on the map (R-34)', () => {
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
  })
  afterEach(() => {
    document.body.innerHTML = ''
  })

  async function show() {
    const w = mount(MapCanvas, { props: { center: { lat: 22.58, lon: 113.94 }, zoom: 17 }, slots: { default: () => h(DogV2Layer) }, attachTo: document.body })
    await flushPromises()
    await useDog2Store().refresh()
    await flushPromises()
    return w
  }

  it('draws the dog with its heading, then grey at the last fix while it has none, then hides with the layer', async () => {
    answer.list.dogs = [dog(fix)]
    const w = await show()
    let icon = document.querySelector('.dog2-icon') as HTMLElement
    expect(icon).not.toBeNull()
    expect(icon.innerHTML).toContain('rotate(91.2deg)')
    expect(icon.textContent).toContain('Lite3')
    expect(icon.innerHTML).toContain('#a3e635')

    answer.list.dogs = [dog({ ...fix, fix: 'none', lat: null, lon: null, heading_deg: null, heading_source: 'none' })]
    await useDog2Store().refresh()
    await flushPromises()
    icon = document.querySelector('.dog2-icon') as HTMLElement
    expect(icon.textContent).toContain('定位中')
    expect(icon.innerHTML).not.toContain('rotate(')

    useLayersStore().set('dogs', false)
    await flushPromises()
    expect(document.querySelector('.dog2-icon')).toBeNull()
    w.unmount()
  })

  it('shows the direction of travel as a hollow arrow and nothing for a dog that never had a fix', async () => {
    answer.list.dogs = [dog({ ...fix, heading_deg: 200, heading_source: 'course' }),
      dog({ fix: 'none', lat: null, lon: null, heading_source: 'none' }, { id: 'lite3-02', label: 'B' })]
    const w = await show()
    const icons = document.querySelectorAll('.dog2-icon')
    expect(icons).toHaveLength(1)
    expect(icons[0]!.innerHTML).toContain('rotate(200deg)')
    expect(icons[0]!.innerHTML).toContain('fill="none"')
    w.unmount()
  })

  it('keeps the operated dog centred while it has a fix, and leaves the view alone otherwise', async () => {
    answer.list.dogs = [dog(fix)]
    let map: import('leaflet').Map | null = null
    const w = mount(MapCanvas, {
      props: { center: { lat: 22.5, lon: 113.8 }, zoom: 17, onReady: (m: import('leaflet').Map) => { map = m } },
      slots: { default: () => h(DogV2Layer, { follow: 'lite3' }) }, attachTo: document.body,
    })
    await flushPromises()
    await useDog2Store().refresh()
    await flushPromises()
    // the default base map is GCJ-02: the centre is the dog's shifted position, a few hundred metres from the WGS84 one
    const c1 = map!.getCenter()
    expect(Math.abs(c1.lat - fix.lat)).toBeLessThan(0.01)
    expect(Math.abs(c1.lng - fix.lon)).toBeLessThan(0.01)
    w.unmount()

    answer.list.dogs = [dog(fix)]
    const w2 = mount(MapCanvas, {
      props: { center: { lat: 22.5, lon: 113.8 }, zoom: 17, onReady: (m: import('leaflet').Map) => { map = m } },
      slots: { default: () => h(DogV2Layer, { follow: 's10' }) }, attachTo: document.body,
    })
    await flushPromises()
    await useDog2Store().refresh()
    await flushPromises()
    expect(Math.abs(map!.getCenter().lat - fix.lat)).toBeGreaterThan(0.05)
    w2.unmount()
  })

  it('does not poll when the new dog system is off', async () => {
    answer.list = { mode: 'off', broker: false, dogs: [] }
    const spy = vi.spyOn(window, 'setInterval')
    const w = mount(MapCanvas, { props: { center: { lat: 22.58, lon: 113.94 }, zoom: 17 }, slots: { default: () => h(DogV2Layer) }, attachTo: document.body })
    await flushPromises()
    expect(spy).not.toHaveBeenCalled()
    w.unmount()
    spy.mockRestore()
    answer.list = { mode: 'mock', broker: true, dogs: [] }
  })
})
