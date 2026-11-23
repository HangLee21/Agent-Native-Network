
<script setup lang="ts">
/**
 * S10 function pages in workflow order (ui-design.md 5.4): prepare & walk → mapping → navigation → arm → grasp.
 * Buttons send exactly what the dog side's page sends, confirm where it confirms, and are grey only where it greys
 * them (or the board is offline / busy); the dog's own reply is shown when it refuses.
 */
import { computed, onBeforeUnmount, ref } from 'vue'
import AppIcon from '@/components/common/AppIcon.vue'
import Step from './Step.vue'
import Btn2 from './Btn2.vue'
import { useDogStore, navActive, S10_POSTURE } from '@/stores/dog'
import { useDogActions } from './useDogActions'
import { jobLabel, s10RunningJob, s10Stowed, trustOk } from './dogFlow'
import { grasp, navGoal, resetGrasp } from './s10Grasp'
import { waitCommand } from './waitCommand'
import { s10MediaUrl } from '@/api/dog'
import { t, tb } from '@/i18n'

const props = defineProps<{ card: string }>()
const emit = defineEmits<{ (e: 'card', c: string): void; (e: 'help', id: string): void }>()
const store = useDogStore()
const act = useDogActions()
/** Command labels: sent to the backend in Chinese (shared data stays in one language), shown translated via tb(). */
const CMD = {
  stand: '站立',   // i18n-ignore: sent to the backend, shown via tb()
  rl: 'RL 控制',   // i18n-ignore: sent to the backend, shown via tb()
  sit: '趴下',   // i18n-ignore: sent to the backend, shown via tb()
  flat: '平地步态',   // i18n-ignore: sent to the backend, shown via tb()
  stairs: '楼梯步态',   // i18n-ignore: sent to the backend, shown via tb()
  stopBeforeHome: '停止机械臂动作（收回前）',   // i18n-ignore: sent to the backend, shown via tb()
  armHome: '收回机械臂',   // i18n-ignore: sent to the backend, shown via tb()
  zero: '标零',   // i18n-ignore: sent to the backend, shown via tb()
  seed: '设为初始位姿',   // i18n-ignore: sent to the backend, shown via tb()
  reset: '清空并重建',   // i18n-ignore: sent to the backend, shown via tb()
  mapping: '开始 / 继续建图',   // i18n-ignore: sent to the backend, shown via tb()
  localization: '切换到定位',   // i18n-ignore: sent to the backend, shown via tb()
  relocalize: '重新定位',   // i18n-ignore: sent to the backend, shown via tb()
  navMode: '切换导航模式',   // i18n-ignore: sent to the backend, shown via tb()
  navCancel: '取消导航',   // i18n-ignore: sent to the backend, shown via tb()
  slower: '减速',   // i18n-ignore: sent to the backend, shown via tb()
  normal: '正常速度',   // i18n-ignore: sent to the backend, shown via tb()
  faster: '加速',   // i18n-ignore: sent to the backend, shown via tb()
  armMove: '执行输入角度',   // i18n-ignore: sent to the backend, shown via tb()
  armEnable: '启用电机',   // i18n-ignore: sent to the backend, shown via tb()
  liftUp: '末端抬起',   // i18n-ignore: sent to the backend, shown via tb()
  liftDown: '末端放下',   // i18n-ignore: sent to the backend, shown via tb()
  letGo: '松手',   // i18n-ignore: sent to the backend, shown via tb()
  snapshot: '拍照',   // i18n-ignore: sent to the backend, shown via tb()
  solve: '求解（不运动）',   // i18n-ignore: sent to the backend, shown via tb()
  plan: '执行到悬停位',   // i18n-ignore: sent to the backend, shown via tb()
  radish: '识别萝卜 / 测量尺寸',   // i18n-ignore: sent to the backend, shown via tb()
  observe: '移动到观察位',   // i18n-ignore: sent to the backend, shown via tb()
  skill: '一键抓取（萝卜）',   // i18n-ignore: sent to the backend, shown via tb()
  armStop: '停止机械臂动作',   // i18n-ignore: sent to the backend, shown via tb()
  graspStop: '停止抓取动作',   // i18n-ignore: sent to the backend, shown via tb()
}

const s = computed(() => store.s10!)
const online = computed(() => store.online('s10'))
const job = computed(() => s10RunningJob(s.value))
const nav = computed(() => navActive(s.value.nav))
const off = computed(() => (online.value ? null : store.pageStale('s10') ? t('本页 {n} 秒没收到 {name} 的新状态', { n: store.staleSecs('s10'), name: 'S10' }) : store.lost('s10') ? t('S10 失联，指令发不出去') : t('S10 离线，指令发不出去')))
/** The board does one thing at a time (global lock): queued buttons are grey while a job runs. */
const busy = computed(() => off.value ?? (job.value
  ? (job.value.stoppable ? t('S10 一次只做一件事：正在执行「{job}」，等它结束或按「停止」', { job: jobLabel(job.value) }) : t('S10 一次只做一件事：正在执行「{job}」，等它结束', { job: jobLabel(job.value) }))
  : null))
/** Platform rule, not the dog's: no posture / gait / map change while navigating. */
const navBlock = computed(() => busy.value ?? (nav.value ? t('导航中：先「取消导航」') : null))
const posture = computed(() => s.value.posture)
const stood = computed(() => posture.value === 'standing' || posture.value === 'rl_control')
const armOk = computed(() => posture.value === 'sitting' || posture.value === 'idle')

const TABS = [
  { k: 'posture', l: t('准备·走动'), i: 'joystick' },
  { k: 'map', l: t('建图'), i: 'map' },
  { k: 'nav', l: t('导航'), i: 'route' },
  { k: 'arm', l: t('机械臂'), i: 'gimbal' },
  { k: 'grasp', l: t('抓取'), i: 'target' },
]
function tabBusy(k: string): boolean {
  const a = job.value?.action ?? ''
  if (k === 'nav') return nav.value || a.startsWith('nav')
  if (k === 'map') return a === 'map'
  if (k === 'arm') return a.startsWith('arm') || !!store.armHold
  if (k === 'grasp') return ['snapshot', 'solve', 'arm_plan', 'radish_detect', 'skill_observe', 'skill_minimal'].includes(a)
  return a === 'posture' || a === 'gait' || !!store.s10Hold
}

