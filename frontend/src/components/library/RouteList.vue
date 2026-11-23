<script setup lang="ts">
/**
 * Route library inside the planning page's left panel (R-07, merged from the separate library page on 2026-11-04):
 * search, import, open for editing, show on the map next to the edited route (eye), and per-route actions.
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import AppIcon from '@/components/common/AppIcon.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import ImportDialog from './ImportDialog.vue'
import { useRoutesStore } from '@/stores/routes'
import { useRouteOverlaysStore } from '@/stores/routeOverlays'
import { useToastStore } from '@/stores/toast'
import { useConfirmStore } from '@/stores/confirm'
import { useExecutionStore } from '@/stores/execution'
import { syncApi } from '@/api/execution'
import { SOURCE_LABELS, type RouteSummary } from '@/api/routes'
import { ApiError } from '@/api/http'
import { dateTime, meters } from '@/utils/format'
import { t } from '@/i18n'

const props = defineProps<{ editingId?: string | null }>()
const emit = defineEmits<{
  (e: 'open', id: string): void
  (e: 'new'): void
  (e: 'execute', id: string): void
  (e: 'sync', id: string): void
  (e: 'deleted', id: string): void
}>()

const routes = useRoutesStore()
const ov = useRouteOverlaysStore()
const toast = useToastStore()
const confirm = useConfirmStore()
const execution = useExecutionStore()
const router = useRouter()
const query = ref('')
const menuFor = ref<string | null>(null)
/** The menu is fixed to the viewport so the scrolling list does not clip it; opens upwards near the bottom. */
const menuPos = ref<Record<string, string>>({})

function toggleMenu(id: string, e: MouseEvent): void {
  if (menuFor.value === id) {
    menuFor.value = null
    return
  }
  const r = (e.currentTarget as HTMLElement).getBoundingClientRect()
  const right = `${Math.max(8, window.innerWidth - r.right)}px`
  menuPos.value = r.bottom + 280 > window.innerHeight
    ? { right, bottom: `${window.innerHeight - r.top + 4}px` }
    : { right, top: `${r.bottom + 4}px` }
  menuFor.value = id
}
const showImport = ref(false)

const filtered = computed(() => {
  const q = query.value.trim().toLowerCase()
  return q ? routes.list.filter((r) => r.name.toLowerCase().includes(q)) : routes.list
})

function syncText(r: RouteSummary): { text: string; cls: string } {
  if (r.sync.synced && r.sync.syncedVersion === r.version) return { text: t('已同步'), cls: 'ok' }
  if (r.sync.synced) return { text: t('有更新未同步'), cls: 'warn' }
  return { text: t('未同步'), cls: 'dim' }
}

function closeMenu(e: MouseEvent): void {
  if (!(e.target as HTMLElement).closest?.('.menu-wrap')) menuFor.value = null
}

onMounted(() => {
  void routes.refresh()
  document.addEventListener('click', closeMenu)
})
onBeforeUnmount(() => document.removeEventListener('click', closeMenu))
watch(() => routes.list, (l) => ov.sync(l))

async function remove(r: RouteSummary): Promise<void> {
  menuFor.value = null
  const ok = await confirm.ask({ title: t('删除航线'), message: t('确认删除「{name}」？此操作不可撤销。', { name: r.name }), confirmText: t('删除'), danger: true, focus: 'cancel' })
  if (!ok) return
  try {
    await routes.remove(r.id)
    ov.forget(r.id)
    emit('deleted', r.id)
    toast.push('ok', t('已删除「{name}」', { name: r.name }))
  } catch (e) {
    toast.push('danger', e instanceof ApiError ? e.message : t('删除失败'))
  }
}

async function duplicate(r: RouteSummary): Promise<void> {
  menuFor.value = null
  try {
    await routes.duplicate(r.id)
    toast.push('ok', t('已复制「{name}」', { name: r.name }))
  } catch (e) {
    toast.push('danger', e instanceof ApiError ? e.message : t('复制失败'))
  }
}

function act(kind: 'execute' | 'sync', id: string): void {
  menuFor.value = null
  if (kind === 'execute') emit('execute', id)
  else emit('sync', id)
}

