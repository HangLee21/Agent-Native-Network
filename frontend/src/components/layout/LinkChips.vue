<script setup lang="ts">
/**
 * First-level status in the top bar (ui-design.md §3, 2.7). One drone: its link, control, battery, satellites,
 * recording and alerts. Several: a chip per enabled drone (colour, name, battery; click selects it), the
 * proximity mode, and the alert count of all drones.
 */
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppIcon from '@/components/common/AppIcon.vue'
import DogChips from '@/components/dog/DogChips.vue'
import { useDogStore, lite3Pose } from '@/stores/dog'
import type { DogId } from '@/api/dog'
import DroneScope from '@/components/common/DroneScope.vue'
import DroneChips from './DroneChips.vue'
import { useFleetStore } from '@/stores/fleet'
import { useControlStore } from '@/stores/control'
import { useTelemetryStore } from '@/stores/telemetry'
import { t, tc } from '@/i18n'

const fleet = useFleetStore()
/* robot dogs (docs/dog/ui-design.md 5.1): with dogs configured every device gets a chip, the drones as with two */
const dogs = useDogStore()
const route = useRoute()
const router = useRouter()
onMounted(() => dogs.start())
const many = computed(() => fleet.drones.length > 1 || dogs.present)
function pickDrone(sn: string): void {
  dogs.select(null)
  fleet.select(sn)
}
function pickDog(id: DogId): void {
  dogs.select(id)
  if (route.path !== '/monitor') void router.push('/monitor')
}
/** Dog alerts in the same counter: lost while busy, Lite3 low-power or out-of-control protection. */
const dogAlerts = computed(() => dogs.ids.filter((id) => {
  if (dogs.lost(id)) return true
  if (id !== 'lite3' || !dogs.online(id)) return false
  const r = dogs.lite3?.robot
  return (typeof r?.battery === 'number' && r.battery < 20) || lite3Pose(r?.robot_state) === 'protect'
}).length)

function chip(sn: string) {
  const tel = useTelemetryStore(sn)
  const control = useControlStore(sn)
  const b = tel.online ? tel.drone?.batteryPercent : null
  const rth = tel.drone?.returnHomePower ?? 20
  return {
    cls: !tel.online ? 'danger' : b != null && b <= rth ? 'danger' : b != null && b <= rth + 10 ? 'warn' : 'ok',
    battery: b != null ? `${b}%` : '—',
    title: `${tel.online ? t('在线') : t('未连接')} · ${control.granted ? (control.drcReady ? t('控制权 · DRC') : tc('chip', '控制权')) : t('无控制权')}`,
  }
}
const alerts = computed(() => fleet.enabled.reduce((n, d) => n + useControlStore(d.gatewaySn).alerts.length, 0) + dogAlerts.value)
const critical = computed(() => fleet.enabled.reduce((n, d) => n + useControlStore(d.gatewaySn).criticalCount, 0) + dogAlerts.value)
const mode = computed(() => (fleet.safety?.proximityMode === 'WARN_ONLY' ? tc('chip', '只报警') : tc('chip', '报警并悬停')))
</script>

<template>
  <template v-if="many">
    <button v-for="d in fleet.enabled" :key="d.gatewaySn" class="chip drone" :class="[chip(d.gatewaySn).cls, { on: d.gatewaySn === fleet.selectedSn && !dogs.selected }]"
            :style="{ '--c': d.color }" :title="t('{name}：{status}（点击选中）', { name: d.label, status: chip(d.gatewaySn).title })" data-test="drone-chip" @click="pickDrone(d.gatewaySn)">
      <span class="sw" /><b>{{ d.label }}</b><span class="num">{{ chip(d.gatewaySn).battery }}</span>
    </button>
    <DogChips @select="pickDog" />
    <span v-if="fleet.drones.length > 1" class="chip" :class="fleet.proximity.length ? 'warn' : ''" :title="t('两机靠近时的处理方式（设置页「安全」可改）')" data-test="proximity-chip">
      {{ t('靠近：{mode}', { mode }) }}
    </span>
    <span class="chip" :class="critical ? 'danger' : alerts ? 'warn' : ''" :title="t('全部设备的告警数量')" data-test="alert-count">
      <AppIcon name="alert" :size="15" /><span class="num">{{ alerts }}</span>
    </span>
  </template>
  <DroneScope v-else-if="fleet.selectedSn" :key="fleet.selectedSn" :sn="fleet.selectedSn">
    <DroneChips />
  </DroneScope>
</template>

<style scoped>
.drone {
  gap: 5px;
  cursor: pointer;
  font: inherit;
}
.drone .sw {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: var(--c);
}
.drone.on {
  outline: 2px solid var(--c);
  outline-offset: -1px;
}
</style>
