<script lang="ts">
/** What the main view shows: the map, the selected drone's video, or (two drones streaming) the other drone's video. */
type MainView = 'map' | 'video' | 'other'

/**
 * Handed from the monitor of one drone to the monitor of the next: the page re-mounts when the operator switches
 * drones (D-31, App.vue), and the new one keeps showing the same kind of main view (2026-11-04 field test).
 */
interface HandOver {
  to: string
  view: MainView
  userSwapped: boolean
}
let handOver: HandOver | null = null

/** The hand-over meant for the monitor of drone `sn`, if any; it is used once. */
function takeHandOver(sn: string): HandOver | null {
  const h = handOver?.to === sn ? handOver : null
  handOver = null
  return h
}
function giveHandOver(h: HandOver | null): void {
  handOver = h
}
</script>

<script setup lang="ts">
/**
 * Flight monitoring (R-14, R-15, R-28, ui-design.md §2.2): video and map on one screen with swappable main/PiP (the
 * PiP can be tucked away), HUD and camera rail over the stage; one side panel, read top to bottom: the selected
 * drone's status and phase, one task card, the latest receipts, and the fixed safety area with every drone's card
 * and safety buttons (collapsible to a rail that keeps them).
 * With two drones streaming and a video in the main view, the small window has two tiles: the map and the video of
 * the drone that is not in the main view; clicking a tile puts it in the main view.
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type L from 'leaflet'
import MapCanvas from '@/components/map/MapCanvas.vue'
import FleetLayers from '@/components/map/FleetLayers.vue'
import DogRouteEditLayer from '@/components/map/DogRouteEditLayer.vue'
import LayerPanel from '@/components/map/LayerPanel.vue'
import DroneInfoPanel from '@/components/drone/DroneInfoPanel.vue'
import TargetDialog from '@/components/control/TargetDialog.vue'
import TakeoffDialog from '@/components/control/TakeoffDialog.vue'
import StickControlOverlay from '@/components/control/StickControlOverlay.vue'
import VideoPanel from '@/components/video/VideoPanel.vue'
import CameraRail from '@/components/video/CameraRail.vue'
import PanelHeader from '@/components/monitor/PanelHeader.vue'
import TaskArea from '@/components/monitor/TaskArea.vue'
import ActivityBar from '@/components/monitor/ActivityBar.vue'
import SafetyFooter from '@/components/monitor/SafetyFooter.vue'
import MonitorRail from '@/components/monitor/MonitorRail.vue'
import AppIcon from '@/components/common/AppIcon.vue'
import DroneScope from '@/components/common/DroneScope.vue'
import { useControlStore } from '@/stores/control'
import { useTelemetryStore } from '@/stores/telemetry'
import { useLiveStore } from '@/stores/live'
import { useManualStore } from '@/stores/manual'
import { useTargetsStore } from '@/stores/targets'
import { useFleetStore } from '@/stores/fleet'
import { useFlightActions } from '@/composables/useFlightActions'
import { controlApi } from '@/api/control'
import type { LatLon } from '@/utils/coord'
import { modeLabel } from '@/utils/format'
import { useDroneSn } from '@/composables/useDrone'
import DogMain from '@/components/dog/DogMain.vue'
import DogPanel from '@/components/dog/DogPanel.vue'
import DogDrawer from '@/components/dog/DogDrawer.vue'
import DogThumb from '@/components/dog/DogThumb.vue'
import HoldPad from '@/components/dog/HoldPad.vue'
import ManualContent from '@/components/dog/ManualContent.vue'
import { useDogActions } from '@/components/dog/useDogActions'
import { grasp } from '@/components/dog/s10Grasp'
import { useDogStore, DOG_NAME } from '@/stores/dog'
import { useDog2Store } from '@/stores/dogv2'
import type { DogId } from '@/api/dog'
import { t } from '@/i18n'

/** The drone this component works on, fixed at setup (D-31). */
const sn = useDroneSn()

const control = useControlStore()
const tel = useTelemetryStore()
const manual = useManualStore()
const live = useLiveStore()
const targets = useTargetsStore()
const fleet = useFleetStore()
const { takeoffOpen, takeoff } = useFlightActions()
/*
 * Robot dogs on the same page (docs/dog/ui-design.md, structure A). With no dog configured every computed below is
 * empty / false and the page is exactly the flight monitor it was.
 */
