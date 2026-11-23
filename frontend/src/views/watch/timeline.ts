/**
 * 监视台 time strip: per-drone phase lanes (+ waypoints and commands when the route is shown) and small-multiple curves
 * (height, speed, battery, separation). Data is drawn only up to the timeline cut-off: live up to now (while reviewing,
 * the part after the cursor is veiled), a replay with the route hidden only up to the cursor. Ported from the prototype.
 */
import { t, tc } from '@/i18n'
import type { WatchEngine } from './engine'
import { FONT, readTokens, rgba } from './mapScene'
import { GROUND_MODES, MODE, PHASE_LABEL, RTH_MODES, bsearch, clamp, isNum, lerp, pairMinAt, type Pair, type WatchFlight } from './model'

interface Metric { key: 'rel' | 'hs' | 'bat' | 'sep'; name: string; unit: string; d: number; step?: boolean; pairs?: boolean; lo: number; hi: number }
type Row = { kind: 'lane'; f: WatchFlight; yMode: number; hMode: number; yMark: number; hMark: number; single: boolean } | { kind: 'chart'; m: Metric; y: number; h: number }
interface Hit { kind: string; f: WatchFlight; x0: number; x1: number; y0: number; y1: number; pri?: number; html: string }
interface Series { label: string; color: string; t: ArrayLike<number>; v: ArrayLike<number>; f?: WatchFlight; step?: boolean; pair?: Pair }

export { clockStr, hmStr, durStr, setDisplayOffset } from './clock'
import { clockStr, hmStr, durStr } from './clock'
const esc = (s: unknown) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!)
const niceCeil = (v: number) => { if (v <= 0) return 1; const e = Math.pow(10, Math.floor(Math.log10(v))); for (const m of [1, 2, 2.5, 5, 10]) if (m * e >= v) return m * e; return 10 * e }

export class Timeline {
  private ctx: CanvasRenderingContext2D
  private st = document.createElement('canvas')
  private w = 0; private h = 0; private dpr = 1
  private L = 92; private R = 16; private axisH = 24
  private rows: Row[] = []
  private hits: Hit[] = []
  private seeking = false
  hoverT: number | null = null
  private C = readTokens()
  private metrics: Metric[] = [
    { key: 'rel', name: t('高度'), unit: 'm', d: 1, lo: 0, hi: 10 },
    { key: 'hs', name: tc('short', '水平速度'), unit: 'm/s', d: 1, lo: 0, hi: 1 },
    { key: 'bat', name: t('电量'), unit: '%', d: 0, step: true, lo: 0, hi: 100 },
    { key: 'sep', name: t('两机间距'), unit: 'm', d: 1, pairs: true, lo: 0, hi: 1 },
  ]

  constructor(private engine: WatchEngine, private cv: HTMLCanvasElement, private wrap: HTMLElement, private tip: HTMLElement) {
    this.ctx = cv.getContext('2d')!
    cv.addEventListener('pointerdown', (e) => {
      if (e.offsetX < this.L - 4) return
      this.seeking = true
      cv.setPointerCapture(e.pointerId)
      this.engine.seek(this.tOf(e.offsetX))
    })
    cv.addEventListener('pointermove', (e) => { if (this.seeking) this.engine.seek(this.tOf(e.offsetX)); this.hover(e.offsetX, e.offsetY) })
    cv.addEventListener('pointerup', () => { this.seeking = false })
    cv.addEventListener('pointercancel', () => { this.seeking = false })
    cv.addEventListener('pointerleave', () => { if (!this.seeking) { this.hoverT = null; this.tip.hidden = true } })
    cv.addEventListener('wheel', (e) => {
      const S = this.engine.S
      if (S.mode !== 'replay') return
      const horiz = Math.abs(e.deltaX) > Math.abs(e.deltaY)
      if (!horiz && !e.ctrlKey && !e.altKey && e.offsetX < this.L) return
      e.preventDefault()
      const span = S.view[1] - S.view[0], full = S.domain[1] - S.domain[0]
      if (horiz || e.shiftKey) { const d = ((horiz ? e.deltaX : e.deltaY) / (this.w - this.L - this.R)) * span; this.engine.setView(S.view[0] + d, S.view[1] + d) }
      else {
        const at = this.tOf(clamp(e.offsetX, this.L, this.w - this.R)), k = Math.exp(e.deltaY * 0.0016), ns = clamp(span * k, 5000, full)
        const a = at - ((at - S.view[0]) / span) * ns
        this.engine.setView(a, a + ns)
      }
    }, { passive: false })
    cv.addEventListener('dblclick', () => { const S = this.engine.S; if (S.mode === 'replay') this.engine.setView(S.domain[0], S.domain[1]) })
  }

