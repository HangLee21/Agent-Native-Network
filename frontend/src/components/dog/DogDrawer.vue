
<script setup lang="ts">
/**
 * Details drawer of the operated dog (ui-design.md 5.6): topics and their ages, background jobs (this platform or
 * elsewhere), every command with the dog's reply, the raw state, and the link. The Lite3 access token is never in
 * any of it (the backend does not hand it out).
 */
import { computed, ref } from 'vue'
import CommandRow from './CommandRow.vue'
import { useDogStore } from '@/stores/dog'
import { jobLabel } from './dogFlow'
import type { DogId } from '@/api/dog'
import { t } from '@/i18n'

const props = defineProps<{ dog: DogId }>()
const store = useDogStore()
const tab = ref<'cmds' | 'jobs' | 'topics' | 'raw' | 'link'>('cmds')
const d = computed(() => store.dogs[props.dog])
/** Lite3: everything the platform has from the new dog system for this dog, as it came (ui-design.md 20.1). */
const raw = computed(() => JSON.stringify((props.dog === 'lite3' ? store.l3v2 : d.value) ?? {}, null, 2))
const topics = computed(() => {
  if (props.dog === 's10') {
    const tp = store.s10?.topics ?? {}
    return [
      [t('腕部相机 彩色'), tp.rgb?.age], [t('腕部相机 深度'), tp.depth?.age], [t('关节角'), tp.joints?.age], [t('运动状态'), tp.motion?.age],
      [t('累计地图点云'), tp.cloudMap?.age], [t('实时雷达'), tp.cloudRaw?.age],
    ] as [string, number | null | undefined][]
  }
  const v = store.l3v2
  const s = (ms: number | null | undefined) => (ms == null ? null : ms / 1000)
  return [[t('状态'), s(v?.statusAgeMs)], [t('遥测'), s(v?.telemetryAgeMs)], [t('运动主机状态包'), v?.status?.motion_host?.feedback_age_s],
    [t('GPS 位置'), s(v?.positionAgeMs)], [t('导航'), s(v?.nav?.ageMs)]] as [string, number | null | undefined][]
})
const fmt = (a: number | null | undefined) => (a == null ? t('没有数据') : t('{n} 秒（取数时）', { n: a.toFixed(1) }))
</script>

<template>
  <div class="ddrawer">
    <div class="tabs">
      <button :class="{ on: tab === 'cmds' }" @click="tab = 'cmds'">{{ t('指令') }}</button>
      <button v-if="dog === 's10'" :class="{ on: tab === 'jobs' }" @click="tab = 'jobs'">{{ t('后台任务') }}</button>
      <button :class="{ on: tab === 'topics' }" @click="tab = 'topics'">{{ t('话题更新时间') }}</button>
      <button :class="{ on: tab === 'raw' }" @click="tab = 'raw'">{{ t('原始返回') }}</button>
      <button :class="{ on: tab === 'link' }" @click="tab = 'link'">{{ t('链路') }}</button>
    </div>
    <div v-if="tab === 'cmds'" class="list">
      <CommandRow v-for="c in store.commands[dog]" :key="c.id" :cmd="c" full />
      <p v-if="!store.commands[dog].length" class="dim">{{ t('暂无指令') }}</p>
    </div>
    <table v-else-if="tab === 'jobs'" class="t"><tbody>
      <tr><th>{{ t('动作') }}</th><th>{{ t('状态') }}</th><th>{{ t('谁发起') }}</th><th>{{ t('进度 / 原因') }}</th></tr>
      <tr v-for="j in store.s10?.jobs ?? []" :key="j.id"><td>{{ jobLabel(j) }}</td><td>{{ j.state }}</td><td>{{ j.origin === 'platform' ? t('本平台') : t('别处（狗方网页等）') }}</td><td>{{ j.error ?? j.detail ?? '' }}</td></tr>
    </tbody></table>
    <table v-else-if="tab === 'topics'" class="t"><tbody>
      <tr><th>{{ t('数据') }}</th><th>{{ t('多久前') }}</th></tr>
      <tr v-for="[n, a] in topics" :key="n"><td>{{ n }}</td><td class="num">{{ fmt(a) }}</td></tr>
    </tbody></table>
    <pre v-else-if="tab === 'raw'" class="raw">{{ raw }}</pre>
    <table v-else class="t"><tbody>
      <tr><td>{{ t('链路') }}</td><td>{{ d?.link.state }}</td></tr>
      <tr><td>{{ t('往返耗时') }}</td><td class="num">{{ d?.link.rttMs ?? '—' }} ms</td></tr>
      <tr><td>{{ t('最近成功') }}</td><td class="num">{{ d?.link.lastOkAt ? new Date(d.link.lastOkAt).toLocaleTimeString() : t('尚未成功') }}</td></tr>
      <tr v-if="dog === 's10'"><td>{{ t('按住移动的时钟同步') }}</td><td>{{ store.s10?.link.clockOk ? t('正常') : t('过期（链路慢或断开）') }}</td></tr>
      <tr><td>{{ t('错误') }}</td><td>{{ d?.link.error ?? d?.link.tokenError ?? t('无') }}</td></tr>
    </tbody></table>
  </div>
</template>

<style scoped>
.ddrawer { display: flex; flex-direction: column; gap: 8px; min-height: 0; height: 100%; }
.tabs { display: flex; gap: 4px; flex: none; }
.tabs button { height: 28px; padding: 0 10px; border-radius: var(--r-ctl); border: 1px solid var(--border); background: transparent; color: var(--text); cursor: pointer; font: inherit; font-size: var(--fs-xs); }
.tabs button.on { background: var(--accent); color: var(--accent-ink); }
.list { overflow: auto; }
.raw { margin: 0; font-size: 11px; overflow: auto; background: #05090f; padding: 8px; border-radius: var(--r-ctl); }
.t { border-collapse: collapse; width: 100%; font-size: 12.5px; }
.t th { text-align: left; color: var(--text-dim); font-weight: 600; padding: 4px 8px; border-bottom: 1px solid var(--border); }
.t td { padding: 4px 8px; border-bottom: 1px solid color-mix(in srgb, var(--border) 60%, transparent); }
</style>
