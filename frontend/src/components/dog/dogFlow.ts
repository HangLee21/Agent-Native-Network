/**
 * Flow bar and "next step" of each dog (docs/dog/ui-design.md 5.4, 9.0). One fixed-height line says what to press
 * next and why a button is grey; it follows the dog's reported state, never what the platform assumes.
 * Order where the dog side's documents are open is the official one (Lite3: moving mode before gait; S10: stand,
 * then RL control); such places are marked in the design's to-confirm list.
 */
import type { DogCommand, Lite3State, S10Job, S10State } from '@/api/dog'
import type { Dog2Nav } from '@/api/dogv2'
import { navShort, navTaskOn } from './dogNav'
import { lite3Pose, navActive, type Lite3Pose } from '@/stores/dog'
import { isEn, t } from '@/i18n'

export type SegState = 'done' | 'cur' | 'bad' | 'alt' | 'sent' | ''
export interface Seg {
  label: string
  state: SegState
  title?: string
}
export interface NextStep {
  cls: '' | 'ok' | 'warn' | 'bad' | 'run'
  icon?: string
  text: string
  /** One-click fix: an action key the panel knows, and its label. */
  fix?: { key: string; label: string; danger?: boolean }
}

export const S10_HOME = [0, 0, 0, 0, 25, 0]
/** Joint angles within 3° of the stowed pose [0,0,0,0,25,0]; null when the joints are unknown. */
export function s10Stowed(s: S10State | undefined): boolean | null {
  const deg = s?.topics.joints?.deg
  if (!deg || deg.length < 6 || deg.some((d) => d == null)) return null
  return deg.every((d, i) => Math.abs((d as number) - S10_HOME[i]!) <= 3)
}

export function s10RunningJob(s: S10State | undefined): S10Job | null {
  return s?.jobs.find((j) => j.state === 'running') ?? null
}

export function trustOk(s: S10State | undefined): boolean {
  const tr = (s?.map?.trust ?? {}) as { verdict?: string; withdrawn?: boolean }
  return tr.verdict === 'ok' && !tr.withdrawn
}

/** Job names by action, in Chinese: also sent to the backend inside stop labels (shared data stays in one language). */
const JOB_ZH: Record<string, string> = {
  posture: '姿态', gait: '步态', navigation_mode: '切换导航模式', navigate: '导航', nav_cancel: '取消导航', nav_speed: '导航速度',   // i18n-ignore: Chinese source names, shown via t()
  map: '地图操作', arm_enable: '启用电机', arm_move: '执行输入角度', arm_home: '收回机械臂', arm_gripper: '夹爪', arm_jog: '点动',   // i18n-ignore: Chinese source names, shown via t()
  arm_cart_step: '末端升降', snapshot: '拍照', solve: '求解', arm_plan: '执行到悬停位', radish_detect: '识别萝卜',   // i18n-ignore: Chinese source names, shown via t()
  skill_observe: '移动到观察位', skill_minimal: '一键抓取',   // i18n-ignore: Chinese source names, shown via t()
}
export function jobLabel(j: S10Job): string {
  const zh = JOB_ZH[j.action]
  return j.label ?? (zh ? t(zh) : j.action)
}
/** The job's name to send to the backend: always Chinese (in English mode the job's own label arrived translated). */
export function jobLabelZh(j: S10Job): string {
  return isEn() ? JOB_ZH[j.action] ?? j.action : jobLabel(j)
}

export function s10Flow(s: S10State | undefined, online: boolean, holding: boolean): Seg[] {
  if (!s || !online) return [{ label: t('连接'), state: 'bad' }, { label: t('站立'), state: '' }, { label: t('可走（RL）'), state: '' }, { label: t('任务'), state: '' }]
  const p = s.posture
  const rl = p === 'rl_control'
  const stood = p === 'standing' || rl
  const job = s10RunningJob(s)
  const nav = navActive(s.nav)
  const second: Seg = p === 'damping' ? { label: t('阻尼（软急停后）'), state: 'bad' }
    : p === 'sitting' ? { label: t('趴着（可用机械臂）'), state: 'alt' }
      : p === 'idle' ? { label: t('空闲 → 站立'), state: 'cur' }
        : { label: t('站立'), state: stood ? 'done' : 'cur' }
  const task = holding ? t('移动中') : nav ? t('导航中') : job ? (job.action === 'map' ? t('地图操作') : job.action.startsWith('arm') ? t('机械臂动作') : t('执行中')) : rl ? t('可以走') : t('走动 / 任务')
  return [
    { label: t('连接'), state: 'done' },
    { ...second, title: t('站立：让狗站起来；趴着时可以用机械臂') },
    { label: t('可走（RL）'), state: rl ? 'done' : stood ? 'cur' : '', title: t('可走状态（RL 控制）：按住移动需要这个状态') },
    { label: task, state: rl || job || holding || nav ? 'cur' : '' },
  ]
}

