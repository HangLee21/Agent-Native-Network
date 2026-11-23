<script setup lang="ts">
import { computed } from 'vue'
import { useTelemetryStore } from '@/stores/telemetry'
import { modeLabel, num } from '@/utils/format'
import { t } from '@/i18n'

const tel = useTelemetryStore()
const dr = computed(() => tel.drone)
</script>

<template>
  <div class="mini panel" data-test="mini-telemetry">
    <div class="row head">
      <span class="chip" :class="tel.online ? 'ok' : 'danger'"><span class="dot" />{{ tel.online ? t('已连接') : t('未连接') }}</span>
      <span class="dim">{{ tel.online ? modeLabel(dr?.modeCode) : '—' }}</span>
    </div>
    <div class="grid num">
      <span class="dim">{{ t('相对高度') }}</span><span>{{ tel.online ? num(dr?.relativeHeight, 1, 'm') : '—' }}</span>
      <span class="dim">{{ t('电量') }}</span><span>{{ tel.online && dr?.batteryPercent != null ? dr.batteryPercent + ' %' : '—' }}</span>
      <span class="dim">{{ t('位置') }}</span><span>{{ dr?.lat != null ? `${dr.lat.toFixed(6)}, ${dr.lon?.toFixed(6)}` : '—' }}</span>
    </div>
  </div>
</template>

<style scoped>
.mini {
  width: 260px;
  padding: var(--sp-3);
  box-shadow: var(--shadow);
  font-size: var(--fs-sm);
}
.head {
  justify-content: space-between;
  margin-bottom: var(--sp-2);
}
.grid {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 2px var(--sp-3);
}
.grid span:nth-child(even) {
  text-align: right;
}
</style>
