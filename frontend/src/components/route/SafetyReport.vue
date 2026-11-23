<script setup lang="ts">
/** Live safety-layer result for the edited route (S-01, S-02). */
import AppIcon from '@/components/common/AppIcon.vue'
import type { SafetyCheckResult } from '@/api/safety'
import { useEditorStore } from '@/stores/editor'
import { t } from '@/i18n'

defineProps<{ result: SafetyCheckResult | null; checking: boolean; error: string | null }>()
const ed = useEditorStore()
</script>

<template>
  <div class="report" data-test="safety-report">
    <div v-if="error" class="line warn"><AppIcon name="alert" :size="16" />{{ t('安全检查暂不可用：{error}', { error }) }}</div>
    <div v-else-if="!result" class="line dim"><AppIcon :name="checking ? 'spinner' : 'shield'" :size="16" />{{ checking ? t('正在进行安全检查…') : t('添加航点后自动进行安全检查') }}</div>
    <template v-else>
      <div class="line" :class="result.passed ? 'ok' : 'bad'">
        <AppIcon :name="result.passed ? 'shield' : 'alert'" :size="16" />
        <b>{{ result.passed ? t('安全检查通过') : t('安全检查未通过（{n} 项）', { n: result.violations.length }) }}</b>
        <AppIcon v-if="checking" name="spinner" :size="14" class="dim" />
      </div>
      <ul v-if="!result.passed" class="list">
        <li v-for="(v, i) in result.violations" :key="i">
          <button v-if="v.waypointIndex !== null" class="link" @click="ed.selected = v.waypointIndex">{{ v.message }}</button>
          <span v-else>{{ v.message }}</span>
        </li>
      </ul>
    </template>
  </div>
</template>

<style scoped>
.report {
  font-size: var(--fs-sm);
}
.line {
  display: flex;
  align-items: center;
  gap: 6px;
}
.line.ok {
  color: var(--ok);
}
.line.bad {
  color: var(--danger);
}
.line.warn {
  color: var(--warn);
}
.list {
  margin: 6px 0 0;
  padding-left: 20px;
  max-height: 120px;
  overflow: auto;
  color: var(--text);
}
.link {
  background: none;
  border: none;
  padding: 0;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
  text-decoration: underline dotted;
}
</style>
