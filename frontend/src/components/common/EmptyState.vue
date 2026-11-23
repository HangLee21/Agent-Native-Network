<script setup lang="ts">
import AppIcon from './AppIcon.vue'

defineProps<{ icon?: string; title: string; hint?: string }>()
</script>

<template>
  <div class="empty">
    <AppIcon :name="icon ?? 'info'" :size="28" />
    <div class="title">{{ title }}</div>
    <div v-if="hint" class="hint">{{ hint }}</div>
    <div class="actions"><slot /></div>
  </div>
</template>

<style scoped>
.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--sp-2);
  padding: var(--sp-5) var(--sp-4);
  color: var(--text-dim);
  text-align: center;
}
.title {
  color: var(--text);
  font-weight: 600;
}
.hint {
  font-size: var(--fs-sm);
  max-width: 320px;
}
.actions {
  display: flex;
  gap: var(--sp-2);
  margin-top: var(--sp-2);
}
.actions:empty {
  display: none;
}
</style>