// ---------------------------------------------------------------- prepare & walk
const gaitName = computed(() => {
  const g = Number((s.value.chassis as { gait?: number }).gait)
  return g === 12290 ? t('平地步态') : g === 12291 ? t('楼梯步态') : t('狗没有报告')
})
function posture_(p: string, label: string): void {
  void act.s10({ action: 'posture', posture: p, label })
}
function gait(g: number, label: string): void {
  void act.s10({ action: 'gait', gait: g, label }, { title: t('S10：切换到{label}？', { label: tb(label) }), message: t('狗会切换步态；未收臂时会先收臂。') })
}
let gone = false
onBeforeUnmount(() => (gone = true))
async function armHome(): Promise<void> {
  // dog page behaviour: stop arm interpolation, wait until no job runs, then go to the stowed pose
  const ok = await act.s10({ action: 'arm_stop', label: CMD.stopBeforeHome }, {
    title: t('S10：收回机械臂？'), message: t('收回到 [0, 0, 0, 0, 25, 0]°。如果有机械臂动作正在执行，会先停止它再收回。'), details: [t('回位可能经过较大范围，请看着机械臂')],
  })
  if (!ok) return
  // a stop or soft e-stop pressed while waiting cancels the return: the arm must not move after it
  const seq = store.stopSeq
  const cancelled = (): boolean => gone || store.stopSeq !== seq
  for (let i = 0; i < 40 && s10RunningJob(store.s10) && !cancelled(); i++) await new Promise((r) => setTimeout(r, 250))
  if (cancelled()) {
    store.note('s10', 'warn', t('收回机械臂已取消：等待期间按了停止'))
    return
  }
  if (s10RunningJob(store.s10)) {
    store.note('s10', 'bad', t('任务尚未退出，请稍后再收回'))
    return
  }
  await act.s10({ action: 'arm_home', label: CMD.armHome })
}
function zero(): void {
  void act.s10({ action: 'posture', posture: 'zero', label: CMD.zero }, { title: t('S10：确认执行标零？'), message: t('标零让关节重新找零位（关节初始化），会改变关节零点。'), danger: true })
}

// ---------------------------------------------------------------- mapping
const mapName = ref('')
const loadName = ref('')
const mapping = computed(() => (s.value.map as { mode?: string } | null)?.mode === 'mapping')
const mapValid = computed(() => /^[\w-]{1,64}$/.test(mapName.value.trim()))
function mapOp(op: string, args: Record<string, unknown>, label: string, ask?: { title: string; message: string; danger?: boolean }): Promise<boolean> {
  return act.s10({ action: 'map', op, args, label, ...(op === 'reset' ? { confirm: 'RESET' } : {}) }, ask)
}
function save(): void {
  const n = mapName.value.trim()
  const label = `保存地图 ${n}`   // i18n-ignore: sent to the backend, shown via tb()
  void mapOp('save', { map_id: n }, label, { title: t('S10：保存地图为 {name}？', { name: n }), message: t('同名结果可能被更新。') })
}
function load(): void {
  const n = loadName.value || s.value.maps[0]
  if (!n) return
  const label = `加载地图 ${n}`   // i18n-ignore: sent to the backend, shown via tb()
  void mapOp('load', { map_id: n, mode: 'localization' }, label, {
    title: t('S10：加载 {name} 用于定位？', { name: n }),
    message: mapping.value ? t('会切换地图并进入定位模式。现在正在建图：没保存的地图可能丢失，请先保存。') : t('会切换地图并进入定位模式。请先保存当前建图。'),
  })
}
function seed(): void {
  void mapOp('pose_estimate', { x: navGoal.x, y: navGoal.y, thetaDeg: navGoal.deg }, CMD.seed, {
    title: t('S10：用这组坐标作为当前位置估计？'), message: t('X {x} m，Y {y} m，朝向 {deg}°（「导航」页填的那组坐标，和狗方网页一样共用一组输入）。', { x: navGoal.x, y: navGoal.y, deg: navGoal.deg }),
  })
}
async function clearMap(): Promise<void> {
  const first = await store.s10 && (await import('@/stores/confirm')).useConfirmStore().ask({
    title: t('S10：清空当前地图并重新建图？'), message: t('会丢弃本次没有保存的地图，然后从零开始建图——不只是擦掉画面。请先保存需要保留的地图。'), danger: true, focus: 'cancel', confirmText: t('我已保存需要保留的地图'),
  })
  if (!first) return
  void mapOp('reset', {}, CMD.reset, { title: t('S10：再确认一次：清空并重建？'), message: t('这一步不能撤销。'), danger: true })
}

// ---------------------------------------------------------------- navigation
function navGo(): void {
  const at = { x: navGoal.x, y: navGoal.y, deg: navGoal.deg }
  const label = `导航到 (${navGoal.x}, ${navGoal.y}, ${navGoal.deg}°)`   // i18n-ignore: sent to the backend, shown via tb()
  void act.s10({ action: 'navigate', x: navGoal.x, y: navGoal.y, thetaDeg: navGoal.deg, label }, {
    title: t('S10：导航到输入的地图坐标？'), message: t('目标 ({x}, {y})，朝向 {deg}°。这是狗自己地图里的坐标（米），不是经纬度。', at), details: [t('发起后由狗的导航程序开狗，导航没有心跳：平台断线时狗很可能继续走')],
  })
}
function navMode(): void {
  void act.s10({ action: 'navigation_mode', label: CMD.navMode }, {
    title: t('S10：切换到导航模式？'), message: t('把狗的使用模式切成导航（狗方说明：使用模式 = 1）。切过去以后，平台和狗方网页都没有切回来的按钮；导航本身不要求先切。'), danger: true,
  })
}
const navRaw = computed(() => JSON.stringify(s.value.nav ?? {}, null, 2))

