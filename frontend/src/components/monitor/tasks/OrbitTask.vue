<script setup lang="ts">
/**
 * POI orbit (R-13). Same flow as before: pick the centre on the map (control.pickingTarget = 'poi'),
 * the existing TargetDialog asks the centre height and sends poi/enter; the speed is set with poi/speed
 * (negative = clockwise). Exit is in the footer (退出环绕, always available as before).
 */
import { computed, ref } from 'vue'
import TaskCardShell from '../TaskCardShell.vue'
import CommandStatus from '@/components/control/CommandStatus.vue'
import { controlApi } from '@/api/control'
import { useControlStore } from '@/stores/control'
import { useTelemetryStore } from '@/stores/telemetry'
import { useTasksStore } from '@/stores/tasks'
import { useOverlaysStore } from '@/stores/overlays'
import type { PoiOverlay } from '@/stores/overlays'
import { num } from '@/utils/format'
import { useDroneSn } from '@/composables/useDrone'
import { t } from '@/i18n'

/** The drone this component works on, fixed at setup (D-31). */
const sn = useDroneSn()

const control = useControlStore()
const tel = useTelemetryStore()
const tasks = useTasksStore()
const overlays = useOverlaysStore()
const poiSpeed = ref(3)
const picking = computed(() => control.pickingTarget === 'poi')
const running = computed(() => tasks.motion === 'orb')
const poi = computed(() => (overlays.items.poi?.data as PoiOverlay | undefined) ?? null)
const state = computed(() => (running.value ? t('环绕中') : picking.value ? t('等待选点') : ''))

const toggle = () => (control.pickingTarget = picking.value ? null : 'poi')
const setPoiSpeed = () => control.run('poi', t('设置环绕速度'), () => controlApi(sn).poiSpeed(poiSpeed.value))
</script>

<template>
  <TaskCardShell task="orb" :title="t('环绕兴趣点')" icon="orbit" :state="state">
    <p v-if="!tel.airborne" class="txt">{{ t('需在空中才能环绕。') }}</p>
    <template v-else>
      <p v-if="picking" class="txt">{{ t('在地图上单击选择环绕中心，然后在对话框里填中心高度。飞机以当前位置到中心的距离为半径环绕。') }}</p>
      <p v-else-if="running" class="txt">{{ t('环绕中') }}<template v-if="poi?.radius != null"> · {{ t('半径') }} <span class="num">{{ num(poi.radius, 0) }} m</span></template></p>
      <button v-if="!running" class="btn btn-sm" :class="{ 'btn-primary': picking }" data-test="poi-pick" @click="toggle">{{ picking ? t('取消选点') : t('在地图上选环绕中心') }}</button>
    </template>
    <div class="speed">
      <label class="lbl">{{ t('环绕速度') }} <input v-model.number="poiSpeed" class="input num" type="number" step="0.5" /> m/s</label>
      <button class="btn btn-sm" data-test="poi-speed" @click="setPoiSpeed">{{ t('设速度') }}</button>
    </div>
    <p class="note">{{ t('负数顺时针、正数逆时针，绝对值不超过 15 m/s。退出环绕在底部「停止」和 ▾ 里。') }}</p>
    <CommandStatus :record="control.byAction('poi')" />
  </TaskCardShell>
</template>

<style scoped>
.txt {
  margin: 0;
  font-size: var(--fs-sm);
}
.btn {
  align-self: flex-start;
}
.speed {
  display: flex;
  align-items: center;
  gap: 6px;
}
.lbl {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: var(--fs-sm);
}
.lbl .input {
  width: 72px;
  min-height: 32px;
}
.note {
  margin: 0;
  font-size: var(--fs-xs);
  color: var(--text-dim);
}
</style>
