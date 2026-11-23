<script setup lang="ts">
/**
 * Flight phase bar (ui-design.md §2.2): 连接 → 控制权 → 起飞 → 任务 → 返航, done green, current blue (amber when it
 * needs attention, e.g. a paused route). The current step says what is happening. `mini`: bars only, for the
 * fleet cards and the collapsed rail.
 */
import { useFlightPhase } from '@/composables/useFlightPhase'
import { useFleetStore } from '@/stores/fleet'
import { t } from '@/i18n'

const props = withDefaults(defineProps<{ sn: string; mini?: boolean }>(), { mini: false })
const { steps } = useFlightPhase(props.sn)
const fleet = useFleetStore()
</script>

<template>
  <ol class="steps" :class="{ mini }" :aria-label="fleet.drones.length > 1 ? t('{name} 的飞行阶段', { name: fleet.label(sn) }) : t('飞行阶段')" data-test="phase-bar">
    <li v-for="(s, i) in steps" :key="i":class="{ done: s.done, cur: s.cur, warn: s.warn }" :aria-current="s.cur ? 'step' : undefined"
        :title="mini && s.cur ? s.label : undefined">
      <span class="bar" /><span v-if="!mini" class="lbl">{{ s.label }}</span>
    </li>
  </ol>
</template>

<style scoped>
.steps {
  display: flex;
  gap: 4px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.steps li {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.bar {
  height: 5px;
  border-radius: 3px;
  background: var(--border);
}
.done .bar { background: var(--ok); }
.cur .bar { background: var(--accent); }
.cur.warn .bar { background: var(--warn); }
.lbl {
  font-size: 11.5px;
  color: var(--text-dim);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.cur .lbl {
  color: var(--text);
  font-weight: 700;
}
.cur.warn .lbl {
  color: var(--warn);
}
.mini {
  gap: 3px;
}
.mini .bar {
  height: 4px;
}
</style>
