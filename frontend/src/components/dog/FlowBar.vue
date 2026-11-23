<script setup lang="ts">
/** Stage bar of a dog: where in its workflow it is (ui-design.md 5.4). Fixed height. */
import type { Seg } from './dogFlow'

defineProps<{ segs: Seg[] }>()
</script>

<template>
  <div class="flow" :style="{ gridTemplateColumns: `repeat(${segs.length}, 1fr)` }" data-test="dog-flow">
    <div v-for="(s, i) in segs" :key="i" :class="s.state" :title="s.title ?? s.label"><i /><span>{{ s.label }}</span></div>
  </div>
</template>

<style scoped>
.flow {
  display: grid;
  gap: 4px;
  height: 30px;
}
.flow > div {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
  font-size: var(--fs-xs);
  color: var(--text-dim);
}
.flow i {
  display: block;
  height: 4px;
  border-radius: 2px;
  background: var(--border);
}
.flow span {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.flow .done i { background: var(--ok); }
.flow .cur i { background: var(--accent); }
.flow .cur span { color: var(--accent); font-weight: 600; }
.flow .bad i { background: var(--danger); }
.flow .bad span { color: var(--danger); }
.flow .alt i { background: var(--warn); }
.flow .sent i { background: repeating-linear-gradient(90deg, var(--warn) 0 6px, transparent 6px 10px); }
.flow .sent span { color: var(--warn); }
</style>
