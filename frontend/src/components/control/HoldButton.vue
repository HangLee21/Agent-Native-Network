<script setup lang="ts">
/** Press-and-hold trigger for the emergency stop (ui-design.md §5): fast, but resistant to accidental touches. */
import { onBeforeUnmount, ref } from 'vue'

const props = withDefaults(defineProps<{ holdMs?: number; disabled?: boolean }>(), { holdMs: 800, disabled: false })
const emit = defineEmits<{ (e: 'trigger'): void }>()
const progress = ref(0)
let start = 0
let raf = 0
let fired = false

function begin(e: Event): void {
  if (props.disabled) return
  e.preventDefault()
  start = performance.now()
  fired = false
  const step = (t: number): void => {
    progress.value = Math.min(1, (t - start) / props.holdMs)
    if (progress.value >= 1 && !fired) {
      fired = true
      emit('trigger')
      cancel()
      return
    }
    raf = requestAnimationFrame(step)
  }
  raf = requestAnimationFrame(step)
}

function cancel(): void {
  cancelAnimationFrame(raf)
  progress.value = 0
}

function onKey(e: KeyboardEvent): void {
  if ((e.key === ' ' || e.key === 'Enter') && !e.repeat) begin(e)
}

onBeforeUnmount(cancel)
</script>

<template>
  <button
    class="hold"
    :disabled="disabled"
    @pointerdown="begin"
    @pointerup="cancel"
    @pointerleave="cancel"
    @pointercancel="cancel"
    @keydown="onKey"
    @keyup="cancel"
    @contextmenu.prevent
  >
    <span class="fill" :style="{ transform: `scaleX(${progress})` }" />
    <span class="content"><slot /></span>
  </button>
</template>

<style scoped>
.hold {
  position: relative;
  overflow: hidden;
  width: 100%;
  min-height: 64px;
  border-radius: var(--r-panel);
  border: 2px solid var(--estop);
  background: var(--estop);
  color: #fff;
  font: inherit;
  font-size: 20px;
  font-weight: 800;
  letter-spacing: 0.2em;
  cursor: pointer;
  touch-action: none;
  user-select: none;
}
.hold:disabled {
  background: var(--panel-2);
  border-color: var(--border);
  color: var(--text-dim);
  cursor: not-allowed;
  letter-spacing: 0.05em;
  font-size: var(--fs-md);
}
.hold:focus-visible {
  outline: 3px solid #fff;
  outline-offset: 2px;
}
.fill {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.35);
  transform-origin: left;
  transform: scaleX(0);
}
.content {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--sp-2);
}
</style>
