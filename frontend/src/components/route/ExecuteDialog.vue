<script setup lang="ts">
/**
 * Execution confirmation (ui-design.md §4.5, 2.7): summary, method, safety result and DJI limitations. With several
 * drones the operator picks which one flies (default: the selected one) unless `sn` fixes it; while another drone
 * is in the air the return heights must differ (S-06) — for a drone the platform did not launch, the operator
 * confirms that here.
 */
import { computed, onMounted, ref } from 'vue'
import AppIcon from '@/components/common/AppIcon.vue'
import { routesApi, FINISH_LABELS, type Route } from '@/api/routes'
import { safetyApi, type SafetyCheckResult } from '@/api/safety'
import type { ExecMode } from '@/api/execution'
import { pathLength } from '@/utils/geo'
import { meters } from '@/utils/format'
import { useTelemetryStore } from '@/stores/telemetry'
import { useExecutionStore } from '@/stores/execution'
import { useFleetStore } from '@/stores/fleet'
import { t } from '@/i18n'

const props = defineProps<{ routeId: string; sn?: string }>()
const emit = defineEmits<{ (e: 'confirm', mode: ExecMode, sn: string, rthConfirmed: boolean): void; (e: 'cancel'): void }>()
const fleet = useFleetStore()
const chosen = ref<string>(props.sn ?? fleet.selectedSn ?? '')
const tel = computed(() => useTelemetryStore(chosen.value))
const busy = computed(() => !!useExecutionStore(chosen.value).active)
const picker = computed(() => !props.sn && fleet.enabled.length > 1)
const othersAirborne = computed(() => fleet.enabled.filter((d) => d.gatewaySn !== chosen.value && useTelemetryStore(d.gatewaySn).airborne))
const rthConfirmed = ref(false)
function status(sn: string): string {
  const tm = useTelemetryStore(sn)
  if (!tm.online) return t('未连接')
  if (useExecutionStore(sn).active) return t('已有航线在执行')
  return tm.airborne ? t('在空中') : t('在地面')
}
const route = ref<Route | null>(null)
const check = ref<SafetyCheckResult | null>(null)
const mode = ref<ExecMode>('STOP_AND_GO')
const loadError = ref<string | null>(null)

onMounted(async () => {
  try {
    route.value = await routesApi.get(props.routeId)
    check.value = await safetyApi.checkRoute({ ...route.value })
  } catch (e) {
    loadError.value = e instanceof Error ? e.message : t('加载失败')
  }
})

const length = computed(() => (route.value ? pathLength(route.value.waypoints) : 0))
const maxH = computed(() => Math.max(0, ...(route.value?.waypoints.map((w) => w.relativeHeight) ?? [0])))
const waits = computed(() => (route.value?.waypoints ?? []).flatMap((w, i) => (w.waitForConfirm ? [i + 1] : [])))
const hasGimbal = computed(() => route.value?.waypoints.some((w) => w.actions.some((a) => a.type === 'GIMBAL_PITCH')) ?? false)
</script>