export interface S10NextInput {
  s: S10State | undefined
  online: boolean
  lost: boolean
  holding: boolean
  card: string
  lastFail: DogCommand | null
  stateAge: number | null
  jobSecs: number
}

export function s10Next(i: S10NextInput): NextStep {
  const { s, card } = i
  if (!s || !i.online) {
    return i.lost
      ? { cls: 'bad', text: t('S10 失联：平台的指令发不出去，请狗旁的人用实体遥控器') }
      : { cls: 'bad', text: t('S10 离线：下面是最后一次收到的数据，按钮都不可用') }
  }
  if (i.holding) return { cls: 'run', icon: 'play', text: t('移动中：松手即停；切到别的程序或设备也会立即停') }
  const job = s10RunningJob(s)
  if (job) {
    const params = { job: jobLabel(job), secs: i.jobSecs }
    const head = job.origin === 'other' ? t('正在执行：{job}（狗方网页发起） {secs} 秒', params) : t('正在执行：{job} {secs} 秒', params)
    const stop = job.stoppable ? undefined : t(' · 不能中途取消，紧急时长按「软急停」')
    return {
      cls: 'run', icon: 'spinner',
      text: `${head}${job.detail ? ` · ${job.detail}` : ''}${stop ?? ''}`,
      fix: job.stoppable ? { key: job.action === 'navigate' ? 'navcancel' : 'armstop', label: job.action === 'navigate' ? t('取消导航') : t('停止'), danger: true } : undefined,
    }
  }
  if (navActive(s.nav)) {
    const st = String(s.nav?.state ?? '')
    const d = s.nav?.detail ? ` · ${String(s.nav.detail)}` : ''
    return { cls: 'run', icon: 'play', text: t('导航中 · 狗的导航状态：{st}', { st }) + d, fix: { key: 'navcancel', label: t('取消导航'), danger: true } }
  }
  if (i.lastFail) {
    const why = i.lastFail.error ?? i.lastFail.detail ?? ''
    return { cls: 'bad', icon: 'x', text: t('上一个动作没成功：{label}', { label: i.lastFail.label }) + (why ? ` · ${why}` : ''), fix: { key: 'clearfail', label: t('知道了') } }
  }
  const stale = i.stateAge != null && i.stateAge > 10
  const fix = (f: NextStep['fix']) => (stale ? undefined : f)
  const staleNote = stale ? t('（状态 {n} 秒没更新）', { n: Math.round(i.stateAge!) }) : ''
  const p = s.posture
  if (p === 'damping') return { cls: 'warn', text: t('软急停后狗处于阻尼（关节不出力），约 3 秒后进入空闲；之后按①「站立」重新站起来') }
  const armCard = card === 'arm' || card === 'grasp'
  if (p === 'idle' && !armCard) return { cls: 'warn', text: t('狗在空闲状态（刚开机，或软急停之后）：空闲时只能站立，先按①「站立」') + staleNote, fix: fix({ key: 'stand', label: t('① 站立') }) }
  if (armCard) {
    if (p !== 'sitting' && p !== 'idle') return { cls: 'warn', text: t('机械臂和抓取要狗趴下（或空闲且低位静止）：先按「趴下」') + staleNote, fix: fix({ key: 'sit', label: t('趴下') }) }
    return card === 'arm'
      ? { cls: 'ok', icon: 'check', text: t('可以用机械臂。用完先「收回至安全位」，再回「准备」页站立') }
      : { cls: 'ok', icon: 'check', text: t('可以抓取：按下面 1 → 4 步的顺序做；拍照后到执行悬停位之前别动机械臂') }
  }
  if (card === 'nav') {
    if (!trustOk(s)) return { cls: 'warn', text: t('导航要先「定位可信」：去「建图」页加载地图或重新定位'), fix: { key: 'card:map', label: t('去定位') } }
    if (s10Stowed(s) === false) return { cls: 'warn', text: t('导航要求机械臂收好：先「收回机械臂」'), fix: fix({ key: 'armhome', label: t('收回机械臂') }) }
    return { cls: '', text: t('下一步：③填目标坐标 → ④「导航到目标」，狗会按自己的导航程序走过去') }
  }
  if (card === 'map') {
    const mapping = s.map?.mode === 'mapping'
    if (mapping && p !== 'rl_control') return { cls: 'warn', text: t('建图中，但狗还不能走：先回「准备 · 走动」页站立、进入可走状态，再按住移动绕场'), fix: { key: 'card:posture', label: t('去准备页') } }
    if (mapping) return { cls: '', text: t('建图中：用右下角「按住移动」让狗绕场走一圈，地图会长出来；走完填名字「保存」') }
    return { cls: '', text: t('要画新地图按 A①「开始建图」；要用已保存的地图，按 B①「加载」再看定位可信度') }
  }
  if (p === 'sitting') return { cls: '', text: t('下一步：按①「站立」让狗站起来（会先自动收回机械臂）') + staleNote, fix: fix({ key: 'stand', label: t('① 站立') }) }
  if (p === 'standing') return { cls: '', text: t('下一步：按②「进入可走状态」，之后才能按住移动') + staleNote, fix: fix({ key: 'rl', label: t('② 可走状态') }) }
  if (p === 'rl_control') return { cls: 'ok', icon: 'check', text: t('可以走了：按住右下角的方向键，松手即停。要用机械臂先按「趴下」') }
  return { cls: 'warn', text: t('狗报告的姿态是「{p}」：按狗的实际情况操作', { p: p ?? t('未知') }) }
}

