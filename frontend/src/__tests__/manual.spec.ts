import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'
import { manualSocketFor, manualUrl } from '@/services/manualSocket'
import { TEST_DRONE, useTestDrone } from './testDrone'

const manualSocket = manualSocketFor(TEST_DRONE)
import StickControlOverlay from '@/components/control/StickControlOverlay.vue'
import GimbalPad from '@/components/control/GimbalPad.vue'
import { useManualStore } from '@/stores/manual'

describe('stick control and gimbal hold (D-16)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    useTestDrone()
    vi.useFakeTimers()
    vi.spyOn(manualSocket, 'ensure').mockImplementation(() => {})
  })
  afterEach(() => vi.restoreAllMocks())

  it('derives the input socket from the telemetry socket address', () => {
    expect(manualUrl('ws://192.0.2.1:8080/ws/telemetry')).toBe('ws://192.0.2.1:8080/ws/manual')
    expect(manualUrl('wss://example.org/ws/telemetry')).toBe('wss://example.org/ws/manual')
    // one socket per drone (D-29)
    expect(manualUrl('ws://192.0.2.1:8080/ws/telemetry', 'RC 1')).toBe('ws://192.0.2.1:8080/ws/manual?droneSn=RC%201')
  })

  it('maps the keyboard to the four channels and streams at 10 Hz', async () => {
    const stick = vi.spyOn(manualSocket, 'stick').mockImplementation(() => {})
    useManualStore().snapshot = { active: true, exiting: false, scale: 0.3, maxScale: 0.5, message: '', heightClamped: false,
      zoneBlocked: false, gimbalMoving: false, log: [] }
    const w = mount(StickControlOverlay, { attachTo: document.body })
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'w' }))
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowLeft' }))
    vi.advanceTimersByTime(100)
    expect(stick).toHaveBeenLastCalledWith(0, 1, 0, -1)
    window.dispatchEvent(new KeyboardEvent('keyup', { key: 'w' }))
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'd' }))
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowUp' }))
    vi.advanceTimersByTime(100)
    expect(stick).toHaveBeenLastCalledWith(1, 0, 1, -1)
    const before = stick.mock.calls.length
    vi.advanceTimersByTime(500)
    expect(stick.mock.calls.length - before).toBe(5) // 10 Hz
    w.unmount()
  })

  it('returns to neutral when the window loses focus or space is pressed', async () => {
    const stick = vi.spyOn(manualSocket, 'stick').mockImplementation(() => {})
    const w = mount(StickControlOverlay, { attachTo: document.body })
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'w' }))
    vi.advanceTimersByTime(100)
    expect(stick).toHaveBeenLastCalledWith(0, 1, 0, 0)
    window.dispatchEvent(new Event('blur'))
    vi.advanceTimersByTime(100)
    expect(stick).toHaveBeenLastCalledWith(0, 0, 0, 0)
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 's' }))
    window.dispatchEvent(new KeyboardEvent('keydown', { key: ' ' }))
    vi.advanceTimersByTime(100)
    expect(stick).toHaveBeenLastCalledWith(0, 0, 0, 0)
    w.unmount()
    expect(stick).toHaveBeenLastCalledWith(0, 0, 0, 0) // a final neutral frame on close
  })

  it('streams gimbal speeds while a direction is held and stops on release', async () => {
    const gimbal = vi.spyOn(manualSocket, 'gimbal').mockImplementation(() => {})
    window.localStorage.clear()
    const w = mount(GimbalPad)
    await w.get('[data-test=gimbal-left]').trigger('pointerdown')
    expect(gimbal).toHaveBeenLastCalledWith(0, -0.436) // default 中 = 25°/s
    vi.advanceTimersByTime(600)
    expect(gimbal.mock.calls.length).toBeGreaterThanOrEqual(4) // 5 Hz while held
    await w.get('[data-test=gimbal-left]').trigger('pointerup')
    expect(gimbal).toHaveBeenLastCalledWith(0, 0)
    const n = gimbal.mock.calls.length
    vi.advanceTimersByTime(600)
    expect(gimbal.mock.calls.length).toBe(n)
    await w.get('[data-test=gimbal-yaw-center]').trigger('click')
    expect(w.emitted('reset')?.[0]).toEqual([2])
  })

  it('turns at the chosen speed, remembers it, and slows down when zoomed in', async () => {
    const gimbal = vi.spyOn(manualSocket, 'gimbal').mockImplementation(() => {})
    window.localStorage.clear()
    const w = mount(GimbalPad, { props: { pad: true } })
    await w.get('[data-test=gimbal-speed-fast]').trigger('click')
    await w.get('[data-test=gimbal-up]').trigger('pointerdown')
    expect(gimbal).toHaveBeenLastCalledWith(0.873, 0) // 50°/s
    await w.get('[data-test=gimbal-up]').trigger('pointerup')
    expect(window.localStorage.getItem('uav.gimbalSpeed')).toBe('fast')
    w.unmount()

    // a new pad (next visit) starts at the remembered speed; at 10× zoom it turns at 2/10 of it
    const z = mount(GimbalPad, { props: { pad: true, zoom: 10 } })
    expect(z.get('[data-test=gimbal-rate]').text()).toContain('约 10°/s')
    await z.get('[data-test=gimbal-right]').trigger('pointerdown')
    expect(gimbal).toHaveBeenLastCalledWith(0, 0.175)
    await z.get('[data-test=gimbal-right]').trigger('pointerup')
    z.unmount()
  })

  it('does nothing while disabled (no DRC)', async () => {
    const gimbal = vi.spyOn(manualSocket, 'gimbal').mockImplementation(() => {})
    const w = mount(GimbalPad, { props: { disabled: true } })
    await w.get('[data-test=gimbal-up]').trigger('pointerdown')
    expect(gimbal).not.toHaveBeenCalled()
  })
})
