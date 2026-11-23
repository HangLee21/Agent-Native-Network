import { afterEach, describe, expect, it } from 'vitest'
import { lang, tb } from '@/i18n'

afterEach(() => {
  lang.value = 'zh'
})

/** Messages built exactly as backend target/ and history/ build them, with realistic values. */
const CASES: [string, string][] = [
  // TargetService
  ['选定目标：' + '视频框选', 'Target picked: Video box select'],
  ['目标位置：' + '三维模型选点', 'Target position: from the 3D model'],
  ['AI 建议目标：' + 'person', 'AI suggests a target: person'],
  ['已采纳 AI 建议（' + 'AI 自动' + '）', 'AI suggestion accepted (AI auto)'],
  ['选点失败：' + '云台对准' + '失败：' + 'device timeout', 'Target pick failed: Gimbal aim failed: device timeout'],
  [
    '选点失败：' + '未收到激光测距数据：请确认飞手已在遥控器 Pilot 2 中打开激光测距（U-23）',
    'Target pick failed: No laser rangefinder data: make sure the pilot has turned on the laser rangefinder in Pilot 2 on the remote controller (U-23)',
  ],
  ['激光测距：' + '128 m', 'Laser range: 128 m'],
  ['复测不符：预期 120 m，实测 87 m', 'Re-check mismatch: expected 120 m, measured 87 m'],
  ['复测：目标在画面中（64 m）', 'Re-check: target in view (64 m)'],
  ['目标状态：' + 'MEASURING', 'Target state: MEASURING'],
  ['操作太频繁：对准指令至少间隔 ' + 800 + ' ms', 'Too fast: aim commands must be at least 800 ms apart'],
  ['本次飞行已有 ' + 3 + ' 次到达后复测距离与预期不符', 'This flight, the re-checked distance after arrival has differed from the expected one 3 times'],
  // TargetPlanner + TargetActionService
  ['不移动：' + '已在 30 m 内，原地保持', 'Not moving: already within 30 m'],
  ['已拒绝：' + '距目标 12 m，小于安全距离 15 m，不移动', 'Rejected: 12 m from the target, closer than the safe distance of 15 m: not moving'],
  ['动作被拒绝：' + '环绕半径 20 m 小于安全距离 30 m，不移动', 'Action rejected: Orbit radius 20 m is less than the safe distance of 30 m: not moving'],
  ['接近目标' + '中', 'Approaching the target'],
  ['已停止（' + 'operator' + '），飞机悬停', 'Stopped (operator); drone hovering'],
  ['飞行指令' + '超时' + '：' + 'no reply in 10 s', 'Flight command timed out: no reply in 10 s'],
  ['飞行指令' + 'CANCELLED' + '：' + 'cancelled', 'Flight command CANCELLED: cancelled'],
  ['目标动作完成：' + '环绕中（在环绕卡片中调整速度，用“退出环绕”停止）', 'Target action done: Orbiting (adjust the speed on the orbit card; use "Exit orbit" to stop)'],
  ['目标动作中止：' + '飞行失败（结果码 ' + 224002 + '）', 'Target action aborted: Flight failed (result code 224002)'],
  ['已到达：' + '目标附近', 'Arrived: near the target'],
  ['激光状态不是“正常”：' + 'TOO_FAR', 'Laser state is not "Normal": TOO_FAR'],
  ['估计误差 6.3 m 超过允许的 5.0 m', 'Estimated error 6.3 m exceeds the allowed 5.0 m'],
  // TargetConfigService
  ['最小距离' + '必须在 ' + '5' + '–' + '200' + ' 之间', 'Minimum distance must be between 5 and 200'],
  ['AI 倒计时' + '必须在 0–' + 30 + ' 之间', 'AI countdown must be between 0 and 30'],
  // AiAutonomyService
  ['不能开启 AI 自动模式：' + ['未获得云端控制权', 'DRC 链路未连接'].join('；'), 'Cannot turn on AI auto mode: No cloud control; DRC link not connected'],
  ['AI 自动模式已关闭：' + '操作员点击“停止 AI”（' + 'admin' + '）', 'AI auto mode off: Operator clicked "Stop AI" (admin)'],
  ['AI 接近目标' + '：' + 'person' + '，' + 10 + ' 秒后执行', 'AI: approach the target (person), runs in 10 s'],
  ['AI 环绕目标' + '，' + 5 + ' 秒后执行', 'AI: orbit the target, runs in 5 s'],
  [
    'AI 不能自动执行：' + ['冷却中（两次 AI 动作至少间隔 30 秒）', '已达每分钟 2 次上限'].join('；'),
    'AI cannot act on its own: Cooling down (at least 30 s between AI actions); Limit of 2 per minute reached',
  ],
  ['建议动作“' + 'APPROACH' + '”需要操作员确认（AI 级别 ' + 1 + '）', 'Suggested action "APPROACH" needs operator approval (AI level 1)'],
  // FlightRecorder
  ['飞行模式：' + '航线飞行', 'Flight mode: Route flight'],
  ['飞行模式：' + '状态 ' + 21, 'Flight mode: code 21'],
  ['航线执行：' + '飞往航点' + '（' + 3 + '/' + 12 + '）', 'Route: flying to waypoint (3/12)'],
  ['航线执行：' + 'PAUSED', 'Route: PAUSED'],
  ['开始记录（飞行器已在空中）', 'Recording started (aircraft already airborne)'],
  ['飞行器限高 ' + 120 + ' m', 'Aircraft altitude limit 120 m'],
  ['写入数据库失败（' + 'disk I/O error' + '），正在重试；飞行控制不受影响', 'Database write failed (disk I/O error); retrying. Flight control is not affected'],
  // HistoryService, RecordingClips, VideoArchiver
  ['这次飞行没有第 ' + 2 + ' 段视频', 'This flight has no video part 2'],
  ['录像服务出错（MediaMTX /get HTTP ' + 500 + '）', 'Recording service error (MediaMTX /get HTTP 500)'],
  ['连不上录像服务（MediaMTX ' + '/list' + '）：' + 'Connection refused', 'Cannot reach the recording service (MediaMTX /list): Connection refused'],
  ['已转为 ' + 720 + 'P' + '；有 ' + 1 + ' 段录像未能取回', 'Transcoded to 720p; parts not fetched: 1'],
  ['视频归档失败：' + 'MediaMTX /get HTTP 404' + '（' + 3 + ' 段录像都未能取回）', 'Video archive failed: MediaMTX /get HTTP 404 (none of the 3 parts could be fetched)'],
  [
    '重新归档没有取回更完整的录像（' + '流媒体服务器上没有本次飞行时段的录像' + '），保留原有录像',
    'The re-archive did not fetch a more complete video (The media server has no recording for the time of this flight); the existing video is kept',
  ],
  ['可用 3.2 GB，低于 5.0 GB' + '，已停止视频归档；飞行记录照常', '3.2 GB free, below 5.0 GB; video archiving stopped. Flight logs carry on as usual'],
  ['已自动开启直播用于录像（清晰度 ' + 1 + '）', 'Live video started automatically for recording (video quality 1)'],
]

describe('backend text from targets and flight logs', () => {
  it('stays Chinese in Chinese mode', () => {
    for (const [zh] of CASES) expect(tb(zh)).toBe(zh)
  })

  it.each(CASES)('translates %s', (zh, en) => {
    lang.value = 'en'
    expect(tb(zh)).toBe(en)
  })
})
