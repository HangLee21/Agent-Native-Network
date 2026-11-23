import type { InjectionKey, ShallowRef } from 'vue'
import type L from 'leaflet'
import type { LatLon } from '@/utils/coord'

export interface MapContext {
  map: ShallowRef<L.Map | null>
  /** WGS84 (platform) -> Leaflet LatLng in the base map's coordinate system. */
  toLatLng: (p: LatLon) => L.LatLngExpression
  /** Leaflet LatLng (user click) -> WGS84. */
  fromLatLng: (ll: L.LatLng) => LatLon
  /** True after the map was re-created for a base-map coordinate-system switch (view is carried over). */
  recreated: () => boolean
}

export const MAP_CONTEXT: InjectionKey<MapContext> = Symbol('map-context')
