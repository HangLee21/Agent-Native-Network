<script setup lang="ts">
/**
 * Route execution (R-09). Shows the running/last execution (ExecutionProgress, stop in the footer) and,
 * when nothing runs, the saved routes with the same ExecuteDialog and execution.execute call as the
 * route list on the planning page.
 */
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import TaskCardShell from '../TaskCardShell.vue'
import ExecutionProgress from '@/components/route/ExecutionProgress.vue'
import ExecuteDialog from '@/components/route/ExecuteDialog.vue'
import type { ExecMode } from '@/api/execution'
import { useExecutionStore } from '@/stores/execution'
import { useRoutesStore } from '@/stores/routes'
import { meters } from '@/utils/format'
import { t } from '@/i18n'

const execution = useExecutionStore()
const routes = useRoutesStore()
const executeId = ref<string | null>(null)
const state = computed(() => (execution.active ? t('执行中') : ''))
const list = computed(() => routes.list.slice(0, 6))

onMounted(() => {
  if (!routes.loaded) void routes.refresh()
})

async function startExecution(mode: ExecMode, _sn: string, rthConfirmed: boolean): Promise<void> {
  const id = executeId.value
  executeId.value = null
  if (id) await execution.execute(id, mode, rthConfirmed)
}
</script>

<template>
  <TaskCardShell task="rte" :title="t('执行航线')" icon="route" :state="state">
    <ExecutionProgress v-if="execution.current" :show-stop="false" />
    <template v-if="!execution.active">
      <p class="txt dim">{{ t('选择已保存的航线。执行前的确认（安全检查、授权提示）与航线库相同。') }}</p>
      <p v-if="routes.loading && !routes.loaded" class="txt dim">{{ t('正在加载航线…') }}</p>
      <p v-else-if="!list.length" class="txt dim">{{ t('航线库为空，') }}<RouterLink to="/plan">{{ t('去规划页画一条') }}</RouterLink>{{ t('。') }}</p>
      <ul v-else class="routes">
        <li v-for="r in list" :key="r.id">
          <button class="route" :disabled="execution.active" :data-test="`route-run-${r.id}`" @click="executeId = r.id">
            <b>{{ r.name }}</b>
            <span class="dim num">{{ t('{n} 个航点 · {len} · 最高 {h} m', { n: r.waypointCount, len: meters(r.lengthMeters), h: Math.round(r.maxHeight) }) }}</span>
          </button>
        </li>
      </ul>
      <RouterLink class="more" to="/plan">{{ t('打开航线列表 →') }}</RouterLink>
    </template>
    <ExecuteDialog v-if="executeId" :route-id="executeId" :sn="execution.sn" @confirm="startExecution" @cancel="executeId = null" />
  </TaskCardShell>
</template>

<style scoped>
.txt {
  margin: 0;
  font-size: var(--fs-sm);
}
.routes {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.route {
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  padding: var(--sp-2) 10px;
  border-radius: var(--r-ctl);
  border: 1px solid var(--border);
  background: var(--panel);
  color: var(--text);
  font: inherit;
  text-align: left;
  cursor: pointer;
}
.route:hover:not(:disabled) {
  border-color: var(--accent);
}
.route span {
  font-size: var(--fs-xs);
}
.more {
  font-size: var(--fs-xs);
}
</style>
