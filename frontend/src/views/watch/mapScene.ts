/**
 * 监视台 map: MapLibre (tilt and rotate; Leaflet cannot) with the configured satellite base map, and a 2D canvas on
 * top that draws the flights in 3D using the map's own camera matrix (a custom layer hands us the matrix every frame).
 * Drawing ported from the 「飞行记录复盘」 prototype; see docs/demo-redesign/monitor-station-design.md.
 */
import maplibregl, { type Map as MlMap, type StyleSpecification } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { config, type BaseMapConfig } from '@/config/runtime'
import { t } from '@/i18n'
import { wgs84ToGcj02 } from '@/utils/coord'
import { AUTO_ROTATE_SPEEDS, type WatchEngine } from './engine'
import {
  D2R, R_EARTH, RTH_MODES, bsearch, clamp, enu, footCorners, isNum, lastBefore, lerp, seenList, stateAt,
  type FlightState, type WatchFlight,
} from './model'

/** The prototype's 「斜视」: camera 34° above the horizon = 56° off vertical. The map never tilts further. */
export const MAX_PITCH = 56
const AUTO_MAX_ZOOM = 19.4
/** Camera glide time constants (s → ms): 全部 eases slowly, following keeps closer to the aircraft. */
const FRAME_TAU = 900
const FOLLOW_TAU = 350
/** 全部 zooms in only when everything fits in about 2/3 of the picture (2^-0.6); after a zoom it fills about 90%. */
const ZOOM_IN_ROOM = 0.6
const ZOOM_MARGIN = 0.15

// ------------------------------------------------------------------ colours
const rgbCache = new Map<string, [number, number, number]>()
let colorCtx: CanvasRenderingContext2D | null = null
/** How far above its ground point a dog's marker stands (metres in the scene): enough to read as 3-D when tilted. */
const DOG_LIFT_M = 6

export function rgbOf(color: string): [number, number, number] {
  const hit = rgbCache.get(color)
  if (hit) return hit
  colorCtx ??= document.createElement('canvas').getContext('2d')
  let out: [number, number, number] = [74, 144, 232]
  if (colorCtx) {
    colorCtx.fillStyle = '#4a90e8'
    colorCtx.fillStyle = color
    const v = String(colorCtx.fillStyle)
    if (v.startsWith('#')) { const n = parseInt(v.slice(1), 16); out = [(n >> 16) & 255, (n >> 8) & 255, n & 255] }
    else { const m = v.match(/[\d.]+/g); if (m && m.length >= 3) out = [+m[0]!, +m[1]!, +m[2]!] }
  }
  rgbCache.set(color, out)
  return out
}
export const rgba = (color: string, a: number) => { const [r, g, b] = rgbOf(color); return `rgba(${r},${g},${b},${a})` }

interface Tokens { panel: string; panel2: string; line: string; ink: string; ink2: string; ink3: string; warn: string; halo: string }
export function readTokens(): Tokens {
  const cs = getComputedStyle(document.documentElement)
  const g = (n: string, d: string) => cs.getPropertyValue(n).trim() || d
  return { panel: g('--panel', '#151b23'), panel2: g('--panel-2', '#1c2430'), line: g('--border', '#2b3644'), ink: g('--text', '#e6edf3'), ink2: g('--text-dim', '#9aa8b6'), ink3: g('--text-dim', '#9aa8b6'), warn: g('--warn', '#f5a524'), halo: 'rgba(8,12,14,0.85)' }
}
export const FONT = { sans: '-apple-system, "PingFang SC", "Microsoft YaHei", sans-serif', mono: '"SF Mono", Menlo, Consolas, monospace' }

// ------------------------------------------------------------------ base map
/** The satellite base map from config.json (id or label mentions satellite), else the default one. */
export function pickBaseMap(): BaseMapConfig | null {
  const m = config().map
  const list = m.baseMaps ?? []
  return list.find((b) => /satellite|卫星/i.test(b.id + b.label)) ?? list.find((b) => b.id === m.defaultBaseMap) ?? list[0] ?? null // i18n-ignore (matching, not text)
}
function tileUrls(url: string, subdomains: string | undefined, key: string): string[] {
  const u = url.replace('{key}', key)
  if (!u.includes('{s}')) return [u]
  const subs = (subdomains || 'abc').split('')
  return subs.map((s) => u.replace('{s}', s))
}
export function mapStyle(base: BaseMapConfig | null, forVideo = false): StyleSpecification {
  const key = config().map.apiKey ?? ''
  const sources: StyleSpecification['sources'] = {}
  const layers: StyleSpecification['layers'] = [{ id: 'bg', type: 'background', paint: { 'background-color': forVideo ? '#9fb3c2' : '#1d2428' } }]
  ;(base?.tiles ?? []).forEach((t, i) => {
    const id = i === 0 ? 'base' : `over${i}`
    sources[id] = { type: 'raster', tiles: tileUrls(t.url, t.subdomains, key), tileSize: 256, maxzoom: t.maxZoom ?? 18, attribution: t.attribution ?? '' }
    layers.push({ id, type: 'raster', source: id, paint: { 'raster-fade-duration': 0 }, layout: i === 0 ? {} : { visibility: 'none' } })
  })
  return { version: 8, sources, layers }
}

// ------------------------------------------------------------------ scene
export class MapScene {
  map: MlMap | null = null
  private cv: HTMLCanvasElement
  private ctx: CanvasRenderingContext2D
  private seenCv = document.createElement('canvas')
  private w = 0; private h = 0; private dpr = 1
  private PM: ArrayLike<number> | null = null
  private B = { b: [0, 0, 0, 0], ex: [0, 0, 0, 0], ey: [0, 0, 0, 0], ez: [0, 0, 0, 0] }
  private P: [number, number] = [0, 0]
  private geo = { lat: 0, lon: 0, mx0: 0, my0: 0, s: 1, gcj: false, key: '' }
  private C: Tokens = readTokens()
  /** Weak: flights are rebuilt as data arrives; a strong map kept every old copy (and its arrays) alive. */
  private states = new WeakMap<WatchFlight, FlightState>()
  private lastFrame = 0
  /** Where the camera is gliding to (local metres; zoom null = leave the zoom alone). */
  private aimAt: { x: number; y: number; zoom: number | null } | null = null
  private rot: { x: number; y: number; id: number } | null = null
  private moved = false
  private camMoving = false
  private lastUser = 0
  private base: BaseMapConfig | null = pickBaseMap()
  hover: { f: WatchFlight; i: number } | null = null
  onHover: ((h: { f: WatchFlight; i: number; x: number; y: number } | null) => void) | null = null
  onViewChange: (() => void) | null = null

