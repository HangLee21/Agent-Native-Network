<script setup lang="ts">
/**
 * Operator console of the demo (docs/demo-design.md §4, §6): settings, checks before the start, the run
 * buttons (start / next / preset target / resume / abort / reset), both aircraft's status and the event log.
 * Return, landing and emergency stop stay on the flight monitor page: the script never does them.
 */
import { computed, onMounted, reactive, ref, watch } from 'vue'
import AppIcon from '@/components/common/AppIcon.vue'
import { isEn, t, tc } from '@/i18n'
import { routesApi, type RouteSummary } from '@/api/routes'
import { useToastStore } from '@/stores/toast'
import { useConfirmStore } from '@/stores/confirm'
import DemoMap from './DemoMap.vue'
import DemoVideo from './DemoVideo.vue'
import DemoCommLog from './DemoCommLog.vue'
import DemoStageBar from './DemoStageBar.vue'
import { useDemoStore } from './useDemoStore'
import {
  COLORS,
  EXEC_TEXT,
  PHASE_TEXT,
  STAGE_TEXT,
  AUTO_DRONE,
  demoApi,
  platformDevices,
  type DemoConfig,
  type Label,
  type LatLon,
  type PlatformDevice,
} from './demoApi'
import { SimFleetCenter } from './demoDefaults'
import { bearingDeg } from './demoGeo'

const demo = useDemoStore()
const toast = useToastStore()
const confirm = useConfirmStore()

const cfg = ref<DemoConfig | null>(null)
const form = ref<DemoConfig | null>(null)
const mappingText = ref('')
const routeList = ref<RouteSummary[]>([])
const busy = ref<string | null>(null)
const picking = ref<null | 'presetTarget' | 'dogStart' | 'simHomeA' | 'simHomeB' | 'sample'>(null)
const sample = reactive({ lat: SimFleetCenter.lat, lon: SimFleetCenter.lon, heading: 0 })
const videoLabel = ref<Label>('A')
const devices = ref<PlatformDevice[]>([])

const stage = computed(() => demo.state?.stage ?? 'READY')
const editable = computed(() => ['READY', 'DONE', 'ABORTED'].includes(stage.value))
const dirty = computed(() => !!form.value && !!cfg.value && JSON.stringify(form.value) !== JSON.stringify(cfg.value) || mappingDirty.value)
const mappingDirty = computed(() => !!cfg.value && mappingText.value !== JSON.stringify(cfg.value.dogMapping, null, 2))
const blocking = computed(() => demo.checks.some((c) => c.level === 'FAIL'))

onMounted(async () => {
  demo.start()
  await Promise.all([loadConfig(), loadRoutes()])
})

async function loadConfig(): Promise<void> {
  try {
    const c = await demoApi.config()
    cfg.value = c
    form.value = JSON.parse(JSON.stringify(c)) as DemoConfig
    mappingText.value = JSON.stringify(c.dogMapping, null, 2)
    const home = c.simHomeA ?? c.presetTarget
    if (home) Object.assign(sample, { lat: round6(home.lat), lon: round6(home.lon) })
  } catch (e) {
    toast.push('danger', t('读取演示设置失败：{msg}', { msg: msg(e) }))
  }
}

async function loadRoutes(): Promise<void> {
  try {
    routeList.value = await routesApi.list()
  } catch {
    routeList.value = []
  }
}

/** The platform's enabled aircraft, to pick which one plays A and B. */
async function loadDevices(): Promise<void> {
  try {
    devices.value = (await platformDevices()).filter((d) => d.enabled && d.droneSn)
  } catch {
    devices.value = []
  }
}

watch(() => form.value?.source, (s) => {
  if (s === 'PLATFORM') void loadDevices()
}, { immediate: true })

/** Centre the sample routes between the two aircraft, A on the left and B on the right. */
function sampleFromAircraft(): void {
  const a = demo.byLabel.A
  const b = demo.byLabel.B
  if (a?.lat == null || a.lon == null || b?.lat == null || b.lon == null) {
    toast.push('warn', t('还没有两架飞机的位置'))
    return
  }
  Object.assign(sample, {
    lat: round6((a.lat + b.lat) / 2),
    lon: round6((a.lon + b.lon) / 2),
    heading: Math.round(bearingDeg({ lat: a.lat, lon: a.lon }, { lat: b.lat, lon: b.lon }) - 90),
  })
}

