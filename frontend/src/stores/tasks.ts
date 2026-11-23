import { perDrone } from './perDrone'
import { computed, ref, watch } from 'vue'
import { controlApi } from '@/api/control'
import { useControlStore } from './control'
import { useTelemetryStore } from './telemetry'
import { useExecutionStore } from './execution'
import { useManualStore } from './manual'
import { useTargetsStore } from './targets'
import { useOverlaysStore } from './overlays'
import { useConfirmStore } from './confirm'
import { useToastStore } from './toast'
import { t } from '@/i18n'

/** Cards of the flight monitor's task area (ui-design.md §2.2). */
export type TaskKey = 'fly' | 'orb' | 'rte' | 'stk' | 'tgt' | 'ai'
/** Activities that move the aircraft; only one at a time (ui-design.md §4.7). */
export type MotionKey = 'fly' | 'orb' | 'rte' | 'stk' | 'tgt' | 'rth'
/** Every stop that exists on the monitor page; each one calls its own, unchanged API. */
export type StopKey = 'fly' | 'orb' | 'rte' | 'tgt' | 'ai' | 'stk'

export const TASK_LABELS: Record<TaskKey, string> = { fly: t('飞往'), orb: t('环绕'), rte: t('航线'), stk: t('杆量控制'), tgt: t('目标'), ai: t('AI 自动') }
export const MOTION_LABELS: Record<MotionKey, string> = { fly: t('飞往'), orb: t('环绕'), rte: t('航线执行'), stk: t('杆量控制'), tgt: t('目标移动'), rth: t('返航') }
const MOTION_CARD: Record<MotionKey, TaskKey | null> = { fly: 'fly', orb: 'orb', rte: 'rte', stk: 'stk', tgt: 'tgt', rth: null }
const MOTION_TASKS: TaskKey[] = ['fly', 'orb', 'rte', 'stk']

export const STOP_ITEMS: { key: StopKey; label: string; api: string }[] = [
  { key: 'fly', label: t('结束 flyto'), api: 'POST /flight/fly-to/stop' },
  { key: 'orb', label: t('退出环绕'), api: 'POST /flight/poi/exit' },
  { key: 'rte', label: t('停止执行'), api: 'POST /executions/current/abort' },
  { key: 'tgt', label: t('停止目标动作'), api: 'POST /targets/active/stop' },
  { key: 'ai', label: t('停止 AI'), api: 'POST /targets/ai/stop' },
  { key: 'stk', label: t('退出杆量控制'), api: 'POST /manual/stick/exit' },
]

const STOP_WAIT_MS = 15000

/**
 * Task area state of the flight monitor: which card is shown, what is moving the aircraft, and the stops.
 * Nothing here adds an API: every stop and start goes through the same store action as before; switching
 * from one moving task to another only chains the old task's stop and the new task's normal start.
 */
