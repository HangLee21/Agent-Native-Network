/**
 * Stop and soft e-stop of a dog, shared by the pad, the side panel and the safety area (ui-design.md 9.2).
 * S10 "stop" stops the one thing that is running and can be stopped; long actions the board cannot cancel
 * (posture, gait, map operations, photo, recognition) are left to finish, and the operator is told so. The dog's
 * state is read every few seconds, so a navigation this platform started in the last 15 s counts as running even
 * before the state shows it. Every stop counts up `stopSeq`, which multi-step sequences check before going on.
 */
import { useDogStore, navActive } from '@/stores/dog'
import { useConfirmStore } from '@/stores/confirm'
import type { DogId } from '@/api/dog'
import { jobLabel, jobLabelZh, s10RunningJob } from './dogFlow'
import { waitCommand } from './waitCommand'
import { t, tb } from '@/i18n'

export function useDogActions() {
  const store = useDogStore()
  const confirm = useConfirmStore()

  /** A navigation sent from this platform recently that has not been seen to end. */
  function recentNavigation(): boolean {
    const now = store.serverNow()
    return store.commands.s10.some((c) => c.action === 'navigate' && now - c.createdAt < 15000 && ['sent', 'running', 'navstart'].includes(c.state))
  }

  /** Sends an S10 stop and puts its answer in the dog's note (seen in the safety row too, whatever is selected). */
  async function sendS10Stop(body: Record<string, unknown>): Promise<void> {
    const label = String(body.label)
    const c = await store.s10Action(body)
    if (!c) return
    const done = c.state === 'sent' || c.state === 'running' ? await waitCommand(c.id, 15000) : c
    if (!done || done.state === 'sent' || done.state === 'running') return
    if (['failed', 'notdone', 'lost', 'noreply', 'unknown'].includes(done.state)) store.note('s10', 'bad', t('{label}：{why}', { label: tb(label), why: done.error ?? done.detail ?? done.state }))
    else store.note('s10', 'ok', t('{label}：狗已回复', { label: tb(label) }))
  }

  async function stop(dog: DogId): Promise<void> {
    store.stopSeq++
    if (dog === 'lite3') {
      await store.l3Stop(false)
      return
    }
    if (store.s10Hold) {
      await store.s10HoldEnd('停止')   // i18n-ignore: sent to the backend, shown via tb()
      return
    }
    if (store.armHold) {
      await store.armHoldEnd('停止')   // i18n-ignore: sent to the backend, shown via tb()
      return
    }
    const s = store.s10
    const job = s10RunningJob(s)
    if (job && job.action === 'navigate') {
      await sendS10Stop({ action: 'nav_cancel', label: '停止 → 取消导航' })   // i18n-ignore: sent to the backend, shown via tb()
    } else if (job && job.stoppable) {
      await sendS10Stop({ action: 'arm_stop', label: `停止 → 停止机械臂动作（${jobLabelZh(job)}）` })   // i18n-ignore: sent to the backend, shown via tb()
    } else if (job) {
      store.note('s10', 'bad', t('「{job}」不能中途取消：等它结束；紧急时长按软急停', { job: jobLabel(job) }))
    } else if (navActive(s?.nav) || recentNavigation()) {
      await sendS10Stop({ action: 'nav_cancel', label: '停止 → 取消导航' })   // i18n-ignore: sent to the backend, shown via tb()
    } else {
      // nothing running: end any hold and stop arm interpolation, both harmless
      await sendS10Stop({ action: 'arm_stop', label: '停止 → 停止机械臂动作' })   // i18n-ignore: sent to the backend, shown via tb()
    }
  }

  /** Soft e-stop (after the 0.8 s press): S10 via the synchronous stop action (damping), Lite3 stop + soft e-stop. */
  async function softEstop(dog: DogId): Promise<void> {
    store.stopSeq++
    if (dog === 'lite3') {
      await store.l3Stop(true)
      return
    }
    if (store.s10Hold) void store.s10HoldEnd('软急停')   // i18n-ignore: sent to the backend, shown via tb()
    if (store.armHold) void store.armHoldEnd('软急停')   // i18n-ignore: sent to the backend, shown via tb()
    await sendS10Stop({ action: 'stop', label: '软急停（阻尼）' })   // i18n-ignore: sent to the backend, shown via tb()
  }

  /** Sends an S10 action, after a confirmation when `ask` is given. */
  async function s10(body: Record<string, unknown>, ask?: { title: string; message: string; danger?: boolean; details?: string[]; confirmText?: string }): Promise<boolean> {
    if (ask) {
      const ok = await confirm.ask({ ...ask, focus: ask.danger ? 'cancel' : 'confirm' })
      if (!ok) return false
    }
    const c = await store.s10Action(body)
    return !!c
  }

  return { stop, softEstop, s10 }
}
