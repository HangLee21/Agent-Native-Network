<script setup lang="ts">
/** Replay side panel: values at the cursor, and command / event lists that follow it (click a row to jump). */
import { computed, nextTick, ref, watch } from 'vue'
import type { FlightCommand, FlightEvent, SessionDetail } from '@/api/history'
import { OUTCOME_LABELS, VIDEO_LABELS } from '@/api/history'
import type { FilledSample } from '@/utils/replay'
import { DRC_HEIGHT_REFERENCE, elapsed } from '@/utils/replay'
import { WIND_DIRECTIONS, meters, modeLabel, num, time } from '@/utils/format'
import { t } from '@/i18n'

const props = defineProps<{
  detail: SessionDetail
  state: FilledSample | null
  cursor: number
  start: number
  commands: FlightCommand[]
  events: FlightEvent[]
}>()
const emit = defineEmits<{ (e: 'seek', t: number): void }>()

const tab = ref<'info' | 'commands' | 'events'>('info')
const listEl = ref<HTMLElement | null>(null)

const shownEvents = computed(() => props.events.filter((e) => e.eventType !== 'RC_POSITION'))

const STATUS_LABELS: Record<FlightCommand['status'], string> = {
  PENDING: t('等待'), REJECTED: t('已拒绝'), SENT: t('已发送'), ACKED: t('已确认'), FAILED: t('失败'), TIMEOUT: t('超时'),
}

function lastIndex<T>(rows: T[], ts: (r: T) => number): number {
  let i = -1
  rows.forEach((r, k) => {
    if (ts(r) <= props.cursor) i = k
  })
  return i
}
const activeCommand = computed(() => lastIndex(props.commands, (c) => c.createdAt))
const activeEvent = computed(() => lastIndex(shownEvents.value, (e) => e.ts))

watch([activeCommand, activeEvent, tab], async () => {
  await nextTick()
  listEl.value?.querySelector('.active')?.scrollIntoView({ block: 'nearest' })
})

const s = computed(() => props.state)
const heightHint = DRC_HEIGHT_REFERENCE === 'UNKNOWN' ? t('相对起飞点高度，取自普通 OSD（约 2 秒一次）') : t('相对起飞点高度（每秒 2 次）')

const flightSeconds = computed(() => {
  const d = props.detail
  const to = d.landedAt ?? d.endedAt
  return to ? (to - (d.takeoffAt ?? d.startedAt)) / 1000 : null
})
</script>

