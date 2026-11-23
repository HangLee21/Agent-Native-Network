<script setup lang="ts">
/**
 * Records list (R-19 ~ R-23, D-40; ui-design.md 2.6, 2.6.1): drones' flights and dogs' records in one table, newest
 * first. Filters (date, device, result, route, alerts, simulated), replay, replay together (overlapping records, or
 * any rows ticked), protect, delete, delete only the video. A dog row opens the joint replay with that one dog.
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useFleetStore } from '@/stores/fleet'
import AppIcon from '@/components/common/AppIcon.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import TrackThumb from '@/components/history/TrackThumb.vue'
import { ApiError } from '@/api/http'
import { historyApi, OUTCOME_LABELS, VIDEO_LABELS, type Outcome, type SessionSummary } from '@/api/history'
import { dogRecordsApi, DOG_OUTCOME_LABELS, dogName, type DogOutcome, type DogRecordSummary } from '@/api/dogRecords'
import { dog2Api } from '@/api/dogv2'
import { DOG_TRACK_COLORS } from '@/utils/jointReplay'
import { togetherPath, type RecordRef } from '@/utils/records'
import { useRoutesStore } from '@/stores/routes'
import { useHistoryStore } from '@/stores/history'
import { useToastStore } from '@/stores/toast'
import { useConfirmStore } from '@/stores/confirm'
import { bytes, dateTime, duration, meters } from '@/utils/format'
import { t, tc } from '@/i18n'

const route = useRoute()
const router = useRouter()
const routes = useRoutesStore()
const history = useHistoryStore()
const toast = useToastStore()
const confirm = useConfirmStore()

/** One row: a drone's flight or a dog's record. key = "drone:<id>" / "dog:<id>". */
type Row = { kind: 'drone'; key: string; s: SessionSummary; at: number } | { kind: 'dog'; key: string; s: DogRecordSummary; at: number }

const flights = ref<SessionSummary[]>([])
/** Dog records in the date range (all dogs, every result): the rows are filtered here, overlaps need them all. */
const dogAll = ref<DogRecordSummary[]>([])
const loading = ref(false)
const loaded = ref(false)
const error = ref<string | null>(null)
const selected = ref<Set<string>>(new Set())

const fromDate = ref('')
const toDate = ref('')
/** '' | 'drone:<OUTCOME>' | 'dog:<OUTCOME>' */
const outcome = ref('')
const routeId = ref(typeof route.query.route === 'string' ? route.query.route : '')
/** '' = every device; 'drone:<aircraft or RC SN>' (D-27); 'dog:<dog id>'. Old links: ?drone=<sn>. */
const device = ref(typeof route.query.drone === 'string' ? `drone:${route.query.drone}` : typeof route.query.dog === 'string' ? `dog:${route.query.dog}` : '')
const fleet = useFleetStore()
const hasAlerts = ref(false)
const SIM_KEY = 'uav.history.includeSimulated'
function loadSim(): boolean {
  try {
    return localStorage.getItem(SIM_KEY) === '1'
  } catch {
    return false
  }
}
const includeSimulated = ref(loadSim())
watch(includeSimulated, (v) => {
  try {
    localStorage.setItem(SIM_KEY, v ? '1' : '0')
  } catch {
    /* storage unavailable */
  }
})

const OUTCOME_CLASS: Record<Outcome | DogOutcome, string> = {
  LANDED: '', COMPLETED: 'ok', STOPPED: 'warn', RETURNED_HOME: '', EMERGENCY_STOP: 'danger', LINK_LOST: 'danger', INTERRUPTED: 'warn',
  ENDED: '', SOFT_ESTOP: 'danger',
}

/** Dogs known to the new dog system (for the device filter before they have any record). */
const knownDogs = ref<{ id: string; name: string }[]>([])
const dogs = computed(() => {
  const m = new Map<string, string>()
  for (const d of knownDogs.value) m.set(d.id, d.name)
  for (const r of dogAll.value) if (!m.has(r.dogId)) m.set(r.dogId, dogName(r))
  return [...m.entries()].sort((a, b) => a[0].localeCompare(b[0])).map(([id, name]) => ({ id, name }))
})
function dogColor(id: string): string {
  const i = dogs.value.findIndex((d) => d.id === id)
  return DOG_TRACK_COLORS[Math.max(0, i) % DOG_TRACK_COLORS.length]!
}

