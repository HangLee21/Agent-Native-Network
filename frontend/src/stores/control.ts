import { perDrone } from './perDrone'
import { computed, ref } from 'vue'
import { controlApi, type Alert, type CommandRecord, type ControlSnapshot } from '@/api/control'
import { ApiError } from '@/api/http'
import { violationsOf } from '@/api/safety'
import { telemetrySocket } from '@/services/ws'
import { t } from '@/i18n'

/**
 * Control authority, DRC, command receipts and alerts (R-10..R-13, S-03).
 * Buttons never show success on click: they follow the command record pushed by the backend.
 */
export const useControlStore = perDrone('control', (sn) => {
  const snapshot = ref<ControlSnapshot | null>(null)
  const commands = ref<CommandRecord[]>([])
  const alerts = ref<Alert[]>([])
  /** Latest command id per UI action key (e.g. "takeoff"), to show status under each button. */
  const lastByAction = ref<Record<string, string>>({})
  /** dogGoal / dogRoute: points of a dog's navigation (one click = the goal; successive clicks add route points). */
  const pickingTarget = ref<null | 'flyto' | 'poi' | 'target' | 'dogGoal' | 'dogRoute'>(null)
  let started = false
  let localSeq = 0

  const granted = computed(() => snapshot.value?.control === 'GRANTED')
  const drcReady = computed(() => !!snapshot.value?.drcReady)
  const criticalCount = computed(() => alerts.value.filter((a) => a.level === 'CRITICAL').length)

  /** Status progression; a receipt never goes back to an earlier stage (REST replies can arrive after WS pushes). */
  const RANK: Record<CommandRecord['status'], number> = { PENDING: 0, SENT: 1, ACKED: 2, FAILED: 2, TIMEOUT: 2, REJECTED: 2 }

  function upsert(rec: CommandRecord): void {
    const i = commands.value.findIndex((c) => c.id === rec.id)
    if (i >= 0 && RANK[commands.value[i]!.status] > RANK[rec.status]) return
    if (i >= 0) commands.value.splice(i, 1, rec)
    else commands.value.unshift(rec)
    if (commands.value.length > 100) commands.value.length = 100
  }

  function byAction(key: string): CommandRecord | null {
    const id = lastByAction.value[key]
    return id ? (commands.value.find((c) => c.id === id) ?? null) : null
  }

  /** Runs a command call; API rejections become a local REJECTED record so the reason is shown in place. */
  async function run(key: string, label: string, call: () => Promise<CommandRecord>): Promise<CommandRecord> {
    try {
      const rec = await call()
      upsert(rec)
      lastByAction.value = { ...lastByAction.value, [key]: rec.id }
      return rec
    } catch (e) {
      const v = e instanceof ApiError ? violationsOf(e.details) : []
      const msg = e instanceof ApiError ? (v.length ? v.map((x) => x.message).join(t('；')) : e.message) : t('请求失败')
      const rec: CommandRecord = {
        id: `local-${++localSeq}`, type: key, label, channel: null, status: 'REJECTED', createdAt: Date.now(),
        sentAt: null, completedAt: Date.now(), resultCode: null, message: msg,
      }
      upsert(rec)
      lastByAction.value = { ...lastByAction.value, [key]: rec.id }
      return rec
    }
  }

  async function requestControl(): Promise<void> {
    try {
      snapshot.value = await controlApi(sn).request()
    } catch (e) {
      await run('control', t('申请云端控制权'), () => Promise.reject(e))
    }
  }

  async function load(): Promise<void> {
    try {
      const [s, c, a] = await Promise.all([controlApi(sn).state(), controlApi(sn).commands(), controlApi(sn).alerts()])
      snapshot.value = s
      commands.value = c
      alerts.value = a
    } catch {
      /* backend unreachable */
    }
  }

  function start(): void {
    if (started || !sn) return
    started = true
    telemetrySocket.onDrone('control', sn, (m) => (snapshot.value = m.data as ControlSnapshot))
    telemetrySocket.onDrone('command', sn, (m) => upsert(m.data as CommandRecord))
    telemetrySocket.onDrone('alerts', sn, (m) => (alerts.value = m.data as Alert[]))
    telemetrySocket.onStatus((c) => c && void load())
    void load()
  }

  return { sn, snapshot, commands, alerts, lastByAction, pickingTarget, granted, drcReady, criticalCount, upsert, byAction, run,
    requestControl, load, start }
})