// a config change made elsewhere (another console, auto-continue toggle) refreshes the form when it is clean
watch(() => demo.state?.autoContinue, (on) => {
  if (cfg.value && on !== undefined && cfg.value.autoContinue !== on) {
    cfg.value = { ...cfg.value, autoContinue: on }
    if (form.value) form.value.autoContinue = on
  }
})

function msg(e: unknown): string {
  return e instanceof Error ? e.message : String(e)
}

const round6 = (v: number) => Math.round(v * 1e6) / 1e6

async function run(name: string, fn: () => Promise<unknown>, ok?: string): Promise<void> {
  busy.value = name
  try {
    await fn()
    if (ok) toast.push('ok', ok, 2500)
  } catch (e) {
    toast.push('danger', t('{name}失败：{msg}', { name, msg: msg(e) }), 7000)
  } finally {
    busy.value = null
    void demo.refreshChecks()
  }
}

async function save(): Promise<void> {
  if (!form.value) return
  let mapping
  try {
    mapping = JSON.parse(mappingText.value)
  } catch {
    toast.push('danger', t('狗数据映射不是合法的 JSON'))
    return
  }
  await run(t('保存设置'), async () => {
    const saved = await demoApi.saveConfig({ ...form.value!, dogMapping: mapping })
    cfg.value = saved
    form.value = JSON.parse(JSON.stringify(saved)) as DemoConfig
    mappingText.value = JSON.stringify(saved.dogMapping, null, 2)
    await demo.loadRoutes()
  }, t('演示设置已保存'))
}

function discard(): void {
  if (!cfg.value) return
  form.value = JSON.parse(JSON.stringify(cfg.value)) as DemoConfig
  mappingText.value = JSON.stringify(cfg.value.dogMapping, null, 2)
}

async function generate(): Promise<void> {
  if (dirty.value && !(await confirm.ask({ title: t('放弃未保存的修改？'), message: t('生成示例航线会覆盖当前的航线选择和位置设置。'), confirmText: t('继续生成') }))) return
  await run(t('生成示例航线'), async () => {
    const saved = await demoApi.sampleRoutes(sample.lat, sample.lon, sample.heading)
    cfg.value = saved
    form.value = JSON.parse(JSON.stringify(saved)) as DemoConfig
    await loadRoutes()
    await demo.refresh()
  }, t('已生成 5 条示例航线并填入设置（可在航线库里修改）'))
}

function onPick(p: LatLon): void {
  const f = form.value
  const which = picking.value
  if (!which || !f) return
  const v = { lat: round6(p.lat), lon: round6(p.lon) }
  if (which === 'sample') Object.assign(sample, v)
  else f[which] = v
  picking.value = null
}

function setPoint(key: 'presetTarget' | 'dogStart' | 'simHomeA' | 'simHomeB', part: 'lat' | 'lon', value: string): void {
  const f = form.value
  if (!f) return
  const n = Number(value)
  if (value.trim() === '') {
    f[key] = null
    return
  }
  if (!Number.isFinite(n)) return
  f[key] = { ...(f[key] ?? { lat: 0, lon: 0 }), [part]: n }
}

const toggleAuto = () => run(t('切换自动继续'), () => demoApi.autoContinue(!demo.state?.autoContinue))
const start = () => run(t('开始'), () => demoApi.start())
const next = () => run(t('下一步'), () => demoApi.next())
const preset = () => run(t('使用预设目标'), () => demoApi.presetTarget())
const resume = (l: Label) => run(t('恢复 {label}', { label: l }), () => demoApi.resume(l))
const simPause = (l: Label) => run(t('模拟 {label} 靠近暂停', { label: l }), () => demoApi.simPause(l))
const reset = () => run(t('重置'), () => demoApi.reset())

