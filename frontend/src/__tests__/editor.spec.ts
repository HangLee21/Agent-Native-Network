import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'
import { useEditorStore } from '@/stores/editor'
import type { Route, Waypoint } from '@/api/routes'
import RouteEditor from '@/components/route/RouteEditor.vue'
import { setConfigForTest } from '@/config/runtime'

describe('route editor (R-06, R-07)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    setConfigForTest({ apiBaseUrl: 'http://api.test', wsUrl: 'ws://api.test/ws', map: { coordSys: 'WGS84', tileUrl: '', subdomains: '', attribution: '', maxZoom: 19, apiKey: '' } })
  })

  it('adds, moves, reorders and removes waypoints', () => {
    const ed = useEditorStore()
    ed.startNew()
    ed.addPoint({ lat: 22.58, lon: 113.94 })
    ed.addPoint({ lat: 22.581, lon: 113.941 })
    ed.addPoint({ lat: 22.582, lon: 113.942 })
    expect(ed.draft!.waypoints).toHaveLength(3)
    expect(ed.draft!.waypoints[0]!.relativeHeight).toBe(60)
    expect(ed.selected).toBe(2)
    ed.reorder(2, -1)
    expect(ed.draft!.waypoints[1]!.lat).toBe(22.582)
    ed.movePoint(0, { lat: 22.5805, lon: 113.9405 })
    expect(ed.draft!.waypoints[0]!.lat).toBe(22.5805)
    ed.removePoint(1)
    expect(ed.draft!.waypoints).toHaveLength(2)
    expect(ed.length).toBeGreaterThan(70)
    expect(ed.dirty).toBe(true)
  })

  it('saves via POST then PUT and keeps the server id/version', async () => {
    const calls: { url: string; method: string; body: unknown }[] = []
    vi.stubGlobal('fetch', vi.fn(async (url: string, init: RequestInit) => {
      calls.push({ url, method: init.method ?? 'GET', body: JSON.parse(String(init.body)) })
      const version = calls.length
      return new Response(JSON.stringify({ id: 'r1', version, name: 'A', waypoints: [] }), { status: 200 })
    }))
    const ed = useEditorStore()
    ed.startNew()
    ed.draft!.name = '  巡检 A '
    ed.addPoint({ lat: 22.58, lon: 113.94 })
    await ed.save()
    expect(calls[0]).toMatchObject({ url: 'http://api.test/api/v1/routes', method: 'POST' })
    expect((calls[0]!.body as { name: string }).name).toBe('巡检 A')
    ed.addPoint({ lat: 22.581, lon: 113.94 })
    await ed.save()
    expect(calls[1]).toMatchObject({ url: 'http://api.test/api/v1/routes/r1', method: 'PUT' })
    expect(ed.draft!.version).toBe(2)
    expect(ed.dirty).toBe(false)
    vi.unstubAllGlobals()
  })

  it('renders the waypoint list and empty state', async () => {
    const ed = useEditorStore()
    const w = mount(RouteEditor)
    expect(w.text()).toContain('当前没有打开的航线')
    await w.find('[data-test=new-route]').trigger('click')
    expect(w.text()).toContain('单击地图添加第一个航点')
    ed.addPoint({ lat: 22.58, lon: 113.94 })
    await w.vm.$nextTick()
    expect(w.findAll('.wp')).toHaveLength(1)
    expect(w.find('[data-test=waypoint-form]').exists()).toBe(true)
  })

  function threePoints() {
    const ed = useEditorStore()
    ed.startNew()
    ed.addPoint({ lat: 22.58, lon: 113.94 })
    ed.addPoint({ lat: 22.581, lon: 113.941 })
    ed.addPoint({ lat: 22.582, lon: 113.942 })
    return ed
  }

  function savedRoute(over: Partial<Route> = {}, wps: Partial<Waypoint>[] = []): Route {
    return {
      id: 'other', name: '汇合段', description: null, source: 'MANUAL', defaultSpeed: 8, defaultHeight: 20, takeoffSecurityHeight: 30,
      rthHeight: 50, rthHeightAuto: false, finishAction: 'HOVER', rcLostAction: 'RETURN_HOME', version: 1, createdAt: 0, updatedAt: 0,
      waypoints: wps.map((w, i) => ({ lat: 22.59 + i * 0.001, lon: 113.95, relativeHeight: 20, speed: null, hoverSeconds: 0, gimbalPitch: null,
        headingMode: 'FOLLOW_WAYLINE', turnMode: 'STOP', actions: [], ...w })),
      ...over,
    }
  }

  it('edits one waypoint, or every checked one when it is checked among others', () => {
    const ed = threePoints()
    expect(ed.setField(1, { relativeHeight: 40 })).toBe(1)
    expect(ed.draft!.waypoints.map((w) => w.relativeHeight)).toEqual([60, 40, 60])
    ed.toggleCheck(0)
    ed.toggleCheck(2)
    expect(ed.setField(2, { relativeHeight: 33 })).toBe(2)
    expect(ed.draft!.waypoints.map((w) => w.relativeHeight)).toEqual([33, 40, 33])
    // an unchecked row is edited alone even while others are checked
    expect(ed.setField(1, { hoverSeconds: 5 })).toBe(1)
    expect(ed.draft!.waypoints.map((w) => w.hoverSeconds)).toEqual([0, 5, 0])
    // a single checked row is just that row
    ed.setAllChecked(false)
    ed.toggleCheck(0)
    expect(ed.targetsOf(0)).toEqual([0])
  })

  it('shift-checks a range and keeps checks in step when waypoints move or go', () => {
    const ed = threePoints()
    ed.addPoint({ lat: 22.583, lon: 113.943 })
    ed.toggleCheck(0)
    ed.toggleCheck(2, true)
    expect(ed.checked).toEqual([0, 1, 2])
    ed.toggleCheck(1, true) // unchecks from the last one clicked (2) down to 1
    expect(ed.checked).toEqual([0])
    ed.setAllChecked(true)
    ed.removePoint(1)
    expect(ed.checked).toEqual([0, 1, 2])
    ed.setAllChecked(false)
    ed.toggleCheck(0)
    ed.reorder(0, 1)
    expect(ed.checked).toEqual([1])
    ed.toggleCheck(2)
    expect(ed.removeChecked()).toBe(2)
    expect(ed.draft!.waypoints).toHaveLength(1)
    expect(ed.checked).toEqual([])
  })

  it('applies a new default to every waypoint on request', () => {
    const ed = threePoints()
    ed.updateWaypoint(1, { relativeHeight: 45, speed: 4 })
    ed.applyToAll({ relativeHeight: 30 })
    ed.applyToAll({ speed: null })
    expect(ed.draft!.waypoints.every((w) => w.relativeHeight === 30 && w.speed === null)).toBe(true)
  })

  it('return height follows the last waypoint when automatic and is sent with the flag', () => {
    const ed = threePoints()
    expect(ed.draft!.rthHeightAuto).toBe(true)
    ed.updateWaypoint(2, { relativeHeight: 35 })
    expect(ed.rthEffective).toBe(35)
    expect(ed.request()).toMatchObject({ rthHeight: 35, rthHeightAuto: true })
    ed.draft!.rthHeightAuto = false
    ed.draft!.rthHeight = 70
    expect(ed.rthEffective).toBe(70)
    expect(ed.request()).toMatchObject({ rthHeight: 70, rthHeightAuto: false })
    // a route saved before the flag existed opens as manual, waypoints without waitForConfirm as not waiting
    const old = savedRoute({ rthHeightAuto: undefined as unknown as boolean }, [{}])
    delete (old.waypoints[0] as Partial<Waypoint>).waitForConfirm
    ed.loadRoute(old)
    expect(ed.draft!.rthHeightAuto).toBe(false)
    expect(ed.draft!.waypoints[0]!.waitForConfirm).toBe(false)
  })

  it('appends another route with a level transit at the higher height, both directions', () => {
    // end 60 m → start 20 m: fly level at 60 m to above the start, then descend there
    let ed = threePoints()
    let res = ed.appendRoute(savedRoute({}, [{ hoverSeconds: 2 }, {}]), { leaveHover: 4, arriveHover: 6, arriveWait: true, levelTransit: true })!
    let wps = ed.draft!.waypoints
    expect(res).toEqual({ from: 3, to: 5, transit: true })
    expect(wps).toHaveLength(6)
    expect(wps[2]!.hoverSeconds).toBe(4)
    expect(wps[3]).toMatchObject({ lat: 22.59, lon: 113.95, relativeHeight: 60, hoverSeconds: 0 })
    expect(wps[4]).toMatchObject({ lat: 22.59, relativeHeight: 20, hoverSeconds: 6, waitForConfirm: true })
    expect(wps[5]!.waitForConfirm).toBe(false)
    expect(ed.dirty).toBe(true)

    // end 10 m → start 20 m: climb above the end first
    setActivePinia(createPinia())
    ed = threePoints()
    ed.applyToAll({ relativeHeight: 10 })
    res = ed.appendRoute(savedRoute({}, [{}]), { leaveHover: 0, arriveHover: 0, arriveWait: false, levelTransit: true })!
    wps = ed.draft!.waypoints
    expect(res.transit).toBe(true)
    expect(wps[3]).toMatchObject({ lat: 22.582, lon: 113.942, relativeHeight: 20 })
    expect(wps[4]).toMatchObject({ lat: 22.59, relativeHeight: 20 })
  })

  it('appends without a transit point when asked not to or the heights match, keeping the other route speeds', () => {
    let ed = threePoints()
    ed.appendRoute(savedRoute({ defaultSpeed: 5 }, [{}, { speed: 9 }]), { leaveHover: 0, arriveHover: 0, arriveWait: false, levelTransit: false })
    let wps = ed.draft!.waypoints
    expect(wps).toHaveLength(5)
    expect(wps[3]!.speed).toBe(5) // followed that route's default, which differs from this one's
    expect(wps[4]!.speed).toBe(9)
    setActivePinia(createPinia())
    ed = threePoints()
    ed.applyToAll({ relativeHeight: 21 })
    const res = ed.appendRoute(savedRoute({}, [{}]), { leaveHover: 0, arriveHover: 0, arriveWait: false, levelTransit: true })!
    wps = ed.draft!.waypoints
    expect(res.transit).toBe(false) // 1 m apart in height: not worth a point
    expect(wps[3]!.speed).toBeNull() // same default speed: still follows it
    // the copy is independent of the source route
    const src = savedRoute({}, [{ actions: [{ type: 'TAKE_PHOTO', value: null }] }])
    ed.appendRoute(src, { leaveHover: 0, arriveHover: 0, arriveWait: false, levelTransit: false })
    ed.draft!.waypoints[4]!.actions.push({ type: 'ZOOM', value: 3 })
    expect(src.waypoints[0]!.actions).toHaveLength(1)
  })

  it('edits cells in the row, checked rows together', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('[]', { status: 200 })))
    const ed = threePoints()
    const w = mount(RouteEditor)
    await w.vm.$nextTick()
    const heights = w.findAll('[data-test=wp-height]')
    expect(heights).toHaveLength(3)
    await heights[1]!.setValue('42')
    expect(ed.draft!.waypoints[1]!.relativeHeight).toBe(42)
    await w.findAll('[data-test=wp-check]')[0]!.trigger('click')
    await w.findAll('[data-test=wp-check]')[2]!.trigger('click')
    expect(w.find('[data-test=batch-bar]').text()).toContain('已选 2 个')
    await w.findAll('[data-test=wp-speed]')[0]!.setValue('5')
    expect(ed.draft!.waypoints.map((x) => x.speed)).toEqual([5, null, 5])
    await w.findAll('[data-test=wp-speed]')[2]!.setValue('')
    expect(ed.draft!.waypoints.map((x) => x.speed)).toEqual([null, null, null])
    // an empty height puts the old value back instead of saving 0
    await w.findAll('[data-test=wp-height]')[1]!.setValue('')
    expect(ed.draft!.waypoints[1]!.relativeHeight).toBe(42)
    vi.unstubAllGlobals()
  })
})
