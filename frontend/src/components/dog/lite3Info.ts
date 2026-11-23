/**
 * What the Lite3 area of the live page shows about the new dog system (ui-design.md 20): the always-visible chips, the
 * rows of the three data groups (motion and attitude, position and heading, board and video) and the one-line
 * summaries of folded groups. Everything comes from GET /api/v2/dogs as the platform has it; nothing is computed
 * that the dog did not report. Every group has a fixed number of rows ("—" when there is no value), so data coming
 * and going never changes a height (ui-design.md 5.9).
 */
import type { Dog2, Dog2Telemetry, Dog2Video } from '@/api/dogv2'
import { depthFrontShort } from '@/components/dogv2/depthFront'
import { t } from '@/i18n'
import { dualHeading } from './dogNav'

export interface InfoRow { label: string; value: string; cls?: '' | 'warnc' | 'badc' | 'dim'; title?: string }

/** "新系统在控" / "老系统在控" / "正在切换" / "离线". */
export function modeText(d: Dog2 | null): string {
  if (!d || !d.online) return t('离线')
  if (d.mode === 'new') return t('新系统在控')
  if (d.mode === 'old') return t('老系统在控')
  return d.mode ? t('正在切换') : t('模式未知')
}

/** Seconds since the motion host's last state packet, as the board reported it (null = none). */
export function packetAge(d: Dog2 | null): number | null {
  const a = d?.status?.motion_host?.feedback_age_s
  return typeof a === 'number' && Number.isFinite(a) ? a : null
}

/** The panel's status line after "在线". */
export function lite3Online(d: Dog2 | null): { cls: string; text: string } {
  if (!d) return { cls: '', text: t('没有数据') }
  if (d.mode !== 'new') return { cls: 'warn', text: t('在线 · {mode}', { mode: modeText(d) }) }
  const a = packetAge(d)
  if (a == null || a > 1) return { cls: 'warn', text: t('在线 · 收不到运动主机的状态包') }
  return { cls: 'ok', text: t('在线 · 新系统在控') }
}

function gnssText(state: string): string {
  const m: Record<string, string> = {
    fix: t('已定位'), no_fix: t('搜星中'), no_device: t('没插 GPS'), no_permission: t('GPS 没有权限'),
    busy: t('GPS 被别的程序占着'), no_data: t('GPS 没有数据'), starting: t('GPS 正在启动'), off: t('GPS 没开'), error: t('GPS 出错'),
  }
  return m[state] ?? state
}

/** Short, for the chip row: "12 星" / "搜星中" / "—" (no GPS configured). */
export function gnssShort(d: Dog2 | null): { text: string; cls: '' | 'warnc' | 'dim' } {
  const s = d?.status?.gnss?.state
  if (!s) return { text: '—', cls: 'dim' }
  const p = d?.position
  if (s === 'fix' && p?.lat != null) return { text: p.sats != null ? t('{n} 星', { n: p.sats }) : gnssText('fix'), cls: '' }
  return { text: gnssText(s), cls: 'warnc' }
}

export function gnssRow(d: Dog2 | null): InfoRow {
  const g = d?.status?.gnss
  if (!g) return { label: t('GPS'), value: t('没配置'), cls: 'dim' }
  const p = d?.position
  if (g.state === 'fix' && p?.lat != null) {
    const parts = [gnssText('fix')]
    if (p.sats != null) parts.push(t('{n} 颗星', { n: p.sats }))
    if (p.hdop != null) parts.push(t('精度因子 {n}', { n: p.hdop.toFixed(1) }))
    if (p.fix && p.fix !== 'single') parts.push(p.fix)
    return { label: t('GPS'), value: parts.join(' · '), cls: p.fix === 'estimated' ? 'warnc' : '' }
  }
  return { label: t('GPS'), value: gnssText(g.state), cls: 'warnc', title: g.text || undefined }
}

export function headingRow(d: Dog2 | null): InfoRow {
  const p = d?.position
  const src = p?.heading_source
  if (!d?.status?.gnss) return { label: t('朝向'), value: t('没配置 GPS'), cls: 'dim' }
  if (!p || !src || src === 'none') return { label: t('朝向'), value: dualHeading(d) ? t('正在确认双天线朝向') : t('没对齐'), cls: 'warnc' }
  const deg = p.heading_deg != null ? ` ${Math.round(p.heading_deg)}°` : ''
  if (src === 'imu_aligned') {
    if (dualHeading(d)) return { label: t('朝向'), value: t('惯导接续') + deg, cls: 'warnc' }
    const m = p.heading_age_s != null ? Math.round(p.heading_age_s / 60) : null
    return { label: t('朝向'), value: (m == null ? t('惯导已对齐') : t('惯导已对齐（{n} 分钟前）', { n: m })) + deg, cls: '' }
  }
  if (src === 'receiver') return { label: t('朝向'), value: t('双天线') + deg, cls: '' }
  if (src === 'course') return { label: t('朝向'), value: t('按行进方向（站着不动时没有）') + deg, cls: 'warnc' }
  return { label: t('朝向'), value: src + deg, cls: '' }
}

