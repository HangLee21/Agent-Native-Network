<script setup lang="ts">
/**
 * Fly to a map point (R-13). Same flow as before: pick on the map (control.pickingTarget = 'flyto'),
 * then the existing TargetDialog asks height and speed and sends fly-to. Stopping is in the footer.
 */
import { computed } from 'vue'
import TaskCardShell from '../TaskCardShell.vue'
import CommandStatus from '@/components/control/CommandStatus.vue'
import { useControlStore } from '@/stores/control'
import { useTelemetryStore } from '@/stores/telemetry'
import { useTasksStore } from '@/stores/tasks'
import { useOverlaysStore } from '@/stores/overlays'
import type { TargetOverlay } from '@/stores/overlays'
import { coord } from '@/utils/format'
import { t } from '@/i18n'

const control = useControlStore()
const tel = useTelemetryStore()
const tasks = useTasksStore()
const overlays = useOverlaysStore()
const picking = computed(() => control.pickingTarget === 'flyto')
const running = computed(() => tasks.motion === 'fly')
const target = computed(() => (overlays.items.target?.data as TargetOverlay | undefined) ?? null)
const state = computed(() => (running.value ? t('飞行中') : picking.value ? t('等待选点') : ''))

const toggle = () => (control.pickingTarget = picking.value ? null : 'flyto')
</script>

<template>
  <TaskCardShell task="fly" :title="t('飞往地图点')" icon="pin" :state="state">
    <p v-if="!tel.airborne" class="txt">{{ t('需在空中才能飞往地图点。') }}</p>
    <template v-else>
      <p v-if="picking" class="txt">{{ t('在地图上单击选择目标点，然后在对话框里填高度和速度。') }}</p>
      <template v-else-if="running">
        <p v-if="target" class="txt">{{ t('正在飞往 {name}', { name: target.label }) }} · <span class="num">{{ coord(target.lat) }}, {{ coord(target.lon) }}</span></p>
        <p class="note">{{ t('要改目标点：先用底部「停止」悬停，再选点。') }}</p>
      </template>
      <button v-if="!running" class="btn btn-sm" :class="{ 'btn-primary': picking }" data-test="flyto-pick" @click="toggle">{{ picking ? t('取消选点') : t('在地图上选点') }}</button>
    </template>
    <CommandStatus :record="control.byAction('flyto')" />
    <p class="note">{{ t('flyto 每次只支持 1 个目标点；低于 20 m 时飞机会先爬升到 20 m（大疆限制）。') }}</p>
  </TaskCardShell>
</template>

<style scoped>
.txt {
  margin: 0;
  font-size: var(--fs-sm);
}
.note {
  margin: 0;
  font-size: var(--fs-xs);
  color: var(--text-dim);
}
.btn {
  align-self: flex-start;
}
</style>
