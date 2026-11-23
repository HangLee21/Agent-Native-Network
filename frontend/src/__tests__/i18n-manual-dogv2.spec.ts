/**
 * English mode for the Guide (the English twin of the manual HTML) and the new dog system page (docs/i18n.md).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { lang } from '@/i18n'
import * as zh from '@/components/dog/manualHtml'
import * as en from '@/components/dog/manualHtml.en'
import ManualContent from '@/components/dog/ManualContent.vue'
import { useDog2Store } from '@/stores/dogv2'
import { dog2Api, replyText } from '@/api/dogv2'
import { ApiError } from '@/api/http'

vi.mock('@/api/dogv2', async (importOriginal) => {
  const real = await importOriginal<typeof import('@/api/dogv2')>()
  return {
    ...real,
    dog2Api: { ...real.dog2Api, list: vi.fn(), take: vi.fn(), release: vi.fn(), teleop: vi.fn(), command: vi.fn() },
  }
})
const api = vi.mocked(dog2Api)

const ids = (html: string) => [...html.matchAll(/\bid="([^"]+)"/g)].map((m) => m[1])
const tags = (html: string) => [...html.matchAll(/<\/?([a-z0-9]+)/g)].map((m) => m[1]).join(' ')

afterEach(() => {
  lang.value = 'zh'
})

describe('English guide', () => {
  it('has the same contents, ids and HTML structure as the Chinese one, and no Chinese left', () => {
    expect(en.MANUAL_TOC.map((x) => [x.id, x.sub])).toEqual(zh.MANUAL_TOC.map((x) => [x.id, x.sub]))
    expect(ids(en.MANUAL_BODY)).toEqual(ids(zh.MANUAL_BODY))
    expect(tags(en.MANUAL_BODY)).toBe(tags(zh.MANUAL_BODY))
    expect(en.MANUAL_BODY).not.toMatch(/[一-鿿]/)
    expect(en.MANUAL_TOC.filter((x) => /[一-鿿]/.test(x.label))).toEqual([])
  })

  it('is what the Guide shows in English mode, and Chinese stays the default', () => {
    const z = mount(ManualContent, { props: { panel: true } })
    expect(z.text()).toContain('先读：安全须知')
    expect(z.get('[data-test=manual-close]').text()).toBe('× 关闭说明（回到操作）')
    lang.value = 'en'
    const w = mount(ManualContent, { props: { panel: false } })
    expect(w.text()).toContain('Read first: safety')
    expect(w.text()).not.toContain('先读')
    expect(w.get('[data-test=manual-close]').text()).toBe('← Back to Monitor')
  })
})

describe('new dog system in English', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
    api.list.mockResolvedValue({ mode: 'mock', broker: true, dogs: [] })
    api.take.mockResolvedValue({ result: 'done', session: 'web-1' })
    api.release.mockResolvedValue({ result: 'done' })
  })
  afterEach(() => {
    vi.useRealTimers()
    vi.clearAllMocks()
  })

  it('words the dog replies', () => {
    lang.value = 'en'
    expect(replyText({ result: 'done' })).toBe('Done by the dog')
    expect(replyText({ result: 'rejected', code: 'BUSY' })).toBe('Not done by the dog: BUSY')
    expect(replyText({ result: 'not_sent' })).toBe('Not sent')
  })

  it('a 409 arriving translated still gives just the reason', async () => {
    lang.value = 'en'
    api.teleop.mockRejectedValue(new ApiError('Control released: no heartbeat from the browser', 409))
    const s = useDog2Store()
    await s.take('lite3-01')
    s.setAxes([1, 0, 0])
    await vi.advanceTimersByTimeAsync(50)
    expect(s.hold.session).toBeNull()
    expect(s.hold.lostReason).toBe('no heartbeat from the browser')
    expect(s.notes[0]?.text).toBe('Control lost: no heartbeat from the browser')
  })

  it('keeps sending the release reason in Chinese, so the backend log stays in one language', async () => {
    lang.value = 'en'
    api.teleop.mockResolvedValue({ ok: true, seq: 1 })
    const s = useDog2Store()
    await s.take('lite3-01')
    s.leave('离开新狗系统页')
    await vi.advanceTimersByTimeAsync(10)
    expect(api.release).toHaveBeenCalledWith('lite3-01', 'web-1', '离开新狗系统页')
    expect(s.notes[0]?.text).toBe('Release control: Done by the dog')
  })
})
