import { afterEach, describe, expect, it } from 'vitest'
import { lang, t, tb, translateIncoming } from '@/i18n'
import { lite3Next, s10Next, type Lite3NextInput } from '@/components/dog/dogFlow'
import { lite3Pose } from '@/stores/dog'
import type { Lite3State, S10State } from '@/api/dog'

afterEach(() => {
  lang.value = 'zh'
})

function s10(over: Partial<S10State> = {}): S10State {
  return {
    dogId: 's10', kind: 's10', name: 'S10', link: { state: 'online', lastOkAt: 1, rttMs: 80, clockOk: true }, serverTime: 1,
    chassis: { posture: 'sitting', available: true }, posture: 'sitting', available: true, nav: { state: 'IDLE' },
    map: { mode: 'localization', trust: { verdict: 'ok', withdrawn: false } }, maps: [], ik: { ready: true }, vision: { ready: true },
    boardTime: 1, workAt: 1, workError: null, jobs: [], topics: { joints: { deg: [0, 0, 0, 0, 25, 0], age: 0.1 } },
    stateAt: 1, stateError: null, holdActive: false, armHoldActive: false, ...over,
  }
}
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

describe('dog panels in English', () => {
  it('gives the next step and its button in English', () => {
    lang.value = 'en'
    const n = s10Next({ s: s10(), online: true, lost: false, holding: false, card: 'posture', lastFail: null, stateAge: 1, jobSecs: 0 })
    expect(n.text).toBe('Next: press ① "Stand up" (the arm is stowed first by itself)')
    expect(n.fix?.label).toBe('① Stand up')
  })

  it('still reads the Lite3 state names after they arrive translated', () => {
    lang.value = 'en'
    const pose = (zh: string) => lite3Pose(translateIncoming({ robot_state: zh }).robot_state)
    expect(pose('站立（力控）')).toBe('standing')
    expect(pose('正在起立')).toBe('transition')
    expect(pose('正在趴下')).toBe('transition')
    expect(pose('趴下')).toBe('lying')
  })

  it('a lost control is still a warning, and a board not in control says why', () => {
    lang.value = 'en'
    const lost = lite3Next(lin(l3(), { endedReason: t('控制权已失去：{detail}', { detail: 'x' }) }))
    expect(lost.cls).toBe('warn')
    expect(lost.text).toBe('Control lost: x. Press ① "Take control" to take it again')
    const noPackets = lite3Next(lin(l3({ connected: false, error: '' })))
    expect(noPackets.cls).toBe('warn')
    expect(noPackets.text).toBe("The board gets no state packets from the motion host: taking control is refused now. If it stays like this, check that the dog is on, or restart it")
    const oldMode = lite3Next(lin(l3({ connected: false, error: t('板卡现在是老系统在控：到「新狗系统」页切到新系统') })))
    expect(oldMode.text).toBe(t('板卡现在是老系统在控：到「新狗系统」页切到新系统'))
  })

  it('shows the Chinese command labels the panels send in English', () => {
    lang.value = 'en'
    const fixed = ['站立', '趴下', 'RL 控制', '平地步态', '收回机械臂', '开始 / 继续建图', '重新定位', '取消导航', '停止机械臂动作', '一键抓取（萝卜）',
      '起立（起立 / 趴下切换）', '移动模式', '低速步态', '取得控制', '软急停（阻尼）', '停止 → 取消导航', '松手', '离开页面', '手动释放']
    for (const zh of fixed) expect(/[一-鿿]/.test(tb(zh)), zh).toBe(false)
    expect(tb('按住移动 · 前进')).toBe('Hold to move · Forward')
    expect(tb('保存地图 lab_1')).toBe('Save map lab_1')
    expect(tb('导航到 (1.5, -2, 90°)')).toBe('Navigate to (1.5, -2, 90°)')
    expect(tb('点动 J3 ＋')).toBe('Jog J3 +')
    const cmd = translateIncoming({ label: '停止 → 停止机械臂动作（执行输入角度）', detail: '松手，狗已停' })
    expect(cmd).toEqual({ label: 'Stop → stop arm motion (Move to entered angles)', detail: 'Let go, dog stopped' })
    expect(t('{reason}：狗已停', { reason: tb('松手') })).toBe('Let go: dog stopped')
  })

  it('shows the Lite3 state 趴下 as a state', () => {
    lang.value = 'en'
    expect(tb('趴下')).toBe('Lying down')
    expect(lite3Pose(tb('趴下'))).toBe('lying')
    expect(lite3Pose(tb('正在趴下'))).toBe('transition')
  })
})