  constructor(private engine: WatchEngine, private container: HTMLElement, overlay: HTMLCanvasElement) {
    this.cv = overlay
    this.ctx = overlay.getContext('2d')!
  }

  mount(): void {
    const S = this.engine.S
    this.updateGeo()
    const map = new maplibregl.Map({
      container: this.container, style: mapStyle(this.base), center: this.lngLatOf(0, 0), zoom: 18, pitch: MAX_PITCH, bearing: this.initialBearing(),
      maxPitch: MAX_PITCH, minPitch: 0, maxZoom: 20.5, minZoom: 3, fadeDuration: 0, attributionControl: { compact: false },
    })
    this.map = map
    map.addControl(new maplibregl.ScaleControl({ maxWidth: 110, unit: 'metric' }), 'bottom-left')
    map.on('load', () => {
      map.addLayer({ id: 'watch3d', type: 'custom', renderingMode: '2d', render: (_gl: WebGLRenderingContext, m: ArrayLike<number>) => { this.PM = m; this.draw() } } as maplibregl.CustomLayerInterface)
      this.applyTheme(); this.applyRoads()
      this.jumpToFit()
    })
    // the user drags the map: stop auto framing / following; zooming stops auto framing; rotating keeps both
    map.on('dragstart', (e) => { if (e.originalEvent) { this.lastUser = performance.now(); this.setCam('free') } })
    map.on('zoomstart', (e) => { if (e.originalEvent && S.cam === 'all') this.setCam('free') })
    map.on('rotatestart', (e) => { if (e.originalEvent) this.lastUser = performance.now() })
    map.on('pitch', () => this.onViewChange?.())
    map.on('rotate', () => this.onViewChange?.())
    const cc = map.getCanvasContainer()
    cc.addEventListener('mousemove', (e) => { if (!this.rot) this.hoverAt(e.offsetX, e.offsetY) })
    cc.addEventListener('mouseleave', () => { this.hover = null; this.onHover?.(null); map.triggerRepaint() })
    cc.addEventListener('click', () => { if (this.hover && !this.moved) this.engine.seek(this.hover.f.t[this.hover.i]!) })
    // 「旋转」: left / one-finger drag turns (left-right) and tilts (up-down, at most to 斜视)
    cc.addEventListener('pointerdown', (e) => {
      this.moved = false
      if (S.drag !== 'rotate' || e.button !== 0 || e.ctrlKey) return
      this.rot = { x: e.clientX, y: e.clientY, id: e.pointerId }
      cc.setPointerCapture(e.pointerId)
      this.lastUser = performance.now()
    })
    cc.addEventListener('pointermove', (e) => {
      if (!this.rot || e.pointerId !== this.rot.id) return
      const dx = e.clientX - this.rot.x, dy = e.clientY - this.rot.y
      this.rot.x = e.clientX; this.rot.y = e.clientY
      if (dx || dy) this.moved = true
      map.jumpTo({ bearing: map.getBearing() - dx * 0.35, pitch: clamp(map.getPitch() - dy * 0.3, 0, MAX_PITCH) })
      this.lastUser = performance.now()
    })
    const end = (e: PointerEvent) => { if (this.rot && e.pointerId === this.rot.id) this.rot = null }
    cc.addEventListener('pointerup', end); cc.addEventListener('pointercancel', end)
  }

  destroy(): void { this.map?.remove(); this.map = null }

  setCam(v: string): void { this.engine.S.cam = v; this.aimAt = null; this.lastFrame = 0; this.engine.bump() }
  setDrag(v: 'pan' | 'rotate'): void {
    this.engine.S.drag = v
    if (!this.map) return
    if (v === 'rotate') this.map.dragPan.disable(); else this.map.dragPan.enable()
  }
  /** Small tile in the rail (its video was swapped into the large area): no interaction. */
  setInteractive(on: boolean): void {
    const m = this.map
    if (!m) return
    for (const h of [m.dragPan, m.scrollZoom, m.boxZoom, m.dragRotate, m.keyboard, m.doubleClickZoom, m.touchZoomRotate, m.touchPitch]) on ? h.enable() : h.disable()
    if (on && this.engine.S.drag === 'rotate') m.dragPan.disable()
  }
  setView(v: 'tilt' | 'top'): void { this.map?.easeTo({ pitch: v === 'tilt' ? MAX_PITCH : 0, duration: 600 }) }
  north(): void { this.map?.easeTo({ bearing: 0, duration: 500 }) }
  zoom(dir: 1 | -1): void { if (!this.map) return; if (this.engine.S.cam === 'all') this.setCam('free'); dir > 0 ? this.map.zoomIn() : this.map.zoomOut() }

  applyTheme(): void {
    this.C = readTokens()
    const m = this.map
    if (!m || !m.getLayer('base')) return
    const dark = document.documentElement.dataset.theme !== 'outdoor'
    m.setPaintProperty('base', 'raster-brightness-max', dark ? 0.8 : 1)
    m.setPaintProperty('base', 'raster-saturation', dark ? -0.15 : 0)
    m.triggerRepaint()
  }
  applyRoads(): void {
    const m = this.map
    if (!m) return
    for (const l of m.getStyle()?.layers ?? []) if (l.id.startsWith('over')) m.setLayoutProperty(l.id, 'visibility', this.engine.S.layers.roads ? 'visible' : 'none')
  }