// ---------------------------------------------------------------- arm
const jointsFresh = computed(() => {
  const a = store.age('s10.joint', s.value.topics.joints?.age, s.value.stateAt)
  return a != null && a <= 2
})
const jointAge = computed(() => store.age('s10.joint', s.value.topics.joints?.age, s.value.stateAt))
const joints = computed(() => s.value.topics.joints?.deg ?? [])
const limits = computed(() => s.value.ik?.limits ?? [])
const jin = ref<number[]>([0, 0, 0, 0, 25, 0])
const armSpeed = ref(10)
const zStep = ref(5)
const opening = ref(40)
function fillJoints(): void {
  const a = jointAge.value
  if (a == null || a > 3) {
    store.note('s10', 'warn', t('没有新鲜的机械臂角度'))
    return
  }
  jin.value = joints.value.map((v) => Math.round((v ?? 0) * 100) / 100)
}
function armMove(): void {
  void act.s10({ action: 'arm_move', joints_deg: jin.value.map(Number), label: CMD.armMove }, {
    title: t('S10：按输入的六轴角度移动机械臂？'),
    message: t('目标 {target}°（当前 {now}°）。', { target: jin.value.map((v) => Number(v).toFixed(1)).join(', '), now: joints.value.map((v) => (v ?? 0).toFixed(1)).join(', ') }),
    details: [t('请检查运动范围；结果误差超过 1° 算未完成')],
  })
}
function gripper(mm: number): void {
  const label = `夹爪开口 ${mm} mm`   // i18n-ignore: sent to the backend, shown via tb()
  void act.s10({ action: 'arm_gripper', opening_mm: mm, label }, { title: t('S10：夹爪开口改为 {mm} mm？', { mm }), message: t('夹爪会张开或合上。') })
}
function armEnable(): void {
  void act.s10({ action: 'arm_enable', label: CMD.armEnable }, { title: t('S10：启用机械臂电机？'), message: t('要求狗静止。') })
}
const JOINT_NAMES = [t('底座旋转'), t('肩'), t('肘'), t('腕旋转'), t('腕俯仰'), t('夹爪旋转')]
function jogStart(i: number, dir: number): void {
  void store.armHoldStart(`j${i}${dir > 0 ? '+' : '-'}`, { action: 'arm_jog', axis: i, dir }, armSpeed.value, `点动 J${i + 1} ${dir > 0 ? '＋' : '−'}`)   // i18n-ignore: sent to the backend, shown via tb()
}
function liftStart(dir: number): void {
  void store.armHoldStart(dir > 0 ? 'zup' : 'zdown', { action: 'arm_cart_step', dir, stepMm: zStep.value }, armSpeed.value, dir > 0 ? CMD.liftUp : CMD.liftDown)
}
function jogEnd(): void {
  void store.armHoldEnd(CMD.letGo)
}

// ---------------------------------------------------------------- grasp
const graspTab = ref<'visual' | 'radish'>('visual')
const hover = ref(50)
const graspYaw = ref(0)
const snapLeft = computed(() => (grasp.snapAt ? Math.max(0, 90 - (store.tick - grasp.snapAt) / 1000) : 0))
const planLeft = computed(() => (grasp.solvedAt ? Math.max(0, 30 - (store.tick - grasp.solvedAt) / 1000) : 0))
async function snap(): Promise<void> {
  resetGrasp()
  const c = await store.s10Action({ action: 'snapshot', label: CMD.snapshot })
  if (!c) return
  const done = await waitCommand(c.id)
  const r = (done?.result ?? {}) as { snapshot?: string; image?: string; width?: number; height?: number; ok?: boolean }
  if (r.snapshot) {
    grasp.snapshot = r.snapshot
    grasp.image = r.image ?? '/media/capture.jpg'
    grasp.width = r.width ?? 640
    grasp.height = r.height ?? 480
    grasp.snapAt = Date.now()
    grasp.selecting = true
  }
}
async function solve(): Promise<void> {
  if (!grasp.snapshot || grasp.u == null || grasp.v == null) return
  grasp.solution = null
  const c = await store.s10Action({ action: 'solve', snapshot: grasp.snapshot, u: grasp.u, v: grasp.v, hover_mm: hover.value, yaw_deg: graspYaw.value, label: CMD.solve })
  if (!c) return
  const done = await waitCommand(c.id)
  const r = (done?.result ?? {}) as Record<string, unknown>
  grasp.solution = {
    ok: r.ok === true && !!r.plan_id,
    planId: (r.plan_id as string) ?? null,
    jointsDeg: (r.joints_deg as number[]) ?? null,
    depthM: (r.depth_m as number) ?? null,
    errorM: (r.verified_position_error_m as number) ?? null,
    targetM: (r.target_base_m as number[]) ?? null,
    reason: done?.error ?? (r.ok === false ? String(r.detail ?? r.error ?? t('求解没有通过')) : null),
  }
  if (grasp.solution.ok) {
    grasp.solvedAt = Date.now()
    if (grasp.solution.jointsDeg) jin.value = grasp.solution.jointsDeg.map((v) => Math.round(v * 100) / 100)
  }
}
function plan(): void {
  if (!grasp.solution?.planId) return
  void act.s10({ action: 'arm_plan', plan_id: grasp.solution.planId, label: CMD.plan }, {
    title: t('S10：执行求出的悬停角度？'), message: t('机械臂会移到目标上方 {mm} mm 悬停，不会自动合爪。', { mm: hover.value }),
    details: grasp.solution.jointsDeg ? [t('关节角：{deg}°', { deg: grasp.solution.jointsDeg.map((v) => v.toFixed(1)).join(', ') })] : [],
  })
}
/** The dog's own name of the object its skill looks for: goes to the dog as is, never translated. */
const RADISH = '萝卜'   // i18n-ignore: sent to the dog
const radish = ref<{ dims?: string; image?: string; at: number } | null>(null)
async function radishDetect(): Promise<void> {
  const c = await store.s10Action({ action: 'radish_detect', label: CMD.radish })
  if (!c) return
  const done = await waitCommand(c.id)
  const r = (done?.result ?? {}) as { ok?: boolean; image?: string; measurement?: { diagnostics?: { length_mm?: number; width_mm?: number; height_mm?: number } } }
  const d = r.measurement?.diagnostics
  // the annotated image is fetched once per result (the dog writes it once), not on every UI tick
  radish.value = r.ok ? { dims: d ? t('长 {l} 宽 {w} 高 {h} mm', { l: d.length_mm, w: d.width_mm, h: d.height_mm }) : t('已识别'), image: r.image, at: done?.finishedAt ?? Date.now() } : null
}
const graspRunning = computed(() => s.value.jobs.some((j) => j.action === 'skill_minimal' && j.state === 'running'))
function observe(): void {
  void act.s10({ action: 'skill_observe', target: RADISH, label: CMD.observe }, { title: t('S10：移动到观察位？'), message: t('会把机械臂移动到拍照位并运行狗方已有的观察流程。') })
}
function skill(): void {
  void act.s10({ action: 'skill_minimal', target: RADISH, label: CMD.skill }, {
    title: t('S10：开始识别、抓取并抬起红色萝卜？'), message: t('请确保狗趴稳，当前夹爪没有需要继续握持的物品；开始会张开夹爪。'), details: [t('完成后保持夹持；失败不会自动重试'), t('可能移动底盘')],
  })
}

