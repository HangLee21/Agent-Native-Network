/**
 * Front depth distance under the Lite3 depth video (telemetry.depth_front, protocol.md 7): the old Lite3 card's
 * "中心深度 X m（有效 Y%）", and a short state when there is no number.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { lang } from '@/i18n'
import { dog2Api, type Dog2, type Dog2Telemetry } from '@/api/dogv2'
import { useDog2Store } from '@/stores/dogv2'
import { depthFrontText } from '@/components/dogv2/depthFront'
import DogMain from '@/components/dog/DogMain.vue'

vi.mock('@/api/dogv2', async (importOriginal) => {
  const real = await importOriginal<typeof import('@/api/dogv2')>()
  return { ...real, dog2Api: { ...real.dog2Api, list: vi.fn(), video: vi.fn() } }
})

type Front = NonNullable<Dog2Telemetry['depth_front']>

function dog(front: Front | undefined, over: Partial<Dog2> = {}): Dog2 {
  return {
    id: 'lite3-01', label: 'Lite3', model: 'lite3', software: '0.1.6', online: true, enabled: true, mode: 'new', gateway: 'active',
    statusAgeMs: 200, telemetryAgeMs: 100, status: { mode: 'new' },
    telemetry: { basic_state: 1, battery_pct: 80, rpy: [0, 0, 0], vel_body: [0, 0, 0], feedback_age_s: 0.02, ...(front ? { depth_front: front } : {}) },
    control: { held: false, mine: false, session: null, endedReason: null },
    video: { rgb: { path: 'dog/lite3-01-rgb', whep: null, state: 'off' }, depth: { path: 'dog/lite3-01-depth', whep: null, state: 'off' } },
    lastSeenAt: 1, ...over,
  }
}

afterEach(() => {
  lang.value = 'zh'
})

describe('front depth text', () => {
  it('reads like the old Lite3 card', () => {
    expect(depthFrontText(dog({ dist_m: 1.2345, valid_pct: 87.4, age_s: 0.12, state: 'ok' }))).toBe('中心深度 1.23 m（有效 87%）')
    expect(depthFrontText(dog({ dist_m: 0.6, valid_pct: 22, age_s: 0.3 }))).toBe('中心深度 0.60 m（有效 22%）')
  })

  it('gives no number when the image is old or nothing in the centre is valid', () => {
    expect(depthFrontText(dog({ dist_m: 1.2, valid_pct: 90, age_s: 0.8, state: 'ok' }))).toBe('中心深度 —（深度图 0.8 秒没更新）')
    expect(depthFrontText(dog({ dist_m: 1.2, valid_pct: 90, age_s: 42.4, state: 'no_image' }))).toBe('中心深度 —（深度图 42 秒没更新）')
    expect(depthFrontText(dog({ dist_m: null, valid_pct: 0, age_s: 0.1, state: 'ok' }))).toBe('中心深度 —（有效 0%）')
    expect(depthFrontText(dog({ dist_m: null, valid_pct: null, age_s: null, state: 'no_image' }))).toBe('中心深度 —（没有深度图）')
    expect(depthFrontText(dog({ dist_m: 1.2, valid_pct: 90, age_s: null, state: 'ok' }))).toBe('中心深度 —（深度图时间不对）')
    expect(depthFrontText(dog({ dist_m: 1.2, valid_pct: 90, age_s: 0.1, state: 'error' }))).toBe('中心深度 —（读取深度图出错）')
  })

  it('no number without fresh telemetry from the new system', () => {
    const f: Front = { dist_m: 1.2, valid_pct: 90, age_s: 0.1, state: 'ok' }
    expect(depthFrontText(dog(f, { telemetryAgeMs: 5000 }))).toBe('中心深度 —')
    expect(depthFrontText(dog(f, { online: false }))).toBe('中心深度 —')
    expect(depthFrontText(dog(f, { mode: 'old' }))).toBe('中心深度 —')
  })

  it('shows nothing for a dog that does not report it', () => {
    expect(depthFrontText(dog(undefined))).toBeNull()
    expect(depthFrontText(dog(undefined, { telemetry: null }))).toBeNull()
    expect(depthFrontText(null)).toBeNull()
  })

  it('in English', () => {
    lang.value = 'en'
    expect(depthFrontText(dog({ dist_m: 1.2345, valid_pct: 87.4, age_s: 0.12 }))).toBe('Centre depth 1.23 m (87% valid)')
    expect(depthFrontText(dog({ dist_m: null, valid_pct: null, age_s: null }))).toBe('Centre depth — (no depth image)')
    expect(depthFrontText(dog({ dist_m: 1, valid_pct: 90, age_s: 3 }))).toBe('Centre depth — (no new depth image for 3.0 s)')
    expect(depthFrontText(dog({ dist_m: 1, valid_pct: 90, age_s: 0.1, state: 'error' }))).toBe('Centre depth — (error reading the depth image)')
  })
})

describe('Lite3 main view', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.mocked(dog2Api.video).mockResolvedValue({ path: 'dog/lite3-01-depth', state: 'off' })
  })

  it('shows the front depth over both pictures (ui-design.md 20.7)', async () => {
    useDog2Store().dogs = [dog({ dist_m: 1.8, valid_pct: 92, age_s: 0.1, state: 'ok' })]
    const w = mount(DogMain, { props: { dog: 'lite3' } })
    expect(w.get('[data-test=dog-depth-front]').text()).toBe('中心深度 1.80 m（有效 92%）')   // colour video first
    const depthBtn = w.findAll('.views button').find((b) => b.text() === '深度')
    await depthBtn!.trigger('click')
    expect(w.get('[data-test=dog-depth-front]').text()).toBe('中心深度 1.80 m（有效 92%）')
    w.unmount()
  })

  it('nothing for a board without it', async () => {
    useDog2Store().dogs = [dog(undefined)]
    const w = mount(DogMain, { props: { dog: 'lite3' } })
    await w.findAll('.views button').find((b) => b.text() === '深度')!.trigger('click')
    expect(w.find('[data-test=dog-depth-front]').exists()).toBe(false)
    w.unmount()
  })
})
