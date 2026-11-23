<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppIcon from '@/components/common/AppIcon.vue'
import MapCanvas from '@/components/map/MapCanvas.vue'
import FleetLayers from '@/components/map/FleetLayers.vue'
import LayerPanel from '@/components/map/LayerPanel.vue'
import RouteEditLayer from '@/components/map/RouteEditLayer.vue'
import RouteOverlayLayer from '@/components/map/RouteOverlayLayer.vue'
import RouteList from '@/components/library/RouteList.vue'
import { useRoutesStore } from '@/stores/routes'
import MiniTelemetry from '@/components/drone/MiniTelemetry.vue'
import RouteEditor from '@/components/route/RouteEditor.vue'
import SafetyReport from '@/components/route/SafetyReport.vue'
import { useRouteSafety } from '@/composables/useRouteSafety'
import { violationsOf } from '@/api/safety'
import ExecuteDialog from '@/components/route/ExecuteDialog.vue'
import SyncDialog from '@/components/route/SyncDialog.vue'
import { useExecutionStore } from '@/stores/execution'
import { useFleetStore } from '@/stores/fleet'
import type { ExecMode, SyncResult } from '@/api/execution'
import { useEditorStore } from '@/stores/editor'
import { useToastStore } from '@/stores/toast'
import { useConfirmStore } from '@/stores/confirm'
import { useTelemetryStore } from '@/stores/telemetry'
import { ApiError } from '@/api/http'
import type { LatLon } from '@/utils/coord'
import { t, tc } from '@/i18n'

const ed = useEditorStore()
const toast = useToastStore()
const confirm = useConfirmStore()
const tel = useTelemetryStore()
const route = useRoute()
const router = useRouter()
const safetyCheck = useRouteSafety()
/** Points to fit the map to: set when a route is opened (not on every edit). */
const fitPoints = ref<LatLon[] | null>(null)
const execution = useExecutionStore()
const fleet = useFleetStore()
const routes = useRoutesStore()
/** Route the execute dialog is open for (the edited one, or one from the list). */
const executeId = ref<string | null>(null)
const syncResult = ref<SyncResult | null>(null)

async function sync(id: string): Promise<void> {
  const r = await execution.sync(id)
  if (r) {
    syncResult.value = r
    void routes.refresh()
  }
}

async function syncToRc(): Promise<void> {
  if (!ed.draft?.id || ed.dirty) {
    toast.push('warn', t('请先保存航线，再同步到遥控器'))
    return
  }
  await sync(ed.draft.id)
}

/** The chosen drone executes (D-31); it becomes the selected one so the monitor shows it. */
async function startExecution(mode: ExecMode, sn: string, rthConfirmed: boolean): Promise<void> {
  const id = executeId.value
  executeId.value = null
  if (id && (await useExecutionStore(sn).execute(id, mode, rthConfirmed))) {
    fleet.select(sn)
    void router.push('/monitor')
  }
}

function openExecute(): void {
  if (!ed.draft?.id || ed.dirty) {
    toast.push('warn', t('请先保存航线，再执行'))
    return
  }
  executeId.value = ed.draft.id
}

/** Unsaved edits are dropped only after the operator agrees. */
async function mayDiscard(): Promise<boolean> {
  return !ed.dirty || confirm.ask({ title: t('放弃修改？'), message: t('当前航线有未保存的修改，离开后将丢失。'), confirmText: t('放弃修改'), danger: true })
}

async function openRoute(id: string): Promise<void> {
  if (id === ed.draft?.id) return
  if (!(await mayDiscard())) return
  ed.close()
  void router.replace({ query: { route: id } })
}

async function newRoute(): Promise<void> {
  if (!(await mayDiscard())) return
  ed.startNew()
  void router.replace({ query: {} })
}

function deleted(id: string): void {
  if (ed.draft?.id === id) {
    ed.close()
    void router.replace({ query: {} })
  }
}

async function openFromQuery(): Promise<void> {
  const id = route.query.route
  if (typeof id === 'string' && id && id !== ed.draft?.id) {
    try {
      await ed.open(id)
      fitPoints.value = ed.points.slice()
    } catch (e) {
      toast.push('danger', e instanceof ApiError ? e.message : t('加载航线失败'))
    }
  }
}

onMounted(openFromQuery)
watch(() => route.query.route, openFromQuery)

function onMapClick(p: LatLon): void {
  if (ed.editing) ed.addPoint(p)
}

