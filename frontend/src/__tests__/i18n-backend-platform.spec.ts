import { afterEach, describe, expect, it } from 'vitest'
import { lang, tb } from '@/i18n'

afterEach(() => {
  lang.value = 'zh'
})

const fmt = (n: number, d: number) => n.toFixed(d)

/** Messages built exactly as backend service/, safety/, fleet/, route/, controller/ and device/ build them. */
const CASES: [string, string][] = [
  // SafetyViolationException + SafetyCheckResult + Violation
  ['安全检查未通过：' + '电量 ' + 18 + '% 低于起飞最低电量 ' + 30 + '%', 'Safety check failed: Battery 18% is below the minimum takeoff battery of 30%'],
  [
    '安全检查未通过：' + '飞行器不在地面待机状态，不能执行起飞' + '（共 ' + 2 + ' 项）',
    'Safety check failed: The aircraft is not on the ground in standby: cannot take off (2 issues in total)',
  ],
  [
    '安全检查未通过：' + '航点 ' + 3 + '：' + '高度 ' + fmt(130, 1) + ' m' + ' 超过平台限高 ' + fmt(120, 0) + ' m',
    'Safety check failed: Waypoint 3: Height 130.0 m is above the platform altitude limit of 120 m',
  ],
  [
    '安全检查未通过：' + '航点 ' + 2 + '：' + '速度 ' + fmt(18, 1) + ' m/s 超出允许范围 [1, 15] m/s' + '（共 3 项）',
    'Safety check failed: Waypoint 2: Speed 18.0 m/s is outside the allowed range [1, 15] m/s (3 issues in total)',
  ],
  ['安全检查未通过：' + '遥控器未连接，无法发送「' + '急停' + '」', 'Safety check failed: Remote controller not connected: cannot send "Emergency stop"'],
  ['安全检查未通过：' + '飞行器未连接' + '，无法执行「' + '开启直播' + '」', 'Safety check failed: Aircraft not connected: cannot run "Start live video"'],
  [
    '安全检查未通过：' + '返航高度' + ' 下发值 ' + fmt(530.4, 1) + ' m 在一种参考系解释下对应相对起飞点 ' + fmt(530.4, 1) + ' m，超出 [20, 120] m'
      + '（该参数高度参考系文档未明确，按两种参考系校验：D-03）'
      + '。可先在起飞前清单或飞行监控右栏 ⋯ 菜单的「飞行器限高」把飞行器限高设为不高于平台限高 120 m（当前飞行器限高：' + '未知' + '），平台即以飞行器限高兜底',
    'Safety check failed: RTH altitude: the value sent, 530.4 m, means 530.4 m above takeoff under one reference, outside [20, 120] m'
      + ' (the height reference of this parameter is not documented, so both references are checked: D-03).'
      + ' Set the aircraft altitude limit to no more than the platform limit of 120 m first (Pre-flight checklist, or "Aircraft altitude limit" in the ⋯ menu of the Monitor page right rail; aircraft limit now: Unknown). The aircraft limit then backs up the platform limit.',
  ],
  // ReturnHeightCheck
  [
    '返航高度与 ' + 'M4E-2' + ' 只差 ' + fmt(4, 1) + ' m（' + 'M4E-2' + ' 的返航高度为 ' + fmt(60, 0) + ' m），至少要差 ' + fmt(10, 0) + ' m：'
      + '两架同时返航时会在同一高度飞向相近的起飞点。可把返航高度改为 ' + fmt(71, 0) + ' m 或更高（执行航线时：在航线的全局参数里把返航高度改为手动）',
    'RTH altitude is only 4.0 m from that of M4E-2 (M4E-2: 60 m). It must differ by at least 10 m: when both return at once, they fly to nearby takeoff points at the same height. Set the RTH altitude to 71 m or higher (for a route: set the RTH altitude to manual in the route\'s global parameters).',
  ],
  // FlightService
  [
    'DRC 链路未连接，无法执行「' + '拍照' + '」。请先获取控制权（获得后自动进入 DRC）。',
    'DRC link not connected: cannot run "Take photo". Get control first (DRC starts automatically once you have it).',
  ],
  ['尚未获得云端控制权，无法执行「' + '兴趣点环绕' + '」', 'No cloud control yet: cannot run "POI orbit"'],
  ['变焦 ' + 5.0.toFixed(1) + '×', 'Zoom 5.0×'],
  ['设置飞行器限高 ' + 120 + ' m', 'Set aircraft altitude limit 120 m'],
  // CommandService + DjiErrorCodes
  ['超时：设备未在 ' + 5 + ' 秒内确认', 'Timed out: the device did not confirm within 5 s'],
  ['飞行器无法执行返航指令，飞行器已被 B 控接管' + '（' + 316023 + '）', 'The aircraft cannot return home: controller B has taken over. (316023)'],
  ['设备返回错误码 ' + 336000, 'Device returned error code 336000'],
  // AlertService
  ['电量 ' + 22 + '%，已低于返航所需电量 ' + 25 + '%' + '（正在返航/降落）', 'Battery 22%, below the 25% needed to return home (returning/landing)'],
  ['当前相对高度 ' + fmt(123.4, 1) + ' m 超过平台限高 ' + fmt(120, 0) + ' m', 'Height 123.4 m is above the platform altitude limit of 120 m'],
  [
    '避障传感器：水平最近 ' + '3.2 m' + '，上方 ' + '—' + '（警示距离 ' + fmt(5, 0) + ' m）',
    'Obstacle sensors: nearest horizontal 3.2 m, above — (warning distance 5 m)',
  ],
  // "label：message" of the command-failed alert, translated part by part
  ['一键返航' + '：' + '超时：设备未在 5 秒内确认', 'Return home: Timed out: the device did not confirm within 5 s'],
  [
    '一键返航' + '：' + '飞行器无法执行返航指令，请检查飞行器是否已开机或已断连' + '（316022）',
    'Return home: The aircraft cannot return home, check that it is powered on and connected (316022)',
  ],
  ['航点 ' + 3 + '：' + '悬停，等待操作员确认后' + '飞往航点 ' + 4, 'Waypoint 3: hovering; flies to waypoint 4 once the operator confirms'],
  // RouteExecutionService
  ['开始执行航线「' + '东门巡查' + '」（' + 6 + ' 个航点，' + '逐点飞行' + '）', 'Starting route "东门巡查" (6 waypoints, point by point)'],
  ['飞往航点 ' + 3 + '/' + 6, 'Flying to waypoint 3/6'],
  [
    '已到达航点 ' + 6 + '（最后一个），悬停等待确认；确认后执行结束动作（' + '返航' + '）',
    'Reached waypoint 6 (the last), hovering until confirmed; then the finish action runs (Return home)',
  ],
  [
    '暂停执行：' + '与 ' + 'M4E-2' + ' 靠近（水平 ' + fmt(14, 0) + ' m' + '，高度差 ' + fmt(3, 0) + ' m' + '）',
    'Paused: Too close to M4E-2 (14 m horizontal, 3 m vertical)',
  ],
  ['航线执行：飞向航点 ' + 4 + ' 未被设备确认：' + '超时：设备未在 5 秒内确认', 'Route: fly to waypoint 4 not confirmed by the device: Timed out: the device did not confirm within 5 s'],
  ['航点 ' + 2 + ' 动作「' + '拍照' + '」：' + '设备已确认', 'Waypoint 2 action "Take photo": Confirmed'],
  ['未获得云端控制权' + '：' + '飞手拒绝授权或授权失败', 'No cloud control: The pilot declined, or approval failed'],
  // ControlService + ManualControlService
  ['飞行控制失效：' + '遥控器夺权（飞手触发返航或 B 控夺权）', 'Flight control lost: RC took over (the pilot triggered RTH, or controller B took control)'],
  ['无法进入杆量控制：' + '飞行器不在空中（请先起飞）', 'Cannot start virtual stick: The aircraft is not in the air (take off first)'],
  ['14:03:22' + ' ' + '退出杆量控制：' + '已发送「' + '一键返航' + '」', '14:03:22 Virtual stick ended: Sent "Return home"'],
  // ProximityMonitor
  [
    'M4E-1' + ' 与 ' + 'M4E-2' + '：水平 ' + fmt(18, 0) + ' m' + '，高度差未知' + '（' + 'M4E-2' + ' 已 ' + 4 + ' 秒没有位置数据，按最后位置判断）',
    'M4E-1 and M4E-2: 18 m horizontal, vertical unknown (no position from M4E-2 for 4 s: judged by the last position)',
  ],
  [
    '仍与 ' + 'M4E-1' + ' 太近（水平 ' + fmt(16, 0) + ' m，推算最近 ' + fmt(9, 0) + ' m，阈值 ' + fmt(20, 0) + ' m' + '），请先拉开距离再恢复',
    'Still too close to M4E-1 (16 m horizontal, predicted closest 9 m, threshold 20 m). Move them apart before resuming.',
  ],
  // DeviceMessageService
  ['上视' + '避障已开启但当前未工作', 'Upward obstacle sensing is on but not working'],
  [
    '告警码 ' + '0x16100083' + '，模块 ' + 3 + '，空中' + '（大疆未提供遥控器场景的 HMS 文案表，请对照 Pilot 2 上的提示）',
    'Alert code 0x16100083, module 3, in the air (DJI gives no HMS text table for the remote-controller setup; see the message in Pilot 2)',
  ],
  // FleetSafetyConfigService, importers, DeviceRegistry, ApiExceptionHandler
  ['反应时间' + '必须在 ' + fmt(0, 0) + '–' + fmt(10, 0) + ' 之间', 'Reaction time must be between 0 and 10'],
  ['第 ' + 7 + ' 行缺少高度，且未提供默认高度', 'Line 7 has no height and no default height is set'],
  ['设备 ' + 'M4E-2' + '（' + '1581F6Q8D24AB00C1234' + '）未启用，请先在设置页「设备」中启用', 'Device M4E-2 (1581F6Q8D24AB00C1234) is not enabled. Enable it first in Settings → Devices.'],
  ['参数不合法：' + 'name' + ' ' + '不能为空', 'Invalid parameter: name must not be empty'],
]

describe('backend platform messages in English', () => {
  it('stay Chinese in Chinese mode', () => {
    expect(tb(CASES[0]![0])).toBe(CASES[0]![0])
  })

  it.each(CASES)('%s', (zh, en) => {
    lang.value = 'en'
    expect(tb(zh)).toBe(en)
  })
})