function dayStart(d: string): number | undefined {
  return d ? new Date(`${d}T00:00:00`).getTime() : undefined
}

const deviceKind = computed(() => (device.value ? device.value.slice(0, device.value.indexOf(':')) : ''))
const deviceId = computed(() => (device.value ? device.value.slice(device.value.indexOf(':') + 1) : ''))
const outcomeKind = computed(() => (outcome.value ? outcome.value.slice(0, outcome.value.indexOf(':')) : ''))
const outcomeValue = computed(() => (outcome.value ? outcome.value.slice(outcome.value.indexOf(':') + 1) : ''))
/** A filter that only drones have (a drone, a drone result, a route) hides the dogs, and the other way round. */
const showDrones = computed(() => deviceKind.value !== 'dog' && outcomeKind.value !== 'dog')
const showDogs = computed(() => deviceKind.value !== 'drone' && outcomeKind.value !== 'drone' && !routeId.value)

let generation = 0

async function refresh(): Promise<void> {
  loading.value = true
  error.value = null
  const from = dayStart(fromDate.value)
  const to = toDate.value ? dayStart(toDate.value)! + 86_400_000 : undefined
  // dog records are few: fetched for the dates only and filtered here (a drone row's overlaps need all of them);
  // they arrive on their own, so a slow or missing dog API never holds up the flights
  const mine = ++generation
  dogRecordsApi.list({ from, to, includeSimulated: includeSimulated.value })
    .then((d) => { if (mine === generation) dogAll.value = d })
    .catch(() => { if (mine === generation) dogAll.value = [] })
  try {
    flights.value = showDrones.value
      ? await historyApi.list({
        from, to,
        outcome: outcomeKind.value === 'drone' ? outcomeValue.value : undefined,
        routeId: routeId.value || undefined,
        drone: deviceKind.value === 'drone' ? deviceId.value : undefined,
        hasAlerts: hasAlerts.value || undefined,
        includeSimulated: includeSimulated.value,
      })
      : []
    selected.value = new Set([...selected.value].filter((k) => rows.value.some((r) => r.key === k)))
    loaded.value = true
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('加载失败')
  } finally {
    loading.value = false
  }
}

const dogRows = computed(() => (showDogs.value ? dogAll.value.filter((r) =>
  (deviceKind.value !== 'dog' || r.dogId === deviceId.value)
  && (outcomeKind.value !== 'dog' || r.outcome === outcomeValue.value)
  && (!hasAlerts.value || r.alertCount > 0)) : []))

const rows = computed<Row[]>(() => [
  ...flights.value.map((s) => ({ kind: 'drone' as const, key: `drone:${s.id}`, s, at: s.takeoffAt ?? s.startedAt })),
  ...dogRows.value.map((s) => ({ kind: 'dog' as const, key: `dog:${s.id}`, s, at: s.startedAt })),
].sort((a, b) => b.at - a.at))

onMounted(() => {
  void routes.refresh()
  void refresh()
  dog2Api.list().then((r) => {
    knownDogs.value = r.dogs.map((d) => ({ id: d.id, name: dogName({ dogModel: d.model, dogLabel: d.label, dogId: d.id }) }))
  }).catch(() => undefined)
})
watch([fromDate, toDate, outcome, routeId, device, hasAlerts, includeSimulated], () => void refresh())
watch(() => history.changed, () => void refresh())

const filtersActive = computed(() => !!(fromDate.value || toDate.value || outcome.value || routeId.value || device.value || hasAlerts.value))

/** The device column: with dogs, several drones, or a flight flown together with another drone's (D-33). */
const showDevice = computed(() => fleet.drones.length > 1 || dogs.value.length > 0 || flights.value.some((s) => s.together?.length))