<template>
  <aside class="side panel">
    <div class="tabs" role="tablist">
      <button role="tab" :class="{ on: tab === 'info' }" @click="tab = 'info'">{{ t('信息') }}</button>
      <button role="tab" :class="{ on: tab === 'commands' }" data-test="tab-commands" @click="tab = 'commands'">{{ t('指令 {n}', { n: commands.length }) }}</button>
      <button role="tab" :class="{ on: tab === 'events' }" data-test="tab-events" @click="tab = 'events'">{{ t('事件 {n}', { n: shownEvents.length }) }}</button>
    </div>
    <div v-if="tab === 'info'" class="body scroll">
      <div class="section-title">{{ t('光标时刻 · {time}（T+{elapsed}）', { time: time(cursor), elapsed: elapsed(cursor - start) }) }}</div>
      <dl class="num" data-test="replay-values">
        <dt>{{ t('飞行模式') }}</dt><dd>{{ modeLabel(s?.modeCode) }}</dd>
        <dt :title="heightHint">{{ t('相对高度') }}</dt><dd>{{ num(s?.height, 1, 'm') }}</dd>
        <dt>{{ t('水平速度') }}</dt><dd>{{ num(s?.horizontalSpeed, 1, 'm/s') }}</dd>
        <dt>{{ t('垂直速度') }}</dt><dd>{{ num(s?.verticalSpeed, 1, 'm/s') }}</dd>
        <dt>{{ t('航向') }}</dt><dd>{{ num(s?.attitudeHead, 0, '°') }}</dd>
        <dt>{{ t('飞机俯仰') }}</dt><dd>{{ num(s?.attitudePitch, 1, '°') }}</dd>
        <dt>{{ t('云台俯仰') }}</dt><dd>{{ num(s?.gimbalPitch, 1, '°') }}</dd>
        <dt>{{ t('变焦') }}</dt><dd>{{ s?.zoomFactor != null ? s.zoomFactor.toFixed(1) + '×' : '—' }}</dd>
        <dt>{{ t('电量') }}</dt><dd>{{ s?.battery != null ? s.battery + '%' : '—' }}<span v-if="s?.returnHomePower != null" class="dim">{{ t('（返航需 {n}%）', { n: s.returnHomePower }) }}</span></dd>
        <dt>GPS / RTK</dt><dd>{{ s?.gpsNumber ?? '—' }} / {{ s?.rtkNumber ?? '—' }}</dd>
        <dt>{{ t('风速') }}</dt><dd>{{ num(s?.windSpeed, 1, 'm/s') }} {{ s?.windDirection ? WIND_DIRECTIONS[s.windDirection] : '' }}</dd>
        <dt>{{ t('离 Home') }}</dt><dd>{{ meters(s?.homeDistance) }}</dd>
        <dt>{{ t('飞行器限高') }}</dt><dd>{{ s?.heightLimit != null ? s.heightLimit + ' m' : '—' }}</dd>
      </dl>
      <div class="section-title">{{ t('本次飞行') }}</div>
      <dl class="num">
        <dt>{{ t('结果') }}</dt><dd>{{ detail.status === 'OPEN' ? t('记录中') : detail.outcome ? OUTCOME_LABELS[detail.outcome] : '—' }}</dd>
        <dt>{{ t('飞行时长') }}</dt><dd>{{ flightSeconds != null ? elapsed(flightSeconds * 1000) : '—' }}</dd>
        <dt>{{ t('距离') }}</dt><dd>{{ meters(detail.distanceMeters) }}</dd>
        <dt>{{ t('最高 / 最远') }}</dt><dd>{{ num(detail.maxRelativeHeight, 0, 'm') }} / {{ meters(detail.maxHomeDistance) }}</dd>
        <dt>{{ t('电量') }}</dt><dd>{{ detail.batteryStart ?? '—' }}% → {{ detail.batteryEnd ?? '—' }}%</dd>
        <dt>{{ t('航线') }}</dt><dd>{{ detail.routeName ?? t('无') }}</dd>
        <dt>{{ t('飞行器') }}</dt><dd>{{ detail.droneSn ?? '—' }}</dd>
        <dt>{{ t('视频') }}</dt><dd>{{ detail.videoStatus ? VIDEO_LABELS[detail.videoStatus] : '—' }}<span v-if="detail.videoMessage" class="dim">{{ t('：{reason}', { reason: detail.videoMessage }) }}</span></dd>
        <dt v-if="detail.delayAvgMs != null">{{ t('图传延时') }}</dt><dd v-if="detail.delayAvgMs != null">{{ detail.delayMinMs }} / {{ detail.delayAvgMs }} / {{ detail.delayMaxMs }} ms</dd>
        <dt v-if="detail.droppedItems">{{ t('丢弃') }}</dt><dd v-if="detail.droppedItems" class="warn">{{ t('{n} 条（写库繁忙时丢弃的遥测）', { n: detail.droppedItems }) }}</dd>
      </dl>
    </div>
    <div v-else-if="tab === 'commands'" ref="listEl" class="body scroll list" data-test="replay-commands">
      <div v-if="!commands.length" class="dim pad">{{ t('这次飞行平台没有下发指令') }}</div>
      <button v-for="(c, i) in commands" :key="c.id" class="item" :class="{ active: i === activeCommand, future: c.createdAt > cursor }" @click="emit('seek', c.createdAt)">
        <span class="t num">{{ time(c.createdAt) }}</span>
        <span class="what">{{ c.label }}</span>
        <span class="st" :class="c.status === 'ACKED' ? 'ok' : ['FAILED', 'TIMEOUT', 'REJECTED'].includes(c.status) ? 'bad' : ''">{{ STATUS_LABELS[c.status] }}</span>
        <span v-if="c.message && c.status !== 'ACKED'" class="msg">{{ c.message }}</span>
      </button>
    </div>
    <div v-else ref="listEl" class="body scroll list" data-test="replay-events">
      <button v-for="(e, i) in shownEvents" :key="e.id" class="item" :class="{ active: i === activeEvent, future: e.ts > cursor }" @click="emit('seek', e.ts)">
        <span class="t num">{{ time(e.ts) }}</span>
        <span class="what" :class="e.eventLevel === 'CRITICAL' ? 'bad' : e.eventLevel === 'WARNING' ? 'warn' : ''">{{ e.title }}</span>
      </button>
    </div>
  </aside>
</template>

<style scoped>
.side {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}
.tabs {
  display: flex;
  border-bottom: 1px solid var(--border);
}
.tabs button {
  flex: 1;
  padding: var(--sp-2);
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  color: var(--text-dim);
  font: inherit;
  font-weight: 600;
  cursor: pointer;
}
.tabs button.on {
  color: var(--text);
  border-bottom-color: var(--accent);
}
.body {
  flex: 1;
  min-height: 0;
  padding: var(--sp-3);
}
dl {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 3px var(--sp-3);
  margin: 0 0 var(--sp-4);
  font-size: var(--fs-sm);
}
dt {
  color: var(--text-dim);
}
dd {
  margin: 0;
}
.warn { color: var(--warn); }
.bad { color: var(--danger); }
.list {
  padding: 0;
}
.pad {
  padding: var(--sp-3);
}
.item {
  display: grid;
  grid-template-columns: auto 1fr auto;
  gap: 2px var(--sp-2);
  width: 100%;
  padding: 6px var(--sp-3);
  background: none;
  border: none;
  border-bottom: 1px solid var(--border);
  color: var(--text);
  font: inherit;
  font-size: var(--fs-sm);
  text-align: left;
  cursor: pointer;
}
.item:hover {
  background: var(--panel-2);
}
.item.active {
  background: color-mix(in srgb, var(--accent) 16%, transparent);
  box-shadow: inset 3px 0 0 var(--accent);
}
.item.future {
  opacity: 0.55;
}
.t {
  color: var(--text-dim);
}
.st {
  font-size: var(--fs-xs);
  font-weight: 600;
}
.st.ok { color: var(--ok); }
.msg {
  grid-column: 2 / 4;
  color: var(--text-dim);
  font-size: var(--fs-xs);
}
</style>
