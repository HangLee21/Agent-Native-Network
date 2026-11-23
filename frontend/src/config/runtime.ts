/**
 * Runtime configuration loaded from /config.json so the frontend can be deployed separately
 * from the backend without rebuilding (C-08). Nothing environment-specific is hard-coded.
 */
import { t } from '@/i18n'
export type CoordSys = 'WGS84' | 'GCJ02'

/** One tile layer of a base map; `{key}` in the URL is replaced with `map.apiKey`. */
export interface BaseMapTile {
  url: string
  subdomains?: string
  maxZoom?: number
  attribution?: string
}

/** A selectable base map (D-17). Every tile layer of one base map shares its coordinate system. */
export interface BaseMapConfig {
  id: string
  label: string
  coordSys: CoordSys
  tiles: BaseMapTile[]
}

export interface MapConfig {
  /** Legacy single-tile fields; used to build `baseMaps` when config.json has no `baseMaps`. */
  coordSys: CoordSys
  tileUrl: string
  subdomains: string
  attribution: string
  maxZoom: number
  apiKey: string
  baseMaps: BaseMapConfig[]
  defaultBaseMap: string
}

export interface RuntimeConfig {
  apiBaseUrl: string
  wsUrl: string
  map: MapConfig
}

const GAODE_ATTRIBUTION = t('© 高德地图')

export const DEFAULT_BASE_MAPS: BaseMapConfig[] = [
  {
    id: 'gaode-street',
    label: t('高德 普通地图'),
    coordSys: 'GCJ02',
    tiles: [
      {
        url: 'https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}',
        subdomains: '1234',
        maxZoom: 18,
        attribution: GAODE_ATTRIBUTION,
      },
    ],
  },
  {
    id: 'gaode-satellite',
    label: t('高德 卫星图'),
    coordSys: 'GCJ02',
    tiles: [
      { url: 'https://webst0{s}.is.autonavi.com/appmaptile?style=6&x={x}&y={y}&z={z}', subdomains: '1234', maxZoom: 18, attribution: GAODE_ATTRIBUTION },
      { url: 'https://webst0{s}.is.autonavi.com/appmaptile?style=8&x={x}&y={y}&z={z}', subdomains: '1234', maxZoom: 18 },
    ],
  },
  {
    id: 'osm',
    label: 'OpenStreetMap',
    coordSys: 'WGS84',
    tiles: [{ url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png', maxZoom: 19, attribution: '© OpenStreetMap contributors' }],
  },
]

const defaults: RuntimeConfig = {
  apiBaseUrl: '',
  wsUrl: '',
  map: {
    coordSys: 'WGS84',
    tileUrl: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    subdomains: '',
    attribution: '© OpenStreetMap contributors',
    maxZoom: 19,
    apiKey: '',
    baseMaps: DEFAULT_BASE_MAPS,
    defaultBaseMap: 'gaode-street',
  },
}

let current: RuntimeConfig = defaults

/**
 * Old config files only have `tileUrl/coordSys/subdomains/...`: they become a single base map
 * that behaves exactly as before. Without any map settings the built-in base maps are used.
 */
function resolveMap(raw: Partial<MapConfig> | undefined): MapConfig {
  const merged: MapConfig = { ...defaults.map, ...(raw ?? {}) }
  if (Array.isArray(raw?.baseMaps) && raw.baseMaps.length > 0) {
    // labels written in Chinese in config.json are shown in English when there is an entry for them
    merged.baseMaps = raw.baseMaps.map((b) => ({
      ...b,
      label: t(b.label),
      tiles: b.tiles.map((x) => (x.attribution ? { ...x, attribution: t(x.attribution) } : x)),
    }))
  } else if (raw?.tileUrl) {
    merged.baseMaps = [
      {
        id: 'configured',
        label: t('配置底图'),
        coordSys: merged.coordSys,
        tiles: [{ url: merged.tileUrl, subdomains: merged.subdomains, maxZoom: merged.maxZoom, attribution: merged.attribution }],
      },
    ]
    merged.defaultBaseMap = 'configured'
  } else {
    merged.baseMaps = defaults.map.baseMaps
  }
  if (!merged.baseMaps.some((b) => b.id === merged.defaultBaseMap)) merged.defaultBaseMap = merged.baseMaps[0]!.id
  return merged
}

/** Derives URLs from the page origin when config.json leaves them empty (same-host deployment). */
export function resolveConfig(raw: Partial<RuntimeConfig>, origin: string): RuntimeConfig {
  const apiBaseUrl = (raw.apiBaseUrl ?? '').replace(/\/+$/, '') || origin
  const wsUrl = raw.wsUrl || apiBaseUrl.replace(/^http/, 'ws') + '/ws/telemetry'
  return { apiBaseUrl, wsUrl, map: resolveMap(raw.map) }
}

export async function loadRuntimeConfig(): Promise<RuntimeConfig> {
  try {
    const res = await fetch('/config.json', { cache: 'no-store' })
    const raw = res.ok ? ((await res.json()) as Partial<RuntimeConfig>) : {}
    current = resolveConfig(raw, window.location.origin)
  } catch {
    current = resolveConfig({}, window.location.origin)
  }
  return current
}

export function config(): RuntimeConfig {
  return current
}

/** Map settings may be given in either shape (legacy fields or `baseMaps`), as in config.json. */
export function setConfigForTest(cfg: Omit<RuntimeConfig, 'map'> & { map: Partial<MapConfig> }): void {
  current = { ...cfg, map: resolveMap(cfg.map) }
}
