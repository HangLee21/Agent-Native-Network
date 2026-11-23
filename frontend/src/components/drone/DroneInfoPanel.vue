<script setup lang="ts">
/** All available basic information in one place (R-05), grouped; raw fields expandable. */
import { computed, ref } from 'vue'
import { useTelemetryStore } from '@/stores/telemetry'
import { droneGroups, flattenRaw } from './infoFields'
import { time } from '@/utils/format'
import { t } from '@/i18n'

const props = withDefaults(defineProps<{ columns?: number }>(), { columns: 3 })
const tel = useTelemetryStore()
const showRaw = ref(false)
const groups = computed(() => droneGroups(tel.drone, tel.rc))
const rawRows = computed(() => [
  ...flattenRaw(tel.drone?.raw ?? {}).map((r) => ({ ...r, label: t('飞行器.{field}', { field: r.label }) })),
  ...flattenRaw(tel.rc?.raw ?? {}).map((r) => ({ ...r, label: t('遥控器.{field}', { field: r.label }) })),
])
</script>

<template>
  <div class="info" data-test="drone-info">
    <div class="meta dim">
      <span>{{ t('最后更新 {time}', { time: time(tel.lastUpdateAt) }) }}</span>
      <span v-if="!tel.online" class="stale">{{ t('数据非实时（设备未连接）') }}</span>
    </div>
    <div class="groups" :style="{ gridTemplateColumns: `repeat(${props.columns}, minmax(0, 1fr))` }">
      <section v-for="g in groups" :key="g.title" class="group">
        <h4 class="section-title">{{ g.title }}</h4>
        <dl>
          <template v-for="r in g.rows" :key="r.label">
            <dt :title="r.hint">{{ r.label }}<span v-if="r.hint" class="hint">ⓘ</span></dt>
            <dd class="num">{{ r.value }}</dd>
          </template>
        </dl>
      </section>
    </div>
    <button class="btn btn-sm btn-ghost raw-toggle" @click="showRaw = !showRaw">
      {{ showRaw ? t('收起全部原始字段') : t('展开全部原始字段（{n}）', { n: rawRows.length }) }}
    </button>
    <table v-if="showRaw" class="raw num">
      <tbody>
        <tr v-for="r in rawRows" :key="r.label">
          <td>{{ r.label }}</td>
          <td>{{ r.value }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.info {
  font-size: var(--fs-sm);
}
.meta {
  display: flex;
  gap: var(--sp-3);
  margin-bottom: var(--sp-3);
  font-size: var(--fs-xs);
}
.stale {
  color: var(--warn);
}
.groups {
  display: grid;
  gap: var(--sp-4);
}
dl {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 3px var(--sp-3);
  margin: 0;
}
dt {
  color: var(--text-dim);
  white-space: nowrap;
}
.hint {
  margin-left: 3px;
  font-size: 10px;
}
dd {
  margin: 0;
  text-align: right;
  overflow-wrap: anywhere;
}
.raw-toggle {
  margin-top: var(--sp-3);
}
.raw {
  width: 100%;
  border-collapse: collapse;
  margin-top: var(--sp-2);
  font-size: var(--fs-xs);
}
.raw td {
  padding: 2px 6px;
  border-bottom: 1px solid var(--border);
  overflow-wrap: anywhere;
}
.raw td:first-child {
  color: var(--text-dim);
  width: 45%;
}
</style>