export function lite3Flow(l: Lite3State | undefined, online: boolean, mine: boolean, holding: boolean): Seg[] {
  // moving mode is not a stage: lite3-01 walks right after standing (MQTT log 2026-11-10); the card keeps the button
  if (!l || !online) return [t('连接'), t('控制权'), t('站立'), t('可以走')].map((x, i) => ({ label: x, state: i === 0 ? 'bad' : '' }))
  const other = l.robot.controller === 'other' || (l.robot.controller === 'platform' && !mine)
  const pose = lite3Pose(l.robot.robot_state)
  const up = pose === 'standing'
  return [
    { label: t('连接'), state: 'done' },
    { label: other ? t('别处控制') : t('控制权'), state: other ? 'bad' : mine ? 'done' : 'cur', title: t('控制权：同一时间只能有一处控制 Lite3') },
    { label: pose === 'transition' ? t('正在起立…') : t('站立'), state: !mine ? '' : up ? 'done' : 'cur' },
    { label: holding ? t('移动中') : t('可以走'), state: mine && up ? 'cur' : '' },
  ]
}

export interface Lite3NextInput {
  l: Lite3State | undefined
  online: boolean
  mine: boolean
  holding: boolean
  pose: Lite3Pose
  marks: { moving: boolean; low: boolean; estopAt: number; selfSit: boolean; standAt?: number }
  endedReason: string | null
  feedbackAge: number | null
  /** The outdoor navigation state, only for a dog that can navigate (ui-design.md 19.1). */
  nav?: Dog2Nav | null
  /** Navigating, and the page that held control went silent (reloaded): this page can take control back. */
  adoptable?: boolean
}

