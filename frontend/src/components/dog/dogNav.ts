/**
 * Outdoor navigation of the new dog system (docs/dog/ui-design.md 19): what the card, the next-step line, the safety
 * row and the map say about a dog's `nav` state. Pure functions, so the wording is tested once. States and reasons are
 * strings on the dog's side (protocol.md 9.3): unknown ones are shown as the dog wrote them.
 */
import type { Dog2, Dog2Nav, Dog2NavCapability, Dog2NavPoint, Dog2NavReady, Dog2SpeedLevel } from '@/api/dogv2'
import { t, tc } from '@/i18n'

export function dualHeading(dog: Dog2 | null | undefined): boolean {
  return dog?.nav?.ready?.heading_start_ok != null || dog?.capabilities?.position?.heading?.includes('receiver') === true
}

export function headingWait(dog: Dog2 | null | undefined): string | null {
  if (!dualHeading(dog)) return null
  const ready = dog?.nav?.ready
  // Older boards lack the explicit start gate. A fresh receiver heading can precede their idle nav update.
  const waiting = ready?.heading_start_ok === false
    || (ready?.heading_start_ok == null && ready?.heading === 'none' && dog?.position?.heading_source === 'none')
  if (!waiting) return null
  return ready?.gnss === 'fix' ? t('位置已获取，正在确认朝向') : t('正在确认双天线朝向')
}

/** A task is on: the dog is starting, walking or paused (it holds the remaining points). */
export function navTaskOn(nav: Dog2Nav | null | undefined): boolean {
  const s = nav?.state
  return s === 'starting' || s === 'running' || s === 'paused'
}

/** The task's points, from either shape: the dog's [[lat, lon]…] or the platform's [{lat, lon, name}…]. */
export function navPoints(nav: Dog2Nav | null | undefined): Dog2NavPoint[] {
  const out: Dog2NavPoint[] = []
  for (const p of nav?.points ?? []) {
    if (Array.isArray(p)) {
      if (typeof p[0] === 'number' && typeof p[1] === 'number') out.push({ lat: p[0], lon: p[1] })
    } else if (p && typeof p.lat === 'number' && typeof p.lon === 'number') out.push({ lat: p.lat, lon: p.lon, name: p.name ?? null })
  }
  return out
}

/** Short labels of the dog's pause / end reasons (protocol.md 9.3). */
export const NAV_REASON: Record<string, string> = {
  operator: t('操作员暂停'),
  operator_away: t('操作员页面没有响应'),
  takeover: t('人工接管'),
  link_wait: t('等平台（网络断过）'),
  link_lost: t('和平台断开'),
  gnss_poor: t('GPS 变差'),
  heading_unknown: t('朝向不可信'),
  loc_stale: t('定位过期'),
  lidar_stale: t('避障雷达没数据'),
  blocked: t('前方有障碍，绕不过去'),
  no_path: t('规划不出路线'),
  outside_area: t('超出允许区域'),
  timeout: t('超时'),
  tilt: t('姿态超限'),
  feedback_stale: t('运动主机状态包断了'),
  motion_refused: t('运动进程拒绝'),
  stopped: t('按了停止'),
  soft_estop: t('软急停'),
  cancelled: t('人工结束'),
  arrived: t('到了'),
  error: t('出错'),
}

/** What the operator can do while paused for this reason. */
const NAV_ADVICE: Record<string, string> = {
  operator: t('点「继续」接着走'),
  operator_away: t('点「继续」接着走'),
  takeover: t('松开方向键后点「继续」接着走'),
  link_wait: t('网络回来狗也不自己走：点「继续」'),
  gnss_poor: t('等 GPS 恢复后点「继续」'),
  heading_unknown: t('用按住移动沿一个方向直走 15 米以上（中途别按转向键）对齐朝向，再点「继续」'),
  loc_stale: t('等定位恢复后点「继续」'),
  lidar_stale: t('等雷达恢复，或关掉避障后「继续」'),
  blocked: t('绕开障碍后「继续」、关掉避障，或按住方向键接管'),
  no_path: t('绕开障碍后「继续」、关掉避障，或按住方向键接管'),
}

