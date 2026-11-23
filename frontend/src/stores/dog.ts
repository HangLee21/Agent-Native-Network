/**
 * Robot dogs (S10, Lite3) on the live-monitoring page (docs/dog/ui-design.md). Holds the latest state pushed by the
 * backend (dog-state), the command log (dog-command), which dog is being operated, and the browser side of
 * hold-to-move / arm jogging / Lite3 control: heartbeats are sent only while a key or button is held (or, for
 * Lite3, while this page holds control). Stopping the dog and giving up Lite3 control are separate (user decision
 * 2026-11-07): switching to another program or device, or the browser going to the background, stops the dog but
 * keeps Lite3 control (an all-zero drive about every 0.8 s keeps the 3 s idle lease, from a worker timer so a
 * background tab keeps its pace); leaving the live page, closing it or losing the link releases it. Control is never
 * taken back automatically. The backend only relays these heartbeats; it never makes its own.
 * <p>
 * Order of hold requests: a new hold (S10 move or arm jog) starts only after the previous one's end has been
 * answered — the backend refuses a second hold while the first is open, so a quick change of direction would
 * otherwise stop the dog with an error.
 */
import { defineStore } from 'pinia'
import { computed, reactive, ref, watch } from 'vue'
import { beacon, dogApi, type DogCommand, type DogId, type DogState, type Lite3State, type S10State } from '@/api/dog'
import { telemetrySocket, type WsMessage } from '@/services/ws'
import { ApiError } from '@/api/http'
import { isEn, t, tb } from '@/i18n'
import { useDog2Store } from '@/stores/dogv2'
import type { Dog2, Dog2NavPoint } from '@/api/dogv2'

export const DOG_IDS: DogId[] = ['s10', 'lite3']
export const DOG_NAME: Record<DogId, string> = { s10: 'S10', lite3: 'Lite3' }
export const DOG_COLOR: Record<DogId, string> = { s10: 'var(--dog-s10, #b794f6)', lite3: 'var(--dog-lite3, #4fd1c5)' }

/** S10 chassis posture names from /api/work, worded like the dog side's page. */
export const S10_POSTURE: Record<string, string> = {
  idle: t('空闲 / 低位'), rl_control: t('RL 控制'), damping: t('阻尼'),
  sitting: isEn() ? 'Lying down' : '趴下', // i18n-ignore: as a state; the button of the same Chinese name is "Lie down"
  standing: isEn() ? 'Standing' : '站立', // i18n-ignore: as a state; the button of the same Chinese name is "Stand up"
}
/** 站立 as a state or a precondition (the same Chinese word on a button is an action, "Stand up"). */
export const STANDING = S10_POSTURE.standing!

export type Lite3Pose = 'lying' | 'standing' | 'transition' | 'protect' | 'unknown'
/**
 * Lite3 state names come from the SDK and are not confirmed (interface doc U08); the official state table has lying,
 * preparing / standing up, force control (standing or walking), lying down, out-of-control protection, posture
 * adjust, AI, zeroing. Unknown names are shown as they are and treated as unknown.
 */
export function lite3Pose(name: string | undefined | null): Lite3Pose {
  const s = (name ?? '').toLowerCase()
  if (!s) return 'unknown'
  // English mode: the dog's Chinese state names arrive translated (docs/i18n.md)
  const en = isEn()
  // "Lying down" is the English of the state 趴下; the move itself (正在趴下) is "Getting down"
  if (en && s === 'lying down') return 'lying'
  if (/失控|protect|fall|摔/.test(s)) return 'protect'   // i18n-ignore: matches the dog's state names, not interface text
  if (/正在|准备|prepar|standing ?up|lying ?down|getting|回零|zero|初始化/.test(s) || (en && /initiali/.test(s))) return 'transition'   // i18n-ignore: matches the dog's state names, not interface text
  if (/趴|lie|lying|sit|prone|crouch/.test(s)) return 'lying'   // i18n-ignore: matches the dog's state names, not interface text
  if (/站|stand|force|力控|move|walk|姿态调整/.test(s) || (en && /posture/.test(s))) return 'standing'   // i18n-ignore: matches the dog's state names, not interface text
  return 'unknown'
}

