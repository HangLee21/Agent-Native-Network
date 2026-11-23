<script setup lang="ts">
/** The scripted messages between A, B and the dog, as a running log (newest at the bottom, kept in view). */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { t, tb } from '@/i18n'
import { useDemoStore } from './useDemoStore'
import { COLORS, type EventKind } from './demoApi'

const props = withDefaults(defineProps<{ kinds?: EventKind[]; showTime?: boolean }>(), {
  kinds: () => ['STAGE', 'COMM', 'TARGET', 'COMMAND', 'INFO', 'WARN'],
  showTime: true,
})
const demo = useDemoStore()
const list = ref<HTMLDivElement | null>(null)
/** Follow the newest message unless someone scrolled up to read older ones. */
let stick = true
let observer: ResizeObserver | null = null

const items = computed(() => demo.events.filter((e) => props.kinds.includes(e.kind)).slice(-120))

function partyColor(p: string | null): string {
  if (p === 'A') return COLORS.A
  if (p === 'B') return COLORS.B
  if (p === tb('狗')) return COLORS.dog
  return '#94a3b8'
}

function clock(ts: number): string {
  const start = demo.state?.startedAt || ts
  const s = Math.max(0, Math.round((ts - start) / 1000))
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
}

function toBottom(smooth: boolean): void {
  const el = list.value
  if (el && stick) el.scrollTo({ top: el.scrollHeight, behavior: smooth ? 'smooth' : 'auto' })
}

function onScroll(): void {
  const el = list.value
  if (el) stick = el.scrollHeight - el.scrollTop - el.clientHeight < 40
}

watch(
  () => items.value.length,
  async () => {
    await nextTick()
    toBottom(true)
  },
)

onMounted(() => {
  toBottom(false)
  // the panel shrinks when the dog card appears: keep the newest message visible
  observer = new ResizeObserver(() => toBottom(false))
  if (list.value) observer.observe(list.value)
})
onBeforeUnmount(() => observer?.disconnect())
</script>

<template>
  <div ref="list" class="log scroll" @scroll.passive="onScroll">
    <div v-if="items.length === 0" class="empty">{{ t('还没有通信') }}</div>
    <template v-for="e in items" :key="e.id">
      <div v-if="e.kind === 'STAGE'" class="stage"><span>{{ e.text }}</span></div>
      <div v-else class="msg" :class="e.kind.toLowerCase()">
        <span v-if="props.showTime" class="t num">{{ clock(e.ts) }}</span>
        <span v-if="e.from" class="who">
          <b :style="{ color: partyColor(e.from) }">{{ e.from }}</b>
          <template v-if="e.to"><i>→</i><b :style="{ color: partyColor(e.to) }">{{ e.to }}</b></template>
        </span>
        <span class="text">{{ e.text }}</span>
      </div>
    </template>
  </div>
</template>

<style scoped>
.log {
  height: 100%;
  overflow-y: auto;
  padding: 6px 2px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.empty {
  margin: auto;
  color: var(--text-dim);
  font-size: var(--fs-sm);
}
.stage {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #cbd5e1;
  font-size: var(--fs-xs);
  font-weight: 600;
  letter-spacing: 0.04em;
}
.stage::before,
.stage::after {
  content: '';
  flex: 1;
  height: 1px;
  background: rgba(148, 163, 184, 0.3);
}
.msg {
  display: grid;
  grid-template-columns: auto auto 1fr;
  align-items: baseline;
  gap: 8px;
  padding: 6px 10px;
  border-radius: 8px;
  background: rgba(30, 41, 59, 0.65);
  border-left: 3px solid transparent;
  font-size: var(--fs-sm);
  line-height: 1.45;
  animation: msg-in 0.35s ease-out;
}
.msg.comm {
  border-left-color: #e2e8f0;
}
.msg.target {
  border-left-color: #f43f5e;
}
.msg.command {
  border-left-color: #4ade80;
}
.msg.command .text {
  font-family: var(--font-num);
}
.msg.warn {
  border-left-color: var(--warn);
}
.msg.info {
  opacity: 0.75;
}
.t {
  color: #64748b;
  font-size: var(--fs-xs);
}
.who {
  white-space: nowrap;
  font-size: var(--fs-xs);
}
.who i {
  margin: 0 3px;
  color: #64748b;
  font-style: normal;
}
.text {
  color: #e2e8f0;
}
@keyframes msg-in {
  from {
    opacity: 0;
    transform: translateY(6px);
  }
}
</style>
