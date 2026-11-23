import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { dog2Api, type Dog2Video as VideoStatus } from '@/api/dogv2'
import { ApiError } from '@/api/http'
import { playWhep } from '@/api/live'
import Dog2Video from '@/components/dogv2/Dog2Video.vue'

vi.mock('@/api/dogv2', () => ({ dog2Api: { video: vi.fn() } }))
vi.mock('@/api/live', () => ({ playWhep: vi.fn() }))

const video: VideoStatus = { path: 'dog/lite3-01-rgb', state: 'live', whep: '/dog/lite3-01-rgb/whep' }
const props = { dog: 'lite3-01', stream: 'rgb' }

function fakeConnection() {
  return { close: vi.fn(), connectionState: 'connected' } as unknown as RTCPeerConnection
}

describe('dog live video', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval'] })
    vi.mocked(dog2Api.video).mockResolvedValue(video)
    vi.mocked(playWhep).mockReset()
  })

  afterEach(() => vi.useRealTimers())

  it('waits for the real publisher and reconnects after it disappears', async () => {
    const first = fakeConnection()
    vi.mocked(playWhep).mockResolvedValueOnce(first).mockResolvedValueOnce(fakeConnection())
    const wrapper = mount(Dog2Video, { props: { ...props, video: { ...video, ready: false } } })
    try {
      await flushPromises()
      expect(playWhep).not.toHaveBeenCalled()
      expect(wrapper.text()).toContain('正在等待狗的视频')
      await wrapper.setProps({ video: { ...video, ready: true } })
      await flushPromises()
      await wrapper.get('video').trigger('playing')
      expect(wrapper.find('.hint').exists()).toBe(false)

      await wrapper.setProps({ video: { ...video, ready: false } })
      expect(first.close).toHaveBeenCalled()
      expect(wrapper.text()).toContain('视频正在重连')
      expect(playWhep).toHaveBeenCalledTimes(1)
      await wrapper.setProps({ video: { ...video, ready: true } })
      await flushPromises()
      expect(playWhep).toHaveBeenCalledTimes(2)
    } finally {
      wrapper.unmount()
    }
  })

  it('automatically retries a WHEP 404 when publisher readiness is unknown', async () => {
    vi.mocked(playWhep).mockRejectedValueOnce(new ApiError('HTTP 404', 404)).mockResolvedValue(fakeConnection())
    const wrapper = mount(Dog2Video, { props: { ...props, video } })
    try {
      await flushPromises()
      expect(playWhep).toHaveBeenCalledTimes(1)
      expect(wrapper.text()).toContain('正在等待狗的视频')
      await vi.advanceTimersByTimeAsync(1500)
      await flushPromises()
      expect(playWhep).toHaveBeenCalledTimes(2)
      await wrapper.get('video').trigger('playing')
      expect(wrapper.find('.hint').exists()).toBe(false)
    } finally {
      wrapper.unmount()
    }
  })
})
