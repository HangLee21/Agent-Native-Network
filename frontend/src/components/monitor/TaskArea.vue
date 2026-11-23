<script setup lang="ts">
/**
 * Task area of the monitor side panel (ui-design.md §2.2): pre-flight checklist on the ground, the task
 * selector, and exactly one task card. If another task is moving the aircraft, a strip says so.
 */
import { computed } from 'vue'
import TaskBar from './TaskBar.vue'
import PreflightCard from './tasks/PreflightCard.vue'
import ReturnHomeCard from './tasks/ReturnHomeCard.vue'
import FlyToTask from './tasks/FlyToTask.vue'
import OrbitTask from './tasks/OrbitTask.vue'
import RouteTask from './tasks/RouteTask.vue'
import StickTask from './tasks/StickTask.vue'
import TargetTask from './tasks/TargetTask.vue'
import AiTask from './tasks/AiTask.vue'
import { useTasksStore, type TaskKey } from '@/stores/tasks'
import { useTelemetryStore } from '@/stores/telemetry'
import { t } from '@/i18n'

const tasks = useTasksStore()
const tel = useTelemetryStore()

const CARD_OF: Record<string, TaskKey | null> = { fly: 'fly', orb: 'orb', rte: 'rte', stk: 'stk', tgt: 'tgt', rth: null }
const stripCard = computed<TaskKey | null>(() => {
  const card = tasks.motion ? CARD_OF[tasks.motion] : null
  return card && card !== tasks.selected ? card : null
})
</script>

<template>
  <div class="task-area" data-test="task-area">
    <PreflightCard v-if="!tel.airborne" />
    <TaskBar :big="tel.airborne && !tasks.selected" />
    <ReturnHomeCard v-if="tel.drone?.modeCode === 9" />
    <button v-if="stripCard" class="strip" data-test="running-strip" @click="tasks.show(stripCard)">
      <span class="dot" /><b>{{ t('{task}进行中', { task: tasks.motionName }) }}</b><span class="go">{{ t('查看 ›') }}</span>
    </button>
    <FlyToTask v-if="tasks.selected === 'fly'" />
    <OrbitTask v-else-if="tasks.selected === 'orb'" />
    <RouteTask v-else-if="tasks.selected === 'rte'" />
    <StickTask v-else-if="tasks.selected === 'stk'" />
    <TargetTask v-else-if="tasks.selected === 'tgt'" />
    <AiTask v-else-if="tasks.selected === 'ai'" />
  </div>
</template>

<style scoped>
.task-area {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.strip {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  width: 100%;
  padding: var(--sp-2) 10px;
  border-radius: var(--r-ctl);
  border: 1px solid color-mix(in srgb, var(--ok) 60%, transparent);
  background: color-mix(in srgb, var(--ok) 10%, transparent);
  color: var(--text);
  font: inherit;
  font-size: var(--fs-sm);
  text-align: left;
  cursor: pointer;
}
.strip b {
  flex: 1;
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--ok);
  animation: pulse 1.2s infinite;
}
.go {
  color: var(--accent);
  font-weight: 600;
}
@keyframes pulse {
  50% {
    opacity: 0.4;
  }
}
</style>