  resize(): void {
    const r = this.container.getBoundingClientRect()
    this.dpr = Math.min(2, window.devicePixelRatio || 1)
    this.w = r.width; this.h = r.height
    this.cv.width = Math.round(this.w * this.dpr); this.cv.height = Math.round(this.h * this.dpr)
    this.map?.resize()
    this.map?.triggerRepaint()
  }
  repaint(): void { this.map?.triggerRepaint() }
  pitch(): number { return this.map?.getPitch() ?? MAX_PITCH }
  bearing(): number { return this.map?.getBearing() ?? 0 }

  // ---------------------------------------------------------------- geometry
  /** Base maps in GCJ-02 get the offset at the scene origin (the same for a few hundred metres). */
  updateGeo(): void {
    const sc = this.engine.S.scene
    const key = `${sc.origin.lat},${sc.origin.lon}`
    if (key === this.geo.key) return
    const gcj = this.base?.coordSys === 'GCJ02'
    const g = gcj ? wgs84ToGcj02(sc.origin.lat, sc.origin.lon) : { lat: sc.origin.lat, lon: sc.origin.lon }
    this.geo = { lat: g.lat, lon: g.lon, gcj, key,
      mx0: (g.lon + 180) / 360, my0: (180 - (180 / Math.PI) * Math.log(Math.tan(Math.PI / 4 + (g.lat * D2R) / 2))) / 360,
      s: 1 / (2 * Math.PI * R_EARTH * Math.cos(g.lat * D2R)) }
  }
  lngLatOf(x: number, y: number): [number, number] {
    return [this.geo.lon + x / (R_EARTH * Math.cos(this.geo.lat * D2R)) / D2R, this.geo.lat + y / R_EARTH / D2R]
  }
  private xyOf(ll: { lng: number; lat: number }): [number, number] {
    return [(ll.lng - this.geo.lon) * D2R * R_EARTH * Math.cos(this.geo.lat * D2R), (ll.lat - this.geo.lat) * D2R * R_EARTH]
  }
  /** clip = M · [mx0 + x·s, my0 − y·s, z·s, 1] precomputed as one base vector plus three axes. */
  private basis(): void {
    const m = this.PM!, s = this.geo.s, mx = this.geo.mx0, my = this.geo.my0, B = this.B
    for (let r = 0; r < 4; r++) {
      B.b[r] = m[r]! * mx + m[4 + r]! * my + m[12 + r]!
      B.ex[r] = m[r]! * s; B.ey[r] = -m[4 + r]! * s; B.ez[r] = m[8 + r]! * s
    }
  }
  private proj(x: number, y: number, z: number): boolean {
    const B = this.B
    const w = B.b[3]! + x * B.ex[3]! + y * B.ey[3]! + z * B.ez[3]!
    if (w <= 1e-6) return false
    this.P[0] = ((B.b[0]! + x * B.ex[0]! + y * B.ey[0]! + z * B.ez[0]!) / w + 1) * 0.5 * this.w
    this.P[1] = (1 - (B.b[1]! + x * B.ex[1]! + y * B.ey[1]! + z * B.ez[1]!) / w) * 0.5 * this.h
    return true
  }
  private seg(c: CanvasRenderingContext2D, x1: number, y1: number, z1: number, x2: number, y2: number, z2: number): void {
    if (!this.proj(x1, y1, z1)) return
    const a = this.P[0], b = this.P[1]
    if (!this.proj(x2, y2, z2)) return
    c.moveTo(a, b); c.lineTo(this.P[0], this.P[1])
  }
  initialBearing(): number {
    // the track's long axis across the screen, turned 28° for depth (the prototype's 斜视)
    const fl = this.engine.S.flights
    let n = 0, mx = 0, my = 0
    for (const f of fl) for (let i = 0; i < f.n; i += 3) { mx += f.x[i]!; my += f.y[i]!; n++ }
    if (n < 3) return 0
    mx /= n; my /= n
    let cxx = 0, cyy = 0, cxy = 0
    for (const f of fl) for (let i = 0; i < f.n; i += 3) { const dx = f.x[i]! - mx, dy = f.y[i]! - my; cxx += dx * dx; cyy += dy * dy; cxy += dx * dy }
    return -0.5 * Math.atan2(2 * cxy, cxx - cyy) / D2R - 28
  }