function videoText(state: string): string {
  const m: Record<string, string> = { off: t('没在推（有人看时才推）'), starting: t('正在开始推流'), live: t('正在推'), error: t('推流出错') }
  return m[state] ?? state
}

export function videoRow(label: string, v: Dog2Video | undefined): InfoRow {
  if (!v) return { label, value: t('没有这一路'), cls: 'dim' }
  return { label, value: videoText(v.state), cls: v.state === 'error' ? 'warnc' : v.state === 'live' ? '' : 'dim' }
}

export function lastErrorRow(d: Dog2 | null): InfoRow {
  const e = d?.status?.last_error
  if (!e) return { label: t('板卡最近的错误'), value: t('无'), cls: 'dim' }
  const age = e.age_s != null ? t('（{n} 秒前）', { n: Math.round(e.age_s) }) : ''
  return { label: t('板卡最近的错误'), value: e.text + age, cls: 'warnc', title: e.code }
}

export function boardRow(d: Dog2 | null): InfoRow {
  return { label: t('板卡程序'), value: `${d?.software ?? '—'} · ${modeText(d)}`, cls: d?.mode === 'new' ? '' : 'warnc' }
}

// ---------------------------------------------------------------- the one-page Lite3 area (ui-design.md 20)

/** Telemetry while the new system holds the dog and it is fresh: the rule the card's other numbers use (stores/dog.ts). */
export function freshTel(d: Dog2 | null | undefined): Dog2Telemetry | null {
  return d && d.mode === 'new' && (d.telemetryAgeMs ?? Infinity) < 3000 ? d.telemetry : null
}

const num = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v)
function fx(v: unknown, digits: number): string {
  return num(v) ? v.toFixed(digits) : '—'
}
/** "0.30 / -0.80 / 12.00", or "—" when the dog did not send the three numbers. */
export function triple(a: unknown, digits = 2): string {
  return Array.isArray(a) && a.length >= 3 && a.slice(0, 3).every(num) ? a.slice(0, 3).map((x) => fx(x, digits)).join(' / ') : '—'
}
function secs(s: number | null | undefined): string {
  if (!num(s)) return '—'
  return s < 10 ? t('{n} 秒前', { n: s.toFixed(1) }) : s < 120 ? t('{n} 秒前', { n: Math.round(s) }) : t('{n} 分钟前', { n: Math.round(s / 60) })
}

/** Horizontal speed from the body velocity (x, y), as the audience page computes it; null without fresh telemetry. */
export function bodySpeed(d: Dog2 | null | undefined): number | null {
  const v = freshTel(d)?.vel_body
  return Array.isArray(v) && num(v[0]) && num(v[1]) ? Math.hypot(v[0], v[1]) : null
}

/** The heading for a chip: degrees, amber when it is only the direction of travel, "没对齐" when there is none. */
export function headingShort(d: Dog2 | null | undefined): { text: string; cls: '' | 'warnc' | 'dim'; title: string } {
  const row = headingRow(d ?? null)
  if (!d?.status?.gnss) return { text: '—', cls: 'dim', title: row.value }
  const p = d.position
  const src = p?.heading_source
  if (!p || !src || src === 'none') return { text: t('没对齐'), cls: 'warnc', title: row.value }
  if (!num(p.heading_deg)) return { text: '—', cls: 'warnc', title: row.value }
  return { text: `${Math.round(p.heading_deg)}°`, cls: row.cls === 'warnc' ? 'warnc' : '', title: row.value }
}

/** The lidar's nearest obstacle straight ahead (nav.front_m), reported by a dog that navigates with avoidance on. */
export function lidarFrontShort(d: Dog2 | null | undefined): { text: string; cls: '' | 'warnc' | 'dim'; title: string } {
  if (!d?.navCapability) return { text: '—', cls: 'dim', title: t('这只狗没有报导航能力') }
  const n = d.nav
  if (!n || !num(n.front_m)) return { text: '—', cls: 'dim', title: t('避障开着时狗才报这个数') }
  const age = num(n.ageMs) ? n.ageMs : null
  const old = age != null && age > 3000
  return { text: `${n.front_m.toFixed(1)} m`, cls: old ? 'warnc' : '', title: old ? t('导航状态 {age}', { age: secs(age / 1000) }) : t('雷达看到的正前方最近的障碍') }
}

export interface Chip { key: string; label: string; value: string; cls: '' | 'warnc' | 'badc' | 'dim'; title?: string }

