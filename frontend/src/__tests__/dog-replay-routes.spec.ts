import { flushPromises, mount } from '@vue/test-utils'
import L from 'leaflet'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import MapCanvas from '@/components/map/MapCanvas.vue'
import JointTimeline from '@/components/history/JointTimeline.vue'
import { setConfigForTest } from '@/config/runtime'
import JointReplayView from '@/views/JointReplayView.vue'

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

it('maps each recorded dog route separately and selects it from the menu or timeline', async () => {
  globalThis.ResizeObserver ??= class {
    observe() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver
  setActivePinia(createPinia())
  setConfigForTest({ apiBaseUrl: 'http://api.test', wsUrl: '', map: { coordSys: 'WGS84', tileUrl: '', subdomains: '', attribution: '', maxZoom: 19, apiKey: '' } })
  const start = (id: number, payload: Record<string, unknown>) => ({
    id, ts: 1000 + 100 * id, eventType: 'NAV_START', eventLevel: 'INFO', title: '开始导航', payload,
  })
  const data: Record<string, unknown> = {
    '/d1': { id: 'd1', kind: 'dog', status: 'CLOSED', dogId: 'lite3-01', dogModel: 'lite3', startedAt: 1000,
      takeoffAt: 1000, endedAt: 2000, landedAt: 2000 },
    '/d1/samples': [{ ts: 1000, lat: 22.5, lon: 113.9 }, { ts: 2000, lat: 22.501, lon: 113.901 }],
    '/d1/events': [
      start(1, { taskId: 'first', points: [{ lat: 22.51, lon: 113.91, name: 'A' }, { lat: 22.52, lon: 113.92 }] }),
      { ...start(1, { taskId: 'first' }), id: 5, ts: 1150, eventType: 'NAV_END' },
      start(2, { taskId: 'second', points: [[22.53, 113.93], [22.54, 113.94]] }),
      start(3, { pointCount: 3 }),
      start(4, { points: [[22.53, 113.93], [100, 113.94]] }),
    ],
    '/d1/commands': [],
  }
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    const key = String(url).replace('http://api.test/api/v1/dog-records', '')
    return new Response(JSON.stringify(data[key] ?? {}), { status: key in data ? 200 : 404 })
  }))
  const line = vi.spyOn(L, 'polyline')
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/history/together', component: JointReplayView }] })
  await router.push('/history/together?ids=dog:d1')
  const wrapper = mount(JointReplayView, { attachTo: document.body, global: { plugins: [router] } })
  try {
    await flushPromises()
    const { toLatLng } = wrapper.getComponent(MapCanvas).vm
    const routes = line.mock.calls.filter(([, options]) => options?.className === 'dog-replay-route')
    const waypoints = [
      [[22.51, 113.91], [22.52, 113.92]],
      [[22.53, 113.93], [22.54, 113.94]],
    ] as const
    expect(routes.map(([points]) => points)).toEqual(waypoints.map((route) => route.map(([lat, lon]) => toLatLng({ lat, lon }))))
    const actual = line.mock.results[line.mock.calls.findIndex(([, options]) => options?.weight === 3)]!.value as L.Polyline
    const routeToggle = wrapper.get('[data-test=joint-dog-routes]')
    expect((routeToggle.element as HTMLInputElement).checked).toBe(true)
    expect(wrapper.findAll('.leaflet-marker-icon[title*="路线"]')).toHaveLength(4)

    const timeline = wrapper.getComponent(JointTimeline)
    const select = wrapper.get('[data-test=joint-dog-route-select]')
    expect(select.findAll('option')).toHaveLength(3)
    await select.setValue('d1:2')
    expect(timeline.props('cursor')).toBe(1200)
    expect(wrapper.findAll('.leaflet-marker-icon[title*="路线 2"]')).toHaveLength(2)
    expect(wrapper.findAll('.leaflet-marker-icon[title*="路线 1"]')).toHaveLength(0)

    const first = wrapper.get('[data-test=dog-nav-span-1]')
    const second = wrapper.get('[data-test=dog-nav-span-2]')
    expect(Number(first.get('rect').attributes('width'))).toBeGreaterThan(4)
    expect(second.get('rect').attributes('width')).toBe('4')
    await first.get('rect').trigger('pointerdown')
    expect((select.element as HTMLSelectElement).value).toBe('d1:1')
    expect(timeline.props('cursor')).toBe(1100)
    expect(first.classes()).toContain('selected')

    await select.setValue('')
    expect(wrapper.findAll('.leaflet-marker-icon[title*="路线"]')).toHaveLength(4)
    await routeToggle.setValue(false)
    expect(wrapper.findAll('.leaflet-marker-icon[title*="路线"]')).toHaveLength(0)
    expect(actual.getElement()?.isConnected).toBe(true)
  } finally {
    wrapper.unmount()
  }
})
