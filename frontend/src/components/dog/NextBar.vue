<script setup lang="ts">
/** One fixed-height line: what to press next, or why buttons are grey, with a one-click fix (ui-design.md 5.4, 5.9). */
import AppIcon from '@/components/common/AppIcon.vue'
import type { NextStep } from './dogFlow'

defineProps<{ step: NextStep }>()
const emit = defineEmits<{ (e: 'fix', key: string): void }>()
</script>

<template>
  <div class="next" :class="step.cls" data-test="dog-next">
    <AppIcon :name="step.icon ?? (step.cls === 'bad' || step.cls === 'warn' ? 'alert' : 'info')" :size="16" />
    <span class="t" :title="step.text">{{ step.text }}</span>
    <button v-if="step.fix" class="btn btn-sm" :class="step.fix.danger ? 'btn-danger' : ''" data-test="dog-next-fix" @click="emit('fix', step.fix.key)">
      {{ step.fix.label }}
    </button>
  </div>
</template>

<style scoped>
.next {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 46px;
  padding: 0 8px;
  border-radius: var(--r-ctl);
  border: 1px solid var(--border);
  background: var(--panel-2, var(--panel));
  font-size: var(--fs-sm);
  overflow: hidden;
}
.t {
  flex: 1;
  min-width: 0;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  line-height: 1.35;
}
.next .btn { flex: none; }
.ok { border-color: color-mix(in srgb, var(--ok) 50%, transparent); }
.ok :deep(svg) { color: var(--ok); }
.warn { border-color: color-mix(in srgb, var(--warn) 60%, transparent); background: color-mix(in srgb, var(--warn) 10%, var(--panel)); }
.warn :deep(svg) { color: var(--warn); }
.bad { border-color: color-mix(in srgb, var(--danger) 60%, transparent); background: color-mix(in srgb, var(--danger) 10%, var(--panel)); }
.bad :deep(svg) { color: var(--danger); }
.run { border-color: var(--accent); background: color-mix(in srgb, var(--accent) 10%, var(--panel)); }
.run :deep(svg) { color: var(--accent); }
</style>
