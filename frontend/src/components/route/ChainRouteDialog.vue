<script setup lang="ts">
/**
 * "接上另一条航线" (2026-11-04): copies a saved route's waypoints onto the end of the edited one. The leg between them
 * is an ordinary leg, optionally flown level at the higher of the two heights; hovers at both ends and a wait for the
 * operator at the other route's start are set here. A copy, not a link: later edits of that route do not follow.
 */
import { computed, onMounted, ref, watch } from 'vue'
import AppIcon from '@/components/common/AppIcon.vue'
import { routesApi, type Route } from '@/api/routes'
import { useRoutesStore } from '@/stores/routes'
import { TRANSIT_MIN_DIFF_M, useEditorStore } from '@/stores/editor'
import { ApiError } from '@/api/http'
import { distance } from '@/utils/geo'
import { meters } from '@/utils/format'
import { t } from '@/i18n'

const emit = defineEmits<{ (e: 'done', message: string): void; (e: 'cancel'): void }>()
const ed = useEditorStore()
const routes = useRoutesStore()
const query = ref('')
const pickedId = ref<string | null>(null)
const picked = ref<Route | null>(null)
const loadError = ref<string | null>(null)
const leaveHover = ref(0)
const arriveHover = ref(0)
const arriveWait = ref(false)
const levelTransit = ref(true)

const choices = computed(() => {
  const q = query.value.trim().toLowerCase()
  return routes.list.filter((r) => r.id !== ed.draft?.id && r.waypointCount > 0 && (!q || r.name.toLowerCase().includes(q)))
})
const last = computed(() => {
  const wps = ed.draft?.waypoints ?? []
  return wps[wps.length - 1] ?? null
})
const first = computed(() => picked.value?.waypoints[0] ?? null)
const gap = computed(() => (last.value && first.value ? distance(last.value, first.value) : null))
const diff = computed(() => (last.value && first.value ? first.value.relativeHeight - last.value.relativeHeight : 0))
const needsTransit = computed(() => Math.abs(diff.value) >= TRANSIT_MIN_DIFF_M && (gap.value ?? 0) > 1)
const transitText = computed(() => {
  if (!last.value || !first.value) return ''
  const hi = Math.max(last.value.relativeHeight, first.value.relativeHeight)
  return diff.value > 0
    ? t('在本航线末点正上方先升到 {hi} m，再平飞到起点', { hi })
    : t('以 {hi} m 平飞到起点正上方，再降到 {h} m', { hi, h: first.value.relativeHeight })
})

onMounted(() => {
  leaveHover.value = last.value?.hoverSeconds ?? 0
  if (!routes.loaded) void routes.refresh()
})

watch(pickedId, async (id) => {
  picked.value = null
  loadError.value = null
  if (!id) return
  try {
    const r = await routesApi.get(id)
    if (pickedId.value !== id) return
    picked.value = r
    arriveHover.value = r.waypoints[0]?.hoverSeconds ?? 0
    arriveWait.value = r.waypoints[0]?.waitForConfirm ?? false
  } catch (e) {
    loadError.value = e instanceof ApiError ? e.message : t('加载失败')
  }
})

function confirmChain(): void {
  const r = picked.value
  if (!r) return
  const res = ed.appendRoute(r, {
    leaveHover: Number(leaveHover.value) || 0,
    arriveHover: Number(arriveHover.value) || 0,
    arriveWait: arriveWait.value,
    levelTransit: levelTransit.value && needsTransit.value,
  })
  if (!res) return
  const firstOfRoute = res.from + (res.transit ? 1 : 0)
  emit('done', res.transit
    ? t('已接上「{name}」：航点 {a}–{b}（另加过渡点 {c}）。保存后才生效。', { name: r.name, a: firstOfRoute + 1, b: res.to + 1, c: res.from + 1 })
    : t('已接上「{name}」：航点 {a}–{b}。保存后才生效。', { name: r.name, a: firstOfRoute + 1, b: res.to + 1 }))
}
</script>

