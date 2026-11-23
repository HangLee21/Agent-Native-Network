import { perDrone } from './perDrone'
import { computed, ref } from 'vue'
import {
  targetsApi,
  targetConfigApi,
  type ActionResult,
  type AiStatus,
  type LaserReading,
  type TargetAction,
  type TargetConfig,
  type TargetConfigUpdate,
  type TargetState,
  type TargetView,
} from '@/api/targets'
import { ApiError } from '@/api/http'
import { violationsOf } from '@/api/safety'
import { telemetrySocket } from '@/services/ws'
import { useToastStore } from './toast'
import { t } from '@/i18n'

/** A "target" / "aiAuto" broadcast: {event, level, title, targetId, target?, ai?, ...}. */
interface TargetEvent {
  event: string
  level: string
  title: string
  targetId: string | null
  target?: TargetView
  ai?: AiStatus
  decision?: string
  reasons?: { message: string }[] | string[]
  status?: string
}

const ENDED = new Set<TargetState>(['DONE', 'FAILED', 'ABORTED', 'CANCELLED', 'EXPIRED'])

/**
 * Target selection and fly-to (R-24 ~ R-27 draft): targets of this flight, the laser reading, settings,
 * AI auto mode and its countdown. Selecting never moves the drone; every movement is a separate action.
 */
