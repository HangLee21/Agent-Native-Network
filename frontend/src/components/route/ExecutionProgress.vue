<script setup lang="ts">
/** Route execution progress in the monitor view (ui-design.md §7 "执行中"). */
import { computed } from 'vue'
import AppIcon from '@/components/common/AppIcon.vue'
import { STATE_TEXT } from '@/api/execution'
import { useExecutionStore } from '@/stores/execution'
import { useConfirmStore } from '@/stores/confirm'
import { time } from '@/utils/format'
import { t } from '@/i18n'

/** `showStop=false`: the flight monitor's safety footer owns the stop (same API and confirmation). */
const props = withDefaults(defineProps<{ showStop?: boolean }>(), { showStop: true })
const ex = useExecutionStore()
const confirm = useConfirmStore()
const s = computed(() => ex.current)
const pct = computed(() => (s.value && s.value.total ? Math.round((s.value.reachedCount / s.value.total) * 100) : 0))
const cls = computed(() => {
  switch (s.value?.state) {
    case 'COMPLETED': return 'ok'
    case 'FAILED':
    case 'ABORTED': return 'bad'
    case 'PAUSED': return 'paused'
    default: return 'run'
  }
})

async function stop(): Promise<void> {
  if (await confirm.ask({ title: t('停止执行'), message: t('将结束当前 flyto，飞机在当前位置悬停。确认停止？'), confirmText: t('停止'), danger: true, focus: 'confirm' })) {
    await ex.abort()
  }
}
</script>

<template>
  <div v-if="s" class="exec" :class="cls" data-test="execution">
    <div class="head">
      <b class="name">{{ s.routeName }}</b>
      <span class="state">{{ STATE_TEXT[s.state] }}</span>
    </div>
    <div class="bar"><span :style="{ width: pct + '%' }" /></div>
    <div class="meta num">
      <span>{{ t('已到达 {a}/{b}', { a: s.reachedCount, b: s.total }) }}</span>
      <span>{{ s.mode === 'STOP_AND_GO' ? t('逐点飞行') : t('途中更新') }}</span>
    </div>
    <p class="msg">{{ s.message }}</p>
    <div v-if="s.state === 'PAUSED'" class="paused-note" data-test="execution-paused">
      <AppIcon name="alert" :size="15" />
      <span v-if="s.pauseReason === 'PROXIMITY'">{{ t('因两机靠近，平台已让飞机悬停。拉开距离后再恢复；仍太近时恢复会被拒绝。') }}</span>
      <span v-else-if="s.pauseReason === 'WAYPOINT_CONFIRM'">{{ t('这个航点设了“到达后等待确认”，飞机悬停等你。确认后继续飞（两机太近时会被拒绝）。') }}</span>
      <span v-else>{{ t('航线已暂停，飞机悬停。') }}</span>
      <button class="btn btn-sm btn-primary" data-test="resume-execution" @click="ex.resume()">
        <AppIcon name="play" :size="15" />{{ s.pauseReason === 'WAYPOINT_CONFIRM' ? t('确认，继续航线') : t('继续航线') }}
      </button>
    </div>
    <button v-if="s.active && props.showStop" class="btn btn-danger btn-sm" data-test="abort-execution" @click="stop"><AppIcon name="stop" :size="15" />{{ t('停止执行') }}</button>
    <details>
      <summary>{{ t('执行记录（{n}）', { n: s.log.length }) }}</summary>
      <ul class="log">
        <li v-for="(l, i) in s.log.slice().reverse().slice(0, 30)" :key="i" :class="l.level === 'WARN' ? 'warn' : ''">
          <span class="num dim">{{ time(l.ts) }}</span> {{ l.text }}
        </li>
      </ul>
    </details>
  </div>
</template>

<style scoped>
.paused-note {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  border: 1px solid var(--warn);
  border-radius: var(--radius);
  color: var(--warn);
  font-size: var(--fs-sm);
}
.exec.paused {
  border-color: var(--warn);
}
.exec {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: var(--sp-3);
  border-radius: var(--r-panel);
  border: 1px solid var(--border);
  background: var(--panel-2);
}
.exec.run {
  border-color: var(--accent);
}
.exec.ok {
  border-color: var(--ok);
}
.exec.bad {
  border-color: var(--danger);
}
.head {
  display: flex;
  justify-content: space-between;
  gap: var(--sp-2);
}
.name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.state {
  font-size: var(--fs-sm);
  font-weight: 600;
}
.run .state { color: var(--accent); }
.ok .state { color: var(--ok); }
.bad .state { color: var(--danger); }
.bar {
  height: 6px;
  border-radius: 3px;
  background: var(--panel-3);
  overflow: hidden;
}
.bar span {
  display: block;
  height: 100%;
  background: var(--accent);
  transition: width 0.3s;
}
.ok .bar span { background: var(--ok); }
.meta {
  display: flex;
  justify-content: space-between;
  font-size: var(--fs-xs);
  color: var(--text-dim);
}
.msg {
  margin: 0;
  font-size: var(--fs-sm);
}
details {
  font-size: var(--fs-xs);
}
summary {
  cursor: pointer;
  color: var(--text-dim);
}
.log {
  list-style: none;
  margin: 4px 0 0;
  padding: 0;
  max-height: 160px;
  overflow: auto;
}
.log li {
  padding: 2px 0;
}
.log li.warn {
  color: var(--warn);
}
</style>
