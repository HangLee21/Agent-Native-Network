<script setup lang="ts">
/**
 * Target selection section of the flight monitor (R-24 ~ R-27 draft): enter "Select target" on the video
 * or pick on the map, review AI proposals, act on the selected target, and AI auto mode.
 */
import { computed } from 'vue'
import AppIcon from '@/components/common/AppIcon.vue'
import TargetCard from './TargetCard.vue'
import AiAutoBar from './AiAutoBar.vue'
import { useTargetsStore } from '@/stores/targets'
import { useControlStore } from '@/stores/control'
import { useLiveStore } from '@/stores/live'
import { useTasksStore } from '@/stores/tasks'
import { STATE_LABELS } from '@/api/targets'
import { num } from '@/utils/format'
import { t } from '@/i18n'

/** `showAi=false`: the flight monitor shows AI auto mode in its own task card. */
withDefaults(defineProps<{ showAi?: boolean }>(), { showAi: true })
const targets = useTargetsStore()
const tasks = useTasksStore()
const control = useControlStore()
const live = useLiveStore()

const canSelect = computed(() => control.drcReady && !!live.status?.streaming)
const selectHint = computed(() => (!control.drcReady ? t('需要 DRC 链路（先获取控制权）') : !live.status?.streaming ? t('先开启视频') : ''))
const others = computed(() => targets.targets.filter((x) => x.id !== targets.selected?.id && !['CANCELLED', 'EXPIRED'].includes(x.state)).slice(0, 4))

function toggleSelect(): void {
  targets.selecting = !targets.selecting
}

function pickOnMap(): void {
  control.pickingTarget = 'target'
}
</script>

<template>
  <div class="panel-target" data-test="target-panel">
    <div class="row tools">
      <button class="btn btn-sm" :class="{ 'btn-primary': targets.selecting }" :disabled="!canSelect && !targets.selecting" :title="selectHint"
        data-test="target-select-toggle" @click="toggleSelect">
        <AppIcon name="crosshair" :size="14" />{{ targets.selecting ? t('退出选目标') : t('在视频中选目标') }}
      </button>
      <button class="btn btn-sm" :title="tasks.lookBlockedReason ?? t('在地图上单击设为目标')" :disabled="!!tasks.lookBlockedReason" data-test="target-map-pick" @click="pickOnMap"><AppIcon name="map" :size="14" />{{ t('地图选点') }}</button>
    </div>
    <p v-if="!canSelect && !targets.selecting" class="dim small">{{ selectHint }}</p>

    <div v-if="targets.proposals.length" class="proposals">
      <span class="dim small">{{ t('AI 建议（{n}）', { n: targets.proposals.length }) }}</span>
      <button v-for="p in targets.proposals" :key="p.id" class="btn btn-sm prop" :class="{ 'btn-warn': targets.selected?.id === p.id }"
        @click="targets.selectedId = p.id">
        {{ p.label ?? t('未命名') }}<span class="dim">{{ num(p.confidence, 2) }}</span>
      </button>
    </div>

    <TargetCard v-if="targets.selected" :target="targets.selected" />
    <p v-else class="dim small">{{ t('尚未选择目标。选目标只转动云台并测距，飞机不会移动。') }}</p>

    <div v-if="others.length" class="others">
      <button v-for="o in others" :key="o.id" class="other" @click="targets.selectedId = o.id">
        <span>{{ o.label ?? ({ TAP: t('点选'), CIRCLE: t('框选'), AI_BOX: 'AI', MAP: t('地图'), MODEL_3D: t('三维'), AI_GEO: 'AI' })[o.input] }}</span>
        <span class="dim">{{ o.distance != null ? `${num(o.distance, 0)} m` : '' }}</span>
        <span class="dim st">{{ STATE_LABELS[o.state] }}</span>
      </button>
      <button class="btn btn-ghost btn-sm" @click="targets.clearFinished()">{{ t('清除已结束') }}</button>
    </div>

    <AiAutoBar v-if="showAi" />
  </div>
</template>

<style scoped>
.panel-target {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}
.tools {
  gap: 6px;
}
.small {
  margin: 0;
  font-size: var(--fs-xs);
}
.proposals {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
}
.prop {
  gap: 4px;
}
.others {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.other {
  display: grid;
  grid-template-columns: 1fr 60px 60px;
  gap: 4px;
  padding: 4px 6px;
  border: none;
  border-radius: var(--r-ctl);
  background: none;
  color: var(--text);
  font: inherit;
  font-size: var(--fs-sm);
  text-align: left;
  cursor: pointer;
}
.other:hover {
  background: var(--panel-2);
}
.st {
  text-align: right;
}
</style>
