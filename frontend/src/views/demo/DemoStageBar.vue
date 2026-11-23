<script setup lang="ts">
/** The five steps of the run: done / current / upcoming; ABORTED keeps the step where it stopped. */
import { computed } from 'vue'
import { useDemoStore } from './useDemoStore'
import { STEPS, stageIndex, type Stage } from './demoApi'

const props = withDefaults(defineProps<{ compact?: boolean }>(), { compact: false })
const demo = useDemoStore()

const current = computed<Stage>(() => {
  const s = demo.state
  if (!s) return 'READY'
  if (s.stage !== 'ABORTED') return s.stage
  const order: Stage[] = ['S4_GUIDE', 'S3_TARGET', 'S2_RESCAN', 'S1_RENDEZVOUS', 'S1_EXPLORE']
  return order.find((x) => s.stageAt[x] != null) ?? 'READY'
})

function status(stage: Stage): 'done' | 'now' | 'next' {
  const c = stageIndex(current.value)
  const i = stageIndex(stage)
  if (demo.state?.stage === 'DONE' || c > i) return 'done'
  return c === i ? 'now' : 'next'
}
</script>

<template>
  <ol class="steps" :class="{ compact: props.compact, aborted: demo.state?.stage === 'ABORTED' }">
    <li v-for="(s, i) in STEPS" :key="s.stage" :class="status(s.stage)">
      <span class="dot">{{ status(s.stage) === 'done' ? '✓' : i + 1 }}</span>
      <span class="name">{{ s.title }}</span>
    </li>
  </ol>
</template>

<style scoped>
.steps {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
}
li {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #64748b;
  font-weight: 600;
  white-space: nowrap;
}
li + li::before {
  content: '';
  width: 28px;
  height: 2px;
  margin-right: 4px;
  background: rgba(100, 116, 139, 0.5);
}
li.done + li::before,
li.now + li::before {
  background: #38bdf8;
}
.dot {
  display: grid;
  place-items: center;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  border: 2px solid currentColor;
  font: 700 13px var(--font-num);
}
li.done {
  color: #7dd3fc;
}
li.done .dot {
  background: #0c4a6e;
  border-color: #38bdf8;
}
li.now {
  color: #fff;
}
li.now .dot {
  background: #38bdf8;
  border-color: #38bdf8;
  color: #04202e;
  box-shadow: 0 0 0 4px rgba(56, 189, 248, 0.25);
  animation: now 1.6s ease-in-out infinite;
}
.aborted li.now .dot {
  background: var(--warn);
  border-color: var(--warn);
  animation: none;
}
.compact li + li::before {
  width: 12px;
}
.compact .dot {
  width: 20px;
  height: 20px;
  font-size: 11px;
}
.compact .name {
  font-size: var(--fs-xs);
}
@keyframes now {
  50% {
    box-shadow: 0 0 0 8px rgba(56, 189, 248, 0.08);
  }
}
</style>
