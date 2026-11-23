<script setup lang="ts">
/**
 * Side panel collapsed to a narrow rail (ui-design.md §2.2), for the largest map / video: the selected drone's stop
 * for the running task, then every drone's own block with its phase, control, numbers and safety buttons — return
 * home / take-off and press-and-hold emergency stop stay available for both drones while the panel is collapsed.
 */
import { computed } from 'vue'
import AppIcon from '@/components/common/AppIcon.vue'
import RailDrone from './RailDrone.vue'
import { useTelemetryStore } from '@/stores/telemetry'
import { useTasksStore } from '@/stores/tasks'
import { useFleetStore } from '@/stores/fleet'
import { t } from '@/i18n'

const emit = defineEmits<{ (e: 'expand'): void }>()
const fleet = useFleetStore()
const tel = useTelemetryStore()
const tasks = useTasksStore()
const many = computed(() => fleet.drones.length > 1)
const showStop = computed(() => tel.airborne || !tasks.stopPlan.idle)
</script>

<template>
  <div class="rail" :class="{ many }" data-test="monitor-rail">
    <button class="btn btn-icon sq" :aria-label="t('展开侧栏')" :title="t('展开侧栏')" data-test="panel-expand" @click="emit('expand')"><AppIcon name="panel-open" :size="16" /></button>
    <button v-if="showStop" class="act stop" :class="{ hot: !tasks.stopPlan.idle }" :aria-label="tasks.stopPlan.label" :title="tasks.stopPlan.label"
            data-test="rail-stop" @click="tasks.stop(tasks.stopPlan.key)">
      <AppIcon name="stop" :size="16" />{{ t('停止') }}<span v-if="many">{{ fleet.label(tel.sn) }}</span>
    </button>
    <span class="grow" />
    <div class="drones" data-test="rail-drones">
      <RailDrone v-for="d in fleet.enabled" :key="d.gatewaySn" :device="d" :selected="d.gatewaySn === fleet.selectedSn" />
    </div>
  </div>
</template>

<style scoped>
.rail {
  height: 100%;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: var(--sp-3) 0;
  overflow-y: auto;
}
.rail.many {
  padding: 8px 6px;
}
.drones {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.sq {
  width: 44px;
  min-height: 36px;
}
.act {
  width: 100%;
  max-width: 56px;
  min-height: 50px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  border-radius: var(--r-ctl);
  font: inherit;
  font-size: 10.5px;
  font-weight: 700;
  cursor: pointer;
}
.act.stop {
  border: 1px solid color-mix(in srgb, var(--danger) 55%, transparent);
  background: transparent;
  color: var(--danger);
}
.act.stop.hot {
  border: 2px solid var(--danger);
  background: color-mix(in srgb, var(--danger) 18%, transparent);
  color: var(--text);
}
</style>
