/**
 * Target selection settings form (D-21 ~ D-24): laser height reference (U-24) and the laser fly-to switch,
 * distance rules, AI auto mode levels and limits, and the AI work area. The state, dirty check, confirmation
 * and save are the ones TargetSettingsCard had before the settings page was split into sections; they live
 * here so that unsaved edits survive switching sections. `changed` is display only.
 */
import { computed, reactive, ref, watch } from 'vue'
import { useTargetsStore } from '@/stores/targets'
import { useToastStore } from '@/stores/toast'
import { useConfirmStore } from '@/stores/confirm'
import type { LaserReference, TargetConfig } from '@/api/targets'
import type { LatLon } from '@/utils/coord'
import { t } from '@/i18n'

export type TargetForm = Omit<TargetConfig, 'aiForbiddenMoveLabels' | 'aiAllowedMoveLabels' | 'aiWorkArea' | 'updatedAt'> & {
  aiForbiddenMoveLabels: string
  aiAllowedMoveLabels: string
}

export const refLabels: Record<LaserReference, string> = {
  UNKNOWN: t('未确认：激光目标只能看向和标记'),
  ELLIPSOID: t('椭球高（默认，外场已确认；与 fly_to_point 相同）'),
  MSL: t('海拔：加上下面的大地水准面差距换算为椭球高'),
}

/** Field names for the save bar, in the order they appear on the page. */
export const TARGET_FIELD_NAMES: Record<string, string> = {
  laserAltitudeReference: t('激光参考系'),
  geoidOffsetM: t('大地水准面差距 N'),
  laserFlyToEnabled: t('飞往激光目标'),
  minDistanceM: t('最小距离'),
  stopDistanceM: t('停止距离'),
  clearanceM: t('高于目标余量'),
  approachSpeed: t('接近速度'),
  aboveHeightM: t('上方高度'),
  maxLaserRangeM: t('激光最大距离'),
  maxAccuracyM: t('允许误差'),
  aiLookLevel: t('AI 对准'),
  aiApproachLevel: t('AI 接近'),
  aiAboveLevel: t('AI 飞到上方'),
  aiOrbitLevel: t('AI 环绕'),
  aiMinConfidence: t('最低置信度'),
  aiMaxMoveM: t('单次最大移动'),
  aiStopDistanceM: t('AI 停止距离'),
  aiExtraHeightM: t('AI 额外高度'),
  aiCountdownS: t('倒计时'),
  aiCooldownS: t('冷却'),
  aiMaxPerMinute: t('每分钟最多'),
  aiMaxAccuracyM: t('AI 允许误差'),
  aiForbiddenMoveLabels: t('禁止移动标签'),
  aiAllowedMoveLabels: t('允许移动标签'),
  aiWorkArea: t('AI 工作区'),
}
const ORDER = Object.keys(TARGET_FIELD_NAMES)

export function useTargetSettings() {
  const targets = useTargetsStore()
  const toast = useToastStore()
  const confirm = useConfirmStore()

  const form = ref<TargetForm | null>(null)
  const area = ref<LatLon[]>([])
  const drawing = ref(false)
  const saving = ref(false)

  function reset(): void {
    const c = targets.config
    if (!c) return
    const { aiForbiddenMoveLabels, aiAllowedMoveLabels, aiWorkArea, updatedAt: _u, ...rest } = c
    form.value = { ...rest, aiForbiddenMoveLabels: aiForbiddenMoveLabels.join(','), aiAllowedMoveLabels: aiAllowedMoveLabels.join(',') }
    area.value = aiWorkArea.map(([lat, lon]) => ({ lat, lon }))
  }
  watch(() => targets.config, reset, { immediate: true })

  const dirty = computed(() => {
    const c = targets.config
    const f = form.value
    if (!c || !f) return false
    const { aiForbiddenMoveLabels, aiAllowedMoveLabels, aiWorkArea, updatedAt: _u, ...rest } = c
    return JSON.stringify({ ...rest, aiForbiddenMoveLabels: aiForbiddenMoveLabels.join(','), aiAllowedMoveLabels: aiAllowedMoveLabels.join(',') }) !== JSON.stringify(f)
      || JSON.stringify(aiWorkArea) !== JSON.stringify(area.value.map((p) => [p.lat, p.lon]))
  })

  /** The same comparison as `dirty`, per field (display only). */
  const changed = computed<string[]>(() => {
    const c = targets.config
    const f = form.value
    if (!c || !f) return []
    const { aiForbiddenMoveLabels, aiAllowedMoveLabels, aiWorkArea, updatedAt: _u, ...rest } = c
    const saved: Record<string, unknown> = { ...rest, aiForbiddenMoveLabels: aiForbiddenMoveLabels.join(','), aiAllowedMoveLabels: aiAllowedMoveLabels.join(',') }
    const cur: Record<string, unknown> = f
    const keys = new Set([...Object.keys(saved), ...Object.keys(cur)])
    const out = [...keys].filter((k) => JSON.stringify(saved[k]) !== JSON.stringify(cur[k]))
    if (JSON.stringify(aiWorkArea) !== JSON.stringify(area.value.map((p) => [p.lat, p.lon]))) out.push('aiWorkArea')
    const rank = (k: string) => (ORDER.includes(k) ? ORDER.indexOf(k) : ORDER.length)
    return out.sort((a, b) => rank(a) - rank(b))
  })

  function onMapClick(p: LatLon): void {
    if (drawing.value) area.value = [...area.value, { lat: Math.round(p.lat * 1e7) / 1e7, lon: Math.round(p.lon * 1e7) / 1e7 }]
  }

  async function save(): Promise<void> {
    const f = form.value
    if (!f) return
    const ok = await confirm.ask({
      title: t('保存目标选择设置'),
      message: t('设置会立即作用于目标动作与 AI 自动模式。确认保存？'),
      details: [
        f.laserAltitudeReference === 'MSL'
          ? t('激光高度参考系：{ref}（N = {n} m）', { ref: refLabels[f.laserAltitudeReference], n: f.geoidOffsetM })
          : t('激光高度参考系：{ref}', { ref: refLabels[f.laserAltitudeReference] }),
        f.laserFlyToEnabled ? t('飞往激光目标：开启') : t('飞往激光目标：关闭'),
        t('最小距离 {min} m · 停止距离 {stop} m · 高于目标 {clearance} m · 速度 {speed} m/s', { min: f.minDistanceM, stop: f.stopDistanceM, clearance: f.clearanceM, speed: f.approachSpeed }),
        t('AI：对准 {look} · 接近 {approach} · 上方 {above} · 环绕 {orbit}；工作区 {n} 个顶点', { look: f.aiLookLevel, approach: f.aiApproachLevel, above: f.aiAboveLevel, orbit: f.aiOrbitLevel, n: area.value.length }),
      ],
    })
    if (!ok) return
    saving.value = true
    const saved = await targets.updateConfig({ ...f, aiWorkArea: area.value.map((p) => [p.lat, p.lon] as [number, number]) })
    saving.value = false
    if (saved) {
      drawing.value = false
      toast.push('ok', t('目标选择设置已保存'))
    }
  }

  return reactive({ form, area, drawing, saving, dirty, changed, reset, onMapClick, save })
}

export type TargetSettings = ReturnType<typeof useTargetSettings>
