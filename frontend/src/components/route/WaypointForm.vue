<script setup lang="ts">
/**
 * The selected waypoint's less frequent settings (R-06, Q-15): gimbal pitch, coordinates, actions, waiting for the
 * operator; moving it up or down. Height, speed and hover are edited in the list row. When the waypoint is one of
 * several checked ones, every setting here except the coordinates changes all of them.
 */
import { computed } from 'vue'
import AppIcon from '@/components/common/AppIcon.vue'
import type { ActionType, Waypoint } from '@/api/routes'
import { useEditorStore } from '@/stores/editor'
import { useToastStore } from '@/stores/toast'
import { distance } from '@/utils/geo'
import { meters } from '@/utils/format'
import { t } from '@/i18n'

const props = defineProps<{ index: number }>()
const ed = useEditorStore()
const toast = useToastStore()
const w = computed<Waypoint | undefined>(() => ed.draft?.waypoints[props.index])
const count = computed(() => ed.targetsOf(props.index).length)
const leg = computed(() => {
  const prev = props.index > 0 ? ed.draft?.waypoints[props.index - 1] : undefined
  return prev && w.value ? distance(prev, w.value) : null
})

function numOrNull(v: string): number | null {
  return v.trim() === '' ? null : Number(v)
}

function told(n: number): void {
  if (n > 1) toast.push('ok', t('已同时修改选中的 {n} 个航点', { n }))
}

function hasAction(type: ActionType): boolean {
  return !!w.value?.actions.some((a) => a.type === type)
}

/** Adds or removes one action on this waypoint (or every checked one), keeping their other actions. */
function setAction(type: ActionType, on: boolean, value: number | null = null): void {
  const ks = ed.targetsOf(props.index)
  for (const k of ks) {
    const wp = ed.draft?.waypoints[k]
    if (!wp) continue
    const actions = wp.actions.filter((a) => a.type !== type)
    if (on) actions.push({ type, value })
    ed.updateWaypoint(k, { actions })
  }
  told(ks.length)
}

const zoom = computed(() => w.value?.actions.find((a) => a.type === 'ZOOM')?.value ?? null)
function setZoom(v: string): void {
  const z = numOrNull(v)
  setAction('ZOOM', z !== null, z)
}

function setGimbal(v: string): void {
  told(ed.setField(props.index, { gimbalPitch: numOrNull(v) }))
}

function setWait(on: boolean): void {
  told(ed.setField(props.index, { waitForConfirm: on }))
}

function setCoord(k: 'lat' | 'lon', v: string): void {
  const x = Number(v)
  if (v.trim() !== '' && Number.isFinite(x)) ed.updateWaypoint(props.index, { [k]: x })
}
</script>

