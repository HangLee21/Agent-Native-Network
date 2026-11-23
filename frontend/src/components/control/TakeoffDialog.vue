<script setup lang="ts">
/**
 * Take-off confirmation with editable defaults (D-11 / DEV-07: one confirmation, parameters visible). With several
 * drones the title names the drone, and while another one is in the air the return heights must differ (S-06):
 * for a drone the platform did not launch, the operator confirms it here.
 */
import { computed, ref } from 'vue'
import AppIcon from '@/components/common/AppIcon.vue'
import { RC_LOST_LABELS, type RcLostAction } from '@/api/routes'
import type { TakeoffRequest } from '@/api/control'
import { useSafetyStore } from '@/stores/safety'
import { useFleetStore } from '@/stores/fleet'
import { useTelemetryStore } from '@/stores/telemetry'
import { useDroneSn } from '@/composables/useDrone'
import { t, tc } from '@/i18n'

const emit = defineEmits<{ (e: 'confirm', r: TakeoffRequest): void; (e: 'cancel'): void }>()
const safety = useSafetyStore()
const fleet = useFleetStore()
const sn = useDroneSn()
const many = computed(() => fleet.drones.length > 1)
const othersAirborne = computed(() => fleet.enabled.filter((d) => d.gatewaySn !== sn && useTelemetryStore(d.gatewaySn).airborne))
const rthConfirmed = ref(false)
const form = ref<TakeoffRequest>({ relativeHeight: 30, securityTakeoffHeight: 20, rthAltitude: 80, rcLostAction: 'RETURN_HOME' as RcLostAction, maxSpeed: 8 })
</script>

<template>
  <div class="backdrop" @keydown.esc="emit('cancel')">
    <form class="dialog panel" role="dialog" aria-modal="true" :aria-label="t('确认起飞')" @submit.prevent="emit('confirm', { ...form, rthConfirmed })">
      <div class="panel-head"><span class="row"><AppIcon name="takeoff" />{{ many ? t('确认 {name} 起飞', { name: fleet.label(sn) }) : t('确认起飞') }}</span></div>
      <div class="panel-body">
        <p class="lead">{{ t('飞行器将从当前位置垂直起飞到目标高度并悬停。') }}</p>
        <label v-if="othersAirborne.length" class="rth" data-test="rth-confirm">
          <input v-model="rthConfirmed" type="checkbox" />
          {{ t('{names} 正在空中：返航高度必须与它至少相差 {m} m，平台会检查。', { names: othersAirborne.map((d) => d.label).join(t('、')), m: fleet.safety?.rthSeparationM ?? 10 }) }}
          {{ t('如果它不是由平台起飞的，请在 Pilot 2 中确认返航高度不同后勾选此项') }}
        </label>
        <div class="grid">
          <label class="field"><span>{{ t('起飞高度（m，相对起飞点）') }}</span><input v-model.number="form.relativeHeight" class="input num" type="number" data-test="takeoff-height" /></label>
          <label class="field"><span>{{ t('安全起飞高度（m）') }}</span><input v-model.number="form.securityTakeoffHeight" class="input num" type="number" min="20" /></label>
          <label class="field"><span>{{ t('返航高度（m）') }}</span><input v-model.number="form.rthAltitude" class="input num" type="number" /></label>
          <label class="field"><span>{{ t('最大速度（m/s）') }}</span><input v-model.number="form.maxSpeed" class="input num" type="number" min="1" max="15" /></label>
          <label class="field wide"><span>{{ t('遥控器失联动作') }}</span>
            <select v-model="form.rcLostAction" class="input">
              <option v-for="(l, k) in RC_LOST_LABELS" :key="k" :value="k">{{ l }}</option>
            </select></label>
        </div>
        <ul class="notes">
          <li>{{ t('平台限高 {h} m，超出将被安全层拒绝。', { h: safety.config?.maxHeight ?? '—' }) }}</li>
          <li>{{ t('如尚未获得控制权，平台会先向遥控器申请授权，') }}<b>{{ t('需飞手在遥控器上点击同意') }}</b>{{ t('后才会起飞。') }}</li>
          <li>{{ t('起飞高度是相对起飞点的高度：飞机原地垂直爬到这个高度后悬停，最低 20 m。') }}</li>
          <li v-if="safety.config?.unknownHeightPolicy === 'DUAL_CHECK'">{{ t('设置页的高度校验策略现在是「双重校验」：飞机会先爬得比填写值高再降回（10-30 外场先冲到约 59 m），最高到') }}<b>{{ tc('inline', '飞行器限高') }}</b>{{ t('。') }}</li>
        </ul>
      </div>
      <div class="actions">
        <button type="button" class="btn" @click="emit('cancel')">{{ t('取消') }}</button>
        <button type="submit" class="btn btn-primary" data-test="takeoff-confirm"><AppIcon name="takeoff" />{{ t('确认起飞') }}</button>
      </div>
    </form>
  </div>
</template>

<style scoped>
.rth {
  display: block;
  margin: 0 0 10px;
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
  width: 520px;
  max-width: calc(100vw - 32px);
  box-shadow: var(--shadow);
}
.lead {
  margin: 0 0 var(--sp-3);
}
.grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--sp-3);
}
.grid .input {
  width: 100%;
}
.wide {
  grid-column: 1 / -1;
}
.notes {
  margin: var(--sp-3) 0 0;
  padding-left: 18px;
  font-size: var(--fs-sm);
  color: var(--text-dim);
}
.actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--sp-2);
  padding: 0 var(--sp-4) var(--sp-4);
}
</style>
