<script setup lang="ts">
/**
 * 飞行安全 section of the settings page (S-01, S-02, D-03): limits and speed, the safe zone and the
 * height-reference policy. All three cards are one save (SaveBar in SettingsView → model.save()).
 */
import { computed } from 'vue'
import AppIcon from '@/components/common/AppIcon.vue'
import MapCanvas from '@/components/map/MapCanvas.vue'
import FleetLayers from '@/components/map/FleetLayers.vue'
import ZoneEditLayer from '@/components/map/ZoneEditLayer.vue'
import { useTelemetryStore } from '@/stores/telemetry'
import type { HeightPolicy } from '@/api/safety'
import type { SafetyKey, SafetySettings } from './useSafetySettings'
import { t } from '@/i18n'

const props = defineProps<{ model: SafetySettings }>()
const tel = useTelemetryStore()

const isChanged = (k: SafetyKey) => props.model.changed.includes(k)
const limitsChanged = computed(() => (['maxHeight', 'minHeight', 'maxSpeed', 'minTakeoffBattery'] as SafetyKey[]).some(isChanged))
const zoneChanged = computed(() => isChanged('safeZoneEnabled') || isChanged('safeZone'))

type NumKey = 'maxHeight' | 'minHeight' | 'maxSpeed' | 'minTakeoffBattery'
interface NumField {
  key: NumKey
  label: string
  unit: string
  hint: string
  min?: number
  max?: number
  step?: number
  test?: string
}
const fields: NumField[] = [
  { key: 'maxHeight', label: t('平台限高 · S-01'), unit: 'm', hint: t('20–1500，相对起飞点'), min: 20, max: 1500, test: 'max-height' },
  { key: 'minHeight', label: t('最低高度'), unit: 'm', hint: t('相对起飞点，低于此高度的航点被拒绝'), min: 0 },
  { key: 'maxSpeed', label: t('最大速度'), unit: 'm/s', hint: t('大疆上限 15'), min: 1, max: 15, step: 0.5 },
  { key: 'minTakeoffBattery', label: t('起飞最低电量'), unit: '%', hint: t('低于此电量不能起飞'), min: 0, max: 100 },
]

const policies: { value: HeightPolicy; title: string; desc: string }[] = [
  { value: 'ASSUME_INFERRED', title: t('按推断参考系校验（默认）'), desc: t('外场已确认（2026-10-30）；两机同时飞行必须用这一项') },
  { value: 'DUAL_CHECK', title: t('双重校验'), desc: t('按椭球高和相对起飞点两种解释都必须合规；此时返航高度无法错开，第二架不能起飞') },
]

/** Height bar: 0–200 m relative to take-off (display only). */
const SCALE = 200
const pct = (v: number) => Math.max(0, Math.min(100, (v / SCALE) * 100))
const shift = (p: number) => (p < 8 ? 'translateX(0)' : p > 92 ? 'translateX(-100%)' : 'translateX(-50%)')
const bar = computed(() => {
  const min = Number(props.model.form.minHeight) || 0
  const max = Number(props.model.form.maxHeight) || 0
  const lo = pct(Math.min(min, max))
  const hi = pct(Math.max(min, max))
  const limit = tel.drone?.heightLimit
  const ac = typeof limit === 'number' ? limit : null
  const acPct = ac === null ? 0 : pct(ac)
  return { min, max, lo, hi, minPct: pct(min), maxPct: pct(max), over: max > SCALE, ac, acPct, acAbove: ac !== null && Math.abs(acPct - pct(min)) < 20 }
})
</script>