const dogs = useDogStore()
const dogActs = useDogActions()
/** The dog being operated; null while the drone `sn` is operated. */
const dogSel = computed<DogId | null>(() => (dogs.selected && dogs.dogs[dogs.selected] ? dogs.selected : null))
/** While a dog is operated, the drone map or video from the small window can be looked at large without switching. */
const peekDrone = ref<'map' | 'video' | null>(null)
/** A dog camera looked at large without switching who is operated. */
const peekDog = ref<DogId | null>(null)
watch(dogSel, () => {
  peekDrone.value = null
  peekDog.value = null
})
/** The dog whose picture fills the main view, if any. */
const stageDog = computed<DogId | null>(() => peekDog.value ?? (dogSel.value && !peekDrone.value ? dogSel.value : null))
/** Other dogs' cameras in the small window (online or lost while busy), never the one in the main view. */
const dogTiles = computed(() => dogs.ids.filter((id) => dogs.important(id) && id !== stageDog.value).slice(0, 2))
const operatingName = computed(() => (dogSel.value ? DOG_NAME[dogSel.value] : selectedLabel.value))
const lostDogs = computed(() => dogs.ids.filter((id) => dogs.lost(id)).map((id) => DOG_NAME[id]).join(t('、')))
/** Dogs this page has not heard about for a while although they were connected; the one in the main view says so itself. */
const staleDogs = computed(() => {
  const ids = dogs.ids.filter((id) => dogs.pageStale(id) && id !== stageDog.value)
  return ids.length ? { names: ids.map((id) => DOG_NAME[id]).join(t('、')), n: Math.max(...ids.map((id) => dogs.staleSecs(id))) } : null
})
/** "?" opens the manual over the main view: the side panel and the safety area stay, control is not released. */
const helpAnchor = ref<string | null>(null)
function openHelp(id: string): void {
  void dogs.s10HoldEnd('打开说明')  // i18n-ignore: sent to the backend, shown via tb()
  void dogs.armHoldEnd('打开说明')  // i18n-ignore: sent to the backend, shown via tb()
  dogs.l3SetAxes([0, 0, 0])
  helpAnchor.value = id
}
function onHelpKey(e: KeyboardEvent): void {
  if (e.key === 'Escape' && helpAnchor.value !== null) {
    e.preventDefault()   // this Esc closes the manual panel; it is not the pad's "stop"
    helpAnchor.value = null
  }
}
window.addEventListener('keydown', onHelpKey)
/**
 * `#/monitor?dog=s10` opens the page operating that dog (links from the manual, screenshots). Read once and dropped
 * from the address, so switching drones (which re-mounts this page) does not jump back to the dog; a dog that is not
 * configured is never selected.
 */
const router = useRouter()
const route = useRoute()
const askedDog = route?.query?.dog
if (askedDog === 's10' || askedDog === 'lite3') {
  const { dog: _drop, ...rest } = route.query
  void router?.replace({ query: rest })
  if (dogs.dogs[askedDog]) dogs.select(askedDog)
  else {
    const stopWait = watch(() => dogs.dogs[askedDog], (d) => {
      if (d) {
        dogs.select(askedDog)
        stopWait()
      }
    })
    window.setTimeout(stopWait, 5000)
  }
}
function operate(id: DogId): void {
  peekDog.value = null
  dogs.select(id)
}
function lookBack(): void {
  peekDog.value = null
  peekDrone.value = null
}
const drawerOpen = ref(false)
const picked = ref<{ kind: 'flyto' | 'poi' | 'target'; point: LatLon } | null>(null)
/** Kept from the monitor of the previously selected drone when this one was mounted by a drone switch. */
const carried = takeHandOver(sn)
/**
 * Which view is large: video by default while streaming, map otherwise; the operator can swap. After a drone switch
 * it is the same kind as before: the controlled drone's video stays the controlled drone's video (now the newly
 * selected one), the other drone's video stays the other (not controlled) drone's video, the map stays the map.
 */
const primary = ref<MainView>(carried?.view ?? (live.status?.streaming ? 'video' : 'map'))
const userSwapped = ref(carried?.userSwapped ?? false)