/**
 * Navigation states are the dog's own (U03); these words count as "navigating" — what the platform greys out while
 * navigating is the platform's own rule, the dog itself does not refuse (ui-design.md 9.3).
 */
export function navActive(nav: Record<string, unknown> | null | undefined): boolean {
  const st = String(nav?.state ?? '').toUpperCase()
  return /RUN|ACTIVE|EXECUT|NAVIGAT|FOLLOW/.test(st)
}

interface S10HoldLocal {
  session?: string
  dir: string
  label: string
  starting: boolean
  beats: number
  ignored: number
  inflight: number
  timer?: number
  /** Called once when this hold is fully over (end answered, or it never started). */
  finish: () => void
}
interface ArmHoldLocal {
  session?: string
  key: string
  starting: boolean
  timer?: number
  inflight: boolean
  finish: () => void
}

/** A promise and its resolver. */
function deferred(): { p: Promise<void>; done: () => void } {
  let done!: () => void
  const p = new Promise<void>((r) => (done = r))
  return { p, done }
}

/** States of a command that are still waiting for the dog. */
const OPEN_STATES = new Set(['sent', 'running'])
/** The backend pushes each dog's state every 0.7–1 s; older than this, the browser has lost the backend. */
const PUSH_STALE_MS = 3500

export interface DogNote {
  cls: 'ok' | 'warn' | 'bad' | 'info'
  text: string
  at: number
}

