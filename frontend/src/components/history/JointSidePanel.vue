<script setup lang="ts">
/**
 * Joint replay side panel (D-33, D-40; ui-design.md 2.6.1, 2.7.1): each device's values at the cursor (a drone's
 * flight values, a dog's speed, battery, heading, GNSS and state), the separation between two drones, and every
 * device's commands and alerts in one list that follows the cursor (click a row to jump).
 */
import { computed, nextTick, ref, watch } from 'vue'
import type { FilledSample } from '@/utils/replay'
import { elapsed } from '@/utils/replay'
import { dogState, type JointItem, type Separation, type Track } from '@/utils/jointReplay'
import { meters, modeLabel, num, time } from '@/utils/format'
import { t } from '@/i18n'

const props = defineProps<{
  tracks: Track[]
  /** Each track's state at the cursor, null outside its recording. */
  states: (FilledSample | null)[]
  separation: Separation | null
  /** A proximity alarm was active at the cursor. */
  alarm: boolean
  items: JointItem[]
  cursor: number
  start: number
}>()
const emit = defineEmits<{ (e: 'seek', t: number): void }>()
/** The separation box is about two drones (S-05). */
const drones = computed(() => props.tracks.filter((tr) => tr.kind === 'drone').length)

/** GNSS fix and satellites of a dog sample, in words. */
function fixText(f: string | null | undefined, sats: number | null | undefined): string {
  if (!f) return '—'
  const name = f === 'none' ? t('未定位') : f === 'rtk_fixed' ? t('RTK 固定') : f === 'rtk_float' ? t('RTK 浮动') : t('已定位')
  return sats != null ? t('{fix} · {n} 颗', { fix: name, n: sats }) : name
}
function modeText(m: string | null | undefined): string {
  return m === 'new' ? t('新系统') : m === 'old' ? t('老系统') : m ? m : '—'
}

const listEl = ref<HTMLElement | null>(null)
const active = computed(() => {
  let i = -1
  props.items.forEach((r, k) => {
    if (r.ts <= props.cursor) i = k
  })
  return i
})
watch(active, async () => {
  await nextTick()
  listEl.value?.querySelector('.active')?.scrollIntoView({ block: 'nearest' })
})

function absent(i: number): string {
  const tr = props.tracks[i]!
  if (!tr.filled.some((s) => s.lat !== null)) return t('没有位置数据')
  return props.cursor < (tr.filled[0]?.ts ?? 0) ? t('还没开始记录') : t('记录已结束')
}
</script>