async function imported(id: string): Promise<void> {
  showImport.value = false
  toast.push('ok', t('航线已导入'))
  await routes.refresh()
  emit('open', id)
}

defineExpose({ openImport: () => (showImport.value = true) })
</script>

<template>
  <div class="route-list" data-test="route-list">
    <div class="tools">
      <input v-model="query" class="input search" :placeholder="t('搜索航线名称')" data-test="route-search" />
      <button class="btn btn-sm" :title="t('导入 KMZ / GeoJSON / CSV 航线文件')" data-test="open-import" @click="showImport = true"><AppIcon name="upload" :size="15" />{{ t('导入') }}</button>
    </div>
    <p v-if="routes.list.length" class="hint dim"><AppIcon name="eye" :size="14" />{{ t('打开眼睛：编辑另一条航线时在地图上一起显示（虚线）') }}</p>
    <div class="rows scroll" data-test="route-table" @scroll="menuFor = null">
      <div v-if="routes.loading && !routes.loaded" class="state dim"><AppIcon name="spinner" />{{ t('正在加载航线…') }}</div>
      <div v-else-if="routes.error" class="state error">
        <AppIcon name="alert" />{{ t('加载失败：{reason}', { reason: routes.error }) }}
        <button class="btn btn-sm" @click="routes.refresh()">{{ t('重试') }}</button>
      </div>
      <EmptyState v-else-if="routes.list.length === 0" icon="library" :title="t('还没有航线')" :hint="t('新建航线后在地图上单击选点；也可以导入 KMZ / GeoJSON / CSV 文件。')">
        <button class="btn btn-primary" data-test="new-route" @click="emit('new')"><AppIcon name="plus" />{{ t('新建航线') }}</button>
        <button class="btn" @click="showImport = true"><AppIcon name="upload" />{{ t('导入文件') }}</button>
      </EmptyState>
      <EmptyState v-else-if="filtered.length === 0" icon="info" :title="t('没有匹配的航线')" />
      <template v-else>
        <div v-for="r in filtered" :key="r.id" class="row-item" :class="{ editing: r.id === props.editingId }" :data-route="r.id">
          <button class="btn btn-ghost btn-sm btn-icon eye" :class="{ on: ov.isShown(r.id) }" :style="ov.isShown(r.id) ? { color: ov.colorOf(r.id)! } : {}"
                  :disabled="r.id === props.editingId" :aria-pressed="ov.isShown(r.id)"
                  :title="r.id === props.editingId ? t('正在编辑，已在地图上') : ov.isShown(r.id) ? t('不在地图上显示') : t('在地图上一起显示')"
                  data-test="overlay-toggle" @click="ov.toggle(r.id)">
            <AppIcon :name="ov.isShown(r.id) || r.id === props.editingId ? 'eye' : 'eye-off'" :size="16" />
          </button>
          <button class="main" :title="t('打开「{name}」编辑', { name: r.name })" data-test="open-route" @click="emit('open', r.id)">
            <span class="name">
              <i v-if="ov.isShown(r.id) && r.id !== props.editingId" class="swatch" :style="{ background: ov.colorOf(r.id)! }" />
              <span class="nm">{{ r.name }}</span>
              <span v-if="r.id === props.editingId" class="tag">{{ t('正在编辑') }}</span>
              <span class="sync" :class="syncText(r).cls">{{ syncText(r).text }}</span>
            </span>
            <span class="meta num">{{ t('{n} 点 · {len} · 最高 {h} m', { n: r.waypointCount, len: meters(r.lengthMeters), h: r.maxHeight }) }}</span>
          </button>
          <div class="menu-wrap">
            <button class="btn btn-ghost btn-sm btn-icon" :title="t('更多操作')" :aria-expanded="menuFor === r.id" data-test="route-menu"
                    @click="toggleMenu(r.id, $event)"><AppIcon name="more" :size="16" /></button>
            <div v-if="menuFor === r.id" class="menu panel" role="menu" :style="menuPos">
              <div class="menu-meta dim num">{{ SOURCE_LABELS[r.source] }} · v{{ r.version }} · {{ dateTime(r.updatedAt) }}</div>
              <button role="menuitem" :disabled="execution.active" data-test="library-execute" @click="act('execute', r.id)"><AppIcon name="play" :size="15" />{{ t('执行') }}</button>
              <button role="menuitem" :disabled="execution.busy" data-test="library-sync" @click="act('sync', r.id)"><AppIcon name="sync" :size="15" />{{ t('同步到遥控器') }}</button>
              <a role="menuitem" :href="syncApi.kmzUrl(r.id)" download @click="menuFor = null"><AppIcon name="download" :size="15" />{{ t('下载 KMZ') }}</a>
              <button role="menuitem" @click="duplicate(r)"><AppIcon name="copy" :size="15" />{{ t('复制') }}</button>
              <button role="menuitem" data-test="route-history" @click="router.push({ path: '/history', query: { route: r.id } })"><AppIcon name="clock" :size="15" />{{ t('历史飞行') }}</button>
              <button role="menuitem" class="danger" data-test="delete-route" @click="remove(r)"><AppIcon name="trash" :size="15" />{{ t('删除') }}</button>
            </div>
          </div>
        </div>
      </template>
    </div>
    <ImportDialog v-if="showImport" @done="imported" @cancel="showImport = false" />
  </div>