function spanOf(r: Row): [number, number] {
  return [r.at, r.s.landedAt ?? r.s.endedAt ?? Date.now()]
}

/** Records of other devices overlapping this one in time: a flight's other drones, and every dog record. */
function overlaps(r: Row): RecordRef[] {
  if (r.kind === 'dog') return r.s.together.map((x) => ({ kind: x.kind, id: x.id }))
  const [a, b] = spanOf(r)
  const dogsThen = dogAll.value.filter((d) => d.startedAt < b && a < (d.endedAt ?? Date.now())).map((d) => ({ kind: 'dog' as const, id: d.id }))
  return [...(r.s.together ?? []).map((x) => ({ kind: 'drone' as const, id: x.id })), ...dogsThen]
}

/** Names of the devices of overlapping records, for the button's tooltip. */
function overlapNames(r: Row): string {
  const names = new Set<string>()
  if (r.kind === 'dog') {
    for (const x of r.s.together) names.add(x.kind === 'dog' ? dogs.value.find((d) => d.id === x.device)?.name ?? x.device : fleet.label(x.device))
  } else {
    for (const x of r.s.together ?? []) names.add(fleet.label(x.gatewaySn))
    for (const x of overlaps(r)) if (x.kind === 'dog') {
      const d = dogAll.value.find((z) => z.id === x.id)
      if (d) names.add(dogName(d))
    }
  }
  return [...names].join(t('、'))
}

function refOf(r: Row): RecordRef {
  return { kind: r.kind, id: r.s.id }
}

/** This record and every overlapping one, replayed together. */
function openTogether(r: Row): void {
  void router.push(togetherPath([refOf(r), ...overlaps(r)]))
}

function open(r: Row): void {
  if (r.kind === 'drone') void router.push(`/history/${r.s.id}`)
  else void router.push(togetherPath([refOf(r)]))
}

function deviceName(r: Row): string {
  return r.kind === 'drone' ? fleet.label(r.s.gatewaySn ?? r.s.droneSn) : dogName(r.s)
}
function deviceColor(r: Row): string {
  return r.kind === 'drone' ? fleet.color(r.s.gatewaySn ?? r.s.droneSn) : dogColor(r.s.dogId)
}
function outcomeText(r: Row): string | null {
  if (!r.s.outcome) return null
  return r.kind === 'drone' ? OUTCOME_LABELS[r.s.outcome] : DOG_OUTCOME_LABELS[r.s.outcome]
}

function seconds(r: Row): number | null {
  const [a] = spanOf(r)
  const to = r.s.landedAt ?? r.s.endedAt
  return to ? (to - a) / 1000 : null
}

