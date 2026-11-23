import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'
import ExecutionProgress from '@/components/route/ExecutionProgress.vue'
import SyncDialog from '@/components/route/SyncDialog.vue'
import { useExecutionStore } from '@/stores/execution'
import { useOverlaysStore } from '@/stores/overlays'
import type { ExecutionSnapshot } from '@/api/execution'

function snap(over: Partial<ExecutionSnapshot> = {}): ExecutionSnapshot {
  return {
    id: 'e1', routeId: 'r1', routeName: '巡检 A', routeVersion: 1, mode: 'STOP_AND_GO', state: 'FLYING', currentIndex: 1, total: 3,
    waypoints: [{ lat: 1, lon: 1, relativeHeight: 30 }, { lat: 2, lon: 2, relativeHeight: 30 }, { lat: 3, lon: 3, relativeHeight: 30 }],
    reachedCount: 1, message: '飞往航点 2/3', startedAt: 1, endedAt: null, log: [{ ts: 1, level: 'INFO', text: '到达航点 1' }], active: true, ...over,
  }
}

describe('route execution (R-09) and sync (R-08)', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('shows progress and offers a stop button while active', () => {
    const ex = useExecutionStore()
    ex.apply(snap())
    expect(useOverlaysStore().route).toHaveLength(3)
    const w = mount(ExecutionProgress)
    expect(w.text()).toContain('飞行中')
    expect(w.text()).toContain('已到达 1/3')
    expect(w.find('[data-test=abort-execution]').exists()).toBe(true)
    ex.apply(snap({ state: 'COMPLETED', active: false, reachedCount: 3, endedAt: 2 }))
  })

  it('keeps a finished run when an older reply of the same run arrives late (abort race)', () => {
    const ex = useExecutionStore()
    ex.apply(snap({ state: 'ABORTED', active: false, endedAt: 5 })) // pushed over the WebSocket first
    ex.apply(snap()) // the abort request's own reply, taken before the run ended
    expect(ex.current?.state).toBe('ABORTED')
    expect(ex.active).toBe(false)
    ex.apply(snap({ id: 'e2' })) // a new run is applied normally
    expect(ex.current?.id).toBe('e2')
  })

  it('tells the operator that the pilot must download the synced route', () => {
    const w = mount(SyncDialog, { props: { result: { routeId: 'r1', waylineName: '巡检 A', routeVersion: 2, syncedAt: 1, warnings: ['航点 2：变焦动作未写入航线文件'], sizeBytes: 2048 } } })
    expect(w.text()).toContain('点击下载')
    expect(w.text()).toContain('变焦动作未写入航线文件')
  })
})

describe('execution snapshots out of order', () => {
  it('a resume reply that is older than the push does not bring PAUSED back', async () => {
    const { createPinia, setActivePinia } = await import('pinia')
    const { useExecutionStore } = await import('@/stores/execution')
    const { useTestDrone } = await import('./testDrone')
    setActivePinia(createPinia())
    useTestDrone()
    const ex = useExecutionStore()
    const base = { id: 'e1', routeId: 'r', routeName: 'R', routeVersion: 1, mode: 'STOP_AND_GO', currentIndex: 1, total: 2, waypoints: [],
      reachedCount: 1, message: '', startedAt: 1, endedAt: null, active: true }
    const log = (n: number) => Array.from({ length: n }, (_, i) => ({ ts: i, level: 'INFO', text: String(i) }))
    ex.apply({ ...base, state: 'FLYING', log: log(4) } as never) // pushed: flying again
    ex.apply({ ...base, state: 'PAUSED', pauseReason: 'PROXIMITY', log: log(3) } as never) // older reply of the resume call
    expect(ex.current?.state).toBe('FLYING')
  })

  it('compares by version once the log is full (200 entries, the oldest dropped)', async () => {
    const { createPinia, setActivePinia } = await import('pinia')
    const { useExecutionStore } = await import('@/stores/execution')
    const { useTestDrone } = await import('./testDrone')
    setActivePinia(createPinia())
    useTestDrone()
    const ex = useExecutionStore()
    const base = { id: 'e1', routeId: 'r', routeName: 'R', routeVersion: 1, mode: 'STOP_AND_GO', currentIndex: 1, total: 2, waypoints: [],
      reachedCount: 1, message: '', startedAt: 1, endedAt: null, active: true }
    const log = Array.from({ length: 200 }, (_, i) => ({ ts: i, level: 'INFO', text: String(i) }))
    ex.apply({ ...base, state: 'FLYING', log, version: 412 } as never) // pushed
    ex.apply({ ...base, state: 'PAUSED', pauseReason: 'PROXIMITY', log, version: 409 } as never) // older reply, same log length
    expect(ex.current?.state).toBe('FLYING')
    ex.apply({ ...base, state: 'PAUSED', pauseReason: 'PROXIMITY', log, version: 415 } as never) // a newer pause
    expect(ex.current?.state).toBe('PAUSED')
  })
})
