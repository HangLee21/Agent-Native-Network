import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import NetworkView from '@/views/NetworkView.vue'
import { useNetworkStore } from '@/stores/network'
// @ts-expect-error plain JavaScript fixture
import { makeSnapshot } from '../../../scripts/network-studio/mock.mjs'
let wrapper: VueWrapper | undefined
let network: ReturnType<typeof useNetworkStore>
const mountView = () => mount(NetworkView, { props: { workspace: network.workspace } })
beforeEach(() => {
  setActivePinia(createPinia()); localStorage.clear(); network = useNetworkStore()
  vi.spyOn(network, 'start').mockResolvedValue()
  vi.spyOn(network, 'stop').mockImplementation(() => undefined)
  network.workspace = 'mock'; network.snapshot = makeSnapshot(); network.receivedAt = Date.now(); network.status = 'online'
})
afterEach(() => { wrapper?.unmount(); wrapper = undefined; vi.restoreAllMocks() })

describe('shared platform and standalone network view', () => {
  it('always marks synthetic evidence and separates the receiver from reporting members', () => {
    wrapper = mountView()
    expect(wrapper.find('[data-test="network-synthetic"]').text()).toContain('模拟数据')
    expect(wrapper.findAll('[data-list-node]')).toHaveLength(6)
    expect(wrapper.find('.metrics').text()).toContain('不含接收网关')
  })
  it('selects and searches by MAC without relabeling node identities', async () => {
    wrapper = mountView()
    await wrapper.find('[data-list-node="02:00:00:01:00:02"]').trigger('click')
    expect(wrapper.find('.inspector h3').text()).toBe('NODE 02')
    await wrapper.find('input[type="search"]').setValue('01:00:02')
    expect(wrapper.findAll('[data-list-node]')).toHaveLength(1)
  })
  it('retains members and shows no geographic markers when GPS is unavailable', async () => {
    network.snapshot = makeSnapshot({ scenario: 'no-gps' }); wrapper = mountView()
    const button = wrapper.findAll('.segmented button').find(b => b.text().includes('GPS 布局'))!
    await button.trigger('click')
    expect(wrapper.text()).toContain('没有可用的 GPS 位置')
    expect(wrapper.findAll('[data-node]')).toHaveLength(0)
    expect(wrapper.findAll('[data-list-node]')).toHaveLength(6)
  })
  it('does not fabricate an empty graph or fake data on an unavailable backend', () => {
    network.workspace = 'real'; network.snapshot = null; network.status = 'error'; network.error = 'NETWORK_HTTP_503'
    wrapper = mountView()
    expect(wrapper.find('[role="alert"]').text()).toContain('不会自动切换到模拟数据')
    expect(wrapper.findAll('[data-list-node]')).toHaveLength(0)
    expect(wrapper.find('[data-test="network-synthetic"]').exists()).toBe(false)
  })
  it('shows explicit disabled production state with no prefilled graph', () => {
    network.workspace = 'real'; network.snapshot = null; network.status = 'disabled'; wrapper = mountView()
    expect(wrapper.text()).toContain('网络数据服务尚未启用')
    expect(wrapper.find('.connection-state').classes()).toContain('neutral')
    expect(wrapper.findAll('[data-node]')).toHaveLength(0)
  })
  it('defaults to GPS with a visible layout summary, north arrow and scale', () => {
    wrapper = mountView()
    expect(wrapper.find('.segmented button').text()).toContain('GPS 布局')
    expect(wrapper.find('.segmented button').attributes('aria-pressed')).toBe('true')
    expect(wrapper.find('[data-test="gps-summary"]').text()).toContain('5 / 6 GPS')
    expect(wrapper.find('[data-test="gps-map-guide"]').exists()).toBe(true)
    expect(wrapper.findAll('[data-node]')).toHaveLength(5)
  })
  it('lets an operator tag a NODE without changing its name, identity or flight binding', async () => {
    wrapper = mountView(); await wrapper.find('[data-list-node="02:00:00:01:00:02"]').trigger('click')
    expect(wrapper.find('#network-node-tag').element).toBeInstanceOf(HTMLSelectElement)
    expect((wrapper.find('#network-node-tag').element as HTMLSelectElement).value).toBe('node')
    await wrapper.find('#network-node-tag').setValue('robot')
    expect(wrapper.find('.inspector h3').text()).toBe('NODE 02')
    expect(wrapper.find('[data-list-node="02:00:00:01:00:02"]').text()).toContain('标签：机器人')
    expect(network.snapshot!.nodes[2]!.binding).toBeNull()
  })
  it('has only server and gateway choices in the real workspace', () => {
    network.workspace = 'real'; network.snapshot = null; network.status = 'disabled'; wrapper = mountView()
    expect(wrapper.findAll('.connection-modes button').map(b => b.text())).toEqual(['服务器', '本地网关'])
    expect(wrapper.find('[data-test="network-synthetic"]').exists()).toBe(false)
    expect(wrapper.find('#network-scenario').exists()).toBe(false)
    expect(wrapper.text()).toContain('未连接，不显示模拟数据')
  })
  it('describes a blocked mock service explicitly rather than presenting it as a connection', () => {
    network.workspace = 'real'; network.snapshot = null; network.status = 'error'; network.error = 'NETWORK_SYNTHETIC_REJECTED'
    wrapper = mountView()
    expect(wrapper.find('[role="alert"]').text()).toContain('已阻止模拟数据进入真实工作区')
    expect(wrapper.findAll('[data-list-node]')).toHaveLength(0)
  })
  it('keeps the mock banner even when the demo backend has not returned any snapshot', () => {
    network.snapshot = null; network.status = 'error'; wrapper = mountView()
    expect(wrapper.find('[data-test="network-synthetic"]').text()).toContain('MOCK')
    expect(wrapper.find('[data-test="real-connection"]').exists()).toBe(false)
  })
})
