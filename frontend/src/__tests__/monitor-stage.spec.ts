import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import MonitorView from '@/views/MonitorView.vue'
import { useDroneSn } from '@/composables/useDrone'
import { useFleetStore } from '@/stores/fleet'
import { useLiveStore } from '@/stores/live'
import type { LiveStatus } from '@/api/live'
import { device, TEST_DRONE, useTestDrone } from './testDrone'

/**
 * The flight-monitor stage with two drones (2026-11-04 field test): the small window also carries the other drone's
 * video while a video is the main view, and switching the controlled drone keeps the kind of main view.
 * A is the selected test drone, B the other one. Players are stubbed: each records the drone it plays.
 */
const A = TEST_DRONE
const B = 'RC-B'

const PlayerStub = defineComponent({
  props: { compact: Boolean, controls: Boolean },
  setup(props) {
    const sn = useDroneSn()
    return () => h('div', { 'data-test': 'player', 'data-sn': sn, 'data-compact': String(props.compact) })
  },
})
const stubs = {
  MapCanvas: true, FleetLayers: true, LayerPanel: true, DroneInfoPanel: true, TargetDialog: true, TakeoffDialog: true,
  StickControlOverlay: true, CameraRail: true, PanelHeader: true, TaskArea: true, ActivityBar: true, SafetyFooter: true,
  MonitorRail: true, VideoPanel: PlayerStub,
}

/** Re-mounts the monitor when the selected drone changes, as App.vue does (D-31). */
const Host = defineComponent({
  setup() {
    const fleet = useFleetStore()
    return () => h(MonitorView, { key: fleet.selectedSn ?? 'none' })
  },
})

const status = (streaming: boolean): LiveStatus =>
  ({ videoId: 'v', streaming, quality: 0, lens: 'wide', playback: streaming ? { protocol: 'MOCK', url: null } : null, lenses: [], pushConfigured: true })

const pane = (w: VueWrapper, name: string) => w.find(`[data-test=${name}]`)
const isMain = (w: VueWrapper, name: string) => pane(w, name).classes().includes('main')
/** Every open player: the drone it plays and whether it is a small tile. */
const players = (w: VueWrapper) => w.findAll('[data-test=player]').map((p) => `${p.attributes('data-sn')}${p.attributes('data-compact') === 'true' ? ' small' : ' main'}`)
const playerIn = (w: VueWrapper, name: string) => pane(w, name).find('[data-test=player]').attributes('data-sn')

async function select(sn: string): Promise<void> {
  useFleetStore().selectedSn = sn
  await flushPromises()
}

