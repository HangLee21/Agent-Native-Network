import { afterEach, describe, expect, it } from 'vitest'
import { lang, tb, translateIncoming } from '@/i18n'
import { lite3Pose } from '@/stores/dog'
import templates from '@/i18n/backend/dogs-demo'

afterEach(() => {
  lang.value = 'zh'
})

/** Messages built the way the Java code builds them (dog, dogv2, demo) and the boards' own replies. */
const CASES: [string, string][] = [
  // DogErrors.unreachable(BoardHttp.Unreachable("连不上（" + e.getClass().getSimpleName() + "）"))
  ['连不上狗：连不上（ConnectException）', 'Cannot reach the dog: Cannot connect (ConnectException)'],
  ['狗方回复 HTTP 502', 'The dog replied HTTP 502'],
  ['没收到狗的回复：狗可能已经收到，先看狗的状态', "No reply from the dog: it may have received the command. Check the dog's state first"],
  ['取状态失败：回复太大', 'Could not get the state: Reply too large'],
  ['没有这只狗：go2', 'No such dog: go2'],
  ['释放控制（浏览器没有心跳）', 'Release control (No heartbeat from the browser)'],
  ['运动心跳失败，控制已解除：连不上狗：连不上（SocketTimeoutException）',
    'Motion heartbeat failed, control released: Cannot reach the dog: Cannot connect (SocketTimeoutException)'],
  ['释放没有得到回复：狗会在租约到期后自己停（连不上狗：连不上（ConnectException））',
    'No reply to the release: the dog stops by itself when the lease expires (Cannot reach the dog: Cannot connect (ConnectException))'],
  ['不支持的 Lite3 动作：jump', 'Unsupported Lite3 action: jump'],
  ['刚按过起立 / 趴下，3 秒内不能再按', 'Stand up / Lie down was just pressed: wait 3 s before pressing again'],
  ['停在 34 mm（目标 80 mm）', 'Stopped at 34 mm (target 80 mm)'],
  ['实际最大误差 1.8°（要求 ≤ 1°）', 'Actual max error 1.8° (must be ≤ 1°)'],
  ['停在阶段：夹持', 'Stopped at stage: gripping'],
  ['心跳失败：心跳 0.7 秒没有回复', 'Heartbeat failed: No heartbeat reply for 0.7 s'],
  ['松手，狗已停', 'Let go, dog stopped'],
  ['未确认停止：约 0.55 秒后应自动停，请看画面（狗方回复 HTTP 500）',
    'Stop not confirmed: it should stop by itself in about 0.55 s. Watch the video (The dog replied HTTP 500)'],
  ['点动被拒：机械臂未收回', 'Jog refused: Arm not stowed'],
  ['x 必须是有限数', 'x must be a finite number'],
  // mock boards
  ['匹配得分 0.82 · 未撤回', 'Match score 0.82 · not revoked'],
  ['姿态已切换为 sit（模拟）', 'Posture switched to sit (simulated)'],
  ['地图操作 save…', 'Map operation save…'],
  // real Lite3 console
  ['停止命令发送失败: stop_movement; 0x21010C0E', 'Failed to send the stop command: stop_movement; 0x21010C0E'],
  ['SDK 初始化失败: timed out', 'SDK initialization failed: timed out'],
  // dogv2 and dog-agent
  ['控制已解除：浏览器没有心跳', 'Control released: No heartbeat from the browser'],
  ['浏览器 400 ms 没有心跳，让狗停下（控制权保留）', 'No browser heartbeat for 400 ms: dog stopped (control kept)'],
  ['狗现在不是趴着的（FORCE_CONTROL），先让狗趴下', 'The dog is not lying down (FORCE_CONTROL): make it lie down first'],
  ['指令参数不对：cmd.args.stream: not one of [front]', 'Invalid command arguments: cmd.args.stream: not one of [front]'],
  ['没发出去：MQTT 没有连上', 'Not sent: MQTT not connected'],
  ['接管后收不到运动主机的状态包；已退回老系统', 'No state packets from the motion host after takeover; back on the old system'],
  ['新系统的运动进程退出了，自动切回老系统', "The new system's motion process exited; switched back to the old system automatically"],
  // demo checks
  ['A（SIM-A）在线', 'A (SIM-A) online'],
  ['两架起飞点只相距 6 m，建议 ≥ 10 m', 'Takeoff points only 6 m apart; ≥ 10 m recommended'],
  ['汇合点水平相距 12 m（高度差 2 m），太近，会触发靠近悬停',
    'Rendezvous points 12 m apart horizontally (2 m height difference): too close, the proximity hold will trigger'],
  ['第一段 A、B 两条航线：同一高度段最近处水平相距 14 m（高度差 1 m），小于 20 m，平台可能会让其中一架悬停',
    'Leg 1 routes of A and B: closest horizontal approach at similar height 14 m (1 m height difference), under 20 m; the platform may hold one of them'],
  ['A 第一段：演示-A 第一段·左侧探索1110（6 个航点）', 'A leg 1: 演示-A 第一段·左侧探索1110 (6 waypoints)'],
  ['低空跟随：未选择航线', 'Low follow: no route selected'],
  ['开始前检查没通过：B（SIM-B）不在线或未找到；高空第二段：航线已不存在',
    'Pre-start checks failed: B (SIM-B) offline or not found; High leg 2: route no longer exists'],
  // demo scenario
  ['第四阶段：低空跟随（本次没有机器狗）', 'Phase 4: low follow (no robot dog this run)'],
  ['交换信息中，7 秒后进入第二阶段', 'Exchanging info; phase 2 in 7 s'],
  ['B 相机看向目标区域没成功：相机看向目标：云台到达限位（模拟 327014）（10 秒后重试）',
    "Pointing B's camera at the target area failed: Camera look-at: gimbal reached its limit (simulated 327014) (retrying in 10 s)"],
  ['放 B 起飞没成功：模拟飞机 SIM-B 还在地面。10 秒后自动重试，也可以点「下一步」立即重试',
    'Launching B failed: Simulated drone SIM-B is still on the ground. Retrying in 10 s, or click "Next" to retry now'],
  ['A 因两机靠近暂停：确认安全后点「恢复」（剧本不会自动恢复）',
    'A paused: drones too close: once it is safe, click "Resume" (the scenario does not resume on its own)'],
  ['发现需要采样的目标，已在画面中标出（视频框选 + 激光测距，39.123456, 116.654321）',
    'Found a target to sample; marked on the video (video box select + laser rangefinder, 39.123456, 116.654321)'],
  ['左转 35°', 'Turn left 35°'],
  ['前进，距目标 42 m', 'Forward, 42 m to target'],
  ['B 的航线失败：已中止，原地悬停', "B's route failed: Aborted, hovering in place"],
  ['已到达航点 3，悬停等待确认', 'Reached waypoint 3, hovering for confirmation'],
]

describe('backend text from the dogs and the demo, in English', () => {
  it('translates real messages', () => {
    lang.value = 'en'
    for (const [zh, en] of CASES) expect(tb(zh), zh).toBe(en)
  })

  it('keeps the event sender and cell labels translatable as whole words', () => {
    lang.value = 'en'
    const ev = translateIncoming({ from: 'B', to: '狗', text: '停止：已到达目标', cells: [{ label: '草地' }] })
    expect(ev).toEqual({ from: 'B', to: 'Dog', text: 'Stop: target reached', cells: [{ label: 'Grass' }] })
  })

  it('gives Lite3 states that the pose reader still recognises', () => {
    lang.value = 'en'
    for (const zh of ['趴下', '正在趴下', '正在起立', '站立（力控）', '暂无状态反馈']) {
      expect(lite3Pose(tb(zh)), zh).toBe(lite3Pose(zh))
    }
  })

  it('has well-formed templates: same placeholders, no Chinese in the English', () => {
    const names = (s: string) => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort().join(',')
    const bad = templates.filter(([zh, en]) => names(zh) !== names(en) || /[一-鿿]/.test(en) || !en.trim())
    expect(bad).toEqual([])
  })
})