/** Reasons for which "turn avoidance off" is offered while paused (avoidance being on). */
export const AVOIDANCE_REASONS = new Set(['blocked', 'no_path', 'lidar_stale'])

/** The reason in words: the platform's label for a known code, else the dog's own text, else the code. */
export function navReason(nav: Pick<Dog2Nav, 'reason' | 'reason_text'> | null | undefined): string {
  if (!nav?.reason) return nav?.reason_text ?? ''
  return NAV_REASON[nav.reason] ?? nav.reason_text ?? nav.reason
}

/** The dog's own text, when it says more than the label. */
export function navReasonDetail(nav: Pick<Dog2Nav, 'reason' | 'reason_text'> | null | undefined): string | null {
  const txt = nav?.reason_text
  if (!txt || !nav?.reason || !NAV_REASON[nav.reason] || txt === NAV_REASON[nav.reason]) return null
  return txt
}

export function navAdvice(reason: string | null | undefined): string | null {
  return reason ? (NAV_ADVICE[reason] ?? null) : null
}

const SPEED_NAME: Record<string, string> = { slow: t('慢'), mid: t('中'), fast: t('快') }
/** "慢 0.12 m/s"; a level the platform has no word for keeps the dog's id. */
export function speedLabel(l: Dog2SpeedLevel): string {
  return `${SPEED_NAME[l.id] ?? l.id} ${l.mps} m/s`
}
export function speedName(id: string | null | undefined): string {
  return id ? (SPEED_NAME[id] ?? id) : '—'
}
/** Speed levels the dog offers; none means: no selector, no level sent. */
export function speedLevels(cap: Dog2NavCapability | null | undefined): Dog2SpeedLevel[] {
  return Array.isArray(cap?.speed_levels) ? cap.speed_levels.filter((l) => l && typeof l.id === 'string') : []
}

export function metresText(m: number | null | undefined): string {
  return m == null || !Number.isFinite(m) ? '—' : `${Math.round(m)} m`
}

export function etaText(s: number | null | undefined): string {
  if (s == null || !Number.isFinite(s)) return '—'
  return s >= 60 ? t('约 {n} 分钟', { n: Math.round(s / 60) }) : t('约 {n} 秒', { n: Math.max(0, Math.round(s)) })
}

export interface ReadyItem { key: string; label: string; ok: boolean | null; text: string }

/** How the heading gets aligned (user, 2026-11-11): a straight walk of 15 m or more in one direction; speed does not matter. */
const HEADING_HINT = (): string => t('朝向没对齐：用按住移动沿一个方向直走 15 米以上，中途别按转向键')

const GOOD_HEADING = new Set(['imu_aligned', 'receiver'])

/**
 * The readiness line (nav.ready): GPS, heading, localisation, lidar, and the navigation parts when they are down.
 * ok = null: not known (the lidar before the parts are started).
 */
export function readyItems(ready: Dog2NavReady | null | undefined, dual = false): ReadyItem[] {
  if (!ready) return []
  const items: ReadyItem[] = []
  const gnssOk = ready.gnss == null ? null : ready.gnss === 'fix'
  items.push({ key: 'gnss', label: 'GPS', ok: gnssOk, text: gnssOk === false ? t('GPS：{state}', { state: GNSS_WORD[ready.gnss!] ?? ready.gnss! }) : '' })
  const hOk = ready.heading_start_ok ?? (ready.heading == null ? null : GOOD_HEADING.has(ready.heading))
  items.push({ key: 'heading', label: t('朝向'), ok: hOk, text: hOk === false && dual ? t('正在确认双天线朝向') : hOk === false ? HEADING_HINT() : '' })
  const locOk = ready.loc == null ? null : ready.loc
  items.push({ key: 'loc', label: t('定位'), ok: locOk, text: locOk === false ? t('定位融合还没好') : '' })
  const lidarOk = ready.lidar ?? null
  items.push({ key: 'lidar', label: t('避障雷达'), ok: lidarOk, text: lidarOk === false ? t('雷达没数据') : '' })
  if (ready.nav2 === false) items.push({ key: 'nav2', label: t('导航部件'), ok: false, text: t('导航部件没起来（打开导航区时平台会让狗拉起）') })
  return items
}