/** Only on the operator's explicit confirmation (S-06: the other aircraft's return height is unknown to the platform). */
async function confirmRth(): Promise<void> {
  const c = demo.state?.rthConfirm
  if (!c) return
  const ok = await confirm.ask({
    title: t('确认两架返航高度不同？'),
    message: `${c.message}`,
    details: [t('请先在另一台遥控器的 Pilot 2 里核对它的返航高度，确认两架相差足够再继续。')],
    confirmText: t('已确认，继续起飞'),
    focus: 'cancel',
  })
  if (ok) await run(t('确认返航高度'), () => demoApi.confirmRth())
}

async function abort(): Promise<void> {
  const ok = await confirm.ask({
    title: t('中止演示？'),
    message: t('两架飞机的当前航线都会结束，原地悬停。剧本不会让飞机返航或降落，请之后在飞行监控页操作。'),
    confirmText: t('中止，原地悬停'),
    danger: true,
    focus: 'confirm',
  })
  if (ok) await run(t('中止'), () => demoApi.abort())
}

const ROUTE_FIELDS: { key: 'routeA1' | 'routeB1' | 'routeHigh2' | 'routeLow2' | 'routeLowFollow'; label: string }[] = [
  { key: 'routeA1', label: t('A 第一段（左侧探索 → 汇合点）') },
  { key: 'routeB1', label: t('B 第一段（右侧探索 → 汇合点）') },
  { key: 'routeHigh2', label: t('高空第二段（俯瞰）') },
  { key: 'routeLow2', label: t('低空第二段（细查 → 发现目标）') },
  { key: 'routeLowFollow', label: t('低空跟随（引导机器狗）') },
]

const MESSAGE_LABELS: Record<string, string> = {
  'start.A': t('A 出发'),
  'start.B': t('B 出发'),
  'exchange.A': t('汇合：A → B'),
  'exchange.B': t('汇合：B → A'),
  'rescan.high': t('第二阶段：高空'),
  'rescan.low': t('第二阶段：低空'),
  'target.found': t('发现目标'),
  'target.dog': t('低空 → 狗：目标已发送'),
  'guide.start': t('低空 → 狗：开始引导'),
  'dog.arrived': t('狗到达'),
  done: t('完成'),
}

const POINTS: { key: 'presetTarget' | 'dogStart' | 'simHomeA' | 'simHomeB'; label: string; sim?: boolean }[] = [
  { key: 'presetTarget', label: t('预设目标点（等不到视频框选时使用）') },
  { key: 'dogStart', label: t('狗的起点（模拟狗、推荐路径的起点）') },
  { key: 'simHomeA', label: t('模拟 A 起飞点'), sim: true },
  { key: 'simHomeB', label: t('模拟 B 起飞点'), sim: true },
]

function openShow(): void {
  window.open(`${location.pathname}#/demo/show`, 'demo-show')
}
</script>