function toggle(key: string): void {
  const next = new Set(selected.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  selected.value = next
}

const allSelected = computed(() => rows.value.length > 0 && rows.value.every((r) => selected.value.has(r.key)))
function toggleAll(): void {
  selected.value = allSelected.value ? new Set() : new Set(rows.value.map((r) => r.key))
}
const selectedRows = computed(() => rows.value.filter((r) => selected.value.has(r.key)))

/** Ticked rows replayed together, any mix of drones and dogs. */
function playSelected(): void {
  void router.push(togetherPath([...selectedRows.value].sort((a, b) => a.at - b.at).map(refOf)))
}

async function protect(r: Row): Promise<void> {
  const on = !r.s.protectedFlag
  try {
    if (r.kind === 'drone') await historyApi.patch(r.s.id, { protectedFlag: on })
    else await dogRecordsApi.patch(r.s.id, { protectedFlag: on })
    r.s.protectedFlag = on
    toast.push('ok', on ? t('已保护，批量删除时会跳过') : t('已取消保护'))
  } catch (e) {
    toast.push('danger', e instanceof ApiError ? e.message : t('操作失败'))
  }
}

async function removeOne(r: Row): Promise<void> {
  const ok = await confirm.ask({
    title: r.kind === 'drone' ? t('删除飞行记录') : t('删除记录'),
    message: r.kind === 'drone'
      ? t('确认删除 {time} 的飞行记录？航迹、指令、事件和视频都会删除，不可撤销。', { time: dateTime(r.s.startedAt) })
      : t('确认删除 {name} {time} 的记录？轨迹、指令、事件和视频都会删除，不可撤销。', { name: deviceName(r), time: dateTime(r.s.startedAt) }),
    confirmText: t('删除'), danger: true, focus: 'cancel',
  })
  if (!ok) return
  try {
    if (r.kind === 'drone') await historyApi.remove(r.s.id)
    else await dogRecordsApi.remove(r.s.id)
    toast.push('ok', t('已删除'))
    await refresh()
  } catch (e) {
    toast.push('danger', e instanceof ApiError ? e.message : t('删除失败'))
  }
}

const idsOf = (kind: Row['kind'], list: Row[]) => list.filter((r) => r.kind === kind).map((r) => r.s.id)

async function removeSelected(): Promise<void> {
  const list = selectedRows.value
  const ok = await confirm.ask({ title: t('批量删除'), message: t('确认删除选中的 {n} 条记录？受保护的和正在记录的会跳过，不可撤销。', { n: list.length }), confirmText: t('删除'), danger: true, focus: 'cancel' })
  if (!ok) return
  try {
    const drone = idsOf('drone', list)
    const dog = idsOf('dog', list)
    const [a, b] = await Promise.all([
      drone.length ? historyApi.removeMany(drone) : Promise.resolve({ deleted: 0, skipped: [] as string[] }),
      dog.length ? dogRecordsApi.removeMany(dog) : Promise.resolve({ deleted: 0, skipped: [] as string[] }),
    ])
    const n = a.deleted + b.deleted
    const skipped = a.skipped.length + b.skipped.length
    toast.push('ok', skipped ? t('已删除 {n} 条，跳过 {skipped} 条（受保护或正在记录）', { n, skipped }) : t('已删除 {n} 条', { n }))
    selected.value = new Set()
    await refresh()
  } catch (e) {
    toast.push('danger', e instanceof ApiError ? e.message : t('删除失败'))
  }
}

/** Deleting only the video keeps the track, commands and events (user, 2026-11-01). */
const hasVideo = (r: Row) => r.s.videoStatus === 'READY' && !!r.s.videoBytes
const selectedVideos = computed(() => selectedRows.value.filter(hasVideo))

async function removeVideoOne(r: Row): Promise<void> {
  const ok = await confirm.ask({
    title: t('删除录像'),
    message: r.kind === 'drone'
      ? t('只删除 {time} 这次飞行的录像（{size}），航迹、指令和事件保留，回放里不再有视频。不可撤销。', { time: dateTime(r.s.startedAt), size: bytes(r.s.videoBytes) })
      : t('只删除 {name} {time} 这段记录的录像（{size}），轨迹、指令和事件保留，回放里不再有视频。不可撤销。', { name: deviceName(r), time: dateTime(r.s.startedAt), size: bytes(r.s.videoBytes) }),
    confirmText: t('删除录像'), danger: true, focus: 'cancel',
  })
  if (!ok) return
  try {
    const res = r.kind === 'drone' ? await historyApi.removeVideo(r.s.id) : await dogRecordsApi.removeVideo(r.s.id)
    toast.push('ok', t('已删除录像，释放 {size}', { size: bytes(res.freedBytes) }))
    await refresh()
  } catch (e) {
    toast.push('danger', e instanceof ApiError ? e.message : t('删除失败'))
  }
}

async function removeSelectedVideos(): Promise<void> {
  const items = selectedVideos.value
  const total = items.reduce((n, r) => n + (r.s.videoBytes ?? 0), 0)
  const ok = await confirm.ask({ title: t('只删录像'), message: t('删除选中的 {n} 条记录的录像（共 {size}），记录保留。受保护的会跳过，不可撤销。', { n: items.length, size: bytes(total) }), confirmText: t('删除录像'), danger: true, focus: 'cancel' })
  if (!ok) return
  try {
    const drone = idsOf('drone', items)
    const dog = idsOf('dog', items)
    const none = { deleted: 0, skipped: [] as string[], freedBytes: 0 }
    const [a, b] = await Promise.all([drone.length ? historyApi.removeVideos(drone) : Promise.resolve(none), dog.length ? dogRecordsApi.removeVideos(dog) : Promise.resolve(none)])
    const n = a.deleted + b.deleted
    const size = bytes(a.freedBytes + b.freedBytes)
    const skipped = a.skipped.length + b.skipped.length
    toast.push('ok', skipped
      ? t('已删除 {n} 段录像，释放 {size}，跳过 {skipped} 条（受保护或还在归档）', { n, size, skipped })
      : t('已删除 {n} 段录像，释放 {size}', { n, size }))
    selected.value = new Set()
    await refresh()
  } catch (e) {
    toast.push('danger', e instanceof ApiError ? e.message : t('删除失败'))
  }
}

function clearFilters(): void {
  fromDate.value = ''
  toDate.value = ''
  outcome.value = ''
  routeId.value = ''
  device.value = ''
  hasAlerts.value = false
}
</script>

<template>
  <div class="history">
    <section class="panel list">
      <div class="panel-head">
        <span>{{ tc('tab', '记录') }}</span>
        <div class="row filters">
          <label class="field-inline">{{ t('从') }} <input v-model="fromDate" type="date" class="input" data-test="filter-from" /></label>
          <label class="field-inline">{{ t('到') }} <input v-model="toDate" type="date" class="input" /></label>
          <select v-model="outcome" class="input" data-test="filter-outcome" :aria-label="t('结果')">
            <option value="">{{ t('全部结果') }}</option>
            <optgroup :label="t('飞机')">
              <option v-for="(label, key) in OUTCOME_LABELS" :key="key" :value="`drone:${key}`">{{ label }}</option>
            </optgroup>
            <optgroup :label="t('狗')">
              <option v-for="(label, key) in DOG_OUTCOME_LABELS" :key="key" :value="`dog:${key}`">{{ label }}</option>
            </optgroup>
          </select>
          <select v-if="fleet.drones.length > 1 || dogs.length" v-model="device" class="input" :aria-label="t('设备')" data-test="filter-device">
            <option value="">{{ t('全部设备') }}</option>
            <optgroup v-if="fleet.drones.length" :label="t('飞机')">
              <option v-for="d in fleet.drones" :key="d.gatewaySn" :value="`drone:${d.gatewaySn}`">{{ d.label }}</option>
            </optgroup>
            <optgroup v-if="dogs.length" :label="t('狗')">
              <option v-for="d in dogs" :key="d.id" :value="`dog:${d.id}`">{{ d.name }}</option>
            </optgroup>
          </select>
          <select v-model="routeId" class="input" :aria-label="t('航线')">
            <option value="">{{ t('全部航线') }}</option>
            <option v-for="r in routes.list" :key="r.id" :value="r.id">{{ r.name }}</option>
          </select>
          <label class="check"><input v-model="hasAlerts" type="checkbox" />{{ t('有告警') }}</label>
          <label class="check"><input v-model="includeSimulated" type="checkbox" data-test="filter-simulated" />{{ t('显示模拟记录') }}</label>
          <button v-if="selected.size >= 2" class="btn btn-sm" data-test="play-selected" @click="playSelected">
            <AppIcon name="play" :size="15" />{{ t('一起回放（{n}）', { n: selected.size }) }}
          </button>
          <button v-if="selectedVideos.length" class="btn btn-sm" data-test="delete-selected-videos" @click="removeSelectedVideos">
            <AppIcon name="camera" :size="15" />{{ t('只删录像（{n}）', { n: selectedVideos.length }) }}
          </button>
          <button v-if="selected.size" class="btn btn-danger btn-sm" data-test="delete-selected" @click="removeSelected">
            <AppIcon name="trash" :size="15" />{{ t('删除选中（{n}）', { n: selected.size }) }}
          </button>
        </div>
      </div>
      <div class="table-wrap scroll">
        <div v-if="loading && !loaded" class="loading dim"><AppIcon name="spinner" />{{ t('正在加载记录…') }}</div>
        <div v-else-if="error" class="error">
          <AppIcon name="alert" />{{ t('加载失败：{error}', { error }) }}
          <button class="btn btn-sm" @click="refresh">{{ t('重试') }}</button>
        </div>
        <EmptyState v-else-if="rows.length === 0 && filtersActive" icon="info" :title="t('没有符合筛选条件的记录')">
          <button class="btn" @click="clearFilters">{{ t('清除筛选') }}</button>
        </EmptyState>
        <EmptyState v-else-if="rows.length === 0" icon="clock" :title="t('还没有记录')"
          :hint="includeSimulated ? t('飞机从起飞开始自动记录；狗在平台给它发指令、有人控制或它在走时自动记录。') : t('飞机从起飞开始自动记录；狗在平台给它发指令、有人控制或它在走时自动记录。模拟的默认隐藏，可勾选“显示模拟记录”。')" />
        <table v-else class="table" data-test="history-table">
          <thead>
            <tr>
              <th class="cb"><input type="checkbox" :checked="allSelected" :aria-label="t('全选')" @change="toggleAll" /></th>
              <th>{{ dogRows.length ? t('轨迹') : t('航迹') }}</th><th v-if="showDevice">{{ t('设备') }}</th><th>{{ t('开始时间') }}</th><th>{{ t('时长') }}</th><th>{{ t('航线') }}</th><th>{{ t('结果') }}</th><th>{{ t('距离') }}</th><th>{{ t('最高') }}</th><th>{{ t('告警') }}</th><th>{{ tc('history', '标记') }}</th><th />
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in rows" :key="r.key" :class="{ selected: selected.has(r.key) }" :data-test="`row-${r.kind}`" @click="open(r)">
              <td class="cb" @click.stop><input type="checkbox" :checked="selected.has(r.key)" :aria-label="t('选择 {time}', { time: dateTime(r.s.startedAt) })" @change="toggle(r.key)" /></td>
              <td><TrackThumb :points="r.s.trackPreview" :dog="r.kind === 'dog'" /></td>
              <td v-if="showDevice">
                <span class="who" :class="r.kind" :style="{ '--c': deviceColor(r) }"><i class="mark" />{{ deviceName(r) }}</span>
                <button v-if="overlaps(r).length" class="btn btn-sm together" data-test="together"
                  :title="t('与 {name} 同时段的记录一起回放', { name: overlapNames(r) })" @click.stop="openTogether(r)">
                  <AppIcon name="play" :size="12" />{{ t('一起') }}
                </button>
              </td>
              <td class="num">{{ dateTime(r.at) }}</td>
              <td class="num">{{ r.s.status === 'OPEN' ? t('记录中') : duration(seconds(r)) }}</td>
              <td class="name">{{ r.kind === 'dog' ? '—' : r.s.routeName ?? t('无航线') }}</td>
              <td>
                <span v-if="r.s.status === 'OPEN'" class="badge danger">{{ t('● 记录中') }}</span>
                <span v-else-if="outcomeText(r)" class="badge" :class="OUTCOME_CLASS[r.s.outcome!]">{{ outcomeText(r) }}</span>
              </td>
              <td class="num">{{ meters(r.s.distanceMeters) }}</td>
              <td class="num">{{ r.s.maxRelativeHeight != null ? Math.round(r.s.maxRelativeHeight) + ' m' : '—' }}</td>
              <td class="num">
                <span v-if="r.s.alertCount" class="alerts" :class="r.s.maxAlertLevel === 'CRITICAL' ? 'danger' : 'warn'">{{ r.s.alertCount }}</span>
                <span v-else class="dim">0</span>
              </td>
              <td>
                <div class="flags">
                <span v-if="r.s.simulated" class="tag">{{ t('模拟') }}</span>
                <span v-if="r.s.resumed" class="tag" :title="t('记录开始时飞行器已在空中（后端重启或链路恢复）')">{{ t('续录') }}</span>
                <span v-if="r.s.protectedFlag" class="tag" :title="t('受保护：批量删除时跳过')"><AppIcon name="lock" :size="12" />{{ tc('state', '保护') }}</span>
                <span v-if="r.s.videoStatus === 'READY'" class="tag"><AppIcon name="camera" :size="12" />{{ t('视频') }}{{ r.s.videoBytes ? ' ' + bytes(r.s.videoBytes) : '' }}</span>
                <span v-else-if="r.s.videoStatus && ['PENDING', 'ARCHIVING', 'FAILED', 'DELETED'].includes(r.s.videoStatus)" class="tag dim">{{ VIDEO_LABELS[r.s.videoStatus] }}</span>
                </div>
              </td>
              <td class="row-actions" @click.stop>
                <button class="btn btn-ghost btn-icon" :title="r.s.protectedFlag ? t('取消保护') : t('保护')" @click="protect(r)"><AppIcon name="lock" :size="16" /></button>
                <button v-if="hasVideo(r)" class="btn btn-ghost btn-sm del-video" :title="t('只删除录像（{size}），保留记录', { size: bytes(r.s.videoBytes) })"
                  :disabled="r.s.protectedFlag" data-test="delete-video" @click="removeVideoOne(r)">{{ t('删录像') }}</button>
                <button class="btn btn-ghost btn-icon" :title="t('删除')" :disabled="r.s.status === 'OPEN'" @click="removeOne(r)"><AppIcon name="trash" :size="16" /></button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>

<style scoped>
.who {
  font-weight: 700;
  color: var(--c);
  display: inline-flex;
  align-items: center;
  gap: 5px;
}
/* a drone is a dot, a dog a rounded square, as on the map */
.who .mark {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--c);
}
.who.dog .mark {
  border-radius: 2px;
}
.del-video {
  padding: 0 6px;
  min-height: 0;
  height: 26px;
  font-size: var(--fs-xs);
  white-space: nowrap;
}
.together {
  margin-left: 6px;
  padding: 0 6px;
  min-height: 0;
  height: 22px;
  font-size: var(--fs-xs);
}
.history {
  height: 100%;
  padding: var(--sp-4);
}
.list {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
.filters {
  flex-wrap: wrap;
  gap: var(--sp-2);
  justify-content: flex-end;
}
.filters .input {
  width: auto;
}
.field-inline,
.check {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: var(--fs-sm);
  color: var(--text-dim);
  white-space: nowrap;
}
.table-wrap {
  flex: 1;
  min-height: 0;
}
.table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--fs-sm);
}
.table th {
  position: sticky;
  top: 0;
  z-index: 1;
  background: var(--panel);
  text-align: left;
  font-weight: 600;
  font-size: var(--fs-xs);
  color: var(--text-dim);
  padding: var(--sp-2) var(--sp-3);
  border-bottom: 1px solid var(--border);
}
.table td {
  padding: var(--sp-2) var(--sp-3);
  border-bottom: 1px solid var(--border);
  vertical-align: middle;
}
.table tbody tr {
  cursor: pointer;
}
.table tbody tr:hover {
  background: var(--panel-2);
}
.table tbody tr.selected {
  background: color-mix(in srgb, var(--accent) 14%, transparent);
}
.cb {
  width: 28px;
}
.name {
  font-weight: 600;
}
.badge {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 10px;
  border: 1px solid var(--border);
  font-size: var(--fs-xs);
  font-weight: 600;
  white-space: nowrap;
}
.badge.ok { color: var(--ok); border-color: var(--ok); }
.badge.warn { color: var(--warn); border-color: var(--warn); }
.badge.danger { color: var(--danger); border-color: var(--danger); }
.alerts {
  font-weight: 700;
}
.alerts.warn { color: var(--warn); }
.alerts.danger { color: var(--danger); }
.flags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
}
.flags .tag {
  display: inline-flex;
  align-items: center;
  gap: 3px;
}
.row-actions {
  white-space: nowrap;
  text-align: right;
}
.loading,
.error {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  padding: var(--sp-5);
}
.error {
  color: var(--danger);
}
</style>
