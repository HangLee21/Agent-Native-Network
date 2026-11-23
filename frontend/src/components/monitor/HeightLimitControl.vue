<script setup lang="ts">
/**
 * Aircraft height_limit (R-13, S-01): the same input, confirmation and API call as the former
 * "更多控制 → 飞行器限高" block. Used in the pre-flight checklist and the panel's ⋯ menu.
 */
import { ref } from 'vue'
import CommandStatus from '@/components/control/CommandStatus.vue'
import { controlApi } from '@/api/control'
import { useControlStore } from '@/stores/control'
import { useTelemetryStore } from '@/stores/telemetry'
import { useConfirmStore } from '@/stores/confirm'
import { useSafetyStore } from '@/stores/safety'
import { useDroneSn } from '@/composables/useDrone'
import { t, tc } from '@/i18n'

/** The drone this component works on, fixed at setup (D-31). */
const sn = useDroneSn()

const control = useControlStore()
const tel = useTelemetryStore()
const confirm = useConfirmStore()
const safety = useSafetyStore()
const heightLimit = ref<number>(120)
/** The verb "set" (button and confirm), not 设置 = "Settings" in the top bar. */
const SET = tc('verb', '设置')

async function setLimit(): Promise<void> {
  if (!(await confirm.ask({ title: t('设置飞行器限高'), message: t('将飞行器自身限高（height_limit）设为 {h} m？', { h: heightLimit.value }), confirmText: SET }))) return
  await control.run('heightLimit', t('设置飞行器限高'), () => controlApi(sn).heightLimit(heightLimit.value))
}
</script>

<template>
  <div class="hl" data-test="height-limit">
    <div class="row-in">
      <input v-model.number="heightLimit" class="input num" type="number" min="20" max="1500" :aria-label="t('飞行器限高（m）')" /> m
      <button class="btn btn-sm" :disabled="!tel.online" data-test="height-limit-set" @click="setLimit">{{ SET }}</button>
      <button class="btn btn-sm btn-ghost" :disabled="!safety.config" @click="heightLimit = safety.config?.maxHeight ?? 120">{{ t('取平台限高') }}</button>
    </div>
    <p class="note">{{ t('当前飞行器限高 {cur} m · 范围 20–1500 m · 平台限高 {max} m', { cur: tel.drone?.heightLimit ?? '—', max: safety.config?.maxHeight ?? '—' }) }}</p>
    <CommandStatus :record="control.byAction('heightLimit')" />
  </div>
</template>

<style scoped>
.hl {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.row-in {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: var(--fs-sm);
}
.row-in .input {
  width: 76px;
  min-height: 32px;
}
.note {
  margin: 0;
  font-size: var(--fs-xs);
  color: var(--text-dim);
}
</style>