<template>
  <div v-if="w" class="wp-form" data-test="waypoint-form">
    <div class="title">
      <h4 class="section-title">{{ t('航点 {n}', { n: index + 1 }) }}</h4>
      <span v-if="leg !== null" class="dim num">{{ t('距上一点 {d}', { d: meters(leg) }) }}</span>
      <span class="grow" />
      <button class="btn btn-ghost btn-sm mini" :title="t('上移')" :disabled="index === 0" data-test="wp-up" @click="ed.reorder(index, -1)"><AppIcon name="up" :size="15" /></button>
      <button class="btn btn-ghost btn-sm mini" :title="t('下移')" :disabled="index === (ed.draft?.waypoints.length ?? 0) - 1" data-test="wp-down" @click="ed.reorder(index, 1)"><AppIcon name="down" :size="15" /></button>
      <button class="btn btn-ghost btn-sm mini" :title="t('删除')" @click="ed.removePoint(index)"><AppIcon name="trash" :size="15" /></button>
    </div>
    <p v-if="count > 1" class="multi">{{ t('这个航点在选中的 {n} 个里：下面除坐标外的改动会同时改这 {n} 个。', { n: count }) }}</p>
    <label class="wait" :class="{ on: w.waitForConfirm }">
      <input type="checkbox" :checked="!!w.waitForConfirm" data-test="wp-wait" @change="setWait(($event.target as HTMLInputElement).checked)" />
      <span>
        <b>{{ t('到达后悬停，等我确认再飞下一点') }}</b>
        <small>{{ t('实时监控页会提示，点「确认，继续航线」后再飞。只在平台执行时有效；同步到遥控器、在 Pilot 2 里执行时不会停。') }}</small>
      </span>
    </label>
    <div class="grid">
      <label class="field">
        <span>{{ t('云台俯仰 (°，空=不变)') }}</span>
        <input class="input num" type="number" step="1" min="-90" max="35" :value="w.gimbalPitch ?? ''" :placeholder="t('不变')"
          @change="setGimbal(($event.target as HTMLInputElement).value)" />
      </label>
      <label class="field">
        <span>{{ t('变焦 (×，空=不变)') }}</span>
        <input class="input num" type="number" min="2" max="200" step="1" :value="zoom ?? ''" :placeholder="t('不变')"
          @change="setZoom(($event.target as HTMLInputElement).value)" />
      </label>
      <label class="field">
        <span>{{ t('纬度 (WGS84)') }}</span>
        <input class="input num" type="number" step="0.000001" :value="w.lat.toFixed(7)"
          @change="setCoord('lat', ($event.target as HTMLInputElement).value)" />
      </label>
      <label class="field">
        <span>{{ t('经度 (WGS84)') }}</span>
        <input class="input num" type="number" step="0.000001" :value="w.lon.toFixed(7)"
          @change="setCoord('lon', ($event.target as HTMLInputElement).value)" />
      </label>
    </div>
    <div class="actions">
      <span class="label">{{ t('到点动作') }}</span>
      <label><input type="checkbox" :checked="hasAction('TAKE_PHOTO')" @change="setAction('TAKE_PHOTO', ($event.target as HTMLInputElement).checked)" /> {{ t('拍照') }}</label>
      <label><input type="checkbox" :checked="hasAction('START_RECORD')" @change="setAction('START_RECORD', ($event.target as HTMLInputElement).checked)" /> {{ t('开始录像') }}</label>
      <label><input type="checkbox" :checked="hasAction('STOP_RECORD')" @change="setAction('STOP_RECORD', ($event.target as HTMLInputElement).checked)" /> {{ t('停止录像') }}</label>
    </div>
  </div>
</template>

<style scoped>
.wp-form {
  padding: var(--sp-2) var(--sp-4) var(--sp-3);
  border-top: 1px solid var(--border);
  background: var(--panel-2);
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}
.title {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
}
.title h4 {
  margin: 0;
}
.title .dim {
  font-size: var(--fs-xs);
}
.mini {
  width: 28px;
  min-width: 28px;
  padding: 0;
  justify-content: center;
}
.multi {
  margin: 0;
  padding: 4px 8px;
  border-radius: var(--r-ctl);
  background: color-mix(in srgb, var(--accent) 12%, transparent);
  font-size: var(--fs-xs);
}
.wait {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: var(--r-ctl);
  cursor: pointer;
  font-size: var(--fs-sm);
}
.wait.on {
  border-color: var(--warn);
  background: color-mix(in srgb, var(--warn) 10%, transparent);
}
.wait input {
  margin-top: 3px;
  accent-color: var(--warn);
}
.wait span {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.wait small {
  color: var(--text-dim);
  font-size: var(--fs-xs);
}
.grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: var(--sp-2) var(--sp-3);
}
.grid .input {
  width: 100%;
  min-width: 0;
}
.actions {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  align-items: center;
  gap: var(--sp-2) var(--sp-3);
  font-size: var(--fs-sm);
}
.actions .label {
  grid-column: 1 / -1;
  color: var(--text-dim);
  font-size: var(--fs-xs);
}
.actions input[type='checkbox'] {
  accent-color: var(--accent);
}
</style>