export const useTasksStore = perDrone('tasks', (sn) => {
  const control = useControlStore(sn)
  const tel = useTelemetryStore(sn)
  const execution = useExecutionStore(sn)
  const manual = useManualStore(sn)
  const targets = useTargetsStore(sn)
  const overlays = useOverlaysStore(sn)
  const confirm = useConfirmStore()
  const toast = useToastStore()

  const selected = ref<TaskKey | null>(null)

  /**
   * What moves the aircraft, from the state the features already report. Fly-to and POI have no explicit
   * running state in the frontend: mode_code 17 (指令飞行) plus the newer of the "poi" / "target" overlays
   * tells them apart. Approximate until U-26/U-27; the stop menu always offers every stop regardless.
   */
  const motion = computed<MotionKey | null>(() => {
    if (manual.snapshot?.active) return 'stk'
    if (targets.active) return 'tgt'
    if (execution.active) return 'rte'
    const mode = tel.drone?.modeCode
    if (mode === 9) return 'rth'
    if (mode === 4) return 'fly'
    if (mode === 17) {
      const poi = overlays.items.poi
      const target = overlays.items.target
      return poi && (!target || poi.updatedAt >= target.updatedAt) ? 'orb' : 'fly'
    }
    return null
  })
  const motionName = computed(() => (tel.drone?.modeCode === 4 ? t('一键起飞') : motion.value ? MOTION_LABELS[motion.value] : ''))
  const aiOn = computed(() => !!targets.ai?.on)
  /**
   * A target "环绕" runs as poi_enter and is not the backend's active target action, so 停止目标动作 / 停止 AI
   * are refused or leave it orbiting; it is ended with 退出环绕 (POST /flight/poi/exit), as before the redesign.
   */
  const targetOrbit = computed(() => targets.active?.action === 'ORBIT')

  /** Running = the card's own task is active; its 返回 is locked until it is stopped. */
  function isRunning(k: TaskKey): boolean {
    if (k === 'ai') return aiOn.value
    return MOTION_CARD[motion.value ?? 'rth'] === k
  }

  /** The main stop: the running activity's own stop. With nothing detected it is today's 结束 flyto. */
  const stopPlan = computed<{ key: StopKey; label: string; idle: boolean }>(() => {
    const m = motion.value
    if (m === 'stk') return { key: 'stk', label: t('退出杆量控制'), idle: false }
    if (m === 'tgt' && targetOrbit.value) return { key: 'orb', label: t('退出环绕 · 悬停'), idle: false }
    if (m === 'tgt') return aiOn.value ? { key: 'ai', label: t('停止 AI · 悬停'), idle: false } : { key: 'tgt', label: t('停止目标动作 · 悬停'), idle: false }
    if (m === 'rte') return { key: 'rte', label: t('停止执行 · 悬停'), idle: false }
    if (aiOn.value) return { key: 'ai', label: t('停止 AI'), idle: false }
    if (m === 'orb') return { key: 'orb', label: t('退出环绕'), idle: false }
    // during take-off (mode 4) keep the old label: whether fly_to_point_stop ends a take-off is not documented
    if (m === 'fly') return { key: 'fly', label: tel.drone?.modeCode === 4 ? t('结束 flyto · 悬停') : t('结束飞往 · 悬停'), idle: false }
    return { key: 'fly', label: t('停止 · 悬停'), idle: true }
  })

  /** Enabled state of each stop, the same conditions as the buttons it replaces. */
  function stopEnabled(k: StopKey): boolean {
    switch (k) {
      case 'fly': return tel.airborne
      case 'orb': return true
      case 'rte': return execution.active
      case 'tgt': return !!targets.active
      case 'ai': return aiOn.value
      case 'stk': return !!manual.snapshot?.active
    }
  }

  /** Other running activities the main stop does not cover (shown under it). */
  const othersRunning = computed(() => {
    const list: string[] = []
    const plan = stopPlan.value.key
    if (aiOn.value && plan !== 'ai') list.push(t('AI 自动'))
    if (execution.active && plan !== 'rte') list.push(t('航线执行'))
    if (manual.snapshot?.active && plan !== 'stk') list.push(t('杆量控制'))
    return list
  })

  /** "看向" turns the aircraft (look_at locked=true); not while the pilot steers it or it returns home. */
  const lookBlockedReason = computed<string | null>(() => {
    if (manual.snapshot?.active) return t('杆量控制中由你控制偏航：先退出杆量控制')
    if (tel.drone?.modeCode === 9) return t('返航中由返航控制航向')
    return null
  })

  async function stop(k: StopKey, opts: { confirmed?: boolean } = {}): Promise<void> {
    switch (k) {
      case 'fly':
        await control.run('flyto', t('结束飞行任务'), () => controlApi(sn).stopFlyTo())
        return
      case 'orb':
        await control.run('poi', t('退出环绕'), () => controlApi(sn).poiExit())
        return
      case 'rte':
        if (!opts.confirmed && !(await confirm.ask({ title: t('停止执行'), message: t('将结束当前 flyto，飞机在当前位置悬停。确认停止？'), confirmText: t('停止'), danger: true, focus: 'confirm' }))) return
        await execution.abort()
        return
      case 'tgt':
        await targets.stop()
        return
      case 'ai':
        await targets.aiStop()
        return
      case 'stk':
        await manual.exit()
        return
    }
  }

  /** The motion task that would have to stop before `next` starts, or null. */
  function conflictFor(next: TaskKey): MotionKey | null {
    const m = motion.value
    if (!m) return null
    if (m !== 'rth' && MOTION_CARD[m] === next) return null
    return m
  }

  function waitUntil(pred: () => boolean, ms: number): Promise<boolean> {
    if (pred()) return Promise.resolve(true)
    return new Promise((resolve) => {
      const timer = setTimeout(() => {
        stopWatch()
        resolve(false)
      }, ms)
      const stopWatch = watch(pred, (ok) => {
        if (!ok) return
        clearTimeout(timer)
        stopWatch()
        resolve(true)
      })
    })
  }

  /** Stops a moving task with its own API and waits until it no longer moves the aircraft. */
  async function stopAndWait(m: MotionKey): Promise<boolean> {
    if (m === 'rth') await control.run('rth', t('取消返航'), () => controlApi(sn).cancelReturnHome())
    else if (m === 'tgt') await stop(targetOrbit.value ? 'orb' : aiOn.value ? 'ai' : 'tgt', { confirmed: true })
    else await stop(m, { confirmed: true })
    const ok = await waitUntil(() => motion.value !== m, STOP_WAIT_MS)
    if (!ok) toast.push('danger', t('{task}没有在 {s} 秒内停下，未开始新任务；请看指令回执', { task: MOTION_LABELS[m], s: STOP_WAIT_MS / 1000 }), 7000)
    return ok
  }

  /** Confirm text for "stop A first, then start B" (shared with the target card's move confirmation). */
  function switchDetails(m: MotionKey): string {
    const api = m === 'rth' ? t('取消返航') : m === 'tgt' ? (targetOrbit.value ? t('退出环绕') : aiOn.value ? t('停止 AI') : t('停止目标动作')) : STOP_ITEMS.find((s) => s.key === m)?.label
    return t('将先停止：{task}（调用原来的「{api}」），确认停下后再继续', { task: MOTION_LABELS[m], api })
  }

  /** Shows a card. Starting a different moving task first stops the running one (one confirmation). */
  async function select(k: TaskKey): Promise<void> {
    const pre = MOTION_TASKS.includes(k) ? conflictFor(k) : null
    if (pre) {
      const ok = await confirm.ask({
        title: t('先停止{a}，再开始{b}？', { a: MOTION_LABELS[pre], b: TASK_LABELS[k] }),
        message: t('同一时间只能有一个运动任务。确认后：停止当前任务，等它停下，再打开新任务继续原来的步骤。'),
        details: [switchDetails(pre), t('停止失败或超时：不开始新任务，并显示原因')],
        confirmText: t('停止并开始{task}', { task: TASK_LABELS[k] }),
        danger: true,
      })
      if (!ok || !(await stopAndWait(pre))) return
    }
    leave(selected.value, k)
    selected.value = k
    if (k === 'fly' && tel.airborne) control.pickingTarget = 'flyto'
    if (k === 'orb' && tel.airborne) control.pickingTarget = 'poi'
  }

  /** Shows a card without starting anything (e.g. the running-task strip). */
  function show(k: TaskKey): void {
    leave(selected.value, k)
    selected.value = k
  }

  /** Leaves a card: back to the running task's card, else to the task list. */
  function back(): void {
    const from = selected.value
    const card = motion.value ? MOTION_CARD[motion.value] : null
    leave(from, null)
    selected.value = card && card !== from ? card : null
  }

  /** Cancels what was only local to the card being left (map pick, video select mode). */
  function leave(from: TaskKey | null, to: TaskKey | null): void {
    if (from === to) return
    if ((from === 'fly' && control.pickingTarget === 'flyto') || (from === 'orb' && control.pickingTarget === 'poi') || (from === 'tgt' && control.pickingTarget === 'target')) {
      control.pickingTarget = null
    }
    if (from === 'tgt') targets.selecting = false
  }

  /** A task that starts elsewhere (plan page, another client) opens its card if nothing is shown. */
  watch(motion, (m) => {
    const card = m && tel.drone?.modeCode !== 4 ? MOTION_CARD[m] : null
    if (card && !selected.value) selected.value = card
  }, { immediate: true })

  return {
    selected, motion, motionName, aiOn, stopPlan, othersRunning, lookBlockedReason,
    isRunning, stopEnabled, stop, conflictFor, stopAndWait, switchDetails, select, show, back,
  }
})