<template>
  <aside class="side panel" data-test="joint-side">
    <!-- the values stay in view; only the list scrolls (it follows the cursor) -->
    <div class="top">
      <div class="section-title">{{ t('此刻 · {time}（T+{elapsed}）', { time: time(cursor), elapsed: elapsed(cursor - start) }) }}</div>
      <div class="cards">
        <div v-for="(tr, i) in tracks" :key="tr.id" class="card" :style="{ '--c': tr.color }" :data-test="`joint-card-${i}`">
          <div class="name"><span class="dot" />{{ tr.label }}</div>
          <template v-if="states[i] && tr.kind === 'dog'">
            <dl class="num">
              <dt>{{ t('速度') }}</dt><dd>{{ num(states[i]!.horizontalSpeed, 2, 'm/s') }}</dd>
              <dt>{{ t('电量') }}</dt><dd>{{ states[i]!.battery != null ? states[i]!.battery + '%' : '—' }}</dd>
              <dt>{{ t('朝向') }}</dt><dd>{{ states[i]!.attitudeHead != null ? Math.round(states[i]!.attitudeHead!) + '°' : '—' }}</dd>
              <dt>{{ t('定位') }}</dt><dd>{{ fixText(dogState(states[i])!.fix, dogState(states[i])!.sats) }}</dd>
              <dt>{{ t('状态') }}</dt><dd>{{ dogState(states[i])!.basicStateName ?? '—' }}</dd>
              <dt>{{ t('在控') }}</dt><dd>{{ modeText(dogState(states[i])!.mode) }}{{ dogState(states[i])!.controlHeld ? ' · ' + (dogState(states[i])!.controlLabel ?? t('有人控制')) : '' }}</dd>
            </dl>
          </template>
          <template v-else-if="states[i]">
            <dl class="num">
              <dt>{{ t('模式') }}</dt><dd>{{ modeLabel(states[i]!.modeCode) }}</dd>
              <dt>{{ t('高度') }}</dt><dd>{{ num(states[i]!.height, 1, 'm') }}</dd>
              <dt>{{ t('水平') }}</dt><dd>{{ num(states[i]!.horizontalSpeed, 1, 'm/s') }}</dd>
              <dt>{{ t('垂直') }}</dt><dd>{{ num(states[i]!.verticalSpeed, 1, 'm/s') }}</dd>
              <dt>{{ t('电量') }}</dt><dd>{{ states[i]!.battery != null ? states[i]!.battery + '%' : '—' }}</dd>
              <dt>{{ t('离 Home') }}</dt><dd>{{ meters(states[i]!.homeDistance) }}</dd>
            </dl>
          </template>
          <div v-else class="absent dim">{{ absent(i) }}</div>
        </div>
      </div>
      <div v-if="drones >= 2" class="sep" :class="{ alarm }" data-test="joint-separation">
        <span class="lbl">{{ t('两机间距') }}</span>
        <span v-if="separation" class="num">
          {{ t('水平') }} <b>{{ Math.round(separation.horizontalM) }} m</b> ·
          {{ t('高度差') }} <b>{{ separation.verticalM === null ? t('未知') : Math.round(separation.verticalM) + ' m' }}</b>
        </span>
        <span v-else class="dim">{{ t('此刻只有一架有位置') }}</span>
        <span v-if="alarm" class="flag">{{ t('靠近告警中') }}</span>
      </div>
      <p v-if="drones >= 2" class="hint dim">{{ t('高度差按各自起飞点的椭球高换算到同一基准；平台当时判断靠近用的是 DRC 高度，数值以告警里记下的为准。') }}</p>
      <div class="section-title">{{ t('指令与告警') }}</div>
    </div>
    <div ref="listEl" class="list scroll" data-test="joint-items">
        <div v-if="!items.length" class="dim pad">{{ t('这些记录没有指令和告警') }}</div>
        <button v-for="(r, i) in items" :key="`${r.ts}-${r.track}-${i}`" class="item" :class="{ active: i === active, future: r.ts > cursor }"
          @click="emit('seek', r.ts)">
          <span class="t num">{{ time(r.ts) }}</span>
          <span class="who" :style="{ '--c': r.track >= 0 ? tracks[r.track]!.color : 'var(--danger)' }">{{ r.track >= 0 ? tracks[r.track]!.label : t('两机') }}</span>
          <span class="what" :class="r.level === 'CRITICAL' ? 'bad' : r.kind === 'alert' && !(tracks[r.track]?.kind === 'dog' && r.level === 'INFO') ? 'warn' : ''">{{ r.text }}</span>
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
.top {
  flex: none;
  padding: var(--sp-3) var(--sp-3) 0;
}
.cards {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--sp-2);
  margin-bottom: var(--sp-3);
}
.card {
  border: 1px solid var(--border);
  border-top: 3px solid var(--c);
  border-radius: var(--r-ctl);
  padding: 6px var(--sp-2);
  min-width: 0;
}
.name {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 700;
  margin-bottom: 4px;
}
.dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: var(--c);
}
dl {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 2px var(--sp-2);
  margin: 0;
  font-size: var(--fs-xs);
}
dt {
  color: var(--text-dim);
}
dd {
  margin: 0;
  text-align: right;
  white-space: nowrap;
}
.absent {
  font-size: var(--fs-sm);
  padding: var(--sp-2) 0;
}
.sep {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px var(--sp-2);
  padding: 6px var(--sp-2);
  border: 1px solid var(--border);
  border-radius: var(--r-ctl);
  font-size: var(--fs-sm);
}
.sep.alarm {
  border-color: var(--danger);
  background: color-mix(in srgb, var(--danger) 14%, transparent);
}
.lbl {
  color: var(--text-dim);
}
.flag {
  margin-left: auto;
  color: var(--danger);
  font-weight: 700;
  font-size: var(--fs-xs);
}
.hint {
  font-size: var(--fs-xs);
  margin: 4px 0 var(--sp-3);
}
.list {
  flex: 1;
  min-height: 0;
  border-top: 1px solid var(--border);
}
.pad {
  padding: var(--sp-3);
}
.item {
  display: grid;
  grid-template-columns: auto auto 1fr;
  align-items: baseline;
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
.who {
  padding: 0 5px;
  border-radius: 4px;
  background: var(--c);
  color: #0d1117;
  font-weight: 700;
  font-size: var(--fs-xs);
}
.warn { color: var(--warn); }
.bad { color: var(--danger); }
</style>
