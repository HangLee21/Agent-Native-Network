<script setup lang="ts">
/** Command receipts list (S-03). */
import { computed } from 'vue'
import CommandStatus from './CommandStatus.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import { useControlStore } from '@/stores/control'
import { time } from '@/utils/format'
import { t } from '@/i18n'

const props = withDefaults(defineProps<{ limit?: number }>(), { limit: 8 })
const control = useControlStore()
const items = computed(() => control.commands.slice(0, props.limit))
</script>

<template>
  <div class="log" data-test="command-log">
    <EmptyState v-if="items.length === 0" icon="info" :title="t('暂无指令')" />
    <div v-for="c in items" :key="c.id" class="item">
      <div class="head">
        <span class="label">{{ c.label }}</span>
        <span v-if="c.channel" class="tag">{{ c.channel === 'DRC' ? 'DRC' : c.channel === 'PROPERTY' ? t('属性') : t('服务') }}</span>
        <span class="t num dim">{{ time(c.createdAt) }}</span>
      </div>
      <CommandStatus :record="c" />
    </div>
  </div>
</template>

<style scoped>
.log {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.item {
  padding: 6px var(--sp-2);
  border-radius: var(--r-ctl);
  background: var(--panel-2);
}
.head {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: var(--fs-sm);
}
.label {
  font-weight: 600;
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.t {
  font-size: var(--fs-xs);
}
</style>