<template>
  <section class="panel s-card" aria-labelledby="settings-limits-title">
    <div class="s-card-head">
      <h2 id="settings-limits-title">{{ t('限高与速度') }}</h2>
      <span v-if="limitsChanged" class="s-badge warn">{{ t('未保存') }}</span>
    </div>
    <div class="s-grid">
      <label v-for="f in fields" :key="f.key" class="field s-field">
        <span class="s-label" :class="{ changed: isChanged(f.key) }">{{ f.label }}</span>
        <span class="s-input-row">
          <input v-model.number="model.form[f.key]" class="input num s-num" :class="{ changed: isChanged(f.key) }" type="number"
            :min="f.min" :max="f.max" :step="f.step" :data-test="f.test" />
          <span class="s-unit">{{ f.unit }}</span>
        </span>
        <span class="s-hint">{{ f.hint }}</span>
      </label>
    </div>
    <div class="hbar-wrap">
      <div class="hbar" role="img" :aria-label="t('高度范围示意：最低 {min} m，平台限高 {max} m', { min: bar.min, max: bar.max })">
        <div class="hbar-track" />
        <div class="hbar-range" :style="{ left: `${bar.lo}%`, width: `${bar.hi - bar.lo}%` }" />
        <span class="hbar-lbl max" :style="{ left: `${bar.maxPct}%`, transform: shift(bar.maxPct) }">{{ t('平台限高 {n} m', { n: bar.max }) }}{{ bar.over ? ' ›' : '' }}</span>
        <span class="hbar-lbl min" :style="{ left: `${bar.minPct}%`, transform: shift(bar.minPct) }">{{ t('最低 {n} m', { n: bar.min }) }}</span>
        <span v-if="bar.ac !== null" class="hbar-lbl ac" :class="{ above: bar.acAbove }" :style="{ left: `${bar.acPct}%`, transform: shift(bar.acPct) }">▲ {{ t('飞行器限高 {n} m', { n: bar.ac }) }}</span>
      </div>
      <span class="s-hint">
        {{ bar.ac === null ? t('示意 0–200 m，相对起飞点。飞行器自身限高（height_limit，20–1500 m）在实时监控页设置，这里只显示（飞行器未上报）。') : t('示意 0–200 m，相对起飞点。飞行器自身限高（height_limit，20–1500 m）在实时监控页设置，这里只显示。') }}
      </span>
    </div>
    <p class="s-note">{{ t('平台安全层会拒绝超出上述范围的航线保存、同步和飞行指令，并给出原因；急停、返航、降落等安全指令不受限高和安全区拦截。') }}</p>
  </section>

  <section id="settings-zone" class="panel s-card" aria-labelledby="settings-zone-title">
    <div class="s-card-head">
      <h2 id="settings-zone-title">{{ t('安全区（S-02）') }}</h2>
      <span v-if="zoneChanged" class="s-badge warn">{{ t('未保存') }}</span>
      <label class="sw">
        <input v-model="model.zoneEnabled" type="checkbox" role="switch" data-test="zone-enabled" />
        <span class="sw-track" aria-hidden="true"><span class="sw-knob" /></span>
        <span class="s-label" :class="{ changed: isChanged('safeZoneEnabled') }">{{ t('启用安全区') }}</span>
      </label>
      <button class="btn btn-sm" :class="{ 'btn-primary': model.drawing }" @click="model.drawing = !model.drawing"><AppIcon name="edit" :size="15" />{{ model.drawing ? t('完成绘制') : t('绘制 / 编辑') }}</button>
      <button class="btn btn-sm" :disabled="model.zone.length === 0" @click="model.zone = []"><AppIcon name="trash" :size="15" />{{ t('清空') }}</button>
    </div>
    <div class="s-map" :class="{ drawing: model.drawing, changed: isChanged('safeZone') }">
      <MapCanvas :center="tel.position" :zoom="16" @map-click="model.onMapClick">
        <ZoneEditLayer :points="model.zone" @move="(i, p) => (model.zone = model.zone.map((q, j) => (j === i ? p : q)))" @remove="(i) => (model.zone = model.zone.filter((_, j) => j !== i))" />
        <FleetLayers markers-only />
      </MapCanvas>
      <span v-if="model.drawing" class="s-map-chip">{{ t('绘制中：单击地图添加顶点，拖动调整，右键删除。当前 {n} 个顶点。', { n: model.zone.length }) }}</span>
    </div>
    <p class="s-note">
      <AppIcon name="info" :size="15" class="inline-icon" /> {{ t('安全区由平台执行：区外的航点、目标点和穿出区域的航段会被拒绝，飞行中越界会告警。遥控器场景没有电子围栏接口，飞机自身不会强制执行该区域，平台失联时不生效。') }}
    </p>
  </section>

  <section id="settings-policy" class="panel s-card" aria-labelledby="settings-policy-title">
    <div class="s-card-head">
      <h2 id="settings-policy-title">{{ t('参考系未明确的高度参数校验策略') }}</h2>
      <span v-if="isChanged('unknownHeightPolicy')" class="s-badge warn">{{ t('未保存') }}</span>
      <span class="s-badge ok">{{ t('外场已确认') }}</span>
    </div>
    <div class="radio-cards" role="radiogroup" aria-labelledby="settings-policy-title">
      <label v-for="p in policies" :key="p.value" class="radio-card">
        <input v-model="model.form.unknownHeightPolicy" type="radio" name="unknown-height-policy" :value="p.value" />
        <span class="rc-text"><b>{{ p.title }}</b>{{ p.desc }}</span>
      </label>
    </div>
  </section>
</template>

<style scoped>
.hbar-wrap {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.hbar {
  position: relative;
  height: 44px;
  margin: 0 2px;
}
.hbar-track,
.hbar-range {
  position: absolute;
  top: 19px;
  height: 6px;
  border-radius: 3px;
}
.hbar-track {
  left: 0;
  right: 0;
  background: var(--panel-3);
}
.hbar-range {
  background: var(--ok);
}
.hbar-lbl {
  position: absolute;
  font-size: 11px;
  line-height: 16px;
  white-space: nowrap;
  color: var(--text-dim);
}
.hbar-lbl.max {
  top: 0;
  color: var(--ok);
  font-weight: 700;
}
.hbar-lbl.min {
  top: 28px;
}
.hbar-lbl.ac {
  top: 28px;
  color: var(--accent);
}
.hbar-lbl.ac.above {
  top: 0;
}
</style>
