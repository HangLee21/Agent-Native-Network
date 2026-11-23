/**
 * The Lite3 area's new-system rows (2026-11-11 review, ui-design.md 20): board and mode, motion host packets, GPS,
 * heading, video, last error; the always-visible chips; the three data groups with a fixed number of rows; the
 * summaries of folded groups. No old-system wording (SDK, dog team's web page) is left in what the card can say.
 */
import { describe, expect, it } from 'vitest'
import type { Dog2 } from '@/api/dogv2'
import {
  boardRow, boardRows, boardSummary, gnssRow, gnssShort, headingRow, lastErrorRow, lite3Chips, lite3Online, motionRows, motionSummary,
  positionRows, positionSummary, videoRow,
} from '@/components/dog/lite3Info'

function dog(over: Partial<Dog2> = {}): Dog2 {
  return {
    id: 'lite3-01', label: 'Lite3', model: 'lite3', software: '0.2.0', online: true, enabled: true, mode: 'new', gateway: 'active',
    statusAgeMs: 300, telemetryAgeMs: 100, telemetry: null, lastSeenAt: 1,
    status: { mode: 'new', motion_host: { feedback_age_s: 0.02 }, gnss: { state: 'fix' }, last_error: null },
    position: { fix: 'single', lat: 29.61, lon: 103.61, sats: 12, hdop: 1.2, heading_source: 'imu_aligned', heading_deg: 91.4, heading_age_s: 130 },
    control: { held: false, mine: false, session: null, endedReason: null },
    video: { rgb: { path: 'dog/lite3-01-rgb', whep: null, state: 'live' }, depth: { path: 'dog/lite3-01-depth', whep: null, state: 'off' } },
    ...over,
  } as Dog2
}

describe('Lite3 card rows on the new dog system', () => {
  it('status line: in control, no packets, other mode', () => {
    expect(lite3Online(dog())).toEqual({ cls: 'ok', text: '在线 · 新系统在控' })
    expect(lite3Online(dog({ status: { mode: 'new', motion_host: { feedback_age_s: 3 } } })).text).toBe('在线 · 收不到运动主机的状态包')
    expect(lite3Online(dog({ mode: 'old' })).text).toBe('在线 · 老系统在控')
  })

  it('board row shows the software version and who is in control', () => {
    expect(boardRow(dog()).value).toBe('0.2.0 · 新系统在控')
    expect(boardRow(dog({ online: false })).value).toBe('0.2.0 · 离线')
  })

  it('GPS: fixed with satellites and HDOP, or why not', () => {
    expect(gnssShort(dog()).text).toBe('12 星')
    expect(gnssRow(dog()).value).toBe('已定位 · 12 颗星 · 精度因子 1.2')
    const noFix = dog({ status: { mode: 'new', gnss: { state: 'no_fix' } }, position: null })
    expect(gnssShort(noFix)).toEqual({ text: '搜星中', cls: 'warnc' })
    expect(gnssRow(dog({ status: { mode: 'new', gnss: { state: 'no_device' } } })).value).toBe('没插 GPS')
    expect(gnssRow(dog({ status: { mode: 'new' } })).value).toBe('没配置')
    expect(gnssShort(dog({ status: { mode: 'new' } })).text).toBe('—')
  })

  it('heading: aligned and how long ago, course only, not yet', () => {
    expect(headingRow(dog()).value).toBe('惯导已对齐（2 分钟前） 91°')
    const course = dog({ position: { fix: 'single', lat: 1, lon: 1, heading_source: 'course', heading_deg: 10 } })
    expect(headingRow(course).value).toBe('按行进方向（站着不动时没有） 10°')
    const none = dog({ position: { fix: 'single', lat: 1, lon: 1, heading_source: 'none' } })
    // only the fact: how to align is said once, in the navigation readiness (ui-design.md 20.5)
    expect(headingRow(none)).toMatchObject({ value: '没对齐', cls: 'warnc' })
  })

  it('video and the last error', () => {
    expect(videoRow('彩色视频', dog().video.rgb).value).toBe('正在推')
    expect(videoRow('深度视频', dog().video.depth).value).toBe('没在推（有人看时才推）')
    expect(lastErrorRow(dog()).value).toBe('无')
    const err = dog({ status: { mode: 'new', last_error: { code: 'gateway', text: '状态包中断', age_s: 12 } } })
    expect(lastErrorRow(err)).toMatchObject({ value: '状态包中断（12 秒前）', cls: 'warnc', title: 'gateway' })
  })

  it('nothing the card can say mentions the old system', () => {
    const all = [lite3Online(dog()).text, boardRow(dog()).value, gnssRow(dog()).value, headingRow(dog()).value]
    for (const s of all) expect(s).not.toMatch(/SDK|狗方/)
  })
})

