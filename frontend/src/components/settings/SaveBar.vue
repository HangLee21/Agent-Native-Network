<script setup lang="ts">
/** Sticky bar at the bottom of the settings content while the current section has unsaved changes. */
import { computed } from 'vue'
import { isEn, t } from '@/i18n'

const props = defineProps<{
  /** Section name, e.g. "飞行安全". */
  title: string
  names: string[]
  saveLabel: string
  saveTest: string
  dirty: boolean
  saving: boolean
}>()
defineEmits<{ (e: 'reset'): void; (e: 'save'): void }>()

/** "飞行安全有 2 项未保存" / "目标选择与 AI 有 2 项未保存" (space after a Latin word). */
const summary = computed(() => {
  const subject = !isEn() && /[A-Za-z0-9]$/.test(props.title) ? `${props.title} ` : props.title
  return props.names.length ? t('{title}有 {n} 项未保存', { title: subject, n: props.names.length }) : t('{title}有未保存的修改', { title: subject })
})
</script>

<template>
  <div class="save-bar" role="region" :aria-label="t('未保存的修改')" data-test="save-bar">
    <span class="dot" aria-hidden="true" />
    <span class="txt">
      <b>{{ summary }}</b>
      <span v-if="names.length" class="dim"> · {{ names.join(t('、')) }}</span>
    </span>
    <div class="row">
      <button type="button" class="btn" :disabled="!dirty" @click="$emit('reset')">{{ t('撤销修改') }}</button>
      <button type="button" class="btn btn-primary" :disabled="!dirty || saving" :data-test="saveTest" @click="$emit('save')">{{ saveLabel }}</button>
    </div>
  </div>
</template>

<style scoped>
.save-bar {
  position: sticky;
  bottom: 0;
  z-index: 10;
  flex: none;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--sp-2) var(--sp-3);
  padding: var(--sp-3) var(--sp-5);
  background: var(--panel-2);
  border-top: 1px solid var(--warn);
  box-shadow: 0 -6px 18px rgba(0, 0, 0, 0.25);
}
.dot {
  flex: none;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--warn);
}
.txt {
  flex: 1 1 240px;
  min-width: 0;
  font-size: var(--fs-sm);
}
.row {
  flex-wrap: wrap;
}
@media (max-width: 760px) {
  .save-bar {
    padding: var(--sp-3) var(--sp-4);
  }
}
</style>