/**
 * The eight always-visible numbers (ui-design.md 20.3). Battery, state and packet age come from the card's own state
 * (the same values as the safety row and the next-step line); the rest straight from the dog's report.
 */
export function lite3Chips(d: Dog2 | null, own: { battery: number | null; state: string | null | undefined; feedbackAge: number | null }): Chip[] {
  const b = own.battery
  const fb = own.feedbackAge
  const v = bodySpeed(d)
  const gps = gnssShort(d)
  const head = headingShort(d)
  const depth = depthFrontShort(d)
  const lidar = lidarFrontShort(d)
  return [
    { key: 'battery', label: t('电量'), value: b == null ? '—' : `${b}%`, cls: b == null ? 'dim' : b < 20 ? 'badc' : b < 35 ? 'warnc' : '' },
    { key: 'state', label: t('状态'), value: own.state || '—', cls: own.state ? '' : 'dim', title: own.state ?? undefined },
    { key: 'speed', label: t('速度'), value: v == null ? '—' : `${v.toFixed(2)} m/s`, cls: v == null ? 'dim' : '', title: t('机身速度（运动主机报的）') },
    { key: 'packet', label: t('状态包'), value: fb == null ? '—' : t('{n} 秒前', { n: fb.toFixed(1) }), cls: fb == null ? 'dim' : fb > 1 ? 'warnc' : '' },
    { key: 'gps', label: t('GPS'), value: gps.text, cls: gps.cls, title: gnssRow(d).value },
    { key: 'heading', label: t('朝向'), value: head.text, cls: head.cls, title: head.title },
    { key: 'depth', label: t('深度前方'), value: depth.text, cls: depth.cls, title: depth.title },
    { key: 'lidar', label: t('雷达前方'), value: lidar.text, cls: lidar.cls, title: lidar.title },
  ]
}

/** 运动与姿态: the state packet as the board passes it on. Grey when it is not fresh (the last values received). */
export function motionRows(d: Dog2 | null): InfoRow[] {
  const tel = d?.telemetry ?? null
  const cls: InfoRow['cls'] = freshTel(d) ? '' : 'dim'
  const st = tel ? `${tel.basic_state_name ?? '—'}${num(tel.basic_state) ? ` (${tel.basic_state})` : ''}` : '—'
  return [
    { label: t('运动状态'), value: st, cls },
    { label: t('步态码 / 运动码'), value: tel ? `${fx(tel.gait_state, 0)} / ${fx(tel.motion_state, 0)}` : '—', cls, title: 'gait_state / motion_state' },
    { label: t('姿态（横滚 / 俯仰 / 偏航）'), value: triple(tel?.rpy, 1), cls, title: t('狗报的原值，单位还没实测') },
    { label: t('角速度'), value: triple(tel?.rpy_rate, 2), cls, title: t('狗报的原值，单位还没实测') },
    { label: t('机身速度 x / y / z'), value: unit(triple(tel?.vel_body), 'm/s'), cls },
    { label: t('世界速度 x / y / z'), value: unit(triple(tel?.vel_world), 'm/s'), cls },
    { label: t('加速度 x / y / z'), value: unit(triple(tel?.acc), 'm/s²'), cls },
    { label: t('运动主机位置 x / y / z'), value: unit(triple(tel?.pos_world), 'm'), cls },
    { label: t('固件'), value: tel ? fx(tel.firmware, 0) : '—', cls },
  ]
}
function unit(v: string, u: string): string {
  return v === '—' ? v : `${v} ${u}`
}

function fixText(fix: string | null | undefined): string {
  const m: Record<string, string> = {
    none: t('没定位'), single: t('单点'), dgps: t('差分'), rtk_float: t('RTK 浮点'), rtk_fixed: t('RTK 固定'), estimated: t('推算'),
  }
  return fix ? m[fix] ?? fix : '—'
}