export const useTargetsStore = perDrone('targets', (sn) => {
  const targets = ref<TargetView[]>([])
  const selectedId = ref<string | null>(null)
  const selecting = ref(false)
  const laser = ref<LaserReading | null>(null)
  const config = ref<TargetConfig | null>(null)
  const ai = ref<AiStatus | null>(null)
  /** Latest decision per target (STAY / CLIMB_ONLY …) to offer the follow-up button in the card. */
  const decisions = ref<Record<string, { decision: string; message: string }>>({})
  const busy = ref(false)
  const lastError = ref<string | null>(null)
  let started = false

  const selected = computed<TargetView | null>(() => {
    const byId = selectedId.value ? targets.value.find((t) => t.id === selectedId.value) : undefined
    return byId ?? targets.value.find((t) => !['CANCELLED', 'EXPIRED'].includes(t.state)) ?? null
  })
  const proposals = computed(() => targets.value.filter((t) => t.state === 'PROPOSED'))
  const active = computed(() => targets.value.find((t) => t.state === 'ACTIVE') ?? null)
  const visibleOnMap = computed(() => targets.value.filter((t) => t.lat != null && t.lon != null && !['CANCELLED', 'EXPIRED'].includes(t.state)))

  function upsert(t: TargetView): void {
    const i = targets.value.findIndex((x) => x.id === t.id)
    if (i >= 0) {
      const cur = targets.value[i]!
      if (cur.updatedAt > t.updatedAt) return
      // An action's reply can be built before its end is pushed in the same millisecond (the mock
      // acknowledges at once); that older view must not bring a finished target back to ACTIVE.
      if (cur.updatedAt === t.updatedAt && ENDED.has(cur.state) && !ENDED.has(t.state)) return
      targets.value.splice(i, 1, t)
    } else {
      targets.value.unshift(t)
    }
    if (targets.value.length > 50) targets.value.length = 50
  }

  function onTargetEvent(e: TargetEvent): void {
    if (e.event === 'TARGET_LIST') {
      void load()
      return
    }
    if (e.target) upsert(e.target)
    if (e.event === 'TARGET_ACTION' && e.targetId && e.decision) {
      decisions.value = { ...decisions.value, [e.targetId]: { decision: e.decision, message: e.title } }
    }
    if (e.event === 'AI_PROPOSAL' && e.status === 'proposed' && e.targetId) {
      useToastStore().push('info', e.title, 6000)
    }
  }

  function onAiEvent(e: TargetEvent): void {
    if (e.ai) ai.value = e.ai
    if (e.event === 'AI_AUTO' || (e.event === 'AI_COUNTDOWN' && e.status !== 'started')) {
      useToastStore().push(e.level === 'WARNING' ? 'warn' : 'info', e.title, 5000)
    }
  }

  async function load(): Promise<void> {
    try {
      const s = await targetsApi(sn).list()
      targets.value = s.targets
      laser.value = s.laser
      config.value = s.config
      ai.value = s.ai
    } catch {
      /* backend unreachable */
    }
  }

  function start(): void {
    if (started || !sn) return
    started = true
    telemetrySocket.onDrone('target', sn, (m) => onTargetEvent(m.data as TargetEvent))
    telemetrySocket.onDrone('aiAuto', sn, (m) => onAiEvent(m.data as TargetEvent))
    telemetrySocket.onDrone('laser', sn, (m) => (laser.value = m.data as LaserReading))
    telemetrySocket.on('target-config', (m) => (config.value = m.data as TargetConfig))
    telemetrySocket.onStatus((c) => c && void load())
    void load()
  }

  function message(e: unknown): string {
    if (e instanceof ApiError) {
      const v = violationsOf(e.details)
      return v.length ? v.map((x) => x.message).join('；') : e.message
    }
    return t('请求失败')
  }

  /** Runs a call; failures become a toast and `lastError` (shown in the card). */
  async function call<T>(fn: () => Promise<T>): Promise<T | null> {
    busy.value = true
    lastError.value = null
    try {
      return await fn()
    } catch (e) {
      lastError.value = message(e)
      useToastStore().push('warn', lastError.value, 6000)
      return null
    } finally {
      busy.value = false
    }
  }

  async function select(input: 'TAP' | 'CIRCLE', lens: string, x: number, y: number, w = 0, h = 0): Promise<void> {
    const t = await call(() => targetsApi(sn).select(input, lens, x, y, w, h))
    if (t) {
      upsert(t)
      selectedId.value = t.id
    }
  }

  async function selectGeo(lat: number, lon: number, height: number): Promise<void> {
    const t = await call(() => targetsApi(sn).geo(lat, lon, height, 'RELATIVE', 'MAP', true))
    if (t) {
      upsert(t)
      selectedId.value = t.id
    }
  }

  async function act(id: string, action: TargetAction, extra: { photo?: boolean } = {}): Promise<ActionResult | null> {
    const r = await call(() => targetsApi(sn).act(id, action, extra))
    if (r) {
      upsert(r.target)
      decisions.value = { ...decisions.value, [id]: { decision: r.decision, message: r.message } }
    } else {
      void refresh(id)
    }
    return r
  }

  async function refresh(id: string): Promise<void> {
    try {
      const s = await targetsApi(sn).list()
      const t = s.targets.find((x) => x.id === id)
      if (t) upsert(t)
    } catch {
      /* ignore */
    }
  }

  const stop = () => call(() => targetsApi(sn).stop()).then((r) => r && upsert(r.target))
  const remeasure = (id: string) => call(() => targetsApi(sn).remeasure(id)).then((t) => t && upsert(t))
  const accept = (id: string) => call(() => targetsApi(sn).accept(id)).then((t) => {
    if (t) {
      upsert(t)
      selectedId.value = t.id
    }
  })
  const cancel = (id: string) => call(() => targetsApi(sn).cancel(id)).then((t) => t && upsert(t))
  const clearFinished = () => call(() => targetsApi(sn).clearFinished()).then(() => load())
  const aiOn = () => call(() => targetsApi(sn).aiOn()).then((s) => s && (ai.value = s))
  const aiOff = () => call(() => targetsApi(sn).aiOff()).then((s) => s && (ai.value = s))
  const aiStop = () => call(() => targetsApi(sn).aiStop()).then((s) => s && (ai.value = s))
  const cancelCountdown = () => call(() => targetsApi(sn).cancelCountdown()).then((s) => s && (ai.value = s))

  async function updateConfig(u: TargetConfigUpdate): Promise<boolean> {
    const c = await call(() => targetConfigApi.updateConfig(u))
    if (c) config.value = c
    return !!c
  }

  return {
    sn, targets, selectedId, selecting, laser, config, ai, decisions, busy, lastError, selected, proposals, active, visibleOnMap,
    start, load, select, selectGeo, act, stop, remeasure, accept, cancel, clearFinished, aiOn, aiOff, aiStop, cancelCountdown,
    updateConfig, onTargetEvent, onAiEvent, upsert,
  }
})
