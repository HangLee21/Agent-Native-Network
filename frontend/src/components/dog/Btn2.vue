<script setup lang="ts">
/** Button with a plain main label and the dog side's own name below it in small print. Grey buttons say why on hover. */
defineProps<{ main: string; sub?: string; reason?: string | null; kind?: '' | 'primary' | 'danger' | 'warn' }>()
const emit = defineEmits<{ (e: 'click'): void }>()
</script>

<template>
  <button class="btn btn2" :class="kind ? `btn-${kind}` : ''" :disabled="!!reason" :title="reason ?? ''" @click="emit('click')">
    <span>{{ main }}</span><small v-if="sub">{{ sub }}</small>
  </button>
</template>

<style scoped>
.btn2 {
  flex-direction: column;
  gap: 0;
  min-height: 40px;
  padding: 4px 12px;
  line-height: 1.2;
}
.btn2 small {
  font-size: 11px;
  opacity: 0.7;
  font-weight: 400;
}
</style>
