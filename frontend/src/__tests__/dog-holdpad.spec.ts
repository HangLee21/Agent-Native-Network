/** Keyboard on the dog pad (review 2026-11-07): shortcuts never move the dog, and an Esc used elsewhere is not a stop. */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import HoldPad from '@/components/dog/HoldPad.vue'
import { useDogStore } from '@/stores/dog'
import { dogApi, type Lite3State } from '@/api/dog'

vi.mock('@/api/dog', async (importOriginal) => {
  const real = await importOriginal<typeof import('@/api/dog')>()
  return { ...real, beacon: vi.fn(), dogApi: { ...real.dogApi, lite3: vi.fn(), s10Action: vi.fn() } }
})

function lite3(): Lite3State {
  return {
    dogId: 'lite3', kind: 'lite3', name: 'Lite3', link: { state: 'online', lastOkAt: Date.now(), rttMs: 20 }, serverTime: Date.now(),
    statusAt: Date.now(), robot: { connected: true, robot_state: '站立（力控）', feedback_age: 0.1, controller: 'platform', controlSession: 's' },
  }
}
const key = (type: 'keydown' | 'keyup', k: string, mods: KeyboardEventInit = {}) =>
  window.dispatchEvent(new KeyboardEvent(type, { key: k, cancelable: true, ...mods }))
const flush = () => new Promise((r) => setTimeout(r, 0))

describe('dog pad keyboard', () => {
  let w: VueWrapper | null = null
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.mocked(dogApi.lite3).mockReset()
    vi.mocked(dogApi.lite3).mockResolvedValue({ ok: true } as never)
    const store = useDogStore()
    store.onState(lite3(), true)
    store.l3.session = 's'
    w = mount(HoldPad, { props: { dog: 'lite3' } })
  })
  afterEach(() => {
    w?.unmount()
    w = null
  })

  it('⌘S / Ctrl+A are shortcuts, not moves', () => {
    const store = useDogStore()
    key('keydown', 's', { metaKey: true })
    key('keydown', 'a', { ctrlKey: true })
    expect(store.l3.axes).toEqual([0, 0, 0])
  })

  it('pressing ⌘ while walking lets go (macOS would never report the letter released)', () => {
    const store = useDogStore()
    key('keydown', 'w')
    expect(store.l3.axes).toEqual([1, 0, 0])
    key('keydown', 'Meta', { metaKey: true })
    expect(store.l3.axes).toEqual([0, 0, 0])
  })

  it('an Esc that closed something else does not stop the dog', async () => {
    const closeOverlay = (e: KeyboardEvent) => e.key === 'Escape' && e.preventDefault()
    window.addEventListener('keydown', closeOverlay)
    key('keydown', 'Escape')
    await flush()
    window.removeEventListener('keydown', closeOverlay)
    expect(w!.emitted('stop')).toBeUndefined()
    // a plain Esc still stops (the page turns the pad's "stop" into the dog's stop)
    key('keydown', 'Escape')
    await flush()
    expect(w!.emitted('stop')).toHaveLength(1)
  })
})
