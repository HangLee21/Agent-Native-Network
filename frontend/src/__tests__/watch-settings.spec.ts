import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import WatchSettingsCard from '@/components/settings/WatchSettingsCard.vue'
import { useWatchSettings } from '@/components/settings/useWatchSettings'
import { watchApi, type WatchSettings } from '@/api/watch'
import { useFleetStore } from '@/stores/fleet'
import type { DeviceView } from '@/api/drones'

const dev = (gatewaySn: string, label: string): DeviceView => ({ droneSn: `D-${gatewaySn}`, gatewaySn, label, color: '#4a90e8', online: true, droneOnline: true, enabled: true, model: 'M4E', firstSeenAt: 1, lastSeenAt: 1, simulated: true })

describe('演示与监视台 settings', () => {
  let saved: Partial<WatchSettings>[]
  beforeEach(() => {
    setActivePinia(createPinia())
    saved = []
    let cur: WatchSettings = { hideRoute: true, videoOrder: [] }
    vi.spyOn(watchApi, 'settings').mockImplementation(async () => cur)
    vi.spyOn(watchApi, 'updateSettings').mockImplementation(async (p) => { saved.push(p); cur = { ...cur, ...p }; return cur })
    useFleetStore().drones = [dev('RC1', 'A'), dev('RC2', 'B')]
  })
  afterEach(() => vi.restoreAllMocks())

  async function mountCard() {
    let model!: ReturnType<typeof useWatchSettings>
    const w = mount({ components: { WatchSettingsCard }, setup() { model = useWatchSettings(); return { model } }, template: '<WatchSettingsCard :model="model" />' })
    await flushPromises()
    return { w, model }
  }

  it('the route is hidden by default and switching it off saves at once', async () => {
    const { w } = await mountCard()
    const box = w.get('[data-test="watch-hide-route"]')
    expect((box.element as HTMLInputElement).checked).toBe(true)
    await box.setValue(false)
    await flushPromises()
    expect(saved).toEqual([{ hideRoute: false }])
  })

  it('moving a drone saves the whole video order', async () => {
    const { w } = await mountCard()
    const rows = w.get('[data-test="watch-video-order"]').findAll('li')
    expect(rows.map((r) => r.find('b').text())).toEqual(['A', 'B'])
    await rows[1]!.findAll('button')[0]!.trigger('click') // B 往前
    await flushPromises()
    expect(saved).toEqual([{ videoOrder: ['RC2', 'RC1'] }])
    expect(w.get('[data-test="watch-video-order"]').findAll('li b').map((b) => b.text())).toEqual(['B', 'A'])
  })
})