  applyTheme(): void { this.C = readTokens() }
  private xOf(t: number): number { const v = this.engine.S.view; return this.L + ((t - v[0]) / (v[1] - v[0])) * (this.w - this.L - this.R) }
  private tOf(x: number): number { const v = this.engine.S.view; return v[0] + ((x - this.L) / (this.w - this.L - this.R)) * (v[1] - v[0]) }

  private layout(): number {
    const S = this.engine.S
    const rows: Row[] = []
    let y = this.axisH + 6
    for (const f of S.flights) {
      if (S.hideRoute) { rows.push({ kind: 'lane', f, yMode: y, hMode: 16, yMark: 0, hMark: 0, single: true }); y += 26 }
      else { rows.push({ kind: 'lane', f, yMode: y, hMode: 16, yMark: y + 19, hMark: 14, single: false }); y += 44 }
    }
    if (S.showCharts) {
      const ms = this.metrics.filter((m) => !m.pairs || S.pairs.length)
      const stacked = window.innerWidth <= 980
      const budget = stacked ? Infinity : clamp(window.innerHeight * 0.31, 190, 440) - 44
      const gap = 12, ch = Math.round(clamp((budget - y - 6) / Math.max(1, ms.length) - gap, 24, 46))
      y += 4
      for (const m of ms) { rows.push({ kind: 'chart', m, y, h: ch }); y += ch + gap }
    }
    this.rows = rows
    return S.flights.length ? y : 0
  }

