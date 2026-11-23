<script setup lang="ts">
/** A numbered step of a dog workflow: plain-language title, buttons, one sentence of explanation, "?" to the manual. */
import AppIcon from '@/components/common/AppIcon.vue'
import { t } from '@/i18n'

defineProps<{ n?: number | string; state?: 'done' | 'cur' | ''; title: string; help?: string }>()
const emit = defineEmits<{ (e: 'help', id: string): void }>()
</script>

<template>
  <div class="st2" :class="state">
    <span class="sn"><AppIcon v-if="state === 'done'" name="check" :size="13" /><template v-else>{{ n }}</template></span>
    <div class="body">
      <div class="stt">{{ title }}<button v-if="help" class="qm" :title="t('{title}是什么？', { title })" @click="emit('help', help)">?</button></div>
      <div v-if="$slots.default" class="ctl"><slot /></div>
      <p v-if="$slots.expl" class="expl"><slot name="expl" /></p>
    </div>
  </div>
</template>

<style scoped>
.st2 {
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr);
  gap: 10px;
  padding: 6px 0;
}
.sn {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  border: 1px solid var(--border);
  color: var(--text-dim);
}
.cur .sn { background: var(--accent); color: var(--accent-ink); border-color: var(--accent); }
.done .sn { background: var(--ok); color: #04130a; border-color: var(--ok); }
.stt { font-weight: 600; display: flex; align-items: center; gap: 6px; min-height: 22px; }
.ctl { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
.expl { margin: 6px 0 0; font-size: var(--fs-xs); color: var(--text-dim); line-height: 1.5; }
.qm {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text-dim);
  font-size: 11px;
  cursor: pointer;
  padding: 0;
}
</style>