  // ---------------------------------------------------------------- camera
  private framePoints(): [number, number, number][] {
    const S = this.engine.S, cut = this.engine.mapCutoff(), pts: [number, number, number][] = []
    for (const f of S.flights) {
      pts.push([f.tx, f.ty, 0])
      const end = cut === Infinity ? f.n - 1 : bsearch(f.t, cut)
      for (let i = 0; i <= end; i += 3) pts.push([f.x[i]!, f.y[i]!, f.z[i]!], [f.x[i]!, f.y[i]!, 0])
      const st = this.states.get(f)
      if (st) pts.push([st.x, st.y, st.z], [st.x, st.y, 0])
      if (!S.hideRoute && S.layers.route) for (const w of f.route) { const [x, y] = enu(S.scene, w.lat, w.lon); pts.push([x, y, f.ell0 + (w.relativeHeight ?? f.routeDefH ?? 0) - S.scene.datum]) }
    }
    let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity
    for (const p of pts) { x0 = Math.min(x0, p[0]); x1 = Math.max(x1, p[0]); y0 = Math.min(y0, p[1]); y1 = Math.max(y1, p[1]) }
    const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2, r = 45
    if (x1 - x0 < 2 * r) pts.push([cx - r, cy, 0], [cx + r, cy, 0])
    if (y1 - y0 < 2 * r) pts.push([cx, cy - r, 0], [cx, cy + r, 0])
    return pts
  }
  jumpToFit(): void {
    const m = this.map
    if (!m || !this.engine.S.flights.length) return
    this.updateGeo()
    const pts = this.framePoints()
    let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity
    for (const p of pts) { x0 = Math.min(x0, p[0]); x1 = Math.max(x1, p[0]); y0 = Math.min(y0, p[1]); y1 = Math.max(y1, p[1]) }
    const cam = m.cameraForBounds([this.lngLatOf(x0, y0), this.lngLatOf(x1, y1)], { padding: 60, bearing: m.getBearing() })
    if (cam?.center && isNum(cam.zoom)) m.jumpTo({ center: cam.center, zoom: Math.min(AUTO_MAX_ZOOM, cam.zoom - 0.3) })
    this.aimAt = null; this.lastFrame = 0
  }
  /**
   * Once per frame. 全部: where the camera should be (centre and zoom that fit what is drawn, with tilt and height) is
   * worked out 10× a second; following: the device's position. Every frame the camera glides a little towards that
   * target, so it moves smoothly instead of in 10 Hz steps. Zoom has a dead band: it only changes when something would
   * leave the picture or everything has shrunk well inside it, so the view does not keep breathing in and out.
   * Auto-rotate: turn around the current view centre.
   */
  step(dt: number): void {
    const m = this.map, S = this.engine.S
    if (!m || !this.PM || this.rot || !S.flights.length) return
    if (m.isMoving() && !this.camMoving) return
    this.updateGeo()
    const opts: { center?: maplibregl.LngLatLike; zoom?: number; bearing?: number } = {}
    if (S.autoRotate > 0 && performance.now() - this.lastUser > 1500) opts.bearing = m.getBearing() + AUTO_ROTATE_SPEEDS[S.autoRotate]! * dt / 1000
    const tNow = performance.now()
    if (S.cam === 'free') this.aimAt = null
    else if (S.cam !== 'all') {
      const f = S.flights.find((g) => g.id === S.cam)
      const st = f ? (this.states.get(f) ?? stateAt(f, S.t)) : null
      this.aimAt = st ? { x: st.x, y: st.y, zoom: null } : null
    } else if (tNow - this.lastFrame >= 100) {
      // framing projects every track point: at most 10× a second
      this.lastFrame = tNow
      this.aimAll()
    }
    const aim = this.aimAt
    if (aim) {
      const a = 1 - Math.exp(-dt / (S.cam === 'all' ? FRAME_TAU : FOLLOW_TAU))
      const [cx, cy] = this.xyOf(m.getCenter())
      if (Math.hypot(aim.x - cx, aim.y - cy) > 0.02) opts.center = this.lngLatOf(lerp(cx, aim.x, a), lerp(cy, aim.y, a))
      const z = m.getZoom()
      if (aim.zoom !== null && Math.abs(aim.zoom - z) > 0.001) opts.zoom = lerp(z, aim.zoom, a)
    }
    if (opts.center || opts.zoom !== undefined || opts.bearing !== undefined) {
      this.camMoving = true
      m.jumpTo(opts)
      this.camMoving = false
    }
  }
  /** 全部: target centre (always) and zoom (only outside the dead band) that fit everything drawn so far. */
  private aimAll(): void {
    const m = this.map!
    this.basis()
    let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity, ok = 0
    for (const p of this.framePoints()) { if (!this.proj(p[0], p[1], p[2])) continue; ok++; x0 = Math.min(x0, this.P[0]); x1 = Math.max(x1, this.P[0]); y0 = Math.min(y0, this.P[1]); y1 = Math.max(y1, this.P[1]) }
    if (!ok) return
    const compact = this.w < 420
    const padT = compact ? 24 : 96, padB = compact ? 16 : 48, padL = compact ? 12 : 40, padR = compact ? 12 : 64
    const aw = this.w - padL - padR, ah = this.h - padT - padB
    // > 0: room to zoom in by this much; < 0: something is outside the picture
    const room = Math.log2(Math.min(aw / Math.max(40, x1 - x0), ah / Math.max(40, y1 - y0)))
    const z = m.getZoom()
    let zoom = this.aimAt?.zoom ?? null
    if (room < 0 || room > ZOOM_IN_ROOM || zoom === null) zoom = z + room - ZOOM_MARGIN
    zoom = Math.min(AUTO_MAX_ZOOM, zoom)
    const c = m.unproject([this.w / 2 + (x0 + x1) / 2 - (padL + aw / 2), this.h / 2 + (y0 + y1) / 2 - (padT + ah / 2)])
    const [x, y] = this.xyOf(c)
    this.aimAt = { x, y, zoom }
  }

  // ---------------------------------------------------------------- hover
  private hoverAt(x: number, y: number): void {
    let best: { f: WatchFlight; i: number } | null = null, bd = 100
    const cut = this.engine.mapCutoff()
    for (const f of this.engine.S.flights) {
      if (!f._ok) continue
      const end = cut === Infinity ? f.n - 1 : bsearch(f.t, cut)
      for (let i = 0; i <= end; i++) { if (!f._ok[i]) continue; const dx = f._sx![i]! - x, dy = f._sy![i]! - y, d = dx * dx + dy * dy; if (d < bd) { bd = d; best = { f, i } } }
    }
    const changed = (best && (!this.hover || this.hover.f !== best.f || this.hover.i !== best.i)) || (!best && this.hover)
    this.hover = best
    this.container.classList.toggle('hot', !!best)
    this.onHover?.(best ? { ...best, x, y } : null)
    if (changed) this.map?.triggerRepaint()
  }