</template>

<style scoped>
.route-list {
  display: flex;
  flex-direction: column;
  min-height: 0;
  flex: 1;
}
.tools {
  display: flex;
  gap: var(--sp-2);
  padding: var(--sp-3) var(--sp-4) var(--sp-2);
}
.search {
  flex: 1;
  min-width: 0;
}
.hint {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0;
  padding: 0 var(--sp-4) var(--sp-2);
  font-size: var(--fs-xs);
}
.rows {
  flex: 1;
  min-height: 0;
  border-top: 1px solid var(--border);
}
.row-item {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px var(--sp-2) 4px var(--sp-3);
  border-bottom: 1px solid var(--border);
}
.row-item:hover {
  background: var(--panel-2);
}
.row-item.editing {
  background: color-mix(in srgb, var(--accent) 14%, transparent);
}
.eye,
.menu-wrap > .btn {
  width: 32px;
  flex: none;
}
.eye {
  color: var(--text-dim);
}
.eye.on {
  opacity: 1;
}
.main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  padding: 4px 2px;
  background: none;
  border: none;
  color: var(--text);
  font: inherit;
  text-align: left;
  cursor: pointer;
}
.name {
  display: flex;
  align-items: baseline;
  gap: 6px;
  width: 100%;
  font-weight: 600;
}
.nm {
  min-width: 0;
  overflow-wrap: anywhere; /* a long name wraps instead of being cut off */
}
.sync {
  margin-left: auto;
  flex: none;
  font-size: var(--fs-xs);
  font-weight: 400;
}
.sync.dim {
  color: var(--text-dim);
}
.swatch {
  width: 14px;
  height: 3px;
  flex: none;
}
.meta {
  font-size: var(--fs-xs);
  color: var(--text-dim);
}
.ok {
  color: var(--ok);
}
.warn {
  color: var(--warn);
}
.menu-wrap {
  position: relative;
}
.menu {
  position: fixed;
  z-index: 1200;
  min-width: 180px;
  padding: 4px;
  display: flex;
  flex-direction: column;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.45);
}
.menu-meta {
  padding: 4px 8px 6px;
  font-size: var(--fs-xs);
  border-bottom: 1px solid var(--border);
  margin-bottom: 4px;
}
.menu button,
.menu a {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border: none;
  border-radius: var(--r-ctl);
  background: none;
  color: var(--text);
  font: inherit;
  font-size: var(--fs-sm);
  text-align: left;
  text-decoration: none;
  cursor: pointer;
}
.menu button:hover:not(:disabled),
.menu a:hover {
  background: var(--panel-2);
}
.menu button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.menu .danger {
  color: var(--danger);
}
.state {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  padding: var(--sp-4);
}
.error {
  color: var(--danger);
}
</style>
