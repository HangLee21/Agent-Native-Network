<script setup lang="ts">
/** One dog command and the dog's reply, in one line (ui-design.md section 8): facts only, no caveats. */
import { computed } from 'vue'
import AppIcon from '@/components/common/AppIcon.vue'
import type { DogCommand } from '@/api/dog'
import { t } from '@/i18n'

const props = defineProps<{ cmd: DogCommand; full?: boolean }>()

const STATES: Record<string, [string, string, string]> = {
  sent: ['spinner', 'dim', t('已发送，等狗回复…')],
  running: ['spinner', 'acc', t('狗已受理，执行中')],
  replied: ['check', 'ok', t('狗已回复')],
  done: ['check', 'ok', t('狗报告完成')],
  notdone: ['x', 'bad', t('狗报告未完成')],
  noflag: ['alert', 'warn', t('狗已返回，没有成功标志')],
  failed: ['x', 'bad', t('失败')],
  timeout: ['clock', 'warn', t('超时：狗没有回复')],
  lost: ['x', 'bad', t('狗那边找不到这个任务')],
  unknown: ['alert', 'warn', t('结果未知')],
  received: ['check', 'ok', t('狗已收到')],
  navstart: ['check', 'ok', t('导航已开始')],
  gripped: ['info', 'acc', t('夹爪停下')],
  stopped: ['stop', 'ok', t('已停止')],
  unconfirmed: ['alert', 'warn', t('未确认停止')],
  noreply: ['alert', 'warn', t('没收到回复')],
}
const st = computed<[string, string, string]>(() => STATES[props.cmd.state] ?? ['info', 'dim', props.cmd.state])
const why = computed(() => props.cmd.error ?? props.cmd.detail ?? '')
const showWhy = computed(() => ['notdone', 'failed', 'lost', 'unknown', 'gripped', 'unconfirmed', 'noflag', 'noreply'].includes(props.cmd.state) && !!why.value)
const time = computed(() => new Date(props.cmd.createdAt).toTimeString().slice(0, 8))
</script>

<template>
  <div class="cmd" :class="{ full }" data-test="dog-cmd">
    <span class="num dim">{{ time }}</span>
    <span class="l" :title="cmd.label">{{ cmd.label }}</span>
    <span class="s" :class="st[1]" :title="showWhy ? t('{label}：{why}', { label: st[2], why }) : st[2]">
      <AppIcon :name="st[0]" :size="13" />{{ showWhy ? t('{label}：{why}', { label: st[2], why }) : st[2] }}
    </span>
    <span v-if="full && cmd.detail && !showWhy" class="d dim" :title="cmd.detail">{{ cmd.detail }}</span>
  </div>
</template>

<style scoped>
.cmd {
  display: grid;
  grid-template-columns: 62px minmax(0, 0.9fr) minmax(0, 1.4fr);
  gap: 6px;
  align-items: center;
  height: 24px;
  font-size: var(--fs-xs);
}
.cmd.full {
  grid-template-columns: 62px minmax(0, 0.9fr) minmax(0, 1.4fr) minmax(0, 1.2fr);
}
.l, .s, .d {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.s { display: flex; align-items: center; gap: 3px; justify-content: flex-end; }
.full .s { justify-content: flex-start; }
.ok { color: var(--ok); }
.bad { color: var(--danger); }
.warn { color: var(--warn); }
.acc { color: var(--accent); }
</style>
