<script setup lang="ts">
/**
 * AI auto mode (R-27 draft, D-24): switched on per flight, off by default. Shows the levels in force, the
 * countdown of a pending automatic movement with a large Cancel, and "Stop AI" (off + stop any fly-to).
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import AppIcon from '@/components/common/AppIcon.vue'
import { useTargetsStore } from '@/stores/targets'
import { useConfirmStore } from '@/stores/confirm'
import { t, tc } from '@/i18n'

const targets = useTargetsStore()
const confirm = useConfirmStore()
const now = ref(Date.now())
let timer = 0
onMounted(() => (timer = window.setInterval(() => (now.value = Date.now()), 250)))
onBeforeUnmount(() => window.clearInterval(timer))

const ai = computed(() => targets.ai)
const levelText = (l: number | undefined) => (l === 2 ? t('自动（倒计时）') : l === 1 ? t('自动对准') : t('只建议'))
const remaining = computed(() => (ai.value?.countdown ? Math.max(0, Math.ceil((ai.value.countdown.deadline - now.value) / 1000)) : 0))
const anyAuto = computed(() => {
  const c = targets.config
  return !!c && (c.aiLookLevel > 0 || c.aiApproachLevel > 0 || c.aiAboveLevel > 0 || c.aiOrbitLevel > 0)
})

async function switchOn(): Promise<void> {
  const c = targets.config
  const ok = await confirm.ask({
    title: t('开启 AI 自动模式'),
    message: t('本次飞行中 AI 可按设置自动对准，或在倒计时后自动移动。确认开启？'),
    confirmText: tc('verb', '开启'),
    details: c ? [
      t('对准：{look}；接近：{approach}；上方：{above}；环绕：{orbit}', { look: levelText(c.aiLookLevel), approach: levelText(c.aiApproachLevel), above: levelText(c.aiAboveLevel), orbit: levelText(c.aiOrbitLevel) }),
      t('置信度 ≥ {conf}；单次移动 ≤ {move} m；停止距离 ≥ {stop} m；倒计时 {s} 秒', { conf: c.aiMinConfidence, move: c.aiMaxMoveM, stop: c.aiStopDistanceM, s: c.aiCountdownS }),
      t('禁止触发移动的标签：{labels}', { labels: c.aiForbiddenMoveLabels.join(t('、')) || t('无') }),
      t('失联、失去控制权、低电量、离开 AI 工作区时自动关闭；不会跨飞行保存'),
    ] : [],
  })
  if (ok) await targets.aiOn()
}
</script>

<template>
  <div class="ai" :class="{ on: ai?.on }" data-test="ai-auto">
    <div class="row head">
      <AppIcon name="eye" :size="15" />
      <b>{{ t('AI 自动模式') }}</b>
      <span class="chip" :class="ai?.on ? 'warn' : ''"><span class="dot" />{{ ai?.on ? t('已开启') : t('关闭') }}</span>
      <span class="grow" />
      <button v-if="!ai?.on" class="btn btn-sm" :disabled="!anyAuto || targets.busy" :title="anyAuto ? '' : t('在设置 → 目标选择中把至少一个动作设为自动')"
        data-test="ai-on" @click="switchOn">{{ tc('verb', '开启') }}</button>
      <button v-else class="btn btn-sm btn-danger" data-test="ai-stop" @click="targets.aiStop()"><AppIcon name="stop" :size="13" />{{ t('停止 AI') }}</button>
    </div>
    <p v-if="ai?.on" class="dim small">{{ t('对准 {look} · 接近 {approach} · 上方 {above} · 环绕 {orbit}', { look: levelText(ai.lookLevel), approach: levelText(ai.approachLevel), above: levelText(ai.aboveLevel), orbit: levelText(ai.orbitLevel) }) }}</p>
    <p v-else-if="ai?.offReason" class="dim small">{{ t('上次关闭：{reason}', { reason: ai.offReason }) }}</p>
    <div v-if="ai?.countdown" class="countdown" role="alert" data-test="ai-countdown">
      <div class="cd-text"><b>{{ ai.countdown.label }}</b><span>{{ t('{n} 秒后执行', { n: remaining }) }}</span></div>
      <button class="btn btn-lg btn-warn" data-test="ai-cancel" @click="targets.cancelCountdown()"><AppIcon name="x" />{{ t('取消') }}</button>
    </div>
  </div>
</template>

<style scoped>
.ai {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: var(--sp-2) var(--sp-3);
  border: 1px solid var(--border);
  border-radius: var(--r-ctl);
}
.ai.on {
  border-color: var(--warn);
  background: color-mix(in srgb, var(--warn) 8%, transparent);
}
.head {
  align-items: center;
  gap: 6px;
}
.small {
  margin: 0;
  font-size: var(--fs-xs);
}
.countdown {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  padding: var(--sp-2);
  border-radius: var(--r-ctl);
  background: color-mix(in srgb, var(--warn) 20%, var(--panel-2));
}
.cd-text {
  display: flex;
  flex-direction: column;
  flex: 1;
  font-size: var(--fs-sm);
}
</style>
