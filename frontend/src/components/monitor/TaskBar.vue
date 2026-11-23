<script setup lang="ts">
/**
 * Task selector (ui-design.md §2.2): one task at a time. Large tiles when airborne and nothing is open,
 * a compact single-select bar otherwise. A green dot marks the task that is actually running.
 */
import { computed } from 'vue'
import AppIcon from '@/components/common/AppIcon.vue'
import { useTasksStore, MOTION_LABELS, type TaskKey } from '@/stores/tasks'
import { useTelemetryStore } from '@/stores/telemetry'
import { t } from '@/i18n'

defineProps<{ big?: boolean }>()
const tasks = useTasksStore()
const tel = useTelemetryStore()

const tiles = computed(() => {
  const air = tel.airborne
  const defs: { key: TaskKey; label: string; short: string; sub: string; icon: string; disabled: boolean; why: string }[] = [
    { key: 'fly', label: t('飞往地图点'), short: t('飞往'), sub: t('地图上点一下，飞到该点悬停'), icon: 'pin', disabled: !air, why: t('需在空中') },
    { key: 'orb', label: t('环绕兴趣点'), short: t('环绕'), sub: t('选中心，以当前距离为半径环绕'), icon: 'orbit', disabled: !air, why: t('需在空中') },
    { key: 'tgt', label: t('选择目标'), short: t('目标'), sub: t('视频点选 / 框选或地图选点；只测距，不移动'), icon: 'crosshair', disabled: false, why: '' },
    { key: 'rte', label: t('执行航线'), short: t('航线'), sub: t('从航线库选择；执行确认与规划页相同'), icon: 'route', disabled: false, why: '' },
    { key: 'stk', label: t('杆量控制'), short: t('杆量'), sub: t('屏幕摇杆或键盘，限制最大杆量'), icon: 'joystick', disabled: false, why: '' },
    { key: 'ai', label: t('AI 自动'), short: 'AI', sub: t('授权平台按 AI 建议自动对准或倒计时后移动'), icon: 'ai', disabled: false, why: '' },
  ]
  return defs.map((d) => {
    const pre = ['fly', 'orb', 'rte', 'stk'].includes(d.key) ? tasks.conflictFor(d.key) : null
    return {
      ...d,
      on: tasks.selected === d.key,
      running: tasks.isRunning(d.key),
      title: d.disabled ? d.why : pre ? t('当前正在{task}：点击后先确认停止，再开始', { task: MOTION_LABELS[pre] }) : d.label,
    }
  })
})
</script>

<template>
  <div v-if="big" class="big" role="group" :aria-label="t('选择任务')" data-test="task-launcher">
    <div class="big-head"><span class="section-title">{{ t('选择任务') }}</span><span class="dim small">{{ t('每张卡片左上角都有「返回」') }}</span></div>
    <div class="grid">
      <button v-for="tile in tiles" :key="tile.key" class="tile" :disabled="tile.disabled" :title="tile.title" :data-test="`task-${tile.key}`" @click="tasks.select(tile.key)">
        <AppIcon :name="tile.icon" :size="22" class="ic" />
        <b>{{ tile.label }}</b>
        <span class="sub">{{ tile.sub }}</span>
      </button>
    </div>
  </div>
  <div v-else class="bar" role="group" :aria-label="t('任务')" data-test="task-bar">
    <button v-for="tile in tiles" :key="tile.key" class="chipbtn" :class="{ on: tile.on }" :disabled="tile.disabled" :aria-pressed="tile.on" :title="tile.title"
      :data-test="`task-${tile.key}`" @click="tasks.select(tile.key)">
      <AppIcon :name="tile.icon" :size="18" />
      <span>{{ tile.short }}</span>
      <span v-if="tile.running" class="run-dot" :aria-label="t('运行中')" />
    </button>
  </div>
</template>

<style scoped>
.big {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}
.big-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}
.small {
  font-size: var(--fs-xs);
}
.grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--sp-2);
}
.tile {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
  min-height: 92px;
  padding: var(--sp-3);
  border-radius: var(--r-panel);
  border: 1px solid var(--border);
  background: var(--panel-2);
  color: var(--text);
  font: inherit;
  text-align: left;
  cursor: pointer;
}
.tile:hover:not(:disabled) {
  border-color: var(--accent);
}
.tile:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.tile .ic {
  color: var(--accent);
}
.sub {
  font-size: var(--fs-xs);
  color: var(--text-dim);
  line-height: 1.35;
}
.bar {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 4px;
}
.chipbtn {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  min-height: 50px;
  padding: 6px 0;
  border-radius: var(--r-ctl);
  border: 1px solid var(--border);
  background: var(--panel-2);
  color: var(--text-dim);
  font: inherit;
  font-size: 11px;
  cursor: pointer;
}
.chipbtn:hover:not(:disabled) {
  border-color: var(--accent);
  color: var(--text);
}
.chipbtn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.chipbtn.on {
  background: var(--accent);
  border-color: var(--accent);
  color: var(--accent-ink);
  font-weight: 700;
}
.run-dot {
  position: absolute;
  top: 4px;
  right: 5px;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--ok);
  box-shadow: 0 0 0 2px var(--panel);
}
</style>