function storedFlag(key: string) {
  let v = false
  try {
    v = localStorage.getItem(key) === '1'
  } catch {
    /* storage unavailable */
  }
  const r = ref(v)
  watch(r, (c) => {
    try {
      localStorage.setItem(key, c ? '1' : '0')
    } catch {
      /* storage unavailable */
    }
  })
  return r
}
const collapsed = storedFlag('uav.panelCollapsed')
/** The picture-in-picture can be tucked away for the largest main view; a chip brings it back. */
const pipHidden = storedFlag('uav.pipHidden')

watch(() => live.status?.streaming, (s) => {
  if (!userSwapped.value) primary.value = s ? 'video' : 'map'
})
watch(() => control.pickingTarget, (p) => {
  if (p === 'dogGoal' || p === 'dogRoute') {
    // a dog's navigation points: the map goes large the way a small-window tile does, the dog stays operated
    if (dogSel.value && !mapLarge.value) peek('map')
    targets.selecting = false
  } else if (p) {
    primary.value = 'map' // picking a target needs the large map
    targets.selecting = false
  }
})
const dogPicking = computed(() => control.pickingTarget === 'dogGoal' || control.pickingTarget === 'dogRoute')
/** Picking a dog's points ends when the dog is no longer the one operated. */
watch(dogSel, () => {
  if (dogPicking.value) control.pickingTarget = null
})
watch(() => targets.selecting, (s) => {
  if (s) primary.value = 'video' // selecting in the video needs the large video
})

/** The other drone whose video can share the stage (R-28): the first other enabled drone that is streaming. */
const other = computed(() => fleet.drones.find((d) => d.gatewaySn !== sn && d.enabled && !!useLiveStore(d.gatewaySn).status?.streaming) ?? null)
/** What the main view shows now: the other drone's video falls back to this drone's video (or the map) when it stops. */
const main = computed<MainView>(() => {
  if (primary.value !== 'other' || other.value) return primary.value
  return live.status?.streaming ? 'video' : 'map'
})
const mapIsPrimary = computed(() => main.value === 'map')
/** Two tiles in the small window: the map and the video not in the main view (two drones streaming, a video in the main view). */
const duo = computed(() => !!other.value && !mapIsPrimary.value)

function swap(): void {
  userSwapped.value = true
  primary.value = mapIsPrimary.value ? 'video' : 'map'
}

/** A small-window tile was clicked: it becomes the main view. */
function show(v: MainView): void {
  userSwapped.value = true
  primary.value = v
}

/** Main view, or the small window's first (left) or second (right) tile; the map is the left tile of two. */
function paneClass(v: MainView): string {
  if (stageDog.value) return v === 'map' ? 'pip panel' : 'pip pip-2 panel'
  if (dogSel.value && peekDrone.value) return peekDrone.value === v ? 'main' : v === 'map' ? 'pip panel' : 'pip pip-2 panel'
  if (main.value === v) return 'main'
  return duo.value && v !== 'map' ? 'pip pip-2 panel' : 'pip panel'
}
/** A dog is operated or looked at: the drone views are tiles (or peeked), the drone-only tools are hidden. */
const dogMode = computed(() => !!stageDog.value || !!dogSel.value)
const mapLarge = computed(() => (dogMode.value ? !stageDog.value && peekDrone.value === 'map' : mapIsPrimary.value))
const videoLarge = computed(() => (dogMode.value ? !stageDog.value && peekDrone.value === 'video' : main.value === 'video'))
function peek(v: 'map' | 'video'): void {
  peekDog.value = null
  peekDrone.value = v
}
function peekDogCam(id: DogId): void {
  peekDrone.value = null
  peekDog.value = id === dogSel.value ? null : id
}

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onHelpKey)
  // picking a dog's points lives in this drone's control store: it does not outlive this page (the points stay)
  if (control.pickingTarget === 'dogGoal' || control.pickingTarget === 'dogRoute') control.pickingTarget = null
  // switching drones re-mounts this page: the dogs stop, Lite3 control stays; leaving the page also releases it
  if (router?.currentRoute.value.path === '/monitor') dogs.stopMotion('切换设备')  // i18n-ignore: sent to the backend, shown via tb()
  else dogs.stopAllLocal('离开实时监控页')  // i18n-ignore: sent to the backend, shown via tb()
  // re-mounted for another drone (not leaving the page): the next monitor starts from what this one shows
  const next = fleet.selectedSn
  giveHandOver(next && next !== sn ? { to: next, view: main.value, userSwapped: userSwapped.value } : null)
})

