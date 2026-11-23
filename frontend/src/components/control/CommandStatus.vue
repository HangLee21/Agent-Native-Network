<script setup lang="ts">
/** Three-state command feedback (ui-design.md §5): sent / device confirmed / failed (+ rejected, timeout, pending). */
import { computed } from 'vue'
import AppIcon from '@/components/common/AppIcon.vue'
import { STATUS_TEXT, type CommandRecord } from '@/api/control'
import { t, tb } from '@/i18n'

const props = defineProps<{ record: CommandRecord | null; compact?: boolean }>()
const meta = computed(() => {
  switch (props.record?.status) {
    case 'PENDING': return { icon: 'clock', cls: 'warn' }
    case 'SENT': return { icon: 'spinner', cls: 'dim' }
    case 'ACKED': return { icon: 'check', cls: 'ok' }
    case 'TIMEOUT': return { icon: 'clock', cls: 'warn' }
    case 'REJECTED': return { icon: 'shield', cls: 'bad' }
    case 'FAILED': return { icon: 'x', cls: 'bad' }
    default: return null
  }
})
const text = computed(() => {
  const r = props.record
  if (!r) return ''
  const base = STATUS_TEXT[r.status]
  // the backend's timeout message already says so; in English it arrives translated (tb gives the same text)
  const saysTimeout = (m: string) => m.startsWith('超时') || m.startsWith(tb('超时')) // i18n-ignore
  return (r.status === 'FAILED' || r.status === 'REJECTED' || r.status === 'TIMEOUT') && r.message && !saysTimeout(r.message)
    ? t('{status}：{message}', { status: base, message: r.message })
    : r.status === 'TIMEOUT' && r.message ? r.message : base
})
</script>

<template>
  <div v-if="record && meta" class="cmd-status" :class="[meta.cls, { compact }]" :data-status="record.status" :title="text">
    <AppIcon :name="meta.icon" :size="14" />
    <span class="txt">{{ text }}</span>
  </div>
</template>

<style scoped>
.cmd-status {
  display: flex;
  align-items: flex-start;
  gap: 5px;
  font-size: var(--fs-xs);
  line-height: 1.35;
}
.cmd-status :deep(svg) {
  margin-top: 1px;
}
.compact .txt {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.ok { color: var(--ok); }
.warn { color: var(--warn); }
.bad { color: var(--danger); }
.dim { color: var(--text-dim); }
</style>
