/**
 * Safety settings form of the settings page (S-01, S-02, D-03). The state, dirty check, confirmation and
 * save are the ones SettingsView had before the page was split into sections; they live here so that
 * unsaved edits survive switching sections. `changed` only lists the edited fields for the badges,
 * highlights and the save bar — it does not take part in saving.
 */
import { computed, reactive, ref, watch } from 'vue'
import { useSafetyStore } from '@/stores/safety'
import { useToastStore } from '@/stores/toast'
import { useConfirmStore } from '@/stores/confirm'
import { ApiError } from '@/api/http'
import type { HeightPolicy } from '@/api/safety'
import type { LatLon } from '@/utils/coord'
import { t } from '@/i18n'

export type SafetyKey = 'maxHeight' | 'minHeight' | 'maxSpeed' | 'minTakeoffBattery' | 'unknownHeightPolicy' | 'safeZoneEnabled' | 'safeZone'

/** Field names for the save bar, in the order they appear on the page. */
export const SAFETY_FIELD_NAMES: Record<SafetyKey, string> = {
  maxHeight: t('平台限高'),
  minHeight: t('最低高度'),
  maxSpeed: t('最大速度'),
  minTakeoffBattery: t('起飞最低电量'),
  safeZoneEnabled: t('启用安全区'),
  safeZone: t('安全区顶点'),
  unknownHeightPolicy: t('校验策略'),
}

export function useSafetySettings() {
  const safety = useSafetyStore()
  const toast = useToastStore()
  const confirm = useConfirmStore()

  const form = ref({ maxHeight: 120, minHeight: 20, maxSpeed: 15, minTakeoffBattery: 25, unknownHeightPolicy: 'ASSUME_INFERRED' as HeightPolicy })
  const zone = ref<LatLon[]>([])
  const zoneEnabled = ref(false)
  const drawing = ref(false)
  const saving = ref(false)

  function reset(): void {
    const c = safety.config
    if (!c) return
    form.value = { maxHeight: c.maxHeight, minHeight: c.minHeight, maxSpeed: c.maxSpeed, minTakeoffBattery: c.minTakeoffBattery, unknownHeightPolicy: c.unknownHeightPolicy }
    zone.value = c.safeZone.map(([lat, lon]) => ({ lat, lon }))
    zoneEnabled.value = c.safeZoneEnabled
  }
  watch(() => safety.config, reset, { immediate: true })

  const dirty = computed(() => {
    const c = safety.config
    if (!c) return false
    return (
      c.maxHeight !== form.value.maxHeight || c.minHeight !== form.value.minHeight || c.maxSpeed !== form.value.maxSpeed ||
      c.minTakeoffBattery !== form.value.minTakeoffBattery || c.unknownHeightPolicy !== form.value.unknownHeightPolicy ||
      c.safeZoneEnabled !== zoneEnabled.value || JSON.stringify(c.safeZone) !== JSON.stringify(zone.value.map((p) => [p.lat, p.lon]))
    )
  })

  /** The same comparisons as `dirty`, per field (display only). */
  const changed = computed<SafetyKey[]>(() => {
    const c = safety.config
    if (!c) return []
    const f = form.value
    const out: SafetyKey[] = []
    if (c.maxHeight !== f.maxHeight) out.push('maxHeight')
    if (c.minHeight !== f.minHeight) out.push('minHeight')
    if (c.maxSpeed !== f.maxSpeed) out.push('maxSpeed')
    if (c.minTakeoffBattery !== f.minTakeoffBattery) out.push('minTakeoffBattery')
    if (c.safeZoneEnabled !== zoneEnabled.value) out.push('safeZoneEnabled')
    if (JSON.stringify(c.safeZone) !== JSON.stringify(zone.value.map((p) => [p.lat, p.lon]))) out.push('safeZone')
    if (c.unknownHeightPolicy !== f.unknownHeightPolicy) out.push('unknownHeightPolicy')
    return out
  })

  function onMapClick(p: LatLon): void {
    if (drawing.value) zone.value = [...zone.value, { lat: Math.round(p.lat * 1e7) / 1e7, lon: Math.round(p.lon * 1e7) / 1e7 }]
  }

  async function save(): Promise<void> {
    const ok = await confirm.ask({
      title: t('保存安全设置'),
      message: t('安全设置会立即作用于所有航线保存、同步与飞行指令。确认保存？'),
      details: [
        t('平台限高 {max} m，最低高度 {min} m（相对起飞点）', { max: form.value.maxHeight, min: form.value.minHeight }),
        t('最大速度 {speed} m/s，起飞最低电量 {battery}%', { speed: form.value.maxSpeed, battery: form.value.minTakeoffBattery }),
        zoneEnabled.value ? t('安全区：启用（{n} 个顶点）', { n: zone.value.length }) : t('安全区：未启用'),
      ],
    })
    if (!ok) return
    saving.value = true
    try {
      await safety.update({ ...form.value, safeZoneEnabled: zoneEnabled.value, safeZone: zone.value.map((p) => [p.lat, p.lon]) })
      drawing.value = false
      toast.push('ok', t('安全设置已保存'))
    } catch (e) {
      toast.push('danger', e instanceof ApiError ? t('保存失败：{msg}', { msg: e.message }) : t('保存失败'))
    } finally {
      saving.value = false
    }
  }

  return reactive({ form, zone, zoneEnabled, drawing, saving, dirty, changed, reset, onMapClick, save })
}

export type SafetySettings = ReturnType<typeof useSafetySettings>