/** 位置与朝向: GPS, heading and the navigation's fused position. */
export function positionRows(d: Dog2 | null): InfoRow[] {
  const p = d?.position ?? null
  const g = d?.status?.gnss
  const fixed = g?.state === 'fix' && p?.lat != null
  const fix: InfoRow = !g ? { label: t('定位'), value: t('没配置 GPS'), cls: 'dim' }
    : fixed ? { label: t('定位'), value: fixText(p!.fix), cls: p!.fix === 'estimated' ? 'warnc' : '' }
      : { label: t('定位'), value: gnssText(g.state), cls: 'warnc', title: g.text || undefined }
  const pose = d?.nav?.pose
  return [
    fix,
    { label: t('经纬度'), value: p && num(p.lat) && num(p.lon) ? `${p.lat.toFixed(6)}, ${p.lon.toFixed(6)}` : '—', title: 'WGS84' },
    { label: t('海拔'), value: p && num(p.alt_m) ? `${p.alt_m.toFixed(1)} m` : '—' },
    { label: t('卫星 · 精度因子'), value: p ? `${num(p.sats) ? t('{n} 颗', { n: p.sats }) : '—'} · ${fx(p.hdop, 1)}` : '—' },
    { label: t('位置收到'), value: d && num(d.positionAgeMs) ? secs(d.positionAgeMs / 1000) : '—', cls: d && num(d.positionAgeMs) && d.positionAgeMs > 5000 ? 'warnc' : '',
      title: p && num(p.fix_age_s) ? t('板卡发出时这组定位已经 {n} 秒', { n: p.fix_age_s.toFixed(1) }) : undefined },
    { label: t('地面速度'), value: p && num(p.speed_mps) ? `${p.speed_mps.toFixed(2)} m/s` : '—' },
    { label: t('行进方向'), value: p && num(p.course_deg) ? `${Math.round(p.course_deg)}°` : '—', title: t('速度低于约 0.4 m/s 时狗不报') },
    headingRow(d),
    { label: t('天线'), value: p?.antenna ?? '—' },
    { label: t('导航用的融合位置'), value: pose && num(pose.lat) && num(pose.lon) ? `${pose.lat.toFixed(6)}, ${pose.lon.toFixed(6)}${num(pose.std_m) ? ` · ±${pose.std_m.toFixed(1)} m` : ''}` : '—',
      cls: d?.navCapability ? '' : 'dim' },
  ]
}

/** 板卡与视频: software, mode, who is in control, the last error, the video streams and how old each part is. */
export function boardRows(d: Dog2 | null, mine: boolean): InfoRow[] {
  const ctl = d?.status?.control
  const held = num(ctl?.held_s) ? t('（{n} 秒）', { n: Math.round(ctl!.held_s!) }) : ''
  const who = !d ? '—' : mine ? t('这个页面') + held : d.control.held ? (d.control.label || t('别处')) + held : t('没人')
  const ages = d ? [
    t('状态 {n}', { n: fx(num(d.statusAgeMs) ? d.statusAgeMs / 1000 : null, 1) }),
    t('遥测 {n}', { n: fx(num(d.telemetryAgeMs) ? d.telemetryAgeMs / 1000 : null, 1) }),
    t('位置 {n}', { n: fx(num(d.positionAgeMs) ? d.positionAgeMs / 1000 : null, 1) }),
    ...(d.navCapability ? [t('导航 {n}', { n: fx(num(d.nav?.ageMs) ? d.nav!.ageMs! / 1000 : null, 1) })] : []),
  ] : []
  const agesText = d ? t('{list} 秒前', { list: ages.join(' · ') }) : '—'
  return [
    { label: t('板卡程序'), value: d?.software ?? '—' },
    { label: t('新老模式'), value: modeText(d), cls: d?.mode === 'new' ? '' : 'warnc' },
    { label: t('运动网关'), value: d?.status?.gateway ?? d?.gateway ?? '—' },
    { label: t('谁在控'), value: who },
    { label: t('平台里启用'), value: !d ? '—' : d.enabled ? t('是') : t('否'), cls: d && !d.enabled ? 'warnc' : '' },
    lastErrorRow(d),
    videoRow(t('彩色视频'), d?.video?.rgb),
    videoRow(t('深度视频'), d?.video?.depth),
    { label: t('数据多久前'), value: agesText },
  ]
}

// ---------------------------------------------------------------- one-line summaries of folded groups

export function motionSummary(d: Dog2 | null): { text: string; cls: '' | 'warnc' | 'dim' } {
  const tel = d?.telemetry
  if (!tel) return { text: t('还没收到遥测'), cls: 'dim' }
  if (!freshTel(d)) return { text: t('遥测 {age}', { age: secs(num(d?.telemetryAgeMs) ? d!.telemetryAgeMs! / 1000 : null) }), cls: 'warnc' }
  return { text: `${tel.basic_state_name ?? '—'} · ${t('姿态 {rpy}', { rpy: triple(tel.rpy, 1) })}`, cls: '' }
}

export function positionSummary(d: Dog2 | null): { text: string; cls: '' | 'warnc' | 'dim' } {
  const g = gnssRow(d)
  const h = headingShort(d)
  return { text: `${g.value} · ${t('朝向 {h}', { h: h.text })}`, cls: g.cls === 'warnc' || h.cls === 'warnc' ? 'warnc' : g.cls === 'dim' ? 'dim' : '' }
}

export function boardSummary(d: Dog2 | null): { text: string; cls: '' | 'warnc' | 'dim' } {
  const e = d?.status?.last_error
  const parts = [d?.software ?? '—', modeText(d), e ? t('最近的错误：{text}', { text: e.text }) : t('没有错误')]
  return { text: parts.join(' · '), cls: e || d?.mode !== 'new' ? 'warnc' : '' }
}
