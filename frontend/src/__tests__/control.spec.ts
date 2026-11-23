import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'
import { useControlStore } from '@/stores/control'
import CommandStatus from '@/components/control/CommandStatus.vue'
import HoldButton from '@/components/control/HoldButton.vue'
import { ApiError } from '@/api/http'
import type { CommandRecord } from '@/api/control'

function rec(status: CommandRecord['status'], over: Partial<CommandRecord> = {}): CommandRecord {
  return { id: 'c1', type: 'ReturnHome', label: '一键返航', channel: 'SERVICES', status, createdAt: 1, sentAt: 1,
    completedAt: null, resultCode: null, message: null, ...over }
}

describe('command reliability UI (S-03)', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('never shows success until the device confirms', () => {
    const sent = mount(CommandStatus, { props: { record: rec('SENT') } })
    expect(sent.text()).toContain('已发送，等待设备确认')
    expect(sent.text()).not.toContain('设备已确认')
    const acked = mount(CommandStatus, { props: { record: rec('ACKED') } })
    expect(acked.text()).toContain('设备已确认')
    const failed = mount(CommandStatus, { props: { record: rec('FAILED', { message: '操作失败，无飞行器控制权（319030）' }) } })
    expect(failed.text()).toContain('失败：操作失败，无飞行器控制权')
    const timeout = mount(CommandStatus, { props: { record: rec('TIMEOUT', { message: '超时：设备未在 10 秒内确认' }) } })
    expect(timeout.attributes('data-status')).toBe('TIMEOUT')
    expect(timeout.text()).toContain('超时')
  })

  it('updates the record shown under a button when the backend pushes a receipt', async () => {
    const s = useControlStore()
    await s.run('rth', '一键返航', async () => rec('SENT'))
    expect(s.byAction('rth')?.status).toBe('SENT')
    s.upsert(rec('ACKED'))
    expect(s.byAction('rth')?.status).toBe('ACKED')
    s.upsert(rec('PENDING')) // stale REST reply arriving after the WebSocket receipt
    expect(s.byAction('rth')?.status).toBe('ACKED')
  })

  it('turns API rejections (safety 422 / precondition 409) into a visible rejected record', async () => {
    const s = useControlStore()
    await s.run('estop', '急停', () => Promise.reject(new ApiError('DRC 链路未连接，无法执行「急停」', 409)))
    expect(s.byAction('estop')?.status).toBe('REJECTED')
    expect(s.byAction('estop')?.message).toContain('DRC')
    await s.run('takeoff', '一键起飞', () =>
      Promise.reject(new ApiError('安全检查未通过', 422, { passed: false, violations: [{ code: 'ABOVE_HEIGHT_LIMIT', message: '高度 500 m 超过平台限高 120 m', waypointIndex: null }] })))
    expect(s.byAction('takeoff')?.message).toContain('超过平台限高')
  })

  it('emergency stop requires a sustained press', async () => {
    vi.useFakeTimers()
    let t = 0
    vi.stubGlobal('performance', { now: () => t })
    const frames: FrameRequestCallback[] = []
    vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => (frames.push(cb), frames.length))
    vi.stubGlobal('cancelAnimationFrame', () => (frames.length = 0))
    const w = mount(HoldButton, { props: { holdMs: 800 } })
    await w.trigger('pointerdown')
    t = 300
    frames.shift()?.(t)
    await w.trigger('pointerup')
    expect(w.emitted('trigger')).toBeUndefined()
    await w.trigger('pointerdown')
    t = 1200
    frames.shift()?.(t)
    expect(w.emitted('trigger')).toHaveLength(1)
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })
})

describe('dangerous landings (DangerZone)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
  })

  async function openZone(enabled = true) {
    const { default: DangerZone } = await import('@/components/control/DangerZone.vue')
    const w = mount(DangerZone, { props: { enabled } })
    await w.get('[data-test=danger-toggle]').trigger('click')
    return w
  }

  it('is collapsed by default and keeps the landing buttons locked until unlocked', async () => {
    const { default: DangerZone } = await import('@/components/control/DangerZone.vue')
    const closed = mount(DangerZone, { props: { enabled: true } })
    expect(closed.find('[data-test=emergency-landing]').exists()).toBe(false)
    const w = await openZone()
    expect(w.get('[data-test=emergency-landing]').attributes('disabled')).toBeDefined()
    expect(w.get('[data-test=force-landing]').attributes('disabled')).toBeDefined()
    await w.get('[data-test=danger-unlock]').trigger('click')
    expect(w.get('[data-test=emergency-landing]').attributes('disabled')).toBeUndefined()
    vi.advanceTimersByTime(30_000)
    await w.vm.$nextTick()
    expect(w.get('[data-test=emergency-landing]').attributes('disabled')).toBeDefined()
  })

  it('cannot be unlocked without DRC and flight', async () => {
    const w = await openZone(false)
    expect(w.get('[data-test=danger-unlock]').attributes('disabled')).toBeDefined()
    expect(w.get('[data-test=force-landing]').attributes('disabled')).toBeDefined()
  })

  it('still asks for confirmation and re-locks after the dialog', async () => {
    const { useConfirmStore } = await import('@/stores/confirm')
    const ask = vi.spyOn(useConfirmStore(), 'ask').mockResolvedValue(false)
    const w = await openZone()
    await w.get('[data-test=danger-unlock]').trigger('click')
    await w.get('[data-test=emergency-landing]').trigger('click')
    await vi.runOnlyPendingTimersAsync()
    expect(ask).toHaveBeenCalledWith(expect.objectContaining({ title: '紧急降落', danger: true, focus: 'cancel' }))
    expect(w.get('[data-test=emergency-landing]').attributes('disabled')).toBeDefined()
    expect(useControlStore().byAction('landing')).toBeFalsy()
  })
})
