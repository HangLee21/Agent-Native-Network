<script setup lang="ts">
import { useRouter } from 'vue-router'
import AppIcon from './AppIcon.vue'
import { useToastStore, type Toast } from '@/stores/toast'

const toast = useToastStore()
const router = useRouter()

function act(t: Toast): void {
  toast.dismiss(t.id)
  if (t.action) void router.push(t.action.to)
}
const icons = { ok: 'check', warn: 'alert', danger: 'x', info: 'info' } as const
</script>

<template>
  <div class="toasts" aria-live="polite">
    <div v-for="t in toast.items" :key="t.id" class="toast" :class="t.kind" role="status" @click="toast.dismiss(t.id)">
      <AppIcon :name="icons[t.kind]" />
      <span>{{ t.text }}</span>
      <button v-if="t.action" class="btn btn-sm toast-action" @click.stop="act(t)">{{ t.action.label }}</button>
    </div>
  </div>
</template>

<style scoped>
.toasts {
  position: fixed;
  top: calc(var(--topbar-h) + 12px);
  left: 50%;
  transform: translateX(-50%);
  z-index: 3000;
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  pointer-events: none;
}
.toast {
  pointer-events: auto;
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  min-width: 280px;
  max-width: 560px;
  padding: var(--sp-2) var(--sp-4);
  border-radius: var(--r-ctl);
  background: var(--panel);
  border: 1px solid var(--border);
  border-left-width: 4px;
  box-shadow: var(--shadow);
  cursor: pointer;
}
.toast-action {
  margin-left: auto;
}
.toast.ok { border-left-color: var(--ok); }
.toast.warn { border-left-color: var(--warn); }
.toast.danger { border-left-color: var(--danger); }
.toast.info { border-left-color: var(--accent); }
</style>
