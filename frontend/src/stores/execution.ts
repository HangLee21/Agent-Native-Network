import { perDrone } from './perDrone'
import { computed, ref } from 'vue'
import { executionApi, syncApi, type ExecMode, type ExecutionSnapshot } from '@/api/execution'
import { ApiError } from '@/api/http'
import { violationsOf } from '@/api/safety'
import { telemetrySocket } from '@/services/ws'
import { useOverlaysStore } from './overlays'
import { useToastStore } from './toast'
import { isEn, t } from '@/i18n'

/** Route execution (R-09) and sync to RC (R-08). */
export const useExecutionStore = perDrone('execution', (sn) => {
  const current = ref<ExecutionSnapshot | null>(null)
  const busy = ref(false)
  let started = false

  const active = computed(() => !!current.value?.active)
  const paused = computed(() => current.value?.state === 'PAUSED')

  function apply(s: ExecutionSnapshot | null): void {
    // A request's reply can arrive after the WebSocket already reported the end of the same execution
    // (e.g. abort → "ABORTED" pushed first); never let that older snapshot bring a finished run back.
    const cur = current.value
    if (s && cur && s.id === cur.id && cur.endedAt != null && s.endedAt == null) return
    // Same for a resume reply built before the run loop flew on (PAUSED) arriving after the push that it did:
    // the version grows with every change (the log length stops growing at 200 entries).
    if (s && cur && s.id === cur.id && (s.version ?? s.log?.length ?? 0) < (cur.version ?? cur.log?.length ?? 0)) return
    current.value = s
    const ov = useOverlaysStore(sn)
    if (s?.active) ov.route = s.waypoints.map((w) => ({ lat: w.lat, lon: w.lon }))
  }

  async function load(): Promise<void> {
    try {
      apply(await executionApi(sn).current())
    } catch {
      /* none */
    }
  }

  function errorText(e: unknown): string {
    if (!(e instanceof ApiError)) return t('请求失败')
    const v = violationsOf(e.details)
    // the head of the backend message ("安全检查未通过：…"); in English it arrives translated, with ": "
    const head = isEn() ? e.message.split(': ')[0] : e.message.split('：')[0]
    return v.length ? t('{head}：{list}', { head, list: v.map((x) => x.message).join(t('；')) }) : e.message
  }

  async function execute(routeId: string, mode: ExecMode, rthConfirmed = false): Promise<boolean> {
    busy.value = true
    try {
      apply(await executionApi(sn).execute(routeId, mode, rthConfirmed))
      return true
    } catch (e) {
      useToastStore().push('danger', t('无法执行：{reason}', { reason: errorText(e) }), 7000)
      return false
    } finally {
      busy.value = false
    }
  }

  async function abort(): Promise<void> {
    try {
      apply(await executionApi(sn).abort())
    } catch (e) {
      useToastStore().push('danger', errorText(e))
    }
  }

  /** After a two-drone proximity pause (S-05); a refusal (still too close) is shown as a toast. */
  async function resume(): Promise<boolean> {
    try {
      apply(await executionApi(sn).resume())
      return true
    } catch (e) {
      useToastStore().push('danger', t('无法恢复：{reason}', { reason: errorText(e) }), 7000)
      return false
    }
  }

  async function sync(routeId: string) {
    busy.value = true
    try {
      return await syncApi.sync(routeId)
    } catch (e) {
      useToastStore().push('danger', t('同步失败：{reason}', { reason: errorText(e) }), 7000)
      return null
    } finally {
      busy.value = false
    }
  }

  function start(): void {
    if (started || !sn) return
    started = true
    telemetrySocket.onDrone('execution', sn, (m) => apply(m.data as ExecutionSnapshot))
    telemetrySocket.onStatus((c) => c && void load())
    void load()
  }

  return { sn, current, busy, active, paused, apply, load, execute, abort, resume, sync, start, errorText }
})
