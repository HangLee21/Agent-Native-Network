import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'
import LayerPanel from '@/components/map/LayerPanel.vue'
import { LAYERS, useLayersStore } from '@/stores/layers'
import { useOverlaysStore } from '@/stores/overlays'
import { resolveConfig, setConfigForTest } from '@/config/runtime'

describe('layer management (R-04)', () => {
  beforeEach(() => {
    localStorage.clear()
    setConfigForTest(resolveConfig({}, 'http://x'))
    setActivePinia(createPinia())
  })

  it('lists every Q-05 layer with a checkbox and toggles visibility persistently', async () => {
    const w = mount(LayerPanel)
    const boxes = w.findAll('input[type=checkbox]')
    expect(boxes.length).toBe(LAYERS.length)
    const track = w.find('input[data-layer=track]')
    expect((track.element as HTMLInputElement).checked).toBe(true)
    await track.setValue(false)
    expect(useLayersStore().isVisible('track')).toBe(false)
    expect(JSON.parse(localStorage.getItem('uav.layers')!).track).toBe(false)
  })

  it('keeps the DJI no-fly layer unavailable with an explanation', () => {
    const w = mount(LayerPanel)
    const box = w.find('input[data-layer=djiNoFly]')
    expect((box.element as HTMLInputElement).disabled).toBe(true)
    expect(w.text()).toContain('只能在接近时告警')
    useLayersStore().set('djiNoFly', true)
    expect(useLayersStore().isVisible('djiNoFly')).toBe(false)
  })

  it('applies and removes overlays pushed by the backend', () => {
    const ov = useOverlaysStore()
    ov.apply({ kind: 'target', data: { lat: 1, lon: 2, relativeHeight: 50, label: '航点 1' }, updatedAt: 1 })
    expect(ov.target()?.label).toBe('航点 1')
    ov.apply({ kind: 'target', data: null, updatedAt: 2 })
    expect(ov.target()).toBeNull()
  })

  it('switches base maps with radio buttons and remembers the choice (D-17)', async () => {
    const w = mount(LayerPanel)
    const radios = w.findAll('input[type=radio]')
    expect(radios.map((r) => r.attributes('data-base-map'))).toEqual(['gaode-street', 'gaode-satellite', 'osm'])
    expect((w.find('input[data-base-map=gaode-street]').element as HTMLInputElement).checked).toBe(true)
    await w.find('input[data-base-map=osm]').setValue(true)
    expect(useLayersStore().baseMap.id).toBe('osm')
    expect(localStorage.getItem('uav.baseMap')).toBe('osm')

    setActivePinia(createPinia())
    expect(useLayersStore().baseMap.coordSys).toBe('WGS84')
  })

  it('ignores a remembered base map that is no longer configured', () => {
    localStorage.setItem('uav.baseMap', 'gone')
    expect(useLayersStore().baseMapId).toBe('gaode-street')
    useLayersStore().setBaseMap('gone')
    expect(useLayersStore().baseMapId).toBe('gaode-street')
  })

  it('hides the base-map group for an old single-tile config', () => {
    setConfigForTest(resolveConfig({ map: { tileUrl: 'https://t/{z}/{x}/{y}.png' } as never }, 'http://x'))
    setActivePinia(createPinia())
    const w = mount(LayerPanel)
    expect(w.find('[data-test=base-maps]').exists()).toBe(false)
    expect(useLayersStore().baseMap.tiles[0]!.url).toBe('https://t/{z}/{x}/{y}.png')
  })
})