/**
 * The map keeps the operated device centred until the operator drags it; the follow button turns it back on. While a
 * dog with a position on the map (new dog system, GPS fix) is operated, that dog is followed instead of the drone.
 */
const following = ref(true)
const dog2 = useDog2Store()
const dogOnMap = computed(() => {
  const d = dogSel.value ? dog2.dogs.find((x) => x.model === dogSel.value) : null
  return d?.online && d.position?.lat != null ? d : null
})
watch(dogSel, () => (following.value = true))
const followLabel = computed(() => {
  if (dogOnMap.value && dogSel.value) return t('跟随 {name}', { name: DOG_NAME[dogSel.value] })
  return fleet.drones.length > 1 && fleet.selected ? t('跟随 {name}', { name: fleet.selected.label }) : t('跟随飞机')
})
const followTitle = computed(() => (dogOnMap.value && dogSel.value
  ? t('地图重新以 {name} 为中心，并随它移动', { name: DOG_NAME[dogSel.value] })
  : t('地图重新以飞机为中心，并随它移动')))
function onMapReady(m: L.Map): void {
  m.on('dragstart', () => (following.value = false))
}
watch(mapIsPrimary, (p) => {
  if (!p) following.value = true // the picture-in-picture map cannot be dragged
})

const many = computed(() => fleet.drones.length > 1)
const selectedLabel = computed(() => fleet.label(sn))
const otherLabel = computed(() => other.value?.label ?? '')
/** The drone whose video is in the small window next to the map (two tiles). */
const tileLabel = computed(() => (main.value === 'other' ? selectedLabel.value : otherLabel.value))
const pipName = computed(() => {
  if (dogMode.value) {
    // what the small window holds while a dog is operated or looked at: the map, the drone video, other dogs' cameras
    const names = [
      ...(mapLarge.value ? [] : [t('地图')]),
      ...(!videoLarge.value && live.status?.streaming ? [t('{name} 视频', { name: selectedLabel.value })] : []),
      ...dogTiles.value.map((id) => DOG_NAME[id]),
    ]
    return names.join(t('、'))
  }
  if (mapIsPrimary.value) return many.value && fleet.selected ? t('{name} 视频', { name: fleet.selected.label }) : t('视频')
  return duo.value ? t('地图、{name} 视频', { name: tileLabel.value }) : t('地图')
})

function onMapClick(p: LatLon): void {
  const pk = control.pickingTarget
  if (pk === 'dogGoal' || pk === 'dogRoute') {
    // the dog's navigation (docs/dog/ui-design.md 19.5): one click is the goal; in route mode every click adds a point
    const id = dog2.navDraft?.dog ?? dogs.l3NavDog?.id
    if (!mapLarge.value || !id) return
    if (pk === 'dogGoal') {
      dog2.draftOpen(dogs.l3NavDog?.id ?? id, [p])
      control.pickingTarget = null
    } else {
      if (!dog2.navDraft) dog2.draftOpen(id, [])
      dog2.draftAdd(p)
    }
    return
  }
  if (pk && mapIsPrimary.value) {
    picked.value = { kind: pk, point: p }
    control.pickingTarget = null
  }
}

async function confirmTarget(height: number, speed: number): Promise<void> {
  const p = picked.value
  picked.value = null
  if (!p) return
  if (p.kind === 'target') await targets.selectGeo(p.point.lat, p.point.lon, height)
  else if (p.kind === 'flyto') await control.run('flyto', t('飞向目标点'), () => controlApi(sn).flyTo(p.point.lat, p.point.lon, height, speed))
  else await control.run('poi', t('进入兴趣点环绕'), () => controlApi(sn).poiEnter(p.point.lat, p.point.lon, height))
}
</script>