/**
 * What the board's ready.text is about. The board writes only its first problem (dog-agent nav/core.py ready()), in
 * the order: ROS side, motion process, GPS, heading, localisation, navigation parts, lidar.
 */
const BOARD_TOPIC: [string, RegExp][] = [
  ['gnss', /^\s*(GPS|GNSS)/i],
  ['heading', /朝向|heading/i],   // i18n-ignore: matched against the board's text
  ['loc', /定位融合|locali[sz]ation/i],   // i18n-ignore: matched against the board's text
  ['nav2', /导航部件|导航进程|navigation (parts|process)/i],   // i18n-ignore: matched against the board's text
  ['lidar', /雷达|lidar/i],   // i18n-ignore: matched against the board's text
]

/**
 * The readiness lines under the ready row, one per problem (ui-design.md 20.5): the platform's line for each item that
 * is not ready, and the board's own text only when it says something the list does not have yet. The board's GPS
 * text replaces the platform's ("GPS 精度因子 3.2，超过 2.5" says more than "GPS：single"); for the heading the
 * platform's line stays, as it gives the right way to align.
 */
export function readyLines(ready: Dog2NavReady | null | undefined, dual = false): string[] {
  const bad = readyItems(ready, dual).filter((r) => r.ok === false)
  const board = ready?.text?.trim() || null
  const about = board ? BOARD_TOPIC.find(([, re]) => re.test(board))?.[0] ?? null : null
  const lines = bad.map((r) => (r.key === 'gnss' && about === 'gnss' ? board! : r.text))
  if (board && !(about && bad.some((r) => r.key === about))) lines.push(board)
  return lines
}

const STATE_TEXT: Record<string, string> = {
  idle: t('空闲'), starting: t('开始中'), running: t('走着'), paused: tc('state', '暂停'), arrived: t('到了'), ended: tc('state', '结束'),
}
/** The task state in words; a state the platform does not know is shown as the dog wrote it. */
export function navStateText(nav: Dog2Nav | null | undefined): string {
  return nav ? STATE_TEXT[nav.state] ?? nav.state : t('没有状态')
}

/** The folded navigation group's line: the task while one is on, else the state and the ready items. */
export function navSummary(nav: Dog2Nav | null | undefined): { text: string; cls: '' | 'warnc' | 'dim' | 'run' } {
  if (!nav) return { text: t('还没收到狗的导航状态'), cls: 'dim' }
  if (navTaskOn(nav)) {
    const left = nav.to_end_m != null ? t(' · 离终点 {d} m', { d: Math.round(nav.to_end_m) }) : ''
    return { text: navShort(nav) + left, cls: nav.state === 'paused' ? 'warnc' : 'run' }
  }
  const items = readyItems(nav.ready)
  const marks = items.map((r) => `${r.label} ${r.ok === true ? '✓' : r.ok === false ? '✕' : '–'}`).join(' ')
  return { text: marks ? `${navStateText(nav)} · ${marks}` : navStateText(nav), cls: items.some((r) => r.ok === false) ? 'warnc' : '' }
}

/** The dog's GNSS words (as in its position reports). */
const GNSS_WORD: Record<string, string> = {
  none: t('没定位'), no_fix: t('没定位'), dr: t('推算定位'), stale: t('数据过期'), off: t('关着'), no_device: t('没有接收机'),
}

/** "走向第 2/3 个点" (1-based for people; the dog counts from 0). */
export function progressText(nav: Dog2Nav, points: Dog2NavPoint[]): string {
  const n = nav.count ?? points.length
  const i = nav.index ?? null
  if (i == null || !n) return ''
  const name = points[i]?.name
  return name ? t('走向第 {i}/{n} 个点（{name}）', { i: i + 1, n, name }) : t('走向第 {i}/{n} 个点', { i: i + 1, n })
}

/** One short line for the safety row and the next-step line while a task is on. */
export function navShort(nav: Dog2Nav): string {
  if (nav.state === 'paused') return t('导航暂停：{reason}', { reason: navReason(nav) || '—' })
  if (nav.state === 'starting') return t('正在开始导航…')
  const n = nav.count ?? 0
  return nav.index != null && n ? t('导航中 · {i}/{n}', { i: nav.index + 1, n }) : t('导航中')
}