async function save(): Promise<void> {
  if (!ed.draft) return
  if (!ed.draft.name.trim()) {
    toast.push('warn', t('请先填写航线名称'))
    return
  }
  if (ed.draft.waypoints.length === 0) {
    toast.push('warn', t('航线至少需要 1 个航点'))
    return
  }
  try {
    const r = await ed.save()
    toast.push('ok', t('已保存「{name}」', { name: r.name }))
    void routes.refresh()
    if (route.query.route !== r.id) void router.replace({ query: { route: r.id } })
  } catch (e) {
    if (e instanceof ApiError && e.status === 422) {
      const v = violationsOf(e.details)
      toast.push('danger', t('安全检查未通过，未保存：{reason}', { reason: v[0]?.message ?? e.message }), 6000)
      void safetyCheck.run()
    } else {
      toast.push('danger', e instanceof ApiError ? t('保存失败：{reason}', { reason: e.message }) : t('保存失败'))
    }
  }
}

async function closeEditor(): Promise<void> {
  if (!(await mayDiscard())) return
  ed.close()
  void router.replace({ query: {} })
}
</script>

<template>
  <div class="plan">
    <aside class="editor panel">
      <div class="panel-head">
        <button v-if="ed.editing" class="back" :title="t('回到航线列表')" data-test="back-to-list" @click="closeEditor">
          <AppIcon name="left" :size="18" />{{ t('航线列表') }}
        </button>
        <span v-else>{{ tc('plural', '航线') }}</span>
        <button class="btn btn-sm" :title="t('新建航线')" data-test="new-route-head" @click="newRoute"><AppIcon name="plus" :size="15" />{{ t('新建') }}</button>
      </div>
      <RouteList v-if="!ed.editing" :editing-id="null" @open="openRoute" @new="newRoute" @execute="executeId = $event" @sync="sync" @deleted="deleted" />
      <RouteEditor v-else :invalid="safetyCheck.invalid.value" @open-library="closeEditor">
        <template #checks>
          <SafetyReport :result="safetyCheck.result.value" :checking="safetyCheck.checking.value" :error="safetyCheck.error.value" />
        </template>
        <template #footer>
          <div class="row">
            <button class="btn btn-primary grow" :disabled="ed.saving || safetyCheck.result.value?.passed === false"
              :title="safetyCheck.result.value?.passed === false ? t('安全检查未通过，不能保存') : ''" data-test="save-route" @click="save">
              <AppIcon :name="ed.saving ? 'spinner' : 'save'" />{{ ed.draft?.id ? t('保存修改') : t('保存航线') }}
            </button>
          </div>
          <div class="row">
            <button class="btn grow" :disabled="!ed.draft?.id || ed.dirty || execution.busy || safetyCheck.result.value?.passed === false" data-test="sync-route" :title="t('生成 WPML 航线文件并发布到 Pilot 2 航线库')" @click="syncToRc">
              <AppIcon name="sync" />{{ t('同步到遥控器') }}
            </button>
            <button class="btn btn-warn grow" :disabled="!ed.draft?.id || ed.dirty || execution.active || safetyCheck.result.value?.passed === false" data-test="execute-route" @click="openExecute">
              <AppIcon name="play" />{{ execution.active ? t('有航线正在执行') : t('执行航线') }}
            </button>
          </div>
          <p v-if="ed.dirty && ed.draft?.id" class="hint-small">{{ t('有未保存的修改：保存后才能同步或执行。') }}</p>
        </template>
      </RouteEditor>
    </aside>
    <section class="map-area" :class="{ editing: ed.editing }" :aria-label="t('地图')">
      <MapCanvas :center="ed.points[0] ?? tel.position" :fit="fitPoints" @map-click="onMapClick">
        <FleetLayers :show-route="false" />
        <RouteOverlayLayer />
        <RouteEditLayer :invalid="safetyCheck.invalid.value" />
      </MapCanvas>
      <div class="float-tr"><LayerPanel /></div>
      <div class="float-br"><MiniTelemetry /></div>
    </section>
    <ExecuteDialog v-if="executeId" :route-id="executeId" @confirm="startExecution" @cancel="executeId = null" />
    <SyncDialog v-if="syncResult" :result="syncResult" @close="syncResult = null" />
  </div>
</template>

<style scoped>
.plan {
  display: grid;
  grid-template-columns: 380px 1fr;
  /* the row must not grow with the editor's content, or its bottom is cut off instead of scrolling */
  grid-template-rows: minmax(0, 1fr);
  height: 100%;
}
.editor {
  border-radius: 0;
  border-width: 0 1px 0 0;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}
.map-area {
  position: relative;
  min-width: 0;
}
.back {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 2px 6px 2px 0;
  background: none;
  border: none;
  color: var(--text);
  font: inherit;
  cursor: pointer;
}
.back:hover {
  color: var(--accent);
}
.map-area.editing :deep(.leaflet-container) {
  cursor: crosshair;
}
.hint-small {
  margin: 0;
  font-size: var(--fs-xs);
  color: var(--warn);
}
.float-tr {
  position: absolute;
  right: 16px;
  top: 16px;
  z-index: 800;
}
.float-br {
  position: absolute;
  right: 56px;
  bottom: 24px;
  z-index: 800;
}
@media (max-width: 1280px) {
  .plan {
    grid-template-columns: 320px 1fr;
  }
}
</style>