<template>
  <div class="monitor" :class="{ 'drawer-open': drawerOpen, collapsed: collapsed && !dogSel, many, 'pip-hidden': pipHidden }">
    <section class="stage" :class="{ duo: duo && !dogMode, stick: manual.snapshot?.active && !dogSel, dogtiles: dogTiles.length > 0 && !pipHidden }" :aria-label="t('主画面')">
      <DogMain v-if="stageDog" :key="stageDog" :dog="stageDog" />
      <div v-show="mapLarge || !pipHidden" :class="paneClass('map')" data-test="map-pane">
        <MapCanvas :center="tel.position" :interactive="mapLarge" :zoom-at="dogSel ? 'topright' : 'bottomright'" @map-click="onMapClick" @ready="onMapReady">
          <FleetLayers :follow="following && !dogOnMap" :follow-dog="following && dogOnMap ? dogSel : null" />
          <DogRouteEditLayer v-if="dog2.navDraft" />
        </MapCanvas>
        <div v-if="mapLarge" class="float-tr">
          <button v-if="!following && (dogOnMap || tel.position)" class="btn btn-sm follow" data-test="follow"
                  :title="followTitle" @click="following = true">
            <AppIcon name="crosshair" :size="15" />{{ followLabel }}
          </button>
          <LayerPanel :default-open="false" />
        </div>
        <template v-if="dogMode && !mapLarge">
          <button class="pip-pick" :title="t('地图放到主画面看（不改变正在操作的 {name}）', { name: operatingName })" :aria-label="t('地图放到主画面')" data-test="pip-pick-map" @click="peek('map')">
            <span class="tile-tag chip">{{ t('地图') }}</span>
          </button>
          <button class="pip-min" :title="t('收起小窗，让主画面更大')" :aria-label="t('收起小窗')" data-test="pip-hide" @click="pipHidden = true">
            <AppIcon name="minus" :size="14" />
          </button>
        </template>
        <button v-else-if="duo && !dogMode" class="pip-pick" :title="t('地图放到主画面')" :aria-label="t('地图放到主画面')" data-test="pip-pick-map" @click="show('map')" />
        <button v-else-if="!mapIsPrimary && !dogMode" class="pip-min" :title="t('收起小窗，让主画面更大')" :aria-label="t('收起小窗')" data-test="pip-hide" @click="pipHidden = true">
          <AppIcon name="minus" :size="14" />
        </button>
      </div>
      <div v-show="videoLarge || (!pipHidden && (!dogMode || !!live.status?.streaming))" :class="paneClass('video')" data-test="video-pane">
        <VideoPanel :compact="!videoLarge" :controls="false" />
        <template v-if="dogMode && !videoLarge">
          <button class="pip-pick" :title="t('{name} 视频放到主画面看（不改变正在操作的 {op}）', { name: selectedLabel, op: operatingName })" data-test="pip-pick-video" @click="peek('video')">
            <span class="tile-tag chip"><span class="dot" :style="{ background: fleet.color(sn) }" />{{ t('{name} 视频', { name: selectedLabel }) }}</span>
          </button>
          <button class="pip-min" :title="t('收起小窗，让主画面更大')" :aria-label="t('收起小窗')" data-test="pip-hide" @click="pipHidden = true">
            <AppIcon name="minus" :size="14" />
          </button>
        </template>
        <template v-else-if="!dogMode">
          <button v-if="main === 'other'" class="pip-pick" :title="t('{name} 视频放到主画面', { name: selectedLabel })" :aria-label="t('{name} 视频放到主画面', { name: selectedLabel })"
                  data-test="pip-pick-video" @click="show('video')">
            <span class="tile-tag chip"><span class="dot" :style="{ background: fleet.color(sn) }" />{{ t('{name} 视频', { name: selectedLabel }) }}</span>
          </button>
          <button v-if="main !== 'video'" class="pip-min" :title="t('收起小窗，让主画面更大')" :aria-label="t('收起小窗')" data-test="pip-hide" @click="pipHidden = true">
            <AppIcon name="minus" :size="14" />
          </button>
        </template>
      </div>
      <!-- dog cameras in the small window: clicking one shows it large without switching who is operated -->
      <div v-for="(id, i) in dogTiles" v-show="!pipHidden" :key="`dog-${id}`" class="pip dogtile panel" :class="`dt-${i}`" data-test="dog-tile">
        <DogThumb :dog="id" />
        <button class="pip-pick" :title="t('{name} 相机放到主画面看（不改变正在操作的设备）', { name: DOG_NAME[id] })" :aria-label="t('{name} 相机放到主画面', { name: DOG_NAME[id] })" @click="peekDogCam(id)" />
      </div>
      <!-- the other drone's video: only while two drones stream and a video is the main view (one more player at most) -->
      <div v-if="other && !dogMode && (main === 'other' || (main === 'video' && !pipHidden))" :key="other.gatewaySn" :class="paneClass('other')"
           data-test="other-video-pane">
        <DroneScope :sn="other.gatewaySn">
          <VideoPanel :compact="main !== 'other'" :controls="false" />
        </DroneScope>
        <template v-if="main !== 'other'">
          <button class="pip-pick" :title="t('{name} 视频放到主画面', { name: otherLabel })" :aria-label="t('{name} 视频放到主画面', { name: otherLabel })" data-test="pip-pick-other" @click="show('other')">
            <span class="tile-tag chip"><span class="dot" :style="{ background: other.color }" />{{ t('{name} 视频', { name: otherLabel }) }}</span>
          </button>
          <button class="pip-min" :title="t('收起小窗，让主画面更大')" :aria-label="t('收起小窗')" data-test="pip-hide" @click="pipHidden = true">
            <AppIcon name="minus" :size="14" />
          </button>
        </template>
      </div>
      <!-- two videos on the stage: name the one in the main view; the camera rail and side panel still work on the selected drone -->
      <div v-if="dogMode && (peekDog || peekDrone)" class="view-badge chip peekbadge" data-test="peek-badge">
        {{ t('主画面是 {view} · 当前操作 {op}', { view: peekDog ? t('{name} 的画面', { name: DOG_NAME[peekDog] }) : peekDrone === 'map' ? t('地图') : t('{name} 视频', { name: selectedLabel }), op: operatingName }) }}
        <button v-if="peekDog" class="btn btn-sm" data-test="peek-operate" @click="operate(peekDog)">{{ t('操作 {name}', { name: DOG_NAME[peekDog] }) }}</button>
        <button class="btn btn-sm" data-test="peek-back" @click="lookBack">{{ t('看回 {name}', { name: operatingName }) }}</button>
      </div>
      <div v-if="duo && !dogMode" class="view-badge chip" data-test="main-view-badge">
        <span class="dot" :style="{ background: main === 'other' ? other?.color : fleet.color(sn) }" />
        <template v-if="main === 'other'">{{ t('{name} 视频 · 当前操作 {op}', { name: otherLabel, op: selectedLabel }) }}</template>
        <template v-else>{{ t('{name} 视频', { name: selectedLabel }) }}</template>
      </div>
      <CameraRail v-if="!dogMode" />
      <div class="stage-bl">
        <button v-if="!dogMode" class="swap btn btn-sm" :title="t('交换主画面与小窗')" data-test="swap" @click="swap">
          <AppIcon name="swap" :size="15" />{{ mapIsPrimary ? t('视频主画面') : t('地图主画面') }}
        </button>
        <button v-if="pipHidden" class="btn btn-sm pip-show" data-test="pip-show" @click="pipHidden = false">
          <AppIcon name="camera" :size="15" />{{ t('展开小窗（{name}）', { name: pipName }) }}
        </button>
      </div>
      <div v-if="control.pickingTarget === 'dogGoal'" class="pick-hint dogpick" data-test="dog-pick-hint">
        <AppIcon name="crosshair" />{{ t('在地图上单击选择狗的目标点') }}
        <button class="btn btn-sm" @click="control.pickingTarget = null">{{ t('取消') }}</button>
      </div>
      <div v-else-if="control.pickingTarget === 'dogRoute'" class="pick-hint dogpick" data-test="dog-pick-hint">
        <AppIcon name="route" />{{ t('单击地图依次添加路线点，拖动调整，右键删除') }}
        <button class="btn btn-sm" data-test="dog-pick-done" @click="control.pickingTarget = null">{{ t('完成') }}</button>
        <button class="btn btn-sm" @click="control.pickingTarget = null; dog2.draftClear()">{{ t('取消') }}</button>
      </div>
      <div v-else-if="control.pickingTarget" class="pick-hint">
        <AppIcon name="crosshair" />{{ control.pickingTarget === 'flyto' ? t('在地图上单击选择目标点') : control.pickingTarget === 'target' ? t('在地图上单击选择目标（不会移动飞机）') : t('在地图上单击选择环绕中心') }}
        <button class="btn btn-sm" @click="control.pickingTarget = null">{{ t('取消') }}</button>
      </div>
      <div v-if="mapIsPrimary && !dogMode" class="mode-badge chip" :class="tel.online ? '' : 'danger'"><span class="dot" />{{ tel.online ? modeLabel(tel.drone?.modeCode) : t('设备未连接') }}</div>
      <StickControlOverlay v-if="manual.snapshot?.active && !dogSel" />
      <HoldPad v-if="dogSel && helpAnchor === null && !(dogSel === 's10' && grasp.selecting)" :key="`pad-${dogSel}`" :dog="dogSel" @stop="dogActs.stop(dogSel)" />
      <div v-if="lostDogs" class="lostbar" data-test="dog-lost">
        <AppIcon name="alert" :size="16" />{{ t('{names} 失联：失联前正在执行动作或被本平台控制。导航没有心跳，狗很可能继续走；平台的指令发不出去，请狗旁的人用实体遥控器', { names: lostDogs }) }}
      </div>
      <div v-else-if="staleDogs" class="lostbar stale" data-test="dog-stale">
        <AppIcon name="alert" :size="16" />{{ t('本页 {n} 秒没收到 {name} 的新状态', { n: staleDogs.n, name: staleDogs.names }) }}
      </div>
      <div v-if="helpAnchor !== null" class="helpov" data-test="help-panel">
        <ManualContent panel :anchor="helpAnchor" @close="helpAnchor = null" />
      </div>
    </section>

    <aside class="side panel" :aria-label="dogSel ? t('{name} 控制', { name: DOG_NAME[dogSel] }) : collapsed ? t('飞行控制（已收起）') : t('飞行控制')">
      <template v-if="dogSel">
        <DogPanel :key="dogSel" :dog="dogSel" @help="openHelp" />
        <SafetyFooter dog-mode />
      </template>
      <MonitorRail v-else-if="collapsed" @expand="collapsed = false" />
      <template v-else>
        <PanelHeader @collapse="collapsed = true" />
        <div class="side-scroll scroll">
          <TaskArea />
        </div>
        <ActivityBar />
        <SafetyFooter />
      </template>
    </aside>

    <section class="drawer panel">
      <button class="drawer-head" :aria-expanded="drawerOpen" @click="drawerOpen = !drawerOpen">
        <AppIcon :name="drawerOpen ? 'down' : 'up'" />
        <span>{{ t('详细信息') }}</span>
        <span class="dim">{{ dogSel ? t('{name} · 指令 · 后台任务 · 话题 · 原始返回 · 链路', { name: DOG_NAME[dogSel] }) : t('全部飞行器 / 遥控器字段') }}</span>
      </button>
      <div v-if="drawerOpen" class="drawer-body scroll">
        <DogDrawer v-if="dogSel" :dog="dogSel" />
        <DroneInfoPanel v-else :columns="4" />
      </div>
    </section>
    <TargetDialog v-if="picked" :kind="picked.kind" :point="picked.point" :default-height="picked.kind === 'target' ? 0 : (tel.drone?.relativeHeight ?? 50)"
      @confirm="confirmTarget" @cancel="picked = null" />
    <TakeoffDialog v-if="takeoffOpen" @confirm="takeoff" @cancel="takeoffOpen = false" />
  </div>