export const useDogStore = defineStore('dog', () => {
  const dogs = reactive<Partial<Record<DogId, DogState>>>({})
  /** Client time when each dog's state arrived. */
  const receivedAt = reactive<Partial<Record<DogId, number>>>({})
  const commands = reactive<Record<DogId, DogCommand[]>>({ s10: [], lite3: [] })
  /** server clock minus browser clock, ms */
  const serverOffsetMs = ref(0)
  const mode = ref<string>('off')
  const selected = ref<DogId | null>(null)
  /** Last moment each dog was seen doing something that makes a lost link serious (hold, job, navigation, control). */
  const activeAt = reactive<Partial<Record<DogId, number>>>({})
  const notes = reactive<Partial<Record<DogId, DogNote>>>({})
  /** What this platform knows about Lite3 that the dog does not report (moving mode, gait, own e-stop, lying down by itself). */
  const l3Marks = reactive({ pose: 'unknown' as Lite3Pose, moving: false, low: false, standAt: 0, estopAt: 0, selfSit: false })
  const tick = ref(Date.now())
  /** Counts stops and soft e-stops sent from this page: a multi-step sequence aborts if it changed meanwhile. */
  const stopSeq = ref(0)
  let started = false

  const ids = computed(() => DOG_IDS.filter((id) => !!dogs[id]))
  const present = computed(() => ids.value.length > 0)
  const s10 = computed(() => dogs.s10 as S10State | undefined)
  const lite3 = computed(() => dogs.lite3 as Lite3State | undefined)

  function serverNow(): number {
    return Date.now() + serverOffsetMs.value
  }

  /** Monotonic event times per data key: an older timestamp never makes an age jump back (11-04 lesson). */
  const eventAt = new Map<string, number>()
  /** Seconds since the data `key` was produced, given its age `baseAge` (s) reported at server time `atServerMs`. */
  function age(key: string, baseAge: number | null | undefined, atServerMs: number | null | undefined): number | null {
    void tick.value
    if (baseAge == null || atServerMs == null) return null
    const ev = atServerMs - baseAge * 1000
    const prev = eventAt.get(key)
    const use = prev != null && prev > ev ? prev : ev
    if (prev == null || ev > prev) eventAt.set(key, ev)
    return Math.max(0, (serverNow() - use) / 1000)
  }

  /** No push from the backend for a while: whatever the last state said, this page no longer sees the dog. */
  function pushStale(id: DogId): boolean {
    void tick.value
    const r = receivedAt[id]
    return r == null || Date.now() - r > PUSH_STALE_MS
  }

  function online(id: DogId): boolean {
    if (pushStale(id)) return false
    const st = dogs[id]?.link.state
    return st === 'online' || st === 'reconnecting'
  }

  /**
   * The last state said the dog was connected, but this page has heard nothing since: the page or its network, not
   * a known loss of the dog (field test 2026-11-10: the page showed "Lite3 lost" for ~10 s while the dog, the backend
   * and the hold beats were fine). Controls stay off as when offline; the wording says what is known.
   */
  function pageStale(id: DogId): boolean {
    const st = dogs[id]?.link.state
    return pushStale(id) && (st === 'online' || st === 'reconnecting')
  }

  /** Whole seconds since this page last heard about the dog. */
  function staleSecs(id: DogId): number {
    void tick.value
    const r = receivedAt[id]
    return r == null ? 0 : Math.floor((Date.now() - r) / 1000)
  }

  /** Offline but was active within the last minute before the link went: the "serious" loss (ui-design.md 4.5). */
  function lost(id: DogId): boolean {
    const d = dogs[id]
    if (!d || online(id) || pageStale(id)) return false
    const last = d.link.lastOkAt ?? 0
    const act = activeAt[id] ?? 0
    return act > 0 && last - act < 15000 && act >= last - 60000
  }

  function important(id: DogId): boolean {
    return online(id) || lost(id) || pageStale(id)
  }

  function onState(d: DogState, fromNewSystem = false): void {
    // since 2026-11-10 the Lite3 comes from the new dog system only (syncLite3 below); the old path's pushes are ignored
    if (d.dogId === 'lite3' && !fromNewSystem) return
    dogs[d.dogId] = d
    receivedAt[d.dogId] = Date.now()
    if (d.dogId === 's10') {
      const s = d as S10State
      if (s.holdActive || s.armHoldActive || s.jobs.some((j) => j.state === 'running') || navActive(s.nav)) activeAt.s10 = s.link.lastOkAt ?? Date.now()
    } else {
      const l = d as Lite3State
      if (l.robot.controller === 'platform') activeAt.lite3 = l.link.lastOkAt ?? Date.now()
      const pose = lite3Pose(l.robot.robot_state)
      const prev = l3Marks.pose
      if (prev !== pose) {
        // after every stand / lie the dog returns to its initial standing state: moving mode and gait must be sent again
        if (prev !== 'unknown') {
          l3Marks.moving = false
          l3Marks.low = false
        }
        const ownStand = Date.now() - l3Marks.standAt < 8000
        if (prev === 'standing' && pose === 'lying' && !ownStand && Date.now() - l3Marks.estopAt > 8000) l3Marks.selfSit = true
        if (pose === 'standing') {
          l3Marks.selfSit = false
          l3Marks.estopAt = 0
        }
        l3Marks.pose = pose
      }
      if (l.robot.controller === 'other') {
        l3Marks.moving = false
        l3Marks.low = false
      }
    }
  }

  /**
   * A command's newest state wins: a REST reply that arrives late (it carries the state at the moment it was sent)
   * never turns a finished command back into "running" after the WebSocket already reported the end.
   */
  function onCommand(c: DogCommand): void {
    const list = commands[c.dogId]
    if (!list) return
    const i = list.findIndex((x) => x.id === c.id)
    const old = i >= 0 ? list[i] : undefined
    if (old) {
      if (!OPEN_STATES.has(old.state) && OPEN_STATES.has(c.state)) return
      list.splice(i, 1, c)
    } else list.unshift(c)
    if (list.length > 50) list.length = 50
  }

  /**
   * Browser-to-server clock offset for hold-to-move timing. The board refuses a heartbeat sent more than 0.6 s ago,
   * so the estimate must be well inside that: only quick round trips are used (the error is at most half the round
   * trip), and the quickest of the last minute wins over a newer but slower one.
   */
  const timeSamples: { rtt: number; offset: number; at: number }[] = []
  async function syncTime(): Promise<void> {
    try {
      const t0 = Date.now()
      const r = await dogApi.time()
      const t1 = Date.now()
      mode.value = r.mode
      timeSamples.push({ rtt: t1 - t0, offset: r.serverMs - (t0 + t1) / 2, at: t1 })
      while (timeSamples.length > 20 || (timeSamples[0] && t1 - timeSamples[0].at > 60000)) timeSamples.shift()
      const quick = timeSamples.filter((s) => s.rtt <= 300)
      const pool = quick.length > 0 ? quick : timeSamples.filter((s) => s.rtt < 1500)
      if (pool.length > 0) serverOffsetMs.value = pool.reduce((a, b) => (b.rtt < a.rtt ? b : a)).offset
    } catch {
      /* backend down: keep the last offset */
    }
  }

  async function load(): Promise<void> {
    try {
      const list = await dogApi.list()
      list.forEach((d) => onState(d))
      for (const d of list) {
        if (d.dogId === 'lite3') continue
        const cmds = await dogApi.commands(d.dogId)
        commands[d.dogId].splice(0, commands[d.dogId].length, ...cmds)
      }
    } catch {
      /* feature off or backend down */
    }
  }

  function start(): void {
    if (started) return
    started = true
    void syncTime()
    void load()
    v2.start()
    telemetrySocket.on('dog-state', (m: WsMessage) => onState(m.data as DogState))
    telemetrySocket.on('dog-command', (m: WsMessage) => onCommand(m.data as DogCommand))
    telemetrySocket.onStatus((c) => c && void load())
    window.setInterval(() => void syncTime(), 5000)
    window.setInterval(() => (tick.value = Date.now()), 250)
    window.addEventListener('blur', () => stopMotion('切到别的程序'))   // i18n-ignore: sent to the backend, shown via tb()
    document.addEventListener('visibilitychange', () => {
      if (document.hidden) stopMotion('浏览器切到后台')   // i18n-ignore: sent to the backend, shown via tb()
    })
    window.addEventListener('pagehide', () => {
      const reason = '离开页面'   // i18n-ignore: sent to the backend, shown via tb()
      if (s10Hold.value?.session) beacon('/api/v1/dogs/s10/hold', { op: 'end', session: s10Hold.value.session, reason })
      if (armHold.value?.session) beacon('/api/v1/dogs/s10/arm-hold', { op: 'end', session: armHold.value.session, reason })
      if (l3.session) v2.leave(reason)
    })
  }

  function note(id: DogId, cls: DogNote['cls'], text: string): void {
    notes[id] = { cls, text, at: Date.now() }
  }

  /** Stops the dogs this browser is moving (S10 hold and arm jog end, Lite3 directions back to zero); Lite3 control stays. */
  function stopMotion(reason: string): void {
    if (s10Hold.value) void s10HoldEnd(reason)
    if (armHold.value) void armHoldEnd(reason)
    if (l3.axes.some((a) => a !== 0)) l3SetAxes([0, 0, 0])
  }

  /** Stops everything and releases Lite3 control: leaving the live page. */
  function stopAllLocal(reason: string): void {
    stopMotion(reason)
    if (l3.session) void l3Release(reason)
  }

  /** Switching device stops what this browser was moving; Lite3 control is kept. */
  function select(id: DogId | null): void {
    if (selected.value === id) return
    stopMotion('切换设备')   // i18n-ignore: sent to the backend, shown via tb()
    selected.value = id
  }

  // ---------------------------------------------------------------- S10 actions

  async function s10Action(body: Record<string, unknown>): Promise<DogCommand | null> {
    try {
      const c = await dogApi.s10Action(body)
      onCommand(c)
      return c
    } catch (e) {
      note('s10', 'bad', e instanceof ApiError ? e.message : t('发送失败'))
      return null
    }
  }

  // ---------------------------------------------------------------- S10 hold-to-move

  const s10Hold = ref<S10HoldLocal | null>(null)
  /** Resolves when the last hold (S10 move or arm jog) is fully over: the next one starts after it. */
  let motionIdle: Promise<void> = Promise.resolve()

  /** Takes the next place in line; resolves when the previous hold is over (at most 1.6 s: its end has a 1.5 s wait). */
  function queueHold(): { previous: Promise<void>; finish: () => void } {
    const prev = motionIdle
    const d = deferred()
    motionIdle = d.p
    let done = false
    const finish = (): void => {
      if (!done) {
        done = true
        d.done()
      }
    }
    return { previous: Promise.race([prev, new Promise<void>((r) => window.setTimeout(r, 1600))]), finish }
  }

  async function s10HoldStart(dir: string, x: number, y: number, yaw: number, label: string): Promise<void> {
    if (s10Hold.value || armHold.value) return
    const q = queueHold()
    const h = reactive<S10HoldLocal>({ dir, label, starting: true, beats: 0, ignored: 0, inflight: 0, finish: q.finish })
    s10Hold.value = h
    await q.previous
    if (s10Hold.value !== h) {
      h.finish()   // released before it could start
      return
    }
    try {
      const r = await dogApi.s10Hold({ op: 'start', x, y, yaw, sentAt: Math.round(serverNow()), label })
      if (s10Hold.value !== h) {
        // released while the start was on its way: end it right away, then let the next hold go
        if (r.session) await endS10Session(r.session, '松手')   // i18n-ignore: sent to the backend, shown via tb()
        h.finish()
        return
      }
      h.session = r.session
      h.starting = false
      void s10Beat(h)
      h.timer = window.setInterval(() => void s10Beat(h), 100)
    } catch (e) {
      if (s10Hold.value === h) s10Hold.value = null
      h.finish()
      note('s10', 'bad', t('没有开始移动：{why}', { why: e instanceof ApiError ? e.message : t('发送失败') }))
    }
  }

  /** Ends a hold session; when the page is going to the background or closing, with a request that survives it. */
  async function endS10Session(session: string, reason: string): Promise<{ confirmed?: boolean; detail?: string } | null> {
    if (document.hidden) {
      beacon('/api/v1/dogs/s10/hold', { op: 'end', session, reason })
      return null
    }
    return dogApi.s10Hold({ op: 'end', session, reason })
  }

  async function s10Beat(h: S10HoldLocal): Promise<void> {
    if (s10Hold.value !== h || !h.session || h.inflight >= 2) return
    h.inflight++
    try {
      const r = await dogApi.s10Hold({ op: 'beat', session: h.session, sentAt: Math.round(serverNow()) })
      if (r.closed) {
        if (s10Hold.value === h) {
          window.clearInterval(h.timer)
          s10Hold.value = null
          h.finish()
          note('s10', 'bad', r.detail ?? t('已停止'))
        }
      } else if (!r.skipped) {
        h.beats++
        if (r.ignored) h.ignored++
      }
    } catch {
      if (s10Hold.value === h) void s10HoldEnd('心跳发送失败')   // i18n-ignore: sent to the backend, shown via tb()
    } finally {
      h.inflight--
    }
  }

  async function s10HoldEnd(reason = '松手'): Promise<void> {   // i18n-ignore: sent to the backend, shown via tb()
    const h = s10Hold.value
    if (!h) return
    s10Hold.value = null
    window.clearInterval(h.timer)
    if (!h.session) return   // the start is still on its way: its reply ends it (s10HoldStart)
    try {
      const r = await endS10Session(h.session, reason)
      if (r) note('s10', r.confirmed ? 'ok' : 'warn', r.confirmed ? t('{reason}：狗已停', { reason: tb(reason) }) : (r.detail ?? t('未确认停止：约 0.55 秒后应自动停，请看画面')))
    } catch {
      note('s10', 'warn', t('未确认停止：约 0.55 秒后应自动停，请看画面'))
    } finally {
      h.finish()
    }
  }

  // ---------------------------------------------------------------- S10 arm jog

  const armHold = ref<ArmHoldLocal | null>(null)

  async function armHoldStart(key: string, motion: Record<string, unknown>, manualSpeed: number, label: string): Promise<void> {
    if (armHold.value || s10Hold.value) return
    const q = queueHold()
    const a = reactive<ArmHoldLocal>({ key, starting: true, inflight: false, finish: q.finish })
    armHold.value = a
    await q.previous
    if (armHold.value !== a) {
      a.finish()
      return
    }
    try {
      const r = await dogApi.s10ArmHold({ op: 'start', motion, manualSpeed, label })
      if (armHold.value !== a) {
        if (r.session) await endArmSession(r.session, '松手')   // i18n-ignore: sent to the backend, shown via tb()
        a.finish()
        return
      }
      a.session = r.session
      a.starting = false
      const beat = async (): Promise<void> => {
        if (armHold.value !== a || a.inflight) return
        a.inflight = true
        try {
          const b = await dogApi.s10ArmHold({ op: 'beat', session: a.session })
          if (b.closed && armHold.value === a) {
            window.clearInterval(a.timer)
            armHold.value = null
            a.finish()
            // the backend's text: "这次点动已结束" when the jog was over anyway (arrives translated in English mode)
            const over = !!b.detail && (b.detail.includes('结束') || b.detail === tb('这次点动已结束'))   // i18n-ignore: matches backend text
            note('s10', over ? 'ok' : 'warn', b.detail ?? t('点动已结束'))
          }
        } catch {
          if (armHold.value === a) void armHoldEnd('心跳发送失败')   // i18n-ignore: sent to the backend, shown via tb()
        } finally {
          a.inflight = false
        }
      }
      void beat()   // the arm lease is 0.6 s: the first beat goes at once, as the dog side's quick page does
      a.timer = window.setInterval(() => void beat(), 100)
    } catch (e) {
      if (armHold.value === a) armHold.value = null
      a.finish()
      note('s10', 'bad', t('点动没有开始：{why}', { why: e instanceof ApiError ? e.message : t('发送失败') }))
    }
  }

  async function endArmSession(session: string, reason: string): Promise<{ confirmed?: boolean; detail?: string } | null> {
    if (document.hidden) {
      beacon('/api/v1/dogs/s10/arm-hold', { op: 'end', session, reason })
      return null
    }
    return dogApi.s10ArmHold({ op: 'end', session, reason })
  }

  async function armHoldEnd(reason = '松手'): Promise<void> {   // i18n-ignore: sent to the backend, shown via tb()
    const a = armHold.value
    if (!a) return
    armHold.value = null
    window.clearInterval(a.timer)
    if (!a.session) return   // the start is still on its way: its reply ends it
    try {
      const r = await endArmSession(a.session, reason)
      if (r && !r.confirmed) note('s10', 'warn', r.detail ?? t('未确认停止：约 0.6 秒后应自动停，请看画面'))
    } catch {
      note('s10', 'warn', t('未确认停止：约 0.6 秒后应自动停，请看画面'))
    } finally {
      a.finish()
    }
  }

  // ---------------------------------------------------------------- Lite3 on the new dog system (2026-11-10)
  // The user switched the Lite3 fully to the new dog system: its state comes from /api/v2/dogs (the first dog of model
  // lite3) and is shaped like the old Lite3State so the live page's cards, chips and safety bar keep working; control,
  // hold-to-move, stand / lie, stop and soft e-stop go through the new system's store (non-waiting beats). The old
  // frontend code is kept in legacy/frontend-lite3-old-ui-2026-11-10/.
  const v2 = useDog2Store()
  const l3v2 = computed<Dog2 | null>(() => v2.dogs.find((d) => d.model === 'lite3') ?? null)

  function syncLite3(d: Dog2 | null): void {
    if (!d) {
      delete dogs.lite3
      return
    }
    const st = d.status
    const tel = d.mode === 'new' && (d.telemetryAgeMs ?? Infinity) < 3000 ? d.telemetry : null
    const oc = st?.old_console ?? null
    const now = serverNow()
    const mine = !!v2.hold.session && v2.hold.dog === d.id
    const l: Lite3State = {
      dogId: 'lite3', kind: 'lite3', name: 'Lite3',
      link: { state: d.online ? 'online' : d.lastSeenAt ? 'offline' : 'never', lastOkAt: d.online ? now : d.lastSeenAt, rttMs: null,
              error: d.online ? null : t('新系统离线') },
      serverTime: now, statusAt: now, standAt: null,
      robot: {
        connected: tel != null,
        feedback_available: tel != null,
        armed: d.control.held,
        controller: mine ? 'platform' : d.control.held ? 'other' : null,
        controlSession: d.control.session,
        feedback_age: tel ? tel.feedback_age_s : null,
        battery: tel?.battery_pct ?? oc?.battery_pct ?? null,
        robot_state: tel ? (tel.basic_state_name ?? String(tel.basic_state)) : (oc?.robot_state ?? undefined),
        error: d.mode === 'new' ? '' : d.mode === 'old'
          ? (oc?.reachable === false ? t('老系统已停用，新系统正在接管运动主机…') : t('板卡现在是老系统在控：到「新狗系统」页切到新系统'))
          : d.mode ? t('正在切换新老系统') : '',
      },
    }
    onState(l, true)
  }
  watch(() => [l3v2.value, v2.hold.session] as const, () => syncLite3(l3v2.value), { deep: true })

  const l3 = reactive<{ session: string | null; arming: boolean; axes: [number, number, number]; endedReason: string | null }>(
    { session: null, arming: false, axes: [0, 0, 0], endedReason: null })
  const l3Moving = computed(() => l3.axes.some((a) => a !== 0))

  // control as the new system's store holds it; a loss it noticed (dog side, lease) is shown like before
  watch(() => [v2.hold.dog, v2.hold.session] as const, ([dog, session]) => {
    const mine = session && dog === l3v2.value?.id ? session : null
    if (l3.session && !mine && v2.hold.lostReason) {
      l3.endedReason = t('控制权已失去：{detail}', { detail: v2.hold.lostReason })
      note('lite3', 'warn', l3.endedReason)
    }
    l3.session = mine
    if (!mine) l3.axes = [0, 0, 0]
  })

  function lastV2Note(id: string): string {
    return v2.notes.find((n) => n.dog === id)?.text ?? t('发送失败')
  }

  async function l3Arm(): Promise<void> {
    const id = l3v2.value?.id
    if (!id || l3.session || l3.arming) return
    l3.arming = true
    l3.endedReason = null
    try {
      await v2.take(id)
      if (v2.hold.dog !== id || !v2.hold.session) note('lite3', 'bad', lastV2Note(id))
    } finally {
      l3.arming = false
    }
  }

  function l3SetAxes(a: [number, number, number]): void {
    l3.axes = a
    if (l3.session) v2.setAxes(a)
  }

  async function l3Release(reason: string): Promise<void> {
    if (!l3.session) return
    l3.session = null
    l3.axes = [0, 0, 0]
    l3.endedReason = t('因{reason}已释放控制', { reason: tb(reason) })
    await v2.release(reason)
  }

  /** True within 3 s of a stand / lie toggle sent from this page. */
  function l3StandCooling(): boolean {
    void tick.value
    return Date.now() - l3Marks.standAt < 3000
  }

  const L3_ACTION = { stand: 'stand_toggle', moving: 'moving_mode', low: 'low_gait' } as const
  async function l3Mode(op: 'low' | 'moving' | 'stand', label: string): Promise<DogCommand | null> {
    const id = l3v2.value?.id
    if (!id || !l3.session) return null
    if (op === 'stand') {
      // a toggle: a second press would undo the first (double click, or the next-step bar and the button)
      if (l3StandCooling()) return null
      l3Marks.standAt = Date.now()
    }
    const r = await v2.command(id, L3_ACTION[op], tb(label))
    if (r?.result === 'done') {
      if (op === 'moving') l3Marks.moving = true
      if (op === 'low') l3Marks.low = true
      if (op === 'stand') {
        l3Marks.moving = false
        l3Marks.low = false
      }
    } else note('lite3', r?.result === 'no_reply' ? 'warn' : 'bad', lastV2Note(id))
    return null
  }

  /** Lite3 stop (or soft e-stop): works without control, in every mode. */
  async function l3Stop(estop: boolean): Promise<void> {
    const id = l3v2.value?.id
    if (!id) return
    l3SetAxes([0, 0, 0])
    if (estop) l3Marks.estopAt = Date.now()
    const r = await v2.command(id, estop ? 'soft_estop' : 'stop', estop ? t('软急停') : t('停止'))
    if (r?.result !== 'done') note('lite3', 'bad', lastV2Note(id))
  }

  /** The new system has fixed colour and depth streams: there is no image source to pick. */
  async function l3Camera(_rgb: string, _depth: string): Promise<void> {}

  // ---------------------------------------------------------------- Lite3 outdoor navigation (ui-design.md 19)
  // Only for a dog that reports a navigation capability; the state (nav) comes with the same 700 ms poll. Answers that
  // are not "done" go into the dog's note, so the safety row shows them whatever is selected.

  /** The Lite3 of the new dog system, when it can navigate. */
  const l3NavDog = computed<Dog2 | null>(() => (l3v2.value?.navCapability ? l3v2.value : null))
  const l3NavCap = computed(() => l3NavDog.value?.navCapability ?? null)
  const l3Nav = computed(() => l3NavDog.value?.nav ?? null)

  function navNote(r: { result: string } | null, id: string): void {
    if (r?.result !== 'done') note('lite3', r?.result === 'no_reply' ? 'warn' : 'bad', lastV2Note(id))
  }

  /** Opens the start dialog (the dialog checks, asks for "狗已站好" and sends). */
  async function l3NavAskStart(points: Dog2NavPoint[], extra: { routeId?: number | null; routeName?: string | null; source?: string | null } = {}): Promise<boolean> {
    const id = l3NavDog.value?.id
    if (!id || !points.length) return false
    return v2.askStart(id, points, extra)
  }

  async function l3NavPause(): Promise<void> {
    const id = l3NavDog.value?.id
    if (id) navNote(await v2.navPause(id), id)
  }

  async function l3NavResume(): Promise<void> {
    const id = l3NavDog.value?.id
    if (id) navNote(await v2.navResume(id), id)
  }

  async function l3NavCancel(): Promise<void> {
    const id = l3NavDog.value?.id
    if (!id) return
    stopSeq.value++
    navNote(await v2.navCancel(id), id)
  }

  /** While a task is on: sends the change; otherwise it is kept for the next start. Off is asked once. */
  async function l3NavAvoidance(on: boolean, taskOn: boolean): Promise<void> {
    const id = l3NavDog.value?.id
    if (!id) return
    if (!on && !(await v2.askAvoidanceOff(id))) return
    if (taskOn) navNote(await v2.navOptions(id, { avoidance: on }), id)
    else v2.navNext[id] = { avoidance: on, speedLevel: v2.navNext[id]?.speedLevel ?? null, speedMps: v2.navNext[id]?.speedMps ?? null }
  }

  async function l3NavSpeed(level: string, taskOn: boolean): Promise<void> {
    const id = l3NavDog.value?.id
    if (!id) return
    if (taskOn) navNote(await v2.navOptions(id, { speedLevel: level }), id)
    else v2.navNext[id] = { avoidance: v2.navNext[id]?.avoidance ?? null, speedLevel: level, speedMps: null }
  }

  /** A typed-in speed (m/s) instead of a level: for the walk going on, else for the next start. */
  async function l3NavSpeedMps(mps: number, taskOn: boolean): Promise<void> {
    const id = l3NavDog.value?.id
    if (!id) return
    if (taskOn) navNote(await v2.navOptions(id, { speedMps: mps }), id)
    else v2.navNext[id] = { avoidance: v2.navNext[id]?.avoidance ?? null, speedLevel: null, speedMps: mps }
  }

  return {
    l3v2, dogs, receivedAt, commands, serverOffsetMs, mode, selected, notes, tick, stopSeq, ids, present, s10, lite3,
    serverNow, syncTime, age, online, pushStale, pageStale, staleSecs, lost, important, start, select, note, stopMotion, stopAllLocal, onState, onCommand,
    s10Action, s10Hold, s10HoldStart, s10HoldEnd, armHold, armHoldStart, armHoldEnd,
    l3, l3Marks, l3Moving, l3Arm, l3SetAxes, l3Release, l3Mode, l3StandCooling, l3Stop, l3Camera,
    l3NavDog, l3NavCap, l3Nav, l3NavAskStart, l3NavPause, l3NavResume, l3NavCancel, l3NavAvoidance, l3NavSpeed, l3NavSpeedMps,
  }
})
