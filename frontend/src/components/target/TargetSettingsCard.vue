<script setup lang="ts">
/**
 * 目标选择与 AI section of the settings page (D-21 ~ D-24): laser height reference (U-24) and the laser
 * fly-to switch, distance rules, AI auto mode levels and limits, and the AI work area (inside the safe zone).
 * The form state and the single save of all four cards live in useTargetSettings (SettingsView owns it).
 */
import { computed } from 'vue'
import AppIcon from '@/components/common/AppIcon.vue'
import MapCanvas from '@/components/map/MapCanvas.vue'
import FleetLayers from '@/components/map/FleetLayers.vue'
import ZoneEditLayer from '@/components/map/ZoneEditLayer.vue'
import SafeZoneRefLayer from '@/components/settings/SafeZoneRefLayer.vue'
import { refLabels, type TargetForm, type TargetSettings } from '@/components/settings/useTargetSettings'
import { useTelemetryStore } from '@/stores/telemetry'
import { useSafetyStore } from '@/stores/safety'
import type { LaserReference } from '@/api/targets'
import type { LatLon } from '@/utils/coord'
import { t } from '@/i18n'

const props = defineProps<{ model: TargetSettings }>()
const tel = useTelemetryStore()
const safety = useSafetyStore()

const form = computed(() => props.model.form)
const isChanged = (k: string) => props.model.changed.includes(k)
const anyChanged = (keys: string[]) => keys.some(isChanged)