<template>
  <div class="backdrop" @click.self="emit('cancel')">
    <div class="dialog panel" role="dialog" aria-modal="true" :aria-label="t('接上另一条航线')" data-test="chain-dialog">
      <div class="panel-head"><span class="row"><AppIcon name="link" />{{ t('接上另一条航线') }}</span></div>
      <div class="panel-body">
        <p class="lead dim">{{ t('把另一条已保存航线的航点复制接到本航线末尾：飞完本航线后飞到它的起点，再按它飞。之后再改那条航线，这里不会跟着变。') }}</p>
        <input v-model="query" class="input" :placeholder="t('搜索航线名称')" />
        <div class="choices scroll" role="radiogroup" :aria-label="t('选择航线')">
          <p v-if="!choices.length" class="dim empty">{{ t('没有可以接的已保存航线') }}</p>
          <label v-for="r in choices" :key="r.id" class="choice" :class="{ on: pickedId === r.id }">
            <input v-model="pickedId" type="radio" :value="r.id" data-test="chain-choice" />
            <span class="grow">{{ r.name }}</span>
            <span class="dim num">{{ t('{n} 点 · {len}', { n: r.waypointCount, len: meters(r.lengthMeters) }) }}</span>
          </label>
        </div>
        <p v-if="loadError" class="bad">{{ loadError }}</p>
        <template v-if="picked && first && last">
          <p class="summary num" data-test="chain-summary">
            {{ t('本航线末点（航点 {n}）{h1} m → 「{name}」起点 {h2} m， 水平相距 {gap}', { n: ed.draft!.waypoints.length, h1: last.relativeHeight, name: picked.name, h2: first.relativeHeight, gap: meters(gap ?? 0) }) }}
          </p>
          <div class="grid">
            <label class="field"><span>{{ t('离开本航线末点前悬停 (s)') }}</span>
              <input v-model.number="leaveHover" class="input num" type="number" min="0" step="1" data-test="chain-leave-hover" /></label>
            <label class="field"><span>{{ t('到达它的起点后悬停 (s)') }}</span>
              <input v-model.number="arriveHover" class="input num" type="number" min="0" step="1" data-test="chain-arrive-hover" /></label>
          </div>
          <label class="opt">
            <input v-model="arriveWait" type="checkbox" data-test="chain-arrive-wait" />
            <span>{{ t('到达它的起点后悬停，等我确认再继续') }} <small class="dim">{{ t('（只在平台执行时有效）') }}</small></span>
          </label>
          <label v-if="needsTransit" class="opt">
            <input v-model="levelTransit" type="checkbox" data-test="chain-level" />
            <span>{{ t('高度不一样：{how}', { how: transitText }) }} <small class="dim">{{ t('（多加 1 个过渡点；不勾就斜着直线飞过去）') }}</small></span>
          </label>
        </template>
      </div>
      <div class="actions">
        <button class="btn" @click="emit('cancel')">{{ t('取消') }}</button>
        <button class="btn btn-primary" :disabled="!picked" data-test="chain-confirm" @click="confirmChain"><AppIcon name="link" />{{ t('接上') }}</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.55);
  z-index: 2400;
  display: flex;
  align-items: center;
  justify-content: center;
}
.dialog {
  width: 520px;
  max-width: calc(100vw - 32px);
  max-height: calc(100vh - 32px);
  display: flex;
  flex-direction: column;
  box-shadow: var(--shadow);
}
.panel-body {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  overflow: auto;
}
.lead {
  margin: 0;
  font-size: var(--fs-sm);
}
.choices {
  max-height: 200px;
  border: 1px solid var(--border);
  border-radius: var(--r-ctl);
}
.empty {
  margin: 0;
  padding: var(--sp-3);
  font-size: var(--fs-sm);
}
.choice {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  padding: 6px var(--sp-3);
  border-bottom: 1px solid var(--border);
  cursor: pointer;
  font-size: var(--fs-sm);
}
.choice:last-child {
  border-bottom: none;
}
.choice.on {
  background: color-mix(in srgb, var(--accent) 14%, transparent);
}
.choice .dim {
  font-size: var(--fs-xs);
}
.summary {
  margin: 0;
  font-size: var(--fs-sm);
}
.grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: var(--sp-2) var(--sp-3);
}
.grid .input {
  width: 100%;
  min-width: 0;
}
.opt {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: var(--fs-sm);
  cursor: pointer;
}
.opt input {
  margin-top: 3px;
  accent-color: var(--accent);
}
.bad {
  color: var(--danger);
  margin: 0;
}
.actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--sp-2);
  padding: var(--sp-3) var(--sp-4);
  border-top: 1px solid var(--border);
}
</style>