const TEL = {
  basic_state: 6, basic_state_name: 'FORCE_CONTROL', battery_pct: 76, rpy: [0.3, -0.8, 12], rpy_rate: [0, 0.01, 0], acc: [0, 0, 9.8],
  vel_body: [0.3, 0.4, 0], vel_world: [0.1, 0.2, 0], pos_world: [1.5, -2, 0], feedback_age_s: 0.02, gait_state: 0, motion_state: 1, firmware: 98,
  depth_front: { dist_m: 1.8, valid_pct: 92, age_s: 0.1, state: 'ok' },
}

describe('the one-page Lite3 area (ui-design.md 20)', () => {
  const full = (over: Partial<Dog2> = {}) => dog({ telemetry: TEL, navCapability: { kind: 'gps', speed_levels: [] }, nav: { state: 'running', front_m: 4.24, ageMs: 300 }, ...over })
  const own = { battery: 76, state: 'FORCE_CONTROL', feedbackAge: 0.05 }

  it('eight chips, always the same eight, in the same order', () => {
    const c = lite3Chips(full(), own)
    expect(c.map((x) => [x.label, x.value])).toEqual([
      ['电量', '76%'], ['状态', 'FORCE_CONTROL'], ['速度', '0.50 m/s'], ['状态包', '0.1 秒前'],
      ['GPS', '12 星'], ['朝向', '91°'], ['深度前方', '1.80 m'], ['雷达前方', '4.2 m'],
    ])
    // nothing known: still eight chips, each "—"
    const empty = lite3Chips(dog({ telemetry: null, status: { mode: 'new' }, position: null }), { battery: null, state: null, feedbackAge: null })
    expect(empty).toHaveLength(8)
    expect(empty.map((x) => x.value)).toEqual(['—', '—', '—', '—', '—', '—', '—', '—'])
    // low battery, old packets, heading only from the direction of travel, no heading
    const warn = lite3Chips(full({ position: { fix: 'single', lat: 1, lon: 1, heading_source: 'course', heading_deg: 10 } }), { battery: 18, state: 'x', feedbackAge: 2 })
    expect(warn.find((x) => x.key === 'battery')?.cls).toBe('badc')
    expect(warn.find((x) => x.key === 'packet')?.cls).toBe('warnc')
    expect(warn.find((x) => x.key === 'heading')).toMatchObject({ value: '10°', cls: 'warnc' })
    expect(lite3Chips(full({ position: { fix: 'single', lat: 1, lon: 1, heading_source: 'none' } }), own).find((x) => x.key === 'heading')?.value).toBe('没对齐')
    // stale telemetry: no speed, no depth number (the depth line says why on hover)
    const stale = lite3Chips(full({ telemetryAgeMs: 5000 }), own)
    expect(stale.find((x) => x.key === 'speed')?.value).toBe('—')
    expect(stale.find((x) => x.key === 'depth')).toMatchObject({ value: '—', cls: 'warnc' })
    // a dog without navigation: the lidar chip is there, with "—"
    expect(lite3Chips(full({ navCapability: null }), own).find((x) => x.key === 'lidar')).toMatchObject({ value: '—', cls: 'dim', title: '这只狗没有报导航能力' })
  })

  it('motion and attitude: every field of the state packet, a fixed number of rows', () => {
    const rows = motionRows(full())
    expect(rows.map((r) => [r.label, r.value])).toEqual([
      ['运动状态', 'FORCE_CONTROL (6)'], ['步态码 / 运动码', '0 / 1'], ['姿态（横滚 / 俯仰 / 偏航）', '0.3 / -0.8 / 12.0'],
      ['角速度', '0.00 / 0.01 / 0.00'], ['机身速度 x / y / z', '0.30 / 0.40 / 0.00 m/s'], ['世界速度 x / y / z', '0.10 / 0.20 / 0.00 m/s'],
      ['加速度 x / y / z', '0.00 / 0.00 / 9.80 m/s²'], ['运动主机位置 x / y / z', '1.50 / -2.00 / 0.00 m'], ['固件', '98'],
    ])
    // no telemetry yet: the same rows with "—"
    expect(motionRows(dog()).map((r) => r.value)).toEqual(Array(9).fill('—'))
    // stale: the last values, grey
    expect(motionRows(full({ telemetryAgeMs: 5000 })).every((r) => r.cls === 'dim')).toBe(true)
  })

  it('position and heading: GPS, heading and the fused position, a fixed number of rows', () => {
    const d = full({
      position: { fix: 'rtk_fixed', lat: 22.5797512, lon: 113.9398, alt_m: 12, sats: 14, hdop: 0.9, fix_age_s: 0.3, speed_mps: 0.42, course_deg: 31.6,
        heading_deg: 30, heading_source: 'imu_aligned', heading_age_s: 20, antenna: 'ok' },
      positionAgeMs: 400, nav: { state: 'idle', pose: { lat: 22.57975, lon: 113.93981, std_m: 0.54 } },
    })
    const rows = positionRows(d)
    expect(rows.map((r) => [r.label, r.value])).toEqual([
      ['定位', 'RTK 固定'], ['经纬度', '22.579751, 113.939800'], ['海拔', '12.0 m'], ['卫星 · 精度因子', '14 颗 · 0.9'], ['位置收到', '0.4 秒前'],
      ['地面速度', '0.42 m/s'], ['行进方向', '32°'], ['朝向', '惯导已对齐（0 分钟前） 30°'], ['天线', 'ok'], ['导航用的融合位置', '22.579750, 113.939810 · ±0.5 m'],
    ])
    const searching = positionRows(dog({ status: { mode: 'new', gnss: { state: 'no_fix', text: '3 颗星' } }, position: null }))
    expect(searching).toHaveLength(10)
    expect(searching[0]).toMatchObject({ value: '搜星中', cls: 'warnc', title: '3 颗星' })
  })

  it('board and video: version, mode, gateway, who is in control, error, video, data ages', () => {
    const rows = boardRows(full({ control: { held: true, mine: true, session: 's', endedReason: null }, status: { mode: 'new', gateway: 'active', control: { session: 's', held_s: 42 } } }), true)
    expect(rows.map((r) => [r.label, r.value])).toEqual([
      ['板卡程序', '0.2.0'], ['新老模式', '新系统在控'], ['运动网关', 'active'], ['谁在控', '这个页面（42 秒）'], ['平台里启用', '是'],
      ['板卡最近的错误', '无'], ['彩色视频', '正在推'], ['深度视频', '没在推（有人看时才推）'], ['数据多久前', '状态 0.3 · 遥测 0.1 · 位置 — · 导航 0.3 秒前'],
    ])
    expect(boardRows(dog({ control: { held: true, mine: false, session: 'x', label: '狗旁的电脑', endedReason: null } }), false)[3]?.value).toBe('狗旁的电脑')
    expect(boardRows(null, false)).toHaveLength(9)
  })

  it('folded groups say the gist in one line', () => {
    expect(motionSummary(full())).toEqual({ text: 'FORCE_CONTROL · 姿态 0.3 / -0.8 / 12.0', cls: '' })
    expect(motionSummary(full({ telemetryAgeMs: 5000 }))).toEqual({ text: '遥测 5.0 秒前', cls: 'warnc' })
    expect(motionSummary(dog())).toEqual({ text: '还没收到遥测', cls: 'dim' })
    expect(positionSummary(full()).text).toBe('已定位 · 12 颗星 · 精度因子 1.2 · 朝向 91°')
    expect(boardSummary(full())).toEqual({ text: '0.2.0 · 新系统在控 · 没有错误', cls: '' })
    const err = full({ status: { mode: 'new', last_error: { code: 'gateway', text: '状态包中断' } } })
    expect(boardSummary(err)).toEqual({ text: '0.2.0 · 新系统在控 · 最近的错误：状态包中断', cls: 'warnc' })
  })
})
