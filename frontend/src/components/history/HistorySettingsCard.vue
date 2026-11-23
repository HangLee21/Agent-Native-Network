<script setup lang="ts">
/**
 * 飞行记录与录像 section of the settings page (D-19, D-20): recording status and the video recording switch.
 * Loading and the immediate save of the switch live in useHistorySettings (SettingsView owns it).
 */
import { computed } from 'vue'
import AppIcon from '@/components/common/AppIcon.vue'
import type { HistorySettings } from '@/components/settings/useHistorySettings'
import { bytes } from '@/utils/format'
import { t } from '@/i18n'

const props = defineProps<{ model: HistorySettings }>()
const status = computed(() => props.model.status)

const gb = (b: number | null | undefined) => (b == null ? '—' : `${(b / 1e9).toFixed(1)} GB`)
</script>

<template>
  <section class="panel s-card" data-test="history-settings" aria-labelledby="settings-history-title">
    <div class="s-card-head"><h2 id="settings-history-title">{{ t('记录与录像') }}</h2></div>
    <p v-if="model.error" class="err"><AppIcon name="alert" :size="15" />{{ model.error }}</p>
    <template v-else-if="status">
      <dl class="s-dl">
        <dt>{{ t('飞行记录') }}</dt>
        <dd>
          <span v-if="!status.recorder.enabled" class="dim">{{ t('已关闭（HISTORY_ENABLED=false）') }}</span>
          <span v-else-if="status.recorder.paused" class="warn">{{ t('暂停：{reason}（待写 {n} 条）', { reason: status.recorder.pausedMessage, n: status.recorder.pendingRows }) }}</span>
          <span v-else class="ok">{{ status.recorder.currentSessionId ? t('正常，正在记录本次飞行') : t('正常') }}</span>
        </dd>
        <dt>{{ t('已保存') }}</dt>
        <dd class="num">{{ t('{n} 次飞行 · {m} 条遥测', { n: status.sessions, m: status.samples }) }}<template v-if="status.videoBytes"> · {{ t('录像 {size}', { size: bytes(status.videoBytes) }) }}
          <span class="s-hint">{{ t('（在「记录」里可以只删录像、保留记录）') }}</span></template></dd>
        <dt>{{ t('录像') }}</dt>
        <dd class="video">
          <label class="sw">
            <input type="checkbox" role="switch" :checked="status.video.recordingEnabled" :disabled="model.saving" data-test="video-recording-toggle"
              @change="model.setVideo(($event.target as HTMLInputElement).checked)" />
            <span class="sw-track" aria-hidden="true"><span class="sw-knob" /></span>
            <span>{{ t('每次飞行录制直播视频（540P）') }}</span>
          </label>
          <span class="s-hint">{{ t('切换后立即保存，下次起飞生效') }}</span>
        </dd>
        <dt>{{ t('录像服务') }}</dt>
        <dd>
          <span v-if="!status.video.configured" class="warn">{{ t('未配置：需设置 VIDEO_PLAYBACK_URL（MediaMTX 回放服务），否则飞行记录中没有视频') }}</span>
          <span v-else>{{ status.video.transcode ? t('已配置，超过 540P 的录像会转码') : t('已配置，未配置 ffmpeg，按直播原码流保存') }}{{ status.video.autoStartStream ? t('；起飞时自动开启 540P 直播') : '' }}</span>
        </dd>
        <dt v-if="status.video.configured">{{ t('磁盘') }}</dt>
        <dd v-if="status.video.configured" :class="status.video.diskLow ? 'warn' : ''">{{ t('可用 {free}，低于 {min} 时停止录像', { free: gb(status.video.freeBytes), min: gb(status.video.minFreeBytes) }) }}</dd>
      </dl>
    </template>
    <p v-else class="dim">{{ t('正在加载…') }}</p>
  </section>
</template>

<style scoped>
.ok { color: var(--ok); }
.warn { color: var(--warn); }
.err {
  display: flex;
  gap: 6px;
  align-items: center;
  color: var(--danger);
  margin: 0;
}
.dim {
  margin: 0;
}
.video {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--sp-1) var(--sp-3);
  margin-top: -6px;
}
</style>