export function lite3Next(i: Lite3NextInput): NextStep {
  const { l } = i
  if (!l || !i.online) return { cls: 'bad', text: t('Lite3 离线：下面是最后一次收到的数据，按钮都不可用') }
  const battery = lite3Battery(l)
  if (i.pose === 'protect') return { cls: 'bad', icon: 'x', text: t('Lite3 进入失控保护（可能摔倒或腿失控）：官方做法是先按 STOP 让它趴下，再重启狗——请狗旁的人处理') }
  if (i.marks.estopAt && i.pose !== 'standing') return { cls: 'bad', icon: 'x', text: t('已软急停：狗趴下了。11-10 实测，之后按「起立」就能重新站起来；站不起来时请狗旁的人用实体遥控器处理') }
  if (battery != null && battery < 20) return { cls: 'bad', text: t('电量 {n}%：低于 20% 时狗进入低电保护，不再响应运动指令（官方说明），请换电池或充电', { n: Math.round(battery) }) }
  // the new system: robot.error carries the board's mode when it is not in control; otherwise no state packets
  if (l.robot.connected === false) return { cls: 'warn', text: l.robot.error || t('板卡收不到运动主机的状态包：这时取得控制会被拒绝。一直这样时看狗是不是开着，或重启狗') }
  // the stand button is a toggle: right after pressing it, never offer it again before the dog reports its new state
  if (i.marks.standAt && Date.now() - i.marks.standAt < 3000 && i.pose !== 'transition') return { cls: 'run', icon: 'spinner', text: t('已发送起立 / 趴下切换，等狗的状态更新（3 秒内不能再按）') }
  if (i.pose === 'transition') return { cls: 'run', icon: 'spinner', text: t('{state}…（开机后第一次起立会先初始化关节，约 10 秒）', { state: l.robot.robot_state }) }
  if (i.marks.selfSit) return { cls: 'warn', text: t('Lite3 自己趴下了（不是本平台按的）：可能是过热保护（官方：原地趴下，冷却后再起立），也可能是别处的指令'), fix: { key: 'selfsitok', label: t('知道了') } }
  const other = l.robot.controller === 'other'
  const otherWindow = l.robot.controller === 'platform' && !i.mine
  if ((other || otherWindow) && !i.mine && i.adoptable) {
    return { cls: 'warn', text: t('导航还在走，控制留在刷新前的页面或另一个页面上，那边已经没有动静：按「接回控制」在这里接着操作'), fix: { key: 'arm', label: t('接回控制') } }
  }
  if (other) return { cls: 'warn', text: t('Lite3 正被别的页面或电脑控制：等对方释放；必须叫停时按底部「停止」，会同时解除对方的控制') }
  if (otherWindow) return { cls: 'warn', text: t('本平台另一个页面正在控制 Lite3：在那个页面点「释放」；必须叫停时按底部「停止」') }
  if (i.holding) return { cls: 'run', icon: 'play', text: t('移动中：松手即停；切到别的程序或设备也会立即停') }
  if (i.mine && i.nav && navTaskOn(i.nav)) {
    if (i.nav.state === 'paused') return { cls: 'warn', text: navShort(i.nav), fix: { key: 'l3navresume', label: t('继续') } }
    const left = i.nav.to_end_m != null ? t(' · 离终点 {d} m', { d: Math.round(i.nav.to_end_m) }) : ''
    return { cls: 'run', icon: 'play', text: navShort(i.nav) + left, fix: { key: 'l3navcancel', label: t('结束导航'), danger: true } }
  }
  const stale = i.feedbackAge != null && i.feedbackAge > 1
  if (!i.mine) {
    return i.endedReason
      // endedReason is the store's own text (t('控制权已失去：{detail}') or t('因{reason}已释放控制')), in the interface language
      ? { cls: i.endedReason.startsWith(t('控制权已失去')) ? 'warn' : '', text: t('{reason}。请按①「取得控制」重新取得', { reason: i.endedReason }), fix: { key: 'arm', label: t('① 取得控制') } }
      : { cls: '', text: t('下一步：按①「取得控制」，取得后这里才能让 Lite3 动'), fix: { key: 'arm', label: t('① 取得控制') } }
  }
  if (i.pose === 'unknown') {
    // stand is a toggle: never suggest "stand up" when the platform cannot tell which way it would go
    return { cls: 'warn', text: t('Lite3 报的状态是「{state}」，平台认不出是站着还是趴着：看画面确认后再按②（起立和趴下是同一个切换按钮）', { state: l.robot.robot_state || t('无') }) }
  }
  if (i.pose !== 'standing') {
    if (stale) return { cls: 'warn', text: t('Lite3 状态 {n} 秒没更新：起立 / 趴下是切换按钮，等状态更新再按', { n: i.feedbackAge!.toFixed(1) }) }
    return { cls: '', text: t('下一步：按②「起立」让狗站起来'), fix: { key: 'stand', label: t('② 起立') } }
  }
  if (!i.marks.low) return { cls: 'ok', icon: 'check', text: t('可以走了：按住方向键，松手即停。想走得慢一些，先按「低速步态」') }
  return { cls: 'ok', icon: 'check', text: t('可以走了：按住右下角的方向键，松手即停') }
}

/**
 * Lite3 battery, read as a percentage like the dog side's page does. The official protocol notes that some firmware
 * reports 0–1 instead; which one this board uses is on the to-confirm list, so nothing is converted here.
 */
export function lite3Battery(l: Lite3State | undefined): number | null {
  const b = l?.robot.battery
  return typeof b === 'number' && Number.isFinite(b) ? Math.round(b) : null
}