  /** Resize if needed and redraw the static layer (data). */
  drawStatic(): void {
    const w = this.wrap.clientWidth
    if (!w) return
    const h = this.layout()
    const dpr = Math.min(2, window.devicePixelRatio || 1)
    if (w !== this.w || h !== this.h || dpr !== this.dpr) {
      this.w = w; this.h = h; this.dpr = dpr
      this.cv.width = Math.round(w * dpr); this.cv.height = Math.round(h * dpr); this.cv.style.height = h + 'px'
      this.st.width = this.cv.width; this.st.height = this.cv.height
    }
    this.domains()
    const c = this.st.getContext('2d')!, S = this.engine.S, C = this.C
    c.setTransform(dpr, 0, 0, dpr, 0, 0); c.clearRect(0, 0, w, h)
    this.hits = []
    if (!S.flights.length) return
    const plotW = w - this.L - this.R, span = S.view[1] - S.view[0]
    const steps = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600].map((s) => s * 1000)
    const step = steps.find((s) => (s / span) * plotW >= 84) ?? 3600000
    const aligned = S.align === 'takeoff', base = aligned ? S.refLift : 0
    c.font = '400 10.5px ' + FONT.mono; c.textBaseline = 'middle'
    for (let t = Math.ceil((S.view[0] - base) / step) * step + base; t <= S.view[1]; t += step) {
      const x = Math.round(this.xOf(t)) + 0.5
      c.strokeStyle = rgba(C.line, 0.6); c.lineWidth = 1; c.beginPath(); c.moveTo(x, this.axisH); c.lineTo(x, h); c.stroke()
      c.strokeStyle = C.line; c.beginPath(); c.moveTo(x, this.axisH - 5); c.lineTo(x, this.axisH); c.stroke()
      const lab = aligned ? durStr(t - base, true) : step < 60000 ? clockStr(t) : hmStr(t)
      c.fillStyle = C.ink3; c.textAlign = 'center'; c.fillText(lab, clamp(x, this.L + 26, w - 30), this.axisH - 13)
    }
    c.textAlign = 'left'
    c.strokeStyle = C.line; c.beginPath(); c.moveTo(this.L, this.axisH + 0.5); c.lineTo(w - this.R, this.axisH + 0.5); c.stroke()
    for (const row of this.rows) row.kind === 'lane' ? this.lane(c, row) : this.chart(c, row)
  }

  private domains(): void {
    const S = this.engine.S, cut = this.engine.tlCutoff()
    for (const m of this.metrics) {
      let lo = Infinity, hi = -Infinity
      if (m.pairs) for (const p of S.pairs) for (let k = 0; k < p.D.length && p.T[k]! <= cut; k++) { hi = Math.max(hi, p.D[k]!); lo = Math.min(lo, p.D[k]!) }
      else for (const f of S.flights) { const a = f[m.key as 'rel' | 'hs' | 'bat']; for (let i = 0; i < f.n && f.t[i]! <= cut; i++) { const v = a[i]!; if (isNum(v)) { hi = Math.max(hi, v); lo = Math.min(lo, v) } } }
      if (!isFinite(hi)) { m.lo = 0; m.hi = m.key === 'bat' ? 100 : 10; continue }
      if (m.key === 'bat') { m.lo = Math.max(0, Math.floor((lo - 2) / 10) * 10); m.hi = Math.min(100, Math.max(m.lo + 10, Math.ceil((hi + 1) / 10) * 10)) }
      else { m.hi = Math.max(niceCeil(hi * 1.04), m.key === 'rel' ? 10 : 1); m.lo = lo < -2 ? -niceCeil(-lo) : 0 }
    }
  }
  private clip(c: CanvasRenderingContext2D, y: number, h: number): void {
    const cut = this.engine.tlCutoff()
    const xr = cut === Infinity ? this.w - this.R : clamp(this.xOf(cut), this.L, this.w - this.R)
    c.save(); c.beginPath(); c.rect(this.L, y - 1, Math.max(0, xr - this.L), h + 2); c.clip()
  }
  private rr(c: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number): void {
    c.beginPath(); c.moveTo(x + r, y); c.arcTo(x + w, y, x + w, y + h, r); c.arcTo(x + w, y + h, x, y + h, r); c.arcTo(x, y + h, x, y, r); c.arcTo(x, y, x + w, y, r); c.closePath()
  }
  private lane(c: CanvasRenderingContext2D, row: Extract<Row, { kind: 'lane' }>): void {
    const S = this.engine.S, C = this.C, f = row.f, color = f.color
    c.fillStyle = color; this.rr(c, 0, row.yMode + 3, 10, 10, 2); c.fill()
    c.font = '600 13px ' + FONT.sans; c.fillStyle = C.ink; c.textBaseline = 'middle'; c.fillText(f.label, 16, row.yMode + 8.5)
    c.font = '400 11px ' + FONT.sans; c.fillStyle = C.ink3
    const nm0 = S.hideRoute || f.kind === 'dog' ? f.devName : f.routeName, nm = nm0.length > 7 ? nm0.slice(0, 6) + '…' : nm0
    c.fillText(nm, 16 + c.measureText(f.label).width + 18, row.yMode + 8.5)
    if (!row.single) { c.font = '500 10.5px ' + FONT.sans; c.fillText(t('航点 · 指令'), 0, row.yMark + 7.5) }
    this.clip(c, row.yMode, row.single ? row.hMode : row.hMode + 19 + row.hMark)
    // a dog (D-40) has no flight modes: still / walking in both views
    const segs = S.hideRoute || f.kind === 'dog'
      ? f.phaseSegs.map((s) => ({ t0: s.t0, t1: s.t1, lab: PHASE_LABEL[s.ph], ground: ['ground', 'ready', 'nodata', 'offline', 'still'].includes(s.ph), fill: ['ground', 'ready', 'nodata', 'offline', 'still'].includes(s.ph) ? C.panel2 : s.ph === 'avoid' ? rgba(C.warn, 0.4) : s.ph === 'rth' || s.ph === 'land' ? rgba(color, 0.42) : rgba(color, 0.24) }))
      : f.modeSegs.map((s) => { const ground = !isNum(s.m) || GROUND_MODES.has(s.m); return { t0: s.t0, t1: s.t1, lab: isNum(s.m) ? MODE[s.m] ?? t('模式 {code}', { code: s.m }) : t('无数据'), ground, fill: ground ? C.panel2 : rgba(color, RTH_MODES.has(s.m) ? 0.42 : s.m === 3 ? 0.12 : 0.22) } })
    for (const s of segs) {
      const x0 = this.xOf(s.t0), x1 = this.xOf(f.live && s === segs[segs.length - 1] ? Math.max(s.t1, S.now) : s.t1)
      if (x1 < this.L || x0 > this.w - this.R) continue
      const w = Math.max(1, x1 - x0 - 2)
      c.fillStyle = s.fill; this.rr(c, x0 + 1, row.yMode, w, row.hMode, 2); c.fill()
      c.font = '500 10.5px ' + FONT.sans
      if (c.measureText(s.lab).width + 10 < w) { c.fillStyle = s.ground ? C.ink3 : C.ink; c.fillText(s.lab, x0 + 6, row.yMode + 8.5) }
      this.hits.push({ kind: 'mode', f, x0, x1, y0: row.yMode, y1: row.yMode + row.hMode, html: `${s.lab}<div class="num k">${t('{time} 起', { time: clockStr(s.t0) })}</div>` })
    }
    if (!row.single) {
      const ym = row.yMark + row.hMark / 2
      c.strokeStyle = C.line; c.lineWidth = 1; c.beginPath(); c.moveTo(this.xOf(f.t0), Math.round(ym) + 0.5); c.lineTo(this.xOf(f.t1), Math.round(ym) + 0.5); c.stroke()
      for (const hd of f.holds) {
        const x0 = this.xOf(hd.t0), w = Math.max(2, this.xOf(hd.t1) - x0)
        c.fillStyle = rgba(color, 0.25); c.fillRect(x0, row.yMark + 1, w, row.hMark - 2)
        this.hits.push({ kind: 'hold', f, x0, x1: x0 + w, y0: row.yMark, y1: row.yMark + row.hMark, html: `${hd.n ? t('悬停等待确认（航点 {n}）', { n: hd.n }) : t('悬停等待确认')}<div class="num k">${clockStr(hd.t0)} – ${clockStr(hd.t1)}</div>` })
      }
      for (const a of f.alerts) {
        const x0 = this.xOf(a.t0), x1 = Math.max(x0 + 2, this.xOf(a.t1))
        c.fillStyle = rgba(C.warn, 0.7); c.fillRect(x0, ym - 1.5, x1 - x0, 3)
        c.beginPath(); c.moveTo(x0, row.yMark + 1); c.lineTo(x0 + 6, row.yMark + 10.6); c.lineTo(x0 - 6, row.yMark + 10.6); c.closePath(); c.fillStyle = C.warn; c.fill()
        this.hits.push({ kind: 'alert', f, x0: x0 - 6, x1: x1 + 6, y0: row.yMark - 2, y1: row.yMark + row.hMark + 2, html: `${esc(a.msg)}<div class="num k">${clockStr(a.t0, true)}</div>` })
      }
      c.font = '500 9.5px ' + FONT.mono
      for (const wp of f.wps) {
        const x = Math.round(this.xOf(wp.t)) + 0.5
        c.strokeStyle = color; c.lineWidth = 1.5; c.beginPath(); c.moveTo(x, row.yMark + 1); c.lineTo(x, row.yMark + row.hMark - 1); c.stroke()
        c.fillStyle = C.ink2; c.fillText(String(wp.n), x + 3, row.yMark + 4.5)
        this.hits.push({ kind: 'wp', f, x0: x - 4, x1: x + 4, y0: row.yMark, y1: row.yMark + row.hMark, html: `${t('到达航点 {n}', { n: wp.n })}<div class="num k">${clockStr(wp.t, true)}</div>` })
      }
      for (const cm of f.cmds) {
        const x = this.xOf(cm.t)
        c.beginPath(); c.moveTo(x, ym - 4.5); c.lineTo(x + 4.5, ym); c.lineTo(x, ym + 4.5); c.lineTo(x - 4.5, ym); c.closePath()
        c.lineWidth = 2; c.strokeStyle = C.panel; c.stroke(); c.fillStyle = cm.bad ? '#d03b3b' : C.ink2; c.fill()
        this.hits.push({ kind: 'cmd', f, x0: x - 6, x1: x + 6, y0: ym - 7, y1: ym + 7, pri: 2, html: `${esc(cm.label)}<div class="num k">${clockStr(cm.t, true)} · ${esc(cm.msg)}</div>` })
      }
    }
    c.restore()
  }
  private series(m: Metric): Series[] {
    const S = this.engine.S
    if (m.pairs) return S.pairs.map((p) => ({ label: p.label, color: this.C.ink2, t: p.T, v: p.D, pair: p }))
    return S.flights.map((f) => ({ label: f.label, color: f.color, t: f.t, v: f[m.key as 'rel' | 'hs' | 'bat'], f, step: m.step }))
  }
  private yOf(m: Metric, row: { y: number; h: number }, v: number): number { return row.y + row.h - ((v - m.lo) / (m.hi - m.lo)) * row.h }
  private chart(c: CanvasRenderingContext2D, row: Extract<Row, { kind: 'chart' }>): void {
    const m = row.m, C = this.C, S = this.engine.S
    c.font = '600 11.5px ' + FONT.sans; c.fillStyle = C.ink2; c.textBaseline = 'middle'; c.fillText(m.name, 0, row.y + 4)
    c.font = '400 10.5px ' + FONT.mono; c.fillStyle = C.ink3; c.fillText(m.unit, 0, row.y + 18)
    c.textAlign = 'right'
    for (const v of [m.lo, (m.lo + m.hi) / 2, m.hi]) {
      const y = Math.round(this.yOf(m, row, v)) + 0.5
      c.strokeStyle = v === m.lo ? C.line : rgba(C.line, 0.55); c.lineWidth = 1; c.beginPath(); c.moveTo(this.L, y); c.lineTo(this.w - this.R, y); c.stroke()
      c.fillStyle = C.ink3; c.fillText(String(Math.round(v * 10) / 10), this.L - 7, y)
    }
    c.textAlign = 'left'
    this.clip(c, row.y, row.h)
    for (const s of this.series(m)) {
      const i0 = Math.max(0, bsearch(s.t, S.view[0]) - 1), i1 = Math.min(s.t.length - 1, bsearch(s.t, S.view[1]) + 1)
      c.strokeStyle = s.color; c.lineWidth = s.pair ? 1.5 : 2; c.lineJoin = 'round'; c.lineCap = 'round'; c.beginPath()
      let pen = false, py = 0
      for (let i = i0; i <= i1; i++) {
        const v = s.v[i]!
        if (!isNum(v)) { pen = false; continue }
        const x = this.xOf(s.t[i]!), y = this.yOf(m, row, v)
        if (pen && s.t[i]! - s.t[i - 1]! > 12000) pen = false
        if (!pen) { c.moveTo(x, y); pen = true } else if (s.step) { c.lineTo(x, py); c.lineTo(x, y) } else c.lineTo(x, y)
        py = y
      }
      c.stroke()
      if (s.pair) {
        const mn = pairMinAt(s.pair, this.engine.tlCutoff())
        if (mn) {
          const x = this.xOf(mn.t), y = this.yOf(m, row, mn.d)
          c.fillStyle = C.ink; c.beginPath(); c.arc(x, y, 3.5, 0, 7); c.fill(); c.lineWidth = 2; c.strokeStyle = C.panel; c.stroke()
          const lab = t('空中最近 {d} m', { d: mn.d.toFixed(1) })
          c.font = '500 10.5px ' + FONT.sans
          const tw = c.measureText(lab).width, lx = x + tw + 12 > this.w - this.R ? x - tw - 8 : x + 8
          c.lineWidth = 3; c.strokeStyle = C.panel; c.strokeText(lab, lx, y - 8); c.fillStyle = C.ink2; c.fillText(lab, lx, y - 8)
        }
      }
    }
    c.restore()
  }
  private valueAt(s: Series, T: number): number | null {
    if (T > this.engine.tlCutoff()) return null
    const i = bsearch(s.t, T)
    if (i < 0 || (i === s.t.length - 1 && T > s.t[i]!)) return null
    const j = Math.min(i + 1, s.t.length - 1), a = j > i && !s.step ? (T - s.t[i]!) / (s.t[j]! - s.t[i]!) : 0
    const v = isNum(s.v[i]) && isNum(s.v[j]) ? lerp(s.v[i]!, s.v[j]!, a) : s.v[i]!
    return isNum(v) ? v : null
  }

  /** Dynamic layer: cursor, live edge, hover line, value dots. */
  draw(): void {
    const c = this.ctx, S = this.engine.S, C = this.C
    c.setTransform(1, 0, 0, 1, 0, 0); c.clearRect(0, 0, this.cv.width, this.cv.height)
    if (!S.flights.length) return
    c.drawImage(this.st, 0, 0)
    c.setTransform(this.dpr, 0, 0, this.dpr, 0, 0)
    const liveRed = getComputedStyle(document.documentElement).getPropertyValue('--danger').trim() || '#ef4444'
    if (this.hoverT != null && this.hoverT >= S.view[0] && this.hoverT <= S.view[1]) {
      const x = Math.round(this.xOf(this.hoverT)) + 0.5
      c.strokeStyle = C.ink3; c.lineWidth = 1; c.beginPath(); c.moveTo(x, this.axisH); c.lineTo(x, this.h); c.stroke()
    }
    if (S.mode === 'live' && S.reviewing) {
      // reviewing: veil from the cursor to now, dashed red line at now
      const xa = this.xOf(S.t), xn = Math.round(this.xOf(S.now)) + 0.5
      c.fillStyle = rgba(C.panel, 0.55); c.fillRect(xa, this.axisH, Math.max(0, xn - xa), this.h - this.axisH)
      c.strokeStyle = liveRed; c.lineWidth = 1; c.setLineDash([3, 3]); c.beginPath(); c.moveTo(xn, this.axisH - 2); c.lineTo(xn, this.h); c.stroke(); c.setLineDash([])
    }
    if (S.t >= S.view[0] && S.t <= S.view[1]) {
      const x = Math.round(this.xOf(S.t)) + 0.5, atLive = S.mode === 'live' && !S.reviewing
      c.strokeStyle = atLive ? liveRed : C.ink; c.lineWidth = 1; c.beginPath(); c.moveTo(x, this.axisH - 2); c.lineTo(x, this.h); c.stroke()
      c.fillStyle = c.strokeStyle; c.beginPath(); c.moveTo(x - 5, this.axisH - 8); c.lineTo(x + 5, this.axisH - 8); c.lineTo(x, this.axisH - 1); c.closePath(); c.fill()
      for (const row of this.rows) {
        if (row.kind !== 'chart') continue
        for (const s of this.series(row.m)) {
          const v = this.valueAt(s, S.t)
          if (v == null) continue
          const y = clamp(this.yOf(row.m, row, v), row.y, row.y + row.h)
          c.beginPath(); c.arc(x, y, 3.5, 0, 7); c.fillStyle = s.color; c.fill(); c.lineWidth = 2; c.strokeStyle = C.panel; c.stroke()
        }
      }
    }
  }

  private hover(x: number, y: number): void {
    const tip = this.tip, S = this.engine.S
    if (x < this.L || !S.flights.length) { this.hoverT = null; tip.hidden = true; return }
    this.hoverT = this.tOf(x)
    const cut = this.engine.tlCutoff()
    let html = ''
    const h = this.hits.filter((k) => x >= k.x0 && x <= k.x1 && y >= k.y0 && y <= k.y1 && this.hoverT! <= cut).sort((a, b) => (b.pri ?? 0) - (a.pri ?? 0))[0]
    if (h) html = `<div class="r"><span class="sw" style="background:${esc(h.f.color)}"></span><b>${esc(h.f.label)}</b> ${h.html}</div>`
    else {
      const row = this.rows.find((r): r is Extract<Row, { kind: 'chart' }> => r.kind === 'chart' && y >= r.y - 6 && y <= r.y + r.h + 6)
      if (row && this.hoverT <= cut) {
        const lines = this.series(row.m).map((s) => { const v = this.valueAt(s, this.hoverT!); return `<div class="r">${s.f ? `<span class="sw" style="background:${esc(s.color)}"></span>` : ''}<span>${esc(s.label)}</span>&nbsp;<b class="num">${v == null ? '–' : v.toFixed(row.m.d)}</b>&nbsp;<span class="k">${row.m.unit}</span></div>` }).join('')
        html = `<div class="k">${row.m.name} · <span class="num">${clockStr(this.hoverT, true)}</span></div>${lines}`
      }
    }
    if (!html) { tip.hidden = true; return }
    tip.innerHTML = html
    tip.hidden = false
    const W = this.wrap.clientWidth, H = this.wrap.clientHeight, tw = tip.offsetWidth, th = tip.offsetHeight
    let lx = x + 14, ly = y + 14
    if (lx + tw > W - 6) lx = x - tw - 14
    if (ly + th > H - 6) ly = y - th - 12
    tip.style.left = Math.max(6, lx) + 'px'; tip.style.top = Math.max(6, ly) + 'px'
  }
}
