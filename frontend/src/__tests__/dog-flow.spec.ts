import { describe, expect, it } from 'vitest'
import { lite3Flow, lite3Next, s10Next, s10Stowed, type Lite3NextInput, type S10NextInput } from '@/components/dog/dogFlow'
import { lite3Pose, navActive } from '@/stores/dog'
import type { Lite3State, S10Job, S10State } from '@/api/dog'

function s10(over: Partial<S10State> = {}): S10State {
  return {
    dogId: 's10', kind: 's10', name: 'S10', link: { state: 'online', lastOkAt: 1, rttMs: 80, clockOk: true }, serverTime: 1,
    chassis: { posture: 'sitting', available: true }, posture: 'sitting', available: true, nav: { state: 'IDLE' },
    map: { mode: 'localization', trust: { verdict: 'ok', withdrawn: false } }, maps: [], ik: { ready: true }, vision: { ready: true },
    boardTime: 1, workAt: 1, workError: null, jobs: [], topics: { joints: { deg: [0, 0, 0, 0, 25, 0], age: 0.1 } },
    stateAt: 1, stateError: null, holdActive: false, armHoldActive: false, ...over,
  }
}
const base = (s: S10State, over: Partial<S10NextInput> = {}): S10NextInput => ({
  s, online: true, lost: false, holding: false, card: 'posture', lastFail: null, stateAge: 1, jobSecs: 3, ...over,
})
const job = (action: string, stoppable: boolean): S10Job => ({ id: 'j', action, state: 'running', origin: 'platform', stoppable, started: 1 })

describe('S10 next step follows the dog (ui-design.md 9.0)', () => {
  it('lying → stand, standing → RL, RL → walk', () => {
    expect(s10Next(base(s10())).fix?.key).toBe('stand')
    expect(s10Next(base(s10({ posture: 'standing' }))).fix?.key).toBe('rl')
    expect(s10Next(base(s10({ posture: 'rl_control' }))).cls).toBe('ok')
  })
  it('after the soft e-stop: damping offers nothing, idle offers stand only', () => {
    expect(s10Next(base(s10({ posture: 'damping' }))).fix).toBeUndefined()
    expect(s10Next(base(s10({ posture: 'idle' }))).fix?.key).toBe('stand')
  })
  it('only stoppable jobs get a stop button', () => {
    const map = s10Next(base(s10({ jobs: [job('map', false)] })))
    expect(map.fix).toBeUndefined()
    expect(map.text).toContain('不能中途取消')
    expect(s10Next(base(s10({ jobs: [job('arm_move', true)] }))).fix?.key).toBe('armstop')
    expect(s10Next(base(s10({ jobs: [job('navigate', true)] }))).fix?.key).toBe('navcancel')
  })
  it('navigation is read from the navigation state, not from a job', () => {
    expect(navActive({ state: 'RUNNING' })).toBe(true)
    expect(s10Next(base(s10({ nav: { state: 'RUNNING' } }))).fix?.key).toBe('navcancel')
  })
  it('no one-click fix when the state is stale', () => {
    expect(s10Next(base(s10(), { stateAge: 25 })).fix).toBeUndefined()
  })
  it('arm page asks to lie down first; navigation needs trust and a stowed arm', () => {
    expect(s10Next(base(s10({ posture: 'standing' }), { card: 'arm' })).fix?.key).toBe('sit')
    expect(s10Next(base(s10({ map: { trust: { verdict: 'bad' } } }), { card: 'nav' })).fix?.key).toBe('card:map')
    const out = s10({ topics: { joints: { deg: [10, 0, 0, 0, 25, 0], age: 0.1 } } })
    expect(s10Stowed(out)).toBe(false)
    expect(s10Next(base(out, { card: 'nav' })).fix?.key).toBe('armhome')
  })
  it('mapping without being able to walk points back to the prepare page', () => {
    expect(s10Next(base(s10({ map: { mode: 'mapping' } }), { card: 'map' })).fix?.key).toBe('card:posture')
  })
  it('offline and lost say so', () => {
    expect(s10Next(base(s10(), { online: false })).cls).toBe('bad')
    expect(s10Next(base(s10(), { online: false, lost: true })).text).toContain('失联')
  })
})

function l3(over: Partial<Lite3State['robot']> = {}): Lite3State {
  return {
    dogId: 'lite3', kind: 'lite3', name: 'Lite3', link: { state: 'online', lastOkAt: 1, rttMs: 60 }, serverTime: 1, statusAt: 1,
    robot: { connected: true, controller: null, battery: 76, robot_state: '趴下', feedback_age: 0.05, error: '', ...over },
  }
}
const lin = (l: Lite3State, over: Partial<Lite3NextInput> = {}): Lite3NextInput => ({
  l, online: true, mine: false, holding: false, pose: lite3Pose(l.robot.robot_state),
  marks: { moving: false, low: false, estopAt: 0, selfSit: false }, endedReason: null, feedbackAge: 0.1, ...over,
})

describe('Lite3 next step follows the official order', () => {
  // moving mode is not a step: lite3-01 walked right after standing with no moving mode sent (MQTT log 2026-11-10)
  it('control → stand → walk, without asking for moving mode', () => {
    expect(lite3Next(lin(l3())).fix?.key).toBe('arm')
    expect(lite3Next(lin(l3(), { mine: true })).fix?.key).toBe('stand')
    const up = l3({ robot_state: '站立（力控）' })
    const ready = lite3Next(lin(up, { mine: true }))
    expect(ready.cls).toBe('ok')
    expect(ready.fix).toBeUndefined()
    expect(ready.text).not.toContain('移动模式')
    const flow = lite3Flow(up, true, true, false)
    expect(flow.map((s) => s.label)).toEqual(['连接', '控制权', '站立', '可以走'])
    expect(flow[3]!.state).toBe('cur')
  })
  it('the stand toggle is not offered while the state is stale', () => {
    expect(lite3Next(lin(l3(), { mine: true, feedbackAge: 3 })).fix).toBeUndefined()
  })
  it('low battery, soft e-stop, protection and control elsewhere are explained', () => {
    expect(lite3Next(lin(l3({ battery: 18 }))).text).toContain('低电保护')
    expect(lite3Next(lin(l3(), { marks: { moving: false, low: false, estopAt: 5, selfSit: false } })).text).toContain('已软急停')
    expect(lite3Next(lin(l3({ robot_state: '失控保护' }))).text).toContain('失控保护')
    expect(lite3Next(lin(l3({ controller: 'other' }))).text).toContain('别的页面或电脑控制')
    expect(lite3Next(lin(l3({ controller: 'other' }))).text).not.toContain('狗方')
    expect(lite3Next(lin(l3({ robot_state: '正在起立' }))).cls).toBe('run')
  })
  it('after an automatic release the next step says why', () => {
    expect(lite3Next(lin(l3(), { endedReason: '因切换设备已停止并释放控制' })).text).toContain('切换设备')
  })
})
