<script setup lang="ts">
/**
 * 演示与监视台 section: 「只显示已经飞过的轨迹」 (default on) and the order of the videos on the 监视台.
 * Saved at once; every open monitor screen follows (pushed as `monitor-settings`).
 */
import { computed } from 'vue'
import AppIcon from '@/components/common/AppIcon.vue'
import { useFleetStore } from '@/stores/fleet'
import type { WatchSettingsState } from './useWatchSettings'
import { t } from '@/i18n'

const props = defineProps<{ model: WatchSettingsState }>()
const fleet = useFleetStore()
const v = computed(() => props.model.value)

/** Registered drones in video order: the saved order first, the rest by name. */
const ordered = computed(() => {
  const order = v.value?.videoOrder ?? []
  const rank = (k: string) => { const i = order.indexOf(k); return i < 0 ? 1000 : i }
  return [...fleet.drones].sort((a, b) => rank(a.gatewaySn) - rank(b.gatewaySn) || a.label.localeCompare(b.label))
})
function move(i: number, d: -1 | 1): void {
  const keys = ordered.value.map((x) => x.gatewaySn)
  const j = i + d
  if (j < 0 || j >= keys.length) return
  ;[keys[i], keys[j]] = [keys[j]!, keys[i]!]
  void props.model.save({ videoOrder: keys })
}
</script>

<template>
  <section class="panel s-card" data-test="watch-settings" aria-labelledby="settings-watch-title">
    <div class="s-card-head"><h2 id="settings-watch-title">{{ t('只显示已经飞过的轨迹') }}</h2></div>
    <p v-if="model.error" class="err"><AppIcon name="alert" :size="15" />{{ model.error }}</p>
    <label class="sw">
      <input type="checkbox" role="switch" :checked="v?.hideRoute ?? true" :disabled="!v || model.saving" data-test="watch-hide-route"
        @change="model.save({ hideRoute: ($event.target as HTMLInputElement).checked })" />
      <span class="sw-track" aria-hidden="true"><span class="sw-knob" /></span>
      <span>{{ (v?.hideRoute ?? true) ? t('开启（默认）') : t('关闭') }}</span>
    </label>
    <p class="s-card-desc">{{ t('开启后，监视台上看不出飞机在按航线飞：') }}</p>
    <ul class="s-list">
      <li>{{ t('地图上不画计划航线和航点，也不画还没飞到的部分，只画飞过的实际轨迹。') }}</li>
      <li>{{ t('不出现航线名称、航点进度、航线完成与否，以及平台发出的航线指令。') }}</li>
      <li>{{ t('动态里只列飞机自己的状态变化：起飞、自动避障、返航、降落。') }}</li>
      <li>{{ t('回放也一样：轨迹、曲线和动态只到当前播放时刻，看上去和实时一样。') }}</li>
    </ul>
    <p class="s-card-desc">{{ t('关闭时：地图用虚线画计划航线和航点编号，卡片写航线和航点进度，动态列出全部指令和告警，回放时没飞到的部分淡色显示，适合自己复盘。') }}</p>
  </section>

  <section class="panel s-card" aria-labelledby="settings-watch-order">
    <div class="s-card-head"><h2 id="settings-watch-order">{{ t('视频顺序') }}</h2></div>
    <p class="s-card-desc">{{ t('监视台右侧从上到下按这个顺序排视频（三路以上时两列，从左到右）。机器狗接入后也会出现在这里。任何一路都可以在监视台上点放大，换到大画面。') }}</p>
    <ol class="order" data-test="watch-video-order">
      <li v-for="(d, i) in ordered" :key="d.gatewaySn">
        <span class="n num">{{ i + 1 }}</span>
        <span class="swc" :style="{ background: d.color }" />
        <b>{{ d.label }}</b>
        <span class="dim">{{ d.model ?? '' }}{{ d.enabled ? '' : ` · ${t('未启用')}` }}</span>
        <span class="grow" />
        <button class="btn btn-sm btn-icon" :disabled="i === 0 || model.saving" :aria-label="t('{name} 往前', { name: d.label })" @click="move(i, -1)"><AppIcon name="up" :size="14" /></button>
        <button class="btn btn-sm btn-icon" :disabled="i === ordered.length - 1 || model.saving" :aria-label="t('{name} 往后', { name: d.label })" @click="move(i, 1)"><AppIcon name="down" :size="14" /></button>
      </li>
      <li v-if="!ordered.length" class="dim">{{ t('还没有登记的设备') }}</li>
    </ol>
    <button v-if="v?.videoOrder.length" class="btn btn-sm" :disabled="model.saving" @click="model.save({ videoOrder: [] })">{{ t('恢复默认（按名称排）') }}</button>
  </section>
</template>

<style scoped>
.s-list { margin: 0; padding-left: 18px; color: var(--text-dim); font-size: var(--fs-sm); line-height: 1.7; }
.order { list-style: none; margin: 0; padding: 0; display: grid; gap: 6px; }
.order li { display: flex; align-items: center; gap: 8px; padding: 6px 8px; border: 1px solid var(--border); border-radius: var(--r-ctl); background: var(--panel-2); }
.n { width: 18px; color: var(--text-dim); }
.swc { width: 10px; height: 10px; border-radius: 2px; }
.grow { flex: 1; }
.dim { color: var(--text-dim); font-size: var(--fs-xs); }
</style>
