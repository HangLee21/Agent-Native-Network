import { computed } from 'vue'
import { useControlStore } from '@/stores/control'
import { useExecutionStore } from '@/stores/execution'
import { useFleetStore } from '@/stores/fleet'
import { useTasksStore } from '@/stores/tasks'
import { useTelemetryStore } from '@/stores/telemetry'
import { t, tc } from '@/i18n'

/** The step name "control", not the status 控制权 = "In control". */
const CONTROL_STEP = tc('phase', '控制权')

export const PHASES = [t('连接'), CONTROL_STEP, tc('phase', '起飞'), t('任务'), tc('phase', '返航')] as const

/** An acknowledged emergency stop counts as "recent" for this long, while nothing moves the aircraft. */
const ESTOP_RECENT_MS = 120_000

export interface PhaseStep {
  label: string
  done: boolean
  cur: boolean
  warn: boolean
}

/**
 * One drone's flight phase (连接 → 控制权 → 起飞 → 任务 → 返航) and the one-line "what next" hint under the phase
 * bar (ui-design.md §2.2). Display only: everything is derived from state the stores already hold.
 */
export function useFlightPhase(sn: string) {
  const tel = useTelemetryStore(sn)
  const control = useControlStore(sn)
  const execution = useExecutionStore(sn)
  const tasks = useTasksStore(sn)
  const fleet = useFleetStore()

  const state = computed(() => control.snapshot?.control ?? 'NONE')
  const mode = computed(() => tel.drone?.modeCode)
  const landing = computed(() => mode.value === 10 || mode.value === 11 || mode.value === 12)
  const paused = computed(() => execution.current?.active && execution.current.state === 'PAUSED' ? execution.current : null)
  const recentEstop = computed(() => {
    const r = control.byAction('estop')
    return !!r && r.status === 'ACKED' && tel.airborne && !tasks.motion && tel.now - (r.completedAt ?? r.createdAt) < ESTOP_RECENT_MS
  })

  /** 0 连接 · 1 控制权 · 2 起飞 · 3 任务 · 4 返航 */
  const at = computed(() => {
    if (!tel.online) return 0
    if (!tel.airborne) return state.value === 'GRANTED' && control.drcReady ? 2 : 1
    if (mode.value === 4) return 2
    if (mode.value === 9 || landing.value) return 4
    return 3
  })

  const warn = computed(() =>
    (at.value === 0 && tel.lastUpdateAt > 0) || state.value === 'LOST' || state.value === 'DENIED' || !!paused.value || recentEstop.value
    || (tel.airborne && state.value === 'GRANTED' && !control.drcReady))

  function currentLabel(i: number): string {
    switch (i) {
      case 0: return tel.lastUpdateAt > 0 ? t('连接中断') : t('未连接')
      case 1:
        if (state.value === 'REQUESTING') return t('等待同意')
        if (state.value === 'DENIED') return t('授权被拒')
        if (state.value === 'LOST') return t('失去控制权')
        if (state.value === 'GRANTED') return control.snapshot?.drcState === 1 ? t('DRC 连接中') : t('DRC 未连接')
        return CONTROL_STEP
      case 2: return mode.value === 4 ? t('起飞中') : t('可起飞')
      case 3: {
        const e = execution.current
        if (e?.active) return e.state === 'PAUSED' ? t('航线暂停') : t('航线 {n}/{total}', { n: e.reachedCount, total: e.total })
        if (tasks.motion && tasks.motion !== 'rth') return tasks.motionName
        return recentEstop.value ? t('急停悬停') : t('悬停')
      }
      default: return landing.value ? t('降落中') : t('返航中')
    }
  }

  const steps = computed<PhaseStep[]>(() =>
    PHASES.map((label, i) => ({ label: i === at.value ? currentLabel(i) : label, done: i < at.value, cur: i === at.value, warn: i === at.value && warn.value })))

  /** What the operator should do next; null while a task runs normally. */
  const hint = computed<{ text: string; warn?: boolean } | null>(() => {
    const many = fleet.drones.length > 1
    const name = fleet.label(sn)
    if (!tel.online) return { text: tel.lastUpdateAt > 0 ? t('与飞机的连接中断：检查遥控器和图传') : t('设备未连接：等待遥控器接入'), warn: true }
    if (state.value === 'REQUESTING') return { text: t('等飞手在遥控器上点“同意”…') }
    if (state.value === 'DENIED') return { text: t('飞手拒绝了授权：需要时重新申请控制权'), warn: true }
    if (state.value === 'LOST') return { text: t('飞手已在遥控器上收回控制权：需要时重新申请'), warn: true }
    if (!tel.airborne) {
      if (state.value !== 'GRANTED') return { text: t('下一步：申请控制权（起飞或执行航线时平台也会自动申请）') }
      if (!control.drcReady) return { text: t('下一步：进入 DRC（急停、相机需要 DRC）') }
      return { text: many ? t('下一步：执行航线，或按下方 {name} 的「起飞」', { name }) : t('下一步：执行航线，或按下方「起飞」') }
    }
    if (state.value === 'GRANTED' && !control.drcReady) return { text: t('DRC 未连接：急停不可用，先点上方「进入 DRC」'), warn: true }
    if (mode.value === 4) return { text: execution.active ? t('起飞中：到达起飞高度后开始航线') : t('起飞中：到达起飞高度后悬停') }
    if (mode.value === 9) return { text: many ? t('返航中：到达 Home 后自动降落；要取消就按下方 {name} 的「取消返航」', { name }) : t('返航中：到达 Home 后自动降落；要取消就按下方「取消返航」') }
    if (landing.value) return { text: t('降落中') }
    if (paused.value) {
      if (paused.value.pauseReason === 'PROXIMITY') {
        return { text: many ? t('航线暂停（两机靠近）：拉开距离后按「继续 {name} 的航线」', { name }) : t('航线暂停（两机靠近）：拉开距离后按「继续航线」'), warn: true }
      }
      if (paused.value.pauseReason === 'WAYPOINT_CONFIRM') {
        const n = paused.value.reachedCount
        return { text: many ? t('到达航点 {n}，等你确认：按「确认，继续 {name} 的航线」飞下一段', { n, name }) : t('到达航点 {n}，等你确认：按「确认，继续航线」飞下一段', { n }), warn: true }
      }
      return { text: t('航线已暂停：按「继续航线」恢复'), warn: true }
    }
    if (state.value !== 'GRANTED') return { text: t('没有云端控制权：要下发任务先申请控制权'), warn: true }
    if (!tasks.motion) return recentEstop.value ? { text: t('急停后悬停：选一个任务，或返航'), warn: true } : { text: t('悬停中：在下面选一个任务') }
    return null
  })

  return { at, steps, warn, hint, paused }
}
