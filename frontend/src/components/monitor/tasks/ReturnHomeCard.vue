<script setup lang="ts">
/** Returning home (mode_code 9): distance to Home; 取消返航 is in the footer's main slot. */
import AppIcon from '@/components/common/AppIcon.vue'
import { useTelemetryStore } from '@/stores/telemetry'
import { meters } from '@/utils/format'
import { t } from '@/i18n'

const tel = useTelemetryStore()
</script>

<template>
  <section class="rth" :aria-label="t('返航中')" data-test="rth-card">
    <div class="head"><AppIcon name="home" :size="17" /><b>{{ t('返航中') }}</b><span class="num">{{ t('距 Home {d}', { d: meters(tel.drone?.homeDistance) }) }}</span></div>
    <p class="note">{{ t('到达 Home 点后自动降落。「取消返航」在底部同一位置，取消后飞机悬停；换其他任务会先问是否取消返航。') }}</p>
  </section>
</template>

<style scoped>
.rth {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px var(--sp-3);
  border-radius: var(--r-panel);
  border: 1px solid var(--warn);
  background: color-mix(in srgb, var(--warn) 10%, var(--panel-2));
}
.head {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--warn);
}
.head b {
  flex: 1;
  color: var(--text);
}
.head .num {
  color: var(--text);
  font-size: var(--fs-sm);
}
.note {
  margin: 0;
  font-size: var(--fs-xs);
  color: var(--text-dim);
}
</style>