describe('monitor stage with two drones', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    useTestDrone(device({ gatewaySn: B, droneSn: 'M4E-B', label: 'B', color: '#D85A30' }))
    useLiveStore(A).status = status(true)
  })

  it('one drone streaming: the small window keeps only the map, as before', async () => {
    useLiveStore(B).status = status(false)
    const w = mount(Host, { global: { stubs } })
    expect(isMain(w, 'video-pane')).toBe(true)
    expect(pane(w, 'map-pane').classes()).toEqual(['pip', 'panel'])
    expect(pane(w, 'other-video-pane').exists()).toBe(false)
    expect(pane(w, 'main-view-badge').exists()).toBe(false)
    expect(w.find('[data-test^=pip-pick]').exists()).toBe(false)
    expect(pane(w, 'map-pane').find('[data-test=pip-hide]').exists()).toBe(true)
    expect(players(w)).toEqual([`${A} main`])

    await w.find('[data-test=swap]').trigger('click')
    expect(isMain(w, 'map-pane')).toBe(true)
    expect(pane(w, 'video-pane').classes()).toEqual(['pip', 'panel'])
    expect(players(w)).toEqual([`${A} small`])
  })

  it('two drones streaming: the small window has the map and the other drone\'s video; a click puts a tile in the main view', async () => {
    useLiveStore(B).status = status(true)
    const w = mount(Host, { global: { stubs } })
    expect(isMain(w, 'video-pane')).toBe(true)
    expect(pane(w, 'map-pane').classes()).toEqual(['pip', 'panel'])
    expect(pane(w, 'other-video-pane').classes()).toEqual(['pip', 'pip-2', 'panel'])
    expect(pane(w, 'other-video-pane').text()).toContain('B 视频')
    expect(pane(w, 'main-view-badge').text()).toBe('A 视频')
    expect(players(w)).toEqual([`${A} main`, `${B} small`]) // the main one plus the other drone's tile, no more

    // B's tile goes to the main view; A's video becomes the second tile, next to the map
    await w.find('[data-test=pip-pick-other]').trigger('click')
    expect(isMain(w, 'other-video-pane')).toBe(true)
    expect(pane(w, 'video-pane').classes()).toEqual(['pip', 'pip-2', 'panel'])
    expect(pane(w, 'video-pane').text()).toContain('A 视频')
    expect(pane(w, 'main-view-badge').text()).toBe('B 视频 · 当前操作 A')
    expect(players(w)).toEqual([`${A} small`, `${B} main`])

    // back to A's video by its tile, then the map by its tile: the other drone's player is closed with the map in the main view
    await w.find('[data-test=pip-pick-video]').trigger('click')
    expect(isMain(w, 'video-pane')).toBe(true)
    await w.find('[data-test=pip-pick-map]').trigger('click')
    expect(isMain(w, 'map-pane')).toBe(true)
    expect(pane(w, 'other-video-pane').exists()).toBe(false)
    expect(players(w)).toEqual([`${A} small`])

    // the swap button still swaps map and the selected drone's video
    await w.find('[data-test=swap]').trigger('click')
    expect(isMain(w, 'video-pane')).toBe(true)
    expect(players(w)).toEqual([`${A} main`, `${B} small`])
  })

  it('tucking the small window away closes the other drone\'s tile; the chip names both tiles', async () => {
    useLiveStore(B).status = status(true)
    const w = mount(Host, { global: { stubs } })
    await pane(w, 'other-video-pane').find('[data-test=pip-hide]').trigger('click')
    expect(pane(w, 'other-video-pane').exists()).toBe(false)
    expect(players(w)).toEqual([`${A} main`])
    expect(w.find('[data-test=pip-show]').text()).toContain('展开小窗（地图、B 视频）')
    await w.find('[data-test=pip-show]').trigger('click')
    expect(players(w)).toEqual([`${A} main`, `${B} small`])
  })

  it('the other drone\'s video in the main view falls back to the selected drone\'s video when it stops', async () => {
    useLiveStore(B).status = status(true)
    const w = mount(Host, { global: { stubs } })
    await w.find('[data-test=pip-pick-other]').trigger('click')
    useLiveStore(B).status = status(false)
    await flushPromises()
    expect(isMain(w, 'video-pane')).toBe(true)
    expect(pane(w, 'other-video-pane').exists()).toBe(false)
    expect(players(w)).toEqual([`${A} main`])
  })
})

describe('switching the controlled drone keeps the kind of main view', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    useTestDrone(device({ gatewaySn: B, droneSn: 'M4E-B', label: 'B', color: '#D85A30' }))
    useLiveStore(A).status = status(true)
    useLiveStore(B).status = status(true)
  })

  it('the controlled drone\'s video stays the controlled drone\'s video', async () => {
    useLiveStore(B).status = null // B's status not loaded yet at the switch: still its video, not the map
    const w = mount(Host, { global: { stubs } })
    expect(playerIn(w, 'video-pane')).toBe(A)
    await select(B)
    expect(isMain(w, 'video-pane')).toBe(true)
    expect(playerIn(w, 'video-pane')).toBe(B)
    await select(A)
    expect(isMain(w, 'video-pane')).toBe(true)
    expect(playerIn(w, 'video-pane')).toBe(A)
  })

  it('the map stays the map', async () => {
    const w = mount(Host, { global: { stubs } })
    await w.find('[data-test=swap]').trigger('click')
    expect(isMain(w, 'map-pane')).toBe(true)
    await select(B)
    expect(isMain(w, 'map-pane')).toBe(true)
    expect(players(w)).toEqual([`${B} small`])
  })

  it('the other drone\'s video stays the video of the drone that is not controlled', async () => {
    const w = mount(Host, { global: { stubs } })
    await w.find('[data-test=pip-pick-other]').trigger('click')
    expect(playerIn(w, 'other-video-pane')).toBe(B)
    await select(B)
    expect(isMain(w, 'other-video-pane')).toBe(true)
    expect(playerIn(w, 'other-video-pane')).toBe(A)
    expect(pane(w, 'main-view-badge').text()).toBe('A 视频 · 当前操作 B')
  })

  it('leaving the page and coming back starts from the default again', async () => {
    const first = mount(Host, { global: { stubs } })
    await first.find('[data-test=swap]').trigger('click')
    expect(isMain(first, 'map-pane')).toBe(true)
    first.unmount() // to another page: the selected drone did not change
    const again = mount(Host, { global: { stubs } })
    expect(isMain(again, 'video-pane')).toBe(true)
  })
})