defineExpose({ armHome })
const P = S10_POSTURE
void props
</script>

<template>
  <div class="s10body">
    <div class="taskbar">
      <button v-for="tab in TABS" :key="tab.k" class="tb" :class="{ on: card === tab.k }" :data-test="`s10-tab-${tab.k}`" @click="emit('card', tab.k)">
        <span v-if="tabBusy(tab.k)" class="tbdot" /><AppIcon :name="tab.i" :size="17" />{{ tab.l }}
      </button>
    </div>

    <div class="carea scroll" :class="{ offl: !online }">
      <!-- prepare & walk -->
      <template v-if="card === 'posture'">
        <div class="cardh"><h3>{{ t('准备：站起来，进入可走状态') }}</h3><button class="qm" @click="emit('help', 'm-s10-walk')">?</button></div>
        <Step :n="1" :state="stood ? 'done' : 'cur'" :title="t('站起来')" @help="emit('help', $event)">
          <Btn2 :main="t('站立')" :reason="navBlock ?? (posture === 'damping' ? t('阻尼中：约 3 秒后进入空闲，之后才能站立') : null)" @click="posture_('stand', CMD.stand)" />
          <template #expl>{{ t('狗会先自动把机械臂收回安全位，再站起来。现在：') }}<b>{{ P[posture ?? ''] ?? posture ?? t('未知') }}</b></template>
        </Step>
        <Step :n="2" :state="posture === 'rl_control' ? 'done' : stood ? 'cur' : ''" :title="t('进入可走状态')" help="g-rl" @help="emit('help', $event)">
          <Btn2 :main="t('进入可走状态')" :sub="t('RL 控制')" :reason="navBlock" @click="posture_('rl', CMD.rl)" />
          <template #expl>{{ t('RL 控制＝用强化学习训练出来的行走控制。官方说明要站好以后才能进入；进入后，方向键让狗走、转。') }}</template>
        </Step>
        <Step :n="3" :title="t('选走法（步态）')" help="g-gait" @help="emit('help', $event)">
          <Btn2 :main="t('平地走法')" :sub="t('平地步态…')" :reason="navBlock" @click="gait(12290, CMD.flat)" />
          <Btn2 :main="t('楼梯走法')" :sub="t('楼梯步态…')" :reason="navBlock" @click="gait(12291, CMD.stairs)" />
          <template #expl>{{ t('平地步态用于平地，楼梯步态用于上下台阶；按住移动时狗会检查步态。现在：{gait}。', { gait: gaitName }) }}</template>
        </Step>
        <Step :n="4" :state="posture === 'rl_control' ? 'cur' : ''" :title="t('走')">
          <template #expl>{{ t('用主画面右下角「按住移动」：按住方向键才动，松手即停。') }}</template>
        </Step>
        <div class="grp">
          <div class="gl">{{ t('休息 / 用机械臂之前') }}</div>
          <div class="brow">
            <Btn2 :main="t('趴下')" :reason="navBlock" @click="posture_('sit', CMD.sit)" />
            <Btn2 :main="t('收回机械臂…')" :sub="t('回到默认位')" :reason="off" @click="armHome" />
          </div>
          <p class="expl">{{ t('机械臂和抓取要狗趴下（或空闲且低位静止）才能用。') }}</p>
        </div>
        <details class="grp">
          <summary class="gl">{{ t('更多（不常用）') }}</summary>
          <div class="brow">
            <Btn2 :main="t('标零…')" sub="posture zero" :reason="navBlock" @click="zero" />
            <button class="btn btn2" disabled :title="t('监控协议需要设备证书，当前不可用（狗方网页也是灰的）')">{{ t('SDK 模式开关') }}</button>
            <button class="btn btn2" disabled :title="t('监控协议尚未连通（狗方网页也是灰的）')">{{ t('正常使用模式') }}</button>
            <button class="btn btn2" disabled :title="t('当前 ROS 导航速度接口不支持这些自由度（狗方网页也是灰的）')">Z / Roll / Pitch</button>
          </div>
        </details>
      </template>

      <!-- mapping -->
      <template v-else-if="card === 'map'">
        <div class="cardh"><h3>{{ t('建图与定位') }}</h3><button class="qm" @click="emit('help', 'm-s10-map')">?</button></div>
        <p class="expl">{{ t('现在：') }}<b>{{ (s.map as any)?.mode ?? t('未知') }}</b> · {{ t('地图') }} <b>{{ (s.map as any)?.map_id ?? t('新地图') }}</b> · {{ t('定位可信度') }}
          <b :class="trustOk(s) ? 'okc' : 'warnc'">{{ (s.map as any)?.trust?.verdict ?? t('未知') }}</b>{{ (s.map as any)?.trust?.detail ? t('（{detail}）', { detail: (s.map as any).trust.detail }) : '' }}</p>
        <div class="subflow">
          <h4>{{ t('A. 画一张新地图') }}</h4>
          <Step :n="1" :state="mapping ? 'done' : ''" :title="t('开始建图')">
            <Btn2 :main="mapping ? t('继续建图') : t('开始 / 继续建图')" :kind="mapping ? '' : 'primary'" :reason="navBlock" @click="mapOp('switch_mode', { mode: 'mapping' }, CMD.mapping)" />
            <template #expl>{{ t('建图模式：狗一边走一边画新地图。') }}</template>
          </Step>
          <Step :n="2" :state="mapping ? 'cur' : ''" :title="t('绕场走一圈')"><template #expl>{{ t('用「按住移动」慢慢走；主画面切到「二维地图」或「点云」看地图长出来。') }}</template></Step>
          <Step :n="3" :title="t('保存')">
            <input v-model="mapName" class="input grow" :placeholder="t('地图名：字母、数字、_、-，1–64 个')" />
            <Btn2 :main="t('保存…')" :reason="navBlock ?? (mapValid ? null : t('地图名称请用字母、数字、下划线或短横线'))" @click="save" />
            <template #expl>{{ t('同名会更新原来的结果。') }}</template>
          </Step>
        </div>
        <div class="subflow">
          <h4>{{ t('B. 用已保存的地图定位（导航前要做）') }}</h4>
          <Step :n="1" :title="t('加载地图')">
            <select v-model="loadName" class="input grow"><option v-for="m in s.maps" :key="m" :value="m">{{ m }}</option></select>
            <Btn2 :main="t('加载用于定位…')" :reason="navBlock ?? (s.maps.length ? null : t('狗方没有列出已保存的地图'))" @click="load" />
            <Btn2 :main="t('切换到定位')" :reason="navBlock" @click="mapOp('switch_mode', { mode: 'localization' }, CMD.localization)" />
          </Step>
          <Step :n="2" :state="trustOk(s) ? 'done' : 'cur'" :title="t('看定位可信度')" help="g-trust" @help="emit('help', $event)">
            <template #expl>{{ t('可信才能导航。') }}</template>
          </Step>
          <Step :n="3" :title="t('不可信时')" help="g-reloc" @help="emit('help', $event)">
            <Btn2 :main="t('重新定位')" :reason="navBlock" @click="mapOp('relocalize', {}, CMD.relocalize)" />
            <Btn2 :main="t('设为初始位姿…')" :reason="navBlock" @click="seed" />
            <template #expl>{{ t('重新定位＝让狗在地图里重新找自己；初始位姿＝告诉狗"你大概在这里、朝这个方向"（坐标在「导航」页填）。') }}</template>
          </Step>
        </div>
        <div class="danger-zone">
          <div class="gl dangerc"><AppIcon name="alert" :size="14" />{{ t('清空当前地图') }}</div>
          <Btn2 :main="t('清空并重建…')" kind="danger" :reason="navBlock" @click="clearMap" />
          <p class="expl">{{ t('会丢弃本次没保存的地图并从零建图。地图操作狗方最长等 90 秒，中途不能取消。') }}</p>
        </div>
      </template>

      <!-- navigation -->
      <template v-else-if="card === 'nav'">
        <div class="cardh"><h3>{{ t('导航：让狗自己走到地图上的一个点') }}</h3><button class="qm" @click="emit('help', 'm-s10-nav')">?</button></div>
        <Step :n="1" :state="trustOk(s) ? 'done' : 'cur'" :title="t('确认定位可信')" help="g-trust" @help="emit('help', $event)">
          <button v-if="!trustOk(s)" class="btn btn-sm" @click="emit('card', 'map')">{{ t('去「建图」页定位') }}</button>
          <template #expl>{{ t('不可信时狗会拒绝导航。现在：') }}<b :class="trustOk(s) ? 'okc' : 'warnc'">{{ (s.map as any)?.trust?.verdict ?? t('未知') }}</b></template>
        </Step>
        <Step :n="2" :state="s10Stowed(s) ? 'done' : 'cur'" :title="t('收好机械臂')">
          <template #expl>{{ t('导航要求机械臂在收好的位置，否则狗会拒绝。现在：{now}。', { now: s10Stowed(s) == null ? t('关节角未知') : s10Stowed(s) ? t('已收好') : t('没收好') }) }}</template>
        </Step>
        <Step :n="3" :title="t('填目标')">
          <div class="frow">
            <label>X<span class="unit"><input v-model.number="navGoal.x" class="input num" type="number" step="0.1" /><span>m</span></span></label>
            <label>Y<span class="unit"><input v-model.number="navGoal.y" class="input num" type="number" step="0.1" /><span>m</span></span></label>
            <label>{{ t('朝向') }}<span class="unit"><input v-model.number="navGoal.deg" class="input num" type="number" step="5" /><span>°</span></span></label>
          </div>
          <template #expl>{{ t('狗自己地图里的坐标（米），不是经纬度。') }}</template>
        </Step>
        <Step :n="4" :state="nav ? 'cur' : ''" :title="t('导航')">
          <Btn2 :main="t('导航到目标…')" kind="primary" :reason="busy ?? (nav ? t('正在导航：先「取消导航」再发新目标') : null)" @click="navGo" />
          <Btn2 :main="t('取消导航')" :reason="off" @click="act.s10({ action: 'nav_cancel', label: CMD.navCancel })" />
          <template #expl>{{ t('"导航已开始"只代表狗开始走了，到没到看下面狗的导航状态。') }}</template>
        </Step>
        <div class="grp">
          <div class="gl">{{ t('导航速度') }}</div>
          <div class="brow">
            <button class="btn btn-sm" :disabled="!!busy" @click="act.s10({ action: 'nav_speed', direction: 'slower', label: CMD.slower })">{{ t('减速') }}</button>
            <button class="btn btn-sm" :disabled="!!busy" @click="act.s10({ action: 'nav_speed', direction: 'normal', label: CMD.normal })">{{ t('正常速度') }}</button>
            <button class="btn btn-sm" :disabled="!!busy" @click="act.s10({ action: 'nav_speed', direction: 'faster', label: CMD.faster })">{{ t('加速') }}</button>
          </div>
        </div>
        <div class="grp">
          <div class="gl">{{ t('狗的导航状态') }}</div>
          <pre class="raw">{{ navRaw }}</pre>
        </div>
        <details class="grp">
          <summary class="gl">{{ t('更多') }}</summary>
          <Btn2 :main="t('切换导航模式…')" :sub="t('使用模式 = 1')" :reason="navBlock" @click="navMode" />
          <p class="expl">{{ t('导航本身不要求先切；切过去以后平台和狗方网页都没有切回来的按钮。') }}</p>
        </details>
      </template>

      <!-- arm -->
      <template v-else-if="card === 'arm'">
        <div class="cardh"><h3>{{ t('机械臂（六个关节 + 夹爪）') }}</h3><button class="qm" @click="emit('help', 'm-s10-arm')">?</button></div>
        <div class="pre">
          <div :class="armOk ? 'okc' : 'badc'"><AppIcon :name="armOk ? 'check' : 'x'" :size="14" />{{ t('底盘：{now}', { now: P[posture ?? ''] ?? posture ?? t('未知') }) }}{{ armOk ? ' ✓' : t(' — 机械臂需要狗趴下，或空闲且低位静止') }}
            <button v-if="!armOk" class="btn btn-sm" :disabled="!!navBlock" @click="posture_('sit', CMD.sit)">{{ t('趴下') }}</button></div>
          <div :class="jointsFresh ? 'okc' : 'badc'"><AppIcon :name="jointsFresh ? 'check' : 'x'" :size="14" />{{ t('关节反馈：{v}', { v: jointsFresh ? t('正常') : t('超过 2 秒没更新（狗会拒绝机械臂动作）') }) }}</div>
          <div :class="s.ik?.ready ? 'okc' : 'warnc'"><AppIcon :name="s.ik?.ready ? 'check' : 'alert'" :size="14" />{{ t('反解（根据目标位置算关节角）：{v}', { v: s.ik?.ready ? t('已就绪') : t('未就绪 {error}', { error: s.ik?.error ?? '' }) }) }}</div>
        </div>
        <div class="joints" :class="{ stale: !jointsFresh }">
          <div v-for="(v, i) in joints" :key="i"><em>J{{ i + 1 }}</em><b class="num">{{ v == null ? '—' : `${v.toFixed(1)}°` }}</b></div>
        </div>
        <details class="sec" open>
          <summary>{{ t('点动：按住让一个关节慢慢转，松手停') }}</summary>
          <div class="frow">
            <label>{{ t('关节速度') }}<select v-model.number="armSpeed" class="input"><option v-for="v in [5, 10, 20, 30, 40]" :key="v" :value="v">{{ v }} °/s</option></select></label>
            <label>{{ t('末端步长') }}<select v-model.number="zStep" class="input"><option v-for="v in [5, 10, 20]" :key="v" :value="v">{{ v }} mm</option></select></label>
          </div>
          <div v-for="(n, i) in JOINT_NAMES" :key="n" class="jog">
            <button class="pk" :class="{ on: store.armHold?.key === `j${i}-` }" :disabled="!!busy && store.armHold?.key !== `j${i}-`" @pointerdown.prevent="jogStart(i, -1)" @pointerup="jogEnd" @pointerleave="jogEnd" @pointercancel="jogEnd" @contextmenu.prevent>−</button>
            <span><b>J{{ i + 1 }}</b> {{ n }}</span>
            <button class="pk" :class="{ on: store.armHold?.key === `j${i}+` }" :disabled="!!busy && store.armHold?.key !== `j${i}+`" @pointerdown.prevent="jogStart(i, 1)" @pointerup="jogEnd" @pointerleave="jogEnd" @pointercancel="jogEnd" @contextmenu.prevent>＋</button>
          </div>
          <div class="jog">
            <button class="pk" :disabled="!!busy && store.armHold?.key !== 'zdown'" @pointerdown.prevent="liftStart(-1)" @pointerup="jogEnd" @pointerleave="jogEnd" @pointercancel="jogEnd" @contextmenu.prevent>↓</button>
            <span>{{ t('末端 放下 / 抬起') }}<br><small class="dim">{{ t('保持朝向，不可达时狗会拒绝') }}</small></span>
            <button class="pk" :disabled="!!busy && store.armHold?.key !== 'zup'" @pointerdown.prevent="liftStart(1)" @pointerup="jogEnd" @pointerleave="jogEnd" @pointercancel="jogEnd" @contextmenu.prevent>↑</button>
          </div>
          <p v-if="grasp.snapshot && snapLeft > 0" class="expl warnc">{{ t('已拍照：执行悬停位之前别动机械臂（当前关节和拍照时差超过 2° 狗会拒绝执行）') }}</p>
        </details>
        <details class="sec">
          <summary>{{ t('输入角度执行') }}</summary>
          <div class="jin">
            <label v-for="i in 6" :key="i">J{{ i }}{{ limits[i - 1] ? `（${limits[i - 1]![0]}~${limits[i - 1]![1]}°）` : '' }}<input v-model.number="jin[i - 1]" class="input num" type="number" step="0.1" /></label>
          </div>
          <div class="brow">
            <button class="btn btn-sm" @click="fillJoints">{{ t('填入当前角度') }}</button>
            <Btn2 :main="t('执行输入角度…')" kind="primary" :reason="busy" @click="armMove" />
          </div>
          <p class="expl">{{ t('执行后核对实际反馈：误差 ≤ 1° 才算完成。') }}</p>
        </details>
        <details class="sec">
          <summary>{{ t('夹爪与回收') }}</summary>
          <div class="frow"><label class="grow">{{ t('夹爪开口') }} <span class="num">{{ opening }}</span> {{ t('mm（0–80）') }}<input v-model.number="opening" type="range" min="0" max="80" /></label>
            <Btn2 :main="t('执行夹爪开口…')" :reason="busy" @click="gripper(opening)" /></div>
          <div class="brow">
            <button class="btn btn-sm" :disabled="!!busy" @click="gripper(80)">{{ t('张开 80') }}</button>
            <button class="btn btn-sm" :disabled="!!busy" @click="gripper(40)">{{ t('半合 40') }}</button>
            <button class="btn btn-sm" :disabled="!!busy" @click="gripper(0)">{{ t('闭合 0') }}</button>
          </div>
          <div class="brow">
            <Btn2 :main="t('收回至安全位…')" :reason="off" @click="armHome" />
            <Btn2 :main="t('启用电机…')" :reason="busy" @click="armEnable" />
          </div>
          <p class="expl">{{ t('夹住东西时夹爪会停在比目标大的开口，显示"夹爪停下"，不算失败。') }}</p>
        </details>
        <div class="grp">
          <button class="btn btn-danger" :disabled="!!off" @click="act.s10({ action: 'arm_stop', label: CMD.armStop })"><AppIcon name="stop" :size="14" />{{ t('停止机械臂动作') }}</button>
          <p class="expl">{{ t('取消后续动作，保持最后目标；不失能、不松夹爪，不是硬件急停。') }}</p>
        </div>
      </template>

      <!-- grasp -->
      <template v-else>
        <div class="cardh"><h3>{{ t('抓取') }}</h3><button class="qm" @click="emit('help', 'm-s10-grasp')">?</button></div>
        <div class="seg2">
          <button :class="{ on: graspTab === 'visual' }" @click="graspTab = 'visual'">{{ t('视觉抓取（手动选点）') }}</button>
          <button :class="{ on: graspTab === 'radish' }" @click="graspTab = 'radish'">{{ t('萝卜一键抓取') }}</button>
        </div>
        <div class="pre">
          <div :class="armOk ? 'okc' : 'badc'"><AppIcon :name="armOk ? 'check' : 'x'" :size="14" />{{ t('底盘：{now}', { now: P[posture ?? ''] ?? posture ?? t('未知') }) }}{{ armOk ? ' ✓' : t(' — 抓取需要狗趴下，或空闲且低位静止') }}</div>
          <div :class="s.vision?.ready ? 'okc' : 'warnc'"><AppIcon :name="s.vision?.ready ? 'check' : 'alert'" :size="14" />{{ t('视觉：{v}', { v: s.vision?.detail ?? t('未知') }) }}</div>
        </div>
        <template v-if="graspTab === 'visual'">
          <Step :n="1" :state="grasp.snapshot ? 'done' : 'cur'" :title="t('拍照')">
            <Btn2 :main="t('拍照')" :reason="busy" @click="snap" />
            <template #expl>{{ t('取一张同步的彩色 + 深度画面，主画面进入选点模式。') }}{{ grasp.snapshot ? t('照片 {n} 秒内可求解', { n: Math.round(snapLeft) }) : '' }}</template>
          </Step>
          <Step :n="2" :state="grasp.u != null ? 'done' : grasp.snapshot ? 'cur' : ''" :title="t('在照片上点目标中心')">
            <button v-if="grasp.snapshot && !grasp.selecting" class="btn btn-sm" @click="grasp.selecting = true">{{ t('回到选点') }}</button>
            <template #expl>{{ grasp.u != null ? t('目标像素 ({u}, {v})', { u: grasp.u, v: grasp.v }) : t('在主画面的照片上点一下') }}</template>
          </Step>
          <Step :n="3" :state="grasp.solution?.ok ? 'done' : grasp.u != null ? 'cur' : ''" :title="t('求解（不运动）')">
            <div class="frow">
              <label>{{ t('悬停高度') }}<span class="unit"><input v-model.number="hover" class="input num" type="number" min="20" max="150" /><span>mm</span></span></label>
              <label>{{ t('夹爪朝向') }}<span class="unit"><input v-model.number="graspYaw" class="input num" type="number" /><span>°</span></span></label>
            </div>
            <Btn2 :main="t('求解')" :reason="busy ?? (!grasp.snapshot || grasp.u == null ? t('先拍照并在照片上选点') : snapLeft <= 0 ? t('照片已超过 90 秒，重新拍照') : null)" @click="solve" />
            <template #expl>
              <template v-if="grasp.solution?.ok">{{ t('深度 {depth} m · 校验误差 {err} mm · {n} 秒内可执行', { depth: grasp.solution.depthM?.toFixed(2), err: ((grasp.solution.errorM ?? 0) * 1000).toFixed(0), n: Math.round(planLeft) }) }}</template>
              <template v-else-if="grasp.solution">{{ t('求解没有通过：{reason}', { reason: grasp.solution.reason }) }}</template>
              <template v-else>{{ t('只计算关节角，机械臂不动。') }}</template>
            </template>
          </Step>
          <Step :n="4" :state="''" :title="t('执行到悬停位')">
            <Btn2 :main="t('执行到悬停位…')" kind="primary" :reason="busy ?? (!grasp.solution?.ok ? t('先求解') : planLeft <= 0 ? t('求解结果已超过 30 秒，重新求解') : null)" @click="plan" />
            <template #expl>{{ t('机械臂停在目标正上方，不会自动合爪；之后用「机械臂」页放下、夹紧、抬起。拍照后到这一步之前别动机械臂。') }}</template>
          </Step>
        </template>
        <template v-else>
          <Step :n="1" :title="t('识别萝卜 / 测量尺寸')">
            <Btn2 :main="t('识别萝卜')" :reason="busy" @click="radishDetect" />
            <template #expl>{{ radish?.dims ?? t('拍一张并识别红色萝卜，不移动机械臂。') }}</template>
          </Step>
          <img v-if="radish?.image" class="radish" :src="s10MediaUrl(radish.image.replace(/^\/media\//, ''), radish.at)" :alt="t('萝卜识别标注')" />
          <Step :n="2" :title="t('移动到观察位')">
            <Btn2 :main="t('移动到观察位…')" :reason="busy ?? (graspRunning || !s.vision?.ready ? t('视觉未就绪或正在抓取') : null)" @click="observe" />
          </Step>
          <Step :n="3" :title="t('一键抓取')">
            <Btn2 :main="t('一键抓取…')" kind="primary" :reason="busy ?? (graspRunning || !s.vision?.ready ? t('视觉未就绪或正在抓取') : null)" @click="skill" />
            <template #expl>{{ t('识别 → 抓取 → 抬起；完成后保持夹持，失败不会自动重试。可能移动底盘。') }}</template>
          </Step>
          <button class="btn btn-danger" :disabled="!!off" @click="act.s10({ action: 'arm_stop', label: CMD.graspStop })"><AppIcon name="stop" :size="14" />{{ t('停止抓取动作') }}</button>
        </template>
      </template>
    </div>
  </div>