  // ---------------------------------------------------------------- drawing
  private draw(): void {
    const ctx = this.ctx, S = this.engine.S, C = this.C
    ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0)
    ctx.clearRect(0, 0, this.w, this.h)
    if (!S.flights.length || !this.PM) return
    this.updateGeo()
    this.basis()
    const L = S.layers, T = S.t, cut = this.engine.mapCutoff(), future = cut === Infinity, showRoute = !S.hideRoute
    for (const f of S.flights) this.states.set(f, stateAt(f, T, this.states.get(f) ?? {}))
    for (const f of S.flights) {
      if (!f._sx || f._sx.length !== f.n) { f._sx = new Float32Array(f.n); f._sy = new Float32Array(f.n); f._ok = new Uint8Array(f.n); f._gx = new Float32Array(f.n); f._gy = new Float32Array(f.n); f._gok = new Uint8Array(f.n) }
      const sx = f._sx, sy = f._sy!, ok = f._ok!, gx = f._gx!, gy = f._gy!, gok = f._gok!
      for (let i = 0; i < f.n; i++) {
        if (this.proj(f.x[i]!, f.y[i]!, f.z[i]!)) { sx[i] = this.P[0]; sy[i] = this.P[1]; ok[i] = 1 } else ok[i] = 0
        if (this.proj(f.x[i]!, f.y[i]!, 0)) { gx[i] = this.P[0]; gy[i] = this.P[1]; gok[i] = 1 } else gok[i] = 0
      }
    }
    if (L.seen) this.drawSeen()
    for (const f of S.flights) {
      if (!L.curtain) continue
      const st = this.states.get(f)!, ic = st.before ? -1 : st.i
      if (ic >= 0) this.curtain(f, 0, ic, rgba(f.color, 0.2), st.inside ? st : null)
      if (future) this.curtain(f, Math.max(0, ic), f.n - 1, rgba(f.color, 0.07), null)
      ctx.lineWidth = 1.25; ctx.strokeStyle = rgba(f.color, 0.75); ctx.setLineDash([])
      if (ic >= 0) this.polyline(f, 0, ic, true, st.inside ? st : null, 'end')
      if (future) { ctx.strokeStyle = rgba(f.color, 0.3); ctx.lineWidth = 1; this.polyline(f, Math.max(0, ic), f.n - 1, true, null) }
    }
    if (showRoute && L.route) for (const f of S.flights) this.drawRoute(f)
    for (const f of S.flights) {
      if (f.kind === 'dog') continue      // a dog has no take-off point
      ctx.lineWidth = 3.5; ctx.strokeStyle = C.halo; ctx.beginPath(); this.circleGround(f.tx, f.ty, 2.6); ctx.stroke()
      ctx.lineWidth = 1.5; ctx.strokeStyle = f.color; ctx.beginPath(); this.circleGround(f.tx, f.ty, 2.6); ctx.stroke()
      ctx.beginPath(); this.seg(ctx, f.tx - 1.4, f.ty, 0, f.tx + 1.4, f.ty, 0); this.seg(ctx, f.tx, f.ty - 1.4, 0, f.tx, f.ty + 1.4, 0); ctx.stroke()
      if (L.labels && this.proj(f.tx, f.ty, 0)) this.tagText(t('{label} 起飞点', { label: f.label }), this.P[0] + 8, this.P[1] + 13)
      if (L.rc && f.rc.length) {
        const rc = lastBefore(f.rc, T) ?? f.rc[0]!
        if (this.proj(rc.x, rc.y, 0)) {
          const X = Math.round(this.P[0]), Y = Math.round(this.P[1])
          ctx.fillStyle = C.panel; ctx.strokeStyle = C.ink2; ctx.lineWidth = 1.25
          ctx.beginPath(); ctx.rect(X - 3.5, Y - 3.5, 7, 7); ctx.fill(); ctx.stroke()
          ctx.fillStyle = f.color; ctx.fillRect(X - 1.5, Y - 1.5, 3, 3)
          if (L.labels) this.tagText(t('{label} 遥控器', { label: f.label }), X + 8, Y - 6)
        }
      }
    }
    if (L.track) for (const f of S.flights) {
      const st = this.states.get(f)!, ic = st.before ? -1 : st.i
      ctx.setLineDash([]); ctx.lineCap = 'round'; ctx.lineJoin = 'round'
      if (future) { ctx.strokeStyle = rgba(f.color, 0.45); ctx.lineWidth = 1.25; this.polyline(f, Math.max(0, ic), f.n - 1, false, st.inside ? st : null, 'start') }
      if (ic >= 0) {
        ctx.strokeStyle = C.halo; ctx.lineWidth = 4.5; this.polyline(f, 0, ic, false, st.inside ? st : null, 'end')
        ctx.strokeStyle = f.color; ctx.lineWidth = 2.25; this.polyline(f, 0, ic, false, st.inside ? st : null, 'end')
      }
    }
    if (showRoute && L.plan) for (const f of S.flights) {
      const st = this.states.get(f)!
      if (!st.inside) continue
      const plan = this.currentPlan(f, T, st)
      if (!plan) continue
      ctx.strokeStyle = rgba(f.color, 0.95); ctx.lineWidth = 1.5; ctx.setLineDash([1.5, 4]); ctx.lineCap = 'round'
      ctx.beginPath(); for (let k = 1; k < plan.pts.length; k++) { const a = plan.pts[k - 1]!, b = plan.pts[k]!; this.seg(ctx, a[0], a[1], a[2], b[0], b[1], b[2]) } ctx.stroke(); ctx.setLineDash([])
    }
    for (const f of S.flights) {
      const st = this.states.get(f)!
      if (!st.inside || st.rel < 2) continue
      if (L.foot) this.footprint(f, st)
      if (L.los && S.footMode !== 'nadir') {
        const yaw = st.gy * D2R, pit = st.gp * D2R
        const dx = Math.sin(yaw) * Math.cos(pit), dy = Math.cos(yaw) * Math.cos(pit), dz = Math.sin(pit)
        let len = 45
        if (dz < -0.035) len = Math.min(400, st.z / -dz)
        ctx.strokeStyle = rgba(f.color, 0.7); ctx.lineWidth = 1; ctx.setLineDash([2, 3])
        ctx.beginPath(); this.seg(ctx, st.x, st.y, st.z, st.x + dx * len, st.y + dy * len, st.z + dz * len); ctx.stroke(); ctx.setLineDash([])
      }
    }
    if (L.sep) for (const p of S.pairs) {
      const a = this.states.get(p.a), b = this.states.get(p.b)
      if (!a?.inside || !b?.inside) continue
      ctx.strokeStyle = 'rgba(232,238,240,0.85)'; ctx.lineWidth = 1; ctx.setLineDash([4, 4])
      ctx.beginPath(); this.seg(ctx, a.x, a.y, a.z, b.x, b.y, b.z); ctx.stroke(); ctx.setLineDash([])
      if (this.proj((a.x + b.x) / 2, (a.y + b.y) / 2, (a.z + b.z) / 2)) this.pillText(Math.hypot(b.x - a.x, b.y - a.y, b.z - a.z).toFixed(1) + ' m', this.P[0], this.P[1])
    }
    const labels: { f: WatchFlight; st: FlightState; X: number; Y: number }[] = []
    for (const f of S.flights) {
      const st = this.states.get(f)!
      const fresh = st.inside && st.stale < 6000
      const dog = f.kind === 'dog'
      // a dog walks on the ground: its marker stands a little above its ground point on a dashed line, like a drone's
      const z = dog ? DOG_LIFT_M : st.z
      ctx.globalAlpha = fresh ? 1 : 0.5
      ctx.strokeStyle = rgba(f.color, 0.85); ctx.lineWidth = dog ? 1.25 : 1
      if (dog) ctx.setLineDash([3, 3])
      ctx.beginPath(); this.seg(ctx, st.x, st.y, z, st.x, st.y, 0); ctx.stroke(); ctx.setLineDash([])
      ctx.fillStyle = rgba(f.color, dog ? 0.85 : 0.6); ctx.beginPath(); this.circleGround(st.x, st.y, dog ? 1.1 : 1.3); ctx.fill()
      if (this.proj(st.x, st.y, z)) {
        const X = this.P[0], Y = this.P[1]
        const hx = st.x + Math.sin(st.head * D2R) * 5, hy = st.y + Math.cos(st.head * D2R) * 5
        let ang = -Math.PI / 2
        if (this.proj(hx, hy, z)) ang = Math.atan2(this.P[1] - Y, this.P[0] - X)
        if (f.kind === 'dog') this.dogGlyph(X, Y, isNum(f.head[st.i]) ? ang : null, f.color, f.id === S.sel)
        else this.glyph(X, Y, ang, f.color, f.id === S.sel)
        labels.push({ f, st, X, Y })
      }
      ctx.globalAlpha = 1
    }
    this.placeLabels(labels)
    const hv = this.hover
    if (hv && hv.f._ok?.[hv.i]) {
      const X = hv.f._sx![hv.i]!, Y = hv.f._sy![hv.i]!
      ctx.lineWidth = 2; ctx.strokeStyle = C.halo; ctx.beginPath(); ctx.arc(X, Y, 5.5, 0, 7); ctx.stroke()
      ctx.lineWidth = 1.5; ctx.strokeStyle = hv.f.color; ctx.beginPath(); ctx.arc(X, Y, 5, 0, 7); ctx.stroke()
    }
  }
  stateOf(f: WatchFlight): FlightState | undefined { return this.states.get(f) }

  private polyline(f: WatchFlight, i0: number, i1: number, ground: boolean, st: FlightState | null, join?: 'start' | 'end'): void {
    const ctx = this.ctx
    const sx = ground ? f._gx! : f._sx!, sy = ground ? f._gy! : f._sy!, ok = ground ? f._gok! : f._ok!
    const pz = (s: FlightState) => (ground ? 0 : s.z)
    ctx.beginPath()
    let pen = false
    if (join === 'start' && st && this.proj(st.x, st.y, pz(st))) { ctx.moveTo(this.P[0], this.P[1]); pen = true; i0 = Math.min(f.n - 1, i0 + 1) }
    for (let i = i0; i <= i1; i++) {
      if (!ok[i]) { pen = false; continue }
      if (pen && i > 0 && f.t[i]! - f.t[i - 1]! > 12000) pen = false
      if (!pen) { ctx.moveTo(sx[i]!, sy[i]!); pen = true } else ctx.lineTo(sx[i]!, sy[i]!)
    }
    if (join === 'end' && st && pen && this.proj(st.x, st.y, pz(st))) ctx.lineTo(this.P[0], this.P[1])
    ctx.stroke()
  }
  private curtain(f: WatchFlight, i0: number, i1: number, fill: string, tail: FlightState | null): void {
    const ctx = this.ctx, sx = f._sx!, sy = f._sy!, gx = f._gx!, gy = f._gy!, ok = f._ok!, gok = f._gok!
    const quad = (ax: number, ay: number, bx: number, by: number, cx: number, cy: number, dx: number, dy: number) => {
      const cr = (bx - dx) * (cy - ay) - (by - dy) * (cx - ax)
      if (cr >= 0) { ctx.moveTo(ax, ay); ctx.lineTo(bx, by); ctx.lineTo(cx, cy); ctx.lineTo(dx, dy) } else { ctx.moveTo(dx, dy); ctx.lineTo(cx, cy); ctx.lineTo(bx, by); ctx.lineTo(ax, ay) }
      ctx.closePath()
    }
    ctx.beginPath()
    for (let i = i0; i < i1; i++) {
      const j = i + 1
      if (!(ok[i] && ok[j] && gok[i] && gok[j]) || f.t[j]! - f.t[i]! > 12000) continue
      if (f.z[i]! < 0.3 && f.z[j]! < 0.3) continue
      quad(sx[i]!, sy[i]!, sx[j]!, sy[j]!, gx[j]!, gy[j]!, gx[i]!, gy[i]!)
    }
    if (tail && ok[i1] && gok[i1] && tail.z > 0.3 && this.proj(tail.x, tail.y, tail.z)) {
      const ax = this.P[0], ay = this.P[1]
      if (this.proj(tail.x, tail.y, 0)) quad(sx[i1]!, sy[i1]!, ax, ay, this.P[0], this.P[1], gx[i1]!, gy[i1]!)
    }
    ctx.fillStyle = fill
    ctx.fill('nonzero')
  }
  private circleGround(x: number, y: number, r: number): void {
    let first = true
    for (let k = 0; k <= 28; k++) {
      const a = (k / 28) * Math.PI * 2
      if (this.proj(x + Math.cos(a) * r, y + Math.sin(a) * r, 0)) { if (first) { this.ctx.moveTo(this.P[0], this.P[1]); first = false } else this.ctx.lineTo(this.P[0], this.P[1]) }
    }
  }
  private drawRoute(f: WatchFlight): void {
    if (!f.route.length) return
    const ctx = this.ctx, S = this.engine.S
    const pts = f.route.map((w) => { const [x, y] = enu(S.scene, w.lat, w.lon); const h = isNum(w.relativeHeight) ? w.relativeHeight : (f.routeDefH ?? 0); return { x, y, z: f.ell0 + h - S.scene.datum, hold: !!w.waitForConfirm } })
    ctx.lineWidth = 1; ctx.strokeStyle = rgba(f.color, 0.35); ctx.setLineDash([])
    ctx.beginPath(); for (const p of pts) this.seg(ctx, p.x, p.y, 0, p.x, p.y, p.z); ctx.stroke()
    ctx.strokeStyle = rgba(f.color, 0.9); ctx.lineWidth = 1.5; ctx.setLineDash([6, 4])
    ctx.beginPath()
    const fz = f.ell0 - S.scene.datum, p0 = pts[0]!
    this.seg(ctx, f.tx, f.ty, fz, f.tx, f.ty, p0.z); this.seg(ctx, f.tx, f.ty, p0.z, p0.x, p0.y, p0.z)
    for (let k = 1; k < pts.length; k++) this.seg(ctx, pts[k - 1]!.x, pts[k - 1]!.y, pts[k - 1]!.z, pts[k]!.x, pts[k]!.y, pts[k]!.z)
    ctx.stroke(); ctx.setLineDash([])
    pts.forEach((p, k) => {
      if (!this.proj(p.x, p.y, p.z)) return
      const X = this.P[0], Y = this.P[1]
      ctx.fillStyle = this.C.halo; ctx.beginPath(); ctx.arc(X, Y, 5, 0, 7); ctx.fill()
      ctx.strokeStyle = f.color; ctx.lineWidth = 1.5; ctx.beginPath(); ctx.arc(X, Y, 3.6, 0, 7); ctx.stroke()
      if (p.hold) { ctx.beginPath(); ctx.arc(X, Y, 7, 0, 7); ctx.lineWidth = 1; ctx.stroke() }
      if (S.layers.labels) this.tagText(p.hold ? t('{n} 等待确认', { n: k + 1 }) : String(k + 1), X + 8, Y - 6, true)
    })
  }
  private currentPlan(f: WatchFlight, T: number, st: FlightState) {
    if (!f.plans.length) return null
    if (RTH_MODES.has(st.mode)) { let r = null; for (const p of f.plans) { if (p.t > T) break; if (p.kind === 'returnHome') r = p } return r }
    const ex = lastBefore(f.exec, T)
    if (!ex || !['TAKING_OFF', 'FLYING'].includes(ex.state)) return null
    let r = null
    for (const p of f.plans) { if (p.t > T) break; if (p.kind !== 'returnHome' && p.t >= ex.t - 3000) r = p }
    return r
  }
  private footPath(c: CanvasRenderingContext2D, cs: [number, number][]): boolean {
    const s: number[] = []
    for (const q of cs) { if (!this.proj(q[0], q[1], 0)) return false; s.push(this.P[0], this.P[1]) }
    // one winding for every quad: overlapping quads filled 'nonzero' paint their union once (no darker overlaps, no holes)
    const area = (s[2]! - s[0]!) * (s[5]! - s[1]!) - (s[4]! - s[0]!) * (s[3]! - s[1]!) + (s[4]! - s[0]!) * (s[7]! - s[1]!) - (s[6]! - s[0]!) * (s[5]! - s[1]!)
    const order = area >= 0 ? [0, 1, 2, 3] : [3, 2, 1, 0]
    c.moveTo(s[order[0]! * 2]!, s[order[0]! * 2 + 1]!)
    for (let k = 1; k < 4; k++) c.lineTo(s[order[k]! * 2]!, s[order[k]! * 2 + 1]!)
    c.closePath()
    return true
  }
  private footprint(f: WatchFlight, st: FlightState): void {
    const cs = footCorners(st, this.engine.S.footMode)
    if (!cs) return
    const ctx = this.ctx
    ctx.beginPath()
    if (!this.footPath(ctx, cs)) return
    ctx.fillStyle = rgba(f.color, 0.14); ctx.fill()
    ctx.strokeStyle = rgba(f.color, 0.8); ctx.lineWidth = 1; ctx.setLineDash([3, 3]); ctx.stroke(); ctx.setLineDash([])
  }
  /** 相机看过的区域: every footprint up to now merged into one region per drone, outlined once. */
  private drawSeen(): void {
    const S = this.engine.S, ctx = this.ctx, T = S.t
    if (this.seenCv.width !== this.cv.width || this.seenCv.height !== this.cv.height) { this.seenCv.width = this.cv.width; this.seenCv.height = this.cv.height }
    const ec = this.seenCv.getContext('2d')!
    for (const f of S.flights) {
      const list = seenList(f, S.footMode, S.scene.datum)
      const st = this.states.get(f)
      const cur = st && st.inside ? footCorners(st, S.footMode) : null
      if ((!list.length || list[0]!.t > T) && !cur) continue
      const build = (g: CanvasRenderingContext2D) => { g.beginPath(); for (const it of list) { if (it.t > T) break; this.footPath(g, it.cs) } if (cur) this.footPath(g, cur) }
      build(ctx); ctx.fillStyle = rgba(f.color, 0.17); ctx.fill('nonzero')
      ec.setTransform(1, 0, 0, 1, 0, 0); ec.clearRect(0, 0, this.seenCv.width, this.seenCv.height); ec.setTransform(this.dpr, 0, 0, this.dpr, 0, 0)
      ec.globalCompositeOperation = 'source-over'; build(ec); ec.lineWidth = 2.5; ec.lineJoin = 'round'; ec.strokeStyle = rgba(f.color, 0.85); ec.stroke()
      ec.globalCompositeOperation = 'destination-out'; ec.fillStyle = '#000'; ec.fill('nonzero'); ec.globalCompositeOperation = 'source-over'
      ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.drawImage(this.seenCv, 0, 0); ctx.restore()
    }
  }
  private glyph(X: number, Y: number, ang: number, c: string, sel: boolean): void {
    const ctx = this.ctx
    ctx.save(); ctx.translate(X, Y); ctx.rotate(ang)
    ctx.beginPath(); ctx.moveTo(12, 0); ctx.lineTo(-7, 7.5); ctx.lineTo(-2.5, 0); ctx.lineTo(-7, -7.5); ctx.closePath()
    ctx.lineJoin = 'round'; ctx.lineWidth = 3.5; ctx.strokeStyle = this.C.halo; ctx.stroke(); ctx.fillStyle = c; ctx.fill()
    ctx.restore()
    if (sel) { ctx.strokeStyle = rgba(c, 0.8); ctx.lineWidth = 1.25; ctx.beginPath(); ctx.arc(X, Y, 16, 0, 7); ctx.stroke() }
  }
  /** A dog (D-40): a rounded square like on the platform's maps, with an arrow when it has a heading. */
  private dogGlyph(X: number, Y: number, ang: number | null, c: string, sel: boolean): void {
    const ctx = this.ctx
    if (ang !== null) {
      ctx.save(); ctx.translate(X, Y); ctx.rotate(ang)
      ctx.beginPath(); ctx.moveTo(17, 0); ctx.lineTo(10, 5); ctx.lineTo(11.5, 0); ctx.lineTo(10, -5); ctx.closePath()
      ctx.lineJoin = 'round'; ctx.lineWidth = 3; ctx.strokeStyle = this.C.halo; ctx.stroke(); ctx.fillStyle = c; ctx.fill()
      ctx.restore()
    }
    this.rr(X - 7.5, Y - 7.5, 15, 15, 4)
    ctx.lineWidth = 3.5; ctx.strokeStyle = this.C.halo; ctx.stroke(); ctx.fillStyle = c; ctx.fill()
    ctx.fillStyle = this.C.halo; ctx.beginPath(); ctx.arc(X, Y, 2.6, 0, 7); ctx.fill()
    if (sel) { ctx.strokeStyle = rgba(c, 0.8); ctx.lineWidth = 1.25; ctx.beginPath(); ctx.arc(X, Y, 16, 0, 7); ctx.stroke() }
  }
  private rr(x: number, y: number, w: number, h: number, r: number): void {
    const c = this.ctx
    c.beginPath(); c.moveTo(x + r, y); c.arcTo(x + w, y, x + w, y + h, r); c.arcTo(x + w, y + h, x, y + h, r); c.arcTo(x, y + h, x, y, r); c.arcTo(x, y, x + w, y, r); c.closePath()
  }
  private pillLabel(x: number, y: number, color: string, main: string, val: string, ax: number, ay: number) {
    const ctx = this.ctx, C = this.C
    ctx.font = '600 12px ' + FONT.sans; const w1 = ctx.measureText(main).width
    ctx.font = '400 11.5px ' + FONT.mono; const w2 = ctx.measureText(val).width
    const w = 8 + 8 + 6 + w1 + 7 + w2 + 9, h = 22
    if (x + w > this.w - 8) x = ax - 16 - w
    ctx.strokeStyle = 'rgba(232,238,240,0.6)'; ctx.lineWidth = 1
    ctx.beginPath(); ctx.moveTo(ax + (x > ax ? 8 : -8), ay - 6); ctx.lineTo(x > ax ? x : x + w, y + h / 2); ctx.stroke()
    this.rr(x, y, w, h, 3); ctx.fillStyle = rgba(C.panel, 0.94); ctx.fill(); ctx.strokeStyle = C.line; ctx.stroke()
    ctx.fillStyle = color; this.rr(x + 8, y + 7, 8, 8, 2); ctx.fill()
    ctx.textBaseline = 'middle'; ctx.fillStyle = C.ink; ctx.font = '600 12px ' + FONT.sans; ctx.fillText(main, x + 22, y + h / 2 + 0.5)
    ctx.fillStyle = C.ink2; ctx.font = '400 11.5px ' + FONT.mono; ctx.fillText(val, x + 22 + w1 + 7, y + h / 2 + 0.5)
    ctx.textBaseline = 'alphabetic'
    return { x, y, w, h }
  }
  private placeLabels(labels: { f: WatchFlight; st: FlightState; X: number; Y: number }[]): void {
    const placed: { x: number; y: number; w: number; h: number }[] = []
    for (const L of labels) {
      const st = L.st
      const dog = L.f.kind === 'dog'
      const val = !st.inside ? (st.before ? (dog ? t('未开始') : t('地面')) : dog ? t('记录结束') : t('已降落'))
        : st.stale >= 6000 ? t('失联 {n} 秒', { n: Math.round(st.stale / 1000) })
          : dog ? t('机器狗 · {v} m/s', { v: st.hs.toFixed(1) }) : `${st.rel.toFixed(1)} m · ${st.hs.toFixed(1)} m/s`
      const x = L.X + 18, w = 150, h = 22
      let y = L.Y - 32
      for (let k = 0; k < 6; k++) { const hit = placed.find((p) => x < p.x + p.w && x + w > p.x && y < p.y + p.h && y + h > p.y); if (!hit) break; y = hit.y - h - 4 }
      this.ctx.globalAlpha = st.inside ? 1 : 0.65
      placed.push(this.pillLabel(x, y, L.f.color, L.f.label, val, L.X, L.Y))
      this.ctx.globalAlpha = 1
    }
  }
  private tagText(text: string, x: number, y: number, mono = false): void {
    const ctx = this.ctx
    ctx.font = (mono ? '500 11px ' + FONT.mono : '500 11px ' + FONT.sans)
    ctx.lineWidth = 3; ctx.strokeStyle = this.C.halo; ctx.lineJoin = 'round'; ctx.strokeText(text, x, y); ctx.fillStyle = '#e8eef0'; ctx.fillText(text, x, y)
  }
  private pillText(text: string, x: number, y: number): void {
    const ctx = this.ctx, C = this.C
    ctx.font = '500 11px ' + FONT.mono; const w = ctx.measureText(text).width + 10, h = 18
    this.rr(x - w / 2, y - h / 2, w, h, 3); ctx.fillStyle = rgba(C.panel, 0.92); ctx.fill(); ctx.strokeStyle = C.line; ctx.lineWidth = 1; ctx.stroke()
    ctx.fillStyle = C.ink2; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText(text, x, y + 0.5); ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic'
  }
}
