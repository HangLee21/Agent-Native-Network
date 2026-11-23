<script setup lang="ts">
/**
 * Stick control (R-13, D-16): same max-scale field, enabling rule and manual.enter call as before.
 * While active, the sticks overlay the video (StickControlOverlay, with its own 退出杆量控制).
 */
import { computed, ref } from 'vue'
import TaskCardShell from '../TaskCardShell.vue'
import { useControlStore } from '@/stores/control'
import { useTelemetryStore } from '@/stores/telemetry'
import { useManualStore } from '@/stores/manual'
import { t } from '@/i18n'

const control = useControlStore()
const tel = useTelemetryStore()
const manual = useManualStore()
const stickScale = ref(30)
const active = computed(() => !!manual.snapshot?.active)
const stickReady = computed(() => control.granted && control.drcReady && tel.airborne)
const why = computed(() => (!control.granted ? t('需要云端控制权') : !control.drcReady ? t('需要 DRC 链路') : !tel.airborne ? t('需在空中') : ''))
const enterStick = () => void manual.enter(stickScale.value / 100)
</script>

<template>
  <TaskCardShell task="stk" :title="t('杆量控制')" icon="joystick" :state="active ? t('控制中') : ''">
    <template v-if="!active">
      <div class="row-in">
        <label class="lbl">{{ t('最大杆量') }} <input v-model.number="stickScale" class="input num" type="number" min="5" :max="Math.round((manual.snapshot?.maxScale ?? 0.5) * 100)" step="5" />%</label>
        <button class="btn btn-sm btn-primary" :disabled="!stickReady" data-test="stick-enter" @click="enterStick">{{ t('进入杆量控制') }}</button>
      </div>
      <p v-if="why" class="note">{{ why }}</p>
    </template>
    <p v-else class="txt">{{ t('杆量控制中：摇杆在画面上，最大杆量在摇杆面板里调整。') }}</p>
    <p v-if="manual.error" class="note err" data-test="stick-error">{{ manual.error }}</p>
    <p v-else-if="manual.snapshot?.message && !active" class="note">{{ manual.snapshot.message }}</p>
    <p class="note">{{ t('杆量指令需 5–10 Hz 持续发送且没有设备回执（DEV-03），平台在服务器端限制杆量、限高附近禁止上升、安全区外禁止水平移动，断开或松手即回中。首次使用请低空、小杆量，飞手随时准备接管。') }}</p>
  </TaskCardShell>
</template>

<style scoped>
.row-in {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.lbl {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: var(--fs-sm);
}
.lbl .input {
  width: 64px;
  min-height: 32px;
}
.txt {
  margin: 0;
  font-size: var(--fs-sm);
}
.note {
  margin: 0;
  font-size: var(--fs-xs);
  color: var(--text-dim);
}
.note.err {
  color: var(--danger);
}
</style>