<template>
  <div class="backdrop">
    <div class="dialog panel" role="dialog" aria-modal="true" :aria-label="t('执行航线')">
      <div class="panel-head"><span class="row"><AppIcon name="play" />{{ route ? t('执行航线 「{name}」', { name: route.name }) : t('执行航线') }}</span></div>
      <div class="panel-body">
        <p v-if="loadError" class="bad">{{ loadError }}</p>
        <template v-else-if="route">
          <dl class="num">
            <dt>{{ t('航点') }}</dt><dd>{{ route.waypoints.length }}</dd>
            <dt>{{ t('总长') }}</dt><dd>{{ meters(length) }}</dd>
            <dt>{{ t('最高高度') }}</dt><dd>{{ t('{h} m（离起飞点地面）', { h: maxH }) }}</dd>
            <dt>{{ t('结束动作') }}</dt><dd>{{ FINISH_LABELS[route.finishAction] }}</dd>
            <dt>{{ t('起飞方式') }}</dt><dd>{{ tel.airborne ? t('已在空中：直接飞往航点 1') : t('一键起飞至航点 1') }}</dd>
            <dt>{{ t('返航高度') }}</dt><dd>{{ route.rthHeightAuto ? t('{h} m（自动：跟随最后一个航点）', { h: route.rthHeight }) : t('{h} m（手动）', { h: route.rthHeight }) }}</dd>
            <template v-if="waits.length">
              <dt>{{ t('等待确认') }}</dt><dd data-test="execute-waits">{{ t('{n|航点|航点} {list} 到达后悬停，等你在实时监控页点「确认，继续航线」', { list: waits.join(t('、')), n: waits.length }) }}</dd>
            </template>
          </dl>
          <fieldset v-if="picker" class="mode" data-test="execute-drone">
            <legend>{{ t('执行飞机') }}</legend>
            <label v-for="d in fleet.enabled" :key="d.gatewaySn" :style="{ '--c': d.color }">
              <input v-model="chosen" type="radio" :value="d.gatewaySn" /> <b class="who">{{ d.label }}</b>
              <span class="dim">{{ status(d.gatewaySn) }}</span>
            </label>
          </fieldset>
          <label v-if="othersAirborne.length && !tel.airborne" class="rth" data-test="rth-confirm">
            <input v-model="rthConfirmed" type="checkbox" />
            {{ othersAirborne.length > 1
              ? t('{names} 正在空中。平台会检查两架的返航高度是否至少相差 {m} m； 如果其中有不是由平台起飞的，请在 Pilot 2 中确认返航高度不同后勾选此项', { names: othersAirborne.map((d) => d.label).join(t('、')), m: fleet.safety?.rthSeparationM ?? 10 })
              : t('{names} 正在空中。平台会检查两架的返航高度是否至少相差 {m} m； 如果它不是由平台起飞的，请在 Pilot 2 中确认返航高度不同后勾选此项', { names: othersAirborne.map((d) => d.label).join(t('、')), m: fleet.safety?.rthSeparationM ?? 10 }) }}
          </label>
          <fieldset class="mode">
            <legend>{{ t('执行方式') }}</legend>
            <label><input v-model="mode" type="radio" value="STOP_AND_GO" /> {{ t('逐点飞行（推荐）：设备确认到达后再飞下一点，航点处短暂悬停') }}</label>
            <label><input v-model="mode" type="radio" value="CONTINUOUS_UPDATE" /> {{ t('途中更新：接近航点就飞向下一点，不停；经过航点时可能还没到设定高度') }}</label>
          </fieldset>
          <div class="safety" :class="check?.passed ? 'ok' : 'bad'">
            <AppIcon :name="check?.passed ? 'shield' : 'alert'" :size="16" />
            <span v-if="!check">{{ t('正在进行安全检查…') }}</span>
            <span v-else-if="check.passed">{{ t('安全检查通过') }}</span>
            <span v-else>{{ t('安全检查未通过：{list}', { list: check.violations.map((v) => v.message).join(t('；')) }) }}</span>
          </div>
          <ul class="notes">
            <li>{{ t('平台用 flyto 逐点驱动（遥控器场景无法由云端下发航线任务，DEV-01）。') }}</li>
            <li>{{ t('如尚未获得控制权，会先向遥控器申请，') }}<b>{{ t('需飞手在遥控器上点击同意') }}</b>{{ t('。执行期间遥控器摇杆、返航、急停按键失效。') }}</li>
            <li>{{ t('拍照/录像动作在到点后由平台下发（需 DRC）；') }}<span v-if="hasGimbal">{{ t('云台俯仰角动作在此方式下会被跳过；') }}</span>{{ t('也可改为“同步到遥控器”由飞手在 Pilot 2 中执行原生航线。') }}</li>
          </ul>
        </template>
        <p v-else class="dim"><AppIcon name="spinner" />{{ t('加载中…') }}</p>
      </div>
      <div class="actions">
        <button class="btn" @click="emit('cancel')">{{ t('取消') }}</button>
        <button class="btn btn-primary" :disabled="!check?.passed || !tel.online || busy" data-test="execute-confirm"
                @click="emit('confirm', mode, chosen, rthConfirmed)">
          <AppIcon name="play" />{{ !tel.online ? t('设备未连接') : busy ? t('已有航线在执行') : picker ? t('由 {name} 执行', { name: fleet.label(chosen) }) : t('开始执行') }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.who {
  color: var(--c);
}
.rth {
  display: block;
  margin-top: 8px;
  font-size: var(--fs-sm);
  color: var(--warn);
}
.backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.55);
  z-index: 2400;
  display: flex;
  align-items: center;
  justify-content: center;
}
.dialog {
  width: 560px;
  max-width: calc(100vw - 32px);
  box-shadow: var(--shadow);
}
dl {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 4px var(--sp-4);
  margin: 0 0 var(--sp-3);
  font-size: var(--fs-sm);
}
dt {
  color: var(--text-dim);
}
dd {
  margin: 0;
}
.mode {
  border: 1px solid var(--border);
  border-radius: var(--r-ctl);
  padding: var(--sp-2) var(--sp-3);
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: var(--fs-sm);
}
.mode legend {
  font-size: var(--fs-xs);
  color: var(--text-dim);
  padding: 0 4px;
}
.mode input {
  accent-color: var(--accent);
}
.safety {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin-top: var(--sp-3);
  font-size: var(--fs-sm);
}
.ok {
  color: var(--ok);
}
.bad {
  color: var(--danger);
}
.notes {
  margin: var(--sp-3) 0 0;
  padding-left: 18px;
  font-size: var(--fs-xs);
  color: var(--text-dim);
}
.actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--sp-2);
  padding: 0 var(--sp-4) var(--sp-4);
}
</style>
