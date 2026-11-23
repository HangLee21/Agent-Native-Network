<script setup lang="ts">
/**
 * One group of the Lite3 area (ui-design.md 20.3): a fixed-height title row that folds and unfolds the group. Folded,
 * the title is followed by a one-line summary (cut short, full text on hover); unfolded, the summary is left out
 * because the content is right below. Only a click on the title folds or unfolds a group; the choice is kept per
 * browser. Nothing here reacts to the dog's state, so no group opens or closes by itself.
 */
import { ref, watch } from 'vue'
import AppIcon from '@/components/common/AppIcon.vue'

const props = withDefaults(defineProps<{ id: string; title: string; summary?: string; summaryCls?: string; defaultOpen?: boolean }>(), { defaultOpen: true })

const KEY = `uav.dog.section.${props.id}`
function readOpen(): boolean {
  try {
    const v = localStorage.getItem(KEY)
    return v == null ? props.defaultOpen : v === '1'
  } catch {
    return props.defaultOpen
  }
}
const open = ref(readOpen())
watch(open, (v) => {
  try {
    localStorage.setItem(KEY, v ? '1' : '0')
  } catch {
    /* storage unavailable: the choice lasts until the page is left */
  }
})
const el = ref<HTMLElement | null>(null)
defineExpose({ el, open })
</script>

<template>
  <section ref="el" class="dsec" :class="{ open }" :data-test="`dog-sec-${id}`">
    <button class="dsh" :aria-expanded="open" @click="open = !open">
      <AppIcon :name="open ? 'down' : 'chevron'" :size="13" class="chev" />
      <span class="ttl">{{ title }}</span>
      <span v-if="!open && summary" class="sum" :class="summaryCls" :title="summary" data-test="dog-sec-summary">{{ summary }}</span>
    </button>
    <div v-if="open" class="dsb"><slot /></div>
  </section>
</template>

<style scoped>
.dsec { border-top: 1px solid var(--border); }
.dsh {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  height: 32px;
  padding: 0 2px;
  border: none;
  background: transparent;
  color: var(--text);
  font: inherit;
  text-align: left;
  cursor: pointer;
}
.dsh:hover .ttl { color: var(--accent); }
.dsh:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
.chev { flex: none; color: var(--text-dim); }
.ttl { flex: none; font-weight: 600; font-size: var(--fs-sm); }
.sum {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-dim);
  font-size: var(--fs-xs);
  font-variant-numeric: tabular-nums;
}
.sum.warnc { color: var(--warn); }
.sum.run { color: var(--accent); }
.dsb { padding: 0 2px 8px; }
</style>
