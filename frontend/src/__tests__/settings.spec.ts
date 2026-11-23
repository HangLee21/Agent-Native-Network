import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import SettingsView from '@/views/SettingsView.vue'
import { resolveConfig, setConfigForTest } from '@/config/runtime'
import { safetyApi, type SafetyConfig } from '@/api/safety'
import { targetConfigApi, type TargetConfig } from '@/api/targets'
import { historyApi, type HistoryStatus } from '@/api/history'
import { useSafetyStore } from '@/stores/safety'
import { useTargetsStore } from '@/stores/targets'
import { useConfirmStore } from '@/stores/confirm'

const ZONE: [number, number][] = [[22.579, 113.939], [22.579, 113.942], [22.582, 113.942]]

function safetyConfig(over: Partial<SafetyConfig> = {}): SafetyConfig {
  return {
    maxHeight: 120, minHeight: 20, maxSpeed: 15, minTakeoffBattery: 25, safeZoneEnabled: true, safeZone: ZONE,
    unknownHeightPolicy: 'DUAL_CHECK', updatedAt: 1, ...over,
  }
}

function targetConfig(over: Partial<TargetConfig> = {}): TargetConfig {
  return {
    laserFlyToEnabled: false, laserAltitudeReference: 'UNKNOWN', geoidOffsetM: -4.5, minDistanceM: 10, stopDistanceM: 30, clearanceM: 10,
    maxLaserRangeM: 1200, maxAccuracyM: 5, approachSpeed: 5, aboveHeightM: 30, aiLookLevel: 0, aiApproachLevel: 0, aiAboveLevel: 0,
    aiOrbitLevel: 0, aiMinConfidence: 0.8, aiMaxMoveM: 100, aiStopDistanceM: 50, aiExtraHeightM: 10, aiMaxAccuracyM: 3, aiCooldownS: 10,
    aiMaxPerMinute: 4, aiCountdownS: 5, aiForbiddenMoveLabels: ['person', 'people'], aiAllowedMoveLabels: [], aiWorkArea: [], updatedAt: 1,
    ...over,
  }
}

function historyStatus(recordingEnabled: boolean): HistoryStatus {
  return {
    recorder: { enabled: true, paused: false, pausedMessage: null, queueSize: 0, droppedTotal: 0, pendingRows: 0, currentSessionId: null },
    video: { configured: true, recordingEnabled, diskLow: false, freeBytes: 182e9, minFreeBytes: 5e9, transcode: false, autoStartStream: true, recordQuality: 1 },
    sessions: 23,
    samples: 1000,
  }
}

let wrapper: VueWrapper | null = null

async function mountSettings(path = '/settings'): Promise<{ w: VueWrapper; router: Router }> {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/settings', component: SettingsView }] })
  await router.push(path)
  await router.isReady()
  wrapper = mount(SettingsView, { global: { plugins: [router] }, attachTo: document.body })
  await flushPromises()
  return { w: wrapper, router }
}

