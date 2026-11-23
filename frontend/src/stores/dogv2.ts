import { defineStore } from 'pinia'
import { computed, reactive, ref } from 'vue'
import { ApiError } from '@/api/http'
import { t, tb } from '@/i18n'
import {
  dog2Api, dogRoutesApi, replyText, type Dog2, type Dog2List, type Dog2NavCheck, type Dog2NavPoint, type Dog2NavProblem,
  type Dog2NavReply, type Dog2NavSettings, type Dog2NavStart, type Dog2NavView, type Dog2Reply, type Dog2Route,
} from '@/api/dogv2'

/**
 * "控制已解除：<reason>" from the backend (409 on a beat). In English mode the message arrives translated, so the
 * prefix is matched in both forms; in Chinese mode this is the same as /^控制已解除：?/.
 */
/** A poll of the dog list not back after this long is abandoned (the page counts a dog as unseen after 3.5 s). */
const POLL_TIMEOUT_MS = 2000

function releasedPrefix(): RegExp {
  const en = tb('控制已解除').replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return new RegExp(`^(?:控制已解除|${en})(?:：|: ?)?`) // i18n-ignore
}

/**
 * Browser side of the new dog system. Hold-to-move sends a beat every 100 ms WITHOUT waiting for the previous
 * one (the old Lite3 path waited, so a slow round trip cut the beats to 1-2 per second and control dropped 9 times
 * in the 2026-11-09 field test). While control is held and nothing is pressed, an all-zero beat about every 0.8 s
 * keeps it (the backend lets go after 2.5 s of silence, the dog after 3 s).
 */
