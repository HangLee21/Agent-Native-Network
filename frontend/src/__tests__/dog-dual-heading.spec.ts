import { describe, expect, it } from 'vitest'
import type { Dog2 } from '@/api/dogv2'
import { dualHeading, headingWait, readyItems, readyLines } from '@/components/dog/dogNav'
import { headingRow, headingShort } from '@/components/dog/lite3Info'

describe('dual antenna readiness', () => {
  it('can keep its position while waiting at rest and reports board permission independently of the heading source', () => {
    const dog = { capabilities: { position: { heading: ['receiver'] } }, status: { gnss: { state: 'fix' } },
      position: { heading_source: 'none', lat: 30, lon: 104 },
      nav: { ready: { gnss: 'fix', heading: 'imu_aligned', heading_start_ok: false } } } as Dog2
    expect(dualHeading(dog)).toBe(true)
    expect(headingWait(dog)).toContain('位置已获取')
    expect(headingRow(dog).value).toBe('正在确认双天线朝向')
    expect(readyItems(dog.nav!.ready, true).find(r => r.key === 'heading')?.ok).toBe(false)
    expect(readyLines(dog.nav!.ready, true)).toContain('正在确认双天线朝向')
    Object.assign(dog.position!, { heading_source: 'imu_aligned', heading_deg: 25 })
    expect(headingShort(dog)).toMatchObject({ text: '25°', cls: 'warnc' })
    dog.nav!.ready!.heading_start_ok = true
    expect(headingWait(dog)).toBeNull()
  })
})