</template>

<style scoped>
.s10body { display: flex; flex-direction: column; min-height: 0; flex: 1; }
.taskbar { display: grid; grid-template-columns: repeat(5, 1fr); gap: 4px; margin: 6px 0; flex: none; }
.tb {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  height: 48px;
  border-radius: var(--r-ctl);
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text);
  font: inherit;
  font-size: var(--fs-xs);
  cursor: pointer;
  justify-content: center;
}
.tb.on { background: var(--accent); color: var(--accent-ink); border-color: var(--accent); }
.tbdot { position: absolute; top: 5px; right: 6px; width: 7px; height: 7px; border-radius: 50%; background: var(--warn); }
.carea { flex: 1; min-height: 0; padding: 4px 2px 8px; }
.carea.offl { opacity: 0.55; }
.cardh { display: flex; align-items: center; gap: 6px; margin: 4px 0; }
.cardh h3 { margin: 0; font-size: var(--fs-md); }
.qm { width: 18px; height: 18px; border-radius: 50%; border: 1px solid var(--border); background: transparent; color: var(--text-dim); font-size: 11px; cursor: pointer; padding: 0; }
.grp { margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--border); }
.gl { font-weight: 600; font-size: var(--fs-sm); margin-bottom: 6px; display: flex; align-items: center; gap: 6px; }
.brow { display: flex; flex-wrap: wrap; gap: 6px; }
.expl { margin: 6px 0 0; font-size: var(--fs-xs); color: var(--text-dim); line-height: 1.5; }
.subflow { border: 1px solid var(--border); border-radius: var(--r-ctl); padding: 6px 10px; margin-top: 8px; }
.subflow h4 { margin: 2px 0; font-size: var(--fs-sm); }
.danger-zone { margin-top: 10px; padding: 8px 10px; border: 1px dashed var(--danger); border-radius: var(--r-ctl); }
.dangerc { color: var(--danger); }
.tbd { display: inline-block; padding: 0 6px; border-radius: 999px; border: 1px solid var(--warn); color: var(--warn); font-size: 11px; line-height: 16px; }
.okc { color: var(--ok); }
.warnc { color: var(--warn); }
.badc { color: var(--danger); }
.pre > div { display: flex; align-items: center; gap: 6px; font-size: var(--fs-sm); min-height: 28px; flex-wrap: wrap; }
.joints { display: grid; grid-template-columns: repeat(6, 1fr); gap: 4px; margin: 8px 0; }
.joints div { display: flex; flex-direction: column; align-items: center; font-size: var(--fs-xs); padding: 4px 0; border: 1px solid var(--border); border-radius: var(--r-ctl); }
.joints em { font-style: normal; color: var(--text-dim); }
.joints.stale { opacity: 0.5; }
.sec { margin-top: 8px; border: 1px solid var(--border); border-radius: var(--r-ctl); padding: 6px 10px; }
.sec summary { cursor: pointer; font-weight: 600; font-size: var(--fs-sm); }
.frow { display: flex; flex-wrap: wrap; gap: 8px; align-items: flex-end; width: 100%; }
.frow label { display: flex; flex-direction: column; gap: 2px; font-size: var(--fs-xs); color: var(--text-dim); }
.unit { display: flex; align-items: center; gap: 4px; }
.unit input { width: 72px; }
.jog { display: grid; grid-template-columns: 44px 1fr 44px; gap: 8px; align-items: center; margin-top: 6px; font-size: var(--fs-sm); }
.pk { height: 40px; border-radius: var(--r-ctl); border: 1px solid var(--border); background: var(--panel); color: var(--text); font-size: 18px; cursor: pointer; touch-action: none; }
.pk.on { background: var(--accent); color: var(--accent-ink); }
.pk:disabled { opacity: 0.4; }
.jin { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; margin: 6px 0; }
.jin label { display: flex; flex-direction: column; font-size: 11px; color: var(--text-dim); gap: 2px; }
.raw { margin: 0; max-height: 120px; overflow: auto; font-size: 11px; background: #05090f; padding: 6px; border-radius: var(--r-ctl); }
.seg2 { display: flex; gap: 4px; margin: 6px 0; }
.seg2 button { flex: 1; height: 32px; border: 1px solid var(--border); border-radius: var(--r-ctl); background: transparent; color: var(--text); cursor: pointer; font: inherit; font-size: var(--fs-xs); }
.seg2 button.on { background: var(--accent); color: var(--accent-ink); }
.radish { width: 100%; border-radius: var(--r-ctl); margin: 6px 0; }
.grow { flex: 1; min-width: 0; }
</style>
