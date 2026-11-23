<script setup lang="ts">
/**
 * Frame of one task card in the monitor's task area (ui-design.md §2.2): 返回 always at the top left,
 * then the title and state. While the card's task moves the aircraft, 返回 is locked and says why.
 */
import { computed } from 'vue'
import AppIcon from '@/components/common/AppIcon.vue'
import { useTasksStore, type TaskKey } from '@/stores/tasks'
import { t } from '@/i18n'

const props = defineProps<{ task: TaskKey; title: string; icon: string; state?: string }>()
const tasks = useTasksStore()
const locked = computed(() => tasks.isRunning(props.task))
</script>

<template>
  <section class="task-card" :class="{ running: locked }" :aria-label="title" :data-test="`task-card-${task}`">
    <header class="head">
      <button class="btn btn-sm back" :disabled="locked" :title="locked ? t('进行中：先用底部红色「停止」结束') : t('返回任务列表')" data-test="task-back" @click="tasks.back()">
        <AppIcon name="left" :size="14" />{{ t('返回') }}
      </button>
      <AppIcon :name="icon" :size="17" class="ic" />
      <b class="title">{{ title }}</b>
      <span v-if="state" class="state">{{ state }}</span>
    </header>
    <p v-if="locked" class="locked">{{ t('进行中：要换任务直接点上面的任务；要结束用底部红色「停止」。') }}</p>
    <slot />
  </section>
</template>

<style scoped>
.task-card {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  padding: 10px var(--sp-3) var(--sp-3);
  border-radius: var(--r-panel);
  border: 1px solid var(--border);
  background: var(--panel-2);
}
.task-card.running {
  border-color: var(--accent);
}
.head {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}
.back {
  flex: none;
  min-height: 28px;
  padding: 0 8px 0 4px;
  gap: 2px;
}
.ic {
  color: var(--accent);
}
.title {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.state {
  flex: none;
  font-size: var(--fs-xs);
  font-weight: 700;
  color: var(--accent);
}
.locked {
  margin: 0;
  font-size: var(--fs-xs);
  color: var(--text-dim);
}
</style>
