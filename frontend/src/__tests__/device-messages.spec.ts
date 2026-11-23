import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'
import DeviceMessages from '@/components/drone/DeviceMessages.vue'
import { useDeviceMessagesStore } from '@/stores/deviceMessages'
import { useToastStore } from '@/stores/toast'
import { telemetrySocket } from '@/services/ws'
import { TEST_DRONE, useTestDrone } from './testDrone'

describe('device messages (D-18)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    useTestDrone()
  })

  it('shows pushed messages newest first, warns with a toast and shows obstacle distances', async () => {
    const store = useDeviceMessagesStore()
    vi.spyOn(store, 'load').mockResolvedValue()
    store.start()
    const toast = vi.spyOn(useToastStore(), 'push')
    const w = mount(DeviceMessages)
    expect(w.text()).toContain('暂无设备消息')
    expect(w.text()).toContain('需 DRC 连接后才有数据')
    telemetrySocket.dispatch({ type: 'deviceMessage', ts: 1, gatewaySn: TEST_DRONE, data: { id: 'a', ts: Date.now(), level: 'INFO', source: 'x', title: '设备消息（未解析）', text: 'events / foo', raw: {} } })
    telemetrySocket.dispatch({ type: 'deviceMessage', ts: 2, gatewaySn: TEST_DRONE, data: { id: 'b', ts: Date.now(), level: 'WARNING', source: 'hsi_info_push', title: '障碍物接近', text: '水平方向 3.2 m', raw: {} } })
    telemetrySocket.dispatch({ type: 'obstacle', ts: 3, gatewaySn: TEST_DRONE, data: { horizontal: 3.2, up: 60, down: 30, around: [3.2], working: {}, near: true, ts: Date.now() } })
    await w.vm.$nextTick()
    const items = w.findAll('li[data-level]')
    expect(items[0]!.text()).toContain('障碍物接近')
    expect(items[0]!.attributes('data-level')).toBe('WARNING')
    expect(w.get('[data-test=obstacles]').classes()).toContain('near')
    expect(w.get('[data-test=obstacles]').text()).toContain('3.2 m')
    expect(toast).toHaveBeenCalledTimes(1) // INFO messages do not toast
    expect(toast).toHaveBeenCalledWith('warn', expect.stringContaining('障碍物接近'), 6000)
  })
})
