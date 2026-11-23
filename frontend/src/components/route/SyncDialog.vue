<script setup lang="ts">
/** Result of "sync to remote controller" (R-08) with the manual download step made explicit (DEV-02). */
import AppIcon from '@/components/common/AppIcon.vue'
import type { SyncResult } from '@/api/execution'
import { syncApi } from '@/api/execution'
import { dateTime } from '@/utils/format'
import { t } from '@/i18n'

defineProps<{ result: SyncResult }>()
const emit = defineEmits<{ (e: 'close'): void }>()
</script>

<template>
  <div class="backdrop" @click.self="emit('close')">
    <div class="dialog panel" role="dialog" aria-modal="true" :aria-label="t('已同步到遥控器')">
      <div class="panel-head"><span class="row ok"><AppIcon name="check" />{{ t('已同步到遥控器航线库') }}</span></div>
      <div class="panel-body">
        <dl class="num">
          <dt>{{ t('航线名称') }}</dt><dd>{{ result.waylineName }}</dd>
          <dt>{{ t('版本') }}</dt><dd>v{{ result.routeVersion }}</dd>
          <dt>{{ t('同步时间') }}</dt><dd>{{ dateTime(result.syncedAt) }}</dd>
          <dt>{{ t('文件') }}</dt><dd>{{ t('WPML 航线文件（KMZ，{kb} KB）', { kb: (result.sizeBytes / 1024).toFixed(1) }) }}</dd>
        </dl>
        <div class="step">
          <b>{{ t('下一步（飞手操作）') }}</b>
          <ol>
            <li>{{ t('在 DJI RC Plus 2 上打开 DJI Pilot 2 → 航线库；') }}</li>
            <li>{{ t('找到「{name}」，点击', { name: result.waylineName }) }}<b>{{ t('下载') }}</b>{{ t('（大疆限制：云端同步的航线需飞手手动下载）；') }}</li>
            <li>{{ t('在 Pilot 2 中检查并执行航线。') }}</li>
          </ol>
        </div>
        <ul v-if="result.warnings.length" class="warns">
          <li v-for="w in result.warnings" :key="w"><AppIcon name="alert" :size="14" />{{ w }}</li>
        </ul>
      </div>
      <div class="actions">
        <a class="btn" :href="syncApi.kmzUrl(result.routeId)" download><AppIcon name="download" />{{ t('下载 KMZ') }}</a>
        <button class="btn btn-primary" @click="emit('close')">{{ t('知道了') }}</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.55);
  z-index: 2400;
  display: flex;
  align-items: center;
  justify-content: center;
}
.dialog {
  width: 520px;
  max-width: calc(100vw - 32px);
  box-shadow: var(--shadow);
}
.ok {
  color: var(--ok);
}
dl {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 4px var(--sp-4);
  margin: 0 0 var(--sp-3);
  font-size: var(--fs-sm);
}
dt {
  color: var(--text-dim);
}
dd {
  margin: 0;
}
.step {
  padding: var(--sp-3);
  border-radius: var(--r-ctl);
  background: color-mix(in srgb, var(--accent) 10%, transparent);
  font-size: var(--fs-sm);
}
.step ol {
  margin: 6px 0 0;
  padding-left: 20px;
}
.warns {
  list-style: none;
  padding: 0;
  margin: var(--sp-3) 0 0;
  color: var(--warn);
  font-size: var(--fs-xs);
}
.warns li {
  display: flex;
  gap: 4px;
}
.actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--sp-2);
  padding: 0 var(--sp-4) var(--sp-4);
}
a.btn {
  text-decoration: none;
}
</style>
