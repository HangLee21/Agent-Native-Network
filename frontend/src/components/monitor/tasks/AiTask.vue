<script setup lang="ts">
/**
 * AI auto mode (R-27 draft, D-23/D-24) in its own card: what switching it on means, the existing
 * AiAutoBar (on / stop / countdown cancel), and a link to pending AI proposals in the target card.
 */
import { computed } from 'vue'
import TaskCardShell from '../TaskCardShell.vue'
import AiAutoBar from '@/components/target/AiAutoBar.vue'
import { useTargetsStore } from '@/stores/targets'
import { useTasksStore, MOTION_LABELS } from '@/stores/tasks'
import { t } from '@/i18n'

const targets = useTargetsStore()
const tasks = useTasksStore()
const on = computed(() => !!targets.ai?.on)
const otherMotion = computed(() => (on.value && tasks.motion && tasks.motion !== 'tgt' ? MOTION_LABELS[tasks.motion] : null))
</script>

<template>
  <TaskCardShell task="ai" :title="t('AI 自动模式')" icon="ai" :state="on ? t('已开启') : t('关闭')">
    <ul class="explain">
      <li><b>{{ t('关闭（默认）：') }}</b>{{ t('外部 AI 只能提交目标建议，显示在「目标」里，需要你采纳或拒绝；飞机不会因为 AI 而动。') }}</li>
      <li><b>{{ t('开启：') }}</b>{{ t('授权平台按设置自动处理 AI 建议：自动对准测距，或倒计时后移动（可取消）；所有限制由服务器执行。') }}</li>
    </ul>
    <AiAutoBar />
    <p v-if="otherMotion" class="warn" data-test="ai-other-motion">{{ t('另有运动任务在进行（{task}）。后端目前不会因此阻止 AI 自动移动，请留意倒计时并及时取消。', { task: otherMotion }) }}</p>
    <button v-if="targets.proposals.length" class="btn btn-sm btn-warn" data-test="ai-proposals-link" @click="tasks.select('tgt')">
      {{ t('AI 建议 {n} 个：到「目标」里采纳或拒绝', { n: targets.proposals.length }) }}
    </button>
  </TaskCardShell>
</template>

<style scoped>
.explain {
  margin: 0;
  padding-left: 18px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: var(--fs-xs);
  color: var(--text-dim);
}
.explain b {
  color: var(--text);
}
.warn {
  margin: 0;
  font-size: var(--fs-xs);
  color: var(--warn);
}
.btn {
  align-self: flex-start;
}
</style>