</template>

<style scoped>
.monitor {
  display: grid;
  grid-template-columns: 1fr 420px;
  grid-template-rows: 1fr 36px;
  height: 100%;
}
.monitor.collapsed {
  grid-template-columns: 1fr 64px;
}
.monitor.collapsed.many {
  grid-template-columns: 1fr 84px;
}
.monitor.drawer-open {
  grid-template-rows: 1fr 320px;
}
.stage {
  --hud-right: 88px;
  position: relative;
  background: #000;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}
.main {
  position: absolute;
  inset: 0;
}
.pip {
  position: absolute;
  left: var(--sp-4);
  bottom: var(--sp-4);
  width: 360px;
  height: 220px;
  z-index: 900;
  overflow: hidden;
  box-shadow: var(--shadow);
  border-width: 2px;
}
/* second small tile (two drones): right of the map tile */
.pip-2 {
  left: calc(var(--sp-4) + 360px + var(--sp-2));
}
.stage-bl {
  position: absolute;
  left: calc(var(--sp-4) + 8px);
  bottom: calc(var(--sp-4) + 228px);
  z-index: 950;
  display: flex;
  gap: var(--sp-2);
}
/* stick control puts its panel right of the small window: the second tile moves above the map tile */
.stage.duo.stick .pip-2 {
  left: var(--sp-4);
  bottom: calc(var(--sp-4) + 228px);
}
.stage.duo.stick .stage-bl {
  bottom: calc(var(--sp-4) + 456px);
}
.pip-hidden .stage-bl,
.pip-hidden .stage.duo.stick .stage-bl {
  left: var(--sp-4);
  bottom: var(--sp-4);
}
/* a small tile of two: click to put it in the main view */
.pip-pick {
  position: absolute;
  inset: 0;
  z-index: 1050; /* above the Leaflet panes and the video overlays, below the collapse button */
  display: flex;
  align-items: flex-start;
  padding: 6px;
  border: none;
  background: transparent;
  cursor: pointer;
}
.pip-pick:hover,
.pip-pick:focus-visible {
  outline: none;
  box-shadow: inset 0 0 0 2px var(--accent);
}
.tile-tag {
  height: 24px;
  padding: 0 8px;
  background: var(--overlay);
  color: var(--text);
  font-size: var(--fs-xs);
}
.view-badge {
  position: absolute;
  left: 16px;
  top: 16px;
  z-index: 800;
  background: var(--overlay);
}
.stage.dogtiles .stage-bl {
  bottom: calc(var(--sp-4) + 386px);
}
/* dog camera tiles: a row of small tiles above the drone tiles */
.dogtile {
  width: 240px;
  height: 150px;
  bottom: calc(var(--sp-4) + 228px);
}
.dt-1 {
  left: calc(var(--sp-4) + 248px);
}
.peekbadge {
  gap: 8px;
  z-index: 1150;
}
.lostbar {
  position: absolute;
  left: 50%;
  top: 60px;
  transform: translateX(-50%);
  z-index: 1150;
  display: flex;
  align-items: center;
  gap: 8px;
  max-width: calc(100% - 200px);
  padding: 8px 14px;
  border-radius: var(--r-ctl);
  background: var(--danger);
  color: #fff;
  font-weight: 600;
  font-size: var(--fs-sm);
}
.lostbar.stale {
  background: color-mix(in srgb, var(--warn) 85%, #000);
}
.helpov {
  position: absolute;
  inset: 0;
  z-index: 1200;
}
.swap,
.pip-show {
  background: var(--overlay);
}
.pip-min {
  position: absolute;
  top: 6px;
  right: 6px;
  z-index: 1100; /* above the Leaflet panes and controls of the PiP map */
  width: 28px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--r-ctl);
  border: 1px solid var(--border);
  background: var(--overlay);
  color: var(--text);
  cursor: pointer;
}
.float-tr {
  position: absolute;
  right: 92px;
  top: 16px;
  z-index: 800;
  display: flex;
  align-items: flex-start;
  gap: var(--sp-2);
}
.follow {
  height: 40px;
  background: var(--overlay);
}
.pick-hint {
  position: absolute;
  top: 16px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 960;
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  padding: 6px var(--sp-3);
  border-radius: var(--r-ctl);
  background: var(--accent);
  color: var(--accent-ink);
  font-weight: 600;
}
/* a dog's points: below the "主画面是 地图 · 当前操作 …" badge that is always there while a dog is operated */
.pick-hint.dogpick {
  top: 60px;
  z-index: 1160;
  max-width: calc(100% - 32px);
}
.mode-badge {
  position: absolute;
  left: 16px;
  top: 16px;
  z-index: 800;
  background: var(--overlay);
}
.side {
  grid-row: 1 / span 2;
  grid-column: 2;
  border-radius: 0;
  border-width: 0 0 0 1px;
  display: flex;
  flex-direction: column;
  min-height: 0;
  min-width: 0;
}
.side-scroll {
  flex: 1 1 auto;
  min-height: 0;
  padding: 10px var(--sp-3);
}
.drawer {
  grid-column: 1;
  border-radius: 0;
  border-width: 1px 0 0 0;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.drawer-head {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  height: 36px;
  padding: 0 var(--sp-4);
  background: none;
  border: none;
  color: var(--text);
  font: inherit;
  font-weight: 600;
  cursor: pointer;
  flex: none;
}
.drawer-head .dim {
  font-weight: 400;
  font-size: var(--fs-xs);
}
.drawer-body {
  padding: 0 var(--sp-4) var(--sp-4);
  flex: 1;
  min-height: 0;
}
</style>