describe('settings page', () => {
  beforeAll(() => {
    globalThis.ResizeObserver ??= class {
      observe() {}
      disconnect() {}
    } as unknown as typeof ResizeObserver
  })

  beforeEach(() => {
    localStorage.clear()
    setConfigForTest(resolveConfig({}, 'http://x'))
    setActivePinia(createPinia())
    vi.spyOn(historyApi, 'status').mockResolvedValue(historyStatus(true))
  })

  afterEach(() => {
    wrapper?.unmount()
    wrapper = null
    vi.restoreAllMocks()
  })

  it('shows the save bar after changing the platform height limit and saves the full payload after confirming', async () => {
    const safety = useSafetyStore()
    safety.apply(safetyConfig())
    const ask = vi.spyOn(useConfirmStore(), 'ask').mockResolvedValue(true)
    const put = vi.spyOn(safetyApi, 'update').mockImplementation(async (c) => safetyConfig({ ...c, updatedAt: 2 }))
    const update = vi.spyOn(safety, 'update')
    const { w } = await mountSettings()

    expect(w.find('[data-test=save-bar]').exists()).toBe(false)
    await w.get('[data-test=max-height]').setValue(150)

    const bar = w.get('[data-test=save-bar]')
    expect(bar.text()).toContain('飞行安全有 1 项未保存')
    expect(bar.text()).toContain('平台限高')
    expect(w.get('[data-test=max-height]').classes()).toContain('changed')
    expect(w.get('[data-test=settings-nav-safety]').text()).toContain('1 项未保存')
    expect(w.get('[data-test=save-safety]').attributes('disabled')).toBeUndefined()

    await w.get('[data-test=save-safety]').trigger('click')
    await flushPromises()

    expect(ask).toHaveBeenCalledWith({
      title: '保存安全设置',
      message: '安全设置会立即作用于所有航线保存、同步与飞行指令。确认保存？',
      details: ['平台限高 150 m，最低高度 20 m（相对起飞点）', '最大速度 15 m/s，起飞最低电量 25%', '安全区：启用（3 个顶点）'],
    })
    const payload = {
      maxHeight: 150, minHeight: 20, maxSpeed: 15, minTakeoffBattery: 25, unknownHeightPolicy: 'DUAL_CHECK', safeZoneEnabled: true, safeZone: ZONE,
    }
    expect(update).toHaveBeenCalledTimes(1)
    expect(update).toHaveBeenCalledWith(payload)
    expect(put).toHaveBeenCalledWith(payload)
    // saved config came back: nothing left to save
    expect(w.find('[data-test=save-bar]').exists()).toBe(false)
  })

  it('does not save when the confirmation is cancelled, and undo restores the saved values', async () => {
    useSafetyStore().apply(safetyConfig())
    vi.spyOn(useConfirmStore(), 'ask').mockResolvedValue(false)
    const put = vi.spyOn(safetyApi, 'update')
    const { w } = await mountSettings()

    await w.get('[data-test=zone-enabled]').setValue(false)
    await w.get('[data-test=save-safety]').trigger('click')
    await flushPromises()
    expect(put).not.toHaveBeenCalled()
    expect(w.get('[data-test=save-bar]').text()).toContain('启用安全区')

    await w.get('[data-test=save-bar]').findAll('button')[0]!.trigger('click')
    expect(w.find('[data-test=save-bar]').exists()).toBe(false)
    expect((w.get('[data-test=zone-enabled]').element as HTMLInputElement).checked).toBe(true)
  })

  it('locks the laser fly-to switch while the laser height reference is unconfirmed', async () => {
    useTargetsStore().config = targetConfig()
    const { w } = await mountSettings('/settings?section=target')

    expect(w.find('[data-test=target-settings]').exists()).toBe(true)
    expect(w.get('[data-test=laser-flyto]').attributes('disabled')).toBeDefined()
    expect(w.find('[data-test=laser-flyto-locked]').exists()).toBe(true)

    const refs = w.findAll('[data-test=laser-reference] input[type=radio]')
    expect(refs).toHaveLength(3)
    expect((refs[0]!.element as HTMLInputElement).checked).toBe(true)
    await refs[1]!.setValue(true) // ELLIPSOID
    expect(w.get('[data-test=laser-flyto]').attributes('disabled')).toBeUndefined()
    expect(w.find('[data-test=laser-flyto-locked]').exists()).toBe(false)
    expect(w.get('[data-test=save-bar]').text()).toContain('目标选择与 AI 有 1 项未保存')
    expect(w.get('[data-test=save-target-settings]').attributes('disabled')).toBeUndefined()
  })

  it('saves the target settings in one request with comma-joined labels after confirming', async () => {
    useTargetsStore().config = targetConfig({ laserAltitudeReference: 'ELLIPSOID' })
    const ask = vi.spyOn(useConfirmStore(), 'ask').mockResolvedValue(true)
    const put = vi.spyOn(targetConfigApi, 'updateConfig').mockImplementation(async () => targetConfig({ laserAltitudeReference: 'ELLIPSOID', aiApproachLevel: 2, updatedAt: 2 }))
    const { w } = await mountSettings('/settings?section=target')

    const approach = w.findAll('[aria-labelledby=settings-aiApproachLevel] input[type=radio]')
    await approach[1]!.setValue(true)
    await w.get('[data-test=save-target-settings]').trigger('click')
    await flushPromises()

    expect(ask).toHaveBeenCalledWith(expect.objectContaining({ title: '保存目标选择设置', message: '设置会立即作用于目标动作与 AI 自动模式。确认保存？' }))
    expect(put).toHaveBeenCalledTimes(1)
    const body = put.mock.calls[0]![0]
    expect(body.aiApproachLevel).toBe(2)
    expect(body.aiForbiddenMoveLabels).toBe('person,people')
    expect(body.aiAllowedMoveLabels).toBe('')
    expect(body.aiWorkArea).toEqual([])
    expect(body).not.toHaveProperty('updatedAt')
    expect(w.find('[data-test=save-bar]').exists()).toBe(false)
  })

  it('switches sections through the navigation and remembers the choice', async () => {
    useSafetyStore().apply(safetyConfig())
    const { w, router } = await mountSettings()
    expect(w.find('[data-test=max-height]').exists()).toBe(true)

    await w.get('[data-test=settings-nav-system]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query.section).toBe('system')
    expect(w.find('[data-test=max-height]').exists()).toBe(false)
    expect(w.text()).toContain('/api/v1/external/targets')
    expect(localStorage.getItem('uav.settings.section')).toBe('system')
  })

  it('keeps unsaved edits when switching sections', async () => {
    useSafetyStore().apply(safetyConfig())
    const { w } = await mountSettings()
    await w.get('[data-test=max-height]').setValue(90)
    await w.get('[data-test=settings-nav-history]').trigger('click')
    await flushPromises()
    expect(w.get('[data-test=settings-nav-safety]').text()).toContain('1 项未保存')
    await w.get('[data-test=settings-nav-safety]').trigger('click')
    await flushPromises()
    expect((w.get('[data-test=max-height]').element as HTMLInputElement).value).toBe('90')
  })

  it('saves the video recording switch immediately and reloads the status', async () => {
    const status = vi.mocked(historyApi.status)
    const put = vi.spyOn(historyApi, 'updateSettings').mockResolvedValue({ videoRecording: false, videoConfigured: true })
    const { w } = await mountSettings('/settings?section=history')
    expect(status).toHaveBeenCalledTimes(1)
    expect(w.get('[data-test=settings-nav-history]').text()).toContain('录像开')
    expect(w.get('[data-test=history-settings]').text()).toContain('切换后立即保存，下次起飞生效')

    status.mockResolvedValue(historyStatus(false))
    await w.get('[data-test=video-recording-toggle]').setValue(false)
    await flushPromises()
    expect(put).toHaveBeenCalledWith(false)
    expect(status).toHaveBeenCalledTimes(2)
    expect(w.get('[data-test=settings-nav-history]').text()).toContain('录像关')
  })
})
