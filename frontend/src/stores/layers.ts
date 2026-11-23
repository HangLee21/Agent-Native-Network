import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { config, type BaseMapConfig } from '@/config/runtime'
import { t } from '@/i18n'

/** Layer catalogue (R-04), built from the research-notes Q-05 list. */
export interface LayerDef {
  id: string
  group: string
  label: string
  color: string
  defaultVisible: boolean
  /** When set, the layer cannot be shown and the reason is displayed (DEV-06). */
  unavailable?: string
}

export const LAYERS: LayerDef[] = [
  { id: 'drone', group: t('飞行器'), label: t('实时位置'), color: 'var(--accent)', defaultVisible: true },
  { id: 'track', group: t('飞行器'), label: t('历史航迹'), color: 'var(--track)', defaultVisible: true },
  { id: 'home', group: t('飞行器'), label: t('Home 点（返航点）'), color: 'var(--ok)', defaultVisible: true },
  { id: 'rc', group: t('飞行器'), label: t('遥控器（飞手）位置'), color: '#f472b6', defaultVisible: true },
  { id: 'alertRing', group: t('飞行器'), label: t('限高 / 限飞区接近提示'), color: 'var(--warn)', defaultVisible: true },
  { id: 'route', group: t('航线'), label: t('计划航线'), color: 'var(--accent)', defaultVisible: true },
  { id: 'target', group: t('航线'), label: t('当前目标点'), color: '#facc15', defaultVisible: true },
  { id: 'devicePaths', group: t('航线'), label: t('飞行器规划路径（flyto / 起飞 / 返航）'), color: '#e2e8f0', defaultVisible: true },
  { id: 'poi', group: t('航线'), label: t('兴趣点环绕'), color: '#fb923c', defaultVisible: true },
  { id: 'targets', group: t('航线'), label: t('选定目标（误差圈、停止点、返回点）'), color: '#f43f5e', defaultVisible: true },
  { id: 'dogs', group: t('机器狗'), label: t('实时位置和朝向'), color: '#a3e635', defaultVisible: true },
  { id: 'dogTrack', group: t('机器狗'), label: t('走过的轨迹'), color: '#a3e635', defaultVisible: true },
  { id: 'dogNav', group: t('机器狗'), label: t('导航（目标、路线、规划路径）'), color: '#a3e635', defaultVisible: true },
  { id: 'safeZone', group: t('安全'), label: t('平台安全区'), color: 'var(--zone)', defaultVisible: true },
  {
    id: 'djiNoFly',
    group: t('安全'),
    label: t('大疆限飞区'),
    color: 'var(--danger)',
    defaultVisible: false,
    unavailable: t('遥控器场景接口不提供限飞区形状，只能在接近时告警（DEV-06）'),
  },
]

const KEY = 'uav.layers'
const BASE_MAP_KEY = 'uav.baseMap'

function load(): Record<string, boolean> {
  const defaults = Object.fromEntries(LAYERS.map((l) => [l.id, l.defaultVisible && !l.unavailable]))
  try {
    const saved = JSON.parse(localStorage.getItem(KEY) ?? '{}') as Record<string, boolean>
    return { ...defaults, ...saved, djiNoFly: false }
  } catch {
    return defaults
  }
}

/** Saved base map if it still exists in the current config, otherwise the configured default (D-17). */
function loadBaseMap(): string {
  const { baseMaps, defaultBaseMap } = config().map
  try {
    const saved = localStorage.getItem(BASE_MAP_KEY)
    if (saved && baseMaps.some((b) => b.id === saved)) return saved
  } catch {
    /* storage unavailable */
  }
  return defaultBaseMap
}

export const useLayersStore = defineStore('layers', () => {
  const visible = ref<Record<string, boolean>>(load())
  const baseMapId = ref<string>(loadBaseMap())
  const baseMaps = computed<BaseMapConfig[]>(() => config().map.baseMaps)
  const baseMap = computed<BaseMapConfig>(() => baseMaps.value.find((b) => b.id === baseMapId.value) ?? baseMaps.value[0]!)

  function isVisible(id: string): boolean {
    return visible.value[id] ?? false
  }

  function set(id: string, on: boolean): void {
    const def = LAYERS.find((l) => l.id === id)
    if (def?.unavailable) return
    visible.value = { ...visible.value, [id]: on }
    try {
      localStorage.setItem(KEY, JSON.stringify(visible.value))
    } catch {
      /* not persisted in private mode */
    }
  }

  function setBaseMap(id: string): void {
    if (!baseMaps.value.some((b) => b.id === id)) return
    baseMapId.value = id
    try {
      localStorage.setItem(BASE_MAP_KEY, id)
    } catch {
      /* not persisted in private mode */
    }
  }

  return { visible, isVisible, set, baseMaps, baseMapId, baseMap, setBaseMap }
})