const refOrder: LaserReference[] = ['UNKNOWN', 'ELLIPSOID', 'MSL']
/** Splits a refLabels text into its bold head and the rest, keeping the text unchanged. */
function splitLabel(s: string): [string, string] {
  // refLabels may be in English (': ' and ' (' instead of the full-width marks)
  const i = s.search(/[：:]/)
  if (i >= 0) return [s.slice(0, i), s.slice(i)]
  const j = s.search(/（| \(/)
  return j >= 0 ? [s.slice(0, j), s.slice(j)] : [s, '']
}

type NumKey = { [K in keyof TargetForm]: TargetForm[K] extends number ? K : never }[keyof TargetForm]
interface NumField {
  key: NumKey
  label: string
  unit: string
  hint?: string
  min?: number
  max?: number
  step?: number
}
const opFields: NumField[] = [
  { key: 'minDistanceM', label: t('最小距离'), unit: 'm', hint: t('小于此距离不移动'), min: 5 },
  { key: 'stopDistanceM', label: t('接近：停止距离'), unit: 'm', min: 5 },
  { key: 'clearanceM', label: t('高于目标的余量'), unit: 'm', min: 2 },
  { key: 'approachSpeed', label: t('接近速度'), unit: 'm/s', hint: '1–15', min: 1, max: 15, step: 0.5 },
  { key: 'aboveHeightM', label: t('飞到上方：高于目标'), unit: 'm', min: 5 },
  { key: 'maxLaserRangeM', label: t('激光最大距离'), unit: 'm', hint: '10–1800', min: 10, max: 1800 },
  { key: 'maxAccuracyM', label: t('允许的估计误差'), unit: 'm', min: 0.5, step: 0.5 },
]
const aiFields: NumField[] = [
  { key: 'aiMinConfidence', label: t('最低置信度'), unit: '', hint: '0.5–1', min: 0.5, max: 1, step: 0.05 },
  { key: 'aiMaxMoveM', label: t('单次最大移动'), unit: 'm', min: 10 },
  { key: 'aiStopDistanceM', label: t('AI 停止距离'), unit: 'm', min: 20 },
  { key: 'aiExtraHeightM', label: t('AI 额外高度'), unit: 'm', min: 0 },
  { key: 'aiCountdownS', label: t('倒计时'), unit: t('秒'), hint: '3–30', min: 3, max: 30 },
  { key: 'aiCooldownS', label: t('冷却'), unit: t('秒'), min: 5 },
  { key: 'aiMaxPerMinute', label: t('每分钟最多'), unit: t('次'), hint: '1–10', min: 1, max: 10 },
  { key: 'aiMaxAccuracyM', label: t('AI 允许误差'), unit: 'm', min: 0.5, step: 0.5 },
]

type LevelKey = 'aiLookLevel' | 'aiApproachLevel' | 'aiAboveLevel' | 'aiOrbitLevel'
const AUTO2 = [{ value: 0, label: t('0 只建议') }, { value: 2, label: t('2 倒计时后自动') }]
const levels: { key: LevelKey; label: string; opts: { value: number; label: string }[] }[] = [
  { key: 'aiLookLevel', label: t('AI 对准'), opts: [{ value: 0, label: t('0 只建议') }, { value: 1, label: t('1 自动对准测距') }] },
  { key: 'aiApproachLevel', label: t('AI 接近'), opts: AUTO2 },
  { key: 'aiAboveLevel', label: t('AI 飞到上方'), opts: AUTO2 },
  { key: 'aiOrbitLevel', label: t('AI 环绕'), opts: AUTO2 },
]

/** The saved platform safe zone, drawn read-only on the work-area map (no request of its own). */
const safeZoneRef = computed<LatLon[] | null>(() => {
  const c = safety.config
  return c && c.safeZoneEnabled && c.safeZone.length >= 3 ? c.safeZone.map(([lat, lon]) => ({ lat, lon })) : null
})
const safeZoneLegend = computed(() => {
  const c = safety.config
  if (!c) return t('安全区：未加载')
  if (!c.safeZoneEnabled) return t('安全区：未启用')
  return safeZoneRef.value ? t('安全区（只读，飞行安全中已保存的区域）') : t('安全区：顶点不足 3 个')
})
</script>

<template>
  <div v-if="!form" class="panel s-card">
    <p class="s-note">{{ t('正在加载目标选择设置…（后端不可达时无法修改）') }}</p>
  </div>
  <div v-else class="target-sections" data-test="target-settings">
    <section id="settings-laser" class="panel s-card" aria-labelledby="settings-laser-title">
      <div class="s-card-head">
        <h2 id="settings-laser-title">{{ t('激光目标') }}</h2>
        <span v-if="anyChanged(['laserAltitudeReference', 'geoidOffsetM', 'laserFlyToEnabled'])" class="s-badge warn">{{ t('未保存') }}</span>
        <span class="s-badge ok">{{ t('外场已确认') }}</span>
      </div>
      <div class="field s-field">
        <span id="laser-reference-label" class="s-label" :class="{ changed: isChanged('laserAltitudeReference') }">{{ t('激光测距高度 measure_target_altitude 的参考系') }}</span>
        <div class="radio-cards stack" role="radiogroup" aria-labelledby="laser-reference-label" data-test="laser-reference">
          <label v-for="k in refOrder" :key="k" class="radio-card">
            <input v-model="form.laserAltitudeReference" type="radio" name="laser-reference" :value="k" />
            <span class="rc-line"><b>{{ splitLabel(refLabels[k])[0] }}</b>{{ splitLabel(refLabels[k])[1] }}</span>
          </label>
        </div>
      </div>
      <div class="laser-row">
        <label class="field s-field">
          <span class="s-label" :class="{ changed: isChanged('geoidOffsetM') }">{{ t('大地水准面差距 N（椭球高 = 海拔 + N）') }}</span>
          <span class="s-input-row">
            <input v-model.number="form.geoidOffsetM" class="input num s-num" :class="{ changed: isChanged('geoidOffsetM') }" type="number" step="0.1"
              :disabled="form.laserAltitudeReference !== 'MSL'" />
            <span class="s-unit">m</span>
          </span>
          <span class="s-hint">{{ t('只在参考系为“海拔”时使用') }}</span>
        </label>
        <div class="field s-field">
          <span class="s-label" :class="{ changed: isChanged('laserFlyToEnabled') }">{{ t('飞往激光目标') }}</span>
          <label class="sw">
            <input v-model="form.laserFlyToEnabled" type="checkbox" role="switch" :disabled="form.laserAltitudeReference === 'UNKNOWN'"
              data-test="laser-flyto" />
            <span class="sw-track" aria-hidden="true"><span class="sw-knob" /></span>
            <span>{{ form.laserFlyToEnabled ? t('开启') : t('关闭') }}</span>
          </label>
        </div>
      </div>
      <p v-if="form.laserAltitudeReference === 'UNKNOWN'" class="s-warn-line" data-test="laser-flyto-locked">
        {{ t('参考系“未确认”时不能开启飞往激光目标：激光目标只能看向和标记。') }}
      </p>
      <p class="s-note">{{ t('外场已确认激光高度是椭球高（2026-10-30：悬停 20 m 测正下方地面，激光高度加 20 m 等于飞机的椭球高）。中文文档写的是“海拔”，所以另外两项留着：换机型或固件后要重新确认时用。N 可在 GeographicLib GeoidEval 用起飞点经纬度查得。') }}</p>
    </section>

    <section class="panel s-card" aria-labelledby="settings-actions-title">
      <div class="s-card-head">
        <h2 id="settings-actions-title">{{ t('操作员动作：距离、高度与速度') }}</h2>
        <span v-if="anyChanged(opFields.map((f) => f.key))" class="s-badge warn">{{ t('未保存') }}</span>
      </div>
      <div class="s-grid">
        <label v-for="f in opFields" :key="f.key" class="field s-field">
          <span class="s-label" :class="{ changed: isChanged(f.key) }">{{ f.label }}</span>
          <span class="s-input-row">
            <input v-model.number="form[f.key]" class="input num s-num" :class="{ changed: isChanged(f.key) }" type="number" :min="f.min" :max="f.max" :step="f.step" />
            <span class="s-unit">{{ f.unit }}</span>
          </span>
          <span v-if="f.hint" class="s-hint">{{ f.hint }}</span>
        </label>
      </div>
    </section>

    <section class="panel s-card" aria-labelledby="settings-ai-title">
      <div class="s-card-head">
        <h2 id="settings-ai-title">{{ t('AI 自动模式') }}</h2>
        <span v-if="anyChanged([...levels.map((l) => l.key), ...aiFields.map((f) => f.key), 'aiForbiddenMoveLabels', 'aiAllowedMoveLabels'])" class="s-badge warn">{{ t('未保存') }}</span>
      </div>
      <p class="s-card-desc">{{ t('每次飞行在实时监控里手动开启；所有限制由服务器执行。') }}</p>
      <div class="levels">
        <div v-for="lv in levels" :key="lv.key" class="level">
          <span :id="`settings-${lv.key}`" class="s-label level-label" :class="{ changed: isChanged(lv.key) }">{{ lv.label }}</span>
          <div class="seg" role="radiogroup" :aria-labelledby="`settings-${lv.key}`">
            <label v-for="o in lv.opts" :key="o.value" class="seg-opt" :class="{ auto: o.value > 0 }">
              <input v-model="form[lv.key]" type="radio" :name="`settings-${lv.key}`" :value="o.value" />
              {{ o.label }}
            </label>
          </div>
        </div>
      </div>
      <h3 class="s-sub">{{ t('限制') }}</h3>
      <div class="s-grid narrow">
        <label v-for="f in aiFields" :key="f.key" class="field s-field">
          <span class="s-label" :class="{ changed: isChanged(f.key) }">{{ f.label }}</span>
          <span class="s-input-row">
            <input v-model.number="form[f.key]" class="input num s-num" :class="{ changed: isChanged(f.key) }" type="number" :min="f.min" :max="f.max" :step="f.step" />
            <span v-if="f.unit" class="s-unit">{{ f.unit }}</span>
          </span>
          <span v-if="f.hint" class="s-hint">{{ f.hint }}</span>
        </label>
      </div>
      <div class="s-grid wide">
        <label class="field s-field">
          <span class="s-label" :class="{ changed: isChanged('aiForbiddenMoveLabels') }">{{ t('不允许触发移动的标签（只能对准）') }}</span>
          <input v-model="form.aiForbiddenMoveLabels" class="input s-text" :class="{ changed: isChanged('aiForbiddenMoveLabels') }" />
          <span class="s-hint">{{ t('逗号分隔') }}</span>
        </label>
        <label class="field s-field">
          <span class="s-label" :class="{ changed: isChanged('aiAllowedMoveLabels') }">{{ t('只允许这些标签触发移动') }}</span>
          <input v-model="form.aiAllowedMoveLabels" class="input s-text" :class="{ changed: isChanged('aiAllowedMoveLabels') }" />
          <span class="s-hint">{{ t('逗号分隔；留空 = 其余都允许') }}</span>
        </label>
      </div>
    </section>

    <section class="panel s-card" aria-labelledby="settings-area-title">
      <div class="s-card-head">
        <h2 id="settings-area-title">{{ t('AI 工作区') }}</h2>
        <span v-if="isChanged('aiWorkArea')" class="s-badge warn">{{ t('未保存') }}</span>
        <button class="btn btn-sm" :class="{ 'btn-primary': model.drawing }" @click="model.drawing = !model.drawing"><AppIcon name="edit" :size="15" />{{ model.drawing ? t('完成绘制') : t('绘制 / 编辑工作区') }}</button>
        <button class="btn btn-sm" :disabled="model.area.length === 0" @click="model.area = []"><AppIcon name="trash" :size="15" />{{ t('清空') }}</button>
      </div>
      <div class="s-legend">
        <span><i class="lg-ref" aria-hidden="true" />{{ safeZoneLegend }}</span>
        <span><i class="lg-area" aria-hidden="true" />{{ t('AI 工作区 · {n} 个顶点', { n: model.area.length }) }}</span>
      </div>
      <div class="s-map" :class="{ drawing: model.drawing, changed: isChanged('aiWorkArea') }">
        <MapCanvas :center="tel.position" :zoom="16" @map-click="model.onMapClick">
          <SafeZoneRefLayer :points="safeZoneRef" />
          <ZoneEditLayer :points="model.area" @move="(i, p) => (model.area = model.area.map((q, j) => (j === i ? p : q)))" @remove="(i) => (model.area = model.area.filter((_, j) => j !== i))" />
          <FleetLayers markers-only />
        </MapCanvas>
        <span v-if="model.drawing" class="s-map-chip">{{ t('单击地图添加顶点，拖动调整，右键删除。当前 {n} 个顶点。', { n: model.area.length }) }}</span>
      </div>
      <p class="s-note">
        <AppIcon name="info" :size="15" class="inline-icon" /> {{ t('AI 工作区：自动移动的目标和停止点都必须在此区域内，且区域须在安全区之内；开启任何自动移动级别前必须划定。地图上的安全区只作参考，在“飞行安全”中修改。') }}
      </p>
    </section>
  </div>
</template>

<style scoped>
.target-sections {
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
}
.laser-row {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: var(--sp-3) var(--sp-5);
}
.levels {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}
.level {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--sp-2);
}
.level-label {
  width: 96px;
  font-size: var(--fs-sm);
  font-weight: 600;
}
</style>