<template>
  <div class="console">
    <!-- settings -->
    <section class="panel col settings">
      <div class="panel-head">
        <span>{{ t('演示设置') }}</span>
        <span v-if="!editable" class="tag">{{ t('演示进行中，暂不能改') }}</span>
        <span v-else-if="dirty" class="tag warn">{{ t('未保存') }}</span>
      </div>
      <div v-if="form" class="panel-body scroll form">
        <fieldset :disabled="!editable">
          <label class="field">
            <span>{{ t('飞机数据源') }}</span>
            <select v-model="form.source" class="input">
              <option value="SIM">{{ t('模拟两机（演示服务内部，不连接任何飞机）') }}</option>
              <option value="PLATFORM">{{ t('平台两机（真实飞机）') }}</option>
            </select>
          </label>
          <p v-if="form.source === 'PLATFORM' && demo.state?.source !== 'PLATFORM'" class="hint warn">{{ t('保存后生效。') }}{{ demo.state?.sourceReason ?? '' }}</p>
          <p v-else-if="demo.state && !demo.state.sourceAvailable" class="hint warn">{{ demo.state.sourceReason }}</p>
          <label class="field">
            <span>{{ t('机器狗') }}</span>
            <select v-model="form.dogMode" class="input">
              <option value="SIM">{{ t('模拟狗（沿推荐路径走，生成假的语义地图）') }}</option>
              <option value="EXTERNAL">{{ t('外部数据（狗那边按映射上报）') }}</option>
              <option value="SKIP">{{ t('跳过（没有狗，只演示飞机部分）') }}</option>
            </select>
          </label>
          <div v-if="form.source === 'PLATFORM'" class="row2">
            <label v-for="l in ['A', 'B'] as Label[]" :key="l" class="field">
              <span>{{ t('{label} 机', { label: l }) }}</span>
              <select v-model="form[l === 'A' ? 'droneA' : 'droneB']" class="input">
                <option :value="AUTO_DRONE">{{ t('自动（平台里标为 {label} 的飞机）', { label: l }) }}</option>
                <option v-for="d in devices" :key="d.droneSn!" :value="d.droneSn">{{ d.label }} · {{ d.droneSn }}{{ d.online ? '' : t('（离线）') }}</option>
              </select>
            </label>
          </div>
          <div v-else class="row2">
            <label class="field"><span>{{ t('{label} 机', { label: 'A' }) }}</span><input class="input" :value="t('模拟 {label}', { label: 'A' })" disabled /></label>
            <label class="field"><span>{{ t('{label} 机', { label: 'B' }) }}</span><input class="input" :value="t('模拟 {label}', { label: 'B' })" disabled /></label>
          </div>
          <label class="field">
            <span>{{ t('第二阶段谁飞高空') }}</span>
            <select v-model="form.highLabel" class="input">
              <option value="A">{{ t('A 高空（32 m），B 低空（20 m）') }}</option>
              <option value="B">{{ t('B 高空，A 低空') }}</option>
            </select>
          </label>

          <h4 class="section-title">{{ t('航线') }}</h4>
          <label v-for="f in ROUTE_FIELDS" :key="f.key" class="field">
            <span>{{ f.label }}</span>
            <select v-model="form[f.key]" class="input">
              <option :value="null">{{ t('（未选择）') }}</option>
              <option v-for="r in routeList" :key="r.id" :value="r.id">{{ r.name }} · {{ t('{n} 点', { n: r.waypointCount }) }} · {{ Math.round(r.minHeight) }}–{{ Math.round(r.maxHeight) }} m</option>
            </select>
          </label>
          <details class="sample">
            <summary>{{ t('生成示例航线（模板）') }}</summary>
            <p class="hint">{{ t('按约定的间距生成 5 条航线：起飞点、并排段、汇合点都隔开 30 m，第二阶段 32 m / 20 m，结束时悬停。生成后可在航线库里改。') }}</p>
            <div class="row3">
              <label class="field"><span>{{ t('中心纬度') }}</span><input v-model.number="sample.lat" class="input num" type="number" step="0.000001" /></label>
              <label class="field"><span>{{ t('中心经度') }}</span><input v-model.number="sample.lon" class="input num" type="number" step="0.000001" /></label>
              <label class="field"><span>{{ t('朝向 °') }}</span><input v-model.number="sample.heading" class="input num" type="number" step="5" /></label>
            </div>
            <div class="row">
              <button class="btn btn-sm" type="button" :class="{ 'btn-primary': picking === 'sample' }" @click="picking = picking === 'sample' ? null : 'sample'">{{ t('在地图上选中心') }}</button>
              <button class="btn btn-sm" type="button" :title="t('中心放在两架飞机中间，A 在左、B 在右')" @click="sampleFromAircraft">{{ t('按两架飞机位置') }}</button>
              <button class="btn btn-sm" type="button" :disabled="busy !== null" @click="generate">{{ t('生成并填入') }}</button>
            </div>
          </details>

          <h4 class="section-title">{{ t('位置') }}</h4>
          <div v-for="p in POINTS" v-show="!p.sim || form.source === 'SIM'" :key="p.key" class="point">
            <span class="plabel">{{ p.label }}</span>
            <div class="row3">
              <input class="input num" :placeholder="t('纬度')" :value="form[p.key]?.lat ?? ''" @change="setPoint(p.key, 'lat', ($event.target as HTMLInputElement).value)" />
              <input class="input num" :placeholder="t('经度')" :value="form[p.key]?.lon ?? ''" @change="setPoint(p.key, 'lon', ($event.target as HTMLInputElement).value)" />
              <button class="btn btn-sm" type="button" :class="{ 'btn-primary': picking === p.key }" @click="picking = picking === p.key ? null : p.key">{{ t('地图选点') }}</button>
            </div>
          </div>

          <h4 class="section-title">{{ t('节奏') }}</h4>
          <div class="row2">
            <label class="field"><span>{{ t('A 离开起飞点多远再放 B（m）') }}</span><input v-model.number="form.staggerDistanceM" class="input num" type="number" min="1" /></label>
            <label class="field"><span>{{ t('最多等多久放 B（s）') }}</span><input v-model.number="form.staggerMaxWaitS" class="input num" type="number" min="1" /></label>
            <label class="field"><span>{{ t('交换信息展示（s）') }}</span><input v-model.number="form.exchangeHoldS" class="input num" type="number" min="1" /></label>
            <label class="field"><span>{{ t('等视频框选（s）') }}</span><input v-model.number="form.targetWaitS" class="input num" type="number" min="1" /></label>
            <label class="field"><span>{{ t('目标展示（s）') }}</span><input v-model.number="form.targetHoldS" class="input num" type="number" min="1" /></label>
          </div>
          <div v-if="form.source === 'SIM'" class="row2">
            <label class="field"><span>{{ t('模拟倍速') }}</span><input v-model.number="form.simSpeedFactor" class="input num" type="number" min="0.25" max="20" step="0.25" /></label>
            <label class="field"><span>{{ t('模拟狗速度（m/s）') }}</span><input v-model.number="form.simDogSpeed" class="input num" type="number" min="0.2" max="3" step="0.1" /></label>
          </div>

          <details>
            <summary>{{ t('协同消息文字') }}</summary>
            <label v-for="(label, key) in MESSAGE_LABELS" :key="key" class="field">
              <span>{{ label }}</span>
              <input v-model="form.messages[key]" class="input" />
            </label>
          </details>
          <details :open="form.dogMode === 'EXTERNAL'">
            <summary>{{ t('狗数据映射（外部数据）') }}</summary>
            <p
              class="hint"
              v-html="t('狗上报到 {ingest}，任意 JSON；这里写字段路径（a.b[0].c）、坐标系（WGS84 / GCJ02 / LOCAL，LOCAL 需要 origin）和朝向单位。狗可以从 {target} 取目标和推荐路径。', {
                ingest: '<code>POST /api/v1/demo/dog/ingest</code>',
                target: '<code>GET /api/v1/demo/dog/target</code>',
              })"
            />
            <textarea v-model="mappingText" class="input mapping num" rows="12" spellcheck="false" />
          </details>
        </fieldset>
      </div>
      <div class="panel-foot">
        <button class="btn" type="button" :disabled="!dirty || busy !== null" @click="discard">{{ t('放弃修改') }}</button>
        <button class="btn btn-primary" type="button" :disabled="!dirty || !editable || busy !== null" @click="save">{{ t('保存设置') }}</button>
      </div>
    </section>

    <!-- map, camera, log -->
    <section class="center">
      <div class="map-box panel">
        <DemoMap compact @pick="onPick" />
        <div v-if="picking" class="pick-hint">{{ t('在地图上点一下设置位置') }} <button class="btn btn-sm" type="button" @click="picking = null">{{ t('取消') }}</button></div>
      </div>
      <div class="lower">
        <div class="panel cam">
          <div class="panel-head">
            <span>{{ t('画面') }}</span>
            <div class="seg">
              <button v-for="l in ['A', 'B'] as Label[]" :key="l" type="button" :class="{ on: videoLabel === l }" @click="videoLabel = l">{{ l }}</button>
            </div>
          </div>
          <div class="cam-body"><DemoVideo :drone="demo.byLabel[videoLabel] ?? null" compact /></div>
        </div>
        <div class="panel events">
          <div class="panel-head"><span>{{ t('事件') }}</span></div>
          <div class="events-body"><DemoCommLog /></div>
        </div>
      </div>
    </section>

    <!-- run -->
    <section class="panel col run">
      <div class="panel-head">
        <span>{{ t('运行') }}</span>
        <button class="btn btn-sm" type="button" @click="openShow"><AppIcon name="monitor" :size="14" /> {{ t('打开观众页') }}</button>
      </div>
      <div class="panel-body scroll">
        <DemoStageBar compact class="steps" />
        <div class="stage-now">
          <b>{{ STAGE_TEXT[stage] }}</b>
          <span v-if="demo.state?.source === 'SIM'" class="tag">{{ t('模拟') }}</span>
        </div>
        <p class="waiting" :class="{ warn: (demo.state?.paused.length ?? 0) > 0 }">{{ demo.state?.waiting }}</p>

        <div v-if="demo.state?.rthConfirm" class="notice danger">
          <b>{{ t('{label} 起飞前需要你确认返航高度', { label: demo.state.rthConfirm.label }) }}</b>
          <p>{{ demo.state.rthConfirm.message }}</p>
          <button class="btn btn-warn" type="button" :disabled="busy !== null" @click="confirmRth">{{ t('确认返航高度不同，继续起飞') }}</button>
        </div>
        <div v-if="demo.proximity && demo.proximity.level !== 'clear'" class="notice" :class="demo.proximity.level === 'hold' ? 'danger' : 'warn'">
          <b>{{ demo.proximity.level === 'hold' ? t('两机太近：平台已让 {who} 悬停', { who: demo.proximity.stopped.join(isEn() ? ' and ' : '、') || t('飞机') }) : t('两机靠近') }}</b>
          <p class="num">
            {{
              t('水平 {h} m · 高度差 {v} m · 预计最近 {p} m（阈值 {th} m）', {
                h: demo.proximity.horizontalM.toFixed(0),
                v: demo.proximity.verticalM?.toFixed(0) ?? '--',
                p: demo.proximity.predictedMinM.toFixed(0),
                th: demo.proximity.thresholdM.toFixed(0),
              })
            }}
          </p>
        </div>
        <p v-if="demo.state" class="hint">
          {{
            t('两机防撞：{sim}平台设置为{mode}，起飞航线的返航高度至少相差 {m} m（在设置页修改）', {
              sim: demo.state.source === 'SIM' ? t('模拟两机不做监测；') : '',
              mode: demo.state.fleetSafety.proximityMode === 'HOLD' ? t('「报警并悬停」') : t('「只报警」'),
              m: demo.state.fleetSafety.rthSeparationM.toFixed(0),
            })
          }}
        </p>

        <label class="auto">
          <input type="checkbox" :checked="demo.state?.autoContinue" :disabled="busy !== null" @change="toggleAuto" />
          <span>{{ t('自动继续') }}<small>{{ t('需要给飞机下发新航线的步骤自动进行；关掉则每步等你点「下一步」。靠近暂停不会自动恢复。') }}</small></span>
        </label>

        <div class="buttons">
          <button v-if="stage === 'READY'" class="btn btn-primary btn-lg" type="button" :disabled="busy !== null || blocking || dirty" @click="start">
            <AppIcon name="play" :size="16" /> {{ t('开始') }}
          </button>
          <button v-else class="btn btn-primary btn-lg" type="button" :disabled="busy !== null || !demo.state?.canNext" @click="next">
            <AppIcon name="chevron" :size="16" /> {{ t('下一步') }}
          </button>
          <p class="hint">{{ dirty && stage === 'READY' ? t('先保存设置再开始') : t('下一步：{hint}', { hint: demo.state?.nextHint ?? '' }) }}</p>
          <button v-if="stage === 'S3_TARGET' && !demo.state?.target" class="btn" type="button" :disabled="busy !== null" @click="preset">{{ t('使用预设目标') }}</button>
          <div class="row">
            <button class="btn btn-warn grow" type="button" :disabled="busy !== null || !['S1_EXPLORE', 'S1_RENDEZVOUS', 'S2_RESCAN', 'S3_TARGET', 'S4_GUIDE'].includes(stage)" @click="abort">{{ t('中止（悬停）') }}</button>
            <button class="btn grow" type="button" :disabled="busy !== null || !['DONE', 'ABORTED'].includes(stage)" @click="reset">{{ t('重置') }}</button>
          </div>
          <p class="hint">{{ t('返航、降落、急停在飞行监控页操作；剧本不会自动做这些。') }}</p>
        </div>

        <h4 class="section-title">{{ tc('plural', '飞机') }}</h4>
        <div v-for="l in ['A', 'B'] as Label[]" :key="l" class="drone" :style="{ '--c': COLORS[l] }">
          <template v-if="demo.byLabel[l]">
            <div class="d-head">
              <b class="badge">{{ l }}</b>
              <span class="dim">{{ demo.byLabel[l]!.id }}</span>
              <span class="grow" />
              <span class="st" :class="demo.byLabel[l]!.execution.state.toLowerCase()">{{ EXEC_TEXT[demo.byLabel[l]!.execution.state] }}</span>
            </div>
            <div class="d-grid num">
              <span>{{ PHASE_TEXT[demo.byLabel[l]!.phase] }}</span>
              <span>{{ demo.byLabel[l]!.relativeHeight?.toFixed(1) ?? '--' }} m</span>
              <span>{{ demo.byLabel[l]!.horizontalSpeed?.toFixed(1) ?? '--' }} m/s</span>
              <span>{{ demo.byLabel[l]!.battery ?? '--' }}%</span>
              <span v-if="demo.byLabel[l]!.execution.total">{{ t('航点 {i}/{n}', { i: Math.min(demo.byLabel[l]!.execution.currentIndex + 1, demo.byLabel[l]!.execution.total), n: demo.byLabel[l]!.execution.total }) }}</span>
            </div>
            <div class="row">
              <button v-if="demo.byLabel[l]!.execution.state === 'PAUSED'" class="btn btn-sm btn-primary" type="button" :disabled="busy !== null" @click="resume(l)">{{ t('恢复 {label}', { label: l }) }}</button>
              <button v-if="demo.state?.source === 'SIM' && demo.byLabel[l]!.execution.state !== 'PAUSED' && ['FLYING', 'AT_WAYPOINT', 'TAKING_OFF'].includes(demo.byLabel[l]!.execution.state)" class="btn btn-sm btn-ghost" type="button" :disabled="busy !== null" @click="simPause(l)">{{ t('模拟靠近暂停') }}</button>
            </div>
          </template>
          <p v-else class="dim">{{ t('{label}（{id}）未找到', { label: l, id: demo.state?.drones[l] }) }}</p>
        </div>
        <p v-if="demo.link" class="dim small">{{ t('两机水平距离 {h} m，高度差 {v} m', { h: demo.link.horizontalM.toFixed(0), v: demo.link.verticalM.toFixed(0) }) }}</p>

        <template v-if="stage === 'READY'">
          <h4 class="section-title">{{ t('开始前检查') }}</h4>
          <ul class="checks">
            <li v-for="(c, i) in demo.checks" :key="i" :class="c.level.toLowerCase()">
              <AppIcon :name="c.level === 'OK' ? 'check' : c.level === 'WARN' ? 'alert' : 'x'" :size="14" />
              <span>{{ c.text }}</span>
            </li>
          </ul>
          <p class="hint">{{ t('航线要求：错开起飞且起飞点分开；并排段和汇合点水平相距 ≥ 30 m，同方向平行进入汇合点；第二阶段高度差 ≥ 12 m；两架返航高度不同；两个飞手各拿一台遥控器。') }}</p>
        </template>
      </div>
    </section>
  </div>