export const useDog2Store = defineStore('dogv2', () => {
  const mode = ref<Dog2List['mode']>('off')
  const broker = ref(false)
  const dogs = ref<Dog2[]>([])
  const error = ref<string | null>(null)
  const page = `page-${Math.random().toString(36).slice(2, 10)}`
  const busy = reactive<Record<string, string | null>>({})
  const notes = ref<{ at: number; dog: string; tone: 'ok' | 'warn' | 'bad'; text: string }[]>([])
  const hold = reactive<{ dog: string | null; session: string | null; axes: [number, number, number]; lastSentAt: number; inflight: number; lostReason: string | null; n: number }>(
    { dog: null, session: null, axes: [0, 0, 0], lastSentAt: 0, inflight: 0, lostReason: null, n: 0 })
  let poller: number | null = null
  let ticker: number | null = null

  const byId = computed(() => Object.fromEntries(dogs.value.map((d) => [d.id, d])) as Record<string, Dog2>)
  const moving = computed(() => hold.axes.some((a) => a !== 0))

  function note(dog: string, tone: 'ok' | 'warn' | 'bad', text: string): void {
    notes.value = [{ at: Date.now(), dog, tone, text }, ...notes.value].slice(0, 30)
  }

  /**
   * One poll at a time; one that has not come back within POLL_TIMEOUT_MS is abandoned so the next goes out (field
   * test 2026-11-10: a stuck poll left the page without news for about 10 s while the dog and the backend were fine).
   * `fresh` (after a command) replaces a poll already out, so the reply shows the state after the command.
   */
  let polling: AbortController | null = null
  let pollingAt = 0

  async function refresh(fresh = false): Promise<void> {
    if (polling && !fresh && Date.now() - pollingAt < POLL_TIMEOUT_MS) return
    polling?.abort()
    const mine = new AbortController()
    polling = mine
    pollingAt = Date.now()
    try {
      const r = await dog2Api.list(mine.signal)
      if (polling !== mine) return      // abandoned: a newer poll is out
      mode.value = r.mode
      broker.value = r.broker
      dogs.value = r.dogs
      error.value = null
      const d = hold.dog ? r.dogs.find((x) => x.id === hold.dog) : null
      if (hold.session && d && !d.control.mine && d.control.session !== hold.session) {
        lost(d.control.endedReason ?? t('狗那边已解除控制'))
      }
    } catch (e) {
      if (polling !== mine) return
      error.value = e instanceof ApiError ? e.message : t('连不上后端')
    } finally {
      if (polling === mine) polling = null
    }
  }

  // several parts of the page may poll at once (the new dog page, the map's dog layer): it stops with the last one
  let users = 0

  function start(intervalMs = 700): void {
    users += 1
    void refresh()
    if (poller === null) poller = window.setInterval(() => void refresh(), intervalMs)
  }

  function stop(): void {
    users = Math.max(0, users - 1)
    if (users > 0) return
    if (poller !== null) window.clearInterval(poller)
    poller = null
  }

  async function run(dog: string, label: string, fn: () => Promise<Dog2Reply>): Promise<Dog2Reply | null> {
    busy[dog] = label
    try {
      const r = await fn()
      note(dog, r.result === 'done' ? 'ok' : r.result === 'no_reply' ? 'warn' : 'bad', t('{action}：{result}', { action: label, result: replyText(r) }))
      return r
    } catch (e) {
      note(dog, 'bad', t('{action}：{result}', { action: label, result: e instanceof ApiError ? e.message : t('发送失败') }))
      return null
    } finally {
      busy[dog] = null
      void refresh(true)
    }
  }

  const command = (dog: string, action: string, label: string, args: Record<string, unknown> = {}) =>
    run(dog, label, () => dog2Api.command(dog, action, args))

  async function take(dog: string): Promise<void> {
    const r = await run(dog, t('取得控制'), () => dog2Api.take(dog, page))
    if (r?.result === 'done' && r.session) {
      hold.dog = dog
      hold.session = r.session
      hold.axes = [0, 0, 0]
      hold.lostReason = null
      hold.lastSentAt = 0
      if (ticker === null) ticker = window.setInterval(tick, 100)
    }
  }

  // the reason goes to the backend in Chinese and comes back translated (en/dogv2.ts has it)
  async function release(reason = '交出控制'): Promise<void> { // i18n-ignore
    const { dog, session } = hold
    endLocal()
    if (dog && session) await run(dog, t('交出控制'), () => dog2Api.release(dog, session, reason))
  }

  function endLocal(): void {
    if (ticker !== null) window.clearInterval(ticker)
    ticker = null
    hold.session = null
    hold.axes = [0, 0, 0]
  }

  function lost(reason: string): void {
    const dog = hold.dog
    endLocal()
    hold.lostReason = reason
    if (dog) note(dog, 'warn', t('控制权已失去：{reason}', { reason }))
  }

  function setAxes(a: [number, number, number]): void {
    const changed = a.some((v, i) => v !== hold.axes[i])
    hold.axes = a
    if (changed) beat()                 // a released key stops at once, not at the next tick
  }

  function tick(): void {
    if (!hold.session) return
    if (moving.value || Date.now() - hold.lastSentAt >= 800) beat()
  }

  function beat(): void {
    const { dog, session } = hold
    if (!dog || !session) return
    if (hold.inflight >= 3) return      // the backend answers within ms; three outstanding means something is stuck
    hold.lastSentAt = Date.now()
    hold.inflight++
    dog2Api.teleop(dog, session, [...hold.axes] as [number, number, number], ++hold.n)
      .catch((e: unknown) => {
        if (hold.session === session && e instanceof ApiError && e.status === 409) lost(e.message.replace(releasedPrefix(), '') || t('狗那边已解除控制'))
      })
      .finally(() => { hold.inflight-- })
  }

  /** Leaving the page or the dog view: stop and hand control back. */
  function leave(reason: string): void {
    if (hold.session) void release(reason)
  }

  // ---------------------------------------------------------------- outdoor navigation (ui-design.md 19)
  // The task state itself comes with the dog list (nav, navCapability), polled as before; these are the actions, the
  // per-dog settings (GET /nav), the points being picked or edited on the map, and the confirmation dialogs.

  const navView = reactive<Record<string, Dog2NavView>>({})
  /** Allowed area from the dog's last check, drawn on the map. */
  const navArea = reactive<Record<string, [number, number][] | null>>({})
  /** Options chosen on the card for the next start (null: the dog's settings). */
  const navNext = reactive<Record<string, { avoidance: boolean | null; speedLevel: string | null; speedMps?: number | null }>>({})
  const navDraft = ref<NavDraft | null>(null)
  const navDialog = ref<NavDialog | null>(null)

  /** GET /nav: capability, settings, latest state (opening the navigation area also lets the dog start its parts). */
  async function navLoad(dog: string): Promise<Dog2NavView | null> {
    try {
      const v = await dog2Api.nav(dog)
      navView[dog] = v
      return v
    } catch {
      return null
    }
  }

  /** Lets the dog start its navigation parts (lidar, Nav2) while the navigation area is open; quiet, nothing to show. */
  async function navPrepare(dog: string): Promise<void> {
    try {
      await dog2Api.navPrepare(dog)
    } catch {
      /* offline, not enabled, or an older backend: the start says what is missing */
    }
  }

  function navSettingsOf(dog: string): Dog2NavSettings | null {
    return navView[dog]?.settings ?? null
  }

  async function navCheck(dog: string, points: Dog2NavPoint[]): Promise<Dog2NavCheck | { error: string }> {
    try {
      const r = await dog2Api.navCheck(dog, points)
      navArea[dog] = r.area ?? null
      return r
    } catch (e) {
      return { error: e instanceof ApiError ? e.message : t('发送失败') }
    }
  }

  /**
   * A nav endpoint call with the usual reply note. A 400 of the platform's own checks comes back as `rejected` with its
   * problems, so a dialog can list them; nothing reaches the dog then.
   */
  async function runNav(dog: string, label: string, fn: () => Promise<Dog2NavReply>): Promise<(Dog2NavReply & { problems?: Dog2NavProblem[] }) | null> {
    busy[dog] = label
    try {
      const r = await fn()
      note(dog, r.result === 'done' ? 'ok' : r.result === 'no_reply' ? 'warn' : 'bad', t('{action}：{result}', { action: label, result: replyText(r) }))
      return r
    } catch (e) {
      const d = (e instanceof ApiError ? e.details : null) as { problems?: Dog2NavProblem[]; code?: string } | null
      const text = e instanceof ApiError ? e.message : t('发送失败')
      note(dog, 'bad', t('{action}：{result}', { action: label, result: text }))
      if (e instanceof ApiError && e.status >= 400 && e.status < 500) {
        return { result: 'rejected', code: d?.code ?? null, text, problems: Array.isArray(d?.problems) ? d.problems : [] }
      }
      return null
    } finally {
      busy[dog] = null
      void refresh(true)
    }
  }

  const navStart = (dog: string, req: Dog2NavStart) => runNav(dog, t('开始导航'), () => dog2Api.navStart(dog, req))
  const navPause = (dog: string) => runNav(dog, t('暂停导航'), () => dog2Api.navPause(dog))
  const navResume = (dog: string) => runNav(dog, t('继续导航'), () => dog2Api.navResume(dog))
  const navCancel = (dog: string) => runNav(dog, t('结束导航'), () => dog2Api.navCancel(dog))
  const navOptions = (dog: string, opts: { avoidance?: boolean; speedLevel?: string; speedMps?: number }) =>
    runNav(dog, opts.avoidance === false ? t('关掉自动避障') : opts.avoidance === true ? t('打开自动避障')
      : opts.speedMps != null ? t('改速度') : t('换速度档位'), () => dog2Api.navOptions(dog, opts))

  async function navSaveSettings(dog: string, settings: Dog2NavSettings): Promise<Dog2NavSettings | string> {
    try {
      const saved = await dog2Api.navSettings(dog, settings)
      const v = navView[dog]
      navView[dog] = { capability: v?.capability ?? byId.value[dog]?.navCapability ?? null, nav: v?.nav ?? null, task: v?.task ?? null, settings: saved }
      return saved
    } catch (e) {
      return e instanceof ApiError ? e.message : t('发送失败')
    }
  }

  // -- the points being picked / edited on the map (one draft at a time, bound to one dog)
  let draftSeq = 0
  let draftTimer: number | null = null

  function draftOpen(dog: string, points: Dog2NavPoint[] = [], meta: { routeId?: number | null; routeName?: string | null } = {}): void {
    navDraft.value = { dog, points: points.map((p) => ({ ...p })), routeId: meta.routeId ?? null, routeName: meta.routeName ?? null, check: null, checking: false, checkError: null }
    scheduleCheck(0)
  }

  function draftEdit(fn: (pts: Dog2NavPoint[]) => Dog2NavPoint[]): void {
    const d = navDraft.value
    if (!d) return
    d.points = fn(d.points)
    d.routeId = null          // edited: no longer the saved route as it was
    scheduleCheck()
  }

  const draftAdd = (p: Dog2NavPoint) => draftEdit((pts) => [...pts, { lat: p.lat, lon: p.lon }])
  const draftMove = (i: number, p: Dog2NavPoint) => draftEdit((pts) => pts.map((q, j) => (j === i ? { ...q, lat: p.lat, lon: p.lon } : q)))
  const draftRemove = (i: number) => draftEdit((pts) => pts.filter((_, j) => j !== i))

  function draftClear(): void {
    if (draftTimer !== null) window.clearTimeout(draftTimer)
    draftTimer = null
    draftSeq++
    navDraft.value = null
  }

  /** Every change is checked by the platform (allowed area, distance, number of points) about 300 ms later. */
  function scheduleCheck(ms = 300): void {
    if (draftTimer !== null) window.clearTimeout(draftTimer)
    draftTimer = window.setTimeout(() => void draftCheck(), ms)
  }

  async function draftCheck(): Promise<void> {
    draftTimer = null
    const d = navDraft.value
    if (!d) return
    const seq = ++draftSeq
    if (!d.points.length) {
      d.check = null
      d.checking = false
      d.checkError = null
      return
    }
    d.checking = true
    const r = await navCheck(d.dog, d.points)
    if (seq !== draftSeq || navDraft.value !== d) return    // a newer edit is being checked
    d.checking = false
    if ('error' in r) {
      d.check = null
      d.checkError = r.error
    } else {
      d.check = r
      d.checkError = null
    }
  }

  // -- the dog route library
  const routes = ref<Dog2Route[]>([])
  const routesError = ref<string | null>(null)

  async function routesLoad(): Promise<void> {
    try {
      routes.value = await dogRoutesApi.list()
      routesError.value = null
    } catch (e) {
      routesError.value = e instanceof ApiError ? e.message : t('连不上后端')
    }
  }

  /** Puts a saved route into the draft (fetches its points when the list did not carry them). */
  async function routeOpen(dog: string, r: Dog2Route): Promise<string | null> {
    try {
      const full = r.points?.length ? r : await dogRoutesApi.get(r.id)
      draftOpen(dog, full.points ?? [], { routeId: full.id, routeName: full.name })
      return null
    } catch (e) {
      return e instanceof ApiError ? e.message : t('发送失败')
    }
  }

  async function routeSave(name: string, points: Dog2NavPoint[]): Promise<Dog2Route | string> {
    try {
      const r = await dogRoutesApi.create({ name, points })
      void routesLoad()
      const d = navDraft.value
      if (d) {
        d.routeId = r.id
        d.routeName = r.name
      }
      return r
    } catch (e) {
      return e instanceof ApiError ? e.message : t('发送失败')
    }
  }

  async function routeImport(dog: string, aircraftRouteId: string): Promise<string | null> {
    try {
      const r = await dogRoutesApi.fromRoute(aircraftRouteId)
      void routesLoad()
      draftOpen(dog, r.points ?? [], { routeId: r.id, routeName: r.name })
      return null
    } catch (e) {
      return e instanceof ApiError ? e.message : t('发送失败')
    }
  }

  async function routeRemove(id: number): Promise<string | null> {
    try {
      await dogRoutesApi.remove(id)
      routes.value = routes.value.filter((r) => r.id !== id)
      return null
    } catch (e) {
      return e instanceof ApiError ? e.message : t('发送失败')
    }
  }

  // -- confirmation dialogs (components/dog/DogNavConfirm.vue)
  let dialogResolve: ((ok: boolean) => void) | null = null

  /** Opens the start dialog for these points; resolves true once the dog started the task. */
  function askStart(dog: string, points: Dog2NavPoint[], extra: { routeId?: number | null; routeName?: string | null; dryRun?: boolean; source?: string | null } = {}): Promise<boolean> {
    dialogResolve?.(false)
    navDialog.value = { kind: 'start', dog, points: points.map((p) => ({ ...p })), routeId: extra.routeId ?? null, routeName: extra.routeName ?? null, dryRun: !!extra.dryRun, source: extra.source ?? null }
    return new Promise((r) => (dialogResolve = r))
  }

  /** Turning avoidance off is asked once, with the fact. */
  function askAvoidanceOff(dog: string): Promise<boolean> {
    dialogResolve?.(false)
    navDialog.value = { kind: 'avoidanceOff', dog }
    return new Promise((r) => (dialogResolve = r))
  }

  function dialogDone(ok: boolean): void {
    const r = dialogResolve
    dialogResolve = null
    navDialog.value = null
    r?.(ok)
  }

  return {
    mode, broker, dogs, byId, error, busy, notes, hold, moving, page, refresh, start, stop, command, take, release, setAxes, leave, note,
    navView, navArea, navNext, navDraft, navDialog, navLoad, navPrepare, navSettingsOf, navCheck, navStart, navPause, navResume, navCancel, navOptions,
    navSaveSettings, draftOpen, draftAdd, draftMove, draftRemove, draftClear, draftCheck, routes, routesError, routesLoad, routeOpen,
    routeSave, routeImport, routeRemove, askStart, askAvoidanceOff, dialogDone,
  }
})

/** Points picked or edited on the map for one dog, with the platform's check of them. */
export interface NavDraft {
  dog: string
  points: Dog2NavPoint[]
  routeId: number | null
  routeName: string | null
  check: Dog2NavCheck | null
  checking: boolean
  checkError: string | null
}

export type NavDialog =
  | { kind: 'start'; dog: string; points: Dog2NavPoint[]; routeId: number | null; routeName: string | null; dryRun: boolean; source: string | null }
  | { kind: 'avoidanceOff'; dog: string }