</template>

<style scoped>
.console {
  position: absolute;
  inset: 0;
  display: grid;
  grid-template-columns: 340px minmax(0, 1fr) 340px;
  gap: var(--sp-3);
  padding: var(--sp-3);
}
.col {
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.col > .panel-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}
.panel-foot {
  display: flex;
  justify-content: flex-end;
  gap: var(--sp-2);
  padding: var(--sp-2) var(--sp-3);
  border-top: 1px solid var(--border);
}
.form fieldset {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
  margin: 0;
  padding: 0;
  border: 0;
}
.row2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--sp-2);
}
.row3 {
  display: grid;
  grid-template-columns: 1fr 1fr auto;
  gap: var(--sp-2);
}
.point .plabel {
  display: block;
  margin-bottom: 4px;
  color: var(--text-dim);
  font-size: var(--fs-xs);
}
.hint {
  margin: 0;
  color: var(--text-dim);
  font-size: var(--fs-xs);
  line-height: 1.5;
}
.hint.warn {
  color: var(--warn);
}
details summary {
  cursor: pointer;
  color: var(--text-dim);
  font-size: var(--fs-sm);
}
details[open] {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}
.mapping {
  font-size: 12px;
  resize: vertical;
}
.center {
  display: grid;
  grid-template-rows: minmax(0, 1.4fr) minmax(0, 1fr);
  gap: var(--sp-3);
  min-width: 0;
  min-height: 0;
}
.map-box {
  position: relative;
  overflow: hidden;
}
.pick-hint {
  position: absolute;
  left: 50%;
  top: 12px;
  z-index: 700;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  border-radius: 8px;
  background: var(--overlay);
  font-size: var(--fs-sm);
}
.lower {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: var(--sp-3);
  min-height: 0;
}
.cam,
.events {
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.cam-body {
  flex: 1;
  min-height: 0;
  position: relative;
}
.events-body {
  flex: 1;
  min-height: 0;
  padding: 0 var(--sp-2);
}
.seg {
  display: flex;
  gap: 2px;
}
.seg button {
  padding: 1px 10px;
  border: 1px solid var(--border);
  background: var(--panel-2);
  color: var(--text-dim);
  border-radius: 4px;
  cursor: pointer;
}
.seg button.on {
  border-color: var(--accent);
  color: var(--text);
}
.steps {
  flex-wrap: wrap;
  row-gap: 6px;
}
.stage-now {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: var(--sp-3);
  font-size: var(--fs-lg);
}
.waiting {
  margin: 6px 0 var(--sp-3);
  color: var(--text-dim);
  font-size: var(--fs-sm);
  line-height: 1.5;
}
.waiting.warn {
  color: var(--warn);
  font-weight: 600;
}
.notice {
  margin: 0 0 var(--sp-3);
  padding: var(--sp-2) var(--sp-3);
  border: 1px solid var(--warn);
  border-radius: var(--r-ctl);
  background: color-mix(in srgb, var(--warn) 12%, transparent);
  font-size: var(--fs-sm);
}
.notice.danger {
  border-color: var(--danger);
  background: color-mix(in srgb, var(--danger) 12%, transparent);
}
.notice p {
  margin: 4px 0 var(--sp-2);
  color: var(--text-dim);
  line-height: 1.5;
}
.auto {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  padding: var(--sp-2);
  border: 1px solid var(--border);
  border-radius: var(--r-ctl);
  cursor: pointer;
}
.auto small {
  display: block;
  margin-top: 2px;
  color: var(--text-dim);
  font-size: var(--fs-xs);
  line-height: 1.4;
}
.buttons {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  margin: var(--sp-3) 0;
}
.drone {
  margin-bottom: var(--sp-2);
  padding: var(--sp-2);
  border: 1px solid var(--border);
  border-left: 3px solid var(--c);
  border-radius: var(--r-ctl);
}
.d-head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.badge {
  display: grid;
  place-items: center;
  width: 22px;
  height: 22px;
  border-radius: 5px;
  background: var(--c);
  color: #0b1220;
}
.st {
  font-size: var(--fs-xs);
}
.st.paused,
.st.failed,
.st.aborted {
  color: var(--warn);
  font-weight: 600;
}
.st.completed {
  color: var(--ok);
}
.d-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 12px;
  margin: 6px 0;
  font-size: var(--fs-sm);
}
.small {
  font-size: var(--fs-xs);
}
.checks {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin: 0 0 var(--sp-2);
  padding: 0;
  list-style: none;
  font-size: var(--fs-sm);
}
.checks li {
  display: flex;
  gap: 6px;
  align-items: flex-start;
}
.checks li.ok {
  color: var(--ok);
}
.checks li.ok span {
  color: var(--text);
}
.checks li.warn {
  color: var(--warn);
}
.checks li.fail {
  color: var(--danger);
}
.tag.warn {
  color: var(--warn);
  border-color: var(--warn);
}
</style>
